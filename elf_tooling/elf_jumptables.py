#!/usr/bin/env python3
"""Find jump tables / switch statements in PS2 ELF code section.

Looks for sequences of lw $t, imm($gp) or lui/ori pairs that form
indirect jump targets (jr $reg after loading from table)."""
import struct
from pathlib import Path


def find_lw_gp_sequences(data, code_start_file=0x80, code_end_file=0x400700):
    """Find lw $rt, imm($gp) instructions - potential jump table lookups."""
    results = []
    for i in range(code_start_file, code_end_file - 4, 4):
        word = struct.unpack_from('<I', data, i)[0]
        op = (word >> 26) & 0x3F
        if op == 0x23:  # lw
            rs = (word >> 21) & 0x1F
            rt = (word >> 16) & 0x1F
            imm = word & 0xFFFF
            if rs == 28:  # $gp
                vaddr = 0x100000 + (i - 0x80)
                results.append({'vaddr': vaddr, 'file': i, 'rt': rt, 'imm': imm})
    return results


def find_jr_instructions(data, code_start_file=0x80, code_end_file=0x400700):
    """Find jr instructions - potential indirect jumps from jump tables."""
    results = []
    for i in range(code_start_file, code_end_file - 4, 4):
        word = struct.unpack_from('<I', data, i)[0]
        op = (word >> 26) & 0x3F
        if op == 0x00:  # R-type
            funct = word & 0x3F
            rs = (word >> 21) & 0x1F
            rd = (word >> 11) & 0x1F
            if funct == 0x08:  # jr
                vaddr = 0x100000 + (i - 0x80)
                results.append({'vaddr': vaddr, 'file': i, 'rs': rs})
    return results


def find_switch_patterns(data, code_start_file=0x80, code_end_file=0x400700):
    """Find potential switch statements: lw from gp + jr sequence."""
    lw_results = find_lw_gp_sequences(data, code_start_file, code_end_file)
    jr_results = find_jr_instructions(data, code_start_file, code_end_file)
    
    switches = []
    for lw in lw_results:
        # Look for jr within 8 instructions after lw
        for jr in jr_results:
            if lw['file'] < jr['file'] <= lw['file'] + 32:
                switches.append({
                    'lw_vaddr': lw['vaddr'],
                    'lw_file': lw['file'],
                    'jr_vaddr': jr['vaddr'],
                    'jr_file': jr['file'],
                    'distance': jr['file'] - lw['file'],
                })
                break
    
    return switches


if __name__ == '__main__':
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    
    data = Path(path).read_bytes()
    
    lw_results = find_lw_gp_sequences(data)
    print(f"=== lw $rt, imm($gp) instructions: {len(lw_results)} ===\n")
    for lw in lw_results[:50]:
        print(f"  vaddr 0x{lw['vaddr']:08X} (file 0x{lw['file']:06X}): lw ${lw['rt']}, 0x{lw['imm']:04X}($gp)")
    
    jr_results = find_jr_instructions(data)
    print(f"\n=== jr instructions: {len(jr_results)} ===\n")
    for jr in jr_results[:50]:
        print(f"  vaddr 0x{jr['vaddr']:08X} (file 0x{jr['file']:06X}): jr ${jr['rs']}")
    
    switches = find_switch_patterns(data)
    print(f"\n=== Potential switch patterns: {len(switches)} ===\n")
    for s in switches[:30]:
        print(f"  lw at 0x{s['lw_vaddr']:08X} -> jr at 0x{s['jr_vaddr']:08X} (dist={s['distance']})")
