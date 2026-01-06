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
from pynput.keyboard import Key, Controller, GlobalHotKeys
import glob

class MidiPlayerUI:
    def __init__(self, root):
        self.root = root
        self.root.title("MIDI to Keys Player")
        self.root.geometry("1200x800")
        self.root.configure(bg='#f0f0f0')

        # キーボードコントローラー
        self.keyboard = Controller()

        # データ保存用
        self.midi_file = None
        self.midi_info = None
        self.key_sequence = []
        self.is_playing = False
        self.play_thread = None
        
        # プレイリスト機能用の新しい変数
        self.playlist = []  # ファイルパスのリスト
        self.current_playlist_index = 0  # 現在再生中のファイルのインデックス
        self.playlist_folder = ""  # 選択されたフォルダ
        
        # トラックミュート機能用の新しい変数
        self.muted_tracks = set()  # ミュートされたトラック番号のセット
        
        # オーバーレイウィンドウ用
        self.overlay_window = None

        # キーボード範囲の設定（MIDI番号）
        self.keyboard_min_note = 60  # C4
        self.keyboard_max_note = 84  # C7

       # 基本的なキーマッピング（C4-C7の範囲、37キー）
        self.base_note_to_key = {
            # C4-C5 (48-59) - オクターブ0-2の低音域
            48: '1', 49: '2', 50: '3', 51: '4', 52: '5', 53: '6', 54: '7', 55: '8', 56: '9', 57: '0', 58: 'q', 59: 'w',
            
            # C5-C6 (60-71) - オクターブ3-4の中音域
            60: 'e', 61: 'r', 62: 't', 63: 'y', 64: 'u', 65: 'i', 66: 'o', 67: 'p', 68: 'a', 69: 's', 70: 'd', 71: 'f',
            
            # C6-C7 (72-84) - オクターブ5-6の高音域
            72: 'g', 73: 'h', 74: 'j', 75: 'k', 76: 'l', 77: 'z', 78: 'x', 79: 'c', 80: 'v', 81: 'b', 82: 'n', 83: 'm', 84: ','
        }

        # 動的に調整されるマッピング（初期値は基本マッピング）
        self.note_to_key = self.base_note_to_key.copy()

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

        # オクターブシフト機能の設定
        self.auto_transpose = tk.BooleanVar(value=False)  # デフォルトでオフ
        self.current_shift = 0  # 現在適用されているシフト量

        # グローバルホットキーの設定
        self.hotkeys = GlobalHotKeys({
            '<ctrl>+<alt>+p': self.hotkey_toggle_play,
            '<ctrl>+<alt>+s': self.hotkey_stop,
            '<ctrl>+<right>': self.hotkey_next,
            '<ctrl>+<left>': self.hotkey_previous,
        })
        self.hotkeys.start()

        self.create_widgets()

    def analyze_midi_range(self, filepath):
        """MIDIファイルの音域を分析してオクターブシフトを計算"""
        mid = mido.MidiFile(filepath)
        
        all_notes = []
        for track in mid.tracks:
            for msg in track:
                if msg.type == 'note_on' and msg.velocity > 0:
                    all_notes.append(msg.note)
        
        if not all_notes:
            return 0  # シフト不要
        
        min_note = min(all_notes)
        max_note = max(all_notes)
        
        midi_range = max_note - min_note
        keyboard_range = self.keyboard_max_note - self.keyboard_min_note  # 36半音
        
        self.log(f"音域分析: 元の範囲 {self.midi_to_note_name(min_note)}-{self.midi_to_note_name(max_note)} (幅: {midi_range}半音)")
        
        # 曲の音域がキーボード範囲を超える場合
        if midi_range > keyboard_range:
            self.log(f"警告: 曲の音域({midi_range}半音)がキーボード範囲({keyboard_range}半音)を超えています")
            # 可能な限り中央に配置
            midi_center = (min_note + max_note) / 2
            keyboard_center = (self.keyboard_min_note + self.keyboard_max_note) / 2
            shift = round((keyboard_center - midi_center) / 12) * 12
        else:
            # 曲全体がキーボード範囲に収まるようにシフト
            # まず曲の中心をキーボードの中心に合わせる
            midi_center = (min_note + max_note) / 2
            keyboard_center = (self.keyboard_min_note + self.keyboard_max_note) / 2
            shift = round((keyboard_center - midi_center) / 12) * 12
            
            # シフト後の範囲を確認
            shifted_min = min_note + shift
            shifted_max = max_note + shift
            
            # 範囲からはみ出る場合は調整
            if shifted_min < self.keyboard_min_note:
                additional_shift = self.keyboard_min_note - shifted_min
                shift += (additional_shift // 12 + (1 if additional_shift % 12 > 0 else 0)) * 12
            elif shifted_max > self.keyboard_max_note:
                additional_shift = shifted_max - self.keyboard_max_note
                shift -= (additional_shift // 12 + (1 if additional_shift % 12 > 0 else 0)) * 12
        
        # 最終確認
        final_min = min_note + shift
        final_max = max_note + shift
        
        self.log(f"オクターブシフト: {shift//12:+d}オクターブ ({shift:+d}半音)")
        self.log(f"シフト後の範囲: {self.midi_to_note_name(final_min)}-{self.midi_to_note_name(final_max)}")
        
        # 範囲外の音符がある場合は警告
        if final_min < self.keyboard_min_note or final_max > self.keyboard_max_note:
            out_of_range_low = max(0, self.keyboard_min_note - final_min)
            out_of_range_high = max(0, final_max - self.keyboard_max_note)
            if out_of_range_low > 0:
                self.log(f"警告: {out_of_range_low}半音が低音側で範囲外です")
            if out_of_range_high > 0:
                self.log(f"警告: {out_of_range_high}半音が高音側で範囲外です")
        
        return shift
    
    def apply_octave_shift(self, shift):
        """オクターブシフトを適用してキーマッピングを更新"""
        self.note_to_key = {}
        
        for original_note, key in self.base_note_to_key.items():
            # シフト前の音符に対応するキーを設定
            shifted_note = original_note - shift
            if 0 <= shifted_note <= 127:  # MIDI番号の有効範囲
                self.note_to_key[shifted_note] = key
        
        # シフト後の実際の範囲をログ
        if self.note_to_key:
            mapped_notes = sorted(self.note_to_key.keys())
            self.log(f"マッピング範囲: {self.midi_to_note_name(mapped_notes[0])}-{self.midi_to_note_name(mapped_notes[-1])} ({len(mapped_notes)}キー)")


    def create_widgets(self):
        # メインフレーム  
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # ファイル選択部分を拡張してフォルダ選択も追加  
        file_frame = ttk.LabelFrame(main_frame, text="ファイル/フォルダ選択", padding="10")
        file_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        self.file_path_var = tk.StringVar()
        self.file_entry = ttk.Entry(file_frame, textvariable=self.file_path_var, width=50, state='readonly')
        self.file_entry.grid(row=0, column=0, padx=(0, 5))

        self.browse_btn = ttk.Button(file_frame, text="ファイル選択", command=self.browse_file)
        self.browse_btn.grid(row=0, column=1, padx=(0, 5))
        
        # 新機能: フォルダ選択ボタン
        self.browse_folder_btn = ttk.Button(file_frame, text="フォルダ選択", command=self.browse_folder)
        self.browse_folder_btn.grid(row=0, column=2, padx=(0, 5))

        # ★新機能: オクターブシフト設定エリア
        transpose_frame = ttk.LabelFrame(main_frame, text="音域設定", padding="10")
        transpose_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        self.transpose_check = ttk.Checkbutton(
            transpose_frame, 
            text="キーボード範囲(C4-C7)に自動調整", 
            variable=self.auto_transpose,
            command=self.on_transpose_toggle
        )
        self.transpose_check.grid(row=0, column=0, sticky=tk.W, padx=(0, 20))
        
        # 現在のシフト状態を表示
        self.transpose_status_label = ttk.Label(transpose_frame, text="シフト: なし", foreground='blue')
        self.transpose_status_label.grid(row=0, column=1, sticky=tk.W)
        
        # 手動シフトボタン（将来の拡張用）
        manual_frame = ttk.Frame(transpose_frame)
        manual_frame.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(5, 0))
        
        ttk.Label(manual_frame, text="手動調整:").grid(row=0, column=0, padx=(0, 5))
        
        self.shift_down_btn = ttk.Button(manual_frame, text="▼ -1オクターブ", command=lambda: self.manual_shift(-12), width=15)
        self.shift_down_btn.grid(row=0, column=1, padx=(0, 5))
        
        self.shift_reset_btn = ttk.Button(manual_frame, text="リセット", command=self.reset_shift, width=10)
        self.shift_reset_btn.grid(row=0, column=2, padx=(0, 5))
        
        self.shift_up_btn = ttk.Button(manual_frame, text="▲ +1オクターブ", command=lambda: self.manual_shift(12), width=15)
        self.shift_up_btn.grid(row=0, column=3)

        # プレイリスト表示エリアを新たに追加
        playlist_frame = ttk.LabelFrame(main_frame, text="プレイリスト", padding="10")
        playlist_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))

        # プレイリスト用のTreeview
        self.playlist_tree = ttk.Treeview(playlist_frame, columns=('status',), height=6)
        self.playlist_tree.heading('#0', text='ファイル名')
        self.playlist_tree.heading('status', text='状態')
        self.playlist_tree.column('#0', width=400)
        self.playlist_tree.column('status', width=100)
        self.playlist_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # プレイリスト用スクロールバー
        playlist_scrollbar = ttk.Scrollbar(playlist_frame, orient=tk.VERTICAL, command=self.playlist_tree.yview)
        playlist_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.playlist_tree.configure(yscrollcommand=playlist_scrollbar.set)

        # プレイリストコントロールボタン
        playlist_control_frame = ttk.Frame(playlist_frame)
        playlist_control_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))
        
        self.prev_btn = ttk.Button(playlist_control_frame, text="◀ 前の曲", command=self.play_previous, state='disabled')
        self.prev_btn.grid(row=0, column=0, padx=(0, 5))
        
        self.next_btn = ttk.Button(playlist_control_frame, text="次の曲 ▶", command=self.play_next, state='disabled')
        self.next_btn.grid(row=0, column=1, padx=(0, 5))

        # MIDI情報表示部分
        info_frame = ttk.LabelFrame(main_frame, text="MIDI情報", padding="10")
        info_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))

        # 基本情報
        basic_frame = ttk.Frame(info_frame)
        basic_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))

        self.info_text = scrolledtext.ScrolledText(basic_frame, height=6, width=80, wrap=tk.WORD)
        self.info_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # トラック情報 - ダブルクリックでミュートのON/OFF切り替え機能を追加
        track_frame = ttk.LabelFrame(info_frame, text="トラック詳細 (ダブルクリックでミュート切り替え)")
        track_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(10, 0))

        # トラック情報用のTreeview - ミュート状態を表示するカラムを追加
        self.track_tree = ttk.Treeview(track_frame, columns=('name', 'instrument', 'notes', 'duration', 'muted'), height=6)
        self.track_tree.heading('#0', text='トラック')
        self.track_tree.heading('name', text='名前')
        self.track_tree.heading('instrument', text='楽器')
        self.track_tree.heading('notes', text='音符数')
        self.track_tree.heading('duration', text='長さ(秒)')
        self.track_tree.heading('muted', text='ミュート')

        self.track_tree.column('#0', width=80)
        self.track_tree.column('name', width=150)
        self.track_tree.column('instrument', width=200)
        self.track_tree.column('notes', width=80)
        self.track_tree.column('duration', width=80)
        self.track_tree.column('muted', width=80)

        # ダブルクリックイベントを追加してミュート切り替えを実現
        self.track_tree.bind('<Double-1>', self.on_track_double_click)
        self.track_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # スクロールバー
        track_scrollbar = ttk.Scrollbar(track_frame, orient=tk.VERTICAL, command=self.track_tree.yview)
        track_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.track_tree.configure(yscrollcommand=track_scrollbar.set)

        # 再生コントロール部分
        control_frame = ttk.LabelFrame(main_frame, text="再生コントロール (ショートカット: Ctrl+Alt+P=再生/停止, Ctrl+Alt+S=停止, Ctrl+←/→=前/次)", padding="10")
        control_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        # 再生ボタン
        self.play_btn = ttk.Button(control_frame, text="▶ PLAY", command=self.toggle_play, state='disabled')
        self.play_btn.grid(row=0, column=0, padx=(0, 10))

        self.stop_btn = ttk.Button(control_frame, text="■ STOP", command=self.stop_play, state='disabled')
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
        status_frame.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E))

        self.status_text = scrolledtext.ScrolledText(status_frame, height=8, width=80, wrap=tk.WORD)
        self.status_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # グリッドの重み設定
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(2, weight=1)
        main_frame.rowconfigure(3, weight=1)
        info_frame.columnconfigure(0, weight=1)
        info_frame.rowconfigure(1, weight=1)
        track_frame.columnconfigure(0, weight=1)
        track_frame.rowconfigure(0, weight=1)
        control_frame.columnconfigure(3, weight=1)
        status_frame.columnconfigure(0, weight=1)
        status_frame.rowconfigure(0, weight=1)
        playlist_frame.columnconfigure(0, weight=1)
        playlist_frame.rowconfigure(0, weight=1)

    def on_transpose_toggle(self):
        """オクターブシフトのオン/オフが切り替えられた時の処理"""
        if self.midi_file:
            self.log("音域設定を変更しました。ファイルを再解析します...")
            self.analyze_file()

    def manual_shift(self, semitones):
        """手動でオクターブシフトを調整"""
        self.current_shift += semitones
        self.log(f"手動シフト: {self.current_shift//12:+d}オクターブ ({self.current_shift:+d}半音)")
        
        if self.midi_file:
            # 自動調整をオフにして手動シフトを適用
            self.auto_transpose.set(False)
            self.apply_octave_shift(self.current_shift)
            
            # キーシーケンスを再生成
            self.key_sequence = self.convert_to_key_sequence(self.midi_file)
            self.update_transpose_status()
            self.log(f"手動調整完了：{len(self.key_sequence)}個のキーイベント")

    def reset_shift(self):
        """シフトをリセット"""
        self.current_shift = 0
        self.log("シフトをリセットしました")
        
        if self.midi_file:
            if self.auto_transpose.get():
                # 自動調整の場合は再解析
                self.analyze_file()
            else:
                # 手動調整の場合はシフトなしで適用
                self.apply_octave_shift(0)
                self.key_sequence = self.convert_to_key_sequence(self.midi_file)
                self.update_transpose_status()

    def update_transpose_status(self):
        """トランスポーズ状態の表示を更新"""
        if self.auto_transpose.get():
            status_text = f"自動調整: {self.current_shift//12:+d}オクターブ ({self.current_shift:+d}半音)"
            color = 'blue'
        else:
            if self.current_shift == 0:
                status_text = "元のメジャー"
                color = 'green'
            else:
                status_text = f"手動調整: {self.current_shift//12:+d}オクターブ ({self.current_shift:+d}半音)"
                color = 'orange'
        
        self.transpose_status_label.config(text=status_text, foreground=color)

    def browse_file(self):
        """ファイル選択ダイアログを開く"""
        file_path = filedialog.askopenfilename(
            title="MIDIファイルを選択",
            filetypes=[("MIDI files", "*.mid *.midi"), ("All files", "*.*")]
        )
        if file_path:
            self.file_path_var.set(file_path)
            self.midi_file = file_path
            # 単一ファイル選択時は、プレイリストをクリアして1つのファイルのみにする
            self.playlist = [file_path]
            self.current_playlist_index = 0
            self.update_playlist_display()
            # 自動解析を実行
            self.analyze_file()
            self.prev_btn.config(state='normal')
            self.next_btn.config(state='normal')
            self.log("ファイルが選択されました: " + os.path.basename(file_path))

    def browse_folder(self):
        """フォルダ選択ダイアログ - フォルダ内の全MIDIファイルをプレイリストに追加"""
        folder_path = filedialog.askdirectory(title="MIDIファイルが含まれるフォルダを選択")
        if folder_path:
            self.playlist_folder = folder_path
            # フォルダ内の.midと.midiファイルを検索
            midi_files = []
            for extension in ['*.mid', '*.midi']:
                midi_files.extend(glob.glob(os.path.join(folder_path, extension)))
            
            if midi_files:
                # ファイル名でソートしてプレイリストに追加
                self.playlist = sorted(midi_files)
                self.current_playlist_index = 0
                self.midi_file = self.playlist[0] if self.playlist else None
                if self.midi_file:
                    self.file_path_var.set(self.midi_file)
                    # 自動解析を実行
                    self.analyze_file()
                self.update_playlist_display()
                self.prev_btn.config(state='normal')
                self.next_btn.config(state='normal')
                self.log(f"フォルダから{len(midi_files)}個のMIDIファイルが見つかりました: {folder_path}")
            else:
                messagebox.showinfo("情報", "選択されたフォルダにMIDIファイルが見つかりませんでした。")
                self.log("選択されたフォルダにMIDIファイルがありませんでした。")

    def update_playlist_display(self):
        """プレイリストの表示を更新"""
        # 既存のアイテムをクリア
        for item in self.playlist_tree.get_children():
            self.playlist_tree.delete(item)
            
        # プレイリストの各ファイルを表示
        for i, file_path in enumerate(self.playlist):
            filename = os.path.basename(file_path)
            status = "再生中" if i == self.current_playlist_index and self.is_playing else "待機中"
            if i == self.current_playlist_index:
                status = "選択中" if not self.is_playing else "再生中"
                
            item = self.playlist_tree.insert('', 'end', text=filename, values=(status,))
            # 現在の曲をハイライト表示
            if i == self.current_playlist_index:
                self.playlist_tree.selection_set(item)
                self.playlist_tree.focus(item)

    def play_next(self):
        """次の曲を再生"""
        if not self.playlist:
            return
            
        # 現在再生中なら停止
        if self.is_playing:
            self.stop_play()
            
        # 次の曲のインデックスを計算（最後の曲の場合は最初に戻る）
        self.current_playlist_index = (self.current_playlist_index + 1) % len(self.playlist)
        self.midi_file = self.playlist[self.current_playlist_index]
        self.file_path_var.set(self.midi_file)
        
        # プレイリスト表示を更新
        self.update_playlist_display()
        
        # 新しい曲を解析して再生開始
        self.analyze_file()
        if self.key_sequence:
            self.start_play()
            
        self.log(f"次の曲: {os.path.basename(self.midi_file)}")

    def play_previous(self):
        """前の曲を再生"""
        if not self.playlist:
            return
            
        # 現在再生中なら停止
        if self.is_playing:
            self.stop_play()
            
        # 前の曲のインデックスを計算（最初の曲の場合は最後に行く）
        self.current_playlist_index = (self.current_playlist_index - 1) % len(self.playlist)
        self.midi_file = self.playlist[self.current_playlist_index]
        self.file_path_var.set(self.midi_file)
        
        # プレイリスト表示を更新
        self.update_playlist_display()
        
        # 新しい曲を解析して再生開始
        self.analyze_file()
        if self.key_sequence:
            self.start_play()
            
        self.log(f"前の曲: {os.path.basename(self.midi_file)}")

    def on_track_double_click(self, event):
        """トラックダブルクリック時のミュート切り替え処理"""
        # クリックされた項目を取得
        item = self.track_tree.selection()[0] if self.track_tree.selection() else None
        if not item:
            return
            
        # トラック番号を取得（テキストから"Track "を除去）
        track_text = self.track_tree.item(item, 'text')
        try:
            track_number = int(track_text.replace('Track ', ''))
        except ValueError:
            return
            
        # ミュート状態を切り替え
        if track_number in self.muted_tracks:
            self.muted_tracks.remove(track_number)
            muted_status = "ON"
            self.log(f"トラック {track_number} をミュート解除しました")
        else:
            self.muted_tracks.add(track_number)
            muted_status = "MUTED"
            self.log(f"トラック {track_number} をミュートしました")
            
        # 表示を更新
        values = list(self.track_tree.item(item, 'values'))
        values[4] = muted_status  # ミュートカラムは5番目（インデックス4）
        self.track_tree.item(item, values=values)

    # ホットキー用のメソッド群
    def hotkey_toggle_play(self):
        """ホットキー: 再生/一時停止切り替え"""
        self.root.after(0, self.toggle_play)
        
    def hotkey_stop(self):
        """ホットキー: 停止"""
        self.root.after(0, self.stop_play)
        
    def hotkey_next(self):
        """ホットキー: 次の曲"""
        self.root.after(0, self.play_next)
        
    def hotkey_previous(self):
        """ホットキー: 前の曲"""
        self.root.after(0, self.play_previous)

    def analyze_file(self):
        """MIDIファイルを解析する（自動実行）"""
        if not self.midi_file:
            return

        try:
            self.log("MIDIファイルを解析中...")
            
            # 自動調整が有効な場合のみオクターブシフトを計算
            if self.auto_transpose.get():
                octave_shift = self.analyze_midi_range(self.midi_file)
                self.current_shift = octave_shift
            else:
                # 自動調整が無効な場合はシフトなし
                octave_shift = 0
                self.current_shift = 0
                self.log("元のメジャーで再生します（シフトなし）")
            
            # シフトを適用
            self.apply_octave_shift(octave_shift)
            
            # 残りの解析処理
            self.midi_info = self.analyze_midi_file(self.midi_file)
            self.key_sequence = self.convert_to_key_sequence(self.midi_file)
            
            # ミュート状態をリセット
            self.muted_tracks.clear()

            self.display_midi_info()
            self.display_track_info()
            self.update_transpose_status()

            self.play_btn.config(state='normal')
            self.log(f"解析完了：{len(self.key_sequence)}個のキーイベントが見つかりました。")

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
        """MIDIファイルをキーシーケンスに変換（テンポ変化対応版）"""
        mid = mido.MidiFile(filepath)
        
        # テンポマップを作成（全トラックから収集）
        tempo_map = []  # (累積tick, tempo)のリスト
        
        for track in mid.tracks:
            current_tick = 0
            for msg in track:
                current_tick += msg.time
                if msg.type == 'set_tempo':
                    tempo_map.append((current_tick, msg.tempo))
        
        # tick順にソートして重複を削除
        tempo_map.sort(key=lambda x: x[0])
        if not tempo_map:
            tempo_map = [(0, 500000)]  # デフォルトテンポ
        
        # tickを秒に変換する関数
        def tick_to_second(tick):
            time_sec = 0.0
            prev_tick = 0
            current_tempo = tempo_map[0][1]
            
            for tempo_tick, tempo in tempo_map:
                if tick <= tempo_tick:
                    # 目標tickに到達前
                    time_sec += mido.tick2second(tick - prev_tick, mid.ticks_per_beat, current_tempo)
                    return time_sec
                else:
                    # このテンポ変化地点まで進む
                    time_sec += mido.tick2second(tempo_tick - prev_tick, mid.ticks_per_beat, current_tempo)
                    prev_tick = tempo_tick
                    current_tempo = tempo
            
            # 最後のテンポ変化以降
            if tick > prev_tick:
                time_sec += mido.tick2second(tick - prev_tick, mid.ticks_per_beat, current_tempo)
            
            return time_sec
        
        # 各トラックのイベントを秒に変換
        events = []
        
        for track_num, track in enumerate(mid.tracks):
            current_tick = 0
            for msg in track:
                current_tick += msg.time
                
                if msg.type == 'note_on' and msg.velocity > 0:
                    events.append({
                        'time': tick_to_second(current_tick),
                        'type': 'note_on',
                        'note': msg.note,
                        'velocity': msg.velocity,
                        'track': track_num
                    })
                elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                    events.append({
                        'time': tick_to_second(current_tick),
                        'type': 'note_off',
                        'note': msg.note,
                        'track': track_num
                    })
        
        events.sort(key=lambda x: x['time'])
        
        # 以降は既存のコードと同じ
        key_sequence = []
        active_notes = set()
        time_groups = defaultdict(list)
        
        for event in events:
            time_groups[round(event['time'], 3)].append(event)
        
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
        """MIDI基本情報を表示（音域情報を追加）"""
        if not self.midi_info:
            return

        # 実際にマッピングされている音域を表示
        mapped_notes = sorted(self.note_to_key.keys())
        if mapped_notes:
            note_range = f"{self.midi_to_note_name(mapped_notes[0])}-{self.midi_to_note_name(mapped_notes[-1])}"
        else:
            note_range = "なし"

        info_text = f"""ファイル名: {self.midi_info['filename']}
フォーマット: Type {self.midi_info['format']}
BPM: {self.midi_info['bpm']}
総時間: {self.midi_info['total_time']:.2f} 秒
トラック数: {self.midi_info['track_count']}
時間分解能: {self.midi_info['ticks_per_beat']} ticks/beat
キーイベント数: {len(self.key_sequence)}
対応音域: {note_range} (C4-C7キーボード)
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
            muted_str = "MUTED" if track['track_number'] in self.muted_tracks else "ON"

            self.track_tree.insert('', 'end',
                                    text=f"Track {track['track_number']}",
                                    values=(track['name'] or '(名前なし)',
                                            instruments_str,
                                            notes_str,
                                            f"{track['duration']:.2f}",
                                            muted_str))

    def create_overlay_window(self):
        """オーバーレイウィンドウを作成"""
        self.overlay_window = tk.Toplevel(self.root)
        self.overlay_window.title("MIDI Player - Playing")
        self.overlay_window.geometry("400x150")
        self.overlay_window.configure(bg='#2c2c2c')
        self.overlay_window.attributes('-topmost', True)  # 常に最前面
        
        # ウィンドウを画面の右上に配置
        self.overlay_window.geometry("+{}+50".format(self.root.winfo_screenwidth() - 450))
        
        # オーバーレイのコンテンツ
        overlay_frame = ttk.Frame(self.overlay_window, padding="20")
        overlay_frame.pack(fill=tk.BOTH, expand=True)
        
        # 現在再生中のファイル名表示
        self.overlay_file_label = ttk.Label(overlay_frame, text="", font=('Arial', 12, 'bold'))
        self.overlay_file_label.pack(pady=(0, 10))
        
        # コントロールボタン
        button_frame = ttk.Frame(overlay_frame)
        button_frame.pack()
        
        self.overlay_prev_btn = ttk.Button(button_frame, text="◀ 前", command=self.play_previous, width=8)
        self.overlay_prev_btn.pack(side=tk.LEFT, padx=5)
        
        self.overlay_play_btn = ttk.Button(button_frame, text="⏸ 停止", command=self.toggle_play, width=10)
        self.overlay_play_btn.pack(side=tk.LEFT, padx=5)
        
        self.overlay_next_btn = ttk.Button(button_frame, text="次 ▶", command=self.play_next, width=8)
        self.overlay_next_btn.pack(side=tk.LEFT, padx=5)
        
        self.overlay_stop_btn = ttk.Button(button_frame, text="⏹ 終了", command=self.stop_play, width=8)
        self.overlay_stop_btn.pack(side=tk.LEFT, padx=5)
        
        # プログレスバー
        self.overlay_progress_var = tk.DoubleVar()
        self.overlay_progress_bar = ttk.Progressbar(overlay_frame, variable=self.overlay_progress_var, maximum=100)
        self.overlay_progress_bar.pack(fill=tk.X, pady=(10, 0))
        
        # 現在のファイル名を更新
        if self.midi_file:
            filename = os.path.basename(self.midi_file)
            self.overlay_file_label.config(text=f"♪ {filename}")

    def destroy_overlay_window(self):
        """オーバーレイウィンドウを破棄"""
        if self.overlay_window:
            self.overlay_window.destroy()
            self.overlay_window = None

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
        
        # オーバーレイウィンドウを作成
        self.create_overlay_window()
        
        # プレイリスト表示を更新
        self.update_playlist_display()

        self.play_thread = threading.Thread(target=self.play_sequence, daemon=True)
        self.play_thread.start()

        self.root.withdraw()   # 完全に非表示（裏のウィンドウが前に出る）
        self.root.after(100, self.root.iconify)  # タスクバーに戻す

        self.log("再生を開始しました。")

    def pause_play(self):
        """再生を一時停止"""
        self.is_playing = False
        self.play_btn.config(text="▶ PLAY")
        
        # オーバーレイのボタンも更新
        if self.overlay_window:
            self.overlay_play_btn.config(text="▶ 再生")
        
        # プレイリスト表示を更新
        self.update_playlist_display()
        self.log("再生を一時停止しました。")

    def stop_play(self):
        """再生を停止"""
        self.is_playing = False
        self.play_btn.config(text="▶ PLAY", state='normal')
        self.stop_btn.config(state='disabled')
        self.progress_var.set(0)

        self.root.deiconify()
        
        # オーバーレイウィンドウを破棄
        self.destroy_overlay_window()
        
        # プレイリスト表示を更新
        self.update_playlist_display()

        # 念のため全てのキーを離す
        try:
            for key in ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0', 'q', 'w',
                        'e', 'r', 't', 'y', 'u', 'i', 'o', 'p', 'a', 's', 'd', 'f',
                        'g', 'h', 'j', 'k', 'l', 'z', 'x', 'c', 'v', 'b', 'n', 'm', ',']:
                try:
                    self.keyboard.release(key)
                except:
                    pass
        except:
            pass

        self.log("再生を停止しました。")

    def play_sequence(self):
        """キーシーケンスを再生 - テンポ変化対応版"""
        if not self.key_sequence:
            return

        speed_multiplier = self.speed_var.get()
        total_duration = self.key_sequence[-1]['time'] if self.key_sequence else 0
        play_start_time = time.time()

        currently_pressed = set()

        try:
            # MIDIファイルからテンポマップを作成
            mid = mido.MidiFile(self.midi_file)
            tempo_map = []
            
            for track in mid.tracks:
                current_tick = 0
                for msg in track:
                    current_tick += msg.time
                    if msg.type == 'set_tempo':
                        tempo_map.append((current_tick, msg.tempo))
            
            tempo_map.sort(key=lambda x: x[0])
            if not tempo_map:
                tempo_map = [(0, 500000)]
            
            # tickを秒に変換する関数（convert_to_key_sequenceと同じロジック）
            def tick_to_second(tick):
                time_sec = 0.0
                prev_tick = 0
                current_tempo = tempo_map[0][1]
                
                for tempo_tick, tempo in tempo_map:
                    if tick <= tempo_tick:
                        time_sec += mido.tick2second(tick - prev_tick, mid.ticks_per_beat, current_tempo)
                        return time_sec
                    else:
                        time_sec += mido.tick2second(tempo_tick - prev_tick, mid.ticks_per_beat, current_tempo)
                        prev_tick = tempo_tick
                        current_tempo = tempo
                
                if tick > prev_tick:
                    time_sec += mido.tick2second(tick - prev_tick, mid.ticks_per_beat, current_tempo)
                
                return time_sec
            
            # 全イベントを再構築（テンポ変化を考慮）
            all_events = []
            
            for track_num, track in enumerate(mid.tracks):
                current_tick = 0
                for msg in track:
                    current_tick += msg.time
                    
                    if msg.type == 'note_on' and msg.velocity > 0:
                        if track_num in self.muted_tracks:
                            continue
                        
                        all_events.append({
                            'time': tick_to_second(current_tick),
                            'type': 'press',
                            'note': msg.note,
                            'velocity': msg.velocity,
                            'track': track_num
                        })
                    elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                        if track_num in self.muted_tracks:
                            continue
                        
                        all_events.append({
                            'time': tick_to_second(current_tick),
                            'type': 'release',
                            'note': msg.note,
                            'track': track_num
                        })
            
            all_events.sort(key=lambda x: x['time'])
            
            # 以降は既存のコードと同じ（イベント再生ループ）
            active_tracks = set(range(len(mid.tracks))) - self.muted_tracks
            self.root.after(0, self.log, f"総イベント数: {len(all_events)}個を再生開始 (アクティブトラック: {sorted(active_tracks)})")

            for i, event in enumerate(all_events):
                if not self.is_playing:
                    break

                target_time = event['time'] / speed_multiplier
                elapsed_time = time.time() - play_start_time
                wait_time = target_time - elapsed_time

                if wait_time > 0:
                    time.sleep(wait_time)

                if not self.is_playing:
                    break

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

                    pressed_keys = sorted(list(currently_pressed))
                    track_info = f"Track{event['track']}"
                    status_msg = f"{event['time']:.3f}s | {action} {key}({note_name}) [{track_info}] | 現在押下: {' + '.join(pressed_keys) if pressed_keys else 'なし'}"

                    self.root.after(0, self.update_play_status, status_msg)

                    progress = (event['time'] / total_duration) * 100 if total_duration > 0 else 0
                    self.root.after(0, self.progress_var.set, progress)
                    if self.overlay_window:
                        self.root.after(0, self.overlay_progress_var.set, progress)

                except Exception as e:
                    error_msg = f"キー入力エラー ({key}={note_name}): {e}"
                    self.root.after(0, self.log, error_msg)

            # 再生完了時に全てのキーを離す
            for key in list(currently_pressed):
                try:
                    self.keyboard.release(key)
                except:
                    pass

            if self.is_playing:
                self.root.after(0, self.on_playback_finished)

        except Exception as e:
            for key in list(currently_pressed):
                try:
                    self.keyboard.release(key)
                except:
                    pass
            self.root.after(0, self.log, f"再生中にエラーが発生しました: {str(e)}")
            self.root.after(0, self.stop_play)

    def on_playback_finished(self):
        """再生完了時の処理 - 自動で次の曲に進む"""
        if len(self.playlist) > 1:
            # プレイリストに複数曲がある場合は自動で次の曲へ
            self.log("曲が終了しました。次の曲を再生します。")
            self.play_next()
        else:
            # 単一ファイルの場合は停止
            self.stop_play()
            self.log("再生が完了しました。")

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

    def __del__(self):
        """デストラクタ - ホットキーを停止"""
        try:
            if hasattr(self, 'hotkeys'):
                self.hotkeys.stop()
        except:
            pass

def main():
    root = tk.Tk()
    app = MidiPlayerUI(root)
    
    # ウィンドウ終了時の処理を追加
    def on_closing():
        try:
            app.hotkeys.stop()  # ホットキーを停止
            app.destroy_overlay_window()  # オーバーレイウィンドウを破棄
        except:
            pass
        root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()