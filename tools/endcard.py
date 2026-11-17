"""D-22: last staff-roll screen (S77 last page) = one composed picture in the text window.

Rows 22-27 (name row + two text lines, 48 px, contiguous) carry, centred on the screen:
  [THE END]                         the game's own English tiles (CHR bank 0, tiles $0A-$23);
                                    brackets drawn in the same 2 px style (the font has none)
  -플레이 해 주셔서 감사합니다!-    Galmuri, normal glyph cells
  -Nodata-                          owner's logo, 70 % size (data/gfx/nodata_logo.png, 88x19)
The 208x48 canvas (columns 3-28) is cut into 8x16 cells; identical cells share a code and empty
cells are blanks. Cells are reached through private-use characters starting at U+E100.
In the script: speaker "={ENDCARD0}", text "{ENDCARD1}{BR}{ENDCARD2}".
"""
import os
from PIL import Image

import glyphs

BASE = 0xE100
COL0 = 3                      # first text column on screen
W, H = 26 * 8, 48
CENTER = 128 - COL0 * 8       # screen centre in canvas pixels
LOGO = os.path.join(os.path.dirname(__file__), "..", "data", "gfx", "nodata_logo.png")
CAPTION = "-플레이 해 주셔서 감사합니다!-"
BRACKET_L = ["###", "##.", "##.", "##.", "##.", "##.", "###"]
BRACKET_R = ["###", ".##", ".##", ".##", ".##", ".##", "###"]

_cells = None   # list of 1-bit 8x16 images (index = code - BASE)
_rows = None    # three strings


def _eng_tile(chr_rom, ch):
    n = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ".index(ch)
    t = chr_rom[16 * n:16 * n + 16]
    im = Image.new("1", (8, 8), 0)
    for y in range(8):
        for x in range(8):
            if (t[y] | t[8 + y]) & (0x80 >> x):
                im.putpixel((x, y), 1)
    return im


def _bracket(rows):
    im = Image.new("1", (8, 8), 0)
    for y, r in enumerate(rows):
        for x, c in enumerate(r):
            if c == "#":
                im.putpixel((x + 3, y), 1)
    return im


def compose(chr_rom):
    canvas = Image.new("1", (W, H), 0)
    # [THE END]: 9 cells of 8 px, glyph rows 0-6, placed at y 5
    tiles = [_bracket(BRACKET_L)] + [None if c == " " else _eng_tile(chr_rom, c) for c in "THE END"] \
        + [_bracket(BRACKET_R)]
    x0 = CENTER - 36
    for k, t in enumerate(tiles):
        if t is not None:
            canvas.paste(t, (x0 + 8 * k, 5))
    # caption: Galmuri cells (ink rows 2-12), cell top at y 14 -> ink 16-26
    x0 = CENTER - 4 * len(CAPTION)
    for k, ch in enumerate(CAPTION):
        if ch != " ":
            canvas.paste(glyphs.glyph_bitmap(ch).point(lambda v: 255 if v else 0).convert("1"), (x0 + 8 * k, 14))
    # logo 88x19 at y 29-47
    logo = Image.open(LOGO).convert("L").point(lambda v: 255 if v >= 128 else 0).convert("1")
    canvas.paste(logo, (CENTER - logo.width // 2, 29))
    return canvas


def build(chr_rom):
    global _cells, _rows
    canvas = compose(chr_rom)
    cells, index, rows = [], {}, []
    for band in range(3):
        s = ""
        for c in range(W // 8):
            cell = canvas.crop((8 * c, 16 * band, 8 * c + 8, 16 * band + 16))
            key = cell.tobytes()
            if cell.getbbox() is None:
                s += " "
                continue
            if key not in index:
                index[key] = len(cells)
                cells.append(cell.convert("L").point(lambda v: 1 if v else 0))
            s += chr(BASE + index[key])
        rows.append(s.rstrip())
    _cells, _rows = cells, rows
    return rows


def rows():
    return _rows


def bitmap(ch):
    return _cells[ord(ch) - BASE]


def is_card(ch):
    return _cells is not None and BASE <= ord(ch) < BASE + len(_cells)
