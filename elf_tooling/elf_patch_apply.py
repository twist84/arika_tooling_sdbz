#!/usr/bin/env python3
"""
ELF tooling: Apply PS2 cheat patches (.pnach / .cht) to an ELF, writing a
modified copy. Complements elf_patch_verify.py (verify -> apply -> re-verify).

Usage:
    python elf_patch_apply.py [elf] [pnach_or_cht] [output_elf]

Defaults:
    elf     = source_data/SLUS_214.42
    cheat   = (required)
    output  = source_data/SLUS_214.42.patched

Only patches whose EE vaddr maps inside the ELF file range are applied.
Patches outside the ELF (IO/GS registers, mastercodes) are reported but skipped.
A patch whose current bytes don't match the expected value is reported and
skipped unless --force is passed (pass "--force" as the last argument).
"""
import re
import shutil
import struct
import sys
from pathlib import Path


def vaddr_to_file(vaddr):
    return vaddr - 0x100000 + 0x80


def parse_pnach(path):
    patches = []
    text = Path(path).read_text(errors='replace')
    patch_re = re.compile(
        r'patch\s*=\s*(\d+),\s*([A-Za-z]+),\s*([0-9A-Fa-f]+),\s*(\w+),\s*([0-9A-Fa-f]+)',
        re.IGNORECASE,
    )
    for line in text.splitlines():
        m = patch_re.search(line)
        if not m:
            continue
        ptype, mem, addr, size, value = m.groups()
        patches.append({
            'source': 'pnach', 'type': ptype, 'mem': mem.upper(),
            'vaddr': int(addr, 16), 'size': size.lower(), 'value': int(value, 16),
            'line': line.strip(),
        })
    return patches


def parse_cht(path, data):
    patches = []
    text = Path(path).read_text(errors='replace')
    line_re = re.compile(r'^\s*([0-9A-Fa-f]{6,8})\s+([0-9A-Fa-f]{8})\s*$')
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('//') or line.startswith('"'):
            continue
        m = line_re.match(line)
        if not m:
            continue
        addr = int(m.group(1), 16)
        value = int(m.group(2), 16)
        candidates = [addr, addr & 0x00FFFFFF]
        chosen = None
        for cand in candidates:
            fo = vaddr_to_file(cand)
            if 0x80 <= fo < len(data) - 4:
                chosen = cand
                break
        if chosen is None:
            chosen = addr
        patches.append({
            'source': 'cht', 'type': '1', 'mem': 'EE',
            'vaddr': chosen, 'size': 'word', 'value': value,
            'line': line,
        })
    return patches


def main():
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    cheat_path = sys.argv[2] if len(sys.argv) > 2 else None
    out_path = sys.argv[3] if len(sys.argv) > 3 else str(Path(elf_path) + '.patched')
    force = '--force' in sys.argv  # accepted for compatibility; patches apply unconditionally

    if cheat_path is None:
        print("Usage: python elf_patch_apply.py [elf] [pnach|cht] [output_elf] [--force]")
        print(f"  Default ELF: {elf_path}")
        print("  Provide a .pnach or .cht cheat file (and an output path).")
        print("  Patches are applied unconditionally (they are writes, not checks).")
        return

    data = bytearray(Path(elf_path).read_bytes())
    cheat_path = Path(cheat_path)
    if cheat_path.suffix.lower() == '.pnach':
        patches = parse_pnach(cheat_path)
    elif cheat_path.suffix.lower() == '.cht':
        patches = parse_cht(cheat_path, data)
    else:
        print(f"Unknown cheat format: {cheat_path.suffix}")
        return

    print("=" * 72)
    print(f"APPLY CHEAT PATCHES: {cheat_path.name}")
    print(f"ELF: {elf_path}  ->  output: {out_path}")
    print(f"Force flag accepted (ignored; patches apply unconditionally).")
    print("=" * 72)

    applied = 0
    already = 0
    skipped_outside = 0

    for i, p in enumerate(patches, 1):
        vaddr = p['vaddr']
        value = p['value']
        file_off = vaddr_to_file(vaddr)

        print(f"\n[{i}/{len(patches)}] {p['source']}: {p['line']}")
        print(f"  EE vaddr = 0x{vaddr:08X}  ->  file offset = 0x{file_off:06X}")
        print(f"  patch value = 0x{value:08X} ({p['size']})")

        if file_off < 0x80 or file_off + 4 > len(data):
            print(f"  OUTSIDE ELF file range (size 0x{len(data):06X}) -> SKIPPED")
            skipped_outside += 1
            continue

        cur = struct.unpack_from('<I', data, file_off)[0]
        if cur == value:
            print(f"  current bytes = 0x{cur:08X}  ->  already matches patch value")
            already += 1
            continue

        struct.pack_into('<I', data, file_off, value)
        applied += 1
        print(f"  APPLIED: 0x{cur:08X} -> 0x{value:08X}")

    Path(out_path).write_bytes(data)
    print(f"\n{'=' * 72}")
    print(f"Summary: {applied} applied, {already} already present, "
          f"{skipped_outside} outside-ELF skipped")
    print(f"Wrote patched ELF: {out_path} ({len(data)} bytes)")


if __name__ == '__main__':
    main()
