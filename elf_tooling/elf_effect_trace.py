#!/usr/bin/env python3
"""
ELF tooling: Deep trace of STG efXX -> .ebz file mapping.

Focuses on:
1. How effect name references (raw addresses in code) are used to load .ebz files
2. CEBZ entry processing per-effect (the loop at 0x00330200-0x00330260)
3. JAL target analysis for code called from CEBZ loading
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


def find_jals_in_range(data, start_off, end_off):
    jals = []
    for off in range(start_off, end_off - 4, 4):
        word = struct.unpack_from('<I', data, off)[0]
        op = (word >> 26) & 0x3F
        if op == 0x03:
            target = word & 0x3FFFFFF
            vaddr = file_to_vaddr(off)
            target_vaddr = (vaddr & 0xF0000000) | (target << 2)
            file_tgt = vaddr_to_file(target_vaddr)
            jals.append((vaddr, off, target_vaddr, file_tgt))
    return jals


def trace_effect_name_refs(data):
    """
    Disassemble code at each effect name raw reference address
    to understand how names are used to construct .ebz file paths.
    """
    print("=" * 70)
    print("EFFECT NAME -> .ebz FILE PATH TRACE")
    print("=" * 70)
    
    # Effect name addresses and their raw refs
    refs = {
        0x004C4E60: [(0x00488B64, 0x388BE4), (0x00488B6C, 0x388BEC)],  # ef00 "k7"
        0x004C4E68: [(0x00488B68, 0x388BE8)],                            # ef01 "k8"
        0x004C4E70: [(0x004FC398, 0x3FC418)],                            # ef02 "02Sp"
        0x004C4E90: [(0x004FC39C, 0x3FC41C)],                            # ef06 "02St"
        0x004C4EB0: [(0x004FC3A0, 0x3FC420)],                            # ef10 "02St"
        0x004C4ED0: [(0x004FC3A8, 0x3FC428)],                            # ef14 "Func02"
        0x004C4EF0: [(0x004FC3AC, 0x3FC42C)],                            # ef18 "02Ta"
        0x004C4F08: [(0x00488C00, 0x388C80)],                            # ef21 "xi07"
        0x004C4F18: [(0x00488C04, 0x388C84)],                            # ef23 "xi04"
        0x004C4F28: [(0x00488C08, 0x388C88)],                            # ef25 "xi08"
        0x004C4F38: [(0x00488C0C, 0x388C8C)],                            # ef27 "xi03"
        0x004C4F48: [(0x00488C10, 0x388C90), (0x00488C18, 0x388C98)],   # ef29 "xi05"
        0x004C4F58: [(0x00488C14, 0x388C94), (0x00488C1C, 0x388C9C)],   # ef31 "xi06"
        0x004C4F70: [(0x004FC3B0, 0x3FC430)],                            # ef34 "02Te"
        0x004C4F90: [(0x00488CA0, 0x388D20)],                            # ef38 "lbox"
    }
    
    for name_addr, refs in refs.items():
        vaddr = file_to_vaddr(name_addr)
        name_bytes = data[name_addr+4:name_addr+8]
        name_str = name_bytes.decode('ascii', errors='replace')
        print(f"\n{'='*70}")
        print(f"Effect name '{name_str}' at vaddr 0x{vaddr:08X} (file 0x{name_addr:06X})")
        print("=" * 70)
        
        for ref_vaddr, ref_off in refs:
            print(f"\n  Code reference at vaddr 0x{ref_vaddr:08X} (file 0x{ref_off:06X}):")
            # Disassemble surrounding code (before and after)
            start_off = max(ref_off - 32, 0x80)
            end_off = min(ref_off + 32, len(data) - 4)
            lines = disasm_range(data, start_off, end_off, max_lines=16)
            for line in lines:
                print(line)
            print()


def trace_cebz_entry_processing(data):
    """
    Disassemble the CEBZ entry processing loop in detail.
    The code at 0x00330200-0x00330260 iterates through entries.
    """
    print("\n" + "=" * 70)
    print("CEBZ ENTRY PROCESSING LOOP (detailed)")
    print("=" * 70)
    
    # The main loop body at 0x00330200-0x00330260
    start_off = vaddr_to_file(0x00330200)
    end_off = vaddr_to_file(0x00330268)
    print(f"\n--- CEBZ entry loop (vaddr 0x00330200-0x00330268) ---")
    lines = disasm_range(data, start_off, end_off, max_lines=26)
    for line in lines:
        print(line)
    
    # Analyze the JAL targets called in this loop
    print(f"\n--- JAL targets called from entry loop ---")
    jal_targets = find_jals_in_range(data, start_off, end_off)
    for vaddr, off, target_vaddr, file_tgt in jal_targets:
        print(f"  JAL at vaddr 0x{vaddr:08X} (file 0x{off:06X}) -> target vaddr 0x{target_vaddr:08X} (file 0x{file_tgt:06X})")
    
    # Disassemble the two JAL targets in more detail
    print(f"\n--- JAL target 0x00191EF8 (string hash function) ---")
    start_off = vaddr_to_file(0x00191EF8)
    lines = disasm_range(data, start_off, min(start_off + 64, len(data) - 4), max_lines=16)
    for line in lines:
        print(line)
    
    print(f"\n--- JAL target 0x00191638 (data unpacker) ---")
    start_off = vaddr_to_file(0x00191638)
    lines = disasm_range(data, start_off, min(start_off + 96, len(data) - 4), max_lines=24)
    for line in lines:
        print(line)


def main():
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    data = Path(elf_path).read_bytes()
    
    trace_effect_name_refs(data)
    trace_cebz_entry_processing(data)


if __name__ == '__main__':
    main()
