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
import endcard  # noqa: E402

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
MAX_SETS = 63                                   # last pair ($FE/$FF) = title bank copy (D-23)

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

# D-28 (bank 11 at $A200, mapped with the text engine's bank 10): staff roll S77 ($4D) pace
STAFF_SRC = """
staff:   JSR UDEMO             ; D-29: story cut-scenes unlock their DEMO entry
         LDA $03D6
         CMP #$4D
         BNE st9
         LDA $03D7
         AND #$60              ; waiting / done?
         BNE stw
         LDA $03D7             ; typing: whole page at once (fast mode, D-11)
         ORA #$10
         STA $03D7
         RTS
stw:     AND #$20
         BEQ st9
         LDA $03DC             ; waiting: at most 40 frames
         CMP #$29
         BCC st9
         LDA #$28
         STA $03DC
st9:     RTS
"""
# D-35 {INSTANT} = $F7 at a page start: the page is drawn at once (fast mode), so a silent
# "……" line does not keep the speaker's mouth animation running while it types.
INST_SRC = """
inst:    INC $03DA
         LDA $03D7
         ORA #$10
         STA $03D7
         PLA                   ; leave the tick without printing (like {NAME})
         PLA
         RTS
"""

# D-28 (bank 3 $BFA2, ending main loop): replaces the fixed-bank endchk at $B82C
ENDCHK_SRC = """
endchk:  JSR $CCF8
         LDA $F9
         AND #$90              ; A or START?
         BEQ e9
         LDX #$0F              ; story: A/START once the end card is up -> Cutie (D-37)
         LDA $F6
         AND #$20
         BEQ ecard
         LDX #$30              ; theater (DEMO 11): START at any time, A on the card -> DEMO SELECT
         LDA $F9
         AND #$10
         BNE fade
ecard:   LDA $03D6
         CMP #$4D
         BNE e9
         BIT $03D7             ; bit 6 = finished
         BVC e9
         CPX #$30
         BEQ fade
         LDY #$09              ; D-37: fade out, silence, clear, Cutie's picture queued, S78
         JMP FAR               ; selected but not running yet (bank 11 r_post)
fadeq:   LDA $0103             ; D-32 (from dret): no fade when passing through the intro on the
         CMP #$5A              ;       way back from a select screen ($0103 = $5A only then)
         BNE fade
         TXA
         JMP $E073
fade:    TXA                   ; target mode: fade out, then $E073 (bank 11 far 8, D-37)
         LDY #$08
         JMP FAR
; ---- S78 running (ending step 18 at $BBEE, STEP18_SRC, comes here) ----
poststep: BIT $03D7
         BVS pdone
         BMI prun
         LDA $055B             ; picture still being drawn
         BNE e9
         LDY #$0A              ; fade in, then her lines start (bank 11 r_fin)
         JMP FAR
prun:    LDX #$00              ; Cutie's mouth, as the opening's S11 page
         JMP $A2C1
pdone:   LDX #$0F              ; S78 done: fade out -> opening
         BNE fade
e9:      RTS
"""

# ending step 18 ($BBEE-$BC00, 19 bytes): S77 = staff roll + card (D-28: no $F6 bit 5 check),
# in story mode S78 after it (D-37, started by endchk)
STEP18_SRC = """
         LDA $03D6
         CMP #POSTSTR
         BNE s77
         JMP POSTSTEP
s77:     CMP #$4D
         BEQ $BB85             ; an RTS (end of step 15)
         LDA #$4D
         JMP $9C5B
"""

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
CTRL = {"{PAGE}": 0xFB, "{WAIT}": 0xFC, "{BR}": 0xFD, "{END}": 0xFE, "{INSTANT}": 0xF7}   # F7: D-35

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
         CMP #$F8
         BEQ raw21
         CMP #$F7
         BNE pr9
         JMP $A2E0             ; D-35 {INSTANT} (bank 11, STAFF_SRC inst)
pr9:     RTS
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
nadv:    LDA $03DA
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
; D-22 {THEEND} = $F8 n t1..tn: one row of tiles at PPU $22A3 (row 21, below the picture
; split): top halves of end-card glyph cells.
raw21:   LDA $30
         BNE nexit
         LDY $03DA
         INY
         LDA ($18),Y
         STA $0100            ; width n
         LDA #$01
         STA $0101
         LDX #$00
rl:      INY
         LDA ($18),Y
         STA $0102,X
         INX
         CPX $0100
         BCC rl
         LDA #$A3
         STA $18
         LDA #$22
         STA $19
         LDA #$00
         LDY #$01
         JSR $E6B0
         BCS nexit
         JMP nadv
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
abtn:    JSR $A200             ; D-28 staff roll pace (bank 11, tools/build.py STAFF_SRC)
         LDA $F9               ; new presses, A = bit 7
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
         CMP #$F7
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
         CMP #$F7
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
    d = json.load(open(path, encoding="utf-8"))
    # D-22: {ENDCARD0..2} = the three rows of the composed end card (tools/endcard.py)
    rows = endcard.rows()
    if rows:
        def ex(t):
            for k in range(3):
                t = t.replace("{ENDCARD%d}" % k, rows[k])
            return t
        for e in d["entries"].values():
            if e.get("ko"):
                e["ko"] = ex(e["ko"])
        d["speakers"] = {k: [ex(n) if n else n for n in v] for k, v in d["speakers"].items()}
    return d


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
    endcard.build(bytes(rom[HEADER + PRG_SIZE:]))   # D-22 (needs the original English tiles)
    out_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "build", "lok_ko_dev.nes")
    p = bytearray(prg(rom))
    src = source_entries(p)
    script = load_script()["entries"]

    # --- verify translation baseline and layout
    ko = {}
    for sid, e in script.items():
        i = int(sid[1:])
        if e.get("extra"):              # D-37: new string after the source ones (no source text)
            if i < PTR_COUNT:
                raise SystemExit(f"{sid}: extra entries must come after S{PTR_COUNT - 1:02d}")
            check_layout(sid, e["ko"])
            # D-38: "orig_font" = Latin letters/digits in the game's own English tiles
            ko[i] = endcard.to_eng(e["ko"]) if e.get("orig_font") else e["ko"]
            continue
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
                # D-22: a name starting with "=" is a raw line (no brackets), e.g. a centred caption
                tag = nm[1:] if nm.startswith("=") else "[" + nm + "]"
                if len(tag) > LINE_CELLS:
                    raise SystemExit(f"{sid}: speaker tag too long")
                name_of[(i, pi)] = tag

    # --- pages in script order, glyph sets
    page_chars, page_ref = [], []
    for i in sorted(ko):
        for pi, page in enumerate(ko[i].split("{PAGE}")):
            chars = [t for t in tokens(page) if not t.startswith("{") and t != " "]
            if "{THEEND}" in page:
                chars += [c for c in endcard.theend() if c != " "]
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


    n_str = max(ko) + 1                 # D-37: extra strings extend the pointer table
    if sorted(k for k in ko if k >= PTR_COUNT) != list(range(PTR_COUNT, n_str)):
        raise SystemExit("extra strings must be numbered without gaps")
    blobs = []
    for i in range(n_str):
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
                if t == "{THEEND}":
                    row = endcard.theend()
                    out += bytes([0xF8, len(row)] + [BLANK_CODE if c == " " else 0x80 + sets[cur].index(c) for c in row])
                elif t in CTRL:
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
    ptrs = [0] * n_str
    t = cpu2file(PTR_TABLE)
    orig_ptrs = [p[t + 2 * k] | p[t + 2 * k + 1] << 8 for k in range(PTR_COUNT)]
    if all(k in ko for k in range(PTR_COUNT)):
        # the table grows into the old start of string 0 (repacked anyway)
        regions = [[TEXT_START + 2 * (n_str - PTR_COUNT), TEXT_END], [SPILL_START, SPILL_END]]
        a0, a1 = cpu2file(TEXT_START), cpu2file(TEXT_END)
        p[a0:a1] = b"\xff" * (a1 - a0)
        order = range(n_str)
    else:
        if n_str > PTR_COUNT:
            raise SystemExit("extra strings need the full translation (table grows into string 0)")
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
    import unlock
    # D-29 unlocks: bank 11 $A300 (labels used by the select screens, r_frame and the staff hook)
    ucode, ul = unlock.build(menus.STAGE_ROUND, (5, 19), (7, 19))
    if orig_p[unlock.FILE:unlock.FILE + len(ucode)] != b"\xff" * len(ucode):
        raise SystemExit("unlock: bank 11 area not free")
    p[unlock.FILE:unlock.FILE + len(ucode)] = ucode
    menus.UNLOCK = ul
    import post
    post.set_palette(orig_p)
    _, el0 = assemble(ENDCHK_SRC.replace("FAR", "$E000").replace("POSTSTR", "$%02X" % post.STRING), 0xBFA2)
    menus.FADE = el0["fadeq"]
    difficulty.UNLOCK = ul
    menu_report = menus.apply(p, orig_p, FIXED_FREE[0] + len(mcode), FIXED_FREE[1], 0xBFFF, 0x9E00)
    diff_report = difficulty.apply(p, orig_p, menu_report["fixed_next"], FIXED_FREE[1])
    # D-28: story-mode ending = S76 + staff roll S77 + end card, no leaving before the card;
    # the staff roll pages are drawn at once and wait 40 frames; on the card A/START fades out
    # to the opening. Theater (DEMO 11) keeps START = back to DEMO SELECT at any time.
    if orig_p[0x7BEE:0x7BF4] != bytes.fromhex("A5F62920F00C") or orig_p[0x7FA2:0x8000] != b"\xff" * 0x5E \
            or orig_p[0x16200:0x16240] != b"\xff" * 0x40:
        raise SystemExit("ending/staff roll: unexpected source bytes")
    if orig_p[0x7BF4:0x7C01] != bytes.fromhex("ADD603C94DF005A94D4C5B9C60"):
        raise SystemExit("ending step 18: unexpected source bytes")
    scode, _ = assemble(STAFF_SRC.replace("UDEMO", "$%04X" % ul["udemo"]), 0xA200)
    if 0xA200 + len(scode) > unlock.ORG:
        raise SystemExit("staff hook too large")
    p[0x16200:0x16200 + len(scode)] = scode
    icode, _ = assemble(INST_SRC, 0xA2E0)
    if 0xA200 + len(scode) > 0xA2E0 or orig_p[0x162E0:0x162E0 + len(icode)] != b"\xff" * len(icode):
        raise SystemExit("inst: bank 11 $A2E0 not free")
    p[0x162E0:0x162E0 + len(icode)] = icode
    ecode, el = assemble(ENDCHK_SRC.replace("FAR", "$%04X" % diff_report["farq"])
                         .replace("POSTSTR", "$%02X" % post.STRING), 0xBFA2)
    # $BBEE (step 18): staff roll also without $F6 bit 5 (D-28), S78 after it (D-37)
    s18, _ = assemble(STEP18_SRC.replace("POSTSTR", "$%02X" % post.STRING)
                      .replace("POSTSTEP", "$%04X" % el["poststep"]), 0xBBEE)
    if len(s18) > 0x13 or orig_p[0x7B85] != 0x60:
        raise SystemExit("ending step 18 does not fit")
    p[0x7BEE:0x7BEE + len(s18)] = s18
    if 0xBFA2 + len(ecode) > 0xC000:
        raise SystemExit("ending: endchk too large")
    p[0x7FA2:0x7FA2 + len(ecode)] = ecode
    # D-32: every cut-scene ends with a fade-out. DEMO 3-10 (bank 3) end with
    # "LDA $F6 / AND #$20 / BEQ +2 / LDX #$30 / TXA / JMP $E073" -> TXA/JMP becomes JMP fade
    # (fade does TXA itself); DEMO 1/2 go through dret (menus.py).
    for off in (0x658C, 0x682B, 0x6B1E, 0x6C95, 0x7057, 0x71FE, 0x7359, 0x76A3):
        if orig_p[off - 7:off + 4] != bytes.fromhex("A5F62920F002A2308A4C73E0")[1:] and \
                orig_p[off - 8:off + 4] != bytes.fromhex("A5F62920F002A2308A4C73E0"):
            raise SystemExit("cut-scene end at file $%05X: unexpected bytes" % off)
        p[off:off + 3] = bytes([0x4C, el["fade"] & 0xFF, el["fade"] >> 8])
    # D-33: every cut-scene picture set-up "LDA #pal / JSR $80BD / LDA #bank / STA $00" had the
    # same race as D-20 (palette uploaded one NMI before the picture's CHR bank): DEMO 8/10
    # showed a frame of font tiles. Rewritten as "LDA #bank / STA $00 / LDA #pal / JSR picfix",
    # picfix (bank 14 tail $DFF7): PHA / JSR $CD04 / PLA / JMP $80BD. What follows each site
    # never uses A (checked: LDA / INC / CLC).
    pf = 0xDFF7
    if orig_p[0x1DFF7:0x1E000] != b"\xff" * 9:
        raise SystemExit("picfix: bank 14 tail not free")
    p[0x1DFF7:0x1DFFF] = bytes.fromhex("482004CD684CBD80")
    nfix = 0
    for off in range(0x4000, 0x8000 - 9):
        o = orig_p[off:off + 9]
        if o[0] == 0xA9 and o[2:5] == b"\x20\xBD\x80" and o[5] == 0xA9 and o[7:9] == b"\x85\x00" \
                and off != 0x786F:
            nxt = orig_p[off + 9]
            if nxt not in (0xA9, 0xEE, 0x18, 0xA5, 0xAD):
                raise SystemExit("picfix: site $%05X followed by %02X" % (off, nxt))
            if orig_p[off + 9:off + 11] == b"\xa9\x0a" and orig_p[off + 11:off + 13] == b"\x85\x01":
                # QA 2026-11-18: Cutie's picture also sets $01 ($0A) right after; set it before
                # picfix too, or its lower half showed font tiles for a frame (DEMO 2, 9 sites)
                if orig_p[off + 13] not in (0xA9, 0xEE, 0x18, 0xA5, 0xAD):
                    raise SystemExit("picfix: site $%05X followed by %02X" % (off, orig_p[off + 13]))
                p[off:off + 13] = bytes([0xA9, o[6], 0x85, 0x00, 0xA9, 0x0A, 0x85, 0x01,
                                         0xA9, o[1], 0x20, pf & 0xFF, pf >> 8])
                nfix += 1
                continue
            p[off:off + 9] = bytes([0xA9, o[6], 0x85, 0x00, 0xA9, o[1], 0x20, pf & 0xFF, pf >> 8])
            nfix += 1
    # QA 2026-11-18: two sites already set the bank first ("LDA #bank / STA $00 / LDA #pal /
    # JSR $80BD") but the picture loader ($819E) waits a frame before the loop's $CD04, so the
    # new palette met the old bank for a frame (DEMO 5 princess; also in the original game).
    for off in (0x623E, 0x6BA1):
        o = orig_p[off:off + 9]
        if o[0] != 0xA9 or o[2:5] != b"\x85\x00\xa9" or o[6:9] != b"\x20\xbd\x80":
            raise SystemExit("picfix: bank-first site $%05X: unexpected bytes" % off)
        p[off + 7:off + 9] = bytes([pf & 0xFF, pf >> 8])
        nfix += 1
    # D-34: the text-window IRQ (scanline ~163, inside row 20) switched the $0800/$0C00 banks
    # low nibble first: for a moment the bank was (new low | old high) = a picture bank whose
    # tile $FF is not blank, and the right end of that scanline showed a coloured streak.
    # High nibble first: the in-between bank is (new high | old low) = a Korean font bank, where
    # $BF/$FF are the blank glyph.
    irq = bytes.fromhex("AD54018D00B0AD55018D01B0AD56018D02B0AD57018D03B0")
    if orig_p[0x1E2DF:0x1E2F7] != irq:
        raise SystemExit("IRQ bank order: unexpected bytes")
    p[0x1E2DF:0x1E2F7] = irq[6:12] + irq[0:6] + irq[18:24] + irq[12:18]
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
    # --- D-23: banks 0/1 (title, below the split) copied to $FE/$FF with "[" "]" in tiles $CC/$CD
    tb = (menus.TITLE_BANKS - FIRST_SET_BANK) * 0x400
    new[tb:tb + 0x800] = chr_old[0:0x800]
    for ch, t in menus.BRACKET_TILES.items():
        a = tb + 16 * (t - 0x80)          # tile $80-$FF of the $0800 window
        new[a:a + 16] = endcard.bracket_tile(ch == "[")
    # --- original kana tiles ($80-$F7 of CHR banks 2/3) -- D-06: removed in the product.
    #     LOK_KANA=marker paints a detection pattern instead (verification builds only).
    kana_mode = os.environ.get("LOK_KANA", "wipe")
    chr_old = bytearray(chr_old)
    marker = bytes([0xF0, 0x88, 0x84, 0x82, 0x41, 0x21, 0x11, 0x0F]) * 2   # colour 3
    for k in range(0x78):
        a = 0x800 + 16 * k
        chr_old[a:a + 16] = marker if kana_mode == "marker" else bytes(16)
    header = bytearray(rom[:HEADER]); header[5] = 32
    header[6] |= 0x02                          # D-29: battery-backed PRG RAM (unlock save)
    out = bytes(header) + bytes(p) + chr_old + bytes(new)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    open(out_path, "wb").write(out)
    nontr = PTR_COUNT - len([k for k in ko if k < PTR_COUNT])
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
