#!/usr/bin/env python3
"""ELF tooling for .pix/.FPIX texture format - trace loading code."""
import struct
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mips_disasm import decode_instruction, file_to_vaddr, vaddr_to_file


def disasm_range(data, start_file_off, end_file_off):
    """Disassemble a range of file offsets."""
    for off in range(start_file_off, end_file_off, 4):
        if off + 4 > len(data):
            break
        word = struct.unpack_from('<I', data, off)[0]
        vaddr = file_to_vaddr(off)
        mnemonic = decode_instruction(word, vaddr)
        print(f'  0x{vaddr:08X} 0x{off:06X}: 0x{word:08X}  {mnemonic}')


def find_format_string_context(data, format_str, vaddr):
    """Find and disassemble code referencing a format string."""
    # Find lui/ori pair that loads this vaddr
    upper = (vaddr >> 16) & 0xFFFF
    lower = vaddr & 0xFFFF

    print(f"=== {format_str} at vaddr 0x{vaddr:08X} ===\n")

    found = []
    for i in range(0x80, 0x400700 - 4, 4):
        word = struct.unpack_from('<I', data, i)[0]
        op = (word >> 26) & 0x3F
        if op == 0x0F:  # lui
            rt = (word >> 16) & 0x1F
            imm = word & 0xFFFF
            if imm == upper:
                if i + 4 < len(data):
                    w2 = struct.unpack_from('<I', data, i + 4)[0]
                    op2 = (w2 >> 26) & 0x3F
                    if op2 == 0x0D:  # ori
                        rt2 = (w2 >> 16) & 0x1F
                        rs2 = (w2 >> 21) & 0x1F
                        imm2 = w2 & 0xFFFF
                        if rt2 == rt and rs2 == rt and imm2 == lower:
                            found.append((i, file_to_vaddr(i)))

    if not found:
        print("  No lui/ori reference found (may be referenced via other addressing)")
        return

    for off, ref_vaddr in found:
        print(f"  Reference at vaddr 0x{ref_vaddr:08X} (file 0x{off:06X}):")
        # Disassemble surrounding code
        start = max(0x80, off - 64)
        end = min(len(data) - 4, off + 64)
        disasm_range(data, start, end)
        print()


if __name__ == '__main__':
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    data = Path(elf_path).read_bytes()

    # Key format string vaddrs from the scan
    formats = {
        '%s.pix': 0x004CC5B0,
        '%s.pix (2)': 0x004CC5D8,
        '%s.mdl': 0x004CC5A8,
        '%s.pmt': 0x004CC728,
        '%s.cht': 0x004CA6B8,
        '%s.ani': 0x004CFAF0,
        '%s.pas': 0x004CFAC8,
        '%s.ebz': 0x004CEF28,
    }

    for name, vaddr in formats.items():
        find_format_string_context(data, name, vaddr)
