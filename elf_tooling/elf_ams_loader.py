#!/usr/bin/env python3
"""ELF tooling for .ams sound sequence format - trace music loading code."""
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


def trace_ams(data):
    """Trace AMS sound sequence format usage in ELF."""
    print("=" * 70)
    print("AMS Sound Sequence Format - ELF Analysis")
    print("=" * 70)

    # AMS strings with code references from the scan
    ams_strings = [
        ('sqm/sel_in.ams', 0x00499280, 0x00242064),
        ('sqm/sel_lp.ams', 0x004992A4, 0x00245F44),
        ('sqm/st01a_in.ams', 0x00499400, 0x00259E2C),
        ('sqm/st01a_lp.ams', 0x00499424, 0x0025A244),
        ('sqm/st01a_in.ams', 0x00499580, 0x0026EBC4),
        ('sqm/st02a_in.ams', 0x00499700, 0x00287E64),
        ('sqm/st02a_lp.ams', 0x00499724, 0x00289214),
        ('sqm/st03a_in.ams', 0x00499880, 0x002965A8),
        ('sqm/st04a_in.ams', 0x00499B80, 0x002C1E80),
        ('sqm/st09a_in.ams', 0x0049A600, 0x003285F8),
        ('sqm/svival_in.ams', 0x0049AC00, 0x0033D320),
        ('sqm/svival_lp.ams', 0x0049AC24, 0x0033D368),
        ('sqm/end.ams', 0x0049B500, 0x00380D4C),
        ('sqm/shouri.ams', 0x0049B980, 0x003A3A1C),
        ('sqm/menu_lp.ams', 0x0049CA48, 0x003A44A8),
    ]

    print(f"\n--- AMS sequence references ({len(ams_strings)} with code refs) ---\n")
    for name, str_vaddr, code_vaddr in ams_strings:
        str_file = vaddr_to_file(str_vaddr)
        code_file = vaddr_to_file(code_vaddr)
        print(f"  {name}")
        print(f"    String at vaddr 0x{str_vaddr:08X} (file 0x{str_file:06X})")
        print(f"    Referenced at vaddr 0x{code_vaddr:08X} (file 0x{code_file:06X})")
        print()

    # Disassemble a few key references
    print("--- Disassembly around key AMS references ---\n")
    key_refs = [
        (0x00242064, "sel_in.ams"),
        (0x00259E2C, "st01a_in.ams"),
        (0x00287E64, "st02a_in.ams"),
        (0x0033D320, "svival_in.ams"),
        (0x003A3A1C, "shouri.ams"),
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
    trace_ams(data)
