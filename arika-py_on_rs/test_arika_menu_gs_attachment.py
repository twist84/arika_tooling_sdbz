"""Asset-free sprite->opcode1 sampler bridge tests with optional EU-beta ELF oracle."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from arika_menu_gs_attachment_elf import (
    MENU_START, MENU_STOP, ZERO_A2, ZERO_A3, ONE_A3, ZERO_A4,
    ZERO_A5, classify_literal_attachment_words, scan_menu_sprite_attachments,
)

from arika_menu_gs_attachment import (
    NATIVE_MENU_ATTACHMENT_SITES, NATIVE_SPRITE_MIN_SIZE,
    SAMPLER_PACKET_PRODUCER, SAMPLER_SETTER_ADDRESS,
    SPRITE_RESOURCE_OFFSET, SPRITE_SAMPLER_OFFSET, STATIC_ATTACHMENT_FLAGS,
    decode_sprite_sampler_flags, decode_sprite_sampler_snapshot,
    static_menu_attachment_initializers,
)


def snapshot(flags=(0, 1, 0, 0), resource=0x12345678):
    blob = bytearray(NATIVE_SPRITE_MIN_SIZE)
    struct.pack_into('<I', blob, SPRITE_RESOURCE_OFFSET, resource)
    blob[SPRITE_SAMPLER_OFFSET:SPRITE_SAMPLER_OFFSET + 4] = bytes(flags)
    return bytes(blob)


class NativeMenuSamplerAttachmentTests(unittest.TestCase):
    def test_known_initializers_have_file_backed_literal_args(self):
        self.assertEqual(NATIVE_MENU_ATTACHMENT_SITES, (
            (0x376034, 2, 'shared tile-owner sprite'),
            (0x378434, 2, 'shared main-menu banner'),
            (0x37a754, 11, 'Dragon item-3 embedded sprite'),
            (0x37bf0c, 4, 'help-panel frame sprite'),
        ))
        rows = static_menu_attachment_initializers()
        self.assertEqual(len(rows), 4)
        for row in rows:
            self.assertEqual(row['initializer_sampler_bytes'], [0, 1, 0, 0])
            self.assertEqual(row['initial_filter'], 'linear')
            self.assertEqual(row['initial_clamp_flag'], 1)
            self.assertIsNone(row['actual_gs_state'])
            self.assertIsNone(row['runtime_resource_pointer'])
        self.assertEqual((SAMPLER_SETTER_ADDRESS, SAMPLER_PACKET_PRODUCER),
                         (0x2fd8f0, 0x2fe920))
        self.assertEqual(STATIC_ATTACHMENT_FLAGS, (0, 1, 0, 0))

    def test_snapshot_preserves_independent_raw_sampler_bytes(self):
        for filter_selector in (0, 1, 2):
            for clamp_selector in (0, 1, 2):
                with self.subTest(filter_selector=filter_selector,
                                  clamp_selector=clamp_selector):
                    data = snapshot((7, filter_selector, clamp_selector, 9))
                    resolved = decode_sprite_sampler_snapshot(data)
                    self.assertEqual(
                        resolved['sprite_sampler_bytes'],
                        [7, filter_selector, clamp_selector, 9])
                    self.assertEqual(resolved['filter_selector'],
                                     filter_selector)
                    self.assertEqual(resolved['clamp_selector'],
                                     clamp_selector)
                    self.assertEqual(resolved['filter_flag'],
                                     filter_selector if filter_selector < 2
                                     else None)
                    self.assertEqual(resolved['clamp_flag'],
                                     (1, 0)[clamp_selector]
                                     if clamp_selector < 2 else None)
                    self.assertEqual(resolved['resource_pointer'],
                                     0x12345678)
                    self.assertTrue(resolved['resource_present'])
                    self.assertTrue(resolved['opcode1_possible'])

    def test_null_resource_cannot_emit_native_binding(self):
        data = decode_sprite_sampler_snapshot(snapshot(resource=0))
        self.assertFalse(data['resource_present'])
        self.assertFalse(data['opcode1_possible'])
        self.assertEqual(data['filter_flag'], 1)
        self.assertEqual(data['clamp_flag'], 1)
        # The sampler fields can be decoded, but no native TEX1 is
        # emitted via the null-resource path.

    def test_strict_literal_argument_classifier_never_guesses(self):
        self.assertEqual(
            classify_literal_attachment_words(ZERO_A2, ONE_A3, ZERO_A4,
                                              ZERO_A5), (0, 1, 0, 0))
        self.assertEqual(
            classify_literal_attachment_words(ZERO_A2, ZERO_A3, ZERO_A4,
                                              ZERO_A5), (0, 0, 0, 0))
        for words in (
            (0, ONE_A3, ZERO_A4, ZERO_A5),
            (ZERO_A2, 0x24070002, ZERO_A4, ZERO_A5),
            (ZERO_A2, ONE_A3, 0x24080002, ZERO_A5),
            (ZERO_A2, ONE_A3, ZERO_A4, 0),
        ):
            with self.subTest(words=words):
                self.assertIsNone(classify_literal_attachment_words(*words))
        with self.assertRaises(ValueError):
            scan_menu_sprite_attachments(bytes(256))

    def test_invalid_snapshot_and_unknown_flag_values(self):
        for data in (b'', bytes(NATIVE_SPRITE_MIN_SIZE - 1),
                     bytearray(NATIVE_SPRITE_MIN_SIZE)):
            with self.subTest(data_type=type(data)), self.assertRaises(ValueError):
                decode_sprite_sampler_snapshot(data)
        for flags in (None, '0000', (0, 1, 0), (-1, 1, 0, 0),
                      (0, 256, 0, 0), (False, 1, 0, 0)):
            with self.subTest(flags=flags), self.assertRaises(ValueError):
                decode_sprite_sampler_flags(flags)
        with self.assertRaises(ValueError):
            decode_sprite_sampler_flags((0, 1, 0, 0), -1)

    def test_cli_static_and_captured_sprite_output(self):
        script = Path(__file__).with_name('arika_menu_gs_attachment.py')
        with tempfile.TemporaryDirectory() as path:
            file = Path(path) / 'synthetic-sprite.bin'
            file.write_bytes(snapshot())
            result = subprocess.run(
                [sys.executable, str(script), str(file)],
                capture_output=True, text=True, check=True)
            decoded = json.loads(result.stdout)
            self.assertEqual(decoded['sprite_sampler_bytes'], [0, 1, 0, 0])
            self.assertEqual(decoded['texture_filter'], 'linear')
            static = subprocess.run(
                [sys.executable, str(script), '--static-menu'],
                capture_output=True, text=True, check=True)
            self.assertEqual(len(json.loads(static.stdout)), 4)


@unittest.skipUnless(os.environ.get('SDBZ_EU_BETA_ELF'),
                     'set SDBZ_EU_BETA_ELF for original instruction oracle')
class NativeAttachmentElfOracleTests(unittest.TestCase):
    def test_setter_producer_and_all_menu_initializer_immediates(self):
        elf = Path(os.environ['SDBZ_EU_BETA_ELF']).read_bytes()
        self.assertEqual(hashlib.sha256(elf).hexdigest(),
                         '80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0')

        def word(addr):
            return struct.unpack_from('<I', elf, addr - 0xfff80)[0]

        # Native generic sprite field writer +0x44/+0x48..+0x4B,
        # including the JR return delay slot at 0x2FD904.
        for addr, expected in (
            (0x2fd8f0, 0xac850044),
            (0x2fd8f4, 0xa0860048),
            (0x2fd8f8, 0xa0870049),
            (0x2fd8fc, 0xa088004a),
            (0x2fd900, 0x03e00008),
            (0x2fd904, 0xa089004b),
            (0x2fd084, 0x92260048),
            (0x2fd088, 0x92270049),
            (0x2fd08c, 0x9228004a),
            (0x2fd090, 0x9229004b),
            (0x2fd094, 0x0c000000 | (0x2fe920 >> 2)),
            (0x2fe980, 0xa6030002),
            (0x2fe984, 0xa6050004),
            (0x2fe988, 0xa2060006),
            (0x2fe98c, 0xa2070007),
        ):
            with self.subTest(address=hex(addr)):
                self.assertEqual(word(addr), expected)

        for addr, source_entry, _owner in NATIVE_MENU_ATTACHMENT_SITES:
            with self.subTest(site=hex(addr)):
                self.assertEqual(word(addr),
                                 0x0c000000 | (SAMPLER_SETTER_ADDRESS >> 2))
                self.assertEqual(word(addr - 0x0c), 0x0000302d)
                self.assertEqual(word(addr - 0x08), 0x24070001)
                self.assertEqual(word(addr - 0x04), 0x0000402d)
                self.assertEqual(word(addr + 0x04), 0x0000482d)
                # Entry selection is a literal in the earlier 0x3725E0 call.
                # Those call-site addresses are established per site below.
        # Scope is the bounded menu-relevant 0x370000..0x3B0000
        # direct-call region, not all source-ELF instructions.
        self.assertEqual((MENU_START, MENU_STOP), (0x370000, 0x3b0000))
        scan = scan_menu_sprite_attachments(elf)
        self.assertEqual(
            (scan['direct_setter_calls'], scan['literal_linear'],
             scan['literal_nearest'], scan['unclassified']),
            (77, 59, 7, 11))
        nearest = {int(site['callsite'], 16)
                   for site in scan['sites']
                   if site['initial_filter'] == 'nearest'}
        self.assertEqual(nearest, {
            0x370a6c, 0x370b7c, 0x370be4, 0x370c08,
            0x37c56c, 0x37c67c, 0x37d8d0,
        })
        by_site = {int(site['callsite'], 16): site
                   for site in scan['sites']}
        for addr, entry, owner in NATIVE_MENU_ATTACHMENT_SITES:
            self.assertEqual(by_site[addr]['initial_filter'], 'linear')
            self.assertEqual(by_site[addr]['known_resource_entry'], entry)
            self.assertEqual(by_site[addr]['known_owner'], owner)

        entry_literals = {
            0x376034: 0x376004,
            0x378434: 0x378404,
            0x37a754: 0x37a724,
            0x37bf0c: 0x37bedc,
        }
        for addr, entry, _ in NATIVE_MENU_ATTACHMENT_SITES:
            self.assertEqual(word(entry_literals[addr]),
                             0x24050000 | entry)


if __name__ == '__main__':
    unittest.main()
