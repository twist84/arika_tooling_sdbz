#!/usr/bin/env python3
"""ELF tooling for .ase sound archive format - trace sound loading code."""
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


def trace_ase(data):
    """Trace ASE sound archive format usage in ELF."""
    print("=" * 70)
    print("ASE Sound Archive Format - ELF Analysis")
    print("=" * 70)

    ase_strings = [
        ('ply/p%02d/voi/%s.ase', 0x004C3AF0, []),
        ('%s.ase', 0x004CC620, []),
        ('ply/p22/voi/enter.ase', 0x004DAC70, [0x00340AC4]),
        ('ply/p22/voi/ending.ase', 0x004DB8B0, [0x003A39BC]),
    ]

    print(f"\n--- ASE sound references ({len(ase_strings)} entries) ---\n")
    for name, str_vaddr, code_vaddrs in ase_strings:
        str_file = vaddr_to_file(str_vaddr)
        print(f"  '{name}' at vaddr 0x{str_vaddr:08X} (file 0x{str_file:06X})")
        for cv in code_vaddrs:
            cf = vaddr_to_file(cv)
            print(f"    Referenced at vaddr 0x{cv:08X} (file 0x{cf:06X})")
        print()

    # Disassemble the two known references
    print("--- Disassembly around ASE references ---\n")
    for label, cv in [("enter.ase", 0x00340AC4), ("ending.ase", 0x003A39BC)]:
        cf = vaddr_to_file(cv)
        print(f"  {label} at vaddr 0x{cv:08X} (file 0x{cf:06X}):")
        start = max(0x80, cf - 48)
        end = min(len(data) - 4, cf + 16)
        disasm_range(data, start, end)
        print()

    # Look for ASE magic in data section
    print("--- ASE magic in ELF data ---")
    ase_positions = []
    idx = 0
    while True:
        idx = data.find(b'ASE', idx)
        if idx == -1:
            break
        ase_positions.append(idx)
        idx += 1
    print(f"  Found {len(ase_positions)} occurrence(s) of 'ASE' bytes")
    for pos in ase_positions[:10]:
        vaddr = file_to_vaddr(pos)
        print(f"    file 0x{pos:06X} (vaddr 0x{vaddr:08X})")


if __name__ == '__main__':
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    data = Path(elf_path).read_bytes()
    trace_ase(data)
