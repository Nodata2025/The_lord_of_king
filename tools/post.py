"""D-37: post-ending scene (story mode only).

After the end card, A/START fades out as before, but instead of the opening the screen
clears, Cutie's picture fades in without music and she says S78 (an extra string, no
source text). When the string ends: fade-out -> opening (mode $0F). DEMO 11 (theater)
keeps A/START on the card -> DEMO SELECT, so S78 never shows there.

Bank 3 (ending loop, tools/build.py ENDCHK_SRC) starts it; the palette work runs in
bank 11 through far (index 8 = fade-out + mode change, 9 = scene set-up), which frees
bank 3 space (its old fade loop moved here).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from asm6502 import assemble  # noqa: E402

B11_ORG, B11_FILE = 0xA600, 0x16600
STRING = 0x4E                      # S78
# Cutie (fairy) as in the opening's S11 page (mode $12, set at bank 3 $A103): palette $84,
# BG banks $00/$01 = $08/$0A, nametable 0 ($ED = 0), layout = picture loader entry $1C
# ($055B = $9C), mouth = bank 3 $A2C1 with X = 0
CUTIE_PAL, CUTIE_BANK, CUTIE_BANK2, CUTIE_DRAW = 0x84, 0x08, 0x0A, 0x9C
PAL = None                          # 16 bytes, filled by set_palette() from the ROM


def set_palette(prg):
    """BG palette the game would load: $80BD(A) copies 16 bytes from bank 2 $80CE+A, then
    $E742(7) puts $E7BB+4..7 into $012C-$012F (text window)."""
    global PAL
    b2 = 0x4000
    pal = bytearray(prg[b2 + 0xCE + CUTIE_PAL:b2 + 0xCE + CUTIE_PAL + 16])
    pal[12:16] = prg[0x1E7BB + 4:0x1E7BB + 8]
    PAL = bytes(pal)


SRC = """
; ---- far 8: fade out, then mode A ($011D) ----
r_fade:  JSR fout
         LDA $011D
         JMP $E073
fout:    LDY #$04              ; 4 steps of -$10 on every palette entry
fo1:     LDX #$1F
fo2:     LDA $0120,X
         SEC
         SBC #$10
         BCS fo3
         LDA #$0F
fo3:     STA $0120,X
         DEX
         BPL fo2
         JSR fup
         DEY
         BNE fo1
         RTS
fup:     LDA $DD               ; BG palette next NMI, sprite palette the one after
         ORA #$30
         STA $DD
         LDX #$06
fw:      JSR $E378             ; one frame (keeps A/X/Y)
         DEX
         BNE fw
         RTS
; ---- far 9: end card -> Cutie, silent ----
r_post:  JSR fout
         JSR $E4EA             ; no music
         JSR $E4F9
         LDA #$A0              ; clear rows 21-27 (end card), one PPU-queue entry per frame
         STA $18               ; source $CD01 = 32 blank tiles (the {PAGE} clear's own)
         LDA #$22
         STA $19
pc1:     LDA #$01
         LDY #$CD
         JSR $E6B0
         PHP
         JSR $E378
         PLP
         BCS pc1               ; queue full: same row again
         LDA $18
         CLC
         ADC #$20
         STA $18
         BCC pc2
         INC $19
pc2:     CMP #$80              ; $2380 = past row 27
         BNE pc1
         LDA #$00              ; no objects (the city scene's people)
         LDX #$C0
po1:     STA $0495,X
         DEX
         BNE po1
         JSR $E3F8             ; and their sprites off now (step 18 never redraws them)
         LDA #BANK             ; Cutie's picture: BG banks, nametable 0
         STA $00
         LDA #BANK2
         STA $01
         LDA #$00
         STA $ED
         LDA #DRAW             ; her layout drawn by the game's own picture loader ($819E),
         STA $055B             ; as the opening does; poststep waits for $055B = 0
         LDA #STR              ; S78 selected, not running ($03D7 = 0): the ending's step 18
         STA $03D6             ; goes to poststep (bank 3) from now on
         LDA #$00
         STA $03D7
         JMP $CD04             ; shadow copy now (the palette is still black)
; ---- far 10: fade in to Cutie's palette ----
r_fin:   LDA #$30              ; target -$30, -$20, -$10, exact
         STA $011D
fi0:     LDX #$0F
fi1:     LDA cpal,X
         SEC
         SBC $011D
         BCS fi2
         LDA #$0F
fi2:     STA $0120,X
         DEX
         BPL fi1
         JSR fup
         LDA $011D
         SEC
         SBC #$10
         STA $011D
         BCS fi0
         LDA #STR              ; start S78 as $9C5B does
         STA $03D6
         LDA #$80
         STA $03D7
         JMP $E378
cpal:    .db PALDB
"""


def assemble_b11():
    if PAL is None:
        raise SystemExit("post: palette not set")
    for v in PAL:
        if (v & 0x0F) == 0x0D:
            raise SystemExit("post: palette value $%02X would fade through $xD" % v)
    src = SRC.replace("BANK2", "$%02X" % CUTIE_BANK2).replace("BANK", "$%02X" % CUTIE_BANK).replace("DRAW", "$%02X" % CUTIE_DRAW).replace("STR", "$%02X" % STRING).replace("PALDB", ",".join("$%02X" % v for v in PAL))
    code, labels = assemble(src, B11_ORG)
    if B11_ORG + len(code) > 0xC000:
        raise SystemExit("post: bank 11 code too large")
    return code, labels
