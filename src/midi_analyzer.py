# midi_analyzer.py - MIDIファイルの解析ロジック

import os
import mido
from collections import defaultdict

from src.constants import (
    KEYBOARD_MIN_NOTE, KEYBOARD_MAX_NOTE,
    BASE_NOTE_TO_KEY, NOTE_NAMES, INSTRUMENT_NAMES,
)


def midi_to_note_name(midi_number: int) -> str:
    """MIDI番号を音名に変換（例: 60 -> 'C4'）"""
    octave = (midi_number // 12) - 1
    note = NOTE_NAMES[midi_number % 12]
    return f"{note}{octave}"


def build_tempo_map(mid: mido.MidiFile) -> list[tuple[int, int]]:
    """
    全トラックからテンポ変化を収集してテンポマップを返す。
    返り値: [(累積tick, tempo), ...] (tick昇順ソート済み)
    デフォルトテンポ (500000 μs/beat = 120 BPM) が先頭に含まれる。
    """
    tempo_map: list[tuple[int, int]] = []
    for track in mid.tracks:
        current_tick = 0
        for msg in track:
            current_tick += msg.time
            if msg.type == 'set_tempo':
                tempo_map.append((current_tick, msg.tempo))

    tempo_map.sort(key=lambda x: x[0])
    if not tempo_map:
        tempo_map = [(0, 500000)]
    return tempo_map


def tick_to_second(tick: int, tempo_map: list[tuple[int, int]], ticks_per_beat: int) -> float:
    """テンポマップを考慮して tick を秒数に変換"""
    time_sec = 0.0
    prev_tick = 0
    current_tempo = tempo_map[0][1]

    for tempo_tick, tempo in tempo_map:
        if tick <= tempo_tick:
            time_sec += mido.tick2second(tick - prev_tick, ticks_per_beat, current_tempo)
            return time_sec
        else:
            time_sec += mido.tick2second(tempo_tick - prev_tick, ticks_per_beat, current_tempo)
            prev_tick = tempo_tick
            current_tempo = tempo

    # 最後のテンポ変化以降
    if tick > prev_tick:
        time_sec += mido.tick2second(tick - prev_tick, ticks_per_beat, current_tempo)
    return time_sec


def analyze_midi_file(filepath: str) -> dict:
    """
    MIDIファイルを解析して基本情報を返す。
    返り値の辞書キー:
      filename, format, track_count, ticks_per_beat,
      total_time, bpm, bpm_changes, tracks
    """
    mid = mido.MidiFile(filepath, clip=True)

    info = {
        'filename': os.path.basename(filepath),
        'format': mid.type,
        'track_count': len(mid.tracks),
        'ticks_per_beat': mid.ticks_per_beat,
        'total_time': mid.length,
        'tracks': [],
    }

    # テンポ変化を全トラックから収集して加重平均BPMを計算
    tempo_changes: list[tuple[float, int, float]] = []  # (時間秒, tempo, bpm)
    current_tempo = 500000

    for track in mid.tracks:
        current_tick = 0
        for msg in track:
            current_tick += msg.time
            if msg.type == 'set_tempo':
                time_sec = mido.tick2second(current_tick, mid.ticks_per_beat, current_tempo)
                current_tempo = msg.tempo
                current_bpm = mido.tempo2bpm(current_tempo)
                tempo_changes.append((time_sec, current_tempo, current_bpm))

    if not tempo_changes:
        tempo_changes.append((0, 500000, 120.0))

    tempo_changes.sort(key=lambda x: x[0])

    total_time = mid.length
    weighted_bpm_sum = 0.0
    for i, (time_sec, tempo, bpm) in enumerate(tempo_changes):
        if i + 1 < len(tempo_changes):
            duration = tempo_changes[i + 1][0] - time_sec
        else:
            duration = total_time - time_sec
        weighted_bpm_sum += bpm * duration

    average_bpm = weighted_bpm_sum / total_time if total_time > 0 else tempo_changes[0][2]
    info['bpm'] = round(average_bpm, 2)
    info['bpm_changes'] = len(tempo_changes)

    # トラック情報を収集
    for i, track in enumerate(mid.tracks):
        track_info = {
            'track_number': i,
            'name': '',
            'instruments': set(),
            'has_notes': False,
            'note_count': 0,
            'duration': 0,
        }

        current_time = 0
        track_tempo = 500000

        for msg in track:
            current_time += msg.time
            if msg.type == 'set_tempo':
                track_tempo = msg.tempo
            elif msg.type == 'track_name':
                track_info['name'] = msg.name
            elif msg.type == 'program_change':
                instrument = INSTRUMENT_NAMES.get(msg.program + 1, f"Program {msg.program}")
                track_info['instruments'].add(instrument)
            elif msg.type == 'note_on' and msg.velocity > 0:
                track_info['has_notes'] = True
                track_info['note_count'] += 1

        track_info['duration'] = mido.tick2second(current_time, mid.ticks_per_beat, track_tempo)
        track_info['instruments'] = list(track_info['instruments'])
        info['tracks'].append(track_info)

    return info


def analyze_midi_range(filepath: str) -> tuple[int, list[str]]:
    """
    MIDIファイルの音域を分析して最適なオクターブシフト量を計算する。
    返り値: (shift_semitones, log_messages)
    """
    mid = mido.MidiFile(filepath, clip=True)
    logs: list[str] = []

    all_notes = [
        msg.note
        for track in mid.tracks
        for msg in track
        if msg.type == 'note_on' and msg.velocity > 0
    ]

    if not all_notes:
        return 0, logs

    min_note = min(all_notes)
    max_note = max(all_notes)
    midi_range = max_note - min_note
    keyboard_range = KEYBOARD_MAX_NOTE - KEYBOARD_MIN_NOTE  # 24半音

    logs.append(
        f"音域分析: 元の範囲 {midi_to_note_name(min_note)}-{midi_to_note_name(max_note)} "
        f"(幅: {midi_range}半音)"
    )

    midi_center = (min_note + max_note) / 2
    keyboard_center = (KEYBOARD_MIN_NOTE + KEYBOARD_MAX_NOTE) / 2
    shift = round((keyboard_center - midi_center) / 12) * 12

    if midi_range > keyboard_range:
        logs.append(
            f"警告: 曲の音域({midi_range}半音)がキーボード範囲({keyboard_range}半音)を超えています"
        )
    else:
        shifted_min = min_note + shift
        shifted_max = max_note + shift
        if shifted_min < KEYBOARD_MIN_NOTE:
            additional = KEYBOARD_MIN_NOTE - shifted_min
            shift += (additional // 12 + (1 if additional % 12 > 0 else 0)) * 12
        elif shifted_max > KEYBOARD_MAX_NOTE:
            additional = shifted_max - KEYBOARD_MAX_NOTE
            shift -= (additional // 12 + (1 if additional % 12 > 0 else 0)) * 12

    final_min = min_note + shift
    final_max = max_note + shift

    logs.append(f"オクターブシフト: {shift // 12:+d}オクターブ ({shift:+d}半音)")
    logs.append(f"シフト後の範囲: {midi_to_note_name(final_min)}-{midi_to_note_name(final_max)}")

    out_low = max(0, KEYBOARD_MIN_NOTE - final_min)
    out_high = max(0, final_max - KEYBOARD_MAX_NOTE)
    if out_low > 0:
        logs.append(f"警告: {out_low}半音が低音側で範囲外です")
    if out_high > 0:
        logs.append(f"警告: {out_high}半音が高音側で範囲外です")

    return shift, logs


def apply_octave_shift(shift: int) -> tuple[dict, list[str]]:
    """
    オクターブシフトを適用した新しいノート→キーのマッピングを返す。
    返り値: (note_to_key, log_messages)
    """
    note_to_key: dict[int, str] = {}
    logs: list[str] = []

    for original_note, key in BASE_NOTE_TO_KEY.items():
        shifted_note = original_note - shift
        if 0 <= shifted_note <= 127:
            note_to_key[shifted_note] = key

    if note_to_key:
        mapped_notes = sorted(note_to_key.keys())
        logs.append(
            f"マッピング範囲: {midi_to_note_name(mapped_notes[0])}-"
            f"{midi_to_note_name(mapped_notes[-1])} ({len(mapped_notes)}キー)"
        )

    return note_to_key, logs


def convert_to_key_sequence(filepath: str, note_to_key: dict) -> list[dict]:
    """
    MIDIファイルをキーシーケンスに変換する（テンポ変化対応）。
    返り値: [{'time': float, 'keys': [...], 'notes': [...], 'active_note_count': int}, ...]
    """
    mid = mido.MidiFile(filepath, clip=True)
    tempo_map = build_tempo_map(mid)

    events: list[dict] = []
    for track_num, track in enumerate(mid.tracks):
        current_tick = 0
        for msg in track:
            current_tick += msg.time
            if msg.type == 'note_on' and msg.velocity > 0:
                events.append({
                    'time': tick_to_second(current_tick, tempo_map, mid.ticks_per_beat),
                    'type': 'note_on',
                    'note': msg.note,
                    'velocity': msg.velocity,
                    'track': track_num,
                })
            elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                events.append({
                    'time': tick_to_second(current_tick, tempo_map, mid.ticks_per_beat),
                    'type': 'note_off',
                    'note': msg.note,
                    'track': track_num,
                })

    events.sort(key=lambda x: x['time'])

    key_sequence: list[dict] = []
    active_notes: set[int] = set()
    time_groups: defaultdict[float, list] = defaultdict(list)

    for event in events:
        time_groups[round(event['time'], 3)].append(event)

    for current_time in sorted(time_groups.keys()):
        for event in time_groups[current_time]:
            if event['type'] == 'note_on':
                active_notes.add(event['note'])
            elif event['type'] == 'note_off':
                active_notes.discard(event['note'])

        if active_notes:
            keys = []
            notes = []
            for note in sorted(active_notes):
                if note in note_to_key:
                    key = note_to_key[note]
                    if key not in keys:
                        keys.append(key)
                notes.append(midi_to_note_name(note))

            if keys:
                key_sequence.append({
                    'time': current_time,
                    'keys': keys,
                    'notes': notes,
                    'active_note_count': len(active_notes),
                })

    return key_sequence


def build_raw_events(filepath: str, muted_tracks: set, note_to_key: dict) -> list[dict]:
    """
    再生用のローレベルイベント一覧（press/release）を返す。
    ミュートトラックはスキップされる。
    返り値: [{'time': float, 'type': 'press'|'release', 'note': int, 'track': int}, ...]
    """
    mid = mido.MidiFile(filepath, clip=True)
    tempo_map = build_tempo_map(mid)

    all_events: list[dict] = []
    for track_num, track in enumerate(mid.tracks):
        if track_num in muted_tracks:
            continue
        current_tick = 0
        for msg in track:
            current_tick += msg.time
            t = tick_to_second(current_tick, tempo_map, mid.ticks_per_beat)
            if msg.type == 'note_on' and msg.velocity > 0:
                all_events.append({
                    'time': t, 'type': 'press',
                    'note': msg.note, 'velocity': msg.velocity, 'track': track_num,
                })
            elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                all_events.append({
                    'time': t, 'type': 'release',
                    'note': msg.note, 'track': track_num,
                })

    all_events.sort(key=lambda x: x['time'])
    return all_events
