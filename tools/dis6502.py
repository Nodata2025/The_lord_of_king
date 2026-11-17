# minimal 6502 disassembler (official opcodes)
OPS={}
def d(m,ops):
    for k,v in ops.items(): OPS[v]=(m,k)
modes=dict(imp=0,acc=0,imm=1,zp=1,zpx=1,zpy=1,izx=1,izy=1,rel=1,abs=2,abx=2,aby=2,ind=2)
T="""ADC 69imm 65zp 75zpx 6Dabs 7Dabx 79aby 61izx 71izy
AND 29imm 25zp 35zpx 2Dabs 3Dabx 39aby 21izx 31izy
ASL 0Aacc 06zp 16zpx 0Eabs 1Eabx
BCC 90rel
BCS B0rel
BEQ F0rel
BIT 24zp 2Cabs
BMI 30rel
BNE D0rel
BPL 10rel
BRK 00imp
BVC 50rel
BVS 70rel
CLC 18imp
CLD D8imp
CLI 58imp
CLV B8imp
CMP C9imm C5zp D5zpx CDabs DDabx D9aby C1izx D1izy
CPX E0imm E4zp ECabs
CPY C0imm C4zp CCabs
DEC C6zp D6zpx CEabs DEabx
DEX CAimp
DEY 88imp
EOR 49imm 45zp 55zpx 4Dabs 5Dabx 59aby 41izx 51izy
INC E6zp F6zpx EEabs FEabx
INX E8imp
INY C8imp
JMP 4Cabs 6Cind
JSR 20abs
LDA A9imm A5zp B5zpx ADabs BDabx B9aby A1izx B1izy
LDX A2imm A6zp B6zpy AEabs BEaby
LDY A0imm A4zp B4zpx ACabs BCabx
LSR 4Aacc 46zp 56zpx 4Eabs 5Eabx
NOP EAimp
ORA 09imm 05zp 15zpx 0Dabs 1Dabx 19aby 01izx 11izy
PHA 48imp
PHP 08imp
PLA 68imp
PLP 28imp
ROL 2Aacc 26zp 36zpx 2Eabs 3Eabx
ROR 6Aacc 66zp 76zpx 6Eabs 7Eabx
RTI 40imp
RTS 60imp
SBC E9imm E5zp F5zpx EDabs FDabx F9aby E1izx F1izy
SEC 38imp
SED F8imp
SEI 78imp
STA 85zp 95zpx 8Dabs 9Dabx 99aby 81izx 91izy
STX 86zp 96zpy 8Eabs
STY 84zp 94zpx 8Cabs
TAX AAimp
TAY A8imp
TSX BAimp
TXA 8Aimp
TXS 9Aimp
TYA 98imp"""
for line in T.splitlines():
    p=line.split(); m=p[0]
    for t in p[1:]: OPS[int(t[:2],16)]=(m,t[2:])
FMT=dict(imp='',acc='A',imm='#${:02X}',zp='${:02X}',zpx='${:02X},X',zpy='${:02X},Y',izx='(${:02X},X)',izy='(${:02X}),Y',abs='${:04X}',abx='${:04X},X',aby='${:04X},Y',ind='(${:04X})')
def dis(buf,off,base,count):
    out=[];i=off
    for _ in range(count):
        if i>=len(buf): break
        op=buf[i]; pc=base+i-off
        if op not in OPS: out.append('%04X  %02X        .db'%(pc,op)); i+=1; continue
        m,md=OPS[op]; n=modes[md]; b=buf[i+1:i+1+n]
        if md=='rel':
            r=b[0]-256 if b[0]>127 else b[0]; arg='${:04X}'.format(pc+2+r)
        elif n==1: arg=FMT[md].format(b[0])
        elif n==2: arg=FMT[md].format(b[0]|b[1]<<8)
        else: arg=FMT[md]
        out.append('%04X  %-9s %s %s'%(pc,' '.join('%02X'%x for x in buf[i:i+1+n]),m,arg)); i+=1+n
    return '\n'.join(out)
if __name__=='__main__':
    import sys
    rom=open(sys.argv[1],'rb').read()[16:16+131072]
    off=int(sys.argv[2],16); base=int(sys.argv[3],16); n=int(sys.argv[4])
    print(dis(rom,off,base,n))
