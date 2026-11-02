#!/usr/bin/env python3
"""ELF tooling for .pas (pose) format - trace pose loading code."""
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
    """Find $gp-relative references (addiu/ori/lw/sw with $gp=$28) to target_vaddr."""
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


def find_raw_addr_refs(data, target_vaddr, code_start=0x80, code_end=0x400700):
    """Find raw 32-bit address values in code section."""
    target_bytes = struct.pack('<I', target_vaddr)
    results = []
    for i in range(code_start, code_end - 4, 4):
        if data[i:i + 4] == target_bytes:
            vaddr = file_to_vaddr(i)
            results.append(('raw-addr', vaddr, i))
    return results


def trace_format(data, format_name, vaddr, max_instr=160):
    """Trace code that references a format string."""
    print(f"\n{'=' * 70}")
    print(f"{format_name} at vaddr 0x{vaddr:08X}")
    print(f"{'=' * 70}\n")

    gp_refs = find_gp_refs(data, vaddr)
    raw_refs = find_raw_addr_refs(data, vaddr)
    all_refs = gp_refs + raw_refs

    print(f"Found {len(all_refs)} code reference(s):\n")
    for kind, ref_vaddr, ref_off in all_refs:
        print(f"  {kind} at vaddr 0x{ref_vaddr:08X} (file 0x{ref_off:06X})")

    for kind, ref_vaddr, ref_off in all_refs:
        print(f"\n  --- Code around {kind} at vaddr 0x{ref_vaddr:08X} ---")
        start = max(0x80, ref_off - 96)
        end = min(len(data) - 4, ref_off + 32)
        disasm_range(data, start, end)
        print()


if __name__ == '__main__':
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    data = Path(elf_path).read_bytes()

    formats = [
        ('PAS pose (%s.pas)', 0x004CFACA),
    ]

    for name, vaddr in formats:
        trace_format(data, name, vaddr)
