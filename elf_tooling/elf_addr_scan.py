#!/usr/bin/env python3
"""Find raw 32-bit address values stored in the ELF code section (pointer tables, vtables, jump tables)."""
import struct
from pathlib import Path
from elf_string_refs import find_refs_to_addr


def find_address_values(data, target_vaddrs, code_start_file=0x80, code_end_file=0x400700):
    """Search code section for 32-bit values matching target vaddrs."""
    results = {}
    for name, target in target_vaddrs.items():
        results[name] = []
        target_bytes = struct.pack('<I', target)
        for i in range(code_start_file, code_end_file - 4, 4):
            if data[i:i+4] == target_bytes:
                vaddr = 0x100000 + (i - 0x80)
                results[name].append((vaddr, i))
    return results


def find_gp_relative_refs(data, target_vaddrs, gp_base=0x00640000, code_start_file=0x80, code_end_file=0x400700):
    """Find $gp-relative references where gp + offset = target_vaddr."""
    results = {}
    for name, target in target_vaddrs.items():
        offset = target - gp_base
        if 0 <= offset < 0x10000:
            results[name] = []
            for i in range(code_start_file, code_end_file - 4, 4):
                word = struct.unpack_from('<I', data, i)[0]
                op = (word >> 26) & 0x3F
                if op in (0x23, 0x2B, 0x09):  # lw, sw, addiu
                    rs = (word >> 21) & 0x1F
                    imm = word & 0xFFFF
                    if rs == 28 and imm == offset:
                        vaddr = 0x100000 + (i - 0x80)
                        results[name].append((vaddr, i, op))
    return results


if __name__ == '__main__':
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'

    data = Path(path).read_bytes()

    targets = {
        'CEffectMgr': 0x004CA870,
        'CEBZData': 0x004CEF18,
        'CEBZHandle': 0x004CEF30,
        'CEBZBase': 0x004CEF40,
        'CEBZEffectObj': 0x004CEF50,
        'CEBZEffect': 0x004CF030,
        'CEBZObject': 0x004C3C08,
        'trc/01/efin0001p0101': 0x004CF0A0,
        'eff/e%c%c/%s': 0x004C3A88,
        '%s.ebz': 0x004CEF28,
    }

    print("=== Raw 32-bit address values in code section ===\n")
    addr_results = find_address_values(data, targets)
    for name, hits in addr_results.items():
        print(f"{name!r} (0x{targets[name]:08X}): {len(hits)} hit(s)")
        for vaddr, off in hits[:10]:
            print(f"  vaddr 0x{vaddr:08X} (file 0x{off:06X})")

    print("\n=== $gp-relative references (gp=0x00640000) ===\n")
    gp_results = find_gp_relative_refs(data, targets)
    for name, hits in gp_results.items():
        if hits:
            print(f"{name!r} (0x{targets[name]:08X}): {len(hits)} hit(s)")
            for vaddr, off, op in hits[:10]:
                opname = {0x23: 'lw', 0x2B: 'sw', 0x09: 'addiu'}[op]
                print(f"  {opname} at vaddr 0x{vaddr:08X} (file 0x{off:06X})")
