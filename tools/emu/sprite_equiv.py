# D-39: run the original ($EA70-$EB26) and the rewritten sprite tile loop on random objects in a
# 6502 interpreter and compare RAM. usage: sprite_equiv.py <ROM before> <ROM after>
import random, sys
sys.path.insert(0, __import__('os').path.dirname(__file__))
from cpu6502 import CPU
old = open(sys.argv[1], 'rb').read()[16:]
new = open(sys.argv[2], 'rb').read()[16:]
def image(prg):
    m = bytearray(0x10000)
    m[0xC000:0xE000] = prg[0x1C000:0x1E000]; m[0xE000:0x10000] = prg[0x1E000:0x20000]
    return m
MO, MN = image(old), image(new)
# valid layouts: table at $EB27 (pointers into the fixed bank with small counts)
lays = []
for k in range(64):
    p = MO[0xEB27 + 2 * k] | MO[0xEB28 + 2 * k] << 8
    if 0xC000 <= p < 0x10000 and 1 <= MO[p] <= 32: lays.append(k)
    else: break
print("layouts", len(lays))
rnd = random.Random(1)
bad = 0; N = 40000; cyc_o = cyc_n = 0
for t in range(N):
    st = {}
    ram = bytearray(rnd.getrandbits(8) for _ in range(0x800))
    lay = rnd.choice(lays); p = MO[0xEB27 + 2 * lay] | MO[0xEB28 + 2 * lay] << 8; n = MO[p]
    ram[0x300] = lay
    for i in range(1, n + 1): ram[0x300 + i] = rnd.choice([0xFE] + [rnd.getrandbits(8)] * 6)
    ram[0x1D], ram[0x1E] = 0x00, 0x03
    ram[0x42], ram[0x43] = 0x80, 0x07
    ram[0x18] = rnd.getrandbits(8) & 0xF7 if rnd.random() < .9 else rnd.getrandbits(8)
    # positions: mostly near screen
    for a in (0x19, 0x1B):
        v = rnd.randint(-40, 300) & 0xFFFF if rnd.random() < .9 else rnd.getrandbits(16)
        ram[a], ram[a + 1] = v & 0xFF, v >> 8
    ram[0x46] = rnd.choice([0, 3, 20, 60, 63, 64, 70])
    ram[0xF4] = rnd.getrandbits(8)
    outs = []
    for M in (MO, MN):
        m = bytearray(M); m[0:0x800] = ram
        c = CPU(m); c.sp = 0xF0
        c.run(0xEA70)
        outs.append((bytes(m[0:0x800]), c.cyc))
    a, b = outs[0][0], outs[1][0]
    cyc_o += outs[0][1]; cyc_n += outs[1][1]
    # compare all RAM except scratch ZP $1F-$26 and stack
    diff = [i for i in range(0x800) if a[i] != b[i] and not (0x1F <= i <= 0x26) and not (0x100 <= i < 0x200)]
    if diff:
        bad += 1
        if bad < 5: print("case", t, "diff", [(hex(i), a[i], b[i]) for i in diff[:8]], "lay", lay, "18=%02X" % ram[0x18])
print("cases", N, "bad", bad, "instr old/new %.2f" % (cyc_o / cyc_n))
