"""EU-beta menu sprite attachment -> native engine filtering selector bridge.

The five-argument fields written by 0x2FD8F0 become one opcode-1
intermediate command in 0x2FE920 when a valid resource is bound.
Four sampler bytes are copied in their original order; this is *not*
a texture atlas index or proof of an observed live GS draw.

Static sites below were independently inspected at the exact original
EU-beta ELF. All four literal sampler arguments are established by
instructions immediately around each JAL (including delay slot).
"""
import struct

from arika_menu_gs_sampling import resolve_texture_binding


SPRITE_RESOURCE_OFFSET = 0x44
SPRITE_SAMPLER_OFFSET = 0x48
SAMPLER_SETTER_ADDRESS = 0x2FD8F0
SAMPLER_PACKET_PRODUCER = 0x2FE920
NATIVE_SPRITE_MIN_SIZE = 0x4C

# (direct call to 0x2FD8F0, resource selector at 0x3725E0, ownership)
# *These are verified initializer calls*, not a run-time draw capture.
NATIVE_MENU_ATTACHMENT_SITES = (
    (0x376034, 2, 'shared tile-owner sprite'),
    (0x378434, 2, 'shared main-menu banner'),
    (0x37A754, 11, 'Dragon item-3 embedded sprite'),
    (0x37BF0C, 4, 'help-panel frame sprite'),
)

STATIC_ATTACHMENT_FLAGS = (0, 1, 0, 0)


def decode_sprite_sampler_flags(flags, resource_pointer=None):
    """Decode four sprite +0x48..+0x4B bytes with the opcode-1 tables.

    +0x48 -> packet +2 (not filtering)
    +0x49 -> packet +4 (filter selector)
    +0x4A -> packet +6 (clamp selector)
    +0x4B -> packet +7 (unverified second option)

    No runtime texture ID, TEX0 record or successful GS submit is
    inferred from the sprite's raw resource pointer.
    """
    if (not isinstance(flags, (tuple, list, bytes)) or len(flags) != 4 or
            any(type(value) is not int or not 0 <= value <= 255
                for value in flags)):
        raise ValueError('four native sprite sampler bytes required')
    if (resource_pointer is not None and
            (type(resource_pointer) is not int or
             not 0 <= resource_pointer <= 0xffffffff)):
        raise ValueError('sprite resource pointer must be a u32 or unknown')

    fields = tuple(flags)
    parsed = resolve_texture_binding({
        'opcode': 1,
        'selectors': [fields[0], fields[1]],
        'options': [fields[2], fields[3]],
        'resource_pointer': resource_pointer,
    })
    # A null resource explicitly prevents native opcode-1 emission.
    # A non-null pointer only permits an attempt, not guaranteed success.
    parsed['sprite_sampler_bytes'] = list(fields)
    parsed['resource_present'] = (resource_pointer != 0
                                  if resource_pointer is not None else None)
    parsed['opcode1_possible'] = (resource_pointer != 0
                                 if resource_pointer is not None else None)
    if resource_pointer == 0:
        # 0x2FD078 branches around the opcode-1 producer on null +0x44.
        # A derived sampler setting is not an emitted TEX1 register.
        parsed['tex1_if_texture_writer_succeeds'] = None
        parsed['tex1_fields_if_emitted'] = None
    parsed['native_sprite_setter'] = hex(SAMPLER_SETTER_ADDRESS)
    parsed['native_packet_producer'] = hex(SAMPLER_PACKET_PRODUCER)
    return parsed


def decode_sprite_sampler_snapshot(sprite):
    """Extract a captured sprite image through +0x4B, no GS assumptions."""
    if not isinstance(sprite, bytes) or len(sprite) < NATIVE_SPRITE_MIN_SIZE:
        raise ValueError('sprite snapshot must contain offsets +0x44..+0x4B')
    ptr = struct.unpack_from('<I', sprite, SPRITE_RESOURCE_OFFSET)[0]
    flags = sprite[SPRITE_SAMPLER_OFFSET:SPRITE_SAMPLER_OFFSET + 4]
    return decode_sprite_sampler_flags(flags, ptr)


def static_menu_attachment_initializers():
    """Return ELF-proven initial filter choices for four *known* sprites."""
    result = []
    for caller, resource_entry, owner in NATIVE_MENU_ATTACHMENT_SITES:
        flags = decode_sprite_sampler_flags(STATIC_ATTACHMENT_FLAGS)
        result.append({
            'call_address': hex(caller),
            'resource_entry': resource_entry,
            'owner': owner,
            'initializer_sampler_bytes': list(STATIC_ATTACHMENT_FLAGS),
            'initial_filter': flags['texture_filter'],
            'initial_clamp_flag': flags['clamp_flag'],
            'runtime_resource_pointer': None,
            'actual_gs_state': None,
            'limitation': ('Initializer-only; subsequent setters, resource '
                           'validation and active GS state unobserved.'),
        })
    return result


def main():
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sprite', type=Path, nargs='?',
                        help='captured sprite memory image (at least 0x4C bytes)')
    parser.add_argument('--static-menu', action='store_true',
                        help='list proven initializer sites instead')
    args = parser.parse_args()
    if bool(args.sprite) == args.static_menu:
        parser.error('provide either a sprite snapshot or --static-menu')
    try:
        if args.static_menu:
            result = static_menu_attachment_initializers()
        else:
            result = decode_sprite_sampler_snapshot(args.sprite.read_bytes())
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
