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
SPILL_START, SPILL_END = 0x928E, 0x9A00        # $FF-filled tail of bank 10; $9A00-$9DFF = menus
CODE_ORG, CODE_END = 0x9E00, 0xA000

LINE_CELLS = 26
MAX_LINES = 2
SET_CAPACITY = 63                               # codes $80-$BE
BLANK_CODE = 0xBF
FIRST_SET_BANK = 0x80                           # 1 KB bank index of set 0 (top half)
MAX_SETS = 64

# ---- in-game menu (bank 12, "weapon exchange / magic up", item type 6) ----
M_BANK_FILE = 0x18000                 # bank 12 at $8000 while the menu runs
FIXED_FILE, FIXED_CPU = 0x1E000, 0xE000
FIXED_FREE = (0xFEEE, 0xFFE0)         # $FF-filled, before the internal title "THE LORD OF KING"
MENU_SRC = {                          # id: (cpu addr, kind, original length incl. terminator/header)
    "M0": (0x8388, "string", 23),     # question, typed at PPU $2AE4
    "M1": (0x83A0, "block", 23),      # choice line, block [w][h] queued at PPU $2B24
    "M2": (0x83CD, "string", 18),     # cheer, typed at PPU $2B24
}
MENU_EXPECT = {
    0x8320: bytes.fromhex("A9018D5D058D5E05"),   # 1x1 header for the typed glyph
    0x81CA: bytes.fromhex("A9A0A083"),           # LDA #<block / LDY #>block
}
MENU_CALL_FILE = 0x1CA66                          # bank 14 $CA66: JSR $80C2 (menu)
MENU_CALL_EXPECT = bytes.fromhex("20C280")
MENU_CELLS = 25                                   # window interior from column 4

MENU_HOOKS = """
fsetbanks: STA $03             ; applied by the game's own per-frame copy ($CD04 in the menu loop)
         RTS
; bank 14 $CA66 calls this instead of the menu: Korean set in, menu, original banks back
menuwrap: LDA #MENUBANK
         JSR fsetbanks
         JSR $80C2
         LDA #$02
         JSR fsetbanks
         RTS
; bank 12 $8320: build a 1x2 source [1][2][top=$055F][bottom=$0560]
menuchar: LDA $055F
         CMP #$80
         BCC mblank            ; kept tiles ($00-$7F, e.g. SPELL POWER UP): blank below
         CMP #$FF
         BEQ mblank
         CLC
         ADC #$40
         BNE mstore
mblank:  LDA #$FF
mstore:  STA $0560
         LDA #$01
         STA $055D
         LDA #$02
         STA $055E
         RTS
; ---- HUD split address (D-10): the game stores the HUD nametable address ($2Bxx) in
; $E9/$EA and writes it to $2006 in the IRQ. Bit $20 of the high byte lands in fine Y, so
; the HUD was drawn 2 px low and the last 2 scanlines showed attribute bytes as digit tiles.
; Clearing that bit at the two places that set $EA removes the strip (timing unchanged).
hudset1: PHP                   ; bank 14 $C06A (was STY $EA / RTS)
         PHA
         TYA
         AND #$DF
         STA $EA
         PLA
         PLP
         RTS
hudset2: PHA                   ; bank 14 $C216 (was STY $EA / INC $034D / RTS)
         TYA
         AND #$DF
         STA $EA
         PLA
         INC $034D
         RTS
menublock: .db BLOCK
"""
HUD_SITES = {                  # bank 14 file offset: expected original bytes
    0x1C06A: bytes.fromhex("84EA60"),
    0x1C216: bytes.fromhex("84EAEE4D0360"),
}

WAIT_FRAMES = 60   # D-18 (original $80 = 128 frames, about 2.1 s)
CTRL = {"{PAGE}": 0xFB, "{WAIT}": 0xFC, "{BR}": 0xFD, "{END}": 0xFE}

# Expected original bytes at each patch site (CPU address in bank 10).
PATCHES_EXPECT = {
    0x8066: bytes.fromhex("ADDF03"),     # LDA $03DF   (control dispatch)
    0x8093: bytes.fromhex("A9DDA003"),   # LDA #$DD / LDY #$03 (1x1 glyph source)
    0x80A9: bytes.fromhex("ADD703"),     # LDA $03D7   ({END} handler)
    0x800E: bytes.fromhex("ADD703"),     # LDA $03D7   (per-frame: wait check)
    0x8022: bytes.fromhex("E6B0A5B02907D006205380206680"),  # 8-frame tick
    0x80E8: bytes.fromhex("C3220323"),   # line base table: $22C3, $2303
    0x80CD: bytes.fromhex("DF"),         # LDA #<clear table
    0x80D1: bytes.fromhex("80"),         # LDA #>clear table
    0x80BD: bytes.fromhex("80"),         # LDA #$80    ({WAIT}: 128 frames)
}

HOOKS = """
; ---- control dispatch: {FONT n} ----
pre:     LDA $03DF
         CMP #$FA
         BEQ setfont
         CMP #$F9
         BEQ name
         RTS
; {NAME} = $F9 n c1..cn: speaker tag drawn at PPU $22C3 (rows 22-23) as one 1x2-cell block
; through the $0100 buffer. Waits (retries next tick) until the PPU queue is empty.
name:    LDA $30
         BNE nexit
         LDY $03DA
         INY
         LDA ($18),Y
         STA $0100            ; width n
         LDA #$02
         STA $0101
         LDX #$00
nl:      INY
         LDA ($18),Y
         STA $0102,X
         INX
         CPX $0100
         BCC nl
         LDY #$00
nb:      LDA $0102,Y
         CLC
         ADC #$40
         STA $0102,X
         INX
         INY
         CPY $0100
         BCC nb
         LDA #$C3
         STA $18
         LDA #$22
         STA $19
         LDA #$00
         LDY #$01
         JSR $E6B0
         BCS nexit
         LDA $03DA
         CLC
         ADC $0100
         CLC
         ADC #$02
         STA $03DA
nexit:   PLA                  ; leave the tick without printing
         PLA
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
; A = 1 KB bank for PPU $0800 (A+1 -> $0C00). Only zero page $03 is changed: the game
; copies it every frame (bank 14 $CD67 -> $0154-7) and its IRQ applies it at the screen
; split. Writing $B000-$B003 directly here caused a one-frame glitch in the picture area
; when it happened mid-frame (found by the kana-marker scan, 2026-11-17).
setbanks: STA $03
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
; ---- {END}: give the original font banks back, but only when the window was just
; cleared ({PAGE} right before {END}). Strings that end with text still on screen (S76 "끝",
; S77 staff roll) keep their Korean set, otherwise the remaining glyphs would turn into
; other tiles (found by the kana-marker scan).
endhook: LDA $03
         CMP #FIRST
         BCC endkeep
         LDY $03DA
         DEY
         LDA ($18),Y          ; byte before {END}
         CMP #$FB
         BNE endkeep
         LDA #$02             ; original font banks 2/3
         JSR setbanks
endkeep: LDA $03D7
         RTS
; ---- D-11 text speed: 4 frames per byte (was 8). A button: while typing, the rest of the
; page is drawn at once in blocks of up to 12 cells (one PPU-queue entry per frame, the NMI
; drains one entry per frame); while waiting at {WAIT}, the wait ends.
; $03D7 bit $10 = "fast" (free bit: engine uses $80/$40/$20/$01, controllers test bit 6).
; $0100-$0119 = block buffer [w][2][top x w][bottom x w] (never written after reset; checked).
abtn:    LDA $F9               ; new presses, A = bit 7
         BPL abdone
         LDA $03D7
         AND #$20
         BEQ abtype
         LDA #$01              ; waiting: let $8015 count it out this frame
         STA $03DC
         BNE abdone
abtype:  LDA $03D7
         ORA #$10
         STA $03D7
abdone:  LDA $03D7
         RTS
tick:    INC $B0
         LDA $03D7
         AND #$10
         BNE fast
         LDA $B0
         AND #$03
         BNE tdone
         JSR $8053
         JSR $8066
tdone:   RTS
fast:    JSR $8053             ; $18/$19 = string, $03DF = next byte
         LDA $03DF
         CMP #$F9
         BCC fglyph
         CMP #$FD
         BNE fctl
         LDA #$1A              ; {BR}: column 26, same frame
         STA $03DB
         INC $03DA
         JMP fast
fctl:    CMP #$FC              ; {WAIT}/{END} end the fast mode
         BCC fkeep
         LDA $03D7
         AND #$EF
         STA $03D7
fkeep:   JSR $8066
         RTS
fglyph:  LDA $30               ; reuse the buffer only after the NMI consumed it
         BNE fdone
         LDA $03DB
         CMP #$1A
         BCC fl1
         LDA #$34
         BNE flim
fl1:     LDA #$1A
flim:    SEC
         SBC $03DB             ; cells left on this line
         CMP #$0C              ; 12 cells: buffer ends at $0119 ($011A-$011F = D-17)
         BCC fl2
         LDA #$0C
fl2:     STA $0100
         LDX #$00
         LDY $03DA
floop:   LDA ($18),Y
         CMP #$F9
         BCS fend
         STA $0102,X           ; top row
         INY
         INX
         CPX $0100
         BCC floop
fend:    STX $0100             ; width
         LDA #$02
         STA $0101             ; height
         LDY #$00
fb:      LDA $0102,Y           ; bottom row = top + $40 ($BF -> $FF blank)
         CLC
         ADC #$40
         STA $0102,X
         INX
         INY
         CPY $0100
         BCC fb
         LDA $03DB             ; PPU address = $2303 + col (+38 on line 2, $2343)
         CMP #$1A
         BCC fp1
         ADC #$25
fp1:     CLC
         ADC #$03
         STA $18
         LDA #$23
         ADC #$00
         STA $19
         LDA #$00
         LDY #$01
         JSR $E6B0
         BCS fdone             ; queue full: try again next frame
         LDA $03DB
         CLC
         ADC $0100
         STA $03DB
         LDA $03DA
         CLC
         ADC $0100
         STA $03DA
fdone:   RTS
; ---- {PAGE} clear: 4 rows (glyph rows 22-25), source $CD01 = [$A0][1][$FF] ----
cleartbl: .db $06
         .db $01,$CD,$C0,$22
         .db $01,$CD,$E0,$22
         .db $01,$CD,$00,$23
         .db $01,$CD,$20,$23
         .db $01,$CD,$40,$23
         .db $01,$CD,$60,$23
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
            check_layout(sid, e["ko"].replace("{SPLIT}", "{WAIT}{PAGE}"))
            ctl = lambda t: re.findall(r"\{(?:WAIT|PAGE|END)\}", t)
            # D-12: {SPLIT} (speaker change) adds a page inside a source page; line breaks ({BR})
            # are free (D-21) - only the source's {WAIT}/{PAGE}/{END} sequence must be kept
            if ctl(e["ko"].replace("{SPLIT}", "")) != ctl(decode(bytes(src[i]))):
                raise SystemExit(f"{sid}: control token sequence differs from source")
            ko[i] = e["ko"].replace("{SPLIT}", "{WAIT}{PAGE}")

    # --- speaker tags (D-13): one entry per page that holds text, None = no tag
    speakers = load_script().get("speakers", {})
    name_of = {}
    for i in sorted(ko):
        sid = f"S{i:02d}"
        text_pages = [pi for pi, pg in enumerate(ko[i].split("{PAGE}"))
                      if re.sub(r"\{[^}]+\}", "", pg).strip()]
        names = speakers.get(sid, [None] * len(text_pages))
        if len(names) != len(text_pages):
            raise SystemExit(f"{sid}: {len(names)} speakers for {len(text_pages)} text pages")
        for pi, nm in zip(text_pages, names):
            if nm:
                tag = "[" + nm + "]"
                if len(tag) > LINE_CELLS:
                    raise SystemExit(f"{sid}: speaker tag too long")
                name_of[(i, pi)] = tag

    # --- pages in script order, glyph sets
    page_chars, page_ref = [], []
    for i in sorted(ko):
        for pi, page in enumerate(ko[i].split("{PAGE}")):
            chars = [t for t in tokens(page) if not t.startswith("{") and t != " "]
            chars += [c for c in name_of.get((i, pi), "") if c != " "]
            page_chars.append(chars); page_ref.append((i, pi))
    assign, sets = pack_sets(page_chars)
    set_of = dict(zip(page_ref, assign))

    # --- menu strings: own set appended after the dialogue sets
    menu = load_script().get("menu", {})
    m = mprg = None
    menu_chars = []
    for mid, (cpu, kind, n) in MENU_SRC.items():
        e = menu[mid]
        a = M_BANK_FILE + cpu - BANK_CPU
        raw = bytes(p[a:a + n])
        if hashlib.sha1(raw).hexdigest() != e["src_sha1"]:
            raise SystemExit(f"{mid}: source hash mismatch")
        if len(tokens(e["ko"])) > MENU_CELLS:
            raise SystemExit(f"{mid}: {len(tokens(e['ko']))} cells (max {MENU_CELLS})")
        menu_chars += [t for t in tokens(e["ko"]) if t != " "]
    menu_set = list(dict.fromkeys(menu_chars))
    if len(menu_set) > SET_CAPACITY:
        raise SystemExit("menu glyphs exceed one set")


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
            if (i, pi) in name_of:
                tag = name_of[(i, pi)]
                out += bytes([0xF9, len(tag)] + [BLANK_CODE if c == " " else 0x80 + sets[cur].index(c) for c in tag])
            for t in tokens(body):
                if t in CTRL:
                    out.append(CTRL[t])
                elif t == " ":
                    out.append(BLANK_CODE)
                else:
                    out.append(0x80 + sets[cur].index(t))
        blobs.append(bytes(out))

    # --- place strings
    # Untranslated entries stay at their original address (unchanged bytes never enter the
    # patch, so no source text is distributed). Translated entries go to the spill area.
    # When everything is translated, the whole script is repacked into the original region
    # first, then the spill area.
    ptrs = [0] * PTR_COUNT
    t = cpu2file(PTR_TABLE)
    orig_ptrs = [p[t + 2 * k] | p[t + 2 * k + 1] << 8 for k in range(PTR_COUNT)]
    if len(ko) == PTR_COUNT:
        regions = [[TEXT_START, TEXT_END], [SPILL_START, SPILL_END]]
        a0, a1 = cpu2file(TEXT_START), cpu2file(TEXT_END)
        p[a0:a1] = b"\xff" * (a1 - a0)
        order = range(PTR_COUNT)
    else:
        regions = [[SPILL_START, SPILL_END]]
        order = sorted(ko)
        for k in range(PTR_COUNT):
            ptrs[k] = orig_ptrs[k]
    r = 0
    for k in order:
        b = blobs[k]
        while regions[r][0] + len(b) > regions[r][1]:
            r += 1
            if r >= len(regions):
                raise SystemExit("script does not fit in bank 10")
        ptrs[k] = regions[r][0]
        a = cpu2file(regions[r][0]); p[a:a + len(b)] = b; regions[r][0] += len(b)
    used = {"spill": regions[-1][0] - SPILL_START}
    for k, v in enumerate(ptrs):
        p[t + 2 * k] = v & 0xFF; p[t + 2 * k + 1] = v >> 8

    # --- menu: set index, strings in place, block + hooks in the fixed bank
    sets.append(menu_set)
    if len(sets) > MAX_SETS:
        raise SystemExit("too many font sets")
    menu_bank = FIRST_SET_BANK + 2 * (len(sets) - 1)
    enc = lambda t: BLANK_CODE if t == " " else 0x80 + menu_set.index(t)
    for mid in ("M0", "M2"):
        cpu, kind, n = MENU_SRC[mid]
        b = bytes(enc(t) for t in tokens(menu[mid]["ko"])) + b"\xfe"
        if len(b) > n:
            raise SystemExit(f"{mid}: {len(b)} bytes, original space {n}")
        a = M_BANK_FILE + cpu - BANK_CPU
        p[a:a + n] = b + b"\xff" * (n - len(b))
    m1 = [enc(t) for t in tokens(menu["M1"]["ko"])]
    block = bytes([len(m1), 2] + m1 + [(c + 0x40) & 0xFF if c != BLANK_CODE else 0xFF for c in m1])
    a = M_BANK_FILE + MENU_SRC["M1"][0] - BANK_CPU
    p[a:a + MENU_SRC["M1"][2]] = b"\xff" * MENU_SRC["M1"][2]       # old block no longer referenced
    msrc = MENU_HOOKS.replace("MENUBANK", "$%02X" % menu_bank).replace(
        "BLOCK", ",".join("$%02X" % x for x in block))
    mcode, mlabels = assemble(msrc, FIXED_FREE[0])
    if FIXED_FREE[0] + len(mcode) > FIXED_FREE[1]:
        raise SystemExit("menu hooks do not fit in the fixed bank")
    orig_p = prg(rom)
    fa = FIXED_FILE + FIXED_FREE[0] - FIXED_CPU
    if any(x != 0xFF for x in orig_p[fa:fa + len(mcode)]):
        raise SystemExit("fixed-bank free area is not $FF")
    for cpu, exp in MENU_EXPECT.items():
        a = M_BANK_FILE + cpu - BANK_CPU
        if orig_p[a:a + len(exp)] != exp:
            raise SystemExit(f"unexpected menu bytes at ${cpu:04X}")
    if orig_p[MENU_CALL_FILE:MENU_CALL_FILE + 3] != MENU_CALL_EXPECT:
        raise SystemExit("unexpected bytes at bank 14 $CA66")
    p[fa:fa + len(mcode)] = mcode
    mj = lambda lab: bytes([0x20, mlabels[lab] & 0xFF, mlabels[lab] >> 8])
    a = M_BANK_FILE + 0x8320 - BANK_CPU; p[a:a + 8] = mj("menuchar") + b"\xea" * 5
    a = M_BANK_FILE + 0x81CA - BANK_CPU
    p[a:a + 4] = bytes([0xA9, mlabels["menublock"] & 0xFF, 0xA0, mlabels["menublock"] >> 8])
    p[MENU_CALL_FILE:MENU_CALL_FILE + 3] = mj("menuwrap")
    for off, exp in HUD_SITES.items():
        if orig_p[off:off + len(exp)] != exp:
            raise SystemExit(f"unexpected HUD bytes at file ${off:05X}")
    h1, h2 = mlabels["hudset1"], mlabels["hudset2"]
    p[0x1C06A:0x1C06D] = bytes([0x4C, h1 & 0xFF, h1 >> 8])                 # JMP hudset1
    p[0x1C216:0x1C21C] = bytes([0x20, h2 & 0xFF, h2 >> 8, 0x60, 0xEA, 0xEA])  # JSR hudset2 / RTS

    # --- title menu and select screens (tools/menus.py, D-14/D-15)
    import menus
    import difficulty
    menu_report = menus.apply(p, orig_p, FIXED_FREE[0] + len(mcode), FIXED_FREE[1], 0xBFFF, 0x9E00)
    diff_report = difficulty.apply(p, orig_p, menu_report["fixed_next"], FIXED_FREE[1])
    # D-20: ending start (bank 3 $B86F) queued the princess palette before the picture CHR bank
    # ($00 = $74) reached the shadow registers, so one frame showed the font tiles. Set the bank and
    # copy it ($CD04) first, then start the palette fade. Code in bank 3's $FF tail at $BF96.
    if orig_p[0x786F:0x7878] != bytes.fromhex("A97820BD80A9748500") or orig_p[0x7F96:0x7FA2] != b"\xff" * 12:
        raise SystemExit("ending palette fix: unexpected source bytes")
    p[0x7F96:0x7FA2] = bytes.fromhex("A97485002004CDA9784CBD80")   # LDA #$74/STA $00/JSR $CD04/LDA #$78/JMP $80BD
    p[0x786F:0x7878] = bytes.fromhex("2096BF") + b"\xea" * 6          # JSR $BF96 / NOP x6

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
    put(0x80E8, bytes.fromhex("03234323"))   # D-13: text lines move to rows 24 and 26 (name on 22)
    put(0x800E, jsr("abtn"))
    put(0x8022, bytes([0x4C, labels["tick"] & 0xFF, labels["tick"] >> 8]))
    put(0x8093, jsr("newchar") + b"\xea")
    put(0x80A9, jsr("endhook"))
    put(0x80CD, bytes([labels["cleartbl"] & 0xFF]))
    put(0x80D1, bytes([labels["cleartbl"] >> 8]))
    put(0x80BD, bytes([WAIT_FRAMES]))          # D-18: wait after a page 128 -> 60 frames (~1 s)

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
    # --- original kana tiles ($80-$F7 of CHR banks 2/3) -- D-06: removed in the product.
    #     LOK_KANA=marker paints a detection pattern instead (verification builds only).
    kana_mode = os.environ.get("LOK_KANA", "wipe")
    chr_old = bytearray(chr_old)
    marker = bytes([0xF0, 0x88, 0x84, 0x82, 0x41, 0x21, 0x11, 0x0F]) * 2   # colour 3
    for k in range(0x78):
        a = 0x800 + 16 * k
        chr_old[a:a + 16] = marker if kana_mode == "marker" else bytes(16)
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
        "distribution": ("NOT FOR DISTRIBUTION (development input policy)" if nontr else "candidate")
                        if os.environ.get("LOK_KANA", "wipe") == "wipe" else "VERIFICATION BUILD (kana marker)",
        "kana_tiles": os.environ.get("LOK_KANA", "wipe"),
        "font_sets": len(sets),
        "glyphs_per_set": [len(s) for s in sets],
        "text_bytes": used,
        "hook_bytes": len(code),
        "menu_hook_bytes": len(mcode),
        "menus": menu_report,
        "difficulty": diff_report,
        "menu_set": len(sets) - 1,
        "hook_labels": {k: "$%04X" % v for k, v in labels.items()},
    }
    json.dump(report, open(out_path + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
