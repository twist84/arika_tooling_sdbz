#!/usr/bin/env python3
"""Final correlation: map STG effect nodes to .ebz files via ELF string tables."""
import struct
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from stg_parser import parse_stg


def extract_elf_strings_with_offsets(data):
    """Extract all null-terminated ASCII strings from ELF data section."""
    strings = []
    i = 0x80
    while i < len(data):
        b = data[i]
        if 32 <= b < 127:
            start = i
            while i < len(data) and 32 <= data[i] < 127:
                i += 1
            if i - start >= 4:
                s = data[start:i].decode('ascii')
                vaddr = 0x100000 + (start - 0x80)
                strings.append((start, vaddr, s))
        else:
            i += 1
    return strings


def extract_stg_effects(data_dir):
    """Parse all STG files and collect effect nodes."""
    effects = {}
    stg_dir = Path(data_dir) / 'stg'
    for stg_file in sorted(stg_dir.rglob('*.stg')):
        result = parse_stg(str(stg_file))
        eff_nodes = [n for n in result['nodes'] if n['kind'] == 1 and n['name'].startswith('ef')]
        if eff_nodes:
            effects[stg_file.name] = eff_nodes
    return effects


def find_ebz_path_for_effect(eff_name, elf_strings):
    """Find .ebz file paths that could correspond to an effect name."""
    matches = []
    m = re.match(r'ef(\d+)', eff_name)
    if not m:
        return matches

    num = m.group(1)
    # Look for paths like eff/eXX/YYYY where XX matches the effect number
    for off, vaddr, s in elf_strings:
        if s.startswith('eff/') and not s.endswith('.ebz'):
            # Check if path contains e{num}/
            if f'e{num}/' in s:
                matches.append((s, vaddr, 'eXX_dir_match'))
            # Check if path starts with e{num}
            elif s.startswith(f'eff/e{num}'):
                matches.append((s, vaddr, 'prefix_match'))
    return matches


def main():
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    data_dir = sys.argv[2] if len(sys.argv) > 2 else r'C:\Dev\arika\source_data\extracted'

    elf_data = Path(elf_path).read_bytes()
    elf_strings = extract_elf_strings_with_offsets(elf_data)
    stg_effects = extract_stg_effects(data_dir)

    print("=== STG Effect -> ELF .ebz Path Correlation ===\n")

    total_mapped = 0
    total_effects = 0

    for stg_name, eff_nodes in sorted(stg_effects.items()):
        print(f"{stg_name} ({len(eff_nodes)} effect nodes):")
        for eff in eff_nodes:
            eff_name = eff['name']
            T = eff.get('T', (0, 0, 0))
            total_effects += 1

            matches = find_ebz_path_for_effect(eff_name, elf_strings)
            if matches:
                total_mapped += 1
                print(f"  {eff_name} T=({T[0]:.1f},{T[1]:.1f},{T[2]:.1f}):")
                for path, vaddr, match_type in matches[:5]:
                    print(f"    -> {path} (0x{vaddr:08X}) [{match_type}]")
            else:
                print(f"  {eff_name} T=({T[0]:.1f},{T[1]:.1f},{T[2]:.1f}): NO .ebz PATH FOUND")
        print()

    print(f"Summary: {total_mapped}/{total_effects} effect nodes have matching .ebz paths in ELF")


if __name__ == '__main__':
    main()
