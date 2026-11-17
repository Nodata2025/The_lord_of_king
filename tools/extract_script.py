"""Extract the cutscene/ending script (bank 10) to JSON.

usage: python3 tools/extract_script.py ROM [out.json]

Output goes to build/ by default (git-ignored): it contains source text.
Every entry is round-trip checked (decode -> encode == source bytes).
"""
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from common import load_rom, prg, decode, encode, SOURCE_PROFILE  # noqa: E402

BANK_FILE = 0x14000      # PRG offset of 8 KB bank 10
BANK_CPU = 0x8000        # mapped at $8000 while the text engine runs
PTR_TABLE = 0x80EC       # read at $8036/$803C, index = $03D6
PTR_COUNT = 78           # every pointer up to the first string start
SCRIPT_END_CPU = 0x8F01  # first byte after the last {END} (credits)


def main():
    rom = load_rom(sys.argv[1] if len(sys.argv) > 1 else None)
    out_path = sys.argv[2] if len(sys.argv) > 2 else "build/script_ja.json"
    p = prg(rom)
    t = BANK_FILE + (PTR_TABLE - BANK_CPU)
    ptrs = [p[t + 2 * i] | p[t + 2 * i + 1] << 8 for i in range(PTR_COUNT)]
    assert ptrs == sorted(ptrs), "pointer table not monotonic"
    assert ptrs[0] == PTR_TABLE + 2 * PTR_COUNT, "table does not end at first string"
    bounds = ptrs + [SCRIPT_END_CPU]
    entries = []
    for i, cpu in enumerate(ptrs):
        a = BANK_FILE + cpu - BANK_CPU
        b = BANK_FILE + bounds[i + 1] - BANK_CPU
        raw = p[a:b]
        text = decode(raw)
        assert encode(text) == raw, f"round trip failed S{i:02d}"
        entries.append({
            "id": f"S{i:02d}",
            "ptr_index": i,
            "cpu": f"${cpu:04X}",
            "prg_offset": f"0x{a:05X}",
            "len": len(raw),
            "sha1": hashlib.sha1(raw).hexdigest(),
            "ja": text,
        })
    doc = {"source": SOURCE_PROFILE, "region": "PRG bank 10 $80EC table, 78 entries",
           "entries": entries}
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    json.dump(doc, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(entries)} entries, {sum(e['len'] for e in entries)} bytes -> {out_path}")


if __name__ == "__main__":
    main()
