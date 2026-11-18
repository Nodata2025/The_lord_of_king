"""D-39: gameplay slowdown with many enemies.

Profile (round 8, 600 frames of play with lag): the enemy spawner scan at $CE4F (called
from the main loop every frame) was the largest busy block, ~23 % of the CPU time. Every
frame it walks the whole spawn list of the round and, for every entry, decodes the 12-bit
position with ASL/ROL abs pairs ($CEA6, ~150 cycles) before comparing it with the scroll
column.

The rewrite (same results, same order: from the last entry down, first match with a clear
"already spawned" flag wins, one spawn per frame) rejects an entry with one AND/CMP on the
low nibble of its position byte (1 in 16 pass), checks the high nibble against both
columns, then the spawned flag, and decodes the fields only for the entry that spawns.
ZP $24-$26 are scratch here (the sprite builder uses them the same way; NMI/IRQ do not).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from asm6502 import assemble  # noqa: E402

ORG, END = 0xCE71, 0xCF1A          # replaces the scan loop + $CEA6 decode/compare
FILE = 0x1C000 + ORG - 0xC000      # bank 14 (fixed at $C000)

SRC = """
         LDY #$00
         LDA ($5C),Y           ; last entry index
         STA $05A7
         CLC
         LDA $5C
         ADC #$01
         STA $5E
         LDA $5D
         ADC #$00
         STA $5F
         LDA $0556             ; column low nibble (in bits 4-7)
         LSR A
         LSR A
         LSR A
         LSR A
         STA $24
         LDA $48               ; axis: byte 0 (horizontal) or 1 (vertical)
         AND #$01
         STA $25
         LDX $4A               ; second column: $4A or $4E ($0557 = it + 1)
         TAY
         BEQ ax
         LDX $4E
ax:      STX $26
lp:      LDA $05A7
         ASL A
         ASL A
         ORA $25
         TAY
         LDA ($5E),Y
         TAX
         AND #$0F
         CMP $24
         BNE nx
         TXA
         LSR A
         LSR A
         LSR A
         LSR A
         CMP $0557
         BEQ hit
         CMP $26
         BNE nx
hit:     LDA $05A7
         JSR $F1C5             ; already spawned?
         BNE nx
         LDA $05A7
         ASL A
         ASL A
         TAY
         JSR dec
         JSR $CF1A             ; spawn (unchanged)
         JMP $E475
nx:      DEC $05A7
         BPL lp
         JMP $E475
dec:     LDA ($5E),Y           ; byte 0 -> $055B (high nibble), $055A (low nibble << 4)
         PHA
         LSR A
         LSR A
         LSR A
         LSR A
         STA $055B
         PLA
         ASL A
         ASL A
         ASL A
         ASL A
         STA $055A
         INY
         LDA ($5E),Y           ; byte 1 -> $055D / $055C
         PHA
         LSR A
         LSR A
         LSR A
         LSR A
         STA $055D
         PLA
         ASL A
         ASL A
         ASL A
         ASL A
         STA $055C
         INY
         LDA ($5E),Y
         STA $055F
         INY
         LDA ($5E),Y
         STA $055E
         RTS
"""

# ---- divide by 192 ($F76D, 16-bit Y:A -> Y = quotient, A = remainder) ----
# Vertical rounds turn every object's world Y into (screen, row) with it, ~20 calls a frame;
# the original subtracts 192 in a loop (quotient + 1 passes, ~25 cycles each).
# New: q = hi + floor(hi / 3) + carry, r = 64 * (hi mod 3) + lo (- 192), since 256 = 192 + 64.
# Same results ($23 = remainder, $24 = 0 as before) for every input except $80C0-$80FF
# (y ~ 32960 px, outside every round); hi >= $81 ("negative") goes to the original short path
# kept in the spawner's spare bytes.
DIV_ORG, DIV_END = 0xF76D, 0xF79D
DIV_SRC = """
         STA $23
         STY $24
         CPY #$81
         BCC dpos
         JMP DIVNEG
dpos:    TYA                   ; Y accumulates the quotient from hi
dl:      CMP #$03
         BCC dm
         SBC #$03
         INY
         BNE dl
dm:      LSR A                 ; hi mod 3 (0-2) -> 0/$40/$80, carry clear
         ROR A
         ROR A
         ADC $23
         BCS db
         CMP #$C0
         BCC ds
db:      SBC #$C0
         INY
ds:      STA $23
         LDA #$00
         STA $24
         LDA $23
         RTS
"""
NEG_SRC = """
dneg:    LDY #$00              ; original result for hi >= $81: Y = 0 (+1), A = lo (- 192)
         LDA $23
         CMP #$C0
         BCC dn9
         SBC #$C0
         INY
dn9:     RTS
"""
DIV_ORIG = bytes.fromhex("85238424A000")   # STA $23 / STY $24 / LDY #0

ORIG_HEAD = bytes.fromhex("A000B15C8DA705")   # $CE71: LDY #0 / LDA ($5C),Y / STA $05A7


def apply(p, orig_p):
    if orig_p[FILE:FILE + len(ORIG_HEAD)] != ORIG_HEAD or orig_p[FILE + END - ORG:FILE + END - ORG + 3] != bytes.fromhex("2070CF"):
        raise SystemExit("optimize: spawner scan bytes differ")
    code, _ = assemble(SRC, ORG)
    if ORG + len(code) > END:
        raise SystemExit("optimize: spawner scan too large (%d)" % len(code))
    p[FILE:FILE + len(code)] = code
    p[FILE + len(code):FILE + END - ORG] = b"\xea" * (END - ORG - len(code))
    # divide by 192
    neg_org = ORG + len(code)
    ncode, nl = assemble(NEG_SRC, neg_org)
    if neg_org + len(ncode) > END:
        raise SystemExit("optimize: no room for the divide's negative path")
    p[FILE + len(code):FILE + len(code) + len(ncode)] = ncode
    dfile = 0x1E000 + DIV_ORG - 0xE000
    if orig_p[dfile:dfile + 6] != DIV_ORIG or orig_p[dfile + DIV_END - DIV_ORG - 1] != 0x60:
        raise SystemExit("optimize: divide bytes differ")
    dcode, _ = assemble(DIV_SRC.replace("DIVNEG", "$%04X" % nl["dneg"]), DIV_ORG)
    if DIV_ORG + len(dcode) > DIV_END:
        raise SystemExit("optimize: divide too large (%d)" % len(dcode))
    p[dfile:dfile + len(dcode)] = dcode
    p[dfile + len(dcode):dfile + DIV_END - DIV_ORG] = b"\xea" * (DIV_END - DIV_ORG - len(dcode))
    return {"spawner_bytes": len(code), "div_bytes": len(dcode), "div_neg_bytes": len(ncode)}
