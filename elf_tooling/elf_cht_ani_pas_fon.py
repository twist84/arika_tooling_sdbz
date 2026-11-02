#!/usr/bin/env python3
"""ELF tooling for .cht facial, .ani animation, .pas pose, .fon font formats."""
import struct
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mips_disasm import decode_instruction, file_to_vaddr, vaddr_to_file


def disasm_range(data, start_file_off, end_file_off):
    for off in range(start_file_off, end_file_off, 4):
        if off + 4 > len(data):
            break
        word = struct.unpack_from('<I', data, off)[0]
        vaddr = file_to_vaddr(off)
        mnemonic = decode_instruction(word, vaddr)
        print(f'  0x{vaddr:08X} 0x{off:06X}: 0x{word:08X}  {mnemonic}')


def find_gp_refs(data, target_vaddr, code_start=0x80, code_end=0x400700):
    target_lower = target_vaddr & 0xFFFF
    results = []
    for i in range(code_start, code_end - 4, 4):
        word = struct.unpack_from('<I', data, i)[0]
        op = (word >> 26) & 0x3F
        rs = (word >> 21) & 0x1F
        imm = word & 0xFFFF
        vaddr = file_to_vaddr(i)
        if op in (0x09, 0x0D, 0x23, 0x2B) and rs == 28 and imm == target_lower:
            kind = {0x09: 'addiu', 0x0D: 'ori', 0x23: 'lw', 0x2B: 'sw'}[op]
            results.append((kind, vaddr, i))
    return results


def find_string_in_data(data, search):
    results = []
    idx = 0
    while True:
        idx = data.find(search, idx)
        if idx == -1:
            break
        results.append(idx)
        idx += 1
    return results


def trace_format(data, format_name, vaddr):
    """Trace code that references a format string."""
    print(f"\n{format_name} at vaddr 0x{vaddr:08X} (file 0x{vaddr_to_file(vaddr):06X})")
    gp_refs = find_gp_refs(data, vaddr)
    print(f"  $gp-relative references: {len(gp_refs)}")
    for kind, ref_vaddr, ref_off in gp_refs:
        print(f"    {kind} at vaddr 0x{ref_vaddr:08X} (file 0x{ref_off:06X})")


def find_magic_in_data(data, magic, name):
    """Find magic bytes in ELF data section."""
    positions = find_string_in_data(data, magic)
    print(f"\n{name} magic ({magic!r}) in ELF data: {len(positions)} occurrence(s)")
    for pos in positions[:10]:
        vaddr = file_to_vaddr(pos)
        start = max(0x80, pos - 16)
        end = min(len(data), pos + len(magic) + 16)
        ctx = data[start:end]
        printable = ''.join(chr(b) if 32 <= b < 127 else '.' for b in ctx)
        print(f"  file 0x{pos:06X} (vaddr 0x{vaddr:08X}): ...{printable}...")


if __name__ == '__main__':
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    data = Path(elf_path).read_bytes()

    print("=" * 70)
    print("Remaining Format Analysis: CHT, ANI, PAS, FON")
    print("=" * 70)

    # Format strings
    formats = [
        ('CHT facial (%s.cht)', 0x004CA6B8),
        ('ANI animation (%s.ani)', 0x004CFAF0),
        ('PAS pose (%s.pas)', 0x004CFAC8),
        ('FON font (font/5-24-2.fon)', 0x004CD460),
    ]

    for name, vaddr in formats:
        trace_format(data, name, vaddr)

    # Magic bytes in data
    find_magic_in_data(data, b'CHT ', 'CHT')
    find_magic_in_data(data, b'HIT ', 'HIT')
    find_magic_in_data(data, b'FFON', 'FFON')

    # Look for .ani, .pas, .fon extension strings
    print("\n--- Extension strings in ELF data ---")
    for ext in [b'.ani', b'.pas', b'.fon', b'.cht']:
        positions = find_string_in_data(data, ext)
        print(f"  {ext.decode()}: {len(positions)} occurrence(s)")
        for pos in positions[:5]:
            vaddr = file_to_vaddr(pos)
            start = max(0x80, pos - 16)
            end = min(len(data), pos + 8)
            ctx = data[start:end]
            printable = ''.join(chr(b) if 32 <= b < 127 else '.' for b in ctx)
            print(f"    file 0x{pos:06X} (vaddr 0x{vaddr:08X}): ...{printable}...")
