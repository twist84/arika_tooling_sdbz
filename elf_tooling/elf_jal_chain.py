#!/usr/bin/env python3
"""Follow JAL chains from CEBZ block references to trace the .ebz loading call graph."""
import struct
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mips_disasm import decode_instruction


def disasm_at(data, file_off):
    """Disassemble one instruction at file offset."""
    word = struct.unpack_from('<I', data, file_off)[0]
    vaddr = 0x100000 + (file_off - 0x80)
    return vaddr, word, decode_instruction(word)


def jal_target(word):
    """Extract JAL target address."""
    target_idx = word & 0x3FFFFFF
    # Need current PC for JAL target calc
    return None  # caller provides


def follow_jal_chain(data, start_file_off, max_depth=5, max_instr_per_func=512):
    """Follow JAL targets from a starting offset, building a call tree."""
    visited = set()
    results = []

    def walk(file_off, depth, indent):
        if depth > max_depth or file_off in visited:
            return
        visited.add(file_off)

        # Disassemble up to max_instr_per_func instructions from this offset
        end = min(file_off + max_instr_per_func * 4, len(data) - 4)
        off = file_off
        while off < end:
            vaddr, word, mnemonic = disasm_at(data, off)
            print(f'{"  " * indent}0x{vaddr:08X} 0x{off:06X}: 0x{word:08X}  {mnemonic}')

            op = (word >> 26) & 0x3F
            if op == 0x03:  # JAL
                target_idx = word & 0x3FFFFFF
                target_vaddr = (vaddr & 0xF0000000) | (target_idx << 2)
                target_file = target_vaddr - 0x100000 + 0x80
                print(f'{"  " * (indent + 1)}>>> JAL to 0x{target_vaddr:08X} (file 0x{target_file:06X})')
                walk(target_file, depth + 1, indent + 2)
            off += 4

    walk(start_file_off, 0, 0)


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    data = Path(path).read_bytes()

    # CEBZ block reference locations where JAL calls happen nearby
    ref_locations = [
        0x232E74,  # ADDIU $11,$28,0xE628 ; CEBZ block ptr
        0x232E98,  # LW $2,0xE628($28)
        0x232F40,  # ADDIU $11,$28,0xE628
        0x232F64,  # LW $22,0xE628($28)
        0x232FA8,  # LW $2,0xE628($28)
    ]

    for ref_off in ref_locations:
        print(f"\n{'=' * 70}")
        print(f"CEBZ block ref at file 0x{ref_off:06X} (vaddr 0x{0x100000 + (ref_off - 0x80):08X})")
        print(f"{'=' * 70}")
        follow_jal_chain(data, ref_off - 48, max_depth=3, max_instr_per_func=64)
        print()
