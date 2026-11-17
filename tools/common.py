"""Shared source-profile check and Japanese character table for The Lord of King (FC, JP).

The ROM path is never hard-coded: pass it on the command line or set LOK_ROM.
"""
import hashlib
import os
import sys

# Supported source profile (iNES, headered). See docs/survey.md.
SOURCE_PROFILE = {
    "name": "Lord of King, The (Japan) [iNES]",
    "size": 262160,
    "sha1": "b1cad2d3e38ccd7780437d2c83effa254576861b",
    "body_crc32": "D0EB749F",
    "mapper": 18,
    "prg_16k": 8,
    "chr_8k": 16,
}

HEADER = 16
PRG_SIZE = 8 * 16384


def load_rom(path=None):
    path = path or os.environ.get("LOK_ROM")
    if not path:
        sys.exit("ROM path required (argument or LOK_ROM)")
    data = open(path, "rb").read()
    sha1 = hashlib.sha1(data).hexdigest()
    if len(data) != SOURCE_PROFILE["size"] or sha1 != SOURCE_PROFILE["sha1"]:
        sys.exit(f"unsupported source: size={len(data)} sha1={sha1}")
    return data


def prg(rom):
    return rom[HEADER:HEADER + PRG_SIZE]


def chr_rom(rom):
    return rom[HEADER + PRG_SIZE:]


# Tile codes $80-$F7 in CHR $0800-$0F7F (BG pattern table $0000).
_KATA = ("アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミ"
         "ムメモヤユヨラリルレロワヲンァィゥェォャュョッ゛゜、。「」!?ー")
_HIRA = ("・あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほま"
         "みむめもやゆよらりるれろわをんぁぃぅぇぉゃゅょっ")

JA = {}
for _i, _c in enumerate(_KATA):
    JA[0x80 + _i] = _c
for _i, _c in enumerate(_HIRA):
    JA[0xC0 + _i] = _c
# Shared (kept) tiles that also appear in text.
for _i, _c in enumerate("0123456789ABCDEFGHIJKLMNOPQRSTUV"):
    JA[_i] = _c
for _i, _c in enumerate("WXYZ"):
    JA[0x20 + _i] = _c
JA[0xFF] = " "

# Control codes, confirmed from the text engine at bank 10 $8066.
CONTROLS = {
    0xFB: "{PAGE}",   # clear window rows, column := 0
    0xFC: "{WAIT}",   # pause $80 frames, then continue
    0xFD: "{BR}",     # jump to line 2 (column := 26)
    0xFE: "{END}",    # stop the text engine
}

DAKUTEN, HANDAKUTEN = 0xB7, 0xB8
_VOICED = dict(zip("かきくけこさしすせそたちつてとはひふへほカキクケコサシスセソタチツテトハヒフヘホウ",
                   "がぎぐげござじずぜぞだぢづでどばびぶべぼガギグゲゴザジズゼゾダヂヅデドバビブベボヴ"))
_SEMI = dict(zip("はひふへほハヒフヘホ", "ぱぴぷぺぽパピプペポ"))


def decode(data):
    """Bytes -> readable text. Base kana + ゛/゜ are shown precomposed; reversible by encode()."""
    out = []
    for b in data:
        if b in CONTROLS:
            out.append(CONTROLS[b])
        elif b == DAKUTEN and out and out[-1] in _VOICED:
            out[-1] = _VOICED[out[-1]]
        elif b == HANDAKUTEN and out and out[-1] in _SEMI:
            out[-1] = _SEMI[out[-1]]
        elif b in JA:
            out.append(JA[b])
        else:
            out.append("{$%02X}" % b)
    return "".join(out)


_REV = {v: k for k, v in JA.items()}
_REV_V = {v: k for k, v in _VOICED.items()}
_REV_S = {v: k for k, v in _SEMI.items()}
_REV_C = {v: k for k, v in CONTROLS.items()}


def encode(text):
    import re
    out = bytearray()
    for tok in re.findall(r"\{[^}]+\}|.", text, re.S):
        if tok in _REV_C:
            out.append(_REV_C[tok])
        elif tok.startswith("{$"):
            out.append(int(tok[2:4], 16))
        elif tok in _REV_V:
            out += bytes([_REV[_REV_V[tok]], DAKUTEN])
        elif tok in _REV_S:
            out += bytes([_REV[_REV_S[tok]], HANDAKUTEN])
        else:
            out.append(_REV[tok])
    return bytes(out)
