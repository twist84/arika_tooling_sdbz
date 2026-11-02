#!/usr/bin/env python3
"""Extract effect name tables from ELF data section.
Pattern: 4-byte index + 'efXX\0\0' + '_2itiefXX\0' (or similar associated names)."""
import struct
import sys
from pathlib import Path


def extract_effect_tables(data):
    """Find all effect name table entries in ELF data section."""
    entries = []
    i = 0x80
    while i < len(data) - 8:
        # Look for 'efXX' followed by at least one null byte
        if data[i:i+2] == b'ef' and data[i+2:i+4].isdigit():
            # Check if followed by null(s)
            null_count = 0
            j = i + 4
            while j < len(data) and data[j] == 0:
                null_count += 1
                j += 1
            if null_count >= 1:
                name = data[i:i+4].decode('ascii')
                vaddr = 0x100000 + (i - 0x80)
                
                # Check for 4-byte index before the name
                idx_val = 0
                if i >= 4:
                    idx_val = struct.unpack_from('<I', data, i - 4)[0]
                
                # Look for associated data after the nulls
                assoc = b''
                k = j
                while k < len(data) and (32 <= data[k] < 127 or data[k] == 0):
                    assoc += bytes([data[k]])
                    k += 1
                
                entries.append({
                    'file_off': i,
                    'vaddr': vaddr,
                    'index_val': idx_val,
                    'name': name,
                    'assoc': assoc.decode('ascii', errors='replace') if assoc else '',
                })
                i = k
            else:
                i += 1
        else:
            i += 1
    return entries


def group_tables(entries, gap=0x100):
    """Group entries into tables based on proximity."""
    if not entries:
        return []
    
    tables = []
    current_table = [entries[0]]
    
    for entry in entries[1:]:
        if entry['file_off'] - current_table[-1]['file_off'] <= gap:
            current_table.append(entry)
        else:
            tables.append(current_table)
            current_table = [entry]
    
    tables.append(current_table)
    return tables


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    data = Path(path).read_bytes()

    entries = extract_effect_tables(data)
    tables = group_tables(entries)

    print(f"=== Effect Name Table Entries ({len(entries)} found, {len(tables)} tables) ===\n")

    for ti, table in enumerate(tables):
        if len(table) < 2:
            continue
        start_vaddr = table[0]['vaddr']
        end_vaddr = table[-1]['vaddr']
        print(f"--- Table {ti}: {len(table)} entries, vaddr 0x{start_vaddr:08X} - 0x{end_vaddr:08X} ---")
        for e in table:
            assoc_str = f" -> {e['assoc']!r}" if e['assoc'] else ''
            print(f"    vaddr 0x{e['vaddr']:08X} (file 0x{e['file_off']:06X}): idx=0x{e['index_val']:08X} ({e['index_val']}) name={e['name']!r}{assoc_str}")
        print()


if __name__ == '__main__':
    main()
