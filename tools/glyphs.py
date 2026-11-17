"""Render Galmuri11 Condensed glyphs into NES 8x16 tiles (top + bottom 8x8, 2bpp).

Font path: argument or LOK_FONT. The font file is not tracked (docs/decisions.md D-02).
Profile: size 12px, baseline offset Y_OFF, ink colour index 3, threshold 128.
"""
import os
from PIL import Image, ImageDraw, ImageFont

SIZE = 12
Y_OFF = 1          # bbox top of Hangul is 1 at size 12 -> ink rows 2..12 of 16
INK = 3            # same colour index as the original kana tiles
BLANK_TILE = bytes(16)

_font_cache = {}


def font(path=None):
    path = path or os.environ.get("LOK_FONT")
    if not path:
        raise SystemExit("font path required (LOK_FONT)")
    if path not in _font_cache:
        _font_cache[path] = ImageFont.truetype(path, SIZE)
    return _font_cache[path]


# D-22: the owner's "-Nodata-" logo (data/gfx/nodata_logo.png, 128x28, 1-bit) is cut into
# 8x16 cells and reached through private-use characters: row r (0 top, 1 bottom), column c
# -> chr(LOGO_BASE + 16*r + c). The logo sits 2 px down inside its 32 px band.
LOGO_BASE = 0xE000
LOGO_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "gfx", "nodata_logo.png")
_logo = None


def logo_chars(row):
    return "".join(chr(LOGO_BASE + 16 * row + c) for c in range(16))


def _logo_cell(code):
    global _logo
    if _logo is None:
        src = Image.open(LOGO_PATH).convert("L")
        if src.size != (128, 28):
            raise SystemExit("logo must be 128x28")
        _logo = Image.new("L", (128, 32), 0)
        _logo.paste(src, (0, 2))
    k = code - LOGO_BASE
    r, c = divmod(k, 16)
    return _logo.crop((8 * c, 16 * r, 8 * c + 8, 16 * r + 16)).point(lambda v: 1 if v >= 128 else 0)


def glyph_bitmap(ch, fpath=None):
    """8x16 1-bit image of one character; fails if it does not fit 8 px."""
    if LOGO_BASE <= ord(ch) < LOGO_BASE + 32:
        return _logo_cell(ord(ch))
    f = font(fpath)
    im = Image.new("L", (16, 16), 0)
    ImageDraw.Draw(im).text((0, Y_OFF), ch, font=f, fill=255)
    box = im.getbbox()
    if ch.strip() and box is None:
        raise ValueError(f"glyph missing in font: {ch!r}")
    if box and box[2] > 8:
        raise ValueError(f"glyph wider than 8px: {ch!r} {box}")
    return im.crop((0, 0, 8, 16)).point(lambda v: 1 if v >= 128 else 0)


def to_tiles(bm):
    """1-bit 8x16 -> (top_tile, bottom_tile) in NES 2bpp format, colour INK."""
    out = []
    for ty in (0, 8):
        lo = bytearray(8); hi = bytearray(8)
        for y in range(8):
            row = 0
            for x in range(8):
                if bm.getpixel((x, ty + y)):
                    row |= 0x80 >> x
            lo[y] = row if INK & 1 else 0
            hi[y] = row if INK & 2 else 0
        out.append(bytes(lo + hi))
    return tuple(out)
