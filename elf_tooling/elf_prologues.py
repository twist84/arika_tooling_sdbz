#!/usr/bin/env python3
"""Find function entry points by scanning for common MIPS prologue patterns.
Also identifies potential .ebz loading functions by looking for file I/O patterns."""
import struct
from pathlib import Path


def find_all_prologues(data, code_start_file=0x80, code_end_file=0x400700):
    """Find all function prologues: addiu $sp,$sp,-imm followed by sw $ra,imm($sp)."""
    prologues = []
    i = code_start_file
    while i < code_end_file - 8:
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
                        frame_size = ((imm1 ^ 0xFFFF) + 1) & 0xFFFF
                        vaddr = 0x100000 + (i - 0x80)
                        prologues.append({
                            'vaddr': vaddr,
                            'file': i,
                            'frame_size': frame_size,
                            'ra_offset': imm2,
                        })
                        i += 8  # skip past this prologue
                        continue
        i += 4
    return prologues


def find_file_io_functions(data, code_start_file=0x80, code_end_file=0x400700):
    """Find functions that likely do file I/O by looking for sceIoOpen/sceIoRead patterns."""
    # PS2 SDK file I/O functions typically use specific syscalls or library calls
    # Look for patterns that suggest file operations
    candidates = []
    i = code_start_file
    while i < code_end_file - 16:
        # Look for sequences that load file-related strings
        window = data[i:i+64]
        
        # Check for "open" or file-related string references nearby
        has_file_string = False
        for j in range(max(0x80, i - 0x100), min(len(data), i + 0x100)):
            if data[j:j+5] == b'open\0' or data[j:j+5] == b'.ebz\0':
                has_file_string = True
                break
        
        if has_file_string:
            # Look backward for prologue
            func_start = i
            for back in range(max(0x80, i - 0x200), i, 4):
                w1 = struct.unpack_from('<I', data, back)[0]
                w2 = struct.unpack_from('<I', data, back + 4)[0]
                op1 = (w1 >> 26) & 0x3F
                op2 = (w2 >> 26) & 0x3F
                if op1 == 0x09 and ((w1 >> 16) & 0x1F) == 29 and ((w1 >> 21) & 0x1F) == 29:
                    if op2 == 0x2B and ((w2 >> 16) & 0x1F) == 31 and ((w2 >> 21) & 0x1F) == 29:
                        func_start = back
                        break
            
            vaddr = 0x100000 + (func_start - 0x80)
            candidates.append({'vaddr': vaddr, 'file': func_start, 'near_file_off': i})
            i += 64
            continue
        i += 4
    return candidates


def main():
    path = r'C:\Dev\arika\source_data\SLUS_214.42'
    data = Path(path).read_bytes()

    prologues = find_all_prologues(data)
    print(f"=== Function Prologues Found: {len(prologues)} ===\n")
    
    # Show prologues near CEBZ block references (file 0x232xxx area)
    cebz_area = [p for p in prologues if 0x230000 <= p['file'] <= 0x240000]
    print(f"Prologues near CEBZ code (file 0x230000-0x240000): {len(cebz_area)}")
    for p in cebz_area[:30]:
        print(f"  vaddr 0x{p['vaddr']:08X} (file 0x{p['file']:06X}): frame={p['frame_size']} ra_off=0x{p['ra_offset']:04X}")
    
    print()
    
    # Show prologues near effect name references (file 0x3C4xxx-0x3CAxxx area)
    effect_area = [p for p in prologues if 0x3C0000 <= p['file'] <= 0x3D0000]
    print(f"Prologues near effect data (file 0x3C0000-0x3D0000): {len(effect_area)}")
    for p in effect_area[:30]:
        print(f"  vaddr 0x{p['vaddr']:08X} (file 0x{p['file']:06X}): frame={p['frame_size']} ra_off=0x{p['ra_offset']:04X}")
    
    print()
    
    # Find file I/O candidates
    io_candidates = find_file_io_functions(data)
    print(f"=== File I/O Function Candidates: {len(io_candidates)} ===\n")
    for c in io_candidates[:30]:
        print(f"  vaddr 0x{c['vaddr']:08X} (file 0x{c['file']:06X}): near file ref at 0x{c['near_file_off']:06X}")
