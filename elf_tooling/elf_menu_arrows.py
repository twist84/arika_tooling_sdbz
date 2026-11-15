#!/usr/bin/env python3
"""Find the native SDBZ menu-arrow layout and animation tables in PS2 ELFs.

The EU beta helper at 0x3753A0 indexes four UV rectangles, reads the
component float age at +0xB0, takes fmod(age, 40.0), and interpolates
(0, 3, -3, 0) at key times (0, 10, 30, 40).

The data block has the same layout in all four inspected regional ELFs.
No ELF or game artwork is included in this repository.
"""
import argparse
import json
import struct
from pathlib import Path

from elf_video_modes import load_segments


NATIVE_UV_RECTS = (
    (37, 19, 0, 50),      # right
    (0, 19, 37, 50),      # left
    (81, 63, 113, 100),  # up
    (81, 100, 113, 63),  # down
)
NATIVE_TIMES = (0.0, 10.0, 30.0, 40.0)
NATIVE_VALUES = (0.0, 3.0, -3.0, 0.0)

TABLE_BYTES = (
    b''.join(struct.pack('<4h', *rect) for rect in NATIVE_UV_RECTS)
    + struct.pack('<8f', *(NATIVE_TIMES + NATIVE_VALUES))
)


def find_arrow_tables(segments):
    found = []
    for base, data in segments:
        start = 0
        while True:
            index = data.find(TABLE_BYTES, start)
            if index < 0:
                break
            found.append({
                'uv_table_va': '0x%08X' % (base + index),
                'curve_times_va': '0x%08X' % (base + index + 32),
                'curve_values_va': '0x%08X' % (base + index + 48),
                'uv_rectangles': [list(rect) for rect in NATIVE_UV_RECTS],
                'key_times': list(NATIVE_TIMES),
                'key_values': list(NATIVE_VALUES),
                'period': 40,
            })
            start = index + len(TABLE_BYTES)
    return found


def inspect_elf(path):
    segments = load_segments(Path(path).read_bytes())
    return {'elf': str(path), 'arrow_tables': find_arrow_tables(segments)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path, nargs='+')
    args = parser.parse_args()
    print(json.dumps([inspect_elf(path) for path in args.elf], indent=2))


if __name__ == '__main__':
    main()
