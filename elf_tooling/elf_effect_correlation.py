#!/usr/bin/env python3
"""Correlate STG effect names with ELF string addresses and .ebz file paths found in ELF."""
import struct
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from stg_parser import parse_stg


def extract_ebz_filenames_from_elf(data):
    """Find all eff/ and trc/ path strings in ELF data section."""
    filenames = {}
    i = 0x80
    while i < len(data) - 4:
        if data[i:i + 4] == b'eff/':
            end = data.index(b'\x00', i) if b'\x00' in data[i:] else len(data)
            s = data[i:end].decode('ascii', errors='replace')
            vaddr = 0x100000 + (i - 0x80)
            filenames[s] = vaddr
            i = end
        elif data[i:i + 4] == b'trc/':
            end = data.index(b'\x00', i) if b'\x00' in data[i:] else len(data)
            s = data[i:end].decode('ascii', errors='replace')
            vaddr = 0x100000 + (i - 0x80)
            filenames[s] = vaddr
            i = end
        else:
            i += 1
    return filenames


def extract_stg_effect_names(data_dir):
    """Parse all STG files and collect efXX effect node names with their TRS."""
    effect_names = {}
    stg_dir = Path(data_dir) / 'stg'
    for stg_file in sorted(stg_dir.rglob('*.stg')):
        result = parse_stg(str(stg_file))
        effects = [n for n in result['nodes'] if n['kind'] == 1 and n['name'].startswith('ef')]
        if effects:
            effect_names[stg_file.name] = effects
    return effect_names


def find_correlations(elf_filenames, stg_effects):
    """Find correlations between STG effect names and ELF .ebz file paths."""
    print("=== STG Effect -> ELF .ebz path correlations ===\n")

    for stg_name, effects in sorted(stg_effects.items()):
        print(f"{stg_name}:")
        for eff in effects:
            eff_name = eff['name']
            T = eff.get('T', (0, 0, 0))
            matches = []

            # Try direct match: ef00 -> eff/e00/...
            for elf_path, vaddr in elf_filenames.items():
                # Extract the number from effect name (e.g. ef00 -> 00)
                import re
                m = re.match(r'ef(\d+)', eff_name)
                if m:
                    num = m.group(1)
                    # Check if elf path contains this number as part of eXX/YYYY pattern
                    if f'e{num}/' in elf_path or f'/e{num}' in elf_path:
                        matches.append((elf_path, vaddr, 'direct_num'))

                # Try exact stem match
                if eff_name in elf_path:
                    matches.append((elf_path, vaddr, 'exact'))

            if matches:
                print(f"  {eff_name} T=({T[0]:.1f},{T[1]:.1f},{T[2]:.1f}):")
                for elf_path, vaddr, match_type in matches[:10]:
                    print(f"    -> {elf_path} (vaddr 0x{vaddr:08X}) [{match_type}]")
            else:
                print(f"  {eff_name} T=({T[0]:.1f},{T[1]:.1f},{T[2]:.1f}): NO MATCH")
        print()


if __name__ == '__main__':
    elf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'
    data_dir = sys.argv[2] if len(sys.argv) > 2 else r'C:\Dev\arika\source_data\extracted'

    elf_data = Path(elf_path).read_bytes()

    print("=== .ebz file paths in ELF ===\n")
    elf_filenames = extract_ebz_filenames_from_elf(elf_data)
    for f, v in sorted(elf_filenames.items(), key=lambda x: x[1]):
        print(f"  {f} (vaddr 0x{v:08X})")
    print(f"\nTotal: {len(elf_filenames)} file paths\n")

    print(f"=== STG effect nodes ===\n")
    stg_effects = extract_stg_effect_names(data_dir)
    total_effects = sum(len(v) for v in stg_effects.values())
    print(f"Total effect nodes across all STG files: {total_effects}\n")

    find_correlations(elf_filenames, stg_effects)
