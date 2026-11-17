"""Make an IPS patch: python3 tools/make_ips.py ORIGINAL PATCHED OUT.ips

Handles growth (the patched ROM is larger: CHR 128 KB -> 256 KB).
Records avoid the 'EOF' offset ($454F46) and are split at 0xFFFF bytes.
"""
import sys


def make_ips(a, b):
    out = bytearray(b"PATCH")
    i, n = 0, len(b)
    while i < n:
        if i < len(a) and a[i] == b[i]:
            i += 1
            continue
        j = i
        while j < n and j - i < 0xFFFF and not (j < len(a) and a[j] == b[j]
                                               and j + 1 < n and j + 1 < len(a) and a[j + 1] == b[j + 1]):
            j += 1
        start = i
        if start == 0x454F46:  # would read as "EOF"
            start -= 1
        chunk = b[start:j]
        out += start.to_bytes(3, "big") + len(chunk).to_bytes(2, "big") + chunk
        i = j
    out += b"EOF"
    return bytes(out)


def apply_ips(a, ips):
    buf = bytearray(a)
    k = 5
    while ips[k:k + 3] != b"EOF":
        off = int.from_bytes(ips[k:k + 3], "big"); size = int.from_bytes(ips[k + 3:k + 5], "big"); k += 5
        if size == 0:
            rl = int.from_bytes(ips[k:k + 2], "big"); data = ips[k + 2:k + 3] * rl; k += 3
        else:
            data = ips[k:k + size]; k += size
        if len(buf) < off + len(data):
            buf += b"\x00" * (off + len(data) - len(buf))
        buf[off:off + len(data)] = data
    return bytes(buf)


if __name__ == "__main__":
    a = open(sys.argv[1], "rb").read()
    b = open(sys.argv[2], "rb").read()
    ips = make_ips(a, b)
    assert apply_ips(a, ips) == b, "IPS round trip failed"
    open(sys.argv[3], "wb").write(ips)
    print(f"{len(ips)} bytes, verified")
