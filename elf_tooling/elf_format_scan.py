#!/usr/bin/env python3
"""General ELF format scanner: finds all references to file format magics and extensions in the PS2 ELF."""
import struct
import sys
from pathlib import Path


def file_to_vaddr(file_off):
    return 0x100000 + (file_off - 0x80)


def vaddr_to_file(vaddr):
    return vaddr - 0x100000 + 0x80


def extract_strings(data, min_len=3):
    """Extract all null-terminated ASCII strings from the ELF data section."""
    strings = []
    i = 0x80
    while i < len(data):
        b = data[i]
        if 32 <= b < 127:
            start = i
            while i < len(data) and 32 <= data[i] < 127:
                i += 1
            if i - start >= min_len:
                s = data[start:i].decode('ascii')
                vaddr = file_to_vaddr(start)
                strings.append((start, vaddr, s))
        else:
            i += 1
    return strings


def find_string_refs(data, target_vaddr):
    """Find all code references to a target vaddr (lui+ori pairs, gp-relative)."""
    target_upper = (target_vaddr >> 16) & 0xFFFF
    target_lower = target_vaddr & 0xFFFF
    results = []

    for i in range(0x80, 0x400700 - 4, 4):
        word = struct.unpack_from('<I', data, i)[0]
        op = (word >> 26) & 0x3F
        rt = (word >> 16) & 0x1F
        rs = (word >> 21) & 0x1F
        imm = word & 0xFFFF
        vaddr = file_to_vaddr(i)

        if op == 0x0F:  # lui
            if imm == target_upper:
                if i + 4 < len(data):
                    w2 = struct.unpack_from('<I', data, i + 4)[0]
                    op2 = (w2 >> 26) & 0x3F
                    if op2 == 0x0D:  # ori
                        rt2 = (w2 >> 16) & 0x1F
                        rs2 = (w2 >> 21) & 0x1F
                        imm2 = w2 & 0xFFFF
                        if rt2 == rt and rs2 == rt and imm2 == target_lower:
                            results.append(('lui+ori', vaddr, i, target_vaddr))
        elif op == 0x0D:  # ori from $gp ($28)
            if rs == 28 and imm == target_lower:
                results.append(('ori-from-gp', vaddr, i, target_vaddr))
        elif op in (0x23, 0x2B):  # lw/sw from $gp
            if rs == 28 and imm == target_lower:
                results.append(('gp-mem', vaddr, i, target_vaddr))
        elif op == 0x09:  # addiu from $gp
            if rs == 28 and imm == target_lower:
                results.append(('addiu-from-gp', vaddr, i, target_vaddr))

    return results


def find_format_references(data, formats):
    """Find all ELF references to format magics and extensions."""
    print("=== ELF Format Reference Map ===\n")

    # First, find all strings containing format extensions
    all_strings = extract_strings(data)

    format_strings = {}
    for ext in formats:
        matches = [(start, vaddr, s) for start, vaddr, s in all_strings if ext in s]
        format_strings[ext] = matches

    for ext, matches in sorted(format_strings.items()):
        print(f"--- {ext} ({len(matches)} string occurrence(s)) ---")
        for start, vaddr, s in matches:
            refs = find_string_refs(data, vaddr)
            print(f"  '{s}' at vaddr 0x{vaddr:08X} (file 0x{start:06X}): {len(refs)} code ref(s)")
            for kind, ref_vaddr, ref_off, _ in refs[:5]:
                print(f"    {kind} at vaddr 0x{ref_vaddr:08X} (file 0x{ref_off:06X})")
        print()


def find_magic_references(data, magics):
    """Find raw magic byte sequences in the ELF data section."""
    print("=== ELF Magic Byte References ===\n")

    for name, magic in magics.items():
        magic_bytes = magic if isinstance(magic, bytes) else magic.encode('ascii')
        positions = []
        idx = 0
        while True:
            idx = data.find(magic_bytes, idx)
            if idx == -1:
                break
            positions.append(idx)
            idx += 1

        print(f"--- {name} ({magic_bytes!r}) ({len(positions)} occurrence(s)) ---")
        for pos in positions[:20]:
            vaddr = file_to_vaddr(pos)
            # Show context
            start = max(0x80, pos - 16)
            end = min(len(data), pos + len(magic_bytes) + 16)
            ctx = data[start:end]
            printable = ''.join(chr(b) if 32 <= b < 127 else '.' for b in ctx)
            print(f"  file 0x{pos:06X} (vaddr 0x{vaddr:08X}): ...{printable}...")
        if len(positions) > 20:
            print(f"  ... and {len(positions) - 20} more")
        print()


if __name__ == '__main__':
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'

    data = Path(elf_path).read_bytes()

    # All known format magics
    magics = {
        'EBZ': b' ZBE',
        'FPIX': b'FPIX',
        'FMDL': b'FMDL',
        'RFSML3': b'RFSML3',
        'CHT ': b'CHT ',
        'HIT ': b'HIT ',
        'FFON': b'FFON',
        'STG ': b'STG ',
        'TIM2': b'TIM2',
        'INFO': b'\x7fwww.arika.co.jp',
    }

    # All known file extensions
    extensions = [
        '.ebz', '.pix', '.mdl', '.spt', '.pmt', '.cht', '.ani', '.hit',
        '.pas', '.fon', '.ase', '.ams', '.stg', '.iko', '.ico', '.txt',
        '.bin', '.dat', '.irx', '.sfd', '.cnf', '.img',
    ]

    find_magic_references(data, magics)
    print()
    find_format_references(data, extensions)
