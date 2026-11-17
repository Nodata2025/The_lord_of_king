"""Tiny two-pass 6502 assembler for hook code (official opcodes only).

Syntax per line:  [label:] MNEMONIC [operand] [; comment]
  #$12 / #<label / #>label   immediate
  $12      zero page (only when value < $100 and the mode exists)
  $1234 / label             absolute
  $1234,X / label,Y         indexed
  ($12),Y  ($12,X)  ($1234) indirect
  .db $01,$02,label_lo...   raw bytes (<label / >label allowed)
  .dw label                 little-endian word
Branches take a label or absolute address.
"""
import re
from dis6502 import OPS

_BY = {}
for code, (m, md) in OPS.items():
    _BY[(m, md)] = code

_SIZE = dict(imp=1, acc=1, imm=2, zp=2, zpx=2, zpy=2, izx=2, izy=2, rel=2, abs=3, abx=3, aby=3, ind=3)


def _val(tok, labels, pass2):
    tok = tok.strip()
    if tok.startswith("<"):
        return _val(tok[1:], labels, pass2) & 0xFF
    if tok.startswith(">"):
        return _val(tok[1:], labels, pass2) >> 8
    m = re.fullmatch(r"(.+?)([+-])(\$?[0-9A-Fa-f]+)", tok)
    if m and not tok.startswith("$"):
        base = _val(m.group(1), labels, pass2)
        off = int(m.group(3)[1:], 16) if m.group(3).startswith("$") else int(m.group(3))
        return base + off if m.group(2) == "+" else base - off
    if tok.startswith("$"):
        return int(tok[1:], 16)
    if tok.isdigit():
        return int(tok)
    if tok in labels:
        return labels[tok]
    if pass2:
        raise ValueError(f"undefined label {tok}")
    return 0x1234  # placeholder, absolute-sized


def _mode(m, arg, labels, pass2):
    if arg is None or arg == "":
        return ("acc" if (m, "acc") in _BY and False else "imp"), None
    if arg == "A":
        return "acc", None
    if arg.startswith("#"):
        return "imm", _val(arg[1:], labels, pass2)
    if (m, "rel") in _BY:
        return "rel", _val(arg, labels, pass2)
    mm = re.fullmatch(r"\((.+),X\)", arg)
    if mm:
        return "izx", _val(mm.group(1), labels, pass2)
    mm = re.fullmatch(r"\((.+)\),Y", arg)
    if mm:
        return "izy", _val(mm.group(1), labels, pass2)
    mm = re.fullmatch(r"\((.+)\)", arg)
    if mm:
        return "ind", _val(mm.group(1), labels, pass2)
    idx = None
    mm = re.fullmatch(r"(.+),([XY])", arg)
    if mm:
        arg, idx = mm.group(1), mm.group(2)
    v = _val(arg, labels, pass2)
    is_label = not arg.strip().startswith("$")
    zp_ok = v < 0x100 and not is_label
    if idx is None:
        return ("zp" if zp_ok and (m, "zp") in _BY else "abs"), v
    if idx == "X":
        return ("zpx" if zp_ok and (m, "zpx") in _BY else "abx"), v
    return ("zpy" if zp_ok and (m, "zpy") in _BY else "aby"), v


def assemble(src, org, labels=None):
    """Returns (bytes, labels). External labels may be passed in."""
    ext = dict(labels or {})
    lines = []
    for raw in src.splitlines():
        line = raw.split(";")[0].rstrip()
        if not line.strip():
            continue
        lab = None
        mm = re.match(r"\s*([A-Za-z_]\w*):\s*(.*)", line)
        if mm:
            lab, line = mm.group(1), mm.group(2)
        lines.append((lab, line.strip()))
    out = b""
    for pass2 in (False, True):
        pc, out, labs = org, bytearray(), dict(ext)
        if pass2:
            labs.update(found)
        found_now = {}
        for lab, line in lines:
            if lab:
                found_now[lab] = pc
                labs[lab] = pc
            if not line:
                continue
            parts = line.split(None, 1)
            m = parts[0].upper()
            arg = parts[1].strip() if len(parts) > 1 else None
            if m == ".DB":
                bs = [_val(x, labs, pass2) & 0xFF for x in arg.split(",")]
                out += bytes(bs); pc += len(bs); continue
            if m == ".DW":
                for x in arg.split(","):
                    v = _val(x, labs, pass2); out += bytes([v & 0xFF, v >> 8]); pc += 2
                continue
            md, v = _mode(m, arg, labs, pass2)
            code = _BY.get((m, md))
            if code is None:
                raise ValueError(f"bad instruction {m} {arg} ({md})")
            out.append(code)
            if md == "rel":
                d = v - (pc + 2)
                if pass2 and not -128 <= d <= 127:
                    raise ValueError(f"branch out of range at ${pc:04X}")
                out.append(d & 0xFF)
            elif _SIZE[md] == 2:
                out.append(v & 0xFF)
            elif _SIZE[md] == 3:
                out += bytes([v & 0xFF, v >> 8])
            pc += _SIZE[md]
        found = found_now
    return bytes(out), found
