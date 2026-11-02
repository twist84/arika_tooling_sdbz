#!/usr/bin/env python3
"""Find MIPS function boundaries in PS2 ELF code section.
Detects function prologues (addiu sp,sp,-N + sw ra,N(sp)) and jal targets."""
import struct
from pathlib import Path


def find_prologues(data, code_start_file=0x80, code_end_file=0x400700):
    """find addiu $sp,$sp,-imm followed by sw $ra,imm($sp)"""
    results = []
    for i in range(code_start_file, code_end_file - 8, 4):
        w1 = struct.unpack_from('<I', data, i)[0]
        w2 = struct.unpack_from('<I', data, i + 4)[0]
        op1 = (w1 >> 26) & 0x3F
        op2 = (w2 >> 26) & 0x3F
        if op1 == 0x09:  # addiu
            rs1 = (w1 >> 21) & 0x1F
            rt1 = (w1 >> 16) & 0x1F
            imm1 = w1 & 0xFFFF
            if rs1 == 29 and rt1 == 29 and (imm1 & 0x8000):  # negative immediate
                if op2 == 0x2B:  # sw
                    rs2 = (w2 >> 21) & 0x1F
                    rt2 = (w2 >> 16) & 0x1F
                    imm2 = w2 & 0xFFFF
                    if rs2 == 29 and rt2 == 31:
                        vaddr = 0x100000 + (i - 0x80)
                        frame_size = ((imm1 ^ 0xFFFF) + 1) & 0xFFFF
                        results.append({'vaddr': vaddr, 'file': i, 'frame_size': frame_size, 'ra_offset': imm2})
    return results


def find_jal_targets(data, code_start_file=0x80, code_end_file=0x400700):
    """Find all JAL instructions and their absolute targets."""
    results = []
    for i in range(code_start_file, code_end_file - 4, 4):
        word = struct.unpack_from('<I', data, i)[0]
        op = (word >> 26) & 0x3F
        if op == 0x03:  # JAL
            vaddr = 0x100000 + (i - 0x80)
            target_idx = word & 0x3FFFFFF
            target = (vaddr & 0xF0000000) | (target_idx << 2)
            results.append({'from': vaddr, 'from_file': i, 'to': target})
    return results


def find_jr_ra(data, code_start_file=0x80, code_end_file=0x400700):
    """Find jr $ra (function epilogues/returns)."""
    results = []
    for i in range(code_start_file, code_end_file - 4, 4):
        word = struct.unpack_from('<I', data, i)[0]
        op = (word >> 26) & 0x3F
        if op == 0x00:  # R-type
            funct = word & 0x3F
            rs = (word >> 21) & 0x1F
            rd = (word >> 11) & 0x1F
            if funct == 0x08 and rs == 31 and rd == 0:  # jr $ra
                vaddr = 0x100000 + (i - 0x80)
                results.append({'vaddr': vaddr, 'file': i})
    return results


if __name__ == '__main__':
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'

    data = Path(path).read_bytes()

    prologs = find_prologues(data)
    print(f"=== Function prologues: {len(prologs)} ===\n")
    for p in prologs[:50]:
        print(f"  vaddr 0x{p['vaddr']:08X} (file 0x{p['file']:06X}): frame={p['frame_size']} ra_off=0x{p['ra_offset']:04X}")

    jals = find_jal_targets(data)
    print(f"\n=== JAL instructions: {len(jals)} ===\n")
    for j in jals[:50]:
        print(f"  vaddr 0x{j['from']:08X} -> 0x{j['to']:08X}")

    jrs = find_jr_ra(data)
    print(f"\n=== jr $ra (returns): {len(jrs)} ===\n")
    for j in jrs[:50]:
        print(f"  vaddr 0x{j['vaddr']:08X} (file 0x{j['file']:06X})")
