"""Find the kana marker tile (LOK_KANA=marker builds) in screenshots.

usage: python3 tools/emu/find_marker.py SHOT_DIR [SHOT_DIR...]
Prints every screenshot where an 8x8 window matches the marker shape (any palette,
any scroll offset): pixels under the marker's 1-bits share one colour, 0-bits another.
"""
import glob
import os
import sys

import numpy as np
from PIL import Image

ROWS = [0xF0, 0x88, 0x84, 0x82, 0x41, 0x21, 0x11, 0x0F]
P = np.array([[(r >> (7 - x)) & 1 for x in range(8)] for r in ROWS], dtype=bool)


def find(path):
    a = np.asarray(Image.open(path).convert("RGB")).astype(np.int32)
    c = (a[..., 0] << 16) | (a[..., 1] << 8) | a[..., 2]
    w = np.lib.stride_tricks.sliding_window_view(c, (8, 8))       # (H-7, W-7, 8, 8)
    ones = w[..., P]; zeros = w[..., ~P]
    ok = (ones.min(-1) == ones.max(-1)) & (zeros.min(-1) == zeros.max(-1)) & (ones[..., 0] != zeros[..., 0])
    ys, xs = np.nonzero(ok)
    return list(zip(xs.tolist(), ys.tolist()))


def main():
    total = 0
    for d in sys.argv[1:]:
        for f in sorted(glob.glob(os.path.join(d, "*.png"))):
            hits = find(f)
            if hits:
                total += 1
                rows = sorted({y for _, y in hits})
                print(f"{f}: {len(hits)} marker cells, y={rows[:6]}{'...' if len(rows) > 6 else ''}")
    print(f"screens with original kana: {total}")
    sys.exit(1 if total else 0)


if __name__ == "__main__":
    main()
