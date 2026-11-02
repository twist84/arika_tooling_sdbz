#!/usr/bin/env python3
"""Map all ELF string addresses to their code references (lui+ori, gp-relative, pointer tables)."""
import struct
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from elf_string_refs import find_refs_to_addr


def extract_strings(data, min_len=4):
    strings = []
    i = 0x80
    while i < len(data):
        b = data[i]
        if 32 <= b < 127:
            start = i
            while i < len(data) and 32 <= data[i] < 127:
                i += 1
            if i - start >= min_len:
                strings.append((start, data[start:i].decode('ascii')))
        else:
            i += 1
    return strings


def map_string_refs(data, filter_substrings=None):
    """Build map of string -> vaddr -> code references."""
    strings = extract_strings(data)
    
    if filter_substrings:
        strings = [(o, s) for o, s in strings
                   if any(sub in s for sub in filter_substrings)]
    
    results = {}
    for off, s in strings:
        vaddr = 0x100000 + (off - 0x80)
        refs = find_refs_to_addr(data, vaddr)
        results[s] = {'file_off': off, 'vaddr': vaddr, 'refs': refs}
    
    return results


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    filters = sys.argv[2:] if len(sys.argv) > 2 else None
    
    data = Path(path).read_bytes()
    results = map_string_refs(data, filters)
    
    total_refs = sum(len(r['refs']) for r in results.values())
    print(f"=== String-to-code reference map ({len(results)} strings, {total_refs} refs) ===\n")
    
    for s, info in sorted(results.items(), key=lambda x: len(x[1]['refs']), reverse=True):
        vaddr = info['vaddr']
        refs = info['refs']
        print(f"{s!r} (vaddr 0x{vaddr:08X}, file 0x{info['file_off']:06X}): {len(refs)} ref(s)")
        for kind, ref_vaddr, off, _ in refs[:8]:
            print(f"  {kind} at vaddr 0x{ref_vaddr:08X} (file 0x{off:06X})")
        print()
