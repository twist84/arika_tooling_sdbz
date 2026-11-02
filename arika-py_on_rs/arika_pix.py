#!/usr/bin/env python3
"""Super Dragon Ball Z FPIX texture container and XPIX/TIM2 chunk parser."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

import arika_dat as archive


MAGIC_FPIX = b"FPIX"
MAGIC_XPIX = b"XPIX"
MAGIC_TIM2 = b"TIM2"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def parse_fpix(data):
    """Parse an FPIX (.pix) texture container into chunks.

    Returns a dict with magic, size, version, and chunks. Each chunk has
    index, magic, offset, size, and raw bytes.
    """
    require(len(data) >= 32 and data[:4] == MAGIC_FPIX, "expected FPIX magic")
    size, count, version = struct.unpack_from("<III", data, 4)
    require(size == len(data), "container size mismatch")
    require(count > 0, "empty FPIX container")
    require(32 + count * 4 <= size, "truncated chunk directory")
    offsets = struct.unpack_from("<" + "I" * count, data, 32)
    require(offsets[0] == 32 + count * 4, "unexpected directory start")

    chunks = []
    for i, start in enumerate(offsets):
        end = offsets[i + 1] if i + 1 < count else size
        require(start + 8 <= end <= size, "invalid chunk extent")
        chunk_magic = data[start:start + 4]
        chunk_size = struct.unpack_from("<I", data, start + 4)[0]
        require(chunk_size == end - start, "chunk size mismatch")
        chunks.append({
            'index': i,
            'magic': chunk_magic.decode('ascii', errors='replace'),
            'offset': start,
            'size': chunk_size,
            'data': data[start:end],
        })
    return {
        'magic': MAGIC_FPIX.decode('ascii'),
        'size': size,
        'version': version,
        'count': count,
        'chunks': chunks,
    }


def parse_tim2(data):
    """Parse a TIM2 texture chunk (PlayStation 2 VRAM texture format).

    Returns header info plus palette and pixel data descriptors.
    """
    require(len(data) >= 16 and data[:4] == MAGIC_TIM2, "expected TIM2 magic")
    # TIM2 header: magic(4), format(4), ..., width/height at known offsets
    # Based on observed XPIX->TIM2 chunks in FPIX containers
    total_size = struct.unpack_from('<I', data, 4)[0] if len(data) >= 8 else len(data)
    require(total_size == len(data), "TIM2 size mismatch")

    # Common TIM2 layout based on observed data
    pixel_format = struct.unpack_from('<I', data, 8)[0] if len(data) >= 12 else 0
    pixel_data_addr = struct.unpack_from('<I', data, 0x10)[0] if len(data) >= 0x14 else 0
    clut_addr = struct.unpack_from('<I', data, 0x14)[0] if len(data) >= 0x18 else 0
    pixel_data_size = struct.unpack_from('<I', data, 0x18)[0] if len(data) >= 0x1C else 0
    clut_size = struct.unpack_from('<I', data, 0x1C)[0] if len(data) >= 0x20 else 0

    return {
        'magic': MAGIC_TIM2.decode('ascii'),
        'total_size': total_size,
        'pixel_format': pixel_format,
        'pixel_data_addr': pixel_data_addr,
        'clut_addr': clut_addr,
        'pixel_data_size': pixel_data_size,
        'clut_size': clut_size,
    }


def parse_xpix(data):
    """Parse an XPIX chunk wrapper inside an FPIX container.

    XPIX chunks contain a TIM2 texture after a small header.
    """
    require(len(data) >= 32 and data[:4] == MAGIC_XPIX, "expected XPIX magic")
    # XPIX header followed by TIM2 data
    header_size = struct.unpack_from('<I', data, 4)[0] if len(data) >= 8 else 32
    tim2_offset = header_size

    result = {
        'magic': MAGIC_XPIX.decode('ascii'),
        'header_size': header_size,
        'tim2_offset': tim2_offset,
        'tim2': None,
    }
    if len(data) > tim2_offset and data[tim2_offset:tim2_offset + 4] == MAGIC_TIM2:
        result['tim2'] = parse_tim2(data[tim2_offset:])
    return result


def parse_pix(path):
    """Parse a .pix file (FPIX container)."""
    data = Path(path).read_bytes()
    fpix = parse_fpix(data)
    for chunk in fpix['chunks']:
        if chunk['magic'] == MAGIC_XPIX.decode('ascii'):
            chunk['xpix'] = parse_xpix(chunk['data'])
    return fpix


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    p = subs.add_parser('json'); p.add_argument('pix'); p.add_argument('output')
    args = parser.parse_args()
    try:
        result = parse_pix(args.pix)
        Path(args.output).write_bytes(json.dumps(result, indent=2).encode())
        print('Wrote ' + args.output)
    except (OSError, ValueError, struct.error) as error:
        print('error: ' + str(error), file=sys.stderr); return 1


if __name__ == '__main__':
    sys.exit(main())
