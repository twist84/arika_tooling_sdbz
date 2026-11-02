#!/usr/bin/env python3
"""Disassemble specific function ranges around key CEBZ/trc/eff addresses."""
import struct
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mips_disasm import decode_instruction


def disasm_range(data, start_file_off, end_file_off, show_bytes=True):
    """Disassemble a range of file offsets."""
    for off in range(start_file_off, end_file_off, 4):
        if off + 4 > len(data):
            break
        word = struct.unpack_from('<I', data, off)[0]
        vaddr = 0x100000 + (off - 0x80)
        mnemonic = decode_instruction(word)
        byte_str = f'0x{word:08X}' if show_bytes else ''
        print(f'  0x{vaddr:08X} 0x{off:06X}: {byte_str:>10}  {mnemonic}')


def find_function_bounds(data, start_file_off, search_back=0x200, search_forward=0x400):
    """Find function bounds around a given offset by looking for prologue patterns."""
    # Search backward for addiu $sp,$sp,-N followed by sw $ra,N($sp)
    func_start = start_file_off
    for off in range(max(0x80, start_file_off - search_back), start_file_off, 4):
        w1 = struct.unpack_from('<I', data, off)[0]
        w2 = struct.unpack_from('<I', data, off + 4)[0]
        op1 = (w1 >> 26) & 0x3F
        op2 = (w2 >> 26) & 0x3F
        if op1 == 0x09:  # addiu
            rs1 = (w1 >> 21) & 0x1F
            rt1 = (w1 >> 16) & 0x1F
            imm1 = w1 & 0xFFFF
            if rs1 == 29 and rt1 == 29 and (imm1 & 0x8000):
                if op2 == 0x2B:  # sw
                    rs2 = (w2 >> 21) & 0x1F
                    rt2 = (w2 >> 16) & 0x1F
                    if rs2 == 29 and rt2 == 31:
                        func_start = off
                        break

    # Search forward for jr $ra
    func_end = start_file_off + search_forward
    for off in range(start_file_off, min(start_file_off + search_forward, len(data) - 4), 4):
        word = struct.unpack_from('<I', data, off)[0]
        op = (word >> 26) & 0x3F
        if op == 0x00:
            funct = word & 0x3F
            rs = (word >> 21) & 0x1F
            if funct == 0x08 and rs == 31:
                func_end = off + 4
                break

    return func_start, func_end


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'

    data = Path(path).read_bytes()

    # Key addresses to disassemble around
    targets = [
        # CEBZ block reference code
        (0x232E74, "CEBZ block ref 1"),
        (0x232E98, "CEBZ block ref 2"),
        (0x232F40, "CEBZ block ref 3"),
        (0x232F64, "CEBZ block ref 4"),
        (0x232FA8, "CEBZ block ref 5"),
        # JAL targets found in CEBZ code
        (0x333CF0, "JAL 0x333CF0 (CEBZ init?)"),
        (0x333A10, "JAL 0x333A10 (helper)"),
        (0x333C20, "JAL 0x333C20"),
        (0x3301A0, "JAL 0x3301A0"),
        (0x3301E0, "JAL 0x3301E0"),
        # trc table code
        (0x3ACEE0, "trc path table start"),
    ]

    for target_off, label in targets:
        print(f"\n{'=' * 70}")
        print(f"{label} at file 0x{target_off:06X} (vaddr 0x{0x100000 + (target_off - 0x80):08X})")
        print(f"{'=' * 70}")

        func_start, func_end = find_function_bounds(data, target_off)
        print(f"Function bounds: file 0x{func_start:06X} - 0x{func_end:06X} ({func_end - func_start} bytes)")
        disasm_range(data, func_start, func_end)
        print()
