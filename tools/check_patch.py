"""Check that an IPS patch carries no source text or source font tiles.

usage: LOK_FONT=... python3 tools/check_patch.py ROM PATCH.ips

* Source text: every 8-byte window of every original script entry is searched in the
  patch payload. Windows made of one repeated byte (e.g. 8 spaces) are ignored.
* Source tiles: each original kana tile ($80-$F7) is searched, unless the same 16 bytes are
  also produced by our own Galmuri glyph generation (coincidental simple shapes such as a
  horizontal bar).
Exit status 1 on any finding.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import load_rom, prg, chr_rom, decode  # noqa: E402
import glyphs  # noqa: E402
from extract_script import BANK_FILE, BANK_CPU, PTR_TABLE, PTR_COUNT, SCRIPT_END_CPU  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    rom = load_rom(sys.argv[1])
    ips = open(sys.argv[2], "rb").read()
    p = prg(rom)
    t = BANK_FILE + PTR_TABLE - BANK_CPU
    ptrs = [p[t + 2 * i] | p[t + 2 * i + 1] << 8 for i in range(PTR_COUNT)] + [SCRIPT_END_CPU]
    text_hits = []
    for i in range(PTR_COUNT):
        raw = p[BANK_FILE + ptrs[i] - BANK_CPU:BANK_FILE + ptrs[i + 1] - BANK_CPU]
        for k in range(0, max(0, len(raw) - 8) + 1):
            w = raw[k:k + 8]
            if len(w) == 8 and len(set(w)) > 1 and w in ips:
                text_hits.append(f"S{i:02d}@{k}:{w.hex()}")
                break
    script = json.load(open(os.path.join(ROOT, "data", "script_ko.json"), encoding="utf-8"))["entries"]
    own = set()
    for ch in {c for e in script.values() for c in e.get("ko", "") if c not in "{} "}:
        try:
            own.update(glyphs.to_tiles(glyphs.glyph_bitmap(ch)))
        except ValueError:
            pass
    c = chr_rom(rom)
    tile_hits = []
    for k in range(0x78):
        tile = c[0x800 + 16 * k:0x810 + 16 * k]
        if any(tile) and tile in ips and tile not in own:
            tile_hits.append(f"${0x80 + k:02X}")
    print("source text windows:", text_hits or "none")
    print("source kana tiles:", tile_hits or "none")
    sys.exit(1 if text_hits or tile_hits else 0)


if __name__ == "__main__":
    main()
