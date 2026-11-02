#!/usr/bin/env python3
"""Examine code around CEBZ class info block references to understand .ebz loading."""
import struct
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mips_disasm import decode_instruction


def disasm_range(data, start_file_off, end_file_off):
    """Disassemble a range of file offsets."""
    for off in range(start_file_off, end_file_off, 4):
        if off + 4 > len(data):
            break
        word = struct.unpack_from('<I', data, off)[0]
        vaddr = 0x100000 + (off - 0x80)
        mnemonic = decode_instruction(word)
        print(f'  0x{vaddr:08X} 0x{off:06X}: 0x{word:08X}  {mnemonic}')


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'

    data = Path(path).read_bytes()

    # CEBZ block reference locations
    ref_locations = [
        0x232E74, 0x232E98, 0x232F40, 0x232F64, 0x232FA8,
    ]

    for ref_off in ref_locations:
        print(f"\n=== Code around CEBZ block ref at file 0x{ref_off:06X} ===")
        start = max(0x80, ref_off - 64)
        end = min(len(data) - 4, ref_off + 64)
        disasm_range(data, start, end)
