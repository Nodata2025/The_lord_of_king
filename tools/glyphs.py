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


def glyph_bitmap(ch, fpath=None):
    """8x16 1-bit image of one character; fails if it does not fit 8 px."""
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
