#!/usr/bin/env python3
"""ELF tooling for .hit hitbox format - trace hitbox loading code."""
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


def trace_hit(data):
    """Trace HIT hitbox format usage in ELF."""
    print("=" * 70)
    print("HIT Hitbox Format - ELF Analysis")
    print("=" * 70)

    hit_strings = [
        ('stg/s01/s01a.hit', 0x004C8860, 0x004DDC48),
        ('stg/s10/s10a.hit', 0x004C9520, 0x00268B44),
        ('stg/s11/s11a.hit', 0x004C9700, 0x00287E64),
        ('stg/s12/s12a.hit', 0x004C99B0, 0x002A8824),
    ]

    print(f"\n--- HIT hitbox references ({len(hit_strings)} with code refs) ---\n")
    for name, str_vaddr, code_vaddr in hit_strings:
        str_file = vaddr_to_file(str_vaddr)
        code_file = vaddr_to_file(code_vaddr)
        print(f"  {name}")
        print(f"    String at vaddr 0x{str_vaddr:08X} (file 0x{str_file:06X})")
        print(f"    Referenced at vaddr 0x{code_vaddr:08X} (file 0x{code_file:06X})")
        print()

    # Disassemble key references
    print("--- Disassembly around key HIT references ---\n")
    key_refs = [
        (0x00268B44, "s10a.hit"),
        (0x00287E64, "s11a.hit"),
        (0x002A8824, "s12a.hit"),
    ]
    for code_vaddr, label in key_refs:
        code_file = vaddr_to_file(code_vaddr)
        print(f"  {label} at vaddr 0x{code_vaddr:08X} (file 0x{code_file:06X}):")
        start = max(0x80, code_file - 48)
        end = min(len(data) - 4, code_file + 16)
        disasm_range(data, start, end)
        print()


if __name__ == '__main__':
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    data = Path(elf_path).read_bytes()
    trace_hit(data)
