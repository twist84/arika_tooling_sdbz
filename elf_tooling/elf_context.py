#!/usr/bin/env python3>
"""Examine context around specific file offsets in the ELF (hex + disassembly)."""
import struct
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mips_disasm import decode_instruction


def hex_dump(data, start, length=128):
    """Hex dump with ASCII."""
    for off in range(start, min(start + length, len(data)), 16):
        chunk = data[off:off+16]
        hexs = ' '.join(f'{b:02X}' for b in chunk)
        asc = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        vaddr = 0x100000 + (off - 0x80)
        print(f'  0x{off:06X} (v 0x{vaddr:08X}): {hexs:<48} {asc}')


def disasm_around(data, file_off, before=16, after=16):
    """Disassemble instructions around a file offset."""
    start = max(0x80, file_off - before * 4)
    end = min(len(data) - 4, file_off + after * 4)
    print(f"\n  Disassembly around file 0x{file_off:06X}:")
    for off in range(start, end, 4):
        word = struct.unpack_from('<I', data, off)[0]
        vaddr = 0x100000 + (off - 0x80)
        mark = ' <<<' if off == file_off else ''
        mnemonic = decode_instruction(word)
        print(f'  0x{vaddr:08X} 0x{off:06X}: 0x{word:08X}  {mnemonic}{mark}')


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    offsets = [int(x, 0) for x in sys.argv[2:]] if len(sys.argv) > 2 else []

    data = Path(path).read_bytes()

    for off in offsets:
        print(f"\n=== Context at file 0x{off:06X} (vaddr 0x{0x100000 + (off - 0x80):08X}) ===")
        hex_dump(data, off, 64)
        disasm_around(data, off)
