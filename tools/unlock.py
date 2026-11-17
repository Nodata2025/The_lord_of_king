"""D-29: STAGE / DEMO SELECT unlocks, saved in battery-backed PRG RAM.

Start: STAGE 1-1 and DEMO 1-2 (the opening). Locked entries show "?????" and the cursor
cannot go there. An entry unlocks the moment the story reaches it:
  STAGE k : gameplay with round $F3 == STAGE_ROUND[k]           (per gameplay frame, r_frame)
  DEMO k  : outside the theater ($F6 bit 5 clear) a dialogue string of that cut-scene runs
            ($03D6 in [DEMO_FIRST[k], DEMO_FIRST[k+1]), first strings recorded per demo)
Every unlock is written straight into PRG RAM ($6000-), which the iNES header now marks as
battery-backed (byte 6 bit 1), so it is saved at once. The SS88006 RAM is enabled through
$9002 (= 3: chip enable + write enable) before each access.

SRAM: $6000 'L' $6001 'K' $6002/$6003 stage bits (0-7 / 8-10) $6004/$6005 demo bits
      $6006 = $6002^$6003^$6004^$6005^$A5. Anything else -> defaults.
Code: bank 11 $A300 (mapped as $A000 with bank 10 during the text engine, the select screens
and the far calls from gameplay).
"""
from asm6502 import assemble

ORG, FILE = 0xA300, 0x16300
DEMO_FIRST = [0x00, 0x08, 0x10, 0x16, 0x1A, 0x1F, 0x21, 0x27, 0x2C, 0x38, 0x3E]


def src(stage_round, stage_cols, demo_cols):
    rows = [10, 13, 16, 19, 22, 25]

    def ppu(k, cols):
        return 0x2000 + 32 * rows[k // 2] + cols[k % 2]
    s_ppu = [ppu(k, stage_cols) for k in range(11)]
    d_ppu = [ppu(k, demo_cols) for k in range(11)]
    db = lambda v: ".db " + ",".join("$%02X" % x for x in v)
    return f"""
; ---- SRAM ----
srchk:   LDA #$03
         STA $9002
         LDA $6000
         CMP #$4C
         BNE srini
         LDA $6001
         CMP #$4B
         BNE srini
         JSR srsum
         CMP $6006
         BEQ srok
srini:   LDA #$4C
         STA $6000
         LDA #$4B
         STA $6001
         LDA #$01              ; STAGE 1-1
         STA $6002
         LDA #$03              ; DEMO 1, 2
         STA $6004
         LDA #$00
         STA $6003
         STA $6005
         JSR srsum
         STA $6006
srok:    RTS
srsum:   LDA $6002
         EOR $6003
         EOR $6004
         EOR $6005
         EOR #$A5
         RTS
; X = index 0-10, Y = list (0 stage, 1 demo) -> $011D = byte offset, A = bit
sraddr:  TYA
         ASL A
         STA $011D
         TXA
         CMP #$08
         BCC sa1
         INC $011D
sa1:     AND #$07
         TAY
         LDA bits,Y
         RTS
; C = 1 when entry X of list Y is locked (X, Y kept)
islock:  TXA
         PHA
         TYA
         PHA
         JSR srchk
         JSR sraddr
         LDX $011D
         AND $6002,X
         CLC
         BNE il1
         SEC
il1:     PLA
         TAY
         PLA
         TAX
         RTS
; unlock entry X of list Y and save
unlock:  JSR srchk
         JSR sraddr
         LDX $011D
         ORA $6002,X
         CMP $6002,X
         BEQ ul9
         STA $6002,X
         JSR srsum
         STA $6006
ul9:     RTS
; ---- gameplay (from r_frame): the round being played ----
ustage:  LDX #$0A
us1:     LDA $F3
         CMP srnd,X
         BEQ us2
         DEX
         BPL us1
         RTS
us2:     LDY #$00
         JMP unlock
; ---- text engine (from the staff hook, every frame): story cut-scenes ----
udemo:   LDA $F6
         AND #$20              ; theater: no unlocks
         BNE ud9
         LDA $03D7
         BPL ud9               ; no string running
         LDX #$0A
ud1:     LDA $03D6
         CMP dfirst,X
         BCS ud2
         DEX
         BPL ud1
ud9:     RTS
ud2:     LDY #$01
         JMP unlock
; ---- select screens (bank 10) ----
; entry: put the cursor on an unlocked entry ($03E4 index, $03E6 list)
selfix:  LDX $03E4
         LDY $03E6
         JSR islock
         BCC sf9
         LDA #$00
         STA $03E4
sf9:     RTS
; after a move: back to the previous index ($011C) when the new one is locked
selchk:  LDX $03E4
         LDY $03E6
         JSR islock
         BCC sc9
         LDA $011C
         STA $03E4
sc9:     RTS
; after the list was drawn (rendering off): "?????" over every locked entry
lockS:   LDY #$00
         BEQ lk0
lockD:   LDY #$01
lk0:     LDX #$00
lk1:     JSR islock
         BCC lk2
         TXA
         PHA
         TYA
         PHA
         LDA #$01
         STA $0108
         LDA #<qS
         STA $0109
         LDA #>qS
         STA $010A
         CPY #$00
         BEQ lk3
         LDA #<qD
         STA $0109
         LDA #>qD
         STA $010A
         LDA dplo,X
         STA $010B
         LDA dphi,X
         JMP lk4
lk3:     LDA splo,X
         STA $010B
         LDA sphi,X
lk4:     STA $010C
         LDA #$08
         STA $18
         LDA #$01
         STA $19
         JSR $E683
         PLA
         TAY
         PLA
         TAX
lk2:     INX
         CPX #$0B
         BCC lk1
         RTS
; ---- D-30 developer command: on the main menu with the cursor on GAME START,
; up up down down left right left right x2 -> everything unlocked, effect 04 ($C1 = 5)
cheat:   LDA $0101
         BNE ch0
         LDA $F9
         AND #$0F
         BEQ ch9
         LDX $0109
         CPX #$10
         BCC ch1
         LDX #$00
ch1:     CPX #$00
         BNE ch2
         LDY $0100             ; the first key only with the cursor on GAME START
         BNE ch0
ch2:     CMP kseq,X
         BNE chm
         INX
         STX $0109
         CPX #$10
         BNE ch9
         JSR srchk
         LDA #$FF
         STA $6002
         STA $6004
         LDA #$07
         STA $6003
         STA $6005
         JSR srsum
         STA $6006
         LDA #$05
         STA $C1
ch0:     LDA #$00
         STA $0109
ch9:     RTS
chm:     LDX #$00              ; wrong key: it may start the sequence again
         LDY $0100
         BNE chz
         CMP kseq
         BNE chz
         INX
chz:     STX $0109
         RTS
kseq:    .db $08,$08,$04,$04,$02,$01,$02,$01,$08,$08,$04,$04,$02,$01,$02,$01
bits:    .db $01,$02,$04,$08,$10,$20,$40,$80
srnd:    {db(stage_round)}
dfirst:  {db(DEMO_FIRST)}
splo:    {db([a & 0xFF for a in s_ppu])}
sphi:    {db([a >> 8 for a in s_ppu])}
dplo:    {db([a & 0xFF for a in d_ppu])}
dphi:    {db([a >> 8 for a in d_ppu])}
qS:      .db $09,$01,$2B,$2B,$2B,$2B,$2B,$FF,$FF,$FF,$FF
qD:      .db $07,$01,$2B,$2B,$2B,$2B,$2B,$FF,$FF
"""


def build(stage_round, stage_cols, demo_cols):
    code, labels = assemble(src(stage_round, stage_cols, demo_cols), ORG)
    if ORG + len(code) > 0xC000:
        raise SystemExit("unlock: bank 11 code too large")
    return code, labels
