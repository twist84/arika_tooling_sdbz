#!/usr/bin/env python3
"""Locate GS default geometry and video register writes in PS2 MIPS ELFs.

Reads the ELF PT_LOAD segments directly; no third-party dependencies.
Does not assume the address layout of any particular regional build.
"""
import argparse
import json
from pathlib import Path
import struct


def load_segments(data):
    if len(data) < 52 or data[:4] != bytes((127, 69, 76, 70)):
        raise ValueError('not an ELF')
    if data[4] != 1 or data[5] != 1 or struct.unpack_from('<H', data, 18)[0] != 8:
        raise ValueError('expected 32-bit little-endian MIPS ELF')
    phoff = struct.unpack_from('<I', data, 28)[0]
    phentsize, phnum = struct.unpack_from('<HH', data, 42)
    if phentsize < 32 or phoff + phnum * phentsize > len(data):
        raise ValueError('invalid program header table')
    result = []
    for index in range(phnum):
        off = phoff + index * phentsize
        kind, file_off, va, _, length, _, _, _ = struct.unpack_from('<8I', data, off)
        if kind == 1 and length:
            if file_off + length > len(data):
                raise ValueError('truncated PT_LOAD segment')
            result.append((va, data[file_off:file_off + length]))
    if not result:
        raise ValueError('no PT_LOAD segment')
    return result


def decode_jal(site, instruction):
    if instruction >> 26 != 3:
        raise ValueError('not JAL')
    return ((site + 4) & 0xf0000000) | ((instruction & 0x03ffffff) << 2)


def find_default_geometry(segments):
    """Find boot routine calling the geometry validator with 640x448 twice."""
    matches = []
    for base, segment in segments:
        count = len(segment) // 4
        words = struct.unpack_from('<%dI' % count, segment)
        for index in range(count - 7):
            # addiu a0,zero,640; addiu a1,zero,448
            if words[index:index + 2] != (0x24040280, 0x240501c0):
                continue
            # move a2,a0 / move a3,a1 / jal / move t0,zero
            if (words[index + 3] != 0x0080302d or
                    words[index + 5] != 0x00a0382d or
                    words[index + 6] >> 26 != 3 or
                    words[index + 7] != 0x0000402d):
                continue
            address = base + 4 * index
            matches.append({
                'width': 640, 'height': 448,
                'secondary_width': 640, 'secondary_height': 448,
                'immediates_va': '0x%08X' % address,
                'call_va': '0x%08X' % (address + 24),
                'validator_va': '0x%08X' % decode_jal(address + 24, words[index + 6]),
            })
    return matches


def inspect_elf(path):
    data = Path(path).read_bytes()
    segments = load_segments(data)
    matches = find_default_geometry(segments)
    return {
        'file': str(path),
        'default_geometry_sites': matches,
        'note': ('These instructions identify a 640x448 graphics '
                 'initialization call, not a final TV output aspect ratio.'),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path, nargs='+')
    args = parser.parse_args()
    print(json.dumps([inspect_elf(path) for path in args.elf], indent=2))


if __name__ == '__main__':
    main()
