#!/usr/bin/env python3
"""Extract native Super Dragon Ball Z background RGBA presets from PS2 ELFs.

The native CStageXX virtual method at slot 29 returns an RGBA float vector
from a class-specific table, indexed by $a1 * 16 bytes. The following method
at slot 31 marks the next table. Nothing here relies on region offsets.
"""
import argparse
import json
import struct
from pathlib import Path


def read_u32(data, index):
    return struct.unpack_from('<I', data, index)[0]


def load_base(data):
    if data[:4] != b'\x7fELF' or data[4:6] != b'\x01\x01':
        raise ValueError('Expected 32-bit little-endian ELF')
    phoff = read_u32(data, 0x1c)
    phsize, phcount = struct.unpack_from('<HH', data, 0x2a)
    for i in range(phcount):
        ph = phoff + i * phsize
        kind, offset, address = struct.unpack_from('<III', data, ph)
        if kind == 1:
            return address - offset
    raise ValueError('No PT_LOAD segment')


def decode_table_address(data, function, base):
    """Recognise LUI, SLL a1 by 4, ADDIU address construction."""
    pos = function - base
    if pos < 0 or pos + 20 > len(data):
        return None
    lui, shift, add = struct.unpack_from('<III', data, pos)
    if (lui >> 26 != 15 or shift >> 26 != 0 or (shift & 0x3f) != 0
            or ((shift >> 6) & 31) != 4 or ((shift >> 16) & 31) != 5
            or add >> 26 != 9):
        return None
    register = (lui >> 16) & 31
    if ((add >> 21) & 31) != register or ((add >> 16) & 31) != register:
        return None
    signed_imm = (add & 0x7fff) - (add & 0x8000)
    return ((lui & 0xffff) << 16) + signed_imm


def extract_class(data, base, class_id):
    name = ('CStage%02d' % class_id).encode() + b'\0'
    occurrence = data.find(name)
    if occurrence < 0:
        raise ValueError('No class name ' + name.decode())
    address = occurrence + base
    lo = address & 0xffff
    hi = (address + 0x8000) >> 16
    for pos in range(0x80, len(data) - 64, 4):
        w = read_u32(data, pos)
        if w >> 26 != 15 or w & 0xffff != hi:
            continue
        dest = (w >> 16) & 31
        for delta in range(4, 52, 4):
            v = read_u32(data, pos + delta)
            if v >> 26 != 9 or v & 0xffff != lo:
                continue
            if ((v >> 21) & 31) != dest or ((v >> 16) & 31) != dest:
                continue
            method = pos + base
            ptr = struct.pack('<I', method)
            at = data.find(ptr, 0x100)
            while at >= 0:
                if at >= 8 and at % 4 == 0:
                    vtable = at + base - 8
                    try:
                        first_getter = read_u32(data, vtable + 29*4 - base)
                        third_getter = read_u32(data, vtable + 31*4 - base)
                        start = decode_table_address(data, first_getter, base)
                        end = decode_table_address(data, third_getter, base)
                        if start is not None and end is not None:
                            count = (end - start) // 16
                            if 1 <= count <= 4 and (end - start) % 16 == 0:
                                colors = []
                                for i in range(count):
                                    rgba = struct.unpack_from('<4f', data, start - base + 16*i)
                                    if any(not 0 <= x <= 1 for x in rgba) or abs(rgba[3] - 1) > 1e-5:
                                        break
                                    colors.append([round(x*255) for x in rgba[:3]])
                                if len(colors) == count:
                                    return dict(colors=colors, table_vaddr='0x%X' % start,
                                                vtable_vaddr='0x%X' % vtable)
                    except (IndexError, struct.error):
                        pass
                at = data.find(ptr, at + 1)
    raise ValueError('Cannot resolve CStage%02d RGBA table' % class_id)


def extract(path):
    data = Path(path).read_bytes()
    base = load_base(data)
    return {'elf': str(path), 'stages': {
        'CStage%02d' % i: extract_class(data, base, i) for i in range(13)
    }}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elfs', nargs='+', help='regional game ELF paths')
    parser.add_argument('--check-regions', action='store_true',
                        help='fail if any region differs in colour data')
    args = parser.parse_args()
    results = [extract(path) for path in args.elfs]
    if args.check_regions and len(results) > 1:
        baseline = {name: item['colors'] for name, item in results[0]['stages'].items()}
        for result in results[1:]:
            other = {name: item['colors'] for name, item in result['stages'].items()}
            if baseline != other:
                raise SystemExit('Regional RGB mismatch: ' + result['elf'])
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
