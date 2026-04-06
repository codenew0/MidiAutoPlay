# player.py - MIDIキー再生エンジン（バックグラウンドスレッド処理）

import time
import threading
from pynput.keyboard import Controller

from src.constants import ALL_KEYS
from src.midi_analyzer import build_raw_events, midi_to_note_name


class MidiPlayer:
    """
    MIDIのキーシーケンスをキーボード入力として送出するエンジン。
    UI から独立しており、コールバック経由で状態を通知する。
    """

    def __init__(self):
        self.keyboard = Controller()
        self.is_playing = False
        self.play_thread: threading.Thread | None = None

        # 再生位置管理
        self.current_event_index = 0   # 現在のイベントインデックス
        self.seek_target_time: float | None = None  # シーク先の時間（秒）

        # コールバック（UI 側でセットする）
        self.on_status_update = None    # fn(message: str)
        self.on_progress_update = None  # fn(percent: float)
        self.on_playback_finished = None  # fn()
        self.on_error = None            # fn(message: str)

    # ------------------------------------------------------------------
    # 公開API
    # ------------------------------------------------------------------

    def start(self, midi_file: str, note_to_key: dict, muted_tracks: set,
              speed: float, key_sequence: list) -> None:
        """再生を開始する（別スレッドで実行）"""
        if self.play_thread and self.play_thread.is_alive():
            return

        self.is_playing = True
        self.play_thread = threading.Thread(
            target=self._play_sequence,
            args=(midi_file, note_to_key, muted_tracks, speed, key_sequence),
            daemon=True,
        )
        self.play_thread.start()

    def pause(self) -> None:
        """再生を一時停止する"""
        self.is_playing = False

    def reset(self) -> None:
        """再生位置を先頭に戻す"""
        self.is_playing = False
        self.current_event_index = 0
        self.seek_target_time = None
        self._release_all_keys()

    def seek(self, target_time: float) -> None:
        """指定秒数にシークする（再生中なら一旦停止が必要）"""
        self.is_playing = False
        self.seek_target_time = target_time
        self.current_event_index = -1  # -1 でシーク時間を使うことを示す
        self._release_all_keys()

    def wait_for_stop(self, timeout: float = 0.5) -> None:
        """再生スレッドが停止するのを待つ"""
        if self.play_thread and self.play_thread.is_alive():
            self.play_thread.join(timeout=timeout)

    # ------------------------------------------------------------------
    # 内部処理
    # ------------------------------------------------------------------

    def _release_all_keys(self) -> None:
        for key in ALL_KEYS:
            try:
                self.keyboard.release(key)
            except Exception:
                pass

    def _emit_status(self, msg: str) -> None:
        if self.on_status_update:
            self.on_status_update(msg)

    def _emit_progress(self, percent: float) -> None:
        if self.on_progress_update:
            self.on_progress_update(percent)

    def _play_sequence(self, midi_file: str, note_to_key: dict,
                       muted_tracks: set, speed: float, key_sequence: list) -> None:
        """バックグラウンドスレッドで実行される再生ループ"""
        total_duration = key_sequence[-1]['time'] if key_sequence else 0
        currently_pressed: set[str] = set()

        try:
            all_events = build_raw_events(midi_file, muted_tracks, note_to_key)

            # 開始インデックスと開始オフセットを決定
            if self.current_event_index == -1 and self.seek_target_time is not None:
                seek_time = self.seek_target_time
                self.seek_target_time = None
                lo, hi = 0, len(all_events)
                while lo < hi:
                    m = (lo + hi) // 2
                    if all_events[m]['time'] < seek_time:
                        lo = m + 1
                    else:
                        hi = m
                self.current_event_index = lo
                start_offset = seek_time
                self._emit_status(
                    f"シーク位置 {self.current_event_index}/{len(all_events)} から再開 "
                    f"({start_offset:.2f}秒)"
                )
            elif 0 < self.current_event_index < len(all_events):
                start_offset = all_events[self.current_event_index]['time']
                self._emit_status(
                    f"位置 {self.current_event_index}/{len(all_events)} から再開 "
                    f"({start_offset:.2f}秒)"
                )
            else:
                start_offset = 0.0
                self.current_event_index = 0

            play_start = time.time() - (start_offset / speed)

            for i in range(self.current_event_index, len(all_events)):
                if not self.is_playing:
                    if self.current_event_index != -1:
                        self.current_event_index = i
                    break

                event = all_events[i]
                target_time = event['time'] / speed
                wait = target_time - (time.time() - play_start)
                while wait > 0 and self.is_playing:
                    time.sleep(min(wait, 0.01))
                    wait = target_time - (time.time() - play_start)

                if not self.is_playing:
                    if self.current_event_index != -1:
                        self.current_event_index = i
                    break

                key = note_to_key.get(event['note'])
                if not key:
                    continue

                note_name = midi_to_note_name(event['note'])
                action = self._send_key(event['type'], key, currently_pressed)

                pressed_display = ' + '.join(sorted(currently_pressed)) or 'なし'
                track_info = f"Track{event['track']}"
                self._emit_status(
                    f"{event['time']:.3f}s | {action} {key}({note_name}) "
                    f"[{track_info}] | 現在押下: {pressed_display}"
                )

                progress = (event['time'] / total_duration * 100) if total_duration > 0 else 0
                self._emit_progress(progress)

            else:
                # for ループが最後まで回った = 最後まで再生完了
                if self.is_playing:
                    self.current_event_index = len(all_events)

            # 最後まで再生した場合は次の曲へ
            if self.is_playing and self.current_event_index >= len(all_events):
                self.current_event_index = 0
                if self.on_playback_finished:
                    self.on_playback_finished()

        except Exception as e:
            self._release_all_keys()
            if self.on_error:
                self.on_error(f"再生中にエラーが発生しました: {e}")
        finally:
            for key in list(currently_pressed):
                try:
                    self.keyboard.release(key)
                except Exception:
                    pass

    def _send_key(self, event_type: str, key: str, currently_pressed: set) -> str:
        """キーを送信して現在の押下セットを更新。アクション名を返す。"""
        if event_type == 'press':
            if key not in currently_pressed:
                self.keyboard.press(key)
                currently_pressed.add(key)
                return "PRESS"
            return "ALREADY PRESSED"
        else:  # release
            if key in currently_pressed:
                self.keyboard.release(key)
                currently_pressed.remove(key)
                return "RELEASE"
            return "ALREADY RELEASED"