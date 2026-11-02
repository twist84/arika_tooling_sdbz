#!/usr/bin/env python3
"""Search PS2 ELF code section for MIPS lui/ori pairs that load string addresses."""
import struct
from pathlib import Path


def find_string_refs(path, strings):
    data = Path(path).read_bytes()
    _find_refs_to_addr_impl(data, strings)


def find_refs_to_addr(data, target_vaddr, code_start_file=0x80, code_end_file=0x400700):
    """Find all code references to target_vaddr (lui+ori, ori-from-gp, gp-relative mem)."""
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
                if i + 4 < len(data):
                    w2 = struct.unpack_from('<I', data, i + 4)[0]
                    op2 = (w2 >> 26) & 0x3F
                    if op2 == 0x0D:  # ori
                        rt2 = (w2 >> 16) & 0x1F
                        rs2 = (w2 >> 21) & 0x1F
                        imm2 = w2 & 0xFFFF
                        if rt2 == rt and rs2 == rt and imm2 == target_lower:
                            results.append(('lui+ori', vaddr, i, target_vaddr))
        elif op == 0x0D:  # ori
            if rs == 28 and imm == target_lower:
                results.append(('ori-from-gp', vaddr, i, target_vaddr))
        elif op in (0x23, 0x2B):  # lw/sw
            if rs == 28 and imm == target_lower:
                results.append(('gp-relative mem', vaddr, i, target_vaddr))
        elif op == 0x09:  # addiu
            if rs == 28 and imm == target_lower:
                results.append(('addiu-from-gp', vaddr, i, target_vaddr))

    return results


def _find_refs_to_addr_impl(data, strings):
    for name, vaddr in strings.items():
        refs = find_refs_to_addr(data, vaddr)
        print(f"\n{name!r} (vaddr 0x{vaddr:08X}): {len(refs)} ref(s)")
        for kind, ref_vaddr, off, _ in refs[:10]:
            print(f"  {kind} at vaddr 0x{ref_vaddr:08X} (file 0x{off:06X})")


if __name__ == '__main__':
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'

    # Known EBZ/effect-related string vaddrs (from ELF data section)
    strings = {
        'eff/e%c%c/%s': 0x004C3A88,
        'CEffectMgr': 0x004CA870,
        'CEBZData': 0x004CEF18,
        'CEBZHandle': 0x004CEF30,
        'CEBZBase': 0x004CEF40,
        'CEBZEffectObj': 0x004CEF50,
        'CEBZEffect': 0x004CF030,
        'trc/01/efin0001p0101': 0x004CF0A0,
    }

    find_string_refs(path, strings)
