"""Native EU-beta CAppLogoMain resources and sprite rectangle evidence.

These are file-backed ELF strings and R5900 instructions, not heuristics
based on screenshots or file names. The loader's runtime resource pointers
are unknown until the game executes; their filenames alone do NOT establish
a PIX atlas index, a GS texture, or measured blending.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import struct

from arika_logo_runtime import ELF_SHA256


LOGO_POINTER_TABLE = 0x004B4770
LOGO_RESOURCE_POINTERS = (0x004D91A0, 0x004D91C0, 0x004D91E0)
LOGO_RESOURCE_NAMES = (
    'dis/d03/d03t0205',
    'dis/d03/d03t0203',
    'dis/d03/d03t0202',
)
LOGO_LOADER_ADDRESS = 0x0041E750
LOGO_DRAW_ADDRESS = 0x0041EB90
LOGO_SPRITE_INITIALIZER = 0x0041E680
LOGO_SOURCE_RECT = (0, 0, 512, 447)
LOGO_DEST_RECT = (0, 0, 512, 448)
LOGO_SAMPLER_BYTES = (0, 1, 0, 0)
ELF_SEGMENT_BIAS = 0xFFF80


def _word(data, address):
    offset = address - ELF_SEGMENT_BIAS
    if offset < 0 or offset + 4 > len(data):
        raise ValueError('ELF virtual address outside file data: 0x%08X' % address)
    return struct.unpack_from('<I', data, offset)[0]


def _cstring(data, address, limit=64):
    offset = address - ELF_SEGMENT_BIAS
    if offset < 0 or offset + limit > len(data):
        raise ValueError('ELF string pointer outside mapped file')
    raw = data[offset:offset + limit].split(b'\0', 1)
    if len(raw) != 2:
        raise ValueError('unterminated native resource name')
    return raw[0].decode('ascii')


def recover_logo_resources(data):
    """Read the original pointers and assert the precise native callsites."""
    if type(data) is not bytes or hashlib.sha256(data).hexdigest() != ELF_SHA256:
        raise ValueError('expected the exact EU-beta SLES_541.61 ELF')
    pointers = tuple(_word(data, LOGO_POINTER_TABLE + i * 4)
                     for i in range(3))
    if pointers != LOGO_RESOURCE_POINTERS:
        raise ValueError('unexpected CAppLogoMain resource pointer table')
    names = tuple(_cstring(data, pointer) for pointer in pointers)
    if names != LOGO_RESOURCE_NAMES:
        raise ValueError('unexpected CAppLogoMain resource names')

    # Exact MIPS words: 3 pointer loads, loader access, sprite binding/draw.
    words = {
        0x41E760: 0xC4424770,
        0x41E770: 0xC4414774,
        0x41E77C: 0xC4404778,
        0x41E7B4: 0x8C44002C,
        0x41E7F4: 0x2404000C,
        0x41E808: 0x8E0300A8,
        0x41EB9C: 0x908200A1,
        0x41EBAC: 0x0C0BEE58,
        0x41EBC8: 0x0C0BF63C,
        0x2FD970: 0xA486002E,
        0x2FD920: 0xA485004E,
    }
    for address, word in words.items():
        if _word(data, address) != word:
            raise ValueError('logo instruction mismatch at 0x%08X' % address)

    return {
        'format': 'ARIKA_EU_BETA_LOGO_RESOURCES',
        'elf_sha256': ELF_SHA256,
        'loader_address': hex(LOGO_LOADER_ADDRESS),
        'draw_address': hex(LOGO_DRAW_ADDRESS),
        'sprite_initialization': hex(LOGO_SPRITE_INITIALIZER),
        'resources': [
            {'index': index, 'name': name, 'name_address': hex(pointer),
             'pointer_table_address': hex(LOGO_POINTER_TABLE + index * 4),
             'wrapper_object_offset': hex(0x2c + index * 4)}
            for index, (name, pointer) in enumerate(zip(names, pointers))
        ],
        'sprite': {
            'object_offset': '0x40',
            'source_rect': list(LOGO_SOURCE_RECT),
            'destination_rect': list(LOGO_DEST_RECT),
            'initial_sampler_bytes': list(LOGO_SAMPLER_BYTES),
            'source_setter': '0x2fd970',
            'destination_setter': '0x2fd920',
            'attachment_setter': '0x2fd8f0',
            'draw_dispatch': '0x2fd8a0',
            'resource_unwrap': '0x2fb960',
        },
        'limits': [
            'Resource names come from ELF; the contents are not embedded.',
            'Pointer table indexes the three asynchronously created resource wrappers.',
            'Native draw dereferences the active index and wrapper before binding.',
            'Initial sampler bytes do not prove the live hardware GS filtering mode.',
            'Draw rectangle is verified, but Qt rendering is not PS2 GS raster parity.',
        ],
    }


def logo_asset_paths(root):
    """Paths for assets extracted under their exact ELF-declared names."""
    root = Path(root)
    return tuple(root.joinpath(*PurePosixPath(name).parts)
                 for name in LOGO_RESOURCE_NAMES)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--assets-root', type=Path,
                        help='check extracted original assets without reading them')
    args = parser.parse_args()
    try:
        report = recover_logo_resources(args.elf.read_bytes())
        if args.assets_root is not None:
            report['asset_files'] = [
                {'index': i, 'path': str(path), 'exists': path.is_file()}
                for i, path in enumerate(logo_asset_paths(args.assets_root))
            ]
    except (OSError, ValueError, UnicodeError) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
