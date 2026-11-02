#!/usr/bin/env python3
"""
ELF tooling: Consolidated symbol cross-reference map for PS2 ELF.

For each known symbol (string, structure, function, entry point), finds all
code references using every addressing mode:
  * lui + ori pair (absolute address construction)
  * ori / addiu / lw / sw from $gp (gp-relative)
  * raw 32-bit value stored in code (pointer tables / vtables)
  * JAL target (direct calls to functions)

Produces a single sorted, annotated map usable as a master index for the ELF.
"""
import struct
import sys
from pathlib import Path


def file_to_vaddr(file_off):
    return 0x100000 + (file_off - 0x80)


def vaddr_to_file(vaddr):
    return vaddr - 0x100000 + 0x80


def sign16(n):
    return n - 0x10000 if n & 0x8000 else n


def find_refs_to_addr(data, target_vaddr, gp_base=None,
                      code_start_file=0x80, code_end_file=0x400700):
    """Find all code references to target_vaddr across addressing modes."""
    target_upper = (target_vaddr >> 16) & 0xFFFF
    target_lower = target_vaddr & 0xFFFF
    results = []

    for i in range(code_start_file, code_end_file - 4, 4):
        word = struct.unpack_from('<I', data, i)[0]
        op = (word >> 26) & 0x3F
        rt = (word >> 16) & 0x1F
        rs = (word >> 21) & 0x1F
        imm = word & 0xFFFF
        imm_signed = sign16(imm)
        vaddr = file_to_vaddr(i)

        if op == 0x0F:  # lui
            if imm == target_upper and i + 4 < len(data):
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
            elif gp_base is not None:
                # ori $rt, $gp, imm where gp + imm = target
                if (gp_base + imm_signed) & 0xFFFFFFFF == target_vaddr:
                    results.append(('ori-from-gp+', vaddr, i, target_vaddr))
        elif op in (0x23, 0x2B):  # lw / sw
            if rs == 28 and imm == target_lower:
                results.append(('gp-mem', vaddr, i, target_vaddr))
            elif gp_base is not None and rs == 28:
                if (gp_base + imm_signed) & 0xFFFFFFFF == target_vaddr:
                    kind = 'lw' if op == 0x23 else 'sw'
                    results.append((f'{kind}-from-gp+', vaddr, i, target_vaddr))
        elif op == 0x09:  # addiu
            if rs == 28 and imm == target_lower:
                results.append(('addiu-from-gp', vaddr, i, target_vaddr))
            elif gp_base is not None and rs == 28:
                if (gp_base + imm_signed) & 0xFFFFFFFF == target_vaddr:
                    results.append(('addiu-from-gp+', vaddr, i, target_vaddr))

    return results


def find_raw_value_hits(data, target_vaddr,
                        code_start_file=0x80, code_end_file=0x400700):
    """Find raw 32-bit little-endian copies of target_vaddr in code section."""
    target_bytes = struct.pack('<I', target_vaddr)
    results = []
    for i in range(code_start_file, code_end_file - 4, 4):
        if data[i:i + 4] == target_bytes:
            results.append((file_to_vaddr(i), i))
    return results


def find_jal_targets(data, target_vaddr,
                     code_start_file=0x80, code_end_file=0x400700):
    """Find all JAL instructions whose absolute target is target_vaddr."""
    results = []
    for i in range(code_start_file, code_end_file - 4, 4):
        word = struct.unpack_from('<I', data, i)[0]
        op = (word >> 26) & 0x3F
        if op == 0x03:  # JAL
            from_vaddr = file_to_vaddr(i)
            target_idx = word & 0x3FFFFFF
            target = (from_vaddr & 0xF0000000) | (target_idx << 2)
            if target == target_vaddr:
                results.append((from_vaddr, i))
    return results


def collect_all_refs(data, symbol, vaddr, gp_base=None):
    """Gather every reference kind for one symbol."""
    refs = []
    for kind, rv, off, _ in find_refs_to_addr(data, vaddr, gp_base):
        refs.append((kind, rv, off))
    for rv, off in find_raw_value_hits(data, vaddr):
        refs.append(('raw-value', rv, off))
    # JAL targets only meaningful for code addresses; include for all
    for fv, off in find_jal_targets(data, vaddr):
        refs.append(('jal-target', fv, off))
    refs.sort(key=lambda r: r[2])
    return refs


def main():
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    data = Path(elf_path).read_bytes()

    # gp_base from elf_addr_scan convention (0x00640000); set None to skip gp+ mode
    gp_base = 0x00640000

    # Known symbols: name -> (vaddr, description, category)
    symbols = [
        # Entry / startup
        ('Entry point', 0x00100008, 'ELF entry point', 'code'),
        # CEBZ / effect class globals
        ('CEffectMgr', 0x004CA870, 'Effect manager singleton', 'data'),
        ('CEBZData', 0x004CEF18, 'CEBZData global', 'data'),
        ('CEBZHandle', 0x004CEF30, 'CEBZHandle global', 'data'),
        ('CEBZBase', 0x004CEF40, 'CEBZBase global', 'data'),
        ('CEBZEffectObj', 0x004CEF50, 'CEBZEffectObj global', 'data'),
        ('CEBZEffect', 0x004CF030, 'CEBZEffect global', 'data'),
        ('CEBZObject', 0x004C3C08, 'CEBZObject global', 'data'),
        # Format strings
        ('%s.ebz', 0x004CEF28, 'EBZ file path format string', 'string'),
        ('eff/e%c%c/%s', 0x004C3A88, 'Effect archive path format string', 'string'),
        ('trc/01/efin0001p0101', 0x004CF0A0, 'Trajectory effect path string', 'string'),
        # CEBZ block info
        ('CEBZ block 0x3FE6A8', 0x003FE6A8, 'CEBZ class info block (file 0x3FE6A8)', 'data'),
    ]

    print("=" * 72)
    print("ELF SYMBOL CROSS-REFERENCE MAP")
    print("=" * 72)
    print(f"ELF: {elf_path}  (gp_base = {hex(gp_base) if gp_base else 'N/A'})")
    print()

    total_refs = 0
    for name, vaddr, desc, category in symbols:
        refs = collect_all_refs(data, name, vaddr, gp_base)
        total_refs += len(refs)
        vaddr_str = f"0x{vaddr:08X}"
        print(f"{name:<24} {vaddr_str:<10} [{category:<5}] {desc}")
        print(f"{'':<24} {'':<10}  {len(refs)} reference(s)")
        for kind, rv, off in refs[:12]:
            kind_label = kind
            if kind == 'jal-target':
                print(f"    {kind_label:<14} called from vaddr 0x{rv:08X} (file 0x{off:06X})")
            else:
                print(f"    {kind_label:<14} at vaddr 0x{rv:08X} (file 0x{off:06X})")
        if len(refs) > 12:
            print(f"    ... and {len(refs) - 12} more")
        print()

    print(f"Total references across {len(symbols)} symbols: {total_refs}")


if __name__ == '__main__':
    main()
