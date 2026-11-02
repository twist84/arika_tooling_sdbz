#!/usr/bin/env python3
"""Find where specific STG effect names (ef00, ef01, etc.) are referenced in the ELF."""
import struct
import sys
from pathlib import Path


def find_effect_name_refs(data, effect_names, code_start_file=0x80, code_end_file=0x400700):
    """Find all occurrences of effect name strings in code section."""
    results = {}
    for name in effect_names:
        results[name] = []
        # Search as null-terminated string
        search = name.encode('ascii') + b'\x00'
        idx = 0
        while True:
            idx = data.find(search, idx)
            if idx == -1 or idx >= code_end_file:
                break
            if idx >= code_start_file:
                vaddr = 0x100000 + (idx - 0x80)
                results[name].append((vaddr, idx))
            idx += 1
    return results


if __name__ == '__main__':
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'

    data = Path(path).read_bytes()

    # Effect names commonly found in STG files
    effect_names = [f'ef{i:02d}' for i in range(40)] + [
        'efkasa', 'efy00', 'eft01', 'eft06', 'efk00', 'efk01', 'efk03',
        'efg00', 'efg01', 'efm00', 'efm01', 'efk04', 'efm02', 'efm03',
        'efk05', 'efb00', 'eft00', 'efk06', 'efk07', 'efk08', 'efk09',
        'efk10', 'efk11', 'efk12', 'efb14', 'efk13', 'efba00',
    ]

    results = find_effect_name_refs(data, effect_names)

    print("=== STG effect name references in ELF ===\n")
    found_any = False
    for name in sorted(results):
        hits = results[name]
        if hits:
            found_any = True
            print(f"{name}: {len(hits)} hit(s)")
            for vaddr, off in hits[:10]:
                print(f"  vaddr 0x{vaddr:08X} (file 0x{off:06X})")
            print()

    if not found_any:
        print("No effect names found as literal strings in ELF code section.")
        print("Effect names are likely constructed at runtime (e.g. sprintf 'ef%02d').")
