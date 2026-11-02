#!/usr/bin/env python3
"""Map STG effect node names to .ebz file names found in ELF strings."""
import struct
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from stg_parser import parse_stg


def extract_ebz_filenames_from_elf(data):
    """Find all eff/ and trc/ path strings in ELF."""
    filenames = set()
    i = 0x80
    while i < len(data) - 4:
        # Look for eff/eXX/ patterns
        if data[i:i+4] == b'eff/':
            end = data.index(b'\x00', i) if b'\x00' in data[i:] else len(data)
            s = data[i:end].decode('ascii', errors='replace')
            filenames.add(s)
            i = end
        elif data[i:i+4] == b'trc/':
            end = data.index(b'\x00', i) if b'\x00' in data[i:] else len(data)
            s = data[i:end].decode('ascii', errors='replace')
            filenames.add(s)
            i = end
        else:
            i += 1
    return sorted(filenames)


def extract_stg_effect_names(data_dir):
    """Parse all STG files and collect efXX effect node names."""
    effect_names = {}
    stg_dir = Path(data_dir) / 'stg'
    for stg_file in sorted(stg_dir.rglob('*.stg')):
        result = parse_stg(str(stg_file))
        effects = [n for n in result['nodes'] if n['kind'] == 1 and n['name'].startswith('ef')]
        if effects:
            effect_names[stg_file.name] = [e['name'] for e in effects]
    return effect_names


if __name__ == '__main__':
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    data_dir = sys.argv[2] if len(sys.argv) > 2 else r'C:\Dev\arika\source_data\extracted'
    
    elf_data = Path(elf_path).read_bytes()
    
    print("=== .ebz file paths referenced in ELF ===\n")
    elf_filenames = extract_ebz_filenames_from_elf(elf_data)
    for f in elf_filenames:
        print(f"  {f}")
    print(f"\nTotal: {len(elf_filenames)} file paths")
    
    print(f"\n=== STG effect node names ===\n")
    stg_effects = extract_stg_effect_names(data_dir)
    for stg_name, effects in stg_effects.items():
        print(f"{stg_name}:")
        for e in effects:
            print(f"  {e}")
    
    print(f"\n=== Name mapping analysis ===\n")
    # Check if any effect names match .ebz file stems
    for stg_name, effects in stg_effects.items():
        for e in effects:
            # ef00 -> e00000? Check if any ELF filename matches pattern
            matches = [f for f in elf_filenames if e.replace('ef', 'e') in f or e in f]
            if matches:
                print(f"  {stg_name}: {e} -> {matches}")
