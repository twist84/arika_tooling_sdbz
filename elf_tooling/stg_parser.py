#!/usr/bin/env python3
"""Parse SDBZ STG stage files: scene graph nodes, names, EFFECT/STAGE roots."""
import struct
from pathlib import Path


def parse_stg(path):
    data = Path(path).read_bytes()
    name_count = struct.unpack_from('<I', data, 8)[0]
    names = []
    for i in range(name_count):
        off = 16 + i * 16
        name = data[off:off + 16].split(b'\x00')[0].decode('ascii', errors='replace')
        names.append(name)

    node_off = 16 + name_count * 16
    off = node_off
    nodes = []
    kind_counts = {}

    while off < len(data):
        kind = data[off]
        inline_ref_count = data[off + 1]
        links = data[off + 2]
        flags = data[off + 3]
        name_index = struct.unpack_from('<I', data, off + 4)[0]
        name = names[name_index] if name_index < len(names) else f"[{name_index}]"

        kind_counts[kind] = kind_counts.get(kind, 0) + 1

        if kind in (1, 2, 3):
            base_size = 44
        elif kind in (4, 6):
            base_size = 60
        elif kind == 5:
            base_size = 96
        else:
            break

        total_size = base_size + (inline_ref_count * 8 if kind == 3 else 0)

        entry = {
            'kind': kind,
            'name': name,
            'links': links,
            'flags': flags,
            'offset': off,
            'size': total_size,
        }

        if kind in (1, 2, 3):
            trs = struct.unpack_from('<9f', data, off + 8)
            entry['T'] = trs[:3]
            entry['R'] = trs[3:6]
            entry['S'] = trs[6:9]

        nodes.append(entry)
        off += total_size

    effect_idx = names.index("EFFECT") if "EFFECT" in names else -1
    stage_idx = names.index("STAGE") if "STAGE" in names else -1

    return {
        'names': names,
        'name_count': name_count,
        'nodes': nodes,
        'kind_counts': kind_counts,
        'effect_idx': effect_idx,
        'stage_idx': stage_idx,
        'parsed_offset': off,
        'file_size': len(data),
        'remaining': len(data) - off,
    }


def print_summary(result, path):
    print(f"\n{path}:")
    print(f"  names={result['name_count']}, EFFECT_idx={result['effect_idx']}, STAGE_idx={result['stage_idx']}")
    print(f"  kind_counts={result['kind_counts']}")
    print(f"  nodes={len(result['nodes'])}, parsed 0x{result['parsed_offset']:X}/0x{result['file_size']:X}, remaining={result['remaining']}")

    kind1 = [n for n in result['nodes'] if n['kind'] == 1]
    if kind1:
        print(f"  Kind=1 nodes ({len(kind1)}):")
        for n in kind1:
            T = n.get('T', (0, 0, 0))
            print(f"    {n['name']!r} links=0x{n['links']:02X} T=({T[0]:.1f},{T[1]:.1f},{T[2]:.1f})")


if __name__ == '__main__':
    import sys
    import glob

    paths = sys.argv[1:] if len(sys.argv) > 1 else glob.glob(r'C:\Dev\arika\source_data\extracted\stg\**\*.stg', recursive=True)
    for path in sorted(paths):
        result = parse_stg(path)
        print_summary(result, path)
