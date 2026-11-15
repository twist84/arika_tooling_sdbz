"""Native 0x19B5C0 command switch and lossless intermediate packet tests."""
import struct
import unittest

from arika_menu_gs_packet import (
    decode_packet, NATIVE_DISPATCH, STATE_KEYS)


# 0x19B614..0x19B634, the ELF's opcode range check and jump-table
# dispatch. It is a 9-entry switch, not direct GS register encoding.
NATIVE_DISPATCH_WORDS = [
    0x96830000, 0x2c610009, 0x1020003e,
    0x3c04004c, 0x00031880, 0x248402c0,
    0x00641821, 0x8c630000, 0x00600008,
]

NATIVE_TABLE_WORDS = [
    0x19b658, 0x19b688, 0x19b6e8,
    0x19b6f8, 0x19b6c8, 0x19b6d8,
    0x19b708, 0x19b710, 0x19b640,
]


def make_packet(commands, header=0):
    return struct.pack('<II', header, len(commands)) + b''.join(commands)


def short(opcode, value=0):
    return struct.pack('<Hh', opcode, value)


class NativeGsIntermediatePacketTests(unittest.TestCase):
    def test_instruction_switch_has_nine_entries_and_exact_elf_targets(self):
        self.assertEqual(len(NATIVE_DISPATCH_WORDS),
                         (0x19b638 - 0x19b614) // 4)
        self.assertEqual(NATIVE_DISPATCH_WORDS[1], 0x2c610009,
                         'sltiu admits opcode 0 through 8')
        self.assertEqual(NATIVE_DISPATCH_WORDS[-1], 0x00600008,
                         'JR dispatches through decoded pointer')
        self.assertEqual(NATIVE_DISPATCH, tuple(NATIVE_TABLE_WORDS))
        self.assertEqual(STATE_KEYS,
                         ('word0', 'byte2', 'byte3',
                          'byte4', 'word6', 'word8'))

    def test_all_nine_opcodes_and_state_reset(self):
        commands = [
            short(2, 0x1234),
            short(3, 0x019a),  # native stores only low byte
            short(4, -7),
            short(5, 42),
            struct.pack('<HHHBBI', 1, 0x12, 0x34, 9, 8, 0x43210123),
            struct.pack('<6H', 6, 0, 512, 0, 448, 0),
            struct.pack('<6H', 7, 1, 2, 3, 4, 5),
            struct.pack('<HHI4s', 0, 0, 4, b'ABCD'),
            short(8),
            struct.pack('<HHI', 0, 0, 0),
        ]
        initial = dict(word0=-1, byte2=3, byte3=7,
                       byte4=9, word6=13, word8=17)
        buffer = make_packet(commands, header=0x11223344)
        out = decode_packet(buffer, initial)
        self.assertEqual(out['format'], 'ARIKA_EE_SPRITE_COMMANDS')
        self.assertEqual(out['header_word'], 0x11223344)
        self.assertEqual(out['command_count'], 10)
        self.assertEqual(out['parsed_bytes'], len(buffer))
        self.assertEqual(out['trailing_bytes'], 0)
        self.assertEqual([x['opcode'] for x in out['commands']],
                         [2, 3, 4, 5, 1, 6, 7, 0, 8, 0])
        self.assertEqual([x['size'] for x in out['commands']],
                         [4, 4, 4, 4, 12, 12, 12, 12, 4, 8])
        self.assertEqual([x['value'] for x in out['commands'][:4]],
                         [0x1234, 0x9a, -7, 42])
        self.assertEqual(out['commands'][4]['selectors'], [0x12, 0x34])
        self.assertEqual(out['commands'][4]['options'], [9, 8])
        self.assertEqual(out['commands'][4]['resource_pointer'], 0x43210123)
        self.assertEqual(out['commands'][5]['payload_hex'],
                         buffer[out['commands'][5]['offset'] + 2:
                                out['commands'][5]['offset'] + 12].hex())
        self.assertEqual(out['commands'][7]['payload_hex'], '41424344')
        self.assertEqual(
            out['commands'][7]['state_at_dispatch'],
            dict(word0=0x1234, byte2=0x9a, byte3=7,
                 byte4=9, word6=-7, word8=42))
        self.assertTrue(out['commands'][8]['state_reset'])
        self.assertEqual(out['commands'][9]['state_at_dispatch'], initial)
        self.assertEqual(out['final_state'], initial)

    def test_null_initial_state_is_explicitly_unknown(self):
        out = decode_packet(
            make_packet([short(2, 3),
                         struct.pack('<HHI', 0, 0, 0)]))
        state = out['commands'][-1]['state_at_dispatch']
        self.assertEqual(state['word0'], 3)
        for key in STATE_KEYS[1:]:
            self.assertIsNone(state[key])
        self.assertIn('not hardware GS', out['limitations'][0])

    def test_rejects_truncation_unknown_opcodes_and_incorrect_lengths(self):
        valid = make_packet([short(4, 13)])
        cases = (
            b'', b'\x00' * 7,
            struct.pack('<II', 0, 2) + short(2, 1),
            make_packet([short(9)]),
            make_packet([struct.pack('<HH', 0, 0)]),
            make_packet([struct.pack('<HHI', 0, 0, 99)]),
            make_packet([struct.pack('<HH', 1, 0)]),
            make_packet([struct.pack('<HH', 6, 0)]),
            valid + b'padding',
        )
        for data in cases:
            with self.subTest(case=data.hex()):
                with self.assertRaises(ValueError):
                    decode_packet(data)
        self.assertEqual(
            decode_packet(valid + b'padding',
                          allow_padding=True)['trailing_bytes'],
            len(b'padding'))
        with self.assertRaises(ValueError):
            decode_packet(valid, {'invented_alpha': 1})
        with self.assertRaises(ValueError):
            decode_packet(valid, {'word0': 'opaque'})
        with self.assertRaises(TypeError):
            decode_packet(bytearray(valid))


if __name__ == '__main__':
    unittest.main()
