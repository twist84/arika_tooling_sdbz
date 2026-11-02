#!/usr/bin/env python3
"""Analyze effect name clusters in ELF to find mapping tables between effect names and .ebz paths."""
import struct
import re
from pathlib import Path


def find_effect_name_regions(data):
    """Find all regions containing effect names (efXX pattern) with surrounding context."""
    regions = []
    i = 0x80
    while i < len(data) - 8:
        if data[i:i+2] == b'ef' and data[i+2:i+4].isdigit():
            # Found potential effect name, check for null termination
            name_end = i + 4
            while name_end < len(data) and data[name_end] == 0:
                name_end += 1
            
            # Look backwards for preceding structure (4-byte aligned)
            region_start = i
            while region_start > 0x80 and (region_start - 4) >= 0x80:
                prev_word = struct.unpack_from('<I', data, region_start - 4)[0]
                # If previous word looks like an index or pointer, extend region
                if prev_word < 0x10000:  # small value, likely index
                    region_start -= 4
                else:
                    break
            
            # Look forward for associated names
            region_end = name_end
            while region_end < len(data) - 4:
                # Check for more effect names or associated strings
                if data[region_end:region_end+2] == b'ef' and data[region_end+2:region_end+4].isdigit():
                    region_end += 4
                    while region_end < len(data) and data[region_end] == 0:
                        region_end += 1
                elif data[region_end] == 0:
                    region_end += 1
                else:
                    break
            
            regions.append({
                'start': region_start,
                'end': region_end,
                'first_name': data[i:i+4].decode('ascii'),
                'first_vaddr': 0x100000 + (i - 0x80),
            })
            i = region_end
        else:
            i += 1
    return regions


def extract_strings_in_region(data, start, end):
    """Extract all null-terminated strings in a region."""
    strings = []
    i = start
    while i < end:
        if 32 <= data[i] < 127:
            s_start = i
            while i < end and 32 <= data[i] < 127:
                i += 1
            s = data[s_start:i].decode('ascii')
            if len(s) >= 3:
                strings.append((s_start, s, 0x100000 + (s_start - 0x80)))
        else:
            i += 1
    return strings


def main():
    path = r'C:\Dev\arika\source_data\SLUS_214.42'
    data = Path(path).read_bytes()

    regions = find_effect_name_regions(data)
    
    print(f"=== Effect Name Regions ({len(regions)} found) ===\n")
    
    for ri, region in enumerate(regions):
        strings = extract_strings_in_region(data, region['start'], region['end'])
        
        # Separate effect names from other strings
        eff_names = [(s, v) for off, s, v in strings if re.match(r'ef\d+', s)]
        other_strings = [(s, v) for off, s, v in strings if not re.match(r'ef\d+', s)]
        
        print(f"\n--- Region {ri}: file 0x{region['start']:06X} - 0x{region['end']:06X} (vaddr 0x{region['first_vaddr']:08X}) ---")
        print(f"  Size: {region['end'] - region['start']} bytes")
        print(f"  First name: {region['first_name']!r}")
        
        if eff_names:
            print(f"  Effect names ({len(eff_names)}):")
            for s, v in eff_names:
                print(f"    {s!r} (vaddr 0x{v:08X})")
        
        if other_strings:
            print(f"  Other strings ({len(other_strings)}):")
            for s, v in other_strings:
                print(f"    {s!r} (vaddr 0x{v:08X})")
        
        # Check for associated patterns
        patterns = {
            '_2iti': [s for s, _ in other_strings if '_2iti' in s],
            '_8tref': [s for s, _ in other_strings if '_8tref' in s],
            '_8AFtref': [s for s, _ in other_strings if '_8AFtref' in s],
            '_1': [s for s, _ in other_strings if s.startswith('_1')],
            '_8': [s for s, _ in other_strings if s.startswith('_8')],
            'CStg': [s for s, _ in other_strings if s.startswith('CStg')],
            'eff/': [s for s, _ in other_strings if s.startswith('eff/')],
            'trc/': [s for s, _ in other_strings if s.startswith('trc/')],
        }
        
        for pat, matches in patterns.items():
            if matches:
                print(f"  {pat} matches ({len(matches)}):")
                for m in matches[:5]:
                    print(f"    {m!r}")


if __name__ == '__main__':
    main()
