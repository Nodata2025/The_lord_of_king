"""Title menu and the original select screens (D-14, D-15).

D-14: START on the title opens GAME START / STAGE SELECT / OMAKE MODE (OMAKE: SOUND TEST /
      DEMO SELECT). The original hidden-command check is no longer called.
D-15: on START everything below the logo is cleared; A/START = execute, B/SELECT = back;
      STAGE SELECT and DEMO SELECT move with the D-pad and list every entry (STAGE 1-1..6-2,
      DEMO 1..11); SOUND TEST gets a row cursor and can be left; leaving a select screen
      reopens the menu at the item it came from.

All code runs in banks that the original screens map: title / SOUND TEST in bank 12 at $8000
with bank 13 at $A000; STAGE / DEMO SELECT in bank 10 at $8000.
"""
from asm6502 import assemble

FONT = {**{str(d): d for d in range(10)}, **{chr(65 + k): 0x0A + k for k in range(26)},
        " ": 0xFF, "-": 0x2D}


def text(s):
    return ".db %d,1,%s" % (len(s), ",".join("$%02X" % FONT[c] for c in s))


def row(s, cells=18):
    return text(("   " + s).ljust(cells)[:cells])


MAGIC = "$A5"          # $0102 = $A5, $0103 = $5A: "reopen the menu", $0104 level, $0105 cursor
MAGIC2 = "$5A"

# --------------------------------------------------------------------------------------------
# bank 13 (title, SOUND TEST)
TITLE_ORG = 0xBC40
TITLE_SRC = """
; ---- title menu: called from bank 12 $8718 (was JSR $878A, the hidden-command check) ------
; RAM $0100 cursor, $0101 level (0 main, 1 omake); $0102-$0105 reopen request
tmenu:   LDA $011E             ; D-17 difficulty: 0 EASY, 1 NORMAL, 2 HARD; $011F = $011E ^ $5A
         CMP #$03
         BCS tdfix
         EOR #$5A
         CMP $011F
         BEQ tdok
tdfix:   LDA #$01              ; power-on garbage -> NORMAL
         STA $011E
         EOR #$5A
         STA $011F
tdok:    LDA #$00
         STA $011A             ; damage remainder, frame counter, extra-move flag
         STA $011B
         STA $011C
         STA $0563
         STA $0100
         STA $0101
         LDA $0102
         CMP #MAGIC
         BNE tm1
         LDA $0103
         CMP #MAGIC2
         BNE tm1
         LDA $0104
         STA $0101
         LDA $0105
         STA $0100
tm1:     LDA #$00
         STA $0102
         LDA #$11              ; sprite palette 0, colours 1-3
         STA $18
         LDA #$3F
         STA $19
         LDA #<spal
         LDY #>spal
         JSR qput
         LDX #$00              ; clear rows 16-25 (everything below the logo)
tclr0:   LDA clrlo,X
         STA $18
         LDA clrhi,X
         STA $19
         TXA
         PHA
         LDA #$01              ; $CD01 = [$A0][1][$FF]: a blank row
         LDY #$CD
         JSR qput
         PLA
         TAX
         INX
         CPX #$0A
         BCC tclr0
         JSR drawlvl
tloop:   JSR $E408
         JSR cursor
         JSR $E378
         LDA $F9
         AND #$08              ; up
         BEQ tdown
         DEC $0100
         BPL tloop
         JSR nitems
         STA $0100
         JMP tnext
tdown:   LDA $F9
         AND #$04              ; down
         BEQ tsel
         INC $0100
         JSR nitems
         CMP $0100
         BCS tloop
         LDA #$00
         STA $0100
         JMP tnext
tsel:    LDA $F9
         AND #$03              ; left/right on DIFFICULTY
         BEQ tsel0
         LDA $0101
         BNE tsel0
         LDA $0100
         CMP #$03
         BNE tsel0
         JMP tdinc             ; left/right/A/START all step EASY -> NORMAL -> HARD
tsel0:   LDA $F9
         AND #$90              ; A or START: execute
         BEQ tback
         LDA $0101
         BNE tsel1
         LDA $0100
         BEQ tgo
         CMP #$03
         BEQ tdinc
         CMP #$01
         BNE topen
         LDA #$20              ; STAGE SELECT
         STA $0563
tgo:     JMP tleave
tdinc:   INC $011E
         LDA $011E
         CMP #$03
         BCC tdset
         LDA #$00
         STA $011E
tdset:   LDA $011E
         EOR #$5A
         STA $011F
         JSR drawdif
         JMP tnext
topen:   LDA #$01
         STA $0101
         LDA #$00
         STA $0100
         JSR drawlvl
         JMP tnext
tsel1:   LDA $0100
         BNE tdemo
         LDA #$80              ; SOUND TEST
         STA $0563
         JMP tleave
tdemo:   LDA #$40              ; DEMO SELECT
         STA $0563
         JMP tleave
tback:   LDA $F9
         AND #$60              ; B or SELECT: back
         BEQ tnext
         LDA $0101
         BEQ texit
         LDA #$00
         STA $0101
         LDA #$02
         STA $0100
         JSR drawlvl
tnext:   JMP tloop
texit:   LDA #$F0              ; main menu: back to the title (redrawn from scratch)
         STA $0200
         LDA #$00
         JMP $E073
cursor:  LDX $0100
         LDA cury,X
         STA $0200
         LDA #$26
         STA $0201
         LDA #$00
         STA $0202
         LDA #$40
         STA $0203
         RTS
nitems:  LDA $0101
         BEQ ni0
         LDA #$01
         RTS
ni0:     LDA #$03
         RTS
drawlvl: LDA $0101
         BNE dlo
         LDA #<m0
         LDY #>m0
         LDX #$00
         JSR qrow
         LDA #<m1
         LDY #>m1
         LDX #$01
         JSR qrow
         LDA #<m2
         LDY #>m2
         LDX #$02
         JSR qrow
drawdif: LDX $011E
         LDA dtlo,X
         LDY dthi,X
         LDX #$03
         JMP qrow
dlo:     LDA #<o0
         LDY #>o0
         LDX #$00
         JSR qrow
         LDA #<o1
         LDY #>o1
         LDX #$01
         JSR qrow
         LDA #<bl
         LDY #>bl
         LDX #$02
         JSR qrow
         LDA #<bl
         LDY #>bl
         LDX #$03
qrow:    PHA
         LDA rowlo,X
         STA $18
         LDA rowhi,X
         STA $19
         PLA
qput:    JSR $E6B0             ; queue full: wait a frame and retry
         BCC qok
         JSR $E378
         JMP qput
qok:     RTS
tleave:  LDA #$F0
         STA $0200
         LDX #$00              ; clear the menu rows (SOUND TEST keeps this screen)
tlv:     TXA
         PHA
         LDA #<bl
         LDY #>bl
         JSR qrow
         PLA
         TAX
         INX
         CPX #$04
         BCC tlv
         RTS
; ---- D-17 lives: game start (bank 12 $8A7A) and continue (bank 12 $8CCB) -----------------
lives0:  LDA #$02
         LDY $011E
         BNE lv2
         LDA #$09              ; EASY: 9 lives
lv2:     STA $96
         RTS
govr:    LDA $011E
         CMP #$02
         BNE lives0
         LDA #$00              ; HARD: no continue, back to the opening
         STA $0102
         LDA #$0F
         JMP $E073
; ---- bank 12 $8709 (was JSR $8770, the hidden-command input recorder) --------------------
thook:   LDA $0102
         CMP #MAGIC
         BNE th9
         LDA $0103
         CMP #MAGIC2
         BNE th9
         LDA $0556             ; wait until the logo fade-in is done ($87F7 sets bit 7)
         BPL th9
         LDA $F9               ; reopen request: act as if START was pressed
         ORA #$10
         STA $F9
th9:     RTS
; ---- SOUND TEST loop (bank 12 $88BE jumps here) -------------------------------------------
sndinit: LDA #$00
         STA $0106             ; row: 0 BGM, 1 EFFECT
         LDA #$11
         STA $18
         LDA #$3F
         STA $19
         LDA #<spal
         LDY #>spal
         JSR qput
snd:     JSR $E408
         LDA $0106             ; cursor: rows 21 / 23, column 9
         BEQ sc0
         LDA #$B7
         BNE sc1
sc0:     LDA #$A7
sc1:     STA $0200
         LDA #$26
         STA $0201
         LDA #$00
         STA $0202
         LDA #$48
         STA $0203
         JSR $E378
         LDA $F9
         AND #$0C              ; up/down: choose the row
         BEQ sn1
         LDA $0106
         EOR #$01
         STA $0106
         JMP snd
sn1:     LDA $F9
         AND #$90              ; A/START: play
         BEQ sn2
         LDA $0106
         BNE sfx
         JSR $88E4             ; original "play BGM $0300"
         JMP snd
sfx:     LDX $0301             ; original "play effect $0301+1"
         INX
         STX $C1
         JMP snd
sn2:     LDA $F9
         AND #$60              ; B/SELECT: stop and go back to OMAKE MODE
         BEQ sn3
         JSR $E4EA
         JSR $E4F9
         LDA #$F0
         STA $0200
         LDA #MAGIC
         STA $0102
         LDA #MAGIC2
         STA $0103
         LDA #$01
         STA $0104
         LDA #$00
         STA $0105
         LDA #$0F              ; via the intro (see select screens)
         JMP $E073
sn3:     LDA $F9
         AND #$03              ; left/right: change the number on this row
         BEQ snx
         LDX $0106
         BNE sn4
         AND #$01              ; BGM: original routine reads up/down bits
         BEQ snl
         LDA #$08
         BNE sns
snl:     LDA #$04
sns:     STA $F9
         JSR $88FE
         JMP snd
sn4:     STA $F9
         JSR $8955
snx:     JMP snd
clrlo:   .db $00,$20,$40,$60,$80,$A0,$C0,$E0,$00,$20
clrhi:   .db $22,$22,$22,$22,$22,$22,$22,$22,$23,$23
rowlo:   .db $27,$67,$A7,$EA
rowhi:   .db $22,$22,$22,$22
cury:    .db $87,$97,$A7,$B7
dtlo:    .db <d0,<d1,<d2
dthi:    .db >d0,>d1,>d2
spal:    .db 3,1,$16,$27,$30
m0:      ROW_GAME
m1:      ROW_STAGE
m2:      ROW_OMAKE
o0:      ROW_SOUND
o1:      ROW_DEMO
bl:      ROW_BLANK
d0:      ROW_DEASY
d1:      ROW_DNORMAL
d2:      ROW_DHARD
"""

TITLE_SRC = (TITLE_SRC.replace("ROW_GAME", row("GAME START")).replace("ROW_STAGE", row("STAGE SELECT"))
             .replace("ROW_OMAKE", row("OMAKE MODE")).replace("ROW_SOUND", row("SOUND TEST"))
             .replace("ROW_DEMO", row("DEMO SELECT")).replace("ROW_BLANK", row(""))
             .replace("ROW_DEASY", text("DIFFICULTY  EASY  "))
             .replace("ROW_DNORMAL", text("DIFFICULTY  NORMAL"))
             .replace("ROW_DHARD", text("DIFFICULTY  HARD  "))
             .replace("MAGIC2", MAGIC2).replace("MAGIC", MAGIC))

# --------------------------------------------------------------------------------------------
# bank 10 (STAGE SELECT, DEMO SELECT)
SEL_ORG = 0x9A00


def _list(title, labels, col1, col2):
    """E683 list: [count] + [src lo][src hi][ppu lo][ppu hi]..., title at $20CA.
    Row-major (D-16): item k sits in row k // 2, column k % 2."""
    rows = [10, 13, 16, 19, 22, 25]
    ents, blocks = [], []
    blocks.append(("t", text(title)))
    ents.append(("t", 0x20CA))
    for k, lab in enumerate(labels):
        col = col1 if k % 2 == 0 else col2
        r = rows[k // 2]
        name = f"i{k}"
        blocks.append((name, text(lab)))
        ents.append((name, 0x2000 + 32 * r + col))
    return ents, blocks


def _emit_list(prefix, ents, blocks):
    out = [f"{prefix}lst: .db {len(ents)}"]
    for name, ppu in ents:
        out.append(f"         .db <{prefix}{name},>{prefix}{name},${ppu & 0xFF:02X},${ppu >> 8:02X}")
    for name, b in blocks:
        out.append(f"{prefix}{name}: {b}")
    return "\n".join(out)


STAGES = ["STAGE 1-1", "STAGE 2-1", "STAGE 2-2", "STAGE 3-1", "STAGE 3-2", "STAGE 4-1",
          "STAGE 4-2", "STAGE 5-1", "STAGE 5-2", "STAGE 6-1", "STAGE 6-2"]
STAGE_ROUND = [0x00, 0x02, 0x03, 0x05, 0x06, 0x08, 0x09, 0x0B, 0x0C, 0x0D, 0x0F]   # $F3
DEMOS = [f"DEMO {n}" for n in range(1, 12)]
DEMO_MODE = [0x0F, 0x12, 0x15, 0x18, 0x1B, 0x1E, 0x21, 0x24, 0x27, 0x2A, 0x2D]

SEL_SRC = """
; $03E4 index 0-10 (row-major: row = index / 2, column = index % 2),
; $03E5 left-column cursor x, $03E6 0 stage / 1 demo
sloopS:  LDA #$20
         STA $03E5
         LDA #$00
         STA $03E6
         JMP sel
dloopD:  LDA #$30
         STA $03E5
         LDA #$01
         STA $03E6
sel:     JSR scur
         JSR $E3E8
         JSR $E378
         LDA $F9
         AND #$08              ; up: one row = two items
         BEQ s1
         LDA $03E4
         CMP #$02
         BCC u9
         SBC #$02
         STA $03E4
u9:      JMP sel
s1:      LDA $F9
         AND #$04              ; down
         BEQ s2
         LDA $03E4
         CLC
         ADC #$02
         CMP #$0B
         BCS d9
         STA $03E4
d9:      JMP sel
s2:      LDA $F9
         AND #$02              ; left
         BEQ s3
         LDA $03E4
         AND #$01
         BEQ l9
         DEC $03E4
l9:      JMP sel
s3:      LDA $F9
         AND #$01              ; right
         BEQ s4
         LDA $03E4
         AND #$01
         BNE r9
         LDA $03E4
         CMP #$0A
         BCS r9
         INC $03E4
r9:      JMP sel
s4:      LDA $F9
         AND #$90              ; A/START: execute
         BEQ s5
         LDX $03E4
         LDA $03E6
         BNE s4d
         LDA stbl,X
         STA $F3
         JMP $911E             ; original stage start (lives, mode $03)
s4d:     LDA dtbl,X
         JMP $E073
s5:      LDA $F9
         AND #$60              ; B/SELECT: back to the menu
         BEQ s9
         LDA $F6
         AND #$DF              ; leave "demo select" context
         STA $F6
         LDA #MAGIC
         STA $0102
         LDA #MAGIC2
         STA $0103
         LDA $03E6             ; stage -> main menu, demo -> OMAKE
         STA $0104
         LDA #$01
         STA $0105
         LDA #$0F              ; via the intro: it sets the title's palette and logo banks
         JMP $E073
s9:      JMP sel
scur:    LDA #$8B              ; original heart cursor object
         STA $03D6
         LDA $03E4
         AND #$01
         BNE sc2
         LDA $03E5             ; left column x
         JMP sc3
sc2:     LDA #$90              ; right column x
sc3:     STA $03DB
         LDA $03E4
         LSR A
         TAX
         LDA ytab,X
         STA $03DE
         LDA #$13
         STA $03D7
         LDA #$90
         STA $03D8
         LDA #$D6
         STA $42
         LDA #$03
         STA $43
         JMP $E9F9
slist:   LDA #<slst
         STA $18
         LDA #>slst
         STA $19
         JMP $E683
dlist:   LDA #<dlst
         STA $18
         LDA #>dlst
         STA $19
         JMP $E683
ytab:    .db $60,$78,$90,$A8,$C0,$D8
stbl:    .db STBL
dtbl:    .db DTBL
SLIST
DLIST
; ---- D-17 lives on STAGE SELECT start (bank 10 $912C) ----
slives:  LDA $011E
         BNE sl2
         LDA #$09
         STA $96
         RTS
sl2:     LDA #$02
         STA $96
         RTS
"""

_se, _sb = _list("STAGE SELECT", STAGES, 5, 19)
_de, _db = _list("DEMO SELECT", DEMOS, 7, 19)
SEL_SRC = (SEL_SRC.replace("STBL", ",".join("$%02X" % x for x in STAGE_ROUND))
           .replace("DTBL", ",".join("$%02X" % x for x in DEMO_MODE))
           .replace("SLIST", _emit_list("s", _se, _sb)).replace("DLIST", _emit_list("d", _de, _db))
           .replace("MAGIC2", MAGIC2).replace("MAGIC", MAGIC))

# DEMO 1 / DEMO 2 (opening modes $0F / $12) return to DEMO SELECT like DEMO 3-11 do
DRET_SRC = """
; intro skip check (bank 2 $9CE3, was LDA $F9 / AND #$10): a pending menu-reopen request
; counts as START, so leaving a select screen passes through the intro in one frame.
iskip:   LDA $0102
         CMP #MAGIC
         BNE isk1
         LDA $0103
         CMP #MAGIC2
         BNE isk1
         LDA #$10
         RTS
isk1:    LDA $F9
         AND #$10
         RTS
; ending main loop (bank 3 $B82C, was JSR $CCF8): START leaves the ending.
; From DEMO SELECT: any time -> DEMO SELECT. In the game the ending stops at S76 "끝" (the
; staff roll S77 only follows in DEMO 11): once S76 or S77 has finished -> the opening ($0F).
endchk:  JSR $CCF8
         LDA $F9
         AND #$10
         BEQ ec9
         LDA $F6
         AND #$20
         BNE ecth
         LDA $03D6
         CMP #$4C              ; S76
         BEQ ec1
         CMP #$4D              ; S77
         BNE ec9
ec1:     LDA $03D7
         AND #$40
         BEQ ec9
         LDA #$0F
         JMP $E073
ecth:    LDA #$30
         JMP $E073
ec9:     RTS
dret:    TAX
         LDA $F6
         AND #$20
         BEQ dr1
         LDX #$30
dr1:     TXA
         JMP $E073
"""

# (file offset, expected original bytes, kind)
SITES = {
    "title_call":  (0x18718, "208A87"),        # JSR $878A  -> JSR tmenu
    "title_rec":   (0x18709, "207087"),        # JSR $8770  -> JSR thook
    "snd_loop":    (0x188BE, "2008E4"),        # loop start -> JMP sndinit
    "demo_list":   (0x14000 + 0x0F20, "201590"),
    "demo_loop":   (0x14000 + 0x0F47, "20BF8F"),
    "stage_list":  (0x14000 + 0x10E8, "20A491"),
    "stage_loop":  (0x14000 + 0x1109, "204691"),
    "m0F_skip":    (0x4000 + 0x1CE9, "A9004C73E0"),
    "intro_start": (0x4000 + 0x1CE3, "A5F92910"),  # LDA $F9 / AND #$10 -> JSR iskip / NOP
    "m0F_end":     (0x4000 + 0x1E81, "A9004C73E0"),
    "m12_skip":    (0x6000 + 0x00A3, "A9034C73E0"),
    "m12_end":     (0x6000 + 0x02BC, "A9034C73E0"),
    "end_loop":    (0x6000 + 0x182C, "20F8CC"),        # ending loop: JSR $CCF8 -> JSR endchk
    "lives_init":  (0x18A7A, "A9028596"),       # LDA #2 / STA $96 -> JSR lives0 / NOP (D-17)
    "lives_cont":  (0x18CCB, "A9028596"),       # continue          -> JSR govr / NOP
    "lives_stage": (0x1512C, "A9028596"),       # STAGE SELECT      -> JSR slives / NOP
    "snd_slide":   (0x18894, "18A5E6690185E6A5E8690029018"[:0] + "18A5E6690185E6A5E869002901"),
}


def apply(p, orig, fixed_free_start, fixed_free_end, bank13_free_end, bank10_free_end):
    """Patch PRG image p (bytearray). Returns a report dict."""
    for name, (off, exp) in SITES.items():
        e = bytes.fromhex(exp)
        if orig[off:off + len(e)] != e:
            raise SystemExit(f"menus: unexpected bytes at {name} (file ${off:05X})")
    tcode, tl = assemble(TITLE_SRC, TITLE_ORG)
    if TITLE_ORG + len(tcode) > bank13_free_end + 1:
        raise SystemExit("menus: bank 13 code too large")
    scode, sl = assemble(SEL_SRC, SEL_ORG)
    if SEL_ORG + len(scode) > bank10_free_end:
        raise SystemExit("menus: bank 10 code too large")
    dcode, dl = assemble(DRET_SRC.replace("MAGIC2", MAGIC2).replace("MAGIC", MAGIC), fixed_free_start)
    if fixed_free_start + len(dcode) > fixed_free_end:
        raise SystemExit("menus: fixed-bank helper does not fit")
    for org, code, foff in ((TITLE_ORG, tcode, 0x1A000 + TITLE_ORG - 0xA000),
                            (SEL_ORG, scode, 0x14000 + SEL_ORG - 0x8000),
                            (fixed_free_start, dcode, 0x1E000 + fixed_free_start - 0xE000)):
        if any(x != 0xFF for x in orig[foff:foff + len(code)]):
            raise SystemExit(f"menus: free area at file ${foff:05X} is not $FF")
        p[foff:foff + len(code)] = code

    def jsr(a): return bytes([0x20, a & 0xFF, a >> 8])
    def jmp(a): return bytes([0x4C, a & 0xFF, a >> 8])
    def put(name, b):
        off = SITES[name][0]; p[off:off + len(b)] = b
    put("title_call", jsr(tl["tmenu"]))
    put("title_rec", jsr(tl["thook"]))
    put("snd_loop", jmp(tl["sndinit"]))
    put("demo_list", jsr(sl["dlist"]))
    put("demo_loop", jmp(sl["dloopD"]))
    put("stage_list", jsr(sl["slist"]))
    put("stage_loop", jmp(sl["sloopS"]))
    put("intro_start", jsr(dl["iskip"]) + b"\xea")
    put("end_loop", jsr(dl["endchk"]))
    put("lives_init", jsr(tl["lives0"]) + b"\xea")
    put("lives_cont", jsr(tl["govr"]) + b"\xea")
    put("lives_stage", jsr(sl["slives"]) + b"\xea")
    # D-16: SOUND TEST appears at once: skip the slide ($E6/$E8 end values) and go on at $88AD
    put("snd_slide", bytes.fromhex("A90085E6A90185E84CAD88") + b"\xea" * 2)
    for name in ("m0F_skip", "m0F_end", "m12_skip", "m12_end"):
        off = SITES[name][0]
        p[off + 3:off + 5] = bytes([dl["dret"] & 0xFF, dl["dret"] >> 8])   # JMP $E073 -> JMP dret
    return {"title_bytes": len(tcode), "select_bytes": len(scode), "dret_bytes": len(dcode),
            "fixed_next": fixed_free_start + len(dcode)}
