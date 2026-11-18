# minimal 6502 interpreter (official opcodes) for routine equivalence tests
class CPU:
    def __init__(s, mem):
        s.m = mem; s.a = s.x = s.y = 0; s.sp = 0xFD; s.pc = 0
        s.c = s.z = s.i = s.d = s.v = s.n = 0; s.cyc = 0
    def rd(s, a): return s.m[a & 0xFFFF]
    def wr(s, a, v): s.m[a & 0xFFFF] = v & 0xFF
    def push(s, v): s.wr(0x100 + s.sp, v); s.sp = (s.sp - 1) & 0xFF
    def pop(s): s.sp = (s.sp + 1) & 0xFF; return s.rd(0x100 + s.sp)
    def nz(s, v): v &= 0xFF; s.z = int(v == 0); s.n = v >> 7; return v
    def p(s): return s.n << 7 | s.v << 6 | 0x20 | s.d << 3 | s.i << 2 | s.z << 1 | s.c
    def setp(s, v): s.n = v >> 7 & 1; s.v = v >> 6 & 1; s.d = v >> 3 & 1; s.i = v >> 2 & 1; s.z = v >> 1 & 1; s.c = v & 1
    def run(s, pc, stop_sp=None, maxi=200000):
        s.pc = pc; base = s.sp
        for _ in range(maxi):
            op = s.rd(s.pc)
            if op == 0x60 and s.sp == base:
                return
            s.step()
        raise RuntimeError("timeout")
    def adr(s, mode):
        pc = s.pc
        if mode == 'imm': s.pc += 2; return pc + 1
        if mode == 'zp': s.pc += 2; return s.rd(pc + 1)
        if mode == 'zpx': s.pc += 2; return (s.rd(pc + 1) + s.x) & 0xFF
        if mode == 'zpy': s.pc += 2; return (s.rd(pc + 1) + s.y) & 0xFF
        if mode == 'abs': s.pc += 3; return s.rd(pc + 1) | s.rd(pc + 2) << 8
        if mode == 'abx': s.pc += 3; return ((s.rd(pc + 1) | s.rd(pc + 2) << 8) + s.x) & 0xFFFF
        if mode == 'aby': s.pc += 3; return ((s.rd(pc + 1) | s.rd(pc + 2) << 8) + s.y) & 0xFFFF
        if mode == 'izx': s.pc += 2; z = (s.rd(pc + 1) + s.x) & 0xFF; return s.rd(z) | s.rd((z + 1) & 0xFF) << 8
        if mode == 'izy': s.pc += 2; z = s.rd(pc + 1); return ((s.rd(z) | s.rd((z + 1) & 0xFF) << 8) + s.y) & 0xFFFF
        raise ValueError(mode)
    def adc(s, v):
        r = s.a + v + s.c; s.v = int(((s.a ^ r) & (v ^ r) & 0x80) != 0); s.c = int(r > 0xFF); s.a = s.nz(r)
    def cmp(s, r, v): s.c = int(r >= v); s.nz(r - v)
    def step(s):
        op = s.rd(s.pc); s.cyc += 1
        T = OPS.get(op)
        if T is None: raise ValueError("op %02X at %04X" % (op, s.pc))
        name, mode = T
        if mode == 'rel':
            off = s.rd(s.pc + 1); s.pc += 2
            if off >= 0x80: off -= 0x100
            cond = {'BPL': not s.n, 'BMI': s.n, 'BVC': not s.v, 'BVS': s.v, 'BCC': not s.c, 'BCS': s.c, 'BNE': not s.z, 'BEQ': s.z}[name]
            if cond: s.pc = (s.pc + off) & 0xFFFF
            return
        if mode == 'imp' or mode == 'acc':
            s.pc += 1
            if name == 'ASL': s.c = s.a >> 7; s.a = s.nz(s.a << 1)
            elif name == 'LSR': s.c = s.a & 1; s.a = s.nz(s.a >> 1)
            elif name == 'ROL': c = s.c; s.c = s.a >> 7; s.a = s.nz(s.a << 1 | c)
            elif name == 'ROR': c = s.c; s.c = s.a & 1; s.a = s.nz(s.a >> 1 | c << 7)
            elif name == 'TAX': s.x = s.nz(s.a)
            elif name == 'TAY': s.y = s.nz(s.a)
            elif name == 'TXA': s.a = s.nz(s.x)
            elif name == 'TYA': s.a = s.nz(s.y)
            elif name == 'TSX': s.x = s.nz(s.sp)
            elif name == 'TXS': s.sp = s.x
            elif name == 'INX': s.x = s.nz(s.x + 1)
            elif name == 'INY': s.y = s.nz(s.y + 1)
            elif name == 'DEX': s.x = s.nz(s.x - 1)
            elif name == 'DEY': s.y = s.nz(s.y - 1)
            elif name == 'CLC': s.c = 0
            elif name == 'SEC': s.c = 1
            elif name == 'CLV': s.v = 0
            elif name == 'CLI': s.i = 0
            elif name == 'SEI': s.i = 1
            elif name == 'CLD': s.d = 0
            elif name == 'SED': s.d = 1
            elif name == 'PHA': s.push(s.a)
            elif name == 'PLA': s.a = s.nz(s.pop())
            elif name == 'PHP': s.push(s.p() | 0x10)
            elif name == 'PLP': s.setp(s.pop())
            elif name == 'NOP': pass
            elif name == 'RTS': lo = s.pop(); hi = s.pop(); s.pc = ((hi << 8 | lo) + 1) & 0xFFFF
            else: raise ValueError(name)
            return
        if name == 'JSR':
            t = s.rd(s.pc + 1) | s.rd(s.pc + 2) << 8; r = s.pc + 2; s.push(r >> 8); s.push(r & 0xFF); s.pc = t; return
        if name == 'JMP':
            if mode == 'abs': s.pc = s.rd(s.pc + 1) | s.rd(s.pc + 2) << 8
            else:
                a = s.rd(s.pc + 1) | s.rd(s.pc + 2) << 8; s.pc = s.rd(a) | s.rd((a & 0xFF00) | ((a + 1) & 0xFF)) << 8
            return
        a = s.adr(mode)
        if name == 'LDA': s.a = s.nz(s.rd(a))
        elif name == 'LDX': s.x = s.nz(s.rd(a))
        elif name == 'LDY': s.y = s.nz(s.rd(a))
        elif name == 'STA': s.wr(a, s.a)
        elif name == 'STX': s.wr(a, s.x)
        elif name == 'STY': s.wr(a, s.y)
        elif name == 'ADC': s.adc(s.rd(a))
        elif name == 'SBC': s.adc(s.rd(a) ^ 0xFF)
        elif name == 'AND': s.a = s.nz(s.a & s.rd(a))
        elif name == 'ORA': s.a = s.nz(s.a | s.rd(a))
        elif name == 'EOR': s.a = s.nz(s.a ^ s.rd(a))
        elif name == 'CMP': s.cmp(s.a, s.rd(a))
        elif name == 'CPX': s.cmp(s.x, s.rd(a))
        elif name == 'CPY': s.cmp(s.y, s.rd(a))
        elif name == 'BIT': v = s.rd(a); s.z = int((s.a & v) == 0); s.n = v >> 7; s.v = v >> 6 & 1
        elif name in ('INC', 'DEC'): s.wr(a, s.nz(s.rd(a) + (1 if name == 'INC' else -1)))
        elif name in ('ASL', 'LSR', 'ROL', 'ROR'):
            v = s.rd(a)
            if name == 'ASL': s.c = v >> 7; v = v << 1
            elif name == 'LSR': s.c = v & 1; v = v >> 1
            elif name == 'ROL': c = s.c; s.c = v >> 7; v = v << 1 | c
            else: c = s.c; s.c = v & 1; v = v >> 1 | c << 7
            s.wr(a, s.nz(v))
        else: raise ValueError(name)

OPS = {}
def _d(name, table):
    for op, mode in table: OPS[op] = (name, mode)
for name, base in (('ORA', 0x00), ('AND', 0x20), ('EOR', 0x40), ('ADC', 0x60), ('STA', 0x80), ('LDA', 0xA0), ('CMP', 0xC0), ('SBC', 0xE0)):
    for off, mode in ((1, 'izx'), (5, 'zp'), (9, 'imm'), (0xD, 'abs'), (0x11, 'izy'), (0x15, 'zpx'), (0x19, 'aby'), (0x1D, 'abx')):
        if name == 'STA' and mode == 'imm': continue
        OPS[base + off] = (name, mode)
for name, base in (('ASL', 0x00), ('ROL', 0x20), ('LSR', 0x40), ('ROR', 0x60)):
    OPS[base + 0x0A] = (name, 'acc'); OPS[base + 6] = (name, 'zp'); OPS[base + 0x16] = (name, 'zpx'); OPS[base + 0xE] = (name, 'abs'); OPS[base + 0x1E] = (name, 'abx')
for name, base in (('DEC', 0xC0), ('INC', 0xE0)):
    OPS[base + 6] = (name, 'zp'); OPS[base + 0x16] = (name, 'zpx'); OPS[base + 0xE] = (name, 'abs'); OPS[base + 0x1E] = (name, 'abx')
_d('LDX', ((0xA2, 'imm'), (0xA6, 'zp'), (0xB6, 'zpy'), (0xAE, 'abs'), (0xBE, 'aby')))
_d('LDY', ((0xA0, 'imm'), (0xA4, 'zp'), (0xB4, 'zpx'), (0xAC, 'abs'), (0xBC, 'abx')))
_d('STX', ((0x86, 'zp'), (0x96, 'zpy'), (0x8E, 'abs')))
_d('STY', ((0x84, 'zp'), (0x94, 'zpx'), (0x8C, 'abs')))
_d('CPX', ((0xE0, 'imm'), (0xE4, 'zp'), (0xEC, 'abs')))
_d('CPY', ((0xC0, 'imm'), (0xC4, 'zp'), (0xCC, 'abs')))
_d('BIT', ((0x24, 'zp'), (0x2C, 'abs')))
for op, n in ((0x10, 'BPL'), (0x30, 'BMI'), (0x50, 'BVC'), (0x70, 'BVS'), (0x90, 'BCC'), (0xB0, 'BCS'), (0xD0, 'BNE'), (0xF0, 'BEQ')): OPS[op] = (n, 'rel')
for op, n in ((0xAA, 'TAX'), (0xA8, 'TAY'), (0x8A, 'TXA'), (0x98, 'TYA'), (0xBA, 'TSX'), (0x9A, 'TXS'), (0xE8, 'INX'), (0xC8, 'INY'), (0xCA, 'DEX'), (0x88, 'DEY'),
              (0x18, 'CLC'), (0x38, 'SEC'), (0xB8, 'CLV'), (0x58, 'CLI'), (0x78, 'SEI'), (0xD8, 'CLD'), (0xF8, 'SED'), (0x48, 'PHA'), (0x68, 'PLA'), (0x08, 'PHP'), (0x28, 'PLP'), (0xEA, 'NOP'), (0x60, 'RTS')):
    OPS[op] = (n, 'imp')
OPS[0x20] = ('JSR', 'abs'); OPS[0x4C] = ('JMP', 'abs'); OPS[0x6C] = ('JMP', 'ind')
