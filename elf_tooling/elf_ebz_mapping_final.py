#!/usr/bin/env python3
"""Map STG effect names to .ebz entries using ref table analysis."""
import struct
import re
import json
from pathlib import Path


def parse_ebz(data):
    """Parse .ebz file and return header, refs, entries."""
    if len(data) < 0x30 or data[0:4] != b" ZBE":
        return None
    version, etype = struct.unpack_from('<HH', data, 4)
    size_field = struct.unpack_from('<I', data, 0x08)[0]
    f0 = struct.unpack_from('<f', data, 0x0C)[0]
    count = struct.unpack_from('<I', data, 0x1C)[0]
    
    # Ref table: 8-byte records (name[8] + u64 value)
    table_size = struct.unpack_from('<I', data, size_field)[0]
    table_count = struct.unpack_from('<I', data, size_field + 4)[0]
    refs = []
    for i in range(table_count):
        roff = size_field + 8 + i * 16
        name_raw = data[roff:roff + 8]
        name = name_raw.split(b'\x00')[0].decode('ascii', errors='replace')
        value = struct.unpack_from('<Q', data, roff + 8)[0]
        refs.append({'name': name, 'value': value, 'value_lo': value & 0xFFFFFFFF, 'value_hi': (value >> 32) & 0xFFFFFFFF})
    
    # Entries: 112-byte records (28 u32 fields)
    entries_off = size_field + table_size
    entries = []
    for i in range(count):
        eoff = entries_off + i * 112
        fields = struct.unpack_from('<28I', data, eoff)
        entries.append({'index': i, 'fields': list(fields), 'field_0x9C': fields[0x9C // 4] if 0x9C // 4 < 28 else None})
    
    return {
        'count': count,
        'table_count': table_count,
        'refs': refs,
        'entries': entries,
    }


def extract_stg_effects(data_dir):
    """Parse all STG files and collect effect nodes."""
    effects = {}
    stg_dir = Path(data_dir) / 'stg'
    for stg_file in sorted(stg_dir.rglob('*.stg')):
        data = stg_file.read_bytes()
        name_count = struct.unpack_from('<I', data, 8)[0]
        names = []
        for i in range(name_count):
            off = 16 + i * 16
            name = data[off:off+16].split(b'\x00')[0].decode('ascii', errors='replace')
            names.append(name)
        
        node_off = 16 + name_count * 16
        off = node_off
        eff_nodes = []
        while off < len(data):
            kind = data[off]
            inline_ref_count = data[off+1]
            links = data[off+2]
            name_index = struct.unpack_from('<I', data, off+4)[0]
            name = names[name_index] if name_index < len(names) else f"[{name_index}]"
            
            if kind in (1, 2, 3):
                base_size = 44
            elif kind in (4, 6):
                base_size = 60
            elif kind == 5:
                base_size = 96
            else:
                break
            
            total_size = base_size + (inline_ref_count * 8 if kind == 3 else 0)
            
            if kind == 1 and name.startswith('ef'):
                trs = struct.unpack_from('<9f', data, off+8)
                eff_nodes.append({
                    'name': name,
                    'links': links,
                    'T': trs[:3],
                    'R': trs[3:6],
                    'S': trs[6:9],
                })
            
            off += total_size
        
        if eff_nodes:
            effects[stg_file.name] = eff_nodes
    return effects


def compute_simple_hash(name):
    """Compute a simple hash matching the CEBZ hash function patterns."""
    # From disassembly: XOR with 5, compare with 5, ORI with 0x1C
    # This is a custom hash - let's try several common approaches
    h = 0
    for c in name.encode('ascii'):
        h = ((h << 5) + h + c) & 0xFFFFFFFF  # djb2-like
    return h


def find_ebz_path_for_effect(eff_name, ebz_files):
    """Find .ebz files that could correspond to an effect name."""
    matches = []
    m = re.match(r'ef(\d+)', eff_name)
    if m:
        num = m.group(1)
        # Direct: ef00 -> eff/e00/...
        for path in ebz_files:
            if f'/e{num}/' in path or path.endswith(f'e{num}'):
                matches.append((path, 'dir_match'))
        # seXX: ef00 -> eff/se00/...
        for path in ebz_files:
            if f'/se{num}/' in path:
                matches.append((path, 'se_match'))
    return matches


def main():
    elf_path = r'C:\Dev\arika\source_data\SLUS_214.42'
    data_dir = r'C:\Dev\arika\source_data\extracted'
    
    # Collect all .ebz files
    ebz_dir = Path(data_dir) / 'eff'
    ebz_files = []
    ebz_data = {}
    for f in sorted(ebz_dir.rglob('*.ebz')):
        rel = str(f.relative_to(ebz_dir))
        ebz_files.append(rel)
        parsed = parse_ebz(f.read_bytes())
        if parsed:
            ebz_data[rel] = parsed
    
    print(f"=== .ebz Files ({len(ebz_files)} total) ===\n")
    for rel in ebz_files:
        d = ebz_data.get(rel, {})
        ref_names = [r['name'] for r in d.get('refs', [])]
        print(f"  {rel}: count={d.get('count',0)}, refs={ref_names[:5]}")
    
    # Collect STG effects
    stg_effects = extract_stg_effects(data_dir)
    print(f"\n=== STG Effect Nodes ===\n")
    total_effects = 0
    for stg_name, nodes in sorted(stg_effects.items()):
        print(f"{stg_name} ({len(nodes)} effects):")
        for n in nodes:
            total_effects += 1
            print(f"  {n['name']}: T=({n['T'][0]:.1f},{n['T'][1]:.1f},{n['T'][2]:.1f})")
        print()
    
    # Try to match
    print("=== STG -> .ebz Mapping ===\n")
    mapped = 0
    unmapped = []
    for stg_name, nodes in sorted(stg_effects.items()):
        for n in nodes:
            matches = find_ebz_path_for_effect(n['name'], ebz_files)
            if matches:
                mapped += 1
                print(f"  {stg_name}: {n['name']} -> {matches[:3]}")
            else:
                unmapped.append((stg_name, n['name']))
    
    print(f"\nMapped: {mapped}/{total_effects}")
    if unmapped:
        print(f"\nUnmapped ({len(unmapped)}):")
        for stg_name, name in unmapped:
            print(f"  {stg_name}: {name}")
    
    # Show all ref table names across .ebz files
    print(f"\n=== All .ebz Ref Table Names ===\n")
    all_ref_names = set()
    for rel, d in ebz_data.items():
        for r in d.get('refs', []):
            all_ref_names.add(r['name'])
    for name in sorted(all_ref_names):
        print(f"  {name}")


if __name__ == '__main__':
    main()
