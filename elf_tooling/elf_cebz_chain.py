#!/usr/bin/env python3
"""
ELF tooling: Deep disassembly of CEBZ effect loading JAL targets.

Disassembles the functions called from CEBZ loading code
to understand how .ebz files are actually loaded at runtime.
"""
import struct
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mips_disasm import decode_instruction


def file_to_vaddr(file_off):
    return 0x100000 + (file_off - 0x80)


def vaddr_to_file(vaddr):
    return vaddr - 0x100000 + 0x80


def disasm_range(data, start_file_off, end_file_off, max_lines=200):
    """Disassemble a range of file offsets."""
    lines = []
    off = start_file_off
    count = 0
    while off < len(data) - 4 and count < max_lines:
        word = struct.unpack_from('<I', data, off)[0]
        vaddr = file_to_vaddr(off)
        info = decode_instruction(word, vaddr)
        mnemonic = info.get('mnemonic', f'unk_op_0x{word>>26:02X} 0x{word:08X}')
        lines.append(f'  0x{vaddr:08X} 0x{off:06X}: 0x{word:08X}  {mnemonic}')
        off += 4
        count += 1
    return lines


def find_jal_targets_in_range(data, start_off, end_off):
    """Find all JAL targets in a code range."""
    targets = []
    off = start_off
    while off < end_off - 4:
        word = struct.unpack_from('<I', data, off)[0]
        op = (word >> 26) & 0x3F
        if op == 0x03:  # JAL
            target = word & 0x3FFFFFF
            vaddr = file_to_vaddr(off)
            target_vaddr = (vaddr & 0xF0000000) | (target << 2)
            targets.append((vaddr, off, target_vaddr, vaddr_to_file(target_vaddr)))
        off += 4
    return targets


def trace_jal_target(data, vaddr, label, max_instructions=80):
    """Disassemble a JAL target function."""
    file_off = vaddr_to_file(vaddr)
    print(f"\n{'='*70}")
    print(f"{label}: vaddr 0x{vaddr:08X} (file 0x{file_off:06X})")
    print("=" * 70)
    
    lines = disasm_range(data, file_off, min(file_off + max_instructions * 4, len(data) - 4), max_lines=max_instructions)
    for line in lines:
        print(line)


def main():
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    data = Path(elf_path).read_bytes()

    print("=" * 70)
    print("CEBZ LOADING CODE - JAL TARGET ANALYSIS")
    print("=" * 70)

    # The CEBZ loading code at 0x003301E0-0x00330300 calls:
    targets = [
        (0x00191EF8, "JAL target #1 (called from 0x0033022C)"),
        (0x00191638, "JAL target #2 (called from 0x00330238)"),
    ]

    for vaddr, label in targets:
        trace_jal_target(data, vaddr, label, max_instructions=64)

    # Also analyze what functions 0x00191EF8 and 0x00191638 call
    print("\n" + "=" * 70)
    print("SECOND-LEVEL CALL ANALYSIS")
    print("=" * 70)

    # Disassemble 0x00191EF8 to find its JAL targets
    print(f"\n--- JAL targets in 0x00191EF8 ---")
    start_off = vaddr_to_file(0x00191EF8)
    end_off = min(start_off + 128, len(data) - 4)
    jal_targets = []
    for off in range(start_off, end_off, 4):
        word = struct.unpack_from('<I', data, off)[0]
        op = (word >> 26) & 0x3F
        if op == 0x03:
            target = word & 0x3FFFFFF
            vaddr = file_to_vaddr(off)
            target_vaddr = (vaddr & 0xF0000000) | (target << 2)
            jal_targets.append((vaddr, off, target_vaddr, vaddr_to_file(target_vaddr)))
    
    for vaddr, off, target_vaddr, file_tgt in jal_targets:
        print(f"  JAL at vaddr 0x{vaddr:08X} (file 0x{off:06X}) -> 0x{target_vaddr:08X} (file 0x{file_tgt:06X})")

    # Disassemble 0x00191638 to find its JAL targets
    print(f"\n--- JAL targets in 0x00191638 ---")
    start_off = vaddr_to_file(0x00191638)
    end_off = min(start_off + 128, len(data) - 4)
    jal_targets = []
    for off in range(start_off, end_off, 4):
        word = struct.unpack_from('<I', data, off)[0]
        op = (word >> 26) & 0x3F
        if op == 0x03:
            target = word & 0x3FFFFFF
            vaddr = file_to_vaddr(off)
            target_vaddr = (vaddr & 0xF0000000) | (target << 2)
            jal_targets.append((vaddr, off, target_vaddr, vaddr_to_file(target_vaddr)))
    
    for vaddr, off, target_vaddr, file_tgt in jal_targets:
        print(f"  JAL at vaddr 0x{vaddr:08X} (file 0x{off:06X}) -> 0x{target_vaddr:08X} (file 0x{file_tgt:06X})")


if __name__ == '__main__':
    main()
