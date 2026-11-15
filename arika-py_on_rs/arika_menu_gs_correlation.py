"""Correlate EU-beta engine opcode-1 binds with captured EE texture records.

Native evidence:
  0x2FD8F0: sprite +0x44 resource object, +0x48..+0x4B flags
  0x2FE920: resource vtable +0x4C returns the opcode-1 +0x08 pointer
  0x19B6B4/BC: command +0x08 -> returned object +0x38 texture ID
  0x10DA20: passes that ID to 0x10C3E0, which indexes 0x4FF8F0

Input MUST be a matching-frame EE RAM image and engine command buffer.
No pointer from a sprite +0x44 is assumed equal to opcode-1 +0x08.
Callback return values are external capture evidence, never inferred.
Register writes are a conditional replay, NOT observed GS register state.
"""
import argparse
import json
from pathlib import Path
import struct

from arika_menu_gs_attachment import (
    NATIVE_SPRITE_MIN_SIZE, decode_sprite_sampler_snapshot,
)
from arika_menu_gs_sampling import decode_packet_sampling
from arika_menu_gs_texture import (
    ELF_DESCRIPTOR_TABLE, GS_TEX0_1, GS_TEX1_1,
    decode_clamp, decode_tex0, decode_tex1,
    parse_native_texture_record, texture_register_writes,
)


RESOURCE_RETURN_SLOT_OFFSET = 0x38
NATIVE_DESCRIPTOR_SIZE = 0x30
RESOURCE_VTABLE_RETURN_OFFSET = 0x4C
SPRITE_OBJECT_RESOURCE_OFFSET = 0x44
CACHE_POINTER_ADDRESS = 0x4FD40C
CACHE_FLAGS_ADDRESS = 0x4FD410


def _address(value):
    if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
        raise ValueError('EE addresses must be 32-bit unsigned integers')
    return value


def _memory_bytes(ram, address, size):
    # Deliberately only supports direct low-address EE RAM images. Do not
    # guess kseg/uncached aliases or silently wrap invalid pointers.
    if type(address) is not int or address < 0 or address > 0xFFFFFFFF:
        return None
    if address + size > len(ram):
        return None
    return ram[address:address + size]


def binding_cache_decision(resource_pointer, sampler_bytes,
                           cached_pointer=None, cached_bytes=None):
    """Replay the command-elision branch at 0x2FE938..0x2FEA34.

    A missing prior cache is unknown, rather than assumed empty.
    The native cache keys on the sprite's resource-object pointer and
    all four sampler bytes, not on the vtable-returned packet pointer.
    """
    _address(resource_pointer)
    if (not isinstance(sampler_bytes, (tuple, list, bytes)) or
            len(sampler_bytes) != 4 or
            any(type(value) is not int or not 0 <= value <= 255
                for value in sampler_bytes)):
        raise ValueError('four sprite sampler bytes are required')
    if resource_pointer == 0:
        return False
    if cached_pointer is None:
        return None
    _address(cached_pointer)
    if resource_pointer != cached_pointer:
        return True
    if cached_bytes is None:
        return None
    if (not isinstance(cached_bytes, (tuple, list, bytes)) or
            len(cached_bytes) != 4 or
            any(type(value) is not int or not 0 <= value <= 255
                for value in cached_bytes)):
        raise ValueError('four cached sampler bytes are required')
    return tuple(sampler_bytes) != tuple(cached_bytes)


def correlate_capture(packet, ram, sprite_addresses=(),
                      callback_returns=None):
    """Follow actual captured pointers without inventing sprite ownership.

    The RAM argument is a contiguous byte image mapped at EE address 0.
    callback_returns maps sprite EE address -> *observed* resource
    vtable +0x4C return pointer for that sprite, from the same frame.
    Without those observations, opcode-1/sprite links remain unknown.
    """
    if not isinstance(packet, bytes) or not isinstance(ram, bytes):
        raise TypeError('packet and RAM captures must be bytes')
    if callback_returns is None:
        callback_returns = {}
    if not isinstance(callback_returns, dict):
        raise ValueError('callback returns must be a mapping')

    sprites = []
    seen = set()
    for address in sprite_addresses:
        _address(address)
        if address in seen:
            raise ValueError('duplicate sprite capture address')
        seen.add(address)
        snapshot = _memory_bytes(ram, address, NATIVE_SPRITE_MIN_SIZE)
        if snapshot is None:
            raise ValueError('sprite is outside captured EE RAM')
        sprite = decode_sprite_sampler_snapshot(snapshot)
        sprites.append({
            'sprite_address': hex(address),
            'resource_object_pointer': hex(sprite['resource_pointer']),
            'sampler_bytes': sprite['sprite_sampler_bytes'],
            'callback_return_pointer': None,
        })

    for address, result_pointer in callback_returns.items():
        _address(address)
        _address(result_pointer)
        if address not in seen:
            raise ValueError('callback return has no listed sprite')
        for sprite in sprites:
            if int(sprite['sprite_address'], 16) == address:
                sprite['callback_return_pointer'] = hex(result_pointer)
                break

    decoded = decode_packet_sampling(packet)
    bindings = []
    for command in decoded['commands']:
        if command['opcode'] != 1:
            continue
        raw_pointer = command['resource_pointer']
        selector = command['texture_binding']
        raw_bytes = [
            command['selectors'][0], command['selectors'][1],
            command['options'][0], command['options'][1],
        ]
        matches = [
            sprite['sprite_address'] for sprite in sprites
            if sprite['callback_return_pointer'] is not None
            and int(sprite['callback_return_pointer'], 16) == raw_pointer
            and sprite['sampler_bytes'] == raw_bytes
            and int(sprite['resource_object_pointer'], 16) != 0
        ]
        row = {
            'command_index': command['index'],
            'command_offset': command['offset'],
            'returned_resource_pointer': hex(raw_pointer),
            'sampler_bytes': raw_bytes,
            'matching_sprites_with_observed_callback_returns': matches,
            'sprite_ownership': ('not_captured' if not callback_returns else
                                 'unique_match' if len(matches) == 1 else
                                 'ambiguous' if matches else 'no_match'),
            'resource_slot': None,
            'descriptor_address': None,
            'descriptor': None,
            'registers_if_native_writer_succeeds': None,
            'register_fields_if_emitted': None,
            'preflight': None,
        }
        bindings.append(row)
        if raw_pointer == 0:
            row['preflight'] = 'null_returned_pointer'
            continue
        raw_id = _memory_bytes(
            ram, raw_pointer + RESOURCE_RETURN_SLOT_OFFSET, 4)
        if raw_id is None:
            row['preflight'] = 'resource_object_outside_ram'
            continue
        slot = struct.unpack('<I', raw_id)[0]
        row['resource_slot'] = slot
        if not 1 <= slot <= 255:
            row['preflight'] = 'invalid_resource_slot'
            continue
        descriptor_address = ELF_DESCRIPTOR_TABLE + (slot - 1) * NATIVE_DESCRIPTOR_SIZE
        row['descriptor_address'] = hex(descriptor_address)
        descriptor = _memory_bytes(
            ram, descriptor_address, NATIVE_DESCRIPTOR_SIZE)
        if descriptor is None:
            row['preflight'] = 'descriptor_outside_ram'
            continue
        row['descriptor'] = parse_native_texture_record(descriptor)
        if not selector['complete']:
            row['preflight'] = 'unverified_sampler_selector'
            continue
        try:
            writes = texture_register_writes(
                slot, descriptor, selector['filter_flag'],
                selector['clamp_flag'])
        except ValueError as error:
            row['preflight'] = 'unsupported_descriptor: ' + str(error)
            continue
        if writes is None:
            row['preflight'] = 'native_writer_rejects_descriptor'
            continue
        registers = dict(writes)
        row['registers_if_native_writer_succeeds'] = {
            hex(address): hex(value) for address, value in writes
        }
        row['register_fields_if_emitted'] = {
            'tex0': decode_tex0(registers[GS_TEX0_1]),
            'tex1': decode_tex1(registers[GS_TEX1_1]),
            'clamp': decode_clamp(registers[0x08]),
        }
        row['preflight'] = 'native_writer_accepts_descriptor'

    return {
        'bindings': bindings,
        'sprites': sprites,
        'capture_scope': {
            'packet_commands': len(decoded['commands']),
            'ram_bytes': len(ram),
            'sprite_addresses': len(sprites),
            'observed_callback_return_count': len(callback_returns),
        },
        'limitations': [
            'Same-frame EE RAM and intermediate engine command data are required.',
            'Sprite +0x44 is NOT the opcode-1 +0x08 pointer.',
            'Sprite associations require captured vtable +0x4C return values.',
            'A cache hit can omit opcode-1 even when a sprite is drawn.',
            'Writer preflight is not actual GS/DMA submission or draw-time state.',
            'Indirect callbacks and subsequent GS commands may override state.',
        ],
    }


def _parse_address(value):
    try:
        return _address(int(value, 0))
    except (ValueError, TypeError) as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def _parse_callback_mapping(value):
    try:
        left, right = value.split(':', 1)
        return _parse_address(left), _parse_address(right)
    except (ValueError, argparse.ArgumentTypeError) as error:
        raise argparse.ArgumentTypeError(
            'expected SPRITE_EE_ADDRESS:OBSERVED_RETURN_POINTER') from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packet', type=Path, help='captured engine command buffer')
    parser.add_argument('ram', type=Path, help='same-frame direct 0-based EE RAM dump')
    parser.add_argument('--sprite', action='append', type=_parse_address,
                        default=[], help='sprite EE address (repeatable)')
    parser.add_argument('--observed-return', action='append',
                        type=_parse_callback_mapping, default=[],
                        help='sprite address:captured vtable +0x4C return')
    args = parser.parse_args()
    try:
        mapping = dict(args.observed_return)
        if len(mapping) != len(args.observed_return):
            raise ValueError('duplicate observed callback return address')
        result = correlate_capture(
            args.packet.read_bytes(), args.ram.read_bytes(),
            args.sprite, mapping)
    except (OSError, ValueError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
