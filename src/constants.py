# constants.py - キーマッピングと定数定義

# キーボード範囲の設定（MIDI番号）
KEYBOARD_MIN_NOTE = 48  # C3 (FFXIVモードの最低音)
KEYBOARD_MAX_NOTE = 84  # C6 (FFXIVモードの最高音)

# 基本的なキーマッピング（C4-C7の範囲、37キー）
BASE_NOTE_TO_KEY = {
    # C4-C5 (48-59) - オクターブ0-2の低音域
    48: '1', 49: '2', 50: '3', 51: '4', 52: '5', 53: '6', 54: '7',
    55: '8', 56: '9', 57: '0', 58: 'q', 59: 'w',

    # C5-C6 (60-71) - オクターブ3-4の中音域
    60: 'e', 61: 'r', 62: 't', 63: 'y', 64: 'u', 65: 'i', 66: 'o',
    67: 'p', 68: 'a', 69: 's', 70: 'd', 71: 'f',

    # C6-C7 (72-84) - オクターブ5-6の高音域
    72: 'g', 73: 'h', 74: 'j', 75: 'k', 76: 'l', 77: 'z', 78: 'x',
    79: 'c', 80: 'v', 81: 'b', 82: 'n', 83: 'm', 84: ',',
}

# piano フォルダと同じ拡張ショートカット。
# ('vk', n) はWindows仮想キー、('vk_ext', n) は拡張仮想キー、
# ('ctrl', key) はCtrlとの同時押しを表す。
_FUNCTION_KEYS = [('vk', vk) for vk in range(0x7C, 0x88)]  # F13-F24
_NUMPAD_KEYS = [
    *[('vk', vk) for vk in range(0x60, 0x6A)],  # Num0-Num9
    ('vk', 0x6E),  # Decimal
    ('vk', 0x6B),  # Add
    ('vk', 0x6D),  # Subtract
    ('vk', 0x6A),  # Multiply
    ('vk_ext', 0x2D),  # Insert（B2）
]
_LOW_KEYS = [*_FUNCTION_KEYS, *_NUMPAD_KEYS]
_HIGH_KEYS = [
    *_FUNCTION_KEYS,
    *[('vk', vk) for vk in range(0x60, 0x6A)],
    ('vk', 0x6E),       # Decimal
    ('vk_ext', 0x0D),   # Numpad Enter
]

FULL_POWER_NOTE_TO_KEY = {
    **{21 + i: key for i, key in enumerate(_LOW_KEYS)},
    **BASE_NOTE_TO_KEY,
    **{85 + i: ('ctrl', key) for i, key in enumerate(_HIGH_KEYS)},
}

PLAY_MODES = {
    'ffxiv': BASE_NOTE_TO_KEY,
    'full': FULL_POWER_NOTE_TO_KEY,
}

# MIDI番号から音名への変換
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'Bb', 'B']

# 全キー一覧（キーリリース用）
ALL_KEYS = [
    '1', '2', '3', '4', '5', '6', '7', '8', '9', '0', 'q', 'w',
    'e', 'r', 't', 'y', 'u', 'i', 'o', 'p', 'a', 's', 'd', 'f',
    'g', 'h', 'j', 'k', 'l', 'z', 'x', 'c', 'v', 'b', 'n', 'm', ',',
]

# 楽器名のマッピング（GM音源準拠）
INSTRUMENT_NAMES = {
    1: "Acoustic Grand Piano", 2: "Bright Acoustic Piano",
    3: "Electric Grand Piano", 4: "Honky-tonk Piano",
    5: "Electric Piano 1", 6: "Electric Piano 2",
    7: "Harpsichord", 8: "Clavi",
    9: "Celesta", 10: "Glockenspiel", 11: "Music Box", 12: "Vibraphone",
    13: "Marimba", 14: "Xylophone", 15: "Tubular Bells", 16: "Dulcimer",
    17: "Drawbar Organ", 18: "Percussive Organ", 19: "Rock Organ", 20: "Church Organ",
    21: "Reed Organ", 22: "Accordion", 23: "Harmonica", 24: "Tango Accordion",
    25: "Acoustic Guitar (nylon)", 26: "Acoustic Guitar (steel)",
    27: "Electric Guitar (jazz)", 28: "Electric Guitar (clean)",
    29: "Electric Guitar (muted)", 30: "Overdriven Guitar",
    31: "Distortion Guitar", 32: "Guitar harmonics",
    33: "Acoustic Bass", 34: "Electric Bass (finger)",
    35: "Electric Bass (pick)", 36: "Fretless Bass",
    37: "Slap Bass 1", 38: "Slap Bass 2",
    39: "Synth Bass 1", 40: "Synth Bass 2",
    41: "Violin", 42: "Viola", 43: "Cello", 44: "Contrabass",
    45: "Tremolo Strings", 46: "Pizzicato Strings",
    47: "Orchestral Harp", 48: "Timpani",
    49: "String Ensemble 1", 50: "String Ensemble 2",
    51: "SynthStrings 1", 52: "SynthStrings 2",
}
