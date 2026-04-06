# playlist_manager.py - プレイリストの状態管理

import os
import glob
import random


class PlaylistManager:
    """
    プレイリストの状態（ファイル一覧・現在インデックス）を管理するクラス。
    UI には依存しない純粋なデータ管理層。
    """

    def __init__(self):
        self.playlist: list[str] = []
        self.current_index: int = 0

    # ------------------------------------------------------------------
    # ファイル・フォルダ読み込み
    # ------------------------------------------------------------------

    def set_single_file(self, filepath: str) -> None:
        """単一ファイルをプレイリストにセット"""
        self.playlist = [filepath]
        self.current_index = 0

    def load_folder(self, folder_path: str) -> int:
        """
        フォルダ内の MIDI ファイルをすべてプレイリストにロードする。
        返り値: 読み込んだファイル数（0 の場合はMIDIファイルなし）
        """
        midi_files: list[str] = []
        for ext in ('*.mid', '*.midi'):
            midi_files.extend(glob.glob(os.path.join(folder_path, ext)))

        if not midi_files:
            return 0

        self.playlist = sorted(midi_files)
        self.current_index = 0
        return len(self.playlist)

    # ------------------------------------------------------------------
    # ナビゲーション
    # ------------------------------------------------------------------

    @property
    def current_file(self) -> str | None:
        if not self.playlist:
            return None
        return self.playlist[self.current_index]

    def go_next(self) -> str | None:
        """次のファイルに移動してファイルパスを返す。プレイリストが空なら None"""
        if not self.playlist:
            return None
        self.current_index = (self.current_index + 1) % len(self.playlist)
        return self.current_file

    def go_previous(self) -> str | None:
        """前のファイルに移動してファイルパスを返す。プレイリストが空なら None"""
        if not self.playlist:
            return None
        self.current_index = (self.current_index - 1) % len(self.playlist)
        return self.current_file

    def is_multi(self) -> bool:
        """プレイリストに2曲以上あるか"""
        return len(self.playlist) > 1

    def shuffle(self) -> None:
        """プレイリストをシャッフルし、先頭を選択状態にする"""
        if len(self.playlist) <= 1:
            return
        random.shuffle(self.playlist)
        self.current_index = 0

    # ------------------------------------------------------------------
    # 表示用データ
    # ------------------------------------------------------------------

    def get_display_items(self, is_playing: bool) -> list[tuple[str, str, bool]]:
        """
        プレイリスト表示用のデータを返す。
        返り値: [(filename, status_label, is_current), ...]
        """
        items = []
        for i, filepath in enumerate(self.playlist):
            filename = os.path.basename(filepath)
            is_current = i == self.current_index
            if is_current:
                status = "再生中" if is_playing else "選択中"
            else:
                status = "待機中"
            items.append((filename, status, is_current))
        return items