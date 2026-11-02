#!/usr/bin/env python3
"""Find where stage files reference specific .ebz/effect paths - trace the data flow."""
import struct
import re
from pathlib import Path


def find_string_adjacencies(data, target_strings, window=0x80):
    """Find where target strings appear adjacent to other data in ELF."""
    results = {}
    for target in target_strings:
        results[target] = []
        target_bytes = target.encode('ascii') + b'\x00'
        idx = 0
        while True:
            idx = data.find(target_bytes, idx)
            if idx == -1:
                break
            # Look at surrounding data
            start = max(0x80, idx - window)
            end = min(len(data), idx + len(target_bytes) + window)
            
            # Find other strings in vicinity
            vicinity_strings = []
            i = start
            while i < end:
                if 32 <= data[i] < 127:
                    s_start = i
                    while i < end and 32 <= data[i] < 127:
                        i += 1
                    s = data[s_start:i].decode('ascii')
                    if len(s) >= 3 and s != target:
                        vicinity_strings.append((s_start, s, 0x100000 + (s_start - 0x80)))
                else:
                    i += 1
            
            results[target].append({
                'file_off': idx,
                'vaddr': 0x100000 + (idx - 0x80),
                'vicinity': vicinity_strings,
            })
            idx += 1
    return results


def main():
    path = r'C:\Dev\arika\source_data\SLUS_214.42'
    data = Path(path).read_bytes()

    # Key .ebz/effect paths found in ELF
    targets = [
        'eff/se00/se00028',
        'eff/se00/se00028z',
        'eff/e12/e12274t01',
        'eff/e12/e12274t02',
        'trc/01/efin0001p0101',
    ]

    print("=== String Adjacency Analysis ===\n")
    
    results = find_string_adjacencies(data, targets, window=0x100)
    
    for target, occurrences in results.items():
        print(f"--- {target!r} ({len(occurrences)} occurrence(s)) ---")
        for occ in occurrences:
            print(f"  vaddr 0x{occ['vaddr']:08X} (file 0x{occ['file_off']:06X})")
            if occ['vicinity']:
                print(f"    Nearby strings:")
                for s_off, s, v in occ['vicinity'][:10]:
                    print(f"      {s!r} (vaddr 0x{v:08X})")
        print()


if __name__ == '__main__':
    main()
