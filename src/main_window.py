# main_window.py - メインウィンドウのUI定義と制御ロジック

import os
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pynput.keyboard import GlobalHotKeys

from src.constants import BASE_NOTE_TO_KEY, ALL_KEYS
from src.midi_analyzer import (
    analyze_midi_file, analyze_midi_range, apply_octave_shift,
    convert_to_key_sequence, midi_to_note_name,
)
from src.player import MidiPlayer
from src.playlist_manager import PlaylistManager
from src.overlay_window import OverlayWindow, _draw_progress


class MidiPlayerUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("MIDI to Keys Player")

        # ウィンドウを画面中央に配置
        w, h = 600, 800
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")
        self.root.configure(bg='#f0f0f0')

        # 状態変数
        self.midi_file: str | None = None
        self.midi_info: dict | None = None
        self.key_sequence: list = []
        self.note_to_key: dict = BASE_NOTE_TO_KEY.copy()
        self.muted_tracks: set = set()
        self.current_shift: int = 0

        # サブコンポーネント
        self.player = MidiPlayer()
        self.playlist_mgr = PlaylistManager()

        # プレイヤーのコールバックを登録
        self.player.on_status_update = lambda msg: self.root.after(0, self.log, msg)
        self.player.on_progress_update = lambda pct: self.root.after(
            0, self._update_progress, pct
        )
        self.player.on_playback_finished = lambda: self.root.after(
            0, self.on_playback_finished
        )
        self.player.on_error = lambda msg: self.root.after(0, self._on_player_error, msg)

        # オーバーレイ
        self.overlay = OverlayWindow(
            root=self.root,
            on_toggle_play=self.toggle_play,
            on_previous=self.play_previous,
            on_next=self.play_next,
            on_close=self.close_overlay,
            on_progress_click=self.on_progress_click,
            on_speed_change=self._on_overlay_speed_change,
            on_speed_drag_start=self._on_overlay_speed_drag_start,
        )

        # グローバルホットキー
        self.hotkeys = GlobalHotKeys({
            '<ctrl>+<alt>+p': lambda: self.root.after(0, self.toggle_play),
            '<ctrl>+<alt>+s': lambda: self.root.after(0, self.reset_play),
            '<ctrl>+<right>': lambda: self.root.after(0, self.play_next),
            '<ctrl>+<left>': lambda: self.root.after(0, self.play_previous),
        })
        self.hotkeys.start()

        self.create_widgets()

    # ------------------------------------------------------------------
    # UI構築
    # ------------------------------------------------------------------

    def create_widgets(self) -> None:
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # ファイル/フォルダ選択
        file_frame = ttk.LabelFrame(main_frame, text="ファイル/フォルダ選択", padding="10")
        file_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        self.file_path_var = tk.StringVar()
        ttk.Entry(file_frame, textvariable=self.file_path_var,
                  width=50, state='readonly').grid(row=0, column=0, padx=(0, 5))
        ttk.Button(file_frame, text="ファイル選択",
                   command=self.browse_file).grid(row=0, column=1, padx=(0, 5))
        ttk.Button(file_frame, text="フォルダ選択",
                   command=self.browse_folder).grid(row=0, column=2, padx=(0, 5))

        # 音域設定
        tr_frame = ttk.LabelFrame(main_frame, text="音域設定", padding="10")
        tr_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        self.auto_transpose = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            tr_frame, text="キーボード範囲(C4-C7)に自動調整",
            variable=self.auto_transpose, command=self.on_transpose_toggle,
        ).grid(row=0, column=0, sticky=tk.W, padx=(0, 20))

        self.transpose_status_label = ttk.Label(tr_frame, text="シフト: なし", foreground='blue')
        self.transpose_status_label.grid(row=0, column=1, sticky=tk.W)

        manual_frame = ttk.Frame(tr_frame)
        manual_frame.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(5, 0))
        ttk.Label(manual_frame, text="手動調整:").grid(row=0, column=0, padx=(0, 5))
        ttk.Button(manual_frame, text="▼ -1オクターブ",
                   command=lambda: self.manual_shift(-12), width=15).grid(row=0, column=1, padx=(0, 5))
        ttk.Button(manual_frame, text="リセット",
                   command=self.reset_shift, width=10).grid(row=0, column=2, padx=(0, 5))
        ttk.Button(manual_frame, text="▲ +1オクターブ",
                   command=lambda: self.manual_shift(12), width=15).grid(row=0, column=3)

        # プレイリスト
        pl_frame = ttk.LabelFrame(main_frame, text="プレイリスト", padding="10")
        pl_frame.grid(row=2, column=0, columnspan=2,
                      sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))

        self.playlist_tree = ttk.Treeview(pl_frame, columns=('status',), height=6)
        self.playlist_tree.heading('#0', text='ファイル名')
        self.playlist_tree.heading('status', text='状態')
        self.playlist_tree.column('#0', width=400)
        self.playlist_tree.column('status', width=50)
        self.playlist_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        pl_sb = ttk.Scrollbar(pl_frame, orient=tk.VERTICAL, command=self.playlist_tree.yview)
        pl_sb.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.playlist_tree.configure(yscrollcommand=pl_sb.set)
        self.playlist_tree.bind('<Double-1>', self.on_playlist_double_click)

        pl_ctrl = ttk.Frame(pl_frame)
        pl_ctrl.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))
        self.prev_btn = ttk.Button(pl_ctrl, text="◀ 前の曲",
                                   command=self.play_previous, state='disabled')
        self.prev_btn.grid(row=0, column=0, padx=(0, 5))
        self.next_btn = ttk.Button(pl_ctrl, text="次の曲 ▶",
                                   command=self.play_next, state='disabled')
        self.next_btn.grid(row=0, column=1, padx=(0, 5))

        # MIDI情報
        info_frame = ttk.LabelFrame(main_frame, text="MIDI情報", padding="10")
        info_frame.grid(row=3, column=0, columnspan=2,
                        sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))

        self.info_text = scrolledtext.ScrolledText(info_frame, height=6, width=80, wrap=tk.WORD)
        self.info_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        track_frame = ttk.LabelFrame(
            info_frame, text="トラック詳細 (ダブルクリックでミュート切り替え)"
        )
        track_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(10, 0))

        self.track_tree = ttk.Treeview(
            track_frame, columns=('name', 'instrument', 'notes', 'duration', 'muted'), height=6
        )
        for col, text, width in [
            ('#0', 'トラック', 80), ('name', '名前', 80), ('instrument', '楽器', 100),
            ('notes', '音符数', 80), ('duration', '長さ(秒)', 80), ('muted', 'ミュート', 80),
        ]:
            self.track_tree.heading(col, text=text)
            self.track_tree.column(col, width=width)

        self.track_tree.bind('<Double-1>', self.on_track_double_click)
        self.track_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        tr_sb = ttk.Scrollbar(track_frame, orient=tk.VERTICAL, command=self.track_tree.yview)
        tr_sb.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.track_tree.configure(yscrollcommand=tr_sb.set)

        # 再生コントロール
        ctrl_frame = ttk.LabelFrame(
            main_frame,
            text="再生コントロール (Ctrl+Alt+P=再生/停止, Ctrl+Alt+S=リセット, Ctrl+←/→=前/次)",
            padding="10",
        )
        ctrl_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))

        self.play_btn = ttk.Button(ctrl_frame, text="▶ PLAY",
                                   command=self.toggle_play, state='disabled')
        self.play_btn.grid(row=0, column=0, padx=(0, 10))
        self.reset_btn = ttk.Button(ctrl_frame, text="↺ RESET",
                                    command=self.reset_play, state='disabled')
        self.reset_btn.grid(row=0, column=1, padx=(0, 10))

        ttk.Label(ctrl_frame, text="速度:").grid(row=0, column=2, padx=(20, 5))
        self.speed_var = tk.DoubleVar(value=1.0)
        ttk.Scale(ctrl_frame, from_=0.1, to=2.0, variable=self.speed_var,
                  orient=tk.HORIZONTAL, length=200).grid(row=0, column=3, padx=(0, 10))
        self.speed_label = ttk.Label(ctrl_frame, text="1.0x")
        self.speed_label.grid(row=0, column=4)
        self.speed_var.trace('w', self._update_speed_label)

        self.progress_var = tk.DoubleVar()
        self.progress_bar = tk.Canvas(
            ctrl_frame, height=20, bg='#e0e0e0', highlightthickness=0, cursor='hand2'
        )
        self.progress_bar.grid(row=1, column=0, columnspan=5,
                                sticky=(tk.W, tk.E), pady=(10, 0))
        self.progress_bar.bind('<Button-1>', self.on_progress_click)
        self.progress_bar.bind(
            '<Configure>', lambda e: _draw_progress(self.progress_bar, self.progress_var)
        )
        self.progress_var.trace_add(
            'write', lambda *a: _draw_progress(self.progress_bar, self.progress_var)
        )

        # ステータスログ
        status_frame = ttk.Frame(main_frame)
        status_frame.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E))
        self.status_text = scrolledtext.ScrolledText(
            status_frame, height=8, width=80, wrap=tk.WORD
        )
        self.status_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # グリッドの重み設定
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        for row in (2, 3):
            main_frame.rowconfigure(row, weight=1)
        info_frame.columnconfigure(0, weight=1)
        info_frame.rowconfigure(1, weight=1)
        track_frame.columnconfigure(0, weight=1)
        track_frame.rowconfigure(0, weight=1)
        ctrl_frame.columnconfigure(3, weight=1)
        status_frame.columnconfigure(0, weight=1)
        status_frame.rowconfigure(0, weight=1)
        pl_frame.columnconfigure(0, weight=1)
        pl_frame.rowconfigure(0, weight=1)

    # ------------------------------------------------------------------
    # ファイル/フォルダ選択
    # ------------------------------------------------------------------

    def browse_file(self) -> None:
        path = filedialog.askopenfilename(
            title="MIDIファイルを選択",
            filetypes=[("MIDI files", "*.mid *.midi"), ("All files", "*.*")],
        )
        if not path:
            return
        self.file_path_var.set(path)
        self.midi_file = path
        self.playlist_mgr.set_single_file(path)
        self.update_playlist_display()
        self.analyze_file()
        self.prev_btn.config(state='normal')
        self.next_btn.config(state='normal')
        self.log(f"ファイルが選択されました: {os.path.basename(path)}")

    def browse_folder(self) -> None:
        folder = filedialog.askdirectory(title="MIDIファイルが含まれるフォルダを選択")
        if not folder:
            return
        count = self.playlist_mgr.load_folder(folder)
        if count == 0:
            messagebox.showinfo("情報", "選択されたフォルダにMIDIファイルが見つかりませんでした。")
            self.log("選択されたフォルダにMIDIファイルがありませんでした。")
            return

        self.midi_file = self.playlist_mgr.current_file
        self.file_path_var.set(self.midi_file)
        self.analyze_file()
        self.update_playlist_display()
        self.prev_btn.config(state='normal')
        self.next_btn.config(state='normal')
        self.log(f"フォルダから{count}個のMIDIファイルが見つかりました: {folder}")

    # ------------------------------------------------------------------
    # MIDI解析
    # ------------------------------------------------------------------

    def analyze_file(self) -> None:
        """現在の midi_file を解析してUIを更新"""
        if not self.midi_file:
            return

        self.player.current_event_index = 0
        self.player.seek_target_time = None
        self.progress_var.set(0)
        if self.overlay.is_open():
            self.overlay.set_progress(0)

        try:
            self.log("MIDIファイルを解析中...")

            if self.auto_transpose.get():
                shift, logs = analyze_midi_range(self.midi_file)
                for msg in logs:
                    self.log(msg)
                self.current_shift = shift
            else:
                shift = 0
                self.current_shift = 0
                self.log("元のメジャーで再生します（シフトなし）")

            self.note_to_key, map_logs = apply_octave_shift(shift)
            for msg in map_logs:
                self.log(msg)

            self.midi_info = analyze_midi_file(self.midi_file)
            self.key_sequence = convert_to_key_sequence(self.midi_file, self.note_to_key)
            self.muted_tracks.clear()

            self._display_midi_info()
            self._display_track_info()
            self._update_transpose_status()

            self.play_btn.config(state='normal')
            self.log(f"解析完了：{len(self.key_sequence)}個のキーイベントが見つかりました。")

        except Exception as e:
            messagebox.showerror("エラー", f"ファイル解析中にエラーが発生しました:\n{e}")
            self.log(f"エラー: {e}")

    # ------------------------------------------------------------------
    # 音域調整
    # ------------------------------------------------------------------

    def on_transpose_toggle(self) -> None:
        if self.midi_file:
            self.log("音域設定を変更しました。ファイルを再解析します...")
            self.analyze_file()

    def manual_shift(self, semitones: int) -> None:
        self.current_shift += semitones
        self.log(f"手動シフト: {self.current_shift // 12:+d}オクターブ ({self.current_shift:+d}半音)")
        if self.midi_file:
            self.auto_transpose.set(False)
            self.note_to_key, logs = apply_octave_shift(self.current_shift)
            for msg in logs:
                self.log(msg)
            self.key_sequence = convert_to_key_sequence(self.midi_file, self.note_to_key)
            self._update_transpose_status()
            self.log(f"手動調整完了：{len(self.key_sequence)}個のキーイベント")

    def reset_shift(self) -> None:
        self.current_shift = 0
        self.log("シフトをリセットしました")
        if self.midi_file:
            if self.auto_transpose.get():
                self.analyze_file()
            else:
                self.note_to_key, _ = apply_octave_shift(0)
                self.key_sequence = convert_to_key_sequence(self.midi_file, self.note_to_key)
                self._update_transpose_status()

    def _update_transpose_status(self) -> None:
        if self.auto_transpose.get():
            text = f"自動調整: {self.current_shift // 12:+d}オクターブ ({self.current_shift:+d}半音)"
            color = 'blue'
        elif self.current_shift == 0:
            text, color = "元のメジャー", 'green'
        else:
            text = f"手動調整: {self.current_shift // 12:+d}オクターブ ({self.current_shift:+d}半音)"
            color = 'orange'
        self.transpose_status_label.config(text=text, foreground=color)

    # ------------------------------------------------------------------
    # 再生コントロール
    # ------------------------------------------------------------------

    def toggle_play(self) -> None:
        if not self.key_sequence:
            messagebox.showwarning("警告", "まずMIDIファイルを解析してください。")
            return
        if self.player.is_playing:
            self._pause()
        else:
            self._start()

    def _start(self) -> None:
        if self.player.play_thread and self.player.play_thread.is_alive():
            return
        self.player.is_playing = True
        self.play_btn.config(text="⏸ PAUSE")
        self.reset_btn.config(state='normal')

        if not self.overlay.is_open():
            self.overlay.create(os.path.basename(self.midi_file or ""), speed=self.speed_var.get())
        else:
            self.overlay.set_filename(os.path.basename(self.midi_file or ""))
            self.overlay.set_play_button_text("⏸ 停止")

        self.update_playlist_display()
        self.player.start(
            midi_file=self.midi_file,
            note_to_key=self.note_to_key,
            muted_tracks=self.muted_tracks,
            speed=self.speed_var.get(),
            key_sequence=self.key_sequence,
        )

        if self.root.state() == 'normal':
            self.root.withdraw()
            self.root.after(100, self.root.iconify)

        pos = self.player.current_event_index
        self.log("再生を開始しました。" if pos == 0 else f"再生を再開しました。(位置: {pos})")

    def _pause(self) -> None:
        self.player.pause()
        self.play_btn.config(text="▶ PLAY")
        if self.overlay.is_open():
            self.overlay.set_play_button_text("▶ 再生")
        self.update_playlist_display()
        self.log(f"再生を一時停止しました。(位置: {self.player.current_event_index})")

    def reset_play(self) -> None:
        was_playing = self.player.is_playing
        self.player.reset()
        self.progress_var.set(0)
        if self.overlay.is_open():
            self.overlay.set_progress(0)
        self.play_btn.config(text="▶ PLAY", state='normal')
        self.update_playlist_display()
        self.log("再生位置をリセットしました。")

    def stop_play(self) -> None:
        """エラー時など内部から呼ぶ停止処理"""
        self.player.is_playing = False
        self.player.current_event_index = 0
        self.player.seek_target_time = None
        self.play_btn.config(text="▶ PLAY", state='normal')
        self.reset_btn.config(state='disabled')
        self.progress_var.set(0)
        if self.root.state() != 'normal':
            self.root.deiconify()
        self.overlay.destroy()
        self.update_playlist_display()
        self.log("再生を停止しました。")

    def _on_player_error(self, msg: str) -> None:
        self.log(msg)
        self.stop_play()

    def on_playlist_double_click(self, event) -> None:
        """プレイリストのダブルクリックで曲を選択（再生中なら停止してから切り替え）"""
        sel = self.playlist_tree.selection()
        if not sel:
            return
        item = sel[0]
        # Treeview内のアイテム順序からインデックスを取得
        all_items = self.playlist_tree.get_children()
        try:
            clicked_index = list(all_items).index(item)
        except ValueError:
            return

        if clicked_index == self.playlist_mgr.current_index:
            return  # 既に選択中

        was_playing = self.player.is_playing
        if was_playing:
            self.player.is_playing = False
            self._release_all_keys()
            self.player.wait_for_stop(timeout=1.0)

        self.player.current_event_index = 0
        self.player.seek_target_time = None

        self.playlist_mgr.current_index = clicked_index
        self.midi_file = self.playlist_mgr.current_file
        if self.midi_file:
            self.file_path_var.set(self.midi_file)
        self.analyze_file()
        self.progress_var.set(0)
        if self.overlay.is_open():
            self.overlay.set_progress(0)
        self.update_playlist_display()
        self.log(f"選択: {os.path.basename(self.midi_file or '')}")

    # ------------------------------------------------------------------
    # プレイリスト操作
    # ------------------------------------------------------------------

    def play_next(self, auto_play: bool = False) -> None:
        was_playing = self.player.is_playing or auto_play
        if self.player.is_playing:
            self.player.is_playing = False
            self._release_all_keys()

        # 前の再生スレッドが完全に終了するのを待つ
        self.player.wait_for_stop(timeout=1.0)

        self.player.current_event_index = 0
        self.player.seek_target_time = None

        self.midi_file = self.playlist_mgr.go_next()
        if self.midi_file:
            self.file_path_var.set(self.midi_file)
        self.analyze_file()
        self.progress_var.set(0)
        if self.overlay.is_open():
            self.overlay.set_progress(0)
        self.update_playlist_display()
        self.log(f"次の曲: {os.path.basename(self.midi_file or '')}")

        if self.key_sequence and was_playing:
            self._start()

    def play_previous(self) -> None:
        was_playing = self.player.is_playing
        if self.player.is_playing:
            self.player.is_playing = False
            self._release_all_keys()

        # 前の再生スレッドが完全に終了するのを待つ
        self.player.wait_for_stop(timeout=1.0)

        self.player.current_event_index = 0
        self.player.seek_target_time = None

        self.midi_file = self.playlist_mgr.go_previous()
        if self.midi_file:
            self.file_path_var.set(self.midi_file)
        self.analyze_file()
        self.progress_var.set(0)
        if self.overlay.is_open():
            self.overlay.set_progress(0)
        self.update_playlist_display()
        self.log(f"前の曲: {os.path.basename(self.midi_file or '')}")

        if self.key_sequence and was_playing:
            self._start()

    def on_playback_finished(self) -> None:
        """再生完了時のコールバック"""
        self.player.is_playing = False
        if self.playlist_mgr.is_multi():
            self.log("曲が終了しました。次の曲を再生します。")
            self.play_next(auto_play=True)
        else:
            self.progress_var.set(100)
            if self.overlay.is_open():
                self.overlay.set_progress(100)
            self.play_btn.config(text="▶ PLAY")
            if self.overlay.is_open():
                self.overlay.set_play_button_text("▶ 再生")
            self.log("再生が完了しました。")

    # ------------------------------------------------------------------
    # シーク・プログレス
    # ------------------------------------------------------------------

    def on_progress_click(self, event) -> None:
        if not self.key_sequence:
            return
        widget = event.widget
        bar_width = widget.winfo_width()
        if bar_width <= 0:
            return
        percent = max(0.0, min(100.0, (event.x / bar_width) * 100))
        total_duration = self.key_sequence[-1]['time'] if self.key_sequence else 0
        if total_duration <= 0:
            return

        target_time = (percent / 100.0) * total_duration
        was_playing = self.player.is_playing

        self.player.seek(target_time)
        self.progress_var.set(percent)
        if self.overlay.is_open():
            self.overlay.set_progress(percent)
        self.log(f"シーク: {target_time:.1f}秒 ({percent:.0f}%)")

        if was_playing:
            self.play_btn.config(text="▶ PLAY")
            if self.overlay.is_open():
                self.overlay.set_play_button_text("▶ 再生")
            self._seek_resume_retry(5)

    def _seek_resume_retry(self, retries_left: int) -> None:
        if retries_left <= 0:
            self.log("シーク後の再開に失敗しました。手動で再生してください。")
            return
        if self.player.play_thread and self.player.play_thread.is_alive():
            self.root.after(100, self._seek_resume_retry, retries_left - 1)
        else:
            self._start()

    def _update_progress(self, percent: float) -> None:
        self.progress_var.set(percent)
        if self.overlay.is_open():
            self.overlay.set_progress(percent)

    # ------------------------------------------------------------------
    # オーバーレイ
    # ------------------------------------------------------------------

    def close_overlay(self) -> None:
        if self.player.is_playing:
            self._pause()
        if self.root.state() != 'normal':
            self.root.deiconify()
        self.overlay.destroy()
        self.update_playlist_display()
        self.log("プレイウィンドウを閉じました。進度は維持されています。")

    def _on_overlay_speed_drag_start(self) -> None:
        """速度スライダーのドラッグ開始時に再生を停止"""
        if self.player.is_playing:
            self.player.pause()
            self.player.wait_for_stop(timeout=0.2)
            self._release_all_keys()
        self.play_btn.config(text="▶ PLAY")
        if self.overlay.is_open():
            self.overlay.set_play_button_text("▶ 再生")

    def _on_overlay_speed_change(self, speed: float) -> None:
        """速度スライダーのリリース時に新しい速度で再生を再開"""
        self.speed_var.set(speed)
        if self.key_sequence:
            self.player.wait_for_stop(timeout=0.2)
            self._start()

    # ------------------------------------------------------------------
    # トラックミュート
    # ------------------------------------------------------------------

    def on_track_double_click(self, event) -> None:
        if not self.track_tree.selection():
            return
        item = self.track_tree.selection()[0]
        track_text = self.track_tree.item(item, 'text')
        try:
            track_number = int(track_text.replace('Track ', ''))
        except ValueError:
            return

        if track_number in self.muted_tracks:
            self.muted_tracks.remove(track_number)
            status = "ON"
            self.log(f"トラック {track_number} をミュート解除しました")
        else:
            self.muted_tracks.add(track_number)
            status = "MUTED"
            self.log(f"トラック {track_number} をミュートしました")

        values = list(self.track_tree.item(item, 'values'))
        values[4] = status
        self.track_tree.item(item, values=values)

    # ------------------------------------------------------------------
    # 表示更新
    # ------------------------------------------------------------------

    def update_playlist_display(self) -> None:
        for item in self.playlist_tree.get_children():
            self.playlist_tree.delete(item)
        for filename, status, is_current in self.playlist_mgr.get_display_items(
            self.player.is_playing
        ):
            item = self.playlist_tree.insert('', 'end', text=filename, values=(status,))
            if is_current:
                self.playlist_tree.selection_set(item)
                self.playlist_tree.focus(item)

    def _display_midi_info(self) -> None:
        if not self.midi_info:
            return
        mapped_notes = sorted(self.note_to_key.keys())
        note_range = (
            f"{midi_to_note_name(mapped_notes[0])}-{midi_to_note_name(mapped_notes[-1])}"
            if mapped_notes else "なし"
        )
        bpm_info = str(self.midi_info['bpm'])
        if self.midi_info.get('bpm_changes', 1) > 1:
            bpm_info += f" (平均, {self.midi_info['bpm_changes']}回変化)"
        text = (
            f"ファイル名: {self.midi_info['filename']}\n"
            f"フォーマット: Type {self.midi_info['format']}\n"
            f"BPM: {bpm_info}\n"
            f"総時間: {self.midi_info['total_time']:.2f} 秒\n"
            f"トラック数: {self.midi_info['track_count']}\n"
            f"時間分解能: {self.midi_info['ticks_per_beat']} ticks/beat\n"
            f"キーイベント数: {len(self.key_sequence)}\n"
            f"対応音域: {note_range} (C4-C7キーボード)\n"
        )
        self.info_text.delete(1.0, tk.END)
        self.info_text.insert(1.0, text)

    def _display_track_info(self) -> None:
        if not self.midi_info:
            return
        for item in self.track_tree.get_children():
            self.track_tree.delete(item)
        displayed = 0
        for track in self.midi_info['tracks']:
            if not track['has_notes'] or track['note_count'] == 0:
                continue
            instruments_str = ', '.join(track['instruments']) if track['instruments'] else 'なし'
            muted_str = "MUTED" if track['track_number'] in self.muted_tracks else "ON"
            self.track_tree.insert(
                '', 'end',
                text=f"Track {track['track_number']}",
                values=(
                    track['name'] or '(名前なし)',
                    instruments_str,
                    str(track['note_count']),
                    f"{track['duration']:.2f}",
                    muted_str,
                ),
            )
            displayed += 1
        self.log(f"音符を含むトラック: {displayed}/{self.midi_info['track_count']}個")

    def _update_speed_label(self, *args) -> None:
        self.speed_label.config(text=f"{self.speed_var.get():.1f}x")

    # ------------------------------------------------------------------
    # ユーティリティ
    # ------------------------------------------------------------------

    def _release_all_keys(self) -> None:
        for key in ALL_KEYS:
            try:
                self.player.keyboard.release(key)
            except Exception:
                pass

    def log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.status_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.status_text.see(tk.END)
        self.root.update_idletasks()

    def __del__(self) -> None:
        try:
            if hasattr(self, 'hotkeys'):
                self.hotkeys.stop()
        except Exception:
            pass