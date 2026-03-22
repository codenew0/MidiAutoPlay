# main.py - エントリーポイント

import tkinter as tk
from src.main_window import MidiPlayerUI


def main():
    root = tk.Tk()
    app = MidiPlayerUI(root)

    def on_closing():
        try:
            app.hotkeys.stop()
            app.overlay.destroy()
        except Exception:
            pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
