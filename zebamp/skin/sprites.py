"""Sprite coordinates of the classic (Winamp 2.x) skin format.

Each sheet maps to the bitmap file name inside a .wsz archive.  Coordinates
are (x, y, width, height) in pixels.  The layout of this format is a de-facto
standard documented by many players; values were cross-checked against the
MIT-licensed Webamp project.
"""

SHEET_FILES = {
    "MAIN": "main",
    "CBUTTONS": "cbuttons",
    "TITLEBAR": "titlebar",
    "SHUFREP": "shufrep",
    "TEXT": "text",
    "NUMBERS": "numbers",
    "NUMS_EX": "nums_ex",
    "PLAYPAUS": "playpaus",
    "MONOSTER": "monoster",
    "POSBAR": "posbar",
    "VOLUME": "volume",
    "BALANCE": "balance",
    "EQMAIN": "eqmain",
    "EQ_EX": "eq_ex",
    "PLEDIT": "pledit",
    "GEN": "gen",
    "GENEX": "genex",
}

S = {
    "MAIN": {
        "MAIN_WINDOW_BACKGROUND": (0, 0, 275, 116),
    },
    "CBUTTONS": {
        "PREV": (0, 0, 23, 18), "PREV_D": (0, 18, 23, 18),
        "PLAY": (23, 0, 23, 18), "PLAY_D": (23, 18, 23, 18),
        "PAUSE": (46, 0, 23, 18), "PAUSE_D": (46, 18, 23, 18),
        "STOP": (69, 0, 23, 18), "STOP_D": (69, 18, 23, 18),
        "NEXT": (92, 0, 22, 18), "NEXT_D": (92, 18, 22, 18),
        "EJECT": (114, 0, 22, 16), "EJECT_D": (114, 16, 22, 16),
    },
    "TITLEBAR": {
        "TITLE": (27, 15, 275, 14), "TITLE_SEL": (27, 0, 275, 14),
        "TITLE_EGG": (27, 72, 275, 14), "TITLE_EGG_SEL": (27, 57, 275, 14),
        "OPTIONS": (0, 0, 9, 9), "OPTIONS_D": (0, 9, 9, 9),
        "MINIMIZE": (9, 0, 9, 9), "MINIMIZE_D": (9, 9, 9, 9),
        "SHADE": (0, 18, 9, 9), "SHADE_D": (9, 18, 9, 9),
        "CLOSE": (18, 0, 9, 9), "CLOSE_D": (18, 9, 9, 9),
        "CLUTTER_BG": (304, 0, 8, 43), "CLUTTER_BG_DISABLED": (312, 0, 8, 43),
        "CLUTTER_O": (304, 47, 8, 8), "CLUTTER_A": (312, 55, 8, 7),
        "CLUTTER_I": (320, 62, 8, 7), "CLUTTER_D": (328, 69, 8, 8),
        "CLUTTER_V": (336, 77, 8, 7),
        "SHADE_BG": (27, 42, 275, 14), "SHADE_BG_SEL": (27, 29, 275, 14),
        "UNSHADE": (0, 27, 9, 9), "UNSHADE_D": (9, 27, 9, 9),
        "SHADE_POS_BG": (0, 36, 17, 7),
        "SHADE_POS_THUMB": (20, 36, 3, 7),
        "SHADE_POS_THUMB_LEFT": (17, 36, 3, 7),
        "SHADE_POS_THUMB_RIGHT": (23, 36, 3, 7),
    },
    "SHUFREP": {
        "SHUFFLE": (28, 0, 47, 15), "SHUFFLE_D": (28, 15, 47, 15),
        "SHUFFLE_SEL": (28, 30, 47, 15), "SHUFFLE_SEL_D": (28, 45, 47, 15),
        "REPEAT": (0, 0, 28, 15), "REPEAT_D": (0, 15, 28, 15),
        "REPEAT_SEL": (0, 30, 28, 15), "REPEAT_SEL_D": (0, 45, 28, 15),
        "EQ": (0, 61, 23, 12), "EQ_SEL": (0, 73, 23, 12),
        "EQ_D": (46, 61, 23, 12), "EQ_SEL_D": (46, 73, 23, 12),
        "PL": (23, 61, 23, 12), "PL_SEL": (23, 73, 23, 12),
        "PL_D": (69, 61, 23, 12), "PL_SEL_D": (69, 73, 23, 12),
    },
    "PLAYPAUS": {
        "PLAYING": (0, 0, 9, 9), "PAUSED": (9, 0, 9, 9),
        "STOPPED": (18, 0, 9, 9),
        "NOT_WORKING": (36, 0, 3, 9), "WORKING": (39, 0, 3, 9),
    },
    "MONOSTER": {
        "STEREO": (0, 12, 29, 12), "STEREO_SEL": (0, 0, 29, 12),
        "MONO": (29, 12, 27, 12), "MONO_SEL": (29, 0, 27, 12),
    },
    "POSBAR": {
        "POS_BG": (0, 0, 248, 10),
        "POS_THUMB": (248, 0, 29, 10), "POS_THUMB_SEL": (278, 0, 29, 10),
    },
    "VOLUME": {
        "VOL_THUMB": (15, 422, 14, 11), "VOL_THUMB_SEL": (0, 422, 14, 11),
    },
    "BALANCE": {
        "BAL_THUMB": (15, 422, 14, 11), "BAL_THUMB_SEL": (0, 422, 14, 11),
    },
    "EQMAIN": {
        "EQ_BG": (0, 0, 275, 116),
        "EQ_TITLE": (0, 149, 275, 14), "EQ_TITLE_SEL": (0, 134, 275, 14),
        "EQ_THUMB": (0, 164, 11, 11), "EQ_THUMB_SEL": (0, 176, 11, 11),
        "EQ_CLOSE": (0, 116, 9, 9), "EQ_CLOSE_D": (0, 125, 9, 9),
        "EQ_ON": (10, 119, 26, 12), "EQ_ON_D": (128, 119, 26, 12),
        "EQ_ON_SEL": (69, 119, 26, 12), "EQ_ON_SEL_D": (187, 119, 26, 12),
        "EQ_AUTO": (36, 119, 32, 12), "EQ_AUTO_D": (154, 119, 32, 12),
        "EQ_AUTO_SEL": (95, 119, 32, 12), "EQ_AUTO_SEL_D": (213, 119, 32, 12),
        "EQ_GRAPH_BG": (0, 294, 113, 19),
        "EQ_GRAPH_COLORS": (115, 294, 1, 19),
        "EQ_PRESETS": (224, 164, 44, 12), "EQ_PRESETS_D": (224, 176, 44, 12),
        "EQ_PREAMP_LINE": (0, 314, 113, 1),
        "EQ_SHADE_BTN_FALLBACK": (254, 152, 9, 9),
    },
    "EQ_EX": {
        "EQS_BG_SEL": (0, 0, 275, 14), "EQS_BG": (0, 15, 275, 14),
        "EQS_VOL_L": (1, 30, 3, 7), "EQS_VOL_C": (4, 30, 3, 7),
        "EQS_VOL_R": (7, 30, 3, 7),
        "EQS_BAL_L": (11, 30, 3, 7), "EQS_BAL_C": (14, 30, 3, 7),
        "EQS_BAL_R": (17, 30, 3, 7),
        "EQ_MAXIMIZE_D": (1, 38, 9, 9), "EQ_MINIMIZE_D": (1, 47, 9, 9),
        "EQS_CLOSE": (11, 38, 9, 9), "EQS_CLOSE_D": (11, 47, 9, 9),
    },
    "PLEDIT": {
        "TOP_TILE": (127, 21, 25, 20), "TOP_LEFT": (0, 21, 25, 20),
        "TOP_TITLE": (26, 21, 100, 20), "TOP_RIGHT": (153, 21, 25, 20),
        "TOP_TILE_SEL": (127, 0, 25, 20), "TOP_LEFT_SEL": (0, 0, 25, 20),
        "TOP_TITLE_SEL": (26, 0, 100, 20), "TOP_RIGHT_SEL": (153, 0, 25, 20),
        "LEFT_TILE": (0, 42, 12, 29), "RIGHT_TILE": (31, 42, 20, 29),
        "BOTTOM_TILE": (179, 0, 25, 38),
        "BOTTOM_LEFT": (0, 72, 125, 38), "BOTTOM_RIGHT": (126, 72, 150, 38),
        "VIS_BG": (205, 0, 75, 38),
        "SHADE_BG": (72, 57, 25, 14), "SHADE_LEFT": (72, 42, 25, 14),
        "SHADE_RIGHT": (99, 57, 50, 14), "SHADE_RIGHT_SEL": (99, 42, 50, 14),
        "SCROLL_HANDLE_SEL": (61, 53, 8, 18), "SCROLL_HANDLE": (52, 53, 8, 18),
        "ADD_URL": (0, 111, 22, 18), "ADD_URL_D": (23, 111, 22, 18),
        "ADD_DIR": (0, 130, 22, 18), "ADD_DIR_D": (23, 130, 22, 18),
        "ADD_FILE": (0, 149, 22, 18), "ADD_FILE_D": (23, 149, 22, 18),
        "REM_ALL": (54, 111, 22, 18), "REM_ALL_D": (77, 111, 22, 18),
        "REM_CROP": (54, 130, 22, 18), "REM_CROP_D": (77, 130, 22, 18),
        "REM_SEL": (54, 149, 22, 18), "REM_SEL_D": (77, 149, 22, 18),
        "REM_MISC": (54, 168, 22, 18), "REM_MISC_D": (77, 168, 22, 18),
        "SEL_INV": (104, 111, 22, 18), "SEL_INV_D": (127, 111, 22, 18),
        "SEL_ZERO": (104, 130, 22, 18), "SEL_ZERO_D": (127, 130, 22, 18),
        "SEL_ALL": (104, 149, 22, 18), "SEL_ALL_D": (127, 149, 22, 18),
        "MISC_SORT": (154, 111, 22, 18), "MISC_SORT_D": (177, 111, 22, 18),
        "MISC_INFO": (154, 130, 22, 18), "MISC_INFO_D": (177, 130, 22, 18),
        "MISC_OPTS": (154, 149, 22, 18), "MISC_OPTS_D": (177, 149, 22, 18),
        "LIST_NEW": (204, 111, 22, 18), "LIST_NEW_D": (227, 111, 22, 18),
        "LIST_SAVE": (204, 130, 22, 18), "LIST_SAVE_D": (227, 130, 22, 18),
        "LIST_LOAD": (204, 149, 22, 18), "LIST_LOAD_D": (227, 149, 22, 18),
        "BAR_ADD": (48, 111, 3, 54), "BAR_REM": (100, 111, 3, 72),
        "BAR_SEL": (150, 111, 3, 54), "BAR_MISC": (200, 111, 3, 54),
        "BAR_LIST": (250, 111, 3, 54),
        "CLOSE_D": (52, 42, 9, 9), "COLLAPSE_D": (62, 42, 9, 9),
        "EXPAND_D": (150, 42, 9, 9),
    },
    "GEN": {
        "TL_SEL": (0, 0, 25, 20), "TLE_SEL": (26, 0, 25, 20),
        "TC_SEL": (52, 0, 25, 20), "TRE_SEL": (78, 0, 25, 20),
        "TLRF_SEL": (104, 0, 25, 20), "TR_SEL": (130, 0, 25, 20),
        "TL": (0, 21, 25, 20), "TLE": (26, 21, 25, 20), "TC": (52, 21, 25, 20),
        "TRE": (78, 21, 25, 20), "TLRF": (104, 21, 25, 20),
        "TR": (130, 21, 25, 20),
        "BL": (0, 42, 125, 14), "BR": (0, 57, 125, 14),
        "BF": (127, 72, 25, 14),
        "ML": (127, 42, 11, 29), "MLB": (158, 42, 11, 24),
        "MR": (139, 42, 8, 29), "MRB": (170, 42, 8, 24),
        "CLOSE_D": (148, 42, 9, 9),
    },
}

# Volume background: 28 frames of 68x13 stacked every 15 px.
VOLUME_FRAME = (0, 0, 68, 13)
VOLUME_FRAMES = 28
BALANCE_FRAME = (9, 0, 38, 13)
BALANCE_FRAMES = 28

# 5x6 bitmap font in text.bmp: char -> (row, column).
FONT_LOOKUP = {}
for _i, _c in enumerate("abcdefghijklmnopqrstuvwxyz\"@"):
    FONT_LOOKUP[_c] = (0, _i)
FONT_LOOKUP[" "] = (0, 30)
for _i, _c in enumerate("0123456789….:()-'!_+\\/[]^&%,=$#"):
    FONT_LOOKUP[_c] = (1, _i)
FONT_LOOKUP.update({"Å": (2, 0), "Ö": (2, 1), "Ä": (2, 2), "?": (2, 3),
                    "*": (2, 4), "<": (1, 22), ">": (1, 23), "{": (1, 22),
                    "}": (1, 23), "å": (2, 0), "ö": (2, 1), "ä": (2, 2)})
CHAR_W, CHAR_H = 5, 6

# Default visualisation colours (viscolor.txt order).
DEFAULT_VISCOLORS = [
    (0, 0, 0), (24, 33, 41), (239, 49, 16), (206, 41, 16), (214, 90, 0),
    (214, 102, 0), (214, 115, 0), (198, 123, 8), (222, 165, 24),
    (214, 181, 33), (189, 222, 41), (148, 222, 33), (41, 206, 16),
    (50, 190, 16), (57, 181, 16), (49, 156, 8), (41, 148, 0), (24, 132, 8),
    (255, 255, 255), (214, 214, 222), (181, 189, 189), (160, 170, 175),
    (148, 156, 165), (150, 150, 150),
]

DEFAULT_PLEDIT = {
    "normal": "#00FF00", "current": "#FFFFFF", "normalbg": "#000000",
    "selectedbg": "#0000FF", "font": "Arial",
}
