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
($5E/$5F, the old +1 copy of the list pointer, is no longer written: only this routine
used it.) ZP $24-$26 are scratch here (the sprite builder uses them the same way; NMI/IRQ do not).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from asm6502 import assemble  # noqa: E402

ORG, END = 0xCE71, 0xCF1A          # replaces the scan loop + $CEA6 decode/compare
FILE = 0x1C000 + ORG - 0xC000      # bank 14 (fixed at $C000)

SRC = """
         LDY #$00
         LDA ($5C),Y           ; last entry index (entries follow at ($5C)+1)
         STA $05A7
         LDA $0556             ; column low nibble (in bits 4-7)
         LSR A
         LSR A
         LSR A
         LSR A
         STA $24
         LDX $4A               ; second column: $4A or $4E ($0557 = it + 1)
         LDA $48               ; axis: byte 0 (horizontal) or 1 (vertical)
         LSR A
         BCC ax
         LDX $4E
ax:      STX $26
         LDA #$01              ; $25 = 1 + axis = offset of the position byte from ($5C)+4i
         ADC #$00
         STA $25
lp:      LDA $05A7
         ASL A
         ASL A
         ORA $25
         TAY
         LDA ($5C),Y
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
         INY
         JSR dec
         JSR $CF1A             ; spawn (unchanged)
         JMP $E475
nx:      DEC $05A7
         BPL lp
         JMP $E475
dec:     LDA ($5C),Y           ; byte 0 -> $055B (high nibble), $055A (low nibble << 4)
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
         LDA ($5C),Y           ; byte 1 -> $055D / $055C
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
         LDA ($5C),Y
         STA $055F
         INY
         LDA ($5C),Y
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

# ---- metasprite tiles -> OAM ($EA70-$EB06; $EB07 OAM writer kept, also called from $CC69) ----
# Every object's tiles go through $EAA9 (~200 cycles a tile: attribute and flip tests
# recomputed per tile, a JSR to $EB07). Round 2-1 with ~10 objects spent ~12k cycles a
# frame in the object draw ($CFBB). Same output, same tile order (even frames last tile
# first, odd frames first tile first), same "drawn" flag ($18 bit 3); the attribute is built
# once per object (it only depends on $18 bits 0-1 and 4-6, which the loop never changes)
# and the flips come from it (bit 6 = H, bit 7 = V).
SPR_ORG, SPR_END = 0xEA70, 0xEB07
SPR_SRC = """
         LDY #$00
         LDA ($1D),Y           ; layout
         ASL A
         TAX
         LDA $EB27,X
         STA $1F
         LDA $EB28,X
         STA $20
         LDA ($1F),Y           ; tile count
         STA $21
         LDA $18               ; attribute = palette | V,H,priority from $18 bits 6,5,4
         AND #$03
         STA $25
         LDA $18
         ASL A
         AND #$E0
         ORA $25
         STA $25
         LDA $F4
         LSR A
         BCS so
se:      JSR st                ; even frame: tiles n..1
         DEC $21
         BNE se
         BEQ sf
so:      LDA $21               ; odd frame: tiles 1..n
         STA $26
         LDA #$01
         STA $21
so1:     JSR st
         INC $21
         DEC $26
         BNE so1
sf:      LDY #$00
         LDA $18
         STA ($42),Y
         RTS
st:      LDY $21
         LDA ($1D),Y           ; tile
         CMP #$FE
         BEQ sx
         STA $24
         TYA
         ASL A
         TAY
         DEY
         LDX #$00
         LDA $25
         ASL A
         ASL A                 ; C = H flip
         LDA ($1F),Y           ; dx
         BCC sh1
         EOR #$FF
         ADC #$00              ; -dx
sh1:     BPL sh2
         DEX                   ; sign extension
sh2:     CLC
         ADC $19
         STA $22
         TXA
         ADC $1A
         BNE sx                ; off screen
         INY
         LDX #$00
         LDA $25
         ASL A                 ; C = V flip
         LDA ($1F),Y           ; dy
         BCC sv1
         EOR #$FF
         ADC #$00
sv1:     BPL sv2
         DEX
sv2:     CLC
         ADC $1B
         STA $23
         TXA
         ADC $1C
         BNE sx
sd:      LDA $18
         ORA #$08
         STA $18
         JMP $EB07             ; OAM write (unchanged)
sx:      RTS
"""
SPR_ORIG = bytes.fromhex("A000B11D0AAABD27EB851FBD28EB8520")

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
    # D-42: HEAVEN OR HELL has no items and no item containers. An item (a broken container's prize, bank 0 $9E2B
    # state) checks "off screen?" ($D115, C=1 -> deleted at $9E0D) every frame before it is
    # drawn or touched; in that mode the check always answers "off screen".
    it_org = neg_org + len(ncode)
    icode, il = assemble("""
hoi:     LDA $011E
         CMP #$04
         BCC hoi1
         RTS
hoi1:    JMP $D115
""", it_org)
    if it_org + len(icode) > END:
        raise SystemExit("optimize: no room for the item hook")
    p[FILE + it_org - ORG:FILE + it_org - ORG + len(icode)] = icode
    if orig_p[0x1E2F:0x1E32] != bytes.fromhex("2015D1") or orig_p[0x1E32] != 0xB0:
        raise SystemExit("optimize: item state bytes differ")
    p[0x1E2F:0x1E32] = bytes([0x20, il["hoi"] & 0xFF, il["hoi"] >> 8])
    # ...and the container (pillar) itself: its idle state ($9DD7) makes the same check,
    # so in that mode it is removed on its first frame, before it is drawn or hit.
    if orig_p[0x1DD7:0x1DDB] != bytes.fromhex("2015D1B0"):
        raise SystemExit("optimize: container state bytes differ")
    p[0x1DD7:0x1DDA] = bytes([0x20, il["hoi"] & 0xFF, il["hoi"] >> 8])
    # D-40 flicker: the player first in every frame. $CFC1 "LDA $F4 / LSR / BCS odd / JSR $D890"
    # becomes "JSR $D890 / LDA $F4 / LSR / BCS odd" (same 8 bytes) and the odd path's closing
    # "JMP $D890" an RTS: odd frames drew the enemies first and the player last, so on crowded
    # lines the player was the one dropped, and enemies covered him every other frame.
    if orig_p[0x1CFC1:0x1CFC9] != bytes.fromhex("A5F44AB02220 90D8".replace(" ", "")) or orig_p[0x1D008:0x1D00B] != bytes.fromhex("4C90D8"):
        raise SystemExit("optimize: object draw order bytes differ")
    p[0x1CFC1:0x1CFC9] = bytes.fromhex("2090D8A5F44AB01F")
    p[0x1D008:0x1D00B] = bytes([0x60, 0xEA, 0xEA])
    dfile = 0x1E000 + DIV_ORG - 0xE000
    if orig_p[dfile:dfile + 6] != DIV_ORIG or orig_p[dfile + DIV_END - DIV_ORG - 1] != 0x60:
        raise SystemExit("optimize: divide bytes differ")
    dcode, _ = assemble(DIV_SRC.replace("DIVNEG", "$%04X" % nl["dneg"]), DIV_ORG)
    if DIV_ORG + len(dcode) > DIV_END:
        raise SystemExit("optimize: divide too large (%d)" % len(dcode))
    p[dfile:dfile + len(dcode)] = dcode
    p[dfile + len(dcode):dfile + DIV_END - DIV_ORG] = b"\xea" * (DIV_END - DIV_ORG - len(dcode))
    sfile = 0x1E000 + SPR_ORG - 0xE000
    if orig_p[sfile:sfile + len(SPR_ORIG)] != SPR_ORIG or orig_p[0x1EB07:0x1EB0B] != bytes.fromhex("A546C940"):
        raise SystemExit("optimize: sprite bytes differ")
    scode, _ = assemble(SPR_SRC, SPR_ORG)
    if SPR_ORG + len(scode) > SPR_END:
        raise SystemExit("optimize: sprite loop too large (%d)" % len(scode))
    p[sfile:sfile + len(scode)] = scode
    p[sfile + len(scode):sfile + SPR_END - SPR_ORG] = b"\xea" * (SPR_END - SPR_ORG - len(scode))
    return {"spawner_bytes": len(code), "div_bytes": len(dcode), "div_neg_bytes": len(ncode),
            "sprite_bytes": len(scode)}
