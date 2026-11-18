"""Original ELF resource map tests; copyright-free fixtures for CI."""
import os
from pathlib import Path
import unittest

from arika_press_start_resources import (
    PRESS_START_RESOURCE_KEYS, PRESS_START_RESOURCE_POINTERS,
    PRESS_START_RESOURCE_HANDLES, PRESS_START_SPRITE_OFFSETS,
    PRESS_START_BACKGROUND_RECT, PRESS_START_FOREGROUND_SOURCE_RECT,
    PRESS_START_FOREGROUND_DEST_RECT, PRESS_START_THIRD_SOURCE_RECT,
    PRESS_START_BACKGROUND_RGBA, PRESS_START_RENDER_WORDS,
    recover_press_start_resource_evidence,
)


class PressStartResourceEvidenceTests(unittest.TestCase):
    def test_exact_three_resource_handles_and_sprite_offsets(self):
        self.assertEqual(PRESS_START_RESOURCE_KEYS, (
            'dis/d03/d03t0101', 'dis/d03/d03t0103', 'dis/d05/d05t0101'))
        self.assertEqual(PRESS_START_RESOURCE_POINTERS,
                         (0x4D7740, 0x4D7760, 0x4D7780))
        self.assertEqual(PRESS_START_RESOURCE_HANDLES,
                         (0x10, 0x14, 0x18))
        self.assertEqual(PRESS_START_SPRITE_OFFSETS,
                         (0x40, 0xA0, 0x100))
        self.assertEqual(PRESS_START_BACKGROUND_RECT, (0, 0, 512, 448))
        self.assertEqual(PRESS_START_FOREGROUND_SOURCE_RECT,
                         (0, 0, 257, 306))
        self.assertEqual(PRESS_START_FOREGROUND_DEST_RECT,
                         (128, 28, 257, 306))
        self.assertEqual(PRESS_START_THIRD_SOURCE_RECT, (15, 97, 17, 17))
        self.assertEqual(PRESS_START_BACKGROUND_RGBA, (.6, .6, .6, 1.0))
        self.assertGreaterEqual(len(PRESS_START_RENDER_WORDS), 20)

    def test_rejects_wrong_elf_without_claiming_recovery(self):
        with self.assertRaisesRegex(ValueError, 'EU-beta ELF'):
            recover_press_start_resource_evidence(b'invalid')

    def test_original_eu_beta_elf_if_available(self):
        path = os.environ.get('SDBZ_EU_BETA_ELF')
        if not path:
            self.skipTest('Original EU-beta ELF is not committed or in CI')
        evidence = recover_press_start_resource_evidence(
            Path(path).read_bytes())
        self.assertEqual(
            [row['resource_key'] for row in evidence['resource_bindings']],
            list(PRESS_START_RESOURCE_KEYS))
        self.assertEqual(evidence['background']['initial_rgba'],
                         [.6, .6, .6, 1.0])
        self.assertGreaterEqual(evidence['verified_render_words'], 20)
        self.assertTrue(evidence['unverified'])


if __name__ == '__main__':
    unittest.main()
