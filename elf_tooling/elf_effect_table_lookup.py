#!/usr/bin/env python3
"""Analyze the sequential effect name table at ELF file 0x3DB1E9+."""
import struct
from pathlib import Path


def analyze_effect_table(data, start_offset=0x3DB1E9, max_entries=200):
    """Analyze the effect name lookup table."""
    print(f"=== Effect Name Table at file 0x{start_offset:06X} ===\n")
    
    entries = []
    off = start_offset
    for i in range(max_entries):
        if off + 8 > len(data):
            break
        
        # Read 8 bytes: 4-byte value + 4-byte name (efXX\0)
        val = struct.unpack_from('<I', data, off)[0]
        name_bytes = data[off+4:off+8]
        
        # Check if it's an efXX name
        if len(name_bytes) == 4 and name_bytes[0:2] == b'ef' and name_bytes[2:4].isdigit() and name_bytes[3] == 0:
            name = name_bytes.decode('ascii')
            vaddr = 0x100000 + (off - 0x80)
            entries.append({
                'file_off': off,
                'vaddr': vaddr,
                'index_val': val,
                'name': name,
            })
            off += 8
        else:
            # Not an efXX entry, stop
            break
    
    print(f"Found {len(entries)} sequential entries:\n")
    for e in entries:
        print(f"  file 0x{e['file_off']:06X} (v 0x{e['vaddr']:08X}): idx=0x{e['index_val']:08X} ({e['index_val']}) name={e['name']!r}")
    
    # Check if index values are sequential
    if entries:
        idx_vals = [e['index_val'] for e in entries]
        print(f"\nIndex value range: 0x{min(idx_vals):08X} - 0x{max(idx_vals):08X}")
        print(f"Index values sequential: {idx_vals == list(range(idx_vals[0], idx_vals[0] + len(idx_vals)))}")
    
    return entries


def find_nearby_pointers(data, table_start, table_end, window=0x40):
    """Find pointer tables near the effect name table."""
    print(f"\n=== Pointer tables near effect name table ===\n")
    
    # Look before and after the table for arrays of pointers
    search_start = max(0x80, table_start - window)
    search_end = min(len(data) - 4, table_end + window)
    
    # Find sequences of 4-byte values that look like pointers to effect names
    name_vaddrs = set()
    off = table_start
    while off < table_end:
        if off + 8 <= len(data):
            val = struct.unpack_from('<I', data, off)[0]
            name_bytes = data[off+4:off+8]
            if len(name_bytes) == 4 and name_bytes[0:2] == b'ef' and name_bytes[2:4].isdigit() and name_bytes[3] == 0:
                name_vaddrs.add(0x100000 + (off + 4 - 0x80))
        off += 8
    
    # Scan for pointer sequences
    i = search_start
    while i < search_end - 4:
        ptr = struct.unpack_from('<I', data, i)[0]
        if ptr in name_vaddrs:
            # Count consecutive pointers
            count = 0
            j = i
            while j < search_end - 4:
                p = struct.unpack_from('<I', data, j)[0]
                if p in name_vaddrs:
                    count += 1
                    j += 4
                else:
                    break
            if count >= 2:
                vaddr_i = 0x100000 + (i - 0x80)
                print(f"  Pointer table at file 0x{i:06X} (vaddr 0x{vaddr_i:08X}): {count} consecutive pointers to effect names")
                for k in range(min(count, 10)):
                    p = struct.unpack_from('<I', data, i + k * 4)[0]
                    name_off = p - 0x100000 + 0x80
                    if 0 <= name_off < len(data) - 4:
                        name = data[name_off:name_off+4].decode('ascii', errors='replace')
                    else:
                        name = '(invalid)'
                    print(f"    [{k}] ptr=0x{p:08X} -> {name!r}")
            i = j
        else:
            i += 4


if __name__ == '__main__':
    path = r'C:\Dev\arika\source_data\SLUS_214.42'
    data = Path(path).read_bytes()
    
    entries = analyze_effect_table(data)
    find_nearby_pointers(data, 0x3DB1E9, 0x3DB1E9 + len(entries) * 8)
