#!/usr/bin/env python3
"""Super Dragon Ball Z .pas pose parser.

PAS files contain pose/animation data referenced by STG stages and TRC
trajectory effects.

Format (inferred from ELF cross-referencing at 0x004CFAC8 "%s.pas"):
  * 0x00: u32 entry_count
  * 0x04-0x0C: reserved (zeros)
  * 0x10+: entry_count u32 file offsets to entry data blocks
  * Each entry data block contains u32 values that reference other entries
    (forming a pose graph / hierarchy)
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path
import sys


def require(condition, message):
    if not condition:
        raise ValueError(message)


def parse_pas(data):
    """Parse a .pas pose file."""
    require(len(data) >= 0x10, "truncated PAS header")
    entry_count = struct.unpack_from('<I', data, 0)[0]
    require(entry_count > 0 and entry_count <= 65536, "invalid entry count")

    # Reserved 12 bytes
    for off in (4, 8, 0xC):
        val = struct.unpack_from('<I', data, off)[0]
        require(val == 0, f"reserved field at 0x{off:X} must be zero")

    # Entry offset table at 0x10
    table_end = 0x10 + entry_count * 4
    require(table_end <= len(data), "truncated entry offset table")

    entry_offsets = list(struct.unpack_from(
        '<' + 'I' * entry_count, data, 0x10))

    # Parse each entry
    entries = []
    for i in range(entry_count):
        off = entry_offsets[i]
        if off == 0:
            # Null entry - no data
            entries.append({
                'index': i,
                'file_offset': 0,
                'size': 0,
                'references': [],
                'raw_hex': '',
            })
            continue

        require(off < len(data), f"entry {i}: offset {off} beyond file")

        # Read entry data until next entry offset or end of file
        next_off = len(data)
        for j in range(i + 1, entry_count):
            if entry_offsets[j] > off:
                next_off = entry_offsets[j]
                break

        entry_size = next_off - off
        require(entry_size >= 4, f"entry {i}: too small")

        entry_data = data[off:next_off]

        # Try to interpret entry data as u32 references to other entries
        references = []
        u32_values = []
        for k in range(0, entry_size - 3, 4):
            val = struct.unpack_from('<I', data, off + k)[0]
            u32_values.append(val)
            # If this value matches another entry's offset, it's a reference
            if val in entry_offsets and val != off:
                ref_index = entry_offsets.index(val)
                references.append({'target_index': ref_index, 'target_offset': val})

        entries.append({
            'index': i,
            'file_offset': off,
            'size': entry_size,
            'references': references,
            'u32_values': u32_values[:16],  # limit output
            'raw_hex': entry_data.hex(),
        })

    return {
        'format': 'ARIKA_PAS',
        'source_sha256': hashlib.sha256(data).hexdigest(),
        'byte_size': len(data),
        'entry_count': entry_count,
        'entries': entries,
        'scope': 'Structurally inferred; entry data contains u32 cross-references forming a pose graph. Semantic meaning of individual fields is not decoded.',
    }


def pas_summary(doc):
    """Human-readable summary of parsed PAS data."""
    lines = [
        f"Format: {doc['format']}",
        f"Size: {doc['byte_size']} bytes",
        f"SHA-256: {doc['source_sha256']}",
        f"Entries: {doc['entry_count']}",
    ]
    total_refs = sum(len(e['references']) for e in doc['entries'])
    lines.append(f"Total cross-references: {total_refs}")
    for e in doc['entries'][:20]:
        if e['size'] == 0:
            lines.append(f"  Entry {e['index']}: null")
        else:
            refs = [r['target_index'] for r in e['references']]
            lines.append(
                f"  Entry {e['index']}: offset=0x{e['file_offset']:04X}, "
                f"size={e['size']}, refs={refs[:8]}"
                + (f" (+{len(refs)-8} more)" if len(refs) > 8 else "")
            )
    if doc['entry_count'] > 20:
        lines.append(f"  ... and {doc['entry_count'] - 20} more entries")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    p = subs.add_parser('json'); p.add_argument('pas'); p.add_argument('output')
    p = subs.add_parser('summary'); p.add_argument('pas')
    args = parser.parse_args()
    try:
        result = parse_pas(Path(args.pas).read_bytes())
        if args.command == 'json':
            Path(args.output).write_bytes(json.dumps(result, indent=2).encode())
            print('Wrote ' + args.output)
        else:
            print(pas_summary(result))
    except (OSError, ValueError, struct.error) as error:
        print('error: ' + str(error), file=sys.stderr); return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
