"""D-17 / D-41 difficulty modes, chosen on the title menu (menus.py).

RAM (inside $0100-$011F, never written by the game after reset; the fast-text buffer now
stops at $0119):
  $011A damage remainder   $011B frame counter 0-4   $011C "extra move" flag for this frame
  $011D far-call A in/out  $011E difficulty 0-4      $011F = $011E ^ $5A (checked on the title)

0 STORY          damage taken x0.5 (remainder carried), attack x1.5, PW gauge never drains,
                 9 lives, no knockback (a hit only starts the blinking invincibility, except
                 the hit that empties the HP).
1 EASY           damage taken x0.75 (remainder carried), no knockback; else NORMAL.
2 NORMAL         original (2 lives).
3 HARD           5 lives, no continue, damage taken x1.25 (+1 every 4 points), attack
                 a - round(a/5) (= /1.25, at least 1), boss max HP x1.5 (max HP >= 40 in the
                 $D57B table), while a boss is on screen every 5th frame objects move twice.
4 HEAVEN OR HELL 9 lives, no continue, any hit empties the player's HP, every enemy (bosses
                 too) dies at the first hit (max HP 0; the game kills when damage > max HP).

Code lives in bank 11 (all $FF in the original) and is reached through `far`: banks 10/11
are mapped through the game's own $08/$AE pair, the same way bank 14 $D030 runs bank 4
enemy code. Bodies at $A800 (DIFF_SRC), dispatcher at $A000.
"""
from asm6502 import assemble

B11_ORG, B11_FILE = 0xA000, 0x16000
UNLOCK = {}                                # set by build.py (tools/unlock.py labels)
B14_ORG, B14_END = 0xDFD3, 0xE000          # $FF-filled tail of bank 14 (fixed at $C000)

B11_SRC = """
disp:    LDA dhi,Y
         PHA
         LDA dlo,Y
         PHA
         LDA $011D
         RTS
dlo:     .db <r_dmg-1,<r_hp-1,<r_atk-1,<r_pw-1,<r_frame-1,<r_hit-1,<ucheat-1,<r_snd-1,<r_fade-1,<r_post-1,<r_fin-1,<r_lives-1,<r_hud-1,<r_clr-1,<r_spawn-1,<r_boss-1
dhi:     .db >r_dmg-1,>r_hp-1,>r_atk-1,>r_pw-1,>r_frame-1,>r_hit-1,>ucheat-1,>r_snd-1,>r_fade-1,>r_post-1,>r_fin-1,>r_lives-1,>r_hud-1,>r_clr-1,>r_spawn-1,>r_boss-1
; ---- 7: SOUND TEST sound control (D-36), A = op ----
;   0: stop everything (entering SOUND TEST)
;   1: B/SELECT: sound playing -> stop it, A=0; nothing playing -> stop, title BGM 0 again,
;      reopen request (OMAKE, SOUND TEST row), title nametable, hidden cursor, A=1
;   2: play effect $0301+1 (sound engine re-enabled first if a finished jingle turned it off)
r_snd:   CMP #$02
         BEQ rs2
         TAX
         BEQ rs0
         LDA $B6
         AND #$02
         ORA $C1
         ORA $C2
         BEQ rs1
rs0:     JSR $E4EA
         JSR $E4F9
         LDA #$00
         STA $011D
         RTS
rs1:     JSR $E4EA
         JSR $E4F9
         LDA #$00
         STA $47
         STA $0105
         STA $E6
         STA $E8
         JSR $E508
         LDA #$A5
         STA $0102
         LDA #$5A
         STA $0103
         LDA #$01
         STA $0104
         STA $011D
         LDA #$F0
         STA $0200
         RTS
rs2:     LDA $B6
         BNE rs3
         JSR $E4F9
rs3:     LDX $0301
         INX
         STX $C1
         RTS
"""

# D-41: difficulty bodies (bank 11 $A800, all $FF in the original); far indexes 0-5 and 11
DIFF_ORG, DIFF_FILE = 0xA800, 0x16800
DIFF_SRC = """
; ---- 0: damage taken (was $C52D: A = attack id) ----
r_dmg:   AND #$3F
         TAY
         LDA $C5D5,Y
         STA $011D
         LDY $011E
         BEQ dst               ; STORY  x0.5
         DEY
         BEQ dea               ; EASY   x0.75
         DEY
         BEQ dap               ; NORMAL
         DEY
         BEQ dhd               ; HARD   x1.25
         LDA #$7F              ; HEAVEN OR HELL: any hit empties the HP
         STA $011D
         BNE dap
dhd:     CLC                   ; +1 for every 4 points taken (remainder kept)
         ADC $011A
dh0:     CMP #$04
         BCC dh1
         SBC #$04
         INC $011D
         BNE dh0
dh1:     STA $011A
         JMP dap
dea:     ASL A                 ; (3 x damage + remainder) / 4, remainder kept
         ADC $011D
         ADC $011A
         PHA
         AND #$03
         STA $011A
         PLA
         LSR A
         LSR A
         STA $011D
         JMP dap
dst:     CLC                   ; half, remainder kept for the next hit
         ADC $011A
         LSR A
         STA $011D
         LDA #$00
         ROL A
         STA $011A
dap:     SEC
         LDA $91
         SBC $011D
         STA $91
         BPL dok
         LDA #$00
         STA $91
dok:     RTS
; ---- 1: enemy max HP (was $D2BC: LDA $060E,X / TAY / LDA $D57B,Y; an enemy dies when its
;      damage total reaches it) ----
r_hp:    LDA $060E,X
         TAY
         LDA $D57B,Y
         LDY $011E
         CPY #$04
         BEQ hh
         CPY #$03
         BNE hr
         CMP #$28              ; HARD: bosses (max HP >= 40) x1.5
         BCC hr
         STA $011D
         LSR A
         ADC $011D
hr:      STA $011D
         RTS
hh:      LDA #$00              ; HEAVEN OR HELL: every enemy dies in one hit (the game kills
         BEQ hr                ; when the damage total is MORE than max HP: max 0)
; ---- 2: player attack power (wraps JSR $D2F1; X = enemy, kept) ----
r_atk:   JSR $D2F1
         LDY $011E
         BEQ as
         CPY #$04              ; HEAVEN OR HELL: maximum damage on every hit (D-42)
         BNE ah
         LDA #$7F
         BNE ar
ah:      CPY #$03
         BNE ar
         STA $011D             ; HARD: a - round(a / 5) (= a / 1.25, at least 1)
         CLC
         ADC #$02
         LDY #$00
ad5:     SEC
         SBC #$05
         BCC ad6
         INY
         BCS ad5
ad6:     TYA
         EOR #$FF
         SEC
         ADC $011D
         BNE ar
         LDA #$01
         BNE ar
as:      STA $011D             ; STORY: x1.5
         LSR A
         ADC $011D
ar:      STA $011D
         RTS
; ---- 3: PW gauge spent by a swing (was $C5C3-$C5D3); STORY: never drains ----
r_pw:    LDA $011E
         BEQ pr
         LDA #$00
         STA $8D
         STA $8E
         LDX #$13
         LDA #$FF
pl:      STA $0360,X
         DEX
         BPL pl
pr:      RTS
; ---- 4: once per gameplay frame (before JSR $CFBB) ----
r_frame: LDX #$00              ; D-43 (every difficulty): the mid-boss sparks (object type $0A,
fs1:     LDA $0600,X           ;  3-1 / 6-2) never set a box size, so they collided with the
         BPL fs2               ;  default 20x46 box; give them their 8x8 picture size ($0A)
         LDA $060E,X
         CMP #$0A
         BNE fs2
         LDA #$0A
         STA $070B,X
fs2:     TXA
         CLC
         ADC #$10
         TAX
         BNE fs1
         LDA $011E             ; D-42 HEAVEN OR HELL: no PW gauge (empty, max 0, not drawn)
         CMP #$04
         BNE fh0
         LDA #$00
         STA $88
         STA $89
         STA $8D
         STA $8E
         LDA $035E             ; "PW" label or a gauge tile still in the HUD row buffer
         AND $0360             ;  (a frame where the gauge max was set before this ran):
         CMP #$FF              ;  blank label + gauge
         BEQ fh2
         LDX #$15
         LDA #$FF
fh1:     STA $035E,X
         DEX
         BPL fh1
         LDA $034D             ; redraw that row (as $C5A2)
         AND #$F0
         ORA #$40
         STA $034D
         JMP fh2
fh0:     JMP fh3
fh2:     LDX #$00              ; D-42: no bubble clusters (object types $1D-$20); their spawn flag stays
fb1:     LDA $0600,X           ;  set, so they never come back
         BPL fb2
         LDA $F3               ; D-46: 5-1 purple bridge (x 2800-3372): no ordinary enemies
         CMP #$0B              ;  (list entries 15 type $26, 22/23 $2F, 27 $30)
         BNE fb5
         LDA $060F,X
         CMP #15
         BEQ fb4
         CMP #22
         BEQ fb4
         CMP #23
         BEQ fb4
         CMP #27
         BEQ fb4
fb5:     LDA $060E,X
         CMP #$10              ; D-45: 5-1's first floor tentacle (type $10 at x 960, on the
         BNE fb3               ;  small platform right after the gap: landing = hit)
         LDA $F3
         CMP #$0B
         BNE fb2
         LDA $0605,X
         CMP #$C0
         BNE fb2
         LDA $0606,X
         CMP #$03
         BEQ fb4
         BNE fb2
fb3:     LDA $060E,X           ; $1D-$20: the bubble/grape clusters (colour per round)
         SEC
         SBC #$1D
         CMP #$04
         BCS fb2
fb4:     LDA #$00
         STA $0600,X
fb2:     TXA
         CLC
         ADC #$10
         TAX
         BNE fb1
         JSR rcol              ; re-arm spawn entries deleted off screen (flag = column | $80)
         STA $011D             ;  once the scroll column has changed
         LDX #$2F
fa1:     LDA $0576,X
         BPL fa2
         AND #$7F
         CMP $011D
         BEQ fa2
         LDA #$00
         STA $0576,X
fa2:     DEX
         BPL fa1
fh3:     JSR USTAGE             ; D-29: the round being played unlocks its STAGE entry
         LDA #$00
         STA $011C
         LDA $011E
         CMP #$03              ; HARD: while a boss is on screen, every 5th frame objects move twice
         BNE fr
         INC $011B
         LDA $011B
         CMP #$05
         BCC fr
         LDA #$00
         STA $011B
         TAX
fl:      LDA $0600,X
         BPL fn
         LDY $060E,X
         LDA $D57B,Y
         CMP #$28
         BCC fn
         INC $011C
         RTS
fn:      TXA
         CLC
         ADC #$10
         TAX
         BNE fl
fr:      RTS
; ---- 5: first frame of a hit (bank 0 $8455). STORY / EASY and still alive: no hurt motion,
;      only the blinking invincibility ($76 bit4, $7D frames) and the hit sound. ----
r_hit:   LDY $011E
         CPY #$02
         BCS hn
         LDA $91
         BEQ hn
         LDA $76
         AND #$1F
         ORA #$10
         STA $76
         LDA #$80
         STA $7D
         LDA #$0D
         STA $C1
         LDA #$01
         STA $011D
         RTS
hn:      LDA #$00
         STA $011D
         RTS
; ---- 11: lives at game start / continue / STAGE SELECT ----
r_lives: LDY $011E
         LDA ltab,Y
         STA $96
         RTS
ltab:    .db $09,$02,$02,$05,$09
; ---- 13: spawn flag of an object deleted off screen (was $F1D1: A = entry, flag = 0 ->
;      the entry spawns again when its column is at the screen edge). D-42 HEAVEN OR HELL:
;      flag = column | $80, cleared by r_frame only after the column has changed, so standing
;      at an edge no longer brings the same enemy back forever. ----
r_clr:   TAX
         LDA #$00
         LDY $011E
         CPY #$04
         BNE rc1
         JSR rcol
         ORA #$80
rc1:     STA $0576,X
         RTS
rcol:    LDA $48               ; the scroll column the spawner compares ($CE81)
         LSR A
         LDA $4A
         BCC rc2
         LDA $4E
rc2:     AND #$7F
         RTS
; ---- 14: D-44 (every difficulty) small dragons (object type $24, 3-2 etc.) could start right
;      where the player is (3-2: landing from a pillar = death on arrival). Replaces the side
;      choice of their set-up (bank 0 $9897-$98AA, X = slot, returns A = facing for $0702):
;      vertical-scroll stages ($48 odd) start them at the list's edge (x 0 -> fly right, else
;      fly left); others turn them toward the player ($D1DA). Small dragons ($21-$26): in
;      vertical stages they start at the screen edge farther from the player; elsewhere one
;      starting within 64 px of the player is moved 96 px to the player's other side. ----
r_spawn: LDX $05A6
         LDA $060E,X           ; small dragons: types $21-$26
         SEC
         SBC #$21
         CMP #$06
         BCS rs9
         LDA $48
         LSR A
         BCC rsh
         LDA $6E               ; vertical stage: start at the screen edge farther from the
         BNE rs9               ;  player (player x < 128 -> right edge 240, else left edge 0)
         LDA $6D
         BMI rs3
         LDA #$F0
         BNE rs4
rs3:     LDA #$00
rs4:     STA $0605,X
         LDA #$00
         STA $0606,X
         JMP rs9
rsh:     SEC                   ; horizontal stage: near = |player x - its x| < 64
         LDA $6D
         SBC $0605,X
         STA $011D
         LDA $6E
         SBC $0606,X
         BEQ rs1
         CMP #$FF
         BNE rs9
         LDA $011D
         CMP #$C0
         BCC rs9
         BCS rs6
rs1:     LDA $011D
         CMP #$40
         BCS rs9
         CLC                   ; it was left of (or on) the player -> player x + 96
         LDA $6D
         ADC #$60
         STA $0605,X
         LDA $6E
         ADC #$00
         STA $0606,X
         JMP rs9
rs6:     SEC                   ; it was right of the player -> player x - 96
         LDA $6D
         SBC #$60
         STA $0605,X
         LDA $6E
         SBC #$00
         STA $0606,X
rs9:     LDA $48               ; the original side choice
         LSR A
         BCC rs11
         LDA #$01
         LDY $0605,X
         BEQ rs10
         LDA #$00
rs10:    STA $011D
         RTS
rs11:    JSR $D1DA
         STA $011D
         RTS
; ---- 15: D-46 HEAVEN OR HELL, 5-1 mid-boss (beast + eagle, type $40). It wakes ($B0CE, bank 1)
;      only once the screen has locked at the end, by then ~70 px in front of the player and
;      charging at 2 px/frame. Here it may also wake once the player reaches the end of the
;      purple bridge (x >= 3360): it then starts from the right screen edge (its list x 3552).
;      A != 0 = wake. ----
r_boss:  LDA $48
         AND #$20
         BNE rb1
         LDA $011E
         CMP #$04
         BNE rb0
         LDA $F3
         CMP #$0B
         BNE rb0
         LDA $6E
         CMP #$0D
         BCC rb0
         BNE rb1
         LDA $6D
         CMP #$20
         BCC rb0
rb1:     LDA #$01
         STA $011D
         RTS
rb0:     LDA #$00
         STA $011D
         RTS
; ---- 12: HUD row buffers at round start (was $C2A9-$C2D9, the same copies); D-42 HEAVEN OR
;      HELL: the "PW" label is left blank ----
r_hud:   LDX #$7F
         LDA #$FF
hu1:     STA $0356,X
         DEX
         BPL hu1
         LDX #$07
hu2:     LDA $C2DA,X
         STA $0358,X
         DEX
         BPL hu2
         LDA #$00
         STA $037D
         LDX #$08
hu3:     LDA $C2E2,X
         STA $0397,X
         LDA $C2EB,X
         STA $03B7,X
         DEX
         BPL hu3
         LDA $011E
         CMP #$04
         BNE hu4
         LDA #$FF
         STA $035E
         STA $035F
hu4:     RTS
"""

FIXED_SRC = """
far:     STA $011D
         LDA $AE
         PHA
         LDA $08
         PHA
         LDA #$0A
         STA $08
         TYA
         PHA
         JSR $E475
         PLA
         TAY
         JSR $A000
         PLA
         STA $08
         PLA
         BEQ f0
         JSR $E48B
         LDA $011D
         RTS
f0:      JSR $E475
         LDA $011D
         RTS
; QA 2026-11-18: callers that wait frames inside far (ending/cut-scene fades) first let the
; NMI drain the PPU queue - an entry queued from bank 2/3 data (a mouth frame) would be copied
; from bank 10/11 while far has them mapped (one frame of garbage tiles at the mouth).
farq:    LDX $30
         BEQ fq1
         JSR $E378
         JMP farq
fq1:     JMP far
frst:    LDY #$04
         JSR far
         JMP $CFBB
atkst:   LDY #$02
         JMP far
"""

B14_SRC = """
hst:     LDY #$05
         JSR far
         BEQ ho
         RTS                   ; EASY: handled, back to $80FD (JMP $8115)
ho:      LDA #$00              ; original $8455
         STA $78
         JMP $8459
vh:      LDA $43
         CMP #$06
         BNE vn
         LDA $011C
         BEQ vn
         JSR vn
vn:      LDA #$04
         STA $18
         JMP $E9AB
"""

SITES = {
    "dmg":   (0x1C52D, "293FA838A591"),     # damage taken          -> LDY #0 / JMP far
    "hp":    (0x1D2BC, "BD0E06A8B97BD5"),   # enemy max HP          -> LDY #1 / JSR far / NOP NOP
    "atk":   (0x1D2CB, "20F1D2"),           # JSR $D2F1             -> JSR atkst
    "pw":    (0x1C5C3, "A900858D858E"),     # gauge reset on swing  -> LDY #3 / JMP far / NOP
    "frame": (0x1C75D, "20BBCF"),           # gameplay loop         -> JSR frst
    "hit":   (0x00455, "A9008578"),         # hurt start            -> JMP hst
    "vel":   (0x1E9A7, "A9048518"),         # object move           -> JMP vh / NOP
    "hud":   (0x1C2A9, "A27FA9FF9D5603"),   # HUD buffers init      -> LDY #12 / JMP far
    "clr":   (0x1F1D1, "AAA9009D760560"),   # spawn flag clear      -> LDY #13 / JMP far
    "box":   (0x1EF81, "18BDAEF279AEF28526"),  # box sizes sum      -> JSR hsum / NOP x6
    "drag":  (0x01897, "A5484A900C"),       # bank 0 $9897 side      -> JSR dstub ($C2D5) / BPL $98AB
    "bwake": (0x030CE, "A5482920"),         # bank 1 $B0CE wake test -> JSR $BFFA / NOP (BEQ kept)
    "bstub": (0x03FFA, "FFFFFFFFFF"),       # bank 1 $BFFA (free)    -> LDY #15 / JMP far
}

# D-42: HEAVEN OR HELL weapon reach. Written into the old $C2AE-$C2D9 body of the HUD init
# (moved to bank 11, r_hud); the $C2DA tables after it stay. The box test $EF4D adds the two
# half sizes from $F2AE; when the second box is the weapon ($1E/$1F = $05F0, $DA92) a quarter
# of the weapon's half size is added (x 1.25 in both axes).
HSUM_ORG, HSUM_END = 0xC2AE, 0xC2DA
HSUM_SRC = """
hsum:    CLC
         LDA $F2AE,X
         ADC $F2AE,Y
         STA $26
         LDA $1E
         CMP #$F0
         BNE hx
         LDA $1F
         CMP #$05
         BNE hx
         LDA $011E
         CMP #$04
         BNE hx
         LDA $F2AE,Y
         LSR A
         LSR A
         CLC
         ADC $26
         STA $26
hx:      RTS
"""


def apply(p, orig, fixed_start, fixed_end):
    for name, (off, exp) in SITES.items():
        if orig[off:off + len(exp) // 2] != bytes.fromhex(exp):
            raise SystemExit(f"difficulty: unexpected bytes at {name} (file ${off:05X})")
    import post
    pcode, pl = post.assemble_b11()
    xcode, xl = assemble(DIFF_SRC.replace("USTAGE", "$%04X" % UNLOCK["ustage"]), DIFF_ORG)
    ext = {"ucheat": UNLOCK["cheat"], "r_fade": pl["r_fade"], "r_post": pl["r_post"], "r_fin": pl["r_fin"]}
    ext.update({k: xl[k] for k in ("r_dmg", "r_hp", "r_atk", "r_pw", "r_frame", "r_hit", "r_lives", "r_hud", "r_clr", "r_spawn", "r_boss")})
    bcode, _ = assemble(B11_SRC.replace("CHEAT", "$%04X" % UNLOCK["cheat"]), B11_ORG, ext)
    if B11_ORG + len(bcode) > 0xA200:
        raise SystemExit("difficulty: bank 11 code reaches the staff hook")
    fcode, fl = assemble(FIXED_SRC, fixed_start)
    kcode, kl = assemble(B14_SRC, B14_ORG, {"far": fl["far"]})
    if fixed_start + len(fcode) > fixed_end:
        raise SystemExit("difficulty: fixed-bank code does not fit")
    if B14_ORG + len(kcode) > B14_END:
        raise SystemExit("difficulty: bank 14 code does not fit")
    for code, foff in ((bcode, B11_FILE), (pcode, post.B11_FILE), (xcode, DIFF_FILE), (fcode, 0x1E000 + fixed_start - 0xE000),
                       (kcode, 0x1C000 + B14_ORG - 0xC000)):
        if any(x != 0xFF for x in orig[foff:foff + len(code)]):
            raise SystemExit(f"difficulty: free area at file ${foff:05X} is not $FF")
        p[foff:foff + len(code)] = code

    def w(a): return bytes([a & 0xFF, a >> 8])
    far = fl["far"]
    put = {
        "dmg":   b"\xa0\x00\x4c" + w(far),
        "hp":    b"\xa0\x01\x20" + w(far) + b"\xea\xea",
        "atk":   b"\x20" + w(fl["atkst"]),
        "pw":    b"\xa0\x03\x4c" + w(far) + b"\xea",
        "frame": b"\x20" + w(fl["frst"]),
        "hit":   b"\x4c" + w(kl["hst"]),
        "vel":   b"\x4c" + w(kl["vh"]) + b"\xea",
        "hud":   b"\xa0\x0c\x4c" + w(far),
        "clr":   b"\xa0\x0d\x4c" + w(far) + b"\xea\xea",
    }
    hcode, hl = assemble(HSUM_SRC, HSUM_ORG)
    if HSUM_ORG + len(hcode) > HSUM_END:
        raise SystemExit("difficulty: hsum does not fit")
    p[0x1C000 + HSUM_ORG - 0xC000:0x1C000 + HSUM_ORG - 0xC000 + len(hcode)] = hcode
    put["box"] = b"\x20" + w(hl["hsum"]) + b"\xea" * 6
    ds = HSUM_ORG + len(hcode)                # 5 bytes left before $C2DA: LDY #14 / JMP far
    if ds + 5 > HSUM_END:
        raise SystemExit("difficulty: no room for the dragon stub")
    p[0x1C000 + ds - 0xC000:0x1C000 + ds - 0xC000 + 5] = b"\xa0\x0e\x4c" + w(far)
    put["drag"] = b"\x20" + w(ds) + b"\x10\x0f"   # far returns LDA $011D (0/1): N = 0
    put["bwake"] = b"\x20\xfa\xbf\xea"            # far returns LDA $011D: Z for the BEQ
    put["bstub"] = b"\xa0\x0f\x4c" + w(far)
    for name, b in put.items():
        off = SITES[name][0]
        p[off:off + len(b)] = b
    return {"far": far, "farq": fl["farq"], "post_bytes": len(pcode), "bank11_bytes": len(bcode), "fixed_bytes": len(fcode), "bank14_bytes": len(kcode),
            "fixed_next": fixed_start + len(fcode)}
