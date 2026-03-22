# overlay_window.py - 再生中オーバーレイウィンドウ

import tkinter as tk
from tkinter import ttk


class OverlayWindow:
    """
    再生中にメインウィンドウの代わりに画面右上に表示される
    コンパクトなコントロールウィンドウ。
    """

    def __init__(
        self,
        root: tk.Tk,
        on_toggle_play,
        on_previous,
        on_next,
        on_close,
        on_progress_click,
    ):
        self.root = root
        self.window: tk.Toplevel | None = None
        self.progress_var: tk.DoubleVar | None = None

        # コールバック
        self._on_toggle_play = on_toggle_play
        self._on_previous = on_previous
        self._on_next = on_next
        self._on_close = on_close
        self._on_progress_click = on_progress_click

    # ------------------------------------------------------------------
    # ライフサイクル
    # ------------------------------------------------------------------

    def create(self, filename: str = "") -> None:
        """オーバーレイウィンドウを作成する（既存があれば先に破棄）"""
        self.destroy()

        self.window = tk.Toplevel(self.root)
        self.window.title("MIDI Player - Playing")
        self.window.geometry("400x150")
        self.window.configure(bg='#2c2c2c')
        self.window.attributes('-topmost', True)
        self.window.geometry("+{}+50".format(self.root.winfo_screenwidth() - 450))
        self.window.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_widgets()
        self.set_filename(filename)

    def destroy(self) -> None:
        """オーバーレイウィンドウを破棄する"""
        if self.progress_var is not None:
            try:
                for trace_id in self.progress_var.trace_info():
                    self.progress_var.trace_remove(trace_id[0], trace_id[1])
            except Exception:
                pass

        if self.window is not None:
            try:
                if self.window.winfo_exists():
                    self.window.destroy()
            except Exception:
                pass
            finally:
                self.window = None

        self.progress_var = None

    def is_open(self) -> bool:
        return self.window is not None and self.window.winfo_exists()

    # ------------------------------------------------------------------
    # UI の更新
    # ------------------------------------------------------------------

    def set_filename(self, filename: str) -> None:
        if self.is_open() and hasattr(self, '_file_label'):
            self._file_label.config(text=f"♪ {filename}" if filename else "")

    def set_play_button_text(self, text: str) -> None:
        if self.is_open() and hasattr(self, '_play_btn'):
            self._play_btn.config(text=text)

    def set_progress(self, percent: float) -> None:
        if self.progress_var is not None:
            self.progress_var.set(percent)

    # ------------------------------------------------------------------
    # ウィジェット構築
    # ------------------------------------------------------------------

    def _build_widgets(self) -> None:
        frame = ttk.Frame(self.window, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)

        # ファイル名ラベル
        self._file_label = ttk.Label(frame, text="", font=('Arial', 12, 'bold'))
        self._file_label.pack(pady=(0, 10))

        # コントロールボタン
        btn_frame = ttk.Frame(frame)
        btn_frame.pack()

        ttk.Button(btn_frame, text="◀ 前", command=self._on_previous, width=8).pack(
            side=tk.LEFT, padx=5
        )
        self._play_btn = ttk.Button(
            btn_frame, text="⏸ 停止", command=self._on_toggle_play, width=10
        )
        self._play_btn.pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="次 ▶", command=self._on_next, width=8).pack(
            side=tk.LEFT, padx=5
        )
        ttk.Button(btn_frame, text="⏹ 終了", command=self._on_close, width=8).pack(
            side=tk.LEFT, padx=5
        )

        # プログレスバー（Canvas シークバー）
        self.progress_var = tk.DoubleVar()
        canvas = tk.Canvas(frame, height=20, bg='#e0e0e0', highlightthickness=0, cursor='hand2')
        canvas.pack(fill=tk.X, pady=(10, 0))
        canvas.bind('<Button-1>', self._on_progress_click)
        canvas.bind('<Configure>', lambda e: _draw_progress(canvas, self.progress_var))
        self.progress_var.trace_add(
            'write', lambda *a: _draw_progress(canvas, self.progress_var)
        )
        self._progress_canvas = canvas


# ------------------------------------------------------------------
# 共通プログレスバー描画ユーティリティ
# ------------------------------------------------------------------

def _draw_progress(canvas: tk.Canvas, var: tk.DoubleVar) -> None:
    """Canvas プログレスバーを描画する"""
    try:
        if not canvas.winfo_exists():
            return
        canvas.delete('all')
        w = canvas.winfo_width()
        h = canvas.winfo_height()
        if w <= 1:
            return
        percent = max(0.0, min(100.0, var.get()))
        fill_w = int((percent / 100.0) * w)
        if fill_w > 0:
            canvas.create_rectangle(0, 0, fill_w, h, fill='#4a9eff', outline='')
        if fill_w < w:
            canvas.create_rectangle(fill_w, 0, w, h, fill='#e0e0e0', outline='')
        if percent > 0:
            canvas.create_text(w // 2, h // 2, text=f"{percent:.0f}%",
                                font=('Arial', 9), fill='#333')
    except tk.TclError:
        pass
