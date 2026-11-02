#!/usr/bin/env python3
"""Decode Super Dragon Ball Z .ebz effect / trajectory archives."""
import argparse
import json
import math
from pathlib import Path
import struct
import sys

MAGIC = b" ZBE"
HEADER_SIZE = 0x30
REF_RECORD = 16
ENTRY_SIZE = 112
ENTRY_FIELDS = 28
NULL = 0xFFFFFFFF


def f32(value):
    f = struct.unpack('<f', struct.pack('<I', value & 0xFFFFFFFF))[0]
    return None if math.isnan(f) else f


def parse_ref_records(data, offset):
    table_size = struct.unpack_from('<I', data, offset)[0]
    table_count = struct.unpack_from('<I', data, offset + 4)[0]
    refs = []
    for i in range(table_count):
        roff = offset + 8 + i * REF_RECORD
        name_raw = data[roff:roff + 8]
        name = name_raw.split(b'\x00')[0].decode('ascii', errors='replace')
        value = struct.unpack_from('<Q', data, roff + 8)[0]
        refs.append({'index': i, 'name': name, 'value': value})
    return table_size, refs


def parse_entries(data, offset, count):
    entries = []
    for i in range(count):
        eoff = offset + i * ENTRY_SIZE
        fields = struct.unpack_from('<28I', data, eoff)
        floats = [f32(v) for v in fields]
        entry = {'index': i, 'fields': list(fields), 'floats': floats}
        entries.append(entry)
    return entries


def parse_ebz(data):
    if len(data) < HEADER_SIZE:
        raise ValueError("file too small for EBZ header")
    magic = data[0:4]
    if magic != MAGIC:
        raise ValueError(f"bad EBZ magic: {magic!r}")
    version, etype = struct.unpack_from('<HH', data, 4)
    size_field = struct.unpack_from('<I', data, 0x08)[0]
    f0 = f32(struct.unpack_from('<I', data, 0x0C)[0])
    pad1, pad2, pad3 = struct.unpack_from('<III', data, 0x10)
    count = struct.unpack_from('<I', data, 0x1C)[0]
    u1, u2, u3 = struct.unpack_from('<HHH', data, 0x20)
    p0, p1, p2 = struct.unpack_from('<III', data, 0x26)

    header = {
        'magic': magic.decode('ascii', errors='replace'),
        'version': version,
        'type': etype,
        'size_field': size_field,
        'param0': f0,
        'pad': [pad1, pad2, pad3],
        'count': count,
        'u1': u1,
        'u2': u2,
        'u3': u3,
        'p0': p0,
        'p1': p1,
        'p2': p2,
    }

    table_size, refs = parse_ref_records(data, size_field)
    entries_offset = size_field + table_size
    entries = parse_entries(data, entries_offset, count)
    entries_end = entries_offset + count * ENTRY_SIZE
    remaining = len(data) - entries_end

    return {
        'header': header,
        'refs': refs,
        'entries': entries,
        'entries_end': entries_end,
        'remaining': remaining,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    p = subs.add_parser('json'); p.add_argument('ebz'); p.add_argument('output')
    args = parser.parse_args()
    try:
        data = Path(args.ebz).read_bytes()
        result = parse_ebz(data)
        Path(args.output).write_bytes(json.dumps(result, indent=2).encode())
        print('Wrote ' + args.output)
    except (OSError, ValueError, struct.error) as error:
        print('error: ' + str(error), file=sys.stderr); return 1


if __name__ == '__main__':
    sys.exit(main())
