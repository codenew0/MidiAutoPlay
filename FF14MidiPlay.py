# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import mido
import threading
import time
import os
from collections import defaultdict
from pynput.keyboard import Controller
from pynput import keyboard  # グローバルホットキー用

# --------------------------------------------------------------
# プレイリスト管理クラス
# --------------------------------------------------------------
class Playlist:
    def __init__(self):
        self.files = []
        self.index = -1

    def load_folder(self, folder_path: str) -> None:
        midi_files = [f for f in os.listdir(folder_path)
                     if f.lower().endswith(('.mid', '.midi'))]
        midi_files.sort()
        self.files = [os.path.join(folder_path, f) for f in midi_files]
        self.index = 0 if self.files else -1

    def has_next(self):
        return self.index + 1 < len(self.files)

    def has_prev(self):
        return self.index - 1 >= 0

    def next(self):
        if self.has_next():
            self.index += 1
            return self.current_path()
        return None

    def prev(self):
        if self.has_prev():
            self.index -= 1
            return self.current_path()
        return None

    def current_path(self):
        if 0 <= self.index < len(self.files):
            return self.files[self.index]
        return None


# --------------------------------------------------------------
# グローバルショートカットハンドラ
# --------------------------------------------------------------
class HotkeyHandler:
    """
    Ctrl+Alt+P : Play / Pause 切替
    Ctrl+Alt+S : Stop
    """
    def __init__(self, ui):
        self.ui = ui
        self.hotkeys = keyboard.GlobalHotKeys({
            '<ctrl>+<alt>+p': self._toggle,
            '<ctrl>+<alt>+s': self._stop
        })
        self.hotkeys.start()

    def _toggle(self):
        self.ui.root.after(0, self.ui.toggle_play)

    def _stop(self):
        self.ui.root.after(0, self.ui.stop_play)


# --------------------------------------------------------------
# メイン UI クラス（元コードにプレイリスト・ショートカットを追加）
# --------------------------------------------------------------
class MidiPlayerUI:
    def __init__(self, root):
        self.root = root
        self.root.title("MIDI to Keys Player")
        self.root.geometry("1000x800")
        self.root.configure(bg='#f0f0f0')

        self.keyboard = Controller()
        self.midi_file = None
        self.midi_info = None
        self.key_sequence = []
        self.is_playing = False
        self.play_thread = None

        # キーマッピングは元コードと同じ（省略せずに保持）
        self.note_to_key = {
            12: 'z', 13: 's', 14: 'x', 15: 'd', 16: 'c', 17: 'v', 18: 'g', 19: 'b',
            20: 'h', 21: 'n', 22: 'j', 23: 'm', 24: 'z', 25: 's', 26: 'x', 27: 'd',
            28: 'c', 29: 'v', 30: 'g', 31: 'b', 32: 'h', 33: 'n', 34: 'j', 35: 'm',
            36: 'z', 37: 's', 38: 'x', 39: 'd', 40: 'c', 41: 'v', 42: 'g', 43: 'b',
            44: 'h', 45: 'n', 46: 'j', 47: 'm',
            48: 'q', 49: '2', 50: 'w', 51: '3', 52: 'e', 53: 'r', 54: '5', 55: 't',
            56: '6', 57: 'y', 58: '7', 59: 'u', 60: 'q', 61: '2', 62: 'w', 63: '3',
            64: 'e', 65: 'r', 66: '5', 67: 't', 68: '6', 69: 'y', 70: '7', 71: 'u',
            72: 'i', 73: '9', 74: 'o', 75: '0', 76: 'p', 77: 'l', 78: '-', 79: '@',
            80: '^', 81: ';', 82: '\\', 83: '[', 84: ':',
            85: '9', 86: 'o', 87: '0', 88: 'p', 89: 'l', 90: '-', 91: '@', 92: '^',
            93: ';', 94: '\\', 95: '[',
        }

        self.note_names = ['C', 'C#', 'D', 'D#', 'E', 'F',
                           'F#', 'G', 'G#', 'A', 'Bb', 'B']

        # 楽器名マッピングは元コードと同一（省略せずに保持）
        self.instrument_names = {
            1: "Acoustic Grand Piano", 2: "Bright Acoustic Piano",
            3: "Electric Grand Piano", 4: "Honky-tonk Piano",
            5: "Electric Piano 1", 6: "Electric Piano 2", 7: "Harpsichord", 8: "Clavi",
            9: "Celesta", 10: "Glockenspiel", 11: "Music Box", 12: "Vibraphone",
            13: "Marimba", 14: "Xylophone", 15: "Tubular Bells", 16: "Dulcimer",
            17: "Drawbar Organ", 18: "Percussive Organ", 19: "Rock Organ", 20: "Church Organ",
            21: "Reed Organ", 22: "Accordion", 23: "Harmonica", 24: "Tango Accordion",
            25: "Acoustic Guitar (nylon)", 26: "Acoustic Guitar (steel)",
            27: "Electric Guitar (jazz)", 28: "Electric Guitar (clean)",
            29: "Electric Guitar (muted)", 30: "Overdriven Guitar",
            31: "Distortion Guitar", 32: "Guitar harmonics", 33: "Acoustic Bass",
            34: "Electric Bass (finger)", 35: "Electric Bass (pick)",
            36: "Fretless Bass", 37: "Slap Bass 1", 38: "Slap Bass 2",
            39: "Synth Bass 1", 40: "Synth Bass 2", 41: "Violin", 42: "Viola",
            43: "Cello", 44: "Contrabass", 45: "Tremolo Strings",
            46: "Pizzicato Strings", 47: "Orchestral Harp", 48: "Timpani",
            49: "String Ensemble 1", 50: "String Ensemble 2",
            51: "SynthStrings 1", 52: "SynthStrings 2"
        }

        # プレイリスト管理オブジェクト
        self.playlist = Playlist()

        # UI 作成
        self.create_widgets()

        # グローバルショートカット開始
        self.hotkey_handler = HotkeyHandler(self)

    # --------------------------------------------------------------
    # UI 生成（変更点は Treeview の列定義とプレイリスト部）
    # --------------------------------------------------------------
    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))

        # ---------- 1. ファイル / フォルダー選択 ----------
        file_frame = ttk.LabelFrame(main_frame,
                                    text="MIDI / フォルダー選択",
                                    padding="10")
        file_frame.grid(row=0, column=0, columnspan=3,
                       sticky=(tk.W, tk.E), pady=(0, 10))

        self.file_path_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.file_path_var,
                  width=50, state='readonly').grid(row=0, column=0,
                                                  padx=(0, 5))
        ttk.Button(file_frame, text="ファイルを選択",
                   command=self.browse_file).grid(row=0, column=1,
                                                padx=(0, 5))

        self.folder_path_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.folder_path_var,
                  width=50, state='readonly').grid(row=1, column=0,
                                                  padx=(0, 5), pady=(5, 0))
        ttk.Button(file_frame, text="フォルダーを選択",
                   command=self.browse_folder).grid(row=1, column=1,
                                                   padx=(0, 5), pady=(5, 0))

        # ---------- 2. プレイリスト ----------
        playlist_frame = ttk.LabelFrame(main_frame,
                                       text="プレイリスト", padding="10")
        playlist_frame.grid(row=2, column=0, columnspan=3,
                           sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))

        self.playlist_box = tk.Listbox(playlist_frame,
                                      height=6, selectmode=tk.SINGLE)
        self.playlist_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        sb = ttk.Scrollbar(playlist_frame,
                           command=self.playlist_box.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.playlist_box.configure(yscrollcommand=sb.set)

        # 前・次 ボタン
        nav = ttk.Frame(main_frame)
        nav.grid(row=3, column=0, columnspan=3,
                 sticky=(tk.W, tk.E), pady=(0, 10))
        ttk.Button(nav, text="⏮ 前へ", command=self.prev_track).grid(
            row=0, column=0, padx=5)
        ttk.Button(nav, text="⏭ 次へ", command=self.next_track).grid(
            row=0, column=1, padx=5)

        # ---------- 3. MIDI情報 ----------
        info_frame = ttk.LabelFrame(main_frame,
                                    text="MIDI情報", padding="10")
        info_frame.grid(row=4, column=0, columnspan=3,
                       sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))

        self.info_text = scrolledtext.ScrolledText(
            info_frame, height=8, width=80, wrap=tk.WORD)
        self.info_text.pack(fill=tk.BOTH, expand=True)

        # ---------- 4. トラック詳細（Treeview） ----------
        track_frame = ttk.LabelFrame(main_frame,
                                     text="トラック詳細", padding="10")
        track_frame.grid(row=5, column=0, columnspan=3,
                        sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))

        # Treeview（#0 列は「トラック番号」用に残す）
        self.track_tree = ttk.Treeview(
            track_frame,
            columns=('instrument', 'notes', 'duration'),
            show='headings',
            height=6)

        # ヘッダー設定
        self.track_tree.heading('#0', text='トラック')
        self.track_tree.column('#0', width=80, anchor='w')

        self.track_tree.heading('instrument', text='楽器')
        self.track_tree.column('instrument', width=200, anchor='w')

        self.track_tree.heading('notes', text='音符数')
        self.track_tree.column('notes', width=80, anchor='center')

        self.track_tree.heading('duration', text='長さ(秒)')
        self.track_tree.column('duration', width=80, anchor='e')

        self.track_tree.pack(fill=tk.BOTH, expand=True)

        # ---------- 5. 再生コントロール ----------
        ctrl_frame = ttk.LabelFrame(main_frame,
                                    text="再生コントロール", padding="10")
        ctrl_frame.grid(row=6, column=0, columnspan=3,
                        sticky=(tk.W, tk.E), pady=(0, 10))

        self.play_btn = ttk.Button(ctrl_frame,
                                   text="▶ PLAY",
                                   command=self.toggle_play,
                                   state='disabled')
        self.play_btn.grid(row=0, column=0, padx=5)

        self.stop_btn = ttk.Button(ctrl_frame,
                                   text="⏹ STOP",
                                   command=self.stop_play,
                                   state='disabled')
        self.stop_btn.grid(row=0, column=1, padx=5)

        # 速度スライダー
        ttk.Label(ctrl_frame, text="速度:").grid(
            row=0, column=2, padx=(20, 5))
        self.speed_var = tk.DoubleVar(value=1.0)
        self.speed_scale = ttk.Scale(ctrl_frame,
                                    from_=0.1, to=2.0,
                                    variable=self.speed_var,
                                    orient=tk.HORIZONTAL,
                                    length=200)
        self.speed_scale.grid(row=0, column=3, padx=(0, 5))
        self.speed_label = ttk.Label(ctrl_frame, text="1.0x")
        self.speed_label.grid(row=0, column=4)

        self.speed_var.trace('w', self.update_speed_label)

        # プログレスバー
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(ctrl_frame,
                                           variable=self.progress_var,
                                           maximum=100)
        self.progress_bar.grid(row=1, column=0, columnspan=5,
                              sticky=(tk.W, tk.E), pady=(10, 0))

        # ---------- 6. ログ/ステータス ----------
        log_frame = ttk.Frame(main_frame)
        log_frame.grid(row=7, column=0, columnspan=3,
                       sticky=(tk.W, tk.E, tk.N, tk.S))
        self.status_text = scrolledtext.ScrolledText(
            log_frame, height=8, width=80, wrap=tk.WORD)
        self.status_text.pack(fill=tk.BOTH, expand=True)

        # ----- グリッド伸縮設定 -----
        for i in range(8):
            main_frame.rowconfigure(i,
                                   weight=1 if i in (4, 5) else 0)
        main_frame.columnconfigure(0, weight=1)

    # --------------------------------------------------------------
    # ファイル／フォルダー選択ハンドラ
    # --------------------------------------------------------------
    def browse_file(self):
        path = filedialog.askopenfilename(
            title="MIDIファイルを選択",
            filetypes=[("MIDI files", "*.mid *.midi"), ("All files", "*.*")])
        if path:
            self.file_path_var.set(path)
            self.midi_file = path
            self.analyze_file()          # すぐ解析して再生可能に

    def browse_folder(self):
        folder = filedialog.askdirectory(title="MIDI フォルダーを選択")
        if not folder:
            return
        self.folder_path_var.set(folder)
        self.playlist.load_folder(folder)

        # Listbox に表示
        self.playlist_box.delete(0, tk.END)
        for f in self.playlist.files:
            self.playlist_box.insert(tk.END,
                                     os.path.basename(f))

        if self.playlist.current_path():
            self.select_playlist_index(0)

    def select_playlist_index(self, idx: int):
        """Listbox と内部状態を同期させる"""
        if 0 <= idx < len(self.playlist.files):
            self.playlist_box.selection_clear(0, tk.END)
            self.playlist_box.selection_set(idx)
            self.playlist_box.activate(idx)

            # UI の midi_file を更新し、解析
            self.midi_file = self.playlist.current_path()
            self.file_path_var.set(self.midi_file)
            self.analyze_file()

    # --------------------------------------------------------------
    # プレイリスト操作（前・次）
    # --------------------------------------------------------------
    def next_track(self):
        if self.playlist.has_next():
            self.playlist.next()
            self.select_playlist_index(self.playlist.index)

    def prev_track(self):
        if self.playlist.has_prev():
            self.playlist.prev()
            self.select_playlist_index(self.playlist.index)

    # --------------------------------------------------------------
    # 解析ロジック（元コードと同等）
    # --------------------------------------------------------------
    def analyze_file(self):
        """MIDI を読み込んで情報・キー列を生成"""
        if not self.midi_file:
            return
        try:
            self.log("MIDI を解析中…")
            self.midi_info = self.analyze_midi_file(self.midi_file)
            self.key_sequence = self.convert_to_key_sequence(
                self.midi_file)

            self.display_midi_info()
            self.display_track_info()

            # 再生ボタン有効化
            self.play_btn.config(state='normal')
            self.stop_btn.config(state='disabled')
            self.log(f"解析完了（キーイベント数: {len(self.key_sequence)}）")
        except Exception as e:
            messagebox.showerror("エラー", f"解析中に例外が発生しました:\n{e}")
            self.log(f"解析エラー: {e}")

    def analyze_midi_file(self, path):
        mid = mido.MidiFile(path)

        info = {
            'filename': os.path.basename(path),
            'format': mid.type,
            'track_count': len(mid.tracks),
            'ticks_per_beat': mid.ticks_per_beat,
            'total_time': mid.length,
            'tracks': []
        }

        current_tempo = 500000
        for i, tr in enumerate(mid.tracks):
            tinfo = {
                'track_number': i,
                'name': '',
                'instruments': set(),
                'has_notes': False,
                'note_count': 0,
                'duration': 0
            }
            cur = 0
            for msg in tr:
                cur += msg.time
                if msg.type == 'set_tempo':
                    current_tempo = msg.tempo
                elif msg.type == 'track_name':
                    tinfo['name'] = msg.name
                elif msg.type == 'program_change':
                    inst = self.instrument_names.get(
                        msg.program + 1,
                        f"Program {msg.program}")
                    tinfo['instruments'].add(inst)
                elif msg.type == 'note_on' and msg.velocity > 0:
                    tinfo['has_notes'] = True
                    tinfo['note_count'] += 1

            tinfo['duration'] = mido.tick2second(
                cur, mid.ticks_per_beat, current_tempo)
            tinfo['instruments'] = list(tinfo['instruments'])
            info['tracks'].append(tinfo)

        # 最後に取得したテンポから BPM を算出
        info['bpm'] = round(mido.tempo2bpm(current_tempo), 2)
        return info

    def convert_to_key_sequence(self, path):
        mid = mido.MidiFile(path)

        events = []
        current_tempo = 500000

        for tr in mid.tracks:
            cur = 0
            for msg in tr:
                cur += msg.time
                if msg.type == 'set_tempo':
                    current_tempo = msg.tempo
                elif msg.type == 'note_on' and msg.velocity > 0:
                    t = mido.tick2second(
                        cur, mid.ticks_per_beat, current_tempo)
                    events.append({
                        'time': t,
                        'type': 'note_on',
                        'note': msg.note,
                        'velocity': msg.velocity
                    })
                elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                    t = mido.tick2second(
                        cur, mid.ticks_per_beat, current_tempo)
                    events.append({
                        'time': t,
                        'type': 'note_off',
                        'note': msg.note
                    })

        events.sort(key=lambda x: x['time'])

        # 同時押しをまとめる（元コードと同等）
        time_groups = defaultdict(list)
        for ev in events:
            time_groups[round(ev['time'], 3)].append(ev)

        key_seq = []
        active_notes = set()
        for t in sorted(time_groups):
            for ev in time_groups[t]:
                if ev['type'] == 'note_on':
                    active_notes.add(ev['note'])
                else:
                    active_notes.discard(ev['note'])

            if not active_notes:
                continue

            keys, notes = [], []
            for n in sorted(active_notes):
                if n in self.note_to_key:
                    k = self.note_to_key[n]
                    if k not in keys:
                        keys.append(k)
                notes.append(self.midi_to_note_name(n))

            key_seq.append({
                'time': t,
                'keys': keys,
                'notes': notes,
                'active_note_count': len(active_notes)
            })
        return key_seq

    def midi_to_note_name(self, num):
        octv = (num // 12) - 1
        name = self.note_names[num % 12]
        return f"{name}{octv}"

    # --------------------------------------------------------------
    # 表示系
    # --------------------------------------------------------------
    def display_midi_info(self):
        if not self.midi_info:
            return
        txt = (f"ファイル名: {self.midi_info['filename']}\n"
               f"フォーマット: Type {self.midi_info['format']}\n"
               f"BPM: {self.midi_info['bpm']}\n"
               f"総時間: {self.midi_info['total_time']:.2f} 秒\n"
               f"トラック数: {self.midi_info['track_count']}\n"
               f"ticks/beat: {self.midi_info['ticks_per_beat']}\n"
               f"キーイベント数: {len(self.key_sequence)}")
        self.info_text.delete(1.0, tk.END)
        self.info_text.insert(tk.END, txt)

    def display_track_info(self):
        if not self.midi_info:
            return
        for i in self.track_tree.get_children():
            self.track_tree.delete(i)

        for tr in self.midi_info['tracks']:
            instr = ', '.join(tr['instruments']) if tr['instruments'] else 'なし'
            notes = str(tr['note_count']) if tr['has_notes'] else '0'
            # text にトラック番号、values に残りの列
            self.track_tree.insert(
                '',
                'end',
                text=str(tr['track_number']),
                values=(instr, notes, f"{tr['duration']:.2f}")
            )

    # --------------------------------------------------------------
    # 再生コントロール
    # --------------------------------------------------------------
    def toggle_play(self):
        if not self.key_sequence:
            messagebox.showwarning(
                "警告", "キーシーケンスがありません。MIDI を解析してください。")
            return

        if self.is_playing:
            self.pause_play()
        else:
            self.start_play()
    def start_play(self):
        if self.play_thread and self.play_thread.is_alive():
            return
        self.is_playing = True
        self.play_btn.config(text="⏸ PAUSE")
        self.stop_btn.config(state='normal')
        self.root.iconify()          # バックグラウンドで実行

        self.play_thread = threading.Thread(
            target=self.play_sequence, daemon=True)
        self.play_thread.start()
        self.log("再生開始")

    def pause_play(self):
        self.is_playing = False
        self.play_btn.config(text="▶ PLAY")
        self.log("一時停止")

    def stop_play(self):
        self.is_playing = False
        self.play_btn.config(text="▶ PLAY", state='normal')
        self.stop_btn.config(state='disabled')
        self.progress_var.set(0)

        # 全キーを解放
        for k in set(self.note_to_key.values()):
            try:
                self.keyboard.release(k)
            except Exception:
                pass
        self.log("再生停止")

    def play_sequence(self):
        """MIDI → キー入力 の本体ロジック"""
        if not self.key_sequence:
            return

        speed = self.speed_var.get()
        total_dur = self.key_sequence[-1]['time']
        start_t = time.time()

        currently_pressed = set()

        try:
            # ---- 正確な press / release イベントを作る ----
            mid = mido.MidiFile(self.midi_file)
            cur_tempo = 500000
            all_ev = []

            for tr in mid.tracks:
                cur = 0
                for msg in tr:
                    cur += msg.time
                    if msg.type == 'set_tempo':
                        cur_tempo = msg.tempo
                    elif msg.type == 'note_on' and msg.velocity > 0:
                        t = mido.tick2second(
                            cur, mid.ticks_per_beat, cur_tempo)
                        all_ev.append({
                            'time': t,
                            'type': 'press',
                            'note': msg.note
                        })
                    elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                        t = mido.tick2second(
                            cur, mid.ticks_per_beat, cur_tempo)
                        all_ev.append({
                            'time': t,
                            'type': 'release',
                            'note': msg.note
                        })
            all_ev.sort(key=lambda x: x['time'])

            self.root.after(0, self.log,
                            f"総イベント数 {len(all_ev)} 件を再生開始")

            # ---- イベント駆動でキー操作 ----
            for ev in all_ev:
                if not self.is_playing:
                    break

                target = ev['time'] / speed
                now = time.time() - start_t
                wait = target - now
                if wait > 0:
                    time.sleep(wait)

                key = self.note_to_key.get(ev['note'])
                note_name = self.midi_to_note_name(ev['note'])

                try:
                    if ev['type'] == 'press':
                        if key not in currently_pressed:
                            self.keyboard.press(key)
                            currently_pressed.add(key)
                            act = "PRESS"
                        else:
                            act = "ALREADY PRESSED"
                    else:  # release
                        if key in currently_pressed:
                            self.keyboard.release(key)
                            currently_pressed.remove(key)
                            act = "RELEASE"
                        else:
                            act = "ALREADY RELEASED"

                    msg = (f"{ev['time']:.3f}s | {act} "
                           f"{key or '?'}({note_name}) | "
                           f"現在押下: {'+'.join(sorted(currently_pressed)) if currently_pressed else 'なし'}")
                    self.root.after(0, self.update_play_status, msg)

                    prog = (ev['time'] / total_dur) * 100 \
                        if total_dur > 0 else 0
                    self.root.after(0, self.progress_var.set, prog)

                except Exception as e:
                    self.root.after(
                        0, self.log,
                        f"キー入力エラー ({key}={note_name}): {e}")

            # 曲が最後まで再生されたら次トラックへ自動遷移
            for k in list(currently_pressed):
                try:
                    self.keyboard.release(k)
                except Exception:
                    pass

            if self.is_playing:  # 正常終了したときだけ
                self.root.after(0, self.log,
                                "曲が終了しました → 次のトラックへ")
                self.root.after(0, self._auto_next_track)

        except Exception as e:
            for k in list(currently_pressed):
                try:
                    self.keyboard.release(k)
                except Exception:
                    pass
            self.root.after(0, self.log,
                            f"再生中にエラー: {e}")
            self.root.after(0, self.stop_play)

    def _auto_next_track(self):
        """プレイリストの次曲へ遷移し、解析→再生を続行"""
        if self.playlist.has_next():
            self.next_track()          # UI 側でインデックス更新・解析実施
            self.start_play()
        else:
            self.log("プレイリストの最後です。再生を停止します")
            self.stop_play()

    # --------------------------------------------------------------
    # 補助メソッド（ログ・速度表示など）
    # --------------------------------------------------------------
    def update_play_status(self, msg):
        self.log(msg)

    def update_speed_label(self, *args):
        spd = self.speed_var.get()
        self.speed_label.config(text=f"{spd:.1f}x")

    def log(self, txt):
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {txt}\n"
        self.status_text.insert(tk.END, line)
        self.status_text.see(tk.END)
        self.root.update_idletasks()


# --------------------------------------------------------------
def main():
    root = tk.Tk()
    app = MidiPlayerUI(root)

    # 必要なら手動解析用ショートカットを追加（例: Ctrl+Alt+A）
    # def manual_analyze():
    #     app.analyze_file()
    # hk = keyboard.GlobalHotKeys({
    #     '<ctrl>+<alt>+a': lambda: root.after(0, manual_analyze)
    # })
    # hk.start()

    root.mainloop()


if __name__ == "__main__":
    main()
