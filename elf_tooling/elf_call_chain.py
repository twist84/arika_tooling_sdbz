#!/usr/bin/env python3
"""Trace the complete JAL call chain from CEBZ block references to find .ebz loading logic."""
import struct
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from mips_disasm import decode_instruction


def get_jal_target(word, from_vaddr):
    """Calculate JAL absolute target address."""
    target_idx = word & 0x3FFFFFF
    return (from_vaddr & 0xF0000000) | (target_idx << 2)


def vaddr_to_file(vaddr):
    return vaddr - 0x100000 + 0x80


def trace_call_chain(data, start_vaddr, max_depth=4, visited=None, depth=0, indent=""):
    """Recursively trace JAL calls from a starting vaddr."""
    if visited is None:
        visited = set()
    
    if depth > max_depth or start_vaddr in visited:
        return
    visited.add(start_vaddr)
    
    start_file = vaddr_to_file(start_vaddr)
    
    # Disassemble function from start
    off = start_file
    end = min(start_file + 0x400, len(data) - 4)  # up to 0x400 bytes per function
    
    jal_calls = []
    while off < end:
        word = struct.unpack_from('<I', data, off)[0]
        vaddr = 0x100000 + (off - 0x80)
        mnemonic = decode_instruction(word)
        
        op = (word >> 26) & 0x3F
        if op == 0x03:  # JAL
            target = get_jal_target(word, vaddr)
            jal_calls.append((vaddr, off, word, mnemonic, target))
        off += 4
    
    if jal_calls:
        print(f"\n{indent}[Depth {depth}] Function at vaddr 0x{start_vaddr:08X} (file 0x{start_file:06X}):")
        for vaddr, off, word, mnemonic, target in jal_calls:
            target_file = vaddr_to_file(target)
            print(f"{indent}  0x{vaddr:08X} (file 0x{off:06X}): {mnemonic} -> 0x{target:08X} (file 0x{target_file:06X})")
            
            # Check if target looks like a known function (has prologue)
            if target_file >= 0x80 and target_file < len(data) - 8:
                w1 = struct.unpack_from('<I', data, target_file)[0]
                w2 = struct.unpack_from('<I', data, target_file + 4)[0]
                op1 = (w1 >> 26) & 0x3F
                op2 = (w2 >> 26) & 0x3F
                is_prologue = (op1 == 0x09 and ((w1 >> 16) & 0x1F) == 29 and ((w1 >> 21) & 0x1F) == 29
                               and op2 == 0x2B and ((w2 >> 16) & 0x1F) == 31 and ((w2 >> 21) & 0x1F) == 29)
                if is_prologue:
                    print(f"{indent}    ^ has function prologue")
                    trace_call_chain(data, target, max_depth, visited, depth + 1, indent + "  ")


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    data = Path(path).read_bytes()

    # CEBZ block reference locations where JAL chains start
    start_offsets = [
        (0x232E74, "CEBZ block ref 1 (ADDIU $11,$28,0xE628)"),
        (0x232E98, "CEBZ block ref 2 (LW $2,0xE628($28))"),
        (0x232F40, "CEBZ block ref 3 (ADDIU $11,$28,0xE628)"),
        (0x232F64, "CEBZ block ref 4 (LW $22,0xE628($28))"),
        (0x232FA8, "CEBZ block ref 5 (LW $2,0xE628($28))"),
    ]

    for file_off, label in start_offsets:
        vaddr = 0x100000 + (file_off - 0x80)
        print(f"\n{'=' * 70}")
        print(f"Tracing from {label} at vaddr 0x{vaddr:08X}")
        print(f"{'=' * 70}")
        
        # Find JAL calls near this location
        for back in range(0, 0x100, 4):
            check_off = file_off - back
            if check_off < 0x80:
                break
            word = struct.unpack_from('<I', data, check_off)[0]
            op = (word >> 26) & 0x3F
            if op == 0x03:  # JAL
                check_vaddr = 0x100000 + (check_off - 0x80)
                target = get_jal_target(word, check_vaddr)
                print(f"\nJAL at vaddr 0x{check_vaddr:08X} (file 0x{check_off:06X}): -> 0x{target:08X} (file 0x{vaddr_to_file(target):06X})")
                trace_call_chain(data, target, max_depth=3)
                break
