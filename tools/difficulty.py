"""D-17 difficulty modes (EASY / NORMAL / HARD), chosen on the title menu (menus.py).

RAM (inside $0100-$011F, never written by the game after reset; the fast-text buffer now
stops at $0119):
  $011A damage remainder   $011B frame counter 0-4   $011C "extra move" flag for this frame
  $011D far-call A in/out  $011E difficulty 0/1/2    $011F = $011E ^ $5A (checked on the title)

EASY   damage taken x0.5 (remainder carried), player attack x1.5 (rounded up),
       PW gauge never drains, 9 lives, no horizontal knockback.
NORMAL original.
HARD   damage taken x1.2 (every 5 points one extra), boss max HP x1.5 (max HP >= 40 in the
       $D57B table = the boss list at bank 0 $8DB1-$8DC0 plus multi-part pieces),
       while a boss is on screen every 5th frame enemy objects (bullets included) move twice,
       no continue (game over -> opening, menus.py).

Code that does not fit the fixed banks lives in bank 11 (all $FF in the original) and is
reached through `far`: banks 10/11 are mapped through the game's own $08/$AE pair, the same
way bank 14 $D030 runs bank 4 enemy code.
"""
from asm6502 import assemble

B11_ORG, B11_FILE = 0xA000, 0x16000
B14_ORG, B14_END = 0xDFD3, 0xE000          # $FF-filled tail of bank 14 (fixed at $C000)

B11_SRC = """
disp:    LDA dhi,Y
         PHA
         LDA dlo,Y
         PHA
         LDA $011D
         RTS
dlo:     .db <r_dmg-1,<r_hp-1,<r_atk-1,<r_pw-1,<r_frame-1
dhi:     .db >r_dmg-1,>r_hp-1,>r_atk-1,>r_pw-1,>r_frame-1
; ---- 0: damage taken (was $C52D: A = attack id) ----
r_dmg:   AND #$3F
         TAY
         LDA $C5D5,Y
         STA $011D
         LDY $011E
         BEQ de
         CPY #$02
         BNE dap
         CLC                   ; HARD: +1 for every 5 points taken
         ADC $011A
         CMP #$05
         BCC dh1
         SBC #$05
         INC $011D
dh1:     STA $011A
         JMP dap
de:      CLC                   ; EASY: half, remainder kept for the next hit
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
; ---- 1: enemy max HP (was $D2BC: LDA $060E,X / TAY / LDA $D57B,Y) ----
r_hp:    LDA $060E,X
         TAY
         LDA $D57B,Y
         LDY $011E
         CPY #$02
         BNE hr
         CMP #$28
         BCC hr
         STA $011D
         LSR A
         ADC $011D
hr:      STA $011D
         RTS
; ---- 2: player attack power (wraps JSR $D2F1) ----
r_atk:   JSR $D2F1
         LDY $011E
         BNE ar
         STA $011D
         LSR A
         ADC $011D
ar:      STA $011D
         RTS
; ---- 3: PW gauge spent by a swing (was $C5C3-$C5D3) ----
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
r_frame: LDA #$00
         STA $011C
         LDA $011E
         CMP #$02
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
frst:    LDY #$04
         JSR far
         JMP $CFBB
atkst:   LDY #$02
         JMP far
"""

B14_SRC = """
kbh:     LDA $011E
         BNE kb1
         LDX #$00              ; EASY: knockback without horizontal speed
         JMP $8431
kb1:     SEC
         LDA $6D
         JMP $84E3
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
    "kb":    (0x004E0, "38A56D"),           # knockback X speed     -> JMP kbh
    "vel":   (0x1E9A7, "A9048518"),         # object move           -> JMP vh / NOP
}


def apply(p, orig, fixed_start, fixed_end):
    for name, (off, exp) in SITES.items():
        if orig[off:off + len(exp) // 2] != bytes.fromhex(exp):
            raise SystemExit(f"difficulty: unexpected bytes at {name} (file ${off:05X})")
    bcode, _ = assemble(B11_SRC, B11_ORG)
    fcode, fl = assemble(FIXED_SRC, fixed_start)
    kcode, kl = assemble(B14_SRC, B14_ORG)
    if fixed_start + len(fcode) > fixed_end:
        raise SystemExit("difficulty: fixed-bank code does not fit")
    if B14_ORG + len(kcode) > B14_END:
        raise SystemExit("difficulty: bank 14 code does not fit")
    for code, foff in ((bcode, B11_FILE), (fcode, 0x1E000 + fixed_start - 0xE000),
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
        "kb":    b"\x4c" + w(kl["kbh"]),
        "vel":   b"\x4c" + w(kl["vh"]) + b"\xea",
    }
    for name, b in put.items():
        off = SITES[name][0]
        p[off:off + len(b)] = b
    return {"bank11_bytes": len(bcode), "fixed_bytes": len(fcode), "bank14_bytes": len(kcode),
            "fixed_next": fixed_start + len(fcode)}
