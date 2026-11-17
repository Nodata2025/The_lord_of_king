"""Product build: Korean script + Hangul font sets -> patched ROM.

usage: LOK_FONT=Galmuri11-Condensed.ttf python3 tools/build.py ROM [out.nes]

Design (docs/survey.md, docs/design.md):
  * CHR-ROM 128 KB -> 256 KB. Font set n = 1 KB banks $80+2n (tiles $80-$BF, top halves)
    and $81+2n (tiles $C0-$FF, bottom halves). Glyph code c ($80-$BE) draws tile c over c+$40.
    Code $BF is a reserved blank (space); tile $FF stays blank in every set.
  * Text control {FONT n} = $FA n selects a set for the following page(s).
  * Hooks in bank 10 (text engine) draw 1x2 tiles, clear 4 rows on {PAGE}, and restore the
    original font banks on {END}. Untranslated strings keep their original bytes and 1x1 path.
"""
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import load_rom, prg, decode, HEADER, PRG_SIZE  # noqa: E402
from asm6502 import assemble  # noqa: E402
import glyphs  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BANK_FILE, BANK_CPU = 0x14000, 0x8000
PTR_TABLE, PTR_COUNT = 0x80EC, 78
TEXT_START, TEXT_END = 0x8188, 0x8F01          # original script region
SPILL_START, SPILL_END = 0x928E, 0x9E00        # $FF-filled tail of bank 10 (candidate free)
CODE_ORG, CODE_END = 0x9E00, 0xA000

LINE_CELLS = 26
MAX_LINES = 2
SET_CAPACITY = 63                               # codes $80-$BE
BLANK_CODE = 0xBF
FIRST_SET_BANK = 0x80                           # 1 KB bank index of set 0 (top half)
MAX_SETS = 64

CTRL = {"{PAGE}": 0xFB, "{WAIT}": 0xFC, "{BR}": 0xFD, "{END}": 0xFE}

# Expected original bytes at each patch site (CPU address in bank 10).
PATCHES_EXPECT = {
    0x8066: bytes.fromhex("ADDF03"),     # LDA $03DF   (control dispatch)
    0x8093: bytes.fromhex("A9DDA003"),   # LDA #$DD / LDY #$03 (1x1 glyph source)
    0x80A9: bytes.fromhex("ADD703"),     # LDA $03D7   ({END} handler)
    0x80CD: bytes.fromhex("DF"),         # LDA #<clear table
    0x80D1: bytes.fromhex("80"),         # LDA #>clear table
}

HOOKS = """
; ---- control dispatch: {FONT n} ----
pre:     LDA $03DF
         CMP #$FA
         BEQ setfont
         RTS
setfont: LDY $03DA
         INY
         LDA ($18),Y          ; n
         ASL A
         CLC
         ADC #FIRST           ; bank of top half
         JSR setbanks
         INC $03DA
         INC $03DA
         PLA                  ; leave the tick without printing
         PLA
         RTS
; A = 1 KB bank for PPU $0800 (A+1 -> $0C00). Zero page $03 is the game's own
; per-frame source for these slots (bank 14 $CD67 copies it to $0154-7 every frame);
; the live registers are written too so the change is immediate.
setbanks: STA $03
         TAX
         AND #$0F
         STA $B000
         TXA
         LSR A
         LSR A
         LSR A
         LSR A
         STA $B001
         INX
         TXA
         AND #$0F
         STA $B002
         TXA
         LSR A
         LSR A
         LSR A
         LSR A
         STA $B003
         RTS
; ---- glyph source: returns A/Y = queue source pointer ----
newchar: LDA $03
         CMP #FIRST           ; Korean set active?
         BCC legacy
         LDA $03DF
         STA $03DE            ; top tile
         CLC
         ADC #$40
         STA $03DF            ; bottom tile
         LDA #$01
         STA $03DC            ; width 1  ($03DC is idle outside {WAIT})
         LDA #$02
         STA $03DD            ; height 2
         LDA #$DC
         LDY #$03
         RTS
legacy:  LDA #$01
         STA $03DD
         STA $03DE
         LDA #$DD
         LDY #$03
         RTS
; ---- {END}: give the original font banks back ----
endhook: LDA $03
         CMP #FIRST
         BCC endkeep
         LDA #$02             ; original font banks 2/3 (opening: observed)
         JSR setbanks
endkeep: LDA $03D7
         RTS
; ---- {PAGE} clear: 4 rows (glyph rows 22-25), source $CD01 = [$A0][1][$FF] ----
cleartbl: .db $04
         .db $01,$CD,$C0,$22
         .db $01,$CD,$E0,$22
         .db $01,$CD,$00,$23
         .db $01,$CD,$20,$23
"""


def cpu2file(a):
    return BANK_FILE + a - BANK_CPU


def tokens(text):
    return re.findall(r"\{[^}]+\}|.", text, re.S)


def load_script():
    path = os.path.join(ROOT, "data", "script_ko.json")
    return json.load(open(path, encoding="utf-8"))


def source_entries(p):
    t = cpu2file(PTR_TABLE)
    ptrs = [p[t + 2 * i] | p[t + 2 * i + 1] << 8 for i in range(PTR_COUNT)]
    bounds = ptrs + [TEXT_END]
    out = []
    for i in range(PTR_COUNT):
        raw = p[cpu2file(ptrs[i]):cpu2file(bounds[i + 1])]
        out.append(raw)
    return out


def check_layout(sid, text):
    """2 lines x 26 cells per page; every page ends with {WAIT}{PAGE} or the string ends with {END}."""
    if not text.endswith("{END}"):
        raise SystemExit(f"{sid}: must end with {{END}}")
    for pi, page in enumerate(text.split("{PAGE}")):
        body = re.sub(r"\{(WAIT|END)\}", "", page)
        lines = body.split("{BR}")
        if len(lines) > MAX_LINES:
            raise SystemExit(f"{sid} page {pi}: {len(lines)} lines (max {MAX_LINES})")
        for ln in lines:
            n = len(tokens(ln))
            if n > LINE_CELLS:
                raise SystemExit(f"{sid} page {pi}: line has {n} cells (max {LINE_CELLS}): {ln}")


def pack_sets(pages):
    """Greedy: consecutive pages share a set while the union fits. Returns (set_of_page, sets)."""
    sets, cur, assign = [], [], []
    for chars in pages:
        need = [c for c in dict.fromkeys(chars) if c not in cur]
        if len(cur) + len(need) > SET_CAPACITY:
            sets.append(cur); cur = []
            need = list(dict.fromkeys(chars))
        cur += need
        assign.append(len(sets))
    if cur:
        sets.append(cur)
    if len(sets) > MAX_SETS:
        raise SystemExit(f"{len(sets)} font sets needed, only {MAX_SETS} fit")
    return assign, sets


def main():
    rom = bytearray(load_rom(sys.argv[1] if len(sys.argv) > 1 else None))
    out_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "build", "lok_ko_dev.nes")
    p = bytearray(prg(rom))
    src = source_entries(p)
    script = load_script()["entries"]

    # --- verify translation baseline and layout
    ko = {}
    for sid, e in script.items():
        i = int(sid[1:])
        if hashlib.sha1(src[i]).hexdigest() != e["src_sha1"]:
            raise SystemExit(f"{sid}: source hash mismatch (stale translation baseline)")
        if e.get("ko"):
            check_layout(sid, e["ko"])
            ko[i] = e["ko"]

    # --- pages in script order, glyph sets
    page_chars, page_ref = [], []
    for i in sorted(ko):
        for pi, page in enumerate(ko[i].split("{PAGE}")):
            chars = [t for t in tokens(page) if not t.startswith("{") and t != " "]
            page_chars.append(chars); page_ref.append((i, pi))
    assign, sets = pack_sets(page_chars)
    set_of = dict(zip(page_ref, assign))

    # --- encode strings
    blobs = []
    for i in range(PTR_COUNT):
        if i not in ko:
            blobs.append(bytes(src[i])); continue
        out, cur = bytearray(), None
        for pi, page in enumerate(ko[i].split("{PAGE}")):
            if pi > 0:
                out.append(CTRL["{PAGE}"])
            body = page
            s = set_of.get((i, pi))
            if s is not None and s != cur and re.sub(r"\{[^}]+\}", "", body).strip():
                out += bytes([0xFA, s]); cur = s
            for t in tokens(body):
                if t in CTRL:
                    out.append(CTRL[t])
                elif t == " ":
                    out.append(BLANK_CODE)
                else:
                    out.append(0x80 + sets[cur].index(t))
        blobs.append(bytes(out))

    # --- place strings: original region first, then the spill area
    regions = [[TEXT_START, TEXT_END], [SPILL_START, SPILL_END]]
    ptrs, r = [], 0
    for b in blobs:
        while regions[r][0] + len(b) > regions[r][1]:
            r += 1
            if r >= len(regions):
                raise SystemExit("script does not fit in bank 10")
        ptrs.append(regions[r][0])
        a = cpu2file(regions[r][0]); p[a:a + len(b)] = b; regions[r][0] += len(b)
    used = {"main": regions[0][0] - TEXT_START, "spill": regions[1][0] - SPILL_START}
    # pad freed original region with $FF so stale bytes never look like text
    a0, a1 = cpu2file(regions[0][0]), cpu2file(TEXT_END)
    p[a0:a1] = b"\xff" * (a1 - a0)
    t = cpu2file(PTR_TABLE)
    for k, v in enumerate(ptrs):
        p[t + 2 * k] = v & 0xFF; p[t + 2 * k + 1] = v >> 8

    # --- hooks
    code, labels = assemble(HOOKS.replace("FIRST", "$%02X" % FIRST_SET_BANK), CODE_ORG)
    if CODE_ORG + len(code) > CODE_END:
        raise SystemExit("hook code too large")
    orig = prg(rom)
    for cpu, exp in PATCHES_EXPECT.items():
        got = orig[cpu2file(cpu):cpu2file(cpu) + len(exp)]
        if got != exp:
            raise SystemExit(f"unexpected source bytes at ${cpu:04X}: {got.hex()}")
    for a in range(cpu2file(CODE_ORG), cpu2file(CODE_ORG) + len(code)):
        if orig[a] != 0xFF:
            raise SystemExit(f"hook area not $FF at file ${a:05X}")
    for a in range(cpu2file(SPILL_START), cpu2file(SPILL_START) + used["spill"]):
        if orig[a] != 0xFF:
            raise SystemExit(f"spill area not $FF at file ${a:05X}")
    c0 = cpu2file(CODE_ORG); p[c0:c0 + len(code)] = code
    jsr = lambda lab: bytes([0x20, labels[lab] & 0xFF, labels[lab] >> 8])
    def put(cpu, b):
        a = cpu2file(cpu); p[a:a + len(b)] = b
    put(0x8066, jsr("pre"))
    put(0x8093, jsr("newchar") + b"\xea")
    put(0x80A9, jsr("endhook"))
    put(0x80CD, bytes([labels["cleartbl"] & 0xFF]))
    put(0x80D1, bytes([labels["cleartbl"] >> 8]))

    # --- CHR: append 128 KB of font sets
    chr_old = bytes(rom[HEADER + PRG_SIZE:])
    new = bytearray(b"\x00" * 0x20000)
    for n, chars in enumerate(sets):
        top = 0x400 * (2 * n); bot = top + 0x400
        for k, ch in enumerate(chars):
            tt, bt = glyphs.to_tiles(glyphs.glyph_bitmap(ch))
            new[top + 16 * k: top + 16 * k + 16] = tt
            new[bot + 16 * k: bot + 16 * k + 16] = bt
        # code $BF (k=63) stays blank in both halves
    header = bytearray(rom[:HEADER]); header[5] = 32
    out = bytes(header) + bytes(p) + chr_old + bytes(new)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    open(out_path, "wb").write(out)
    nontr = PTR_COUNT - len(ko)
    report = {
        "output": os.path.basename(out_path),
        "sha1": hashlib.sha1(out).hexdigest(),
        "translated_entries": len(ko),
        "untranslated_entries_kept_original": nontr,
        "distribution": "NOT FOR DISTRIBUTION (development input policy)" if nontr else "candidate",
        "font_sets": len(sets),
        "glyphs_per_set": [len(s) for s in sets],
        "text_bytes": used,
        "hook_bytes": len(code),
        "hook_labels": {k: "$%04X" % v for k, v in labels.items()},
    }
    json.dump(report, open(out_path + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
