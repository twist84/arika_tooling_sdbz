#!/usr/bin/env python3
"""
ELF tooling: Correlate extracted game files with ELF string references.

Enumerates files under source_data/extracted/, builds their expected ELF
load paths, then scans the ELF once to build a string->location map and
finds all code references (lui+ori pairs + raw values) to those paths.

Format strings used by the ELF:
  * 'eff/e%c%c/%s'  at vaddr 0x004C3A88
  * '%s.ebz'        at vaddr 0x004CEF28
  * 'trc/01/efin0001p0101' at vaddr 0x004CF0A0

Usage:
    python elf_file_corr.py [elf] [extracted_dir]
"""
import os
import struct
import sys
from pathlib import Path


def file_to_vaddr(file_off):
    return 0x100000 + (file_off - 0x80)


def vaddr_to_file(vaddr):
    return vaddr - 0x100000 + 0x80


def sign16(n):
    return n - 0x10000 if n & 0x8000 else n


def find_all_strings(data, start=0x80, end=None):
    """Return dict: string -> list of file_offsets."""
    if end is None:
        end = len(data)
    result = {}
    i = start
    while i < end:
        b = data[i]
        if 32 <= b < 127:
            start_off = i
            chars = []
            while i < end and 32 <= data[i] < 127:
                chars.append(chr(data[i]))
                i += 1
            s = ''.join(chars)
            result.setdefault(s, []).append(start_off)
        else:
            i += 1
    return result


def find_refs_to_vaddr(data, target_vaddr, code_start=0x80, code_end=0x400700):
    """Find all code references to target_vaddr (lui+ori pair or raw value)."""
    target_upper = (target_vaddr >> 16) & 0xFFFF
    target_lower = target_vaddr & 0xFFFF
    refs = []
    for i in range(code_start, code_end - 4, 4):
        word = struct.unpack_from('<I', data, i)[0]
        op = (word >> 26) & 0x3F
        rt = (word >> 16) & 0x1F
        rs = (word >> 21) & 0x1F
        imm = word & 0xFFFF
        vaddr = file_to_vaddr(i)

        # lui + ori pair
        if op == 0x0F and imm == target_upper and i + 4 < len(data):
            w2 = struct.unpack_from('<I', data, i + 4)[0]
            op2 = (w2 >> 26) & 0x3F
            if op2 == 0x0D:
                rt2 = (w2 >> 16) & 0x1F
                rs2 = (w2 >> 21) & 0x1F
                imm2 = w2 & 0xFFFF
                if rt2 == rt and rs2 == rt and imm2 == target_lower:
                    refs.append(('lui+ori', vaddr, i))
        # raw 32-bit value
        if data[i:i + 4] == struct.pack('<I', target_vaddr):
            refs.append(('raw-value', vaddr, i))
    return refs


def main():
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    extracted_dir = Path(sys.argv[2] if len(sys.argv) > 2 else r'C:\Dev\arika\source_data\extracted')

    data = Path(elf_path).read_bytes()

    print("=" * 72)
    print("ELF EXTRACTED-FILE CORRELATION")
    print("=" * 72)
    print(f"ELF: {elf_path}")
    print(f"Extracted dir: {extracted_dir}")
    print()

    # Build string map
    strings = find_all_strings(data)
    print(f"Unique strings found in ELF: {len(strings)}")
    print()

    # Enumerate extracted files and build expected load paths
    extracted_files = []
    for root, dirs, files in os.walk(extracted_dir):
        for fname in files:
            fpath = Path(root) / fname
            rel = fpath.relative_to(extracted_dir)
            extracted_files.append(str(rel))

    print(f"Extracted files: {len(extracted_files)}")
    print()

    # Find which extracted paths exist as strings in the ELF
    matched = []
    for path in sorted(extracted_files):
        if path in strings:
            matched.append(path)

    print(f"Extracted paths found as ELF strings: {len(matched)}")
    print()

    # Show references for matched paths
    total_refs = 0
    for path in matched:
        str_offs = strings[path]
        refs = []
        for str_off in str_offs:
            str_vaddr = file_to_vaddr(str_off)
            refs.extend(find_refs_to_vaddr(data, str_vaddr))
        total_refs += len(refs)
        if refs:
            print(f"\n  {path} ({len(refs)} ref(s)):")
            for kind, vaddr, file_off in refs[:6]:
                print(f"    {kind:<10} at vaddr 0x{vaddr:08X} (file 0x{file_off:06X})")
            if len(refs) > 6:
                print(f"    ... and {len(refs) - 6} more")

    print()
    print(f"Total references: {total_refs}")

    # Also report format string references
    print()
    print("=" * 72)
    print("FORMAT STRING REFERENCES")
    print("=" * 72)
    for name, fmt_str in [('eff/e%c%c/%s', 'eff/e%c%c/%s'),
                          ('%s.ebz', '%s.ebz'),
                          ('trc path', 'trc/01/efin0001p0101')]:
        if fmt_str in strings:
            str_offs = strings[fmt_str]
            all_refs = []
            for str_off in str_offs:
                str_vaddr = file_to_vaddr(str_off)
                all_refs.extend(find_refs_to_vaddr(data, str_vaddr))
            print(f"\n  '{fmt_str}' ({len(str_offs)} occurrence(s), {len(all_refs)} ref(s)):")
            for kind, vaddr, file_off in all_refs[:8]:
                print(f"    {kind:<10} at vaddr 0x{vaddr:08X} (file 0x{file_off:06X})")


if __name__ == '__main__':
    main()
