"""Decode EU-beta engine sprite command buffers from 0x19B5C0.

This is an *intermediate engine command list*, NOT GIF/GS register data.
Command labels and widths follow the ELF opcode dispatch at 0x19B614 and
jump table 0x4C02C0. State fields without caller-provided initial values
stay None. The tool does not invent blend modes or video register settings.

Usage:
    python arika_menu_gs_packet.py packet_buffer.bin
    python arika_menu_gs_packet.py packet_buffer.bin --initial-state '{"word0": 1}'
"""
import argparse
import json
from pathlib import Path
import struct


# ELF 0x4C02C0, nine little-endian jump targets indexed by opcode.
NATIVE_DISPATCH = (
    0x19b658, 0x19b688, 0x19b6e8, 0x19b6f8, 0x19b6c8,
    0x19b6d8, 0x19b708, 0x19b710, 0x19b640,
)
STATE_KEYS = ('word0', 'byte2', 'byte3', 'byte4', 'word6', 'word8')


def decode_packet(buffer, initial_state=None, allow_padding=False):
    """Parse a complete 8-byte packet head and counted native commands.

    The number of commands is the u32 at +4; commands begin at +8.
    Opcodes 0 and 8 invoke engine callbacks. 1 binds a texture
    resource. 2..5 update four fields of the local 10-byte render
    state. 6 and 7 carry unexamined 12-byte payloads.
    """
    if not isinstance(buffer, bytes):
        raise TypeError('packet must be bytes')
    if len(buffer) < 8:
        raise ValueError('native command header truncated')
    if initial_state is None:
        initial_state = {}
    if not isinstance(initial_state, dict):
        raise ValueError('initial state must be an object')
    if set(initial_state) - set(STATE_KEYS):
        raise ValueError('unknown initial state key')
    for key, value in initial_state.items():
        if not isinstance(value, int):
            raise ValueError('initial state fields must be integers')

    head, count = struct.unpack_from('<II', buffer)
    if count > (len(buffer) - 8) // 4:
        raise ValueError('native command count exceeds available words')
    original = {key: initial_state.get(key) for key in STATE_KEYS}
    state = dict(original)
    cursor = 8
    commands = []

    for index in range(count):
        if len(buffer) - cursor < 4:
            raise ValueError('truncated native command opcode')
        opcode = struct.unpack_from('<H', buffer, cursor)[0]
        if opcode >= len(NATIVE_DISPATCH):
            raise ValueError('unknown native command opcode %d' % opcode)
        size = 12 if opcode in (1, 6, 7) else 4
        if opcode == 0:
            if len(buffer) - cursor < 8:
                raise ValueError('truncated native command payload header')
            payload_size = struct.unpack_from('<I', buffer, cursor + 4)[0]
            size = 8 + payload_size
        if size > len(buffer) - cursor:
            raise ValueError('truncated native command payload')

        command = dict(index=index, offset=cursor, opcode=opcode,
                       target=NATIVE_DISPATCH[opcode], size=size)
        if opcode == 0:
            command['payload_size'] = size - 8
            command['payload_hex'] = buffer[cursor + 8:cursor + size].hex()
            command['state_at_dispatch'] = dict(state)
        elif opcode == 1:
            # The actual interpreter reads +4 halfword and +6 byte
            # to index two engine resource tables at GP-0x7FA8/0x7FA0.
            # The selector names and resulting GS modes remain unknown.
            command['selectors'] = [
                struct.unpack_from('<H', buffer, cursor + off)[0]
                for off in (2, 4)]
            command['options'] = [
                buffer[cursor + 6], buffer[cursor + 7]]
            command['resource_pointer'] = struct.unpack_from(
                '<I', buffer, cursor + 8)[0]
        elif opcode in (2, 3, 4, 5):
            value = struct.unpack_from('<h', buffer, cursor + 2)[0]
            key = {2: 'word0', 3: 'byte2', 4: 'word6', 5: 'word8'}[opcode]
            state[key] = (value & 0xff) if opcode == 3 else value
            command['value'] = state[key]
            command['field'] = key
        elif opcode in (6, 7):
            command['payload_hex'] = buffer[cursor + 2:cursor + 12].hex()
        elif opcode == 8:
            # 0x19B640 reloads the local state through 0x199500.
            state = dict(original)
            command['state_reset'] = True

        commands.append(command)
        cursor += size

    if cursor != len(buffer) and not allow_padding:
        raise ValueError('trailing unparsed native command bytes')
    return dict(
        format='ARIKA_EE_SPRITE_COMMANDS', version=1,
        header_word=head, command_count=count, parsed_bytes=cursor,
        trailing_bytes=len(buffer) - cursor,
        initial_state=original, final_state=state,
        commands=commands,
        limitations=[
            'Engine command list, not hardware GS/GIF register data.',
            'Texture flags, GS blend/depth/filter semantics unverified.',
            'Initial render state requires an external observed context.'
        ])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('packet', type=Path)
    parser.add_argument('--initial-state', default='{}',
                        help='JSON object of observed initial state fields')
    parser.add_argument('--allow-padding', action='store_true',
                        help='accept unused allocation bytes after commands')
    parser.add_argument('--resolve-sampling', action='store_true',
                        help='annotate opcode-1 native filter/clamp table flags')
    args = parser.parse_args()
    try:
        state = json.loads(args.initial_state)
        data = decode_packet(args.packet.read_bytes(),
                             state, args.allow_padding)
        if args.resolve_sampling:
            from arika_menu_gs_sampling import annotate_packet_sampling
            data = annotate_packet_sampling(data)
    except (OSError, ValueError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps(data, indent=2))


if __name__ == '__main__':
    main()
