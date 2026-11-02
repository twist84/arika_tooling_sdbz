#!/usr/bin/env python3
"""ELF tooling for .spt script format - trace script loading code."""
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


def trace_spt(data):
    """Trace SPT script format usage in ELF."""
    print("=" * 70)
    print("SPT Script Format - ELF Analysis")
    print("=" * 70)

    # SPT strings from the scan
    spt_strings = [
        ('spt/stg/stg0200.spt', 0x004DB060, 0x00364214),
        ('spt/stg/stg0400.spt', 0x004DB0A0, 0x00364D4C),
        ('spt/stg/stg0600.spt', 0x004DB0E0, 0x00365830),
        ('spt/stg/stg0700.spt', 0x004DB100, 0x00366634),
        ('spt/fgt/def01.spt', 0x004DB180, 0x00370AB0),
        ('spt/fgt/def09.spt', 0x004DB220, 0x00374D70),
        ('spt/fgt/def10.spt', 0x004DB240, 0x00374F78),
        ('spt/fgt/def12.spt', 0x004DB280, 0x00376A90),
        ('spt/fgt/def22.spt', 0x004DB2A0, 0x00376CE8),
        ('spt/fgt/def26.spt', 0x004DB320, 0x0037968C),
        ('spt/fgt/def28.spt', 0x004DB360, 0x0037B504),
        ('spt/fgt/win01.spt', 0x004DB3E0, 0x0037CBEC),
        ('spt/fgt/win03.spt', 0x004DB420, 0x0037D1F4),
        ('spt/fgt/win04.spt', 0x004DB440, 0x0037F2BC),
        ('spt/fgt/win05.spt', 0x004DB460, 0x0037F4C4),
        ('spt/fgt/win11.spt', 0x004DB4C0, 0x00380744),
        ('spt/fgt/win22.spt', 0x004DB500, 0x00380D4C),
        ('spt/fgt/win24.spt', 0x004DB540, 0x003815A8),
        ('spt/fgt/win26.spt', 0x004DB580, 0x0038847C),
        ('spt/fgt/win28.spt', 0x004DB5C0, 0x0038A8B8),
        ('spt/fgt/win29.spt', 0x004DB5E0, 0x00391F74),
        ('spt/stg/tit0100.spt', 0x004DB640, 0x0039D1E0),
        ('spt/stg/tit0200.spt', 0x004DB660, 0x003A2278),
        ('spt/stg/tit0600.spt', 0x004DB6E0, 0x003A389C),
        ('spt/fgt/res00.spt', 0x004DB740, 0x003A38E4),
    ]

    print(f"\n--- SPT script references ({len(spt_strings)} with code refs) ---\n")
    for name, str_vaddr, code_vaddr in spt_strings:
        code_file = vaddr_to_file(code_vaddr)
        str_file = vaddr_to_file(str_vaddr)
        print(f"  {name}")
        print(f"    String at vaddr 0x{str_vaddr:08X} (file 0x{str_file:06X})")
        print(f"    Referenced at vaddr 0x{code_vaddr:08X} (file 0x{code_file:06X})")
        print()

    # Disassemble a few key references
    print("\n--- Disassembly around key SPT references ---\n")
    key_refs = [
        (0x00364214, "stg0200.spt"),
        (0x00364D4C, "stg0400.spt"),
        (0x00370AB0, "def01.spt"),
        (0x003A38E4, "res00.spt"),
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
    trace_spt(data)
