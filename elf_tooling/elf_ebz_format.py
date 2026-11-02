#!/usr/bin/env python3
"""ELF tooling: .ebz (CEBZ effect) binary format parser."""
import struct
import sys
from pathlib import Path


def parse_ebz(data, filepath=None):
    """Parse a .ebz (CEBZ effect) binary file.
    
    Returns a dict with header info and entries.
    """
    if len(data) < 0x20:
        return {'error': 'file too small'}
    
    # Header
    magic = data[0:4]
    if magic != b' ZBE':
        return {'error': f'invalid magic: {magic!r}'}
    
    version = struct.unpack_from('<I', data, 0x04)[0]
    data_size = struct.unpack_from('<I', data, 0x08)[0]
    scale = struct.unpack_from('<f', data, 0x0C)[0]
    entry_count = struct.unpack_from('<I', data, 0x1C)[0]
    
    result = {
        'magic': magic.decode('ascii'),
        'version': f'{(version >> 16) & 0xFF}.{version & 0xFF}',
        'data_size': data_size,
        'scale': scale,
        'entry_count': entry_count,
        'file_size': len(data),
        'entries': [],
    }
    
    # Extract strings from file
    strings = {}
    i = 0
    while i < len(data) - 3:
        b = data[i]
        if 32 <= b < 127:
            start = i
            while i < len(data) and 32 <= data[i] < 127:
                i += 1
            s = data[start:i].decode('ascii')
            if len(s) >= 2:
                strings[start] = s
        else:
            i += 1
    
    # Parse entries (start at 0x20)
    entry_start = 0x20
    remaining = len(data) - entry_start
    if entry_count > 0:
        entry_size = remaining // entry_count
    else:
        entry_size = 0
    
    for entry_idx in range(entry_count):
        entry_off = entry_start + entry_idx * entry_size
        if entry_off + 0x20 > len(data):
            break
        
        entry = {
            'index': entry_idx,
            'file_offset': entry_off,
            'entry_size': entry_size,
        }
        
        # Read entry fields
        entry['type_flags'] = struct.unpack_from('<I', data, entry_off)[0]
        entry['field_04'] = struct.unpack_from('<I', data, entry_off + 0x04)[0]
        entry['field_08'] = struct.unpack_from('<I', data, entry_off + 0x08)[0]
        entry['field_0C'] = struct.unpack_from('<I', data, entry_off + 0x0C)[0]
        entry['f_0x10'] = struct.unpack_from('<f', data, entry_off + 0x10)[0]
        entry['f_0x20'] = struct.unpack_from('<f', data, entry_off + 0x20)[0]
        entry['f_0x24'] = struct.unpack_from('<f', data, entry_off + 0x24)[0]
        entry['field_0x28'] = struct.unpack_from('<I', data, entry_off + 0x28)[0]
        entry['field_0x2C'] = struct.unpack_from('<I', data, entry_off + 0x2C)[0]
        entry['field_0x30'] = struct.unpack_from('<I', data, entry_off + 0x30)[0]
        entry['field_0x34'] = struct.unpack_from('<I', data, entry_off + 0x34)[0]
        entry['field_0x38'] = struct.unpack_from('<I', data, entry_off + 0x38)[0]
        entry['field_0x3C'] = struct.unpack_from('<I', data, entry_off + 0x3C)[0]
        entry['f_0x40'] = struct.unpack_from('<f', data, entry_off + 0x40)[0]
        entry['f_0x44'] = struct.unpack_from('<f', data, entry_off + 0x44)[0]
        entry['f_0x48'] = struct.unpack_from('<f', data, entry_off + 0x48)[0]
        entry['f_0x4C'] = struct.unpack_from('<f', data, entry_off + 0x4C)[0]
        entry['field_0x50'] = struct.unpack_from('<I', data, entry_off + 0x50)[0]
        entry['f_0x54'] = struct.unpack_from('<f', data, entry_off + 0x54)[0]
        entry['field_0x58'] = struct.unpack_from('<I', data, entry_off + 0x58)[0]
        entry['field_0x5C'] = struct.unpack_from('<I', data, entry_off + 0x5C)[0]
        entry['field_0x60'] = struct.unpack_from('<I', data, entry_off + 0x60)[0]
        entry['field_0x64'] = struct.unpack_from('<I', data, entry_off + 0x64)[0]
        entry['field_0x68'] = struct.unpack_from('<I', data, entry_off + 0x68)[0]
        entry['field_0x6C'] = struct.unpack_from('<I', data, entry_off + 0x6C)[0]
        entry['f_0x70'] = struct.unpack_from('<f', data, entry_off + 0x70)[0]
        entry['f_0x74'] = struct.unpack_from('<f', data, entry_off + 0x74)[0]
        entry['field_0x78'] = struct.unpack_from('<I', data, entry_off + 0x78)[0]
        entry['field_0x7C'] = struct.unpack_from('<I', data, entry_off + 0x7C)[0]
        
        # Look for particle name string near this entry
        # Strings seem to be at the end of each entry block
        entry_end = entry_off + entry_size
        entry_strings = []
        for str_off, s in strings.items():
            if entry_off <= str_off < entry_end:
                entry_strings.append((str_off - entry_off, s))
        entry['strings'] = entry_strings
        
        result['entries'].append(entry)
    
    # Collect all strings not in entries (global strings)
    all_entry_string_offsets = set()
    for entry in result['entries']:
        for str_off_rel, _ in entry['strings']:
            all_entry_string_offsets.add(entry['file_offset'] + str_off_rel)
    
    result['global_strings'] = [
        (off, s) for off, s in strings.items() 
        if off not in all_entry_string_offsets
    ]
    
    return result


def print_ebz(result, filepath=None):
    """Pretty-print parsed .ebz data."""
    if 'error' in result:
        print(f"Error: {result['error']}")
        return
    
    name = filepath.name if filepath else 'unknown'
    print(f"=== {name} ===")
    print(f"  Magic: {result['magic']}")
    print(f"  Version: {result['version']}")
    print(f"  Data size: {result['data_size']} (0x{result['data_size']:X})")
    print(f"  Scale: {result['scale']:.6f}")
    print(f"  Entry count: {result['entry_count']}")
    print(f"  File size: {result['file_size']}")
    print()
    
    for entry in result['entries']:
        print(f"  Entry [{entry['index']}] at +0x{entry['file_offset']:04X} (size={entry['entry_size']}):")
        print(f"    type_flags=0x{entry['type_flags']:08X} field_04=0x{entry['field_04']:08X} ({entry['field_04']})")
        print(f"    field_08=0x{entry['field_08']:08X} field_0C=0x{entry['field_0C']:08X}")
        print(f"    f_0x10={entry['f_0x10']:.6f} f_0x20={entry['f_0x20']:.6f} f_0x24={entry['f_0x24']:.6f}")
        print(f"    field_0x28=0x{entry['field_0x28']:08X} field_0x2C=0x{entry['field_0x2C']:08X}")
        print(f"    field_0x30=0x{entry['field_0x30']:08X} field_0x34=0x{entry['field_0x34']:08X}")
        print(f"    field_0x38=0x{entry['field_0x38']:08X} field_0x3C=0x{entry['field_0x3C']:08X}")
        print(f"    f_0x40={entry['f_0x40']:.6f} f_0x44={entry['f_0x44']:.6f} f_0x48={entry['f_0x48']:.6f} f_0x4C={entry['f_0x4C']:.6f}")
        print(f"    field_0x50=0x{entry['field_0x50']:08X} f_0x54={entry['f_0x54']:.6f}")
        print(f"    field_0x58=0x{entry['field_0x58']:08X} field_0x5C=0x{entry['field_0x5C']:08X}")
        print(f"    field_0x60=0x{entry['field_0x60']:08X} field_0x64=0x{entry['field_0x64']:08X}")
        print(f"    field_0x68=0x{entry['field_0x68']:08X} field_0x6C=0x{entry['field_0x6C']:08X}")
        print(f"    f_0x70={entry['f_0x70']:.6f} f_0x74={entry['f_0x74']:.6f}")
        print(f"    field_0x78=0x{entry['field_0x78']:08X} field_0x7C=0x{entry['field_0x7C']:08X}")
        if entry['strings']:
            print(f"    Strings:")
            for str_off_rel, s in entry['strings']:
                print(f"      +0x{str_off_rel:04X}: {s}")
        print()


def main():
    # Default files to analyze
    default_files = [
        r'C:\Dev\arika\source_data\extracted\eff\e00\e00003.ebz',
        r'C:\Dev\arika\source_data\extracted\eff\e00\e00005.ebz',
        r'C:\Dev\arika\source_data\extracted\trc\01\efin0001p0101.ebz',
    ]
    
    files = sys.argv[1:] if len(sys.argv) > 1 else default_files
    
    for fp in files:
        path = Path(fp)
        if not path.exists():
            print(f"File not found: {fp}")
            continue
        data = path.read_bytes()
        result = parse_ebz(data, path)
        print_ebz(result, path)


if __name__ == '__main__':
    main()
