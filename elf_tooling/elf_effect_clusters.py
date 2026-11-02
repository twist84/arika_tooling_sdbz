#!/usr/bin/env python3
"""Analyze effect name reference clusters in ELF to find lookup tables mapping names to .ebz files."""
import struct
from pathlib import Path


def find_effect_name_positions(data, effect_names):
    """Find all file offsets where each effect name appears."""
    positions = {}
    for name in effect_names:
        positions[name] = []
        search = name.encode('ascii') + b'\x00'
        idx = 0
        while True:
            idx = data.find(search, idx)
            if idx == -1:
                break
            positions[name].append(idx)
            idx += 1
    return positions


def find_clusters(positions, window=0x200):
    """Group nearby references into clusters."""
    all_positions = []
    for name, pos_list in positions.items():
        for pos in pos_list:
            all_positions.append((pos, name))
    all_positions.sort()

    clusters = []
    current_cluster = []
    cluster_start = None

    for pos, name in all_positions:
        if cluster_start is None:
            cluster_start = pos
            current_cluster = [(pos, name)]
        elif pos - cluster_start <= window:
            current_cluster.append((pos, name))
        else:
            clusters.append((cluster_start, current_cluster))
            cluster_start = pos
            current_cluster = [(pos, name)]

    if current_cluster:
        clusters.append((cluster_start, current_cluster))

    return clusters


def analyze_cluster(data, cluster_start, entries, window=0x200):
    """Analyze a cluster of effect name references for table structure."""
    cluster_end = cluster_start + window
    cluster_data = data[cluster_start:cluster_end]

    print(f"\n=== Cluster at file 0x{cluster_start:06X} (vaddr 0x{0x100000 + (cluster_start - 0x80):08X}) ===")
    print(f"  Window: 0x{cluster_start:06X} - 0x{cluster_end:06X}")
    print(f"  Entries ({len(entries)}):")

    # Sort entries by position
    entries_sorted = sorted(entries, key=lambda x: x[0])

    # Look for pointer table pattern: consecutive 4-byte values pointing to strings
    ptr_table_candidates = []
    off = cluster_start
    while off < cluster_end - 4:
        ptr = struct.unpack_from('<I', data, off)[0]
        file_off = ptr - 0x100000 + 0x80
        # Check if ptr points to one of our effect names
        for pos, name in entries_sorted:
            if file_off == pos:
                ptr_table_candidates.append((off, ptr, name))
                break
        off += 4

    if ptr_table_candidates:
        print(f"  Pointer table candidates ({len(ptr_table_candidates)}):")
        for off, ptr, name in ptr_table_candidates:
            vaddr = 0x100000 + (off - 0x80)
            print(f"    file 0x{off:06X} (v 0x{vaddr:08X}): ptr=0x{ptr:08X} -> {name!r}")
    else:
        # Show hex dump of cluster instead
        print(f"  No pointer table found. Hex dump:")
        for off in range(cluster_start, min(cluster_end, len(data)), 16):
            chunk = data[off:off + 16]
            hexs = ' '.join(f'{b:02X}' for b in chunk)
            asc = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
            vaddr = 0x100000 + (off - 0x80)
            print(f"    0x{off:06X} (v 0x{vaddr:08X}): {hexs:<48} {asc}")

    print(f"  Effect names in cluster:")
    for pos, name in entries_sorted:
        vaddr = 0x100000 + (pos - 0x80)
        print(f"    {name!r} at file 0x{pos:06X} (v 0x{vaddr:08X})")


if __name__ == '__main__':
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Dev\arika\source_data\SLUS_214.42'

    data = Path(path).read_bytes()

    effect_names = [f'ef{i:02d}' for i in range(40)] + [
        'efkasa', 'efy00', 'eft01', 'eft06', 'efk00', 'efk01', 'efk03',
        'efg00', 'efg01', 'efm00', 'efm01', 'efk04', 'efm02', 'efm03',
        'efk05', 'efb00', 'eft00', 'efk06', 'efk07', 'efk08', 'efk09',
        'efk10', 'efk11', 'efk12', 'efb14', 'efk13', 'efba00',
    ]

    positions = find_effect_name_positions(data, effect_names)
    clusters = find_clusters(positions, window=0x100)

    print(f"=== Effect name clusters ({len(clusters)} found) ===\n")

    for cluster_start, entries in clusters:
        analyze_cluster(data, cluster_start, entries)
