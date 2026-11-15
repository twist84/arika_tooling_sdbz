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
    RESOURCE_MANAGER_GLOBAL_ADDRESS, RESOURCE_MANAGER_VTABLE,
    RESOURCE_MANAGER_ENTRY_COUNT, RESOURCE_RETURN_SLOT_OFFSET,
    RESOURCE_VTABLE_RETURN_OFFSET, binding_cache_decision,
    correlate_capture, resolve_resource_selector_from_ram,
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


def make_ram_with_manager(ready=True, manager_vtable=RESOURCE_MANAGER_VTABLE):
    ram = bytearray(make_ram())
    manager = 0x3000
    wrapper = 0x4000
    record = 0x5000
    table = 0x6000
    struct.pack_into('<I', ram, RESOURCE_MANAGER_GLOBAL_ADDRESS, manager)
    struct.pack_into('<II', ram, manager, manager_vtable, wrapper)
    struct.pack_into('<II', ram, wrapper + 4, int(ready), record)
    struct.pack_into('<I', ram, record + 0x34, table)
    struct.pack_into('<I', ram, table + 4 * 4, RESOURCE_OBJECT)
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

    def test_original_manager_selector_maps_to_sprite_resource_not_packet(self):
        ram = make_ram_with_manager()
        self.assertEqual(RESOURCE_MANAGER_GLOBAL_ADDRESS, 0x4fdc48)
        self.assertEqual(RESOURCE_MANAGER_ENTRY_COUNT, 13)
        entry = resolve_resource_selector_from_ram(ram, 4)
        self.assertEqual(entry['status'], 'resolved')
        self.assertEqual(entry['resource_object_pointer'], hex(RESOURCE_OBJECT))
        self.assertNotEqual(entry['resource_object_pointer'], hex(RETURNED_ADDRESS))
        report = correlate_capture(
            make_packet(), ram, [SPRITE_ADDRESS],
            resource_selectors=(2, 4, 11))
        self.assertEqual(len(report['selector_entries']), 3)
        self.assertEqual(report['selector_entries'][1]['matching_captured_sprites'],
                         [hex(SPRITE_ADDRESS)])
        self.assertEqual(report['selector_entries'][0]['status'], 'entry_null')
        self.assertEqual(report['selector_entries'][2]['status'], 'entry_null')
        # A selector match to the sprite's resource object alone DOES
        # NOT establish the vtable callback return / opcode-1 identity.
        self.assertEqual(report['bindings'][0]['sprite_ownership'], 'not_captured')

    def test_manager_missing_unready_mismatch_and_native_fallback(self):
        self.assertEqual(
            resolve_resource_selector_from_ram(make_ram(), 4)['status'],
            'manager_not_initialized')
        self.assertEqual(
            resolve_resource_selector_from_ram(make_ram_with_manager(False), 4)[
                'status'], 'wrapper_not_ready')
        self.assertEqual(
            resolve_resource_selector_from_ram(
                make_ram_with_manager(manager_vtable=0x12345678), 4)['status'],
            'unverified_manager_vtable')
        for index in (13, 42, 0xffffffff):
            with self.subTest(index=index):
                result = resolve_resource_selector_from_ram(
                    make_ram_with_manager(), index)
                self.assertEqual(result['status'], 'native_fallback_null')
                self.assertEqual(result['resource_object_pointer'], '0x0')
        with self.assertRaises(ValueError):
            resolve_resource_selector_from_ram(make_ram(), -1)
        with self.assertRaises(ValueError):
            resolve_resource_selector_from_ram(make_ram(), True)
        with self.assertRaises(TypeError):
            resolve_resource_selector_from_ram(bytearray(make_ram()), 4)

    def test_manager_partial_capture_does_not_fabricate_a_pointer(self):
        tiny = bytearray(RESOURCE_MANAGER_GLOBAL_ADDRESS + 4)
        struct.pack_into('<I', tiny, RESOURCE_MANAGER_GLOBAL_ADDRESS, 0x3000)
        result = resolve_resource_selector_from_ram(bytes(tiny), 4)
        self.assertEqual(result['status'], 'unverified_manager_vtable'
                         if len(tiny) > 0x3000 else 'manager_outside_ram')
        # Manager+4 points at wrapper outside a truncated capture.
        partial = bytearray(RESOURCE_MANAGER_GLOBAL_ADDRESS + 4)
        struct.pack_into('<I', partial, RESOURCE_MANAGER_GLOBAL_ADDRESS, 0x3000)
        struct.pack_into('<II', partial, 0x3000, RESOURCE_MANAGER_VTABLE, 0x700000)
        self.assertEqual(
            resolve_resource_selector_from_ram(bytes(partial), 4)['status'],
            'wrapper_outside_ram')
        partial = bytearray(make_ram_with_manager())
        struct.pack_into('<I', partial, 0x5000 + 0x34, 0xfffffffc)
        self.assertEqual(
            resolve_resource_selector_from_ram(bytes(partial), 4)['status'],
            'entry_outside_ram')

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
        # The static menu global and checked vtable prove this is a
        # 13-entry resource-manager selector, not a PIX atlas index.
        manager_words = {
            0x374de4: 0x8f82e8d8,
            0x374e3c: 0xae030000,
            0x374f14: 0x2402000d,
            0x3725f4: 0x8c990000,
            0x3725f8: 0x8f39000c,
            0x372604: 0x0202102b,
            0x372610: 0x8e390000,
            0x372618: 0x8f390010,
            0x37262c: 0x0c0bee64,
            0x372630: 0x8e240004,
            0x372634: 0x8c420034,
            0x372640: 0x8c420000,
            0x2fb990: 0x8c820004,
            0x2fb994: 0x30420001,
            0x2fb998: 0x10400002,
            0x2fb9a0: 0x8c820008,
            0x4f188c: 0x00374f10,
            0x4f1890: 0x00354870,
        }
        for va, opcode in manager_words.items():
            with self.subTest(manager_va=hex(va)):
                self.assertEqual(word(va), opcode)
        for va, opcode in expected.items():
            with self.subTest(va=hex(va)):
                self.assertEqual(word(va), opcode)


if __name__ == '__main__':
    unittest.main()
