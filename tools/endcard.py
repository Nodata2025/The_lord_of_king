"""D-22: last staff-roll screen (S77 last page) = one composed picture in the text window.

Row 21 (y 168-175, just below the picture split) carries [THE END] in the game's own English
tiles (CHR bank 0, $0A-$23; brackets drawn in the same 2 px style, the font has none), written by
the {THEEND} control ($F8: one row of top-half tiles at PPU $22A3).
Rows 22-27 (name row + two text lines, 48 px, contiguous) carry, centred on the screen:
  -플레이 해 주셔서 감사합니다!-    Galmuri, normal glyph cells
  -Nodata-                          owner's logo, 70 % size (data/gfx/nodata_logo.png, 88x19)
The 208x48 canvas (columns 3-28) is cut into 8x16 cells; identical cells share a code and empty
cells are blanks. Cells are reached through private-use characters starting at U+E100.
In the script: "{THEEND}{ENDCARD1}{BR}{ENDCARD2}" (row 22 stays empty, no speaker).
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
BRACKET_L = ["###", "##.", "##.", "##.", "##.", "##.", "###"]   # drawn at columns 4-6 (1 px gap, like letters)
BRACKET_R = ["###", ".##", ".##", ".##", ".##", ".##", "###"]   # drawn at columns 0-2

_cells = None   # list of 1-bit 8x16 images (index = code - BASE)
_rows = None    # three strings
_theend = None  # [THE END] row (screen row 21)
_chr = None     # original CHR (English tiles for ENG_BASE cells)

# D-38: the game's own English tiles (0-9, A-Z) as dialogue glyph cells, reached through
# private-use characters ENG_BASE + index; ink rows 4-10 of the 8x16 cell (Hangul: 2-12)
ENG_BASE = 0xE200
ENG_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
ENG_Y = 4


def to_eng(text):
    """Digits and letters outside {CONTROL} tokens -> original-font cells (letters upper-cased)."""
    out, depth = [], 0
    for ch in text:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif depth == 0 and ch.upper() in ENG_CHARS and ch.isascii():
            ch = chr(ENG_BASE + ENG_CHARS.index(ch.upper()))
        out.append(ch)
    return "".join(out)


def is_eng(ch):
    return ENG_BASE <= ord(ch) < ENG_BASE + len(ENG_CHARS)


def eng_bitmap(ch):
    if _chr is None:
        raise SystemExit("endcard: CHR not set (build first)")
    cell = Image.new("L", (8, 16), 0)
    cell.paste(_eng_tile(_chr, ENG_CHARS[ord(ch) - ENG_BASE]).convert("L").point(lambda v: 1 if v else 0), (0, ENG_Y))
    return cell


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
    dx = 4 if rows is BRACKET_L else 0
    for y, r in enumerate(rows):
        for x, c in enumerate(r):
            if c == "#":
                im.putpixel((x + dx, y), 1)
    return im


def bracket_tile(left):
    """NES 2bpp tile (colour 3) of '[' or ']' in the game's font style."""
    im = _bracket(BRACKET_L if left else BRACKET_R)
    lo = bytearray(8)
    for y in range(8):
        for x in range(8):
            if im.getpixel((x, y)):
                lo[y] |= 0x80 >> x
    return bytes(lo) + bytes(lo)


def compose(chr_rom):
    canvas = Image.new("1", (W, H), 0)
    # caption: Galmuri cells (ink rows 2-12), cell top at y 14 -> ink 16-26
    x0 = CENTER - 4 * len(CAPTION)
    for k, ch in enumerate(CAPTION):
        if ch != " ":
            canvas.paste(glyphs.glyph_bitmap(ch).point(lambda v: 255 if v else 0).convert("1"), (x0 + 8 * k, 14))
    # logo 88x19 at y 29-47
    logo = Image.open(LOGO).convert("L").point(lambda v: 255 if v >= 128 else 0).convert("1")
    canvas.paste(logo, (CENTER - logo.width // 2, 29))
    return canvas


def theend_canvas(chr_rom):
    """[THE END] on its own 8 px row (screen row 21, y 168-174), centred like the rest."""
    c = Image.new("1", (W, 8), 0)
    tiles = [_bracket(BRACKET_L)] + [None if ch == " " else _eng_tile(chr_rom, ch) for ch in "THE END"] \
        + [_bracket(BRACKET_R)]
    x0 = CENTER - 36
    for k, t in enumerate(tiles):
        if t is not None:
            c.paste(t, (x0 + 8 * k, 0))
    return c


def build(chr_rom):
    global _cells, _rows, _theend, _chr
    _chr = chr_rom
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
    # [THE END] row: cells whose top 8 px hold the text (only the top tiles are drawn)
    te = theend_canvas(chr_rom)
    s = ""
    for c in range(W // 8):
        top = te.crop((8 * c, 0, 8 * c + 8, 8))
        if top.getbbox() is None:
            s += " "
            continue
        cell = Image.new("1", (8, 16), 0)
        cell.paste(top, (0, 0))
        key = cell.tobytes()
        if key not in index:
            index[key] = len(cells)
            cells.append(cell.convert("L").point(lambda v: 1 if v else 0))
        s += chr(BASE + index[key])
    _theend = s.rstrip()
    _cells, _rows = cells, rows
    return rows


def theend():
    return _theend


def rows():
    return _rows


def bitmap(ch):
    return _cells[ord(ch) - BASE]


def is_card(ch):
    return _cells is not None and BASE <= ord(ch) < BASE + len(_cells)
