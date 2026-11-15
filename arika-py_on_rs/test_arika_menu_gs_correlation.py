"""Asset-free and optional exact-ELF tests for capture-driven GS correlation."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from arika_menu_gs_correlation import (
    CACHE_FLAGS_ADDRESS, CACHE_POINTER_ADDRESS,
    RESOURCE_RETURN_SLOT_OFFSET, RESOURCE_VTABLE_RETURN_OFFSET,
    binding_cache_decision, correlate_capture,
)
from arika_menu_gs_texture import ELF_DESCRIPTOR_TABLE


SPRITE_ADDRESS = 0x1000
RESOURCE_OBJECT = 0xA000
RETURNED_ADDRESS = 0x2000


def make_packet(filter_index=1, clamp_index=0, resource=RETURNED_ADDRESS,
                option_at_plus_two=0):
    command = struct.pack('<HHHBBI', 1, option_at_plus_two,
                          filter_index, clamp_index, 0, resource)
    return struct.pack('<II', 0, 1) + command


def make_ram(slot=1, tbp0=0x100, include_sprite=True):
    ram = bytearray(ELF_DESCRIPTOR_TABLE + 0x60)
    if include_sprite:
        struct.pack_into('<I', ram, SPRITE_ADDRESS + 0x44, RESOURCE_OBJECT)
        ram[SPRITE_ADDRESS + 0x48:SPRITE_ADDRESS + 0x4c] = bytes((0, 1, 0, 0))
    struct.pack_into('<I', ram, RETURNED_ADDRESS + 0x38, slot)
    if 1 <= slot <= 2:
        address = ELF_DESCRIPTOR_TABLE + (slot - 1) * 48
        struct.pack_into('<h', ram, address + 2, tbp0)
        struct.pack_into('<h', ram, address + 6, 9)
        struct.pack_into('<h', ram, address + 8, 8)
        struct.pack_into('<H', ram, address + 0x0e, 0)
        struct.pack_into('<h', ram, address + 0x16, 512)
        struct.pack_into('<h', ram, address + 0x18, 256)
    return bytes(ram)


class NativeGsCorrelationTests(unittest.TestCase):
    def test_valid_record_and_explicit_sprite_callback_match(self):
        report = correlate_capture(
            make_packet(), make_ram(), [SPRITE_ADDRESS],
            {SPRITE_ADDRESS: RETURNED_ADDRESS})
        self.assertEqual(len(report['bindings']), 1)
        row = report['bindings'][0]
        self.assertEqual(row['preflight'], 'native_writer_accepts_descriptor')
        self.assertEqual(row['resource_slot'], 1)
        self.assertEqual(row['descriptor_address'], hex(ELF_DESCRIPTOR_TABLE))
        self.assertEqual(row['sprite_ownership'], 'unique_match')
        self.assertEqual(
            row['matching_sprites_with_observed_callback_returns'],
            [hex(SPRITE_ADDRESS)])
        self.assertEqual(row['registers_if_native_writer_succeeds']['0x14'],
                         '0x60')
        self.assertEqual(row['register_fields_if_emitted']['tex0']['tbp0'],
                         0x100)
        self.assertEqual(row['register_fields_if_emitted']['tex1']['mmag'], 1)
        self.assertEqual(row['register_fields_if_emitted']['clamp']['wms'], 1)
        self.assertIn('not actual gs', report['limitations'][-2].lower())

    def test_sprite_resource_object_is_not_returned_packet_pointer(self):
        report = correlate_capture(make_packet(), make_ram(),
                                   [SPRITE_ADDRESS])
        row = report['bindings'][0]
        self.assertEqual(report['sprites'][0]['resource_object_pointer'],
                         hex(RESOURCE_OBJECT))
        self.assertEqual(row['returned_resource_pointer'],
                         hex(RETURNED_ADDRESS))
        self.assertEqual(row['sprite_ownership'], 'not_captured')
        self.assertEqual(row['matching_sprites_with_observed_callback_returns'],
                         [])
        self.assertEqual(row['preflight'], 'native_writer_accepts_descriptor')

    def test_wrong_callback_or_sampler_cannot_assert_owner(self):
        report = correlate_capture(
            make_packet(), make_ram(), [SPRITE_ADDRESS],
            {SPRITE_ADDRESS: RETURNED_ADDRESS + 4})
        self.assertEqual(report['bindings'][0]['sprite_ownership'], 'no_match')
        report = correlate_capture(
            make_packet(option_at_plus_two=256), make_ram(),
            [SPRITE_ADDRESS], {SPRITE_ADDRESS: RETURNED_ADDRESS})
        self.assertEqual(report['bindings'][0]['sprite_ownership'], 'no_match')

    def test_invalid_slot_and_native_rejection_stay_unknown(self):
        for slot in (0, 256, 0xffffffff):
            with self.subTest(slot=slot):
                row = correlate_capture(
                    make_packet(), make_ram(slot=slot))['bindings'][0]
                self.assertEqual(row['resource_slot'], slot)
                self.assertEqual(row['preflight'], 'invalid_resource_slot')
                self.assertIsNone(
                    row['registers_if_native_writer_succeeds'])
        row = correlate_capture(
            make_packet(), make_ram(tbp0=0))['bindings'][0]
        self.assertEqual(row['preflight'],
                         'native_writer_rejects_descriptor')
        self.assertIsNone(row['registers_if_native_writer_succeeds'])

    def test_unknown_flags_do_not_get_guessed(self):
        row = correlate_capture(
            make_packet(filter_index=2), make_ram())['bindings'][0]
        self.assertEqual(row['preflight'], 'unverified_sampler_selector')
        self.assertIsNone(row['registers_if_native_writer_succeeds'])
        self.assertEqual(row['resource_slot'], 1)

    def test_null_and_unreadable_return_pointer(self):
        self.assertEqual(
            correlate_capture(make_packet(resource=0),
                              make_ram())['bindings'][0]['preflight'],
            'null_returned_pointer')
        self.assertEqual(
            correlate_capture(make_packet(resource=0x10000),
                              bytes(0x2000))['bindings'][0]['preflight'],
            'resource_object_outside_ram')
        ram = make_ram()
        truncated = ram[:ELF_DESCRIPTOR_TABLE]
        self.assertEqual(
            correlate_capture(make_packet(), truncated)['bindings'][0]['preflight'],
            'descriptor_outside_ram')

    def test_cache_uses_original_resource_pointer_and_all_four_bytes(self):
        self.assertEqual((CACHE_POINTER_ADDRESS, CACHE_FLAGS_ADDRESS),
                         (0x4fd40c, 0x4fd410))
        flags = (0, 1, 0, 0)
        self.assertFalse(binding_cache_decision(0, flags))
        self.assertIsNone(binding_cache_decision(RESOURCE_OBJECT, flags))
        self.assertFalse(binding_cache_decision(
            RESOURCE_OBJECT, flags, RESOURCE_OBJECT, flags))
        self.assertTrue(binding_cache_decision(
            RESOURCE_OBJECT + 4, flags, RESOURCE_OBJECT, flags))
        for index in range(4):
            changed = list(flags)
            changed[index] = 2
            self.assertTrue(binding_cache_decision(
                RESOURCE_OBJECT, changed, RESOURCE_OBJECT, flags))
        with self.assertRaises(ValueError):
            binding_cache_decision(RESOURCE_OBJECT, (0, 1))

    def test_rejects_unfounded_callback_returns_and_duplicate_sprites(self):
        with self.assertRaises(ValueError):
            correlate_capture(make_packet(), make_ram(), [],
                              {SPRITE_ADDRESS: RETURNED_ADDRESS})
        with self.assertRaises(ValueError):
            correlate_capture(make_packet(), make_ram(),
                              [SPRITE_ADDRESS, SPRITE_ADDRESS])
        with self.assertRaises(ValueError):
            correlate_capture(make_packet(), make_ram(),
                              [0x10000000])
        with self.assertRaises(TypeError):
            correlate_capture(make_packet(), bytearray(1024))

    def test_json_cli_with_synthetic_snapshot(self):
        script = Path(__file__).with_name('arika_menu_gs_correlation.py')
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            packet = directory / 'command.bin'
            ram = directory / 'ram.bin'
            packet.write_bytes(make_packet())
            ram.write_bytes(make_ram())
            completed = subprocess.run(
                [sys.executable, str(script), str(packet), str(ram),
                 '--sprite', hex(SPRITE_ADDRESS),
                 '--observed-return',
                 '%s:%s' % (hex(SPRITE_ADDRESS), hex(RETURNED_ADDRESS))],
                text=True, capture_output=True, check=True)
            result = json.loads(completed.stdout)
            self.assertEqual(result['bindings'][0]['sprite_ownership'],
                             'unique_match')


@unittest.skipUnless(os.environ.get('SDBZ_EU_BETA_ELF'),
                     'requires original EU-beta ELF with verified SHA256')
class NativeGsCorrelationElfTests(unittest.TestCase):
    def test_exact_resource_binding_and_cache_instruction_words(self):
        elf = Path(os.environ['SDBZ_EU_BETA_ELF']).read_bytes()
        self.assertEqual(
            hashlib.sha256(elf).hexdigest(),
            '80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0')
        def word(va):
            return struct.unpack_from('<I', elf, va - 0xfff80)[0]
        expected = {
            0x2fe938: 0x12200047,  # return early on null resource
            0x2fe940: 0x8f83e09c,  # cached resource pointer
            0x2fe944: 0x1071002c,  # compare cached resource
            0x2fe94c: 0xa386e0a0,  # cache 4 independent bytes
            0x2fe950: 0xa387e0a1,
            0x2fe954: 0xa388e0a2,
            0x2fe958: 0xa389e0a3,
            0x2fe970: 0xaf91e09c,  # cache new resource
            0x2fe994: 0x8f39004c,  # resource vtable +0x4c
            0x2fe998: 0x0320f809,  # JALR
            0x2fe9a4: 0xae020008,  # returned pointer in cmd +8
            0x2fea00: 0x1483ffd2,  # compare each cache byte
            0x2fea10: 0x1483ffce,
            0x2fea20: 0x1483ffca,
            0x2fea30: 0x1483ffc6,
            0x19b6b4: 0x8e820008,  # command returned pointer
            0x19b6bc: 0x8c440038,  # returned object texture ID
            0x10da84: 0x0c0430f8,  # resource ID -> GS writer
        }
        self.assertEqual(RESOURCE_RETURN_SLOT_OFFSET, 0x38)
        self.assertEqual(RESOURCE_VTABLE_RETURN_OFFSET, 0x4c)
        for va, opcode in expected.items():
            with self.subTest(va=hex(va)):
                self.assertEqual(word(va), opcode)


if __name__ == '__main__':
    unittest.main()
