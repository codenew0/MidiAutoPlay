# midi_analyzer.py - MIDIファイルの解析ロジック

import os
import mido
from collections import Counter
from itertools import groupby

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

    # MIDI の既定テンポは 120 BPM。同じ tick に複数の指定がある場合は
    # 後から収集した指定を採用する。
    merged: dict[int, int] = {0: 500000}
    for tick, tempo in tempo_map:
        merged[tick] = tempo
    return sorted(merged.items())


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

    # テンポ変更を累積時間へ正しく変換して、時間加重平均BPMを計算
    tempo_map = build_tempo_map(mid)
    tempo_changes = [
        (
            tick_to_second(tick, tempo_map, mid.ticks_per_beat),
            tempo,
            mido.tempo2bpm(tempo),
        )
        for tick, tempo in tempo_map
    ]

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

        current_tick = 0

        for msg in track:
            current_tick += msg.time
            if msg.type == 'track_name':
                track_info['name'] = msg.name
            elif msg.type == 'program_change':
                instrument = INSTRUMENT_NAMES.get(msg.program + 1, f"Program {msg.program}")
                track_info['instruments'].add(instrument)
            elif msg.type == 'note_on' and msg.velocity > 0:
                track_info['has_notes'] = True
                track_info['note_count'] += 1

        track_info['duration'] = tick_to_second(
            current_tick, tempo_map, mid.ticks_per_beat
        )
        track_info['instruments'] = list(track_info['instruments'])
        info['tracks'].append(track_info)

    return info


def analyze_midi_range(
    filepath: str,
    keyboard_min_note: int = KEYBOARD_MIN_NOTE,
    keyboard_max_note: int = KEYBOARD_MAX_NOTE,
) -> tuple[int, list[str]]:
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
    keyboard_range = keyboard_max_note - keyboard_min_note

    logs.append(
        f"音域分析: 元の範囲 {midi_to_note_name(min_note)}-{midi_to_note_name(max_note)} "
        f"(幅: {midi_range}半音)"
    )

    midi_center = (min_note + max_note) / 2
    keyboard_center = (keyboard_min_note + keyboard_max_note) / 2
    shift = round((keyboard_center - midi_center) / 12) * 12

    if midi_range > keyboard_range:
        logs.append(
            f"警告: 曲の音域({midi_range}半音)が演奏範囲({keyboard_range}半音)を超えています"
        )
    else:
        shifted_min = min_note + shift
        shifted_max = max_note + shift
        if shifted_min < keyboard_min_note:
            additional = keyboard_min_note - shifted_min
            shift += (additional // 12 + (1 if additional % 12 > 0 else 0)) * 12
        elif shifted_max > keyboard_max_note:
            additional = shifted_max - keyboard_max_note
            shift -= (additional // 12 + (1 if additional % 12 > 0 else 0)) * 12

    final_min = min_note + shift
    final_max = max_note + shift

    logs.append(f"オクターブシフト: {shift // 12:+d}オクターブ ({shift:+d}半音)")
    logs.append(f"シフト後の範囲: {midi_to_note_name(final_min)}-{midi_to_note_name(final_max)}")

    out_low = max(0, keyboard_min_note - final_min)
    out_high = max(0, final_max - keyboard_max_note)
    if out_low > 0:
        logs.append(f"警告: {out_low}半音が低音側で範囲外です")
    if out_high > 0:
        logs.append(f"警告: {out_high}半音が高音側で範囲外です")

    return shift, logs


def apply_octave_shift(
    shift: int, base_mapping: dict | None = None
) -> tuple[dict, list[str]]:
    """
    オクターブシフトを適用した新しいノート→キーのマッピングを返す。
    返り値: (note_to_key, log_messages)
    """
    note_to_key: dict[int, str] = {}
    logs: list[str] = []

    mapping = BASE_NOTE_TO_KEY if base_mapping is None else base_mapping
    for original_note, key in mapping.items():
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
    active_notes: Counter[int] = Counter()

    # 時刻を丸めると短い音の on/off が同一時刻に潰れるため、計算された
    # float 値そのものが等しいイベントだけをまとめる。
    for current_time, grouped_events in groupby(events, key=lambda event: event['time']):
        for event in grouped_events:
            if event['type'] == 'note_on':
                active_notes[event['note']] += 1
            elif event['type'] == 'note_off':
                note = event['note']
                if active_notes[note] > 1:
                    active_notes[note] -= 1
                else:
                    active_notes.pop(note, None)

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
