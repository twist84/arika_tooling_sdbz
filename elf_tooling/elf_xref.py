#!/usr/bin/env python3
"""Cross-reference finder for PS2 ELF: find all code references to a target address/vaddr."""
import struct
from pathlib import Path


def find_refs_to_addr(data, target_vaddr, code_start_file=0x80, code_end_file=0x400700):
    """Find all lui/ori/addiu/lw/sw references to target_vaddr in code."""
    target_upper = (target_vaddr >> 16) & 0xFFFF
    target_lower = target_vaddr & 0xFFFF
    results = []

    for i in range(code_start_file, code_end_file - 4, 4):
        word = struct.unpack_from('<I', data, i)[0]
        op = (word >> 26) & 0x3F
        rt = (word >> 16) & 0x1F
        rs = (word >> 21) & 0x1F
        imm = word & 0xFFFF
        vaddr = 0x100000 + (i - 0x80)

        if op == 0x0F:  # lui
            if imm == target_upper:
                # Check next instruction for ori
                if i + 4 < len(data):
                    w2 = struct.unpack_from('<I', data, i + 4)[0]
                    op2 = (w2 >> 26) & 0x3F
                    if op2 == 0x0D:  # ori
                        rt2 = (w2 >> 16) & 0x1F
                        rs2 = (w2 >> 21) & 0x1F
                        imm2 = w2 & 0xFFFF
                        if rt2 == rt and rs2 == rt and imm2 == target_lower:
                            results.append(('lui+ori', vaddr, i, target_vaddr))
        elif op == 0x0D:  # ori (standalone, likely from gp)
            if rs == 28 and imm == target_lower:  # $gp = $28
                results.append(('ori-from-gp', vaddr, i, target_vaddr))
        elif op in (0x23, 0x2B):  # lw/sw
            if rs == 28 and imm == target_lower:  # $gp-relative
                results.append(('gp-relative mem', vaddr, i, target_vaddr))
        elif op == 0x09:  # addiu
            if rs == 28 and imm == target_lower:  # $gp-relative
                results.append(('addiu-from-gp', vaddr, i, target_vaddr))

    return results


def find_jal_targets(data, code_start_file=0x80, code_end_file=0x400700):
    """Find all JAL instructions and their targets."""
    results = []
    for i in range(code_start_file, code_end_file - 4, 4):
        word = struct.unpack_from('<I', data, i)[0]
        op = (word >> 26) & 0x3F
        if op == 0x03:  # JAL
            target = (word & 0x3FFFFFF) << 2
            # JAL target is relative to current PC (4-byte aligned)
            vaddr = 0x100000 + (i - 0x80)
            # MIPS J target: (PC & 0xF0000000) | (target << 2)
            jal_target = (vaddr & 0xF0000000) | target
            results.append((vaddr, i, jal_target))
    return results


def find_function_prologues(data, code_start_file=0x80, code_end_file=0x400700):
    """Find common MIPS function prologues: addiu $sp,$sp,-N ; sw $ra,N($sp)"""
    results = []
    for i in range(code_start_file, code_end_file - 8, 4):
        w1 = struct.unpack_from('<I', data, i)[0]
        w2 = struct.unpack_from('<I', data, i + 4)[0]
        op1 = (w1 >> 26) & 0x3F
        op2 = (w2 >> 26) & 0x3F
        # addiu $sp,$sp,-imm
        if op1 == 0x09:
            rs1 = (w1 >> 21) & 0x1F
            rt1 = (w1 >> 16) & 0x1F
            imm1 = w1 & 0xFFFF
            if rs1 == 29 and rt1 == 29 and imm1 & 0x8000:  # negative
                # sw $ra, imm($sp) follows
                if op2 == 0x2B:
                    rs2 = (w2 >> 21) & 0x1F
                    rt2 = (w2 >> 16) & 0x1F
                    imm2 = w2 & 0xFFFF
                    if rs2 == 29 and rt2 == 31:
                        vaddr = 0x100000 + (i - 0x80)
                        results.append((vaddr, i, imm1, imm2))
    return results


if __name__ == '__main__':
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'

    data = Path(path).read_bytes()

    # Known addresses of interest
    targets = {
        'CEffectMgr': 0x004CA870,
        'CEBZData': 0x004CEF18,
        'CEBZHandle': 0x004CEF30,
        'CEBZBase': 0x004CEF40,
        'CEBZEffectObj': 0x004CEF50,
        'CEBZEffect': 0x004CF030,
        'trc/01/efin0001p0101': 0x004CF0A0,
        'eff/e%c%c/%s': 0x004C3A88,
        'Entry point': 0x00100008,
    }

    print("=== Cross-references to key addresses ===\n")
    for name, target in targets.items():
        refs = find_refs_to_addr(data, target)
        print(f"{name!r} (vaddr 0x{target:08X}): {len(refs)} ref(s)")
        for kind, vaddr, off, _ in refs[:10]:
            print(f"  {kind} at vaddr 0x{vaddr:08X} (file 0x{off:06X})")

    print("\n=== JAL targets (first 30) ===\n")
    jals = find_jal_targets(data)
    print(f"Total JAL instructions: {len(jals)}")
    for vaddr, off, target in jals[:30]:
        print(f"  vaddr 0x{vaddr:08X} (file 0x{off:06X}): JAL 0x{target:08X}")

    print("\n=== Function prologues (first 30) ===\n")
    prologs = find_function_prologues(data)
    print(f"Total prologues found: {len(prologs)}")
    for vaddr, off, imm1, imm2 in prologs[:30]:
        print(f"  vaddr 0x{vaddr:08X} (file 0x{off:06X}): addiu sp,sp,{imm1} sw ra,{imm2}(sp)")
