"""ELF-derived Press Start copyright and prompt atlas geometry tests."""
import os
from pathlib import Path
import unittest

from arika_press_start_copyright import (
    COPYRIGHT_LINES, COPYRIGHT_TEXT_TABLE, COPYRIGHT_TEXT_POINTERS,
    COPYRIGHT_FONT_SCALE, COPYRIGHT_SYMBOL_SOURCE,
    PRESS_START_CAPTURE_PROMPT_SOURCES,
    PRESS_START_COPYRIGHT_WORDS, native_copyright_draws,
    native_prompt_case_one, verify_press_start_copyright_elf,
)


class PressStartCopyrightTests(unittest.TestCase):
    def test_original_two_native_copyright_strings(self):
        self.assertEqual(COPYRIGHT_TEXT_TABLE, 0x4F9454)
        self.assertEqual(COPYRIGHT_TEXT_POINTERS, (0x4C9820, 0x4C9850))
        self.assertEqual(COPYRIGHT_LINES, (
            '1989 BIRD STUDIO/SHUEISHA, TOEI ANIMATION',
            '2006 NAMCO BANDAI GAMES'))
        self.assertAlmostEqual(COPYRIGHT_FONT_SCALE, .67, places=6)

    def test_exact_dark_shadow_white_text_and_symbol_draw_order(self):
        ops = native_copyright_draws()
        self.assertEqual([op['kind'] for op in ops],
                         ['text', 'text', 'text', 'text', 'sprite', 'sprite'])
        self.assertEqual(
            [(op['x'], op['y'], op['rgb']) for op in ops[:4]],
            [(88.0, 383.0, .25), (88.0, 400.0, .25),
             (86.0, 381.0, 1.0), (86.0, 398.0, 1.0)])
        self.assertEqual(
            [(op['source_rect'], op['dest_rect']) for op in ops[4:]],
            [(COPYRIGHT_SYMBOL_SOURCE, (68.0, 382.0, 17, 17)),
             (COPYRIGHT_SYMBOL_SOURCE, (68.0, 399.0, 17, 17))])
        faded = native_copyright_draws(.5)
        self.assertEqual(faded[4]['dest_rect'][1], 382.5)
        self.assertEqual(faded[5]['dest_rect'][1], 399.5)
        self.assertTrue(all(op['alpha'] == .5 for op in faded))

    def test_capture_prompt_case_one_source_and_destination(self):
        self.assertEqual(PRESS_START_CAPTURE_PROMPT_SOURCES, (
            (0, 357, 99, 30), (204, 357, 74, 30),
            (99, 357, 105, 30)))
        self.assertEqual(native_prompt_case_one(), (
            ((0, 357, 99, 30), (116.0, 344.0, 99.0, 30.0)),
            ((204, 357, 74, 30), (217.0, 344.0, 74.0, 30.0)),
            ((99, 357, 105, 30), (293.0, 344.0, 105.0, 30.0)),
        ))

    def test_alpha_rejects_unknown_or_unphysical_values(self):
        for value in (-1.0, 1.01, None, True, float('nan'),
                      float('inf'), '1'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                native_copyright_draws(value)

    def test_exact_elf_copyright_and_prompt_oracle(self):
        self.assertGreaterEqual(len(PRESS_START_COPYRIGHT_WORDS), 15)
        with self.assertRaisesRegex(ValueError, 'EU-beta ELF'):
            verify_press_start_copyright_elf(b'wrong region')
        path = os.environ.get('SDBZ_EU_BETA_ELF')
        if not path:
            self.skipTest('original EU beta ELF unavailable on CI')
        result = verify_press_start_copyright_elf(Path(path).read_bytes())
        self.assertEqual(tuple(result['strings']), COPYRIGHT_LINES)
        self.assertEqual(len(result['draws']), 6)


if __name__ == '__main__':
    unittest.main()
