#!/usr/bin/env python3
"""Inspect PS2 GS DISPLAY/DISPFB registers and locate SDBZ write paths.

Input may be a game ELF and/or raw register values captured from PCSX2.
A static ELF can prove how registers are packed, but cannot prove which
dynamic configuration is active when a particular menu is visible.
"""
import argparse
import json
from pathlib import Path
import struct

from elf_video_modes import load_segments


def unpack_display(value):
    value = int(value)
    if value < 0 or value >= (1 << 64):
        raise ValueError('GS register must be an unsigned 64-bit integer')
    dx = value & 0xfff
    dy = (value >> 12) & 0x7ff
    magh = (value >> 23) & 0xf
    magv = (value >> 27) & 0x3
    dw = (value >> 32) & 0xfff
    dh = (value >> 44) & 0x7ff
    return dict(dx=dx, dy=dy, magh=magh, magv=magv, dw=dw, dh=dh,
                horizontal_magnification=magh+1,
                vertical_magnification=magv+1,
                nominal_source_width=(dw+1)/(magh+1),
                nominal_source_height=(dh+1)/(magv+1))


def unpack_dispfb(value):
    value = int(value)
    if value < 0 or value >= (1 << 64):
        raise ValueError('GS register must be an unsigned 64-bit integer')
    return dict(fbp=value & 0x1ff, fbw=(value >> 9) & 0x3f,
                psm=(value >> 15) & 0x1f, dbx=(value >> 32) & 0x7ff,
                dby=(value >> 43) & 0x7ff)


def pack_display(dx, dy, magh, magv, dw, dh):
    values = (dx, dy, magh, magv, dw, dh)
    masks = (0xfff, 0x7ff, 0xf, 0x3, 0xfff, 0x7ff)
    shifts = (0, 12, 23, 27, 32, 44)
    if any(not isinstance(v, int) or v < 0 or v > mask
           for v, mask in zip(values, masks)):
        raise ValueError('invalid GS DISPLAY field')
    return sum(v << shift for v, shift in zip(values, shifts))


def find_display2_packers(segments):
    """Find the exact DW=0x9ff packing sequence that ends in a GS DISPLAY2 sd.

    The scan has a second, short instruction-chain guard, so an incidental
    0x9ff constant elsewhere cannot be reported as a DISPLAY2 packer.
    """
    results = []
    for base, blob in segments:
        size = len(blob) // 4
        words = struct.unpack_from('<%dI' % size, blob)
        for i in range(size - 16):
            if words[i] != 0x240409ff or words[i+1] != 0x0004283c:
                continue
            # lui v1,0x1200 / sd a0,0xa0(v1); in a delay slot.
            if words[i+8] != 0x3c031200 or words[i+14] != 0xfc6400a0:
                continue
            # dsll32 a0,a0,12 / or a0,a0,a1
            if words[i+11] != 0x0004233c or words[i+12] != 0x00852025:
                continue
            results.append(dict(dw_constant_va='0x%08X' % (base+i*4),
                                register_write_va='0x%08X' % (base+(i+14)*4),
                                register='DISPLAY2',
                                register_address='0x120000A0',
                                dw=0x9ff))
    return results


def inspect_elf(path):
    return dict(elf=str(path), display2_packers=find_display2_packers(
        load_segments(Path(path).read_bytes())))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', nargs='*', type=Path)
    parser.add_argument('--display', help='DISPLAY1/2 register, e.g. 0x...')
    parser.add_argument('--dispfb', help='DISPFB1/2 register, e.g. 0x...')
    args = parser.parse_args()
    report = {}
    if args.elf:
        report['elf'] = [inspect_elf(path) for path in args.elf]
    if args.display is not None:
        report['display'] = unpack_display(int(args.display, 0))
    if args.dispfb is not None:
        report['dispfb'] = unpack_dispfb(int(args.dispfb, 0))
    if not report:
        parser.error('provide an ELF and/or a GS register value')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
