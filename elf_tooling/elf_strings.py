#!/usr/bin/env python3
"""Scan ELF data section for string tables and referenced strings, map them to code references."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import struct
from elf_string_refs import find_refs_to_addr


def extract_strings(data, min_len=4):
    """Extract ASCII strings from the data section."""
    strings = []
    i = 0x80  # skip ELF header
    while i < len(data):
        b = data[i]
        if 32 <= b < 127:
            start = i
            while i < len(data) and 32 <= data[i] < 127:
                i += 1
            if i - start >= min_len:
                s = data[start:i].decode('ascii')
                strings.append((start, s))
        else:
            i += 1
    return strings


def find_string_literals(data, substrings):
    """Find strings containing any of the given substrings."""
    results = []
    for off, s in extract_strings(data):
        for sub in substrings:
            if sub in s:
                results.append((off, s))
                break
    return results


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'

    data = Path(path).read_bytes()

    print("=== Strings containing 'eff/' ===")
    for off, s in find_string_literals(data, ['eff/']):
        vaddr = 0x100000 + (off - 0x80)
        print(f"  file 0x{off:06X} (vaddr 0x{vaddr:08X}): {s!r}")

    print("\n=== Strings containing '.ebz' ===")
    for off, s in find_string_literals(data, ['.ebz']):
        vaddr = 0x100000 + (off - 0x80)
        print(f"  file 0x{off:06X} (vaddr 0x{vaddr:08X}): {s!r}")

    print("\n=== Strings containing 'trc/' ===")
    for off, s in find_string_literals(data, ['trc/']):
        vaddr = 0x100000 + (off - 0x80)
        print(f"  file 0x{off:06X} (vaddr 0x{vaddr:08X}): {s!r}")

    print("\n=== Strings containing 'CEBZ' or 'CEffect' ===")
    for off, s in find_string_literals(data, ['CEBZ', 'CEffect']):
        vaddr = 0x100000 + (off - 0x80)
        print(f"  file 0x{off:06X} (vaddr 0x{vaddr:08X}): {s!r}")

    print("\n=== Code references to string addresses ===")
    # Build string vaddr map (deduplicate)
    str_map = {}
    for off, s in find_string_literals(data, ['eff/', '.ebz', 'trc/', 'CEBZ', 'CEffect']):
        str_map[s] = 0x100000 + (off - 0x80)

    for s, vaddr in sorted(str_map.items(), key=lambda x: x[1]):
        refs = find_refs_to_addr(data, vaddr)
        print(f"\n  {s!r} (vaddr 0x{vaddr:08X}): {len(refs)} ref(s)")
        for kind, ref_vaddr, off, _ in refs[:5]:
            print(f"    {kind} at vaddr 0x{ref_vaddr:08X} (file 0x{off:06X})")
