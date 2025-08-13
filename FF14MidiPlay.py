import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import mido
import threading
import time
import json
from typing import Dict, List
import os
from collections import defaultdict
import pynput
from pynput.keyboard import Key, Controller


class MidiPlayerUI:
    def __init__(self, root):
        self.root = root
        self.root.title("MIDI to Keys Player")
        self.root.geometry("1000x700")
        self.root.configure(bg='#f0f0f0')

        # キーボードコントローラー
        self.keyboard = Controller()

        # データ保存用
        self.midi_file = None
        self.midi_info = None
        self.key_sequence = []
        self.is_playing = False
        self.play_thread = None

        # 音名からキーへのマッピング
        self.note_to_key = {
            # オクターブ0-2 (低音域) - C, C#, D, D#, E, F, F#, G, G#, A, Bb, B
            12: 'z', 13: 's', 14: 'x', 15: 'd', 16: 'c', 17: 'v', 18: 'g', 19: 'b', 20: 'h', 21: 'n', 22: 'j', 23: 'm',
            24: 'z', 25: 's', 26: 'x', 27: 'd', 28: 'c', 29: 'v', 30: 'g', 31: 'b', 32: 'h', 33: 'n', 34: 'j', 35: 'm',
            36: 'z', 37: 's', 38: 'x', 39: 'd', 40: 'c', 41: 'v', 42: 'g', 43: 'b', 44: 'h', 45: 'n', 46: 'j', 47: 'm',

            # オクターブ3-4 (中音域) - C, C#, D, D#, E, F, F#, G, G#, A, Bb, B
            48: 'q', 49: '2', 50: 'w', 51: '3', 52: 'e', 53: 'r', 54: '5', 55: 't', 56: '6', 57: 'y', 58: '7', 59: 'u',
            60: 'q', 61: '2', 62: 'w', 63: '3', 64: 'e', 65: 'r', 66: '5', 67: 't', 68: '6', 69: 'y', 70: '7', 71: 'u',

            # オクターブ5-6 (高音域) - C, C#, D, Eb, E, F, F#, G, G#, A, Bb, B, C
            72: 'i', 73: '9', 74: 'o', 75: '0', 76: 'p', 77: 'l', 78: '-', 79: '@', 80: '^', 81: ';', 82: '\\', 83: '[',
            84: ':',
            85: '9', 86: 'o', 87: '0', 88: 'p', 89: 'l', 90: '-', 91: '@', 92: '^', 93: ';', 94: '\\', 95: '[',
        }

        # MIDI番号から音名への変換
        self.note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'Bb', 'B']

        # 楽器名のマッピング
        self.instrument_names = {
            1: "Acoustic Grand Piano", 2: "Bright Acoustic Piano", 3: "Electric Grand Piano", 4: "Honky-tonk Piano",
            5: "Electric Piano 1", 6: "Electric Piano 2", 7: "Harpsichord", 8: "Clavi",
            9: "Celesta", 10: "Glockenspiel", 11: "Music Box", 12: "Vibraphone",
            13: "Marimba", 14: "Xylophone", 15: "Tubular Bells", 16: "Dulcimer",
            17: "Drawbar Organ", 18: "Percussive Organ", 19: "Rock Organ", 20: "Church Organ",
            21: "Reed Organ", 22: "Accordion", 23: "Harmonica", 24: "Tango Accordion",
            25: "Acoustic Guitar (nylon)", 26: "Acoustic Guitar (steel)", 27: "Electric Guitar (jazz)",
            28: "Electric Guitar (clean)", 29: "Electric Guitar (muted)", 30: "Overdriven Guitar",
            31: "Distortion Guitar", 32: "Guitar harmonics", 33: "Acoustic Bass", 34: "Electric Bass (finger)",
            35: "Electric Bass (pick)", 36: "Fretless Bass", 37: "Slap Bass 1", 38: "Slap Bass 2",
            39: "Synth Bass 1", 40: "Synth Bass 2", 41: "Violin", 42: "Viola", 43: "Cello", 44: "Contrabass",
            45: "Tremolo Strings", 46: "Pizzicato Strings", 47: "Orchestral Harp", 48: "Timpani",
            49: "String Ensemble 1", 50: "String Ensemble 2", 51: "SynthStrings 1", 52: "SynthStrings 2"
        }

        self.create_widgets()

    def create_widgets(self):
        # メインフレーム
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # ファイル選択部分
        file_frame = ttk.LabelFrame(main_frame, text="MIDIファイル選択", padding="10")
        file_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        self.file_path_var = tk.StringVar()
        self.file_entry = ttk.Entry(file_frame, textvariable=self.file_path_var, width=60, state='readonly')
        self.file_entry.grid(row=0, column=0, padx=(0, 10))

        self.browse_btn = ttk.Button(file_frame, text="ファイルを選択", command=self.browse_file)
        self.browse_btn.grid(row=0, column=1, padx=(0, 10))

        self.analyze_btn = ttk.Button(file_frame, text="解析実行", command=self.analyze_file, state='disabled')
        self.analyze_btn.grid(row=0, column=2)

        # MIDI情報表示部分
        info_frame = ttk.LabelFrame(main_frame, text="MIDI情報", padding="10")
        info_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))

        # 基本情報
        basic_frame = ttk.Frame(info_frame)
        basic_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))

        self.info_text = scrolledtext.ScrolledText(basic_frame, height=8, width=80, wrap=tk.WORD)
        self.info_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # トラック情報
        track_frame = ttk.LabelFrame(info_frame, text="トラック詳細")
        track_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(10, 0))

        # トラック情報用のTreeview
        self.track_tree = ttk.Treeview(track_frame, columns=('name', 'instrument', 'notes', 'duration'), height=6)
        self.track_tree.heading('#0', text='トラック')
        self.track_tree.heading('name', text='名前')
        self.track_tree.heading('instrument', text='楽器')
        self.track_tree.heading('notes', text='音符数')
        self.track_tree.heading('duration', text='長さ(秒)')

        self.track_tree.column('#0', width=80)
        self.track_tree.column('name', width=150)
        self.track_tree.column('instrument', width=200)
        self.track_tree.column('notes', width=80)
        self.track_tree.column('duration', width=80)

        self.track_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # スクロールバー
        track_scrollbar = ttk.Scrollbar(track_frame, orient=tk.VERTICAL, command=self.track_tree.yview)
        track_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.track_tree.configure(yscrollcommand=track_scrollbar.set)

        # 再生コントロール部分
        control_frame = ttk.LabelFrame(main_frame, text="再生コントロール", padding="10")
        control_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        # 再生ボタン
        self.play_btn = ttk.Button(control_frame, text="▶ PLAY", command=self.toggle_play, state='disabled')
        self.play_btn.grid(row=0, column=0, padx=(0, 10))

        self.stop_btn = ttk.Button(control_frame, text="⏹ STOP", command=self.stop_play, state='disabled')
        self.stop_btn.grid(row=0, column=1, padx=(0, 10))

        # 速度調整
        ttk.Label(control_frame, text="速度:").grid(row=0, column=2, padx=(20, 5))
        self.speed_var = tk.DoubleVar(value=1.0)
        self.speed_scale = ttk.Scale(control_frame, from_=0.1, to=2.0, variable=self.speed_var, orient=tk.HORIZONTAL,
                                     length=200)
        self.speed_scale.grid(row=0, column=3, padx=(0, 10))

        self.speed_label = ttk.Label(control_frame, text="1.0x")
        self.speed_label.grid(row=0, column=4)
        self.speed_var.trace('w', self.update_speed_label)

        # プログレスバー
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(control_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.grid(row=1, column=0, columnspan=5, sticky=(tk.W, tk.E), pady=(10, 0))

        # 現在の状態表示
        status_frame = ttk.Frame(main_frame)
        status_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E))

        self.status_text = scrolledtext.ScrolledText(status_frame, height=8, width=80, wrap=tk.WORD)
        self.status_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # グリッドの重み設定
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
        info_frame.columnconfigure(0, weight=1)
        info_frame.rowconfigure(1, weight=1)
        track_frame.columnconfigure(0, weight=1)
        track_frame.rowconfigure(0, weight=1)
        control_frame.columnconfigure(3, weight=1)
        status_frame.columnconfigure(0, weight=1)
        status_frame.rowconfigure(0, weight=1)

    def browse_file(self):
        """ファイル選択ダイアログを開く"""
        file_path = filedialog.askopenfilename(
            title="MIDIファイルを選択",
            filetypes=[("MIDI files", "*.mid *.midi"), ("All files", "*.*")]
        )
        if file_path:
            self.file_path_var.set(file_path)
            self.midi_file = file_path
            self.analyze_btn.config(state='normal')
            self.log("ファイルが選択されました: " + os.path.basename(file_path))

    def analyze_file(self):
        """MIDIファイルを解析する"""
        if not self.midi_file:
            return

        try:
            self.log("MIDIファイルを解析中...")
            self.midi_info = self.analyze_midi_file(self.midi_file)
            self.key_sequence = self.convert_to_key_sequence(self.midi_file)

            self.display_midi_info()
            self.display_track_info()

            self.play_btn.config(state='normal')
            self.log(f"解析完了！{len(self.key_sequence)}個のキーイベントが見つかりました。")

        except Exception as e:
            messagebox.showerror("エラー", f"ファイル解析中にエラーが発生しました:\n{str(e)}")
            self.log(f"エラー: {str(e)}")

    def analyze_midi_file(self, filepath):
        """MIDIファイルを解析して基本情報を取得"""
        mid = mido.MidiFile(filepath)

        info = {
            'filename': os.path.basename(filepath),
            'format': mid.type,
            'track_count': len(mid.tracks),
            'ticks_per_beat': mid.ticks_per_beat,
            'total_time': mid.length,
            'tracks': []
        }

        current_tempo = 500000
        current_bpm = 120

        for i, track in enumerate(mid.tracks):
            track_info = {
                'track_number': i,
                'name': '',
                'instruments': set(),
                'has_notes': False,
                'note_count': 0,
                'duration': 0
            }

            current_time = 0
            for msg in track:
                current_time += msg.time

                if msg.type == 'set_tempo':
                    current_tempo = msg.tempo
                    current_bpm = mido.tempo2bpm(current_tempo)
                elif msg.type == 'track_name':
                    track_info['name'] = msg.name
                elif msg.type == 'program_change':
                    instrument = self.instrument_names.get(msg.program + 1, f"Program {msg.program}")
                    track_info['instruments'].add(instrument)
                elif msg.type == 'note_on' and msg.velocity > 0:
                    track_info['has_notes'] = True
                    track_info['note_count'] += 1

            track_info['duration'] = mido.tick2second(current_time, mid.ticks_per_beat, current_tempo)
            track_info['instruments'] = list(track_info['instruments'])
            info['tracks'].append(track_info)

        info['bpm'] = round(current_bpm, 2)
        return info

    def convert_to_key_sequence(self, filepath):
        """MIDIファイルをキーシーケンスに変換"""
        mid = mido.MidiFile(filepath)

        events = []
        current_tempo = 500000

        for track_num, track in enumerate(mid.tracks):
            current_time = 0
            for msg in track:
                current_time += msg.time

                if msg.type == 'set_tempo':
                    current_tempo = msg.tempo
                elif msg.type == 'note_on' and msg.velocity > 0:
                    time_in_seconds = mido.tick2second(current_time, mid.ticks_per_beat, current_tempo)
                    events.append({
                        'time': time_in_seconds,
                        'type': 'note_on',
                        'note': msg.note,
                        'velocity': msg.velocity,
                        'track': track_num
                    })
                elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                    time_in_seconds = mido.tick2second(current_time, mid.ticks_per_beat, current_tempo)
                    events.append({
                        'time': time_in_seconds,
                        'type': 'note_off',
                        'note': msg.note,
                        'track': track_num
                    })

        events.sort(key=lambda x: x['time'])

        key_sequence = []
        active_notes = set()
        time_groups = defaultdict(list)

        # イベントを時間でグループ化
        for event in events:
            time_groups[round(event['time'], 3)].append(event)

        # 各時間ポイントでキーイベントを生成
        for current_time in sorted(time_groups.keys()):
            events_at_time = time_groups[current_time]

            for event in events_at_time:
                if event['type'] == 'note_on':
                    active_notes.add(event['note'])
                elif event['type'] == 'note_off':
                    active_notes.discard(event['note'])

            if active_notes:
                keys = []
                notes = []
                for note in sorted(active_notes):
                    if note in self.note_to_key:
                        key = self.note_to_key[note]
                        if key not in keys:
                            keys.append(key)
                    notes.append(self.midi_to_note_name(note))

                if keys:
                    key_sequence.append({
                        'time': current_time,
                        'keys': keys,
                        'notes': notes,
                        'active_note_count': len(active_notes)
                    })

        return key_sequence

    def midi_to_note_name(self, midi_number):
        """MIDI番号を音名に変換"""
        octave = (midi_number // 12) - 1
        note = self.note_names[midi_number % 12]
        return f"{note}{octave}"

    def display_midi_info(self):
        """MIDI基本情報を表示"""
        if not self.midi_info:
            return

        info_text = f"""ファイル名: {self.midi_info['filename']}
フォーマット: Type {self.midi_info['format']}
BPM: {self.midi_info['bpm']}
総時間: {self.midi_info['total_time']:.2f} 秒
トラック数: {self.midi_info['track_count']}
時間分解能: {self.midi_info['ticks_per_beat']} ticks/beat
キーイベント数: {len(self.key_sequence)}
"""

        self.info_text.delete(1.0, tk.END)
        self.info_text.insert(1.0, info_text)

    def display_track_info(self):
        """トラック情報を表示"""
        if not self.midi_info:
            return

        # 既存のアイテムをクリア
        for item in self.track_tree.get_children():
            self.track_tree.delete(item)

        # トラック情報を追加
        for track in self.midi_info['tracks']:
            instruments_str = ', '.join(track['instruments']) if track['instruments'] else 'なし'
            notes_str = str(track['note_count']) if track['has_notes'] else '0'

            self.track_tree.insert('', 'end',
                                   text=f"Track {track['track_number']}",
                                   values=(track['name'] or '(名前なし)',
                                           instruments_str,
                                           notes_str,
                                           f"{track['duration']:.2f}"))

    def toggle_play(self):
        """再生/一時停止を切り替える"""
        if not self.key_sequence:
            messagebox.showwarning("警告", "キーシーケンスがありません。まずMIDIファイルを解析してください。")
            return

        if self.is_playing:
            self.pause_play()
        else:
            self.start_play()

    def start_play(self):
        """再生を開始"""
        if self.play_thread and self.play_thread.is_alive():
            return

        self.is_playing = True
        self.play_btn.config(text="⏸ PAUSE")
        self.stop_btn.config(state='normal')

        self.root.iconify()

        self.play_thread = threading.Thread(target=self.play_sequence, daemon=True)
        self.play_thread.start()

        self.log("再生を開始しました。")

    def pause_play(self):
        """再生を一時停止"""
        self.is_playing = False
        self.play_btn.config(text="▶ PLAY")
        self.log("再生を一時停止しました。")

    def stop_play(self):
        """再生を停止"""
        self.is_playing = False
        self.play_btn.config(text="▶ PLAY", state='normal')
        self.stop_btn.config(state='disabled')
        self.progress_var.set(0)

        # 念のため全てのキーを離す
        try:
            for key in ['z', 's', 'x', 'd', 'c', 'v', 'g', 'b', 'h', 'n', 'j', 'm',
                        'q', '2', 'w', '3', 'e', 'r', '5', 't', '6', 'y', '7', 'u',
                        'i', '9', 'o', '0', 'p', 'l', '-', '@', '^', ';', '\\', '[', ':']:
                try:
                    self.keyboard.release(key)
                except:
                    pass
        except:
            pass

        self.log("再生を停止しました。")

    def play_sequence(self):
        """キーシーケンスを再生"""
        if not self.key_sequence:
            return

        speed_multiplier = self.speed_var.get()
        total_duration = self.key_sequence[-1]['time'] if self.key_sequence else 0
        play_start_time = time.time()

        # 現在押されているキーを管理
        currently_pressed = set()

        try:
            # 全てのイベント（note_on と note_off）を時間順で処理
            all_events = []

            # MIDIファイルから正確なイベントを再取得
            mid = mido.MidiFile(self.midi_file)
            current_tempo = 500000

            for track_num, track in enumerate(mid.tracks):
                current_time = 0
                for msg in track:
                    current_time += msg.time

                    if msg.type == 'set_tempo':
                        current_tempo = msg.tempo
                    elif msg.type == 'note_on' and msg.velocity > 0:
                        time_in_seconds = mido.tick2second(current_time, mid.ticks_per_beat, current_tempo)
                        all_events.append({
                            'time': time_in_seconds,
                            'type': 'press',
                            'note': msg.note,
                            'velocity': msg.velocity
                        })
                    elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                        time_in_seconds = mido.tick2second(current_time, mid.ticks_per_beat, current_tempo)
                        all_events.append({
                            'time': time_in_seconds,
                            'type': 'release',
                            'note': msg.note
                        })

            # 時間順にソート
            all_events.sort(key=lambda x: x['time'])

            self.root.after(0, self.log, f"総イベント数: {len(all_events)}個を再生開始")

            for i, event in enumerate(all_events):
                if not self.is_playing:
                    break

                # 正確な時間まで待機
                target_time = event['time'] / speed_multiplier
                elapsed_time = time.time() - play_start_time
                wait_time = target_time - elapsed_time

                if wait_time > 0:
                    time.sleep(wait_time)

                if not self.is_playing:
                    break

                # キーマッピングを取得
                key = self.note_to_key.get(event['note'])
                if not key:
                    continue

                note_name = self.midi_to_note_name(event['note'])

                try:
                    if event['type'] == 'press':
                        if key not in currently_pressed:
                            self.keyboard.press(key)
                            currently_pressed.add(key)
                            action = "PRESS"
                        else:
                            action = "ALREADY PRESSED"
                    elif event['type'] == 'release':
                        if key in currently_pressed:
                            self.keyboard.release(key)
                            currently_pressed.remove(key)
                            action = "RELEASE"
                        else:
                            action = "ALREADY RELEASED"

                    # 現在の状態を表示
                    pressed_keys = sorted(list(currently_pressed))
                    status_msg = f"{event['time']:.3f}s | {action} {key}({note_name}) | 現在押下: {' + '.join(pressed_keys) if pressed_keys else 'なし'}"

                    # UIを更新
                    self.root.after(0, self.update_play_status, status_msg)

                    # プログレスバーを更新
                    progress = (event['time'] / total_duration) * 100 if total_duration > 0 else 0
                    self.root.after(0, self.progress_var.set, progress)

                except Exception as e:
                    error_msg = f"キー入力エラー ({key}={note_name}): {e}"
                    self.root.after(0, self.log, error_msg)

            # 再生完了時に全てのキーを離す
            for key in list(currently_pressed):
                try:
                    self.keyboard.release(key)
                except:
                    pass

            # 再生完了
            if self.is_playing:
                self.root.after(0, self.stop_play)
                self.root.after(0, self.log, "再生が完了しました。")

        except Exception as e:
            # エラー時も全てのキーを離す
            for key in list(currently_pressed):
                try:
                    self.keyboard.release(key)
                except:
                    pass
            self.root.after(0, self.log, f"再生中にエラーが発生しました: {str(e)}")
            self.root.after(0, self.stop_play)

    def update_play_status(self, message):
        """再生状況を更新"""
        self.log(message)
        # 最新の状態を表示するためにスクロール
        self.status_text.see(tk.END)

    def update_speed_label(self, *args):
        """速度ラベルを更新"""
        speed = self.speed_var.get()
        self.speed_label.config(text=f"{speed:.1f}x")

    def log(self, message):
        """ログメッセージを表示"""
        timestamp = time.strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}\n"
        self.status_text.insert(tk.END, log_message)
        self.status_text.see(tk.END)
        self.root.update_idletasks()


def main():
    root = tk.Tk()
    app = MidiPlayerUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()