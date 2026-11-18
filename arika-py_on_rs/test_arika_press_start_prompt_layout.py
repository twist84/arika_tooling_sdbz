"""Offscreen and exact ELF regression tests for all prompt dispatch layouts."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
import unittest

from arika_press_start_prompt_layout import (
    PRESS_START_PROMPT_CASES, PRESS_START_PROMPT_CASE_ENTRY,
    PRESS_START_PROMPT_LAYOUT_WORDS, native_prompt_layout,
    verify_press_start_prompt_layout_elf,
)


class PressStartPromptLayoutTests(unittest.TestCase):
    def test_all_five_native_case_sources_and_destinations(self):
        expected = {
            0: [(154, 0, 99), (255, 99, 105)],
            1: [(116, 0, 99), (217, 204, 74), (293, 99, 105)],
            2: [(88, 278, 92), (182, 0, 39),
                (223, 80, 90), (315, 170, 110)],
            3: [(86, 278, 92), (180, 39, 41),
                (223, 80, 90), (315, 170, 110)],
            4: [(118, 278, 92), (212, 80, 90),
                (304, 170, 110)],
        }
        self.assertEqual(set(PRESS_START_PROMPT_CASES), set(range(5)))
        self.assertEqual(set(PRESS_START_PROMPT_CASE_ENTRY), set(range(5)))
        self.assertGreaterEqual(len(PRESS_START_PROMPT_LAYOUT_WORDS), 40)
        for case, triples in expected.items():
            with self.subTest(case=case):
                result = native_prompt_layout(case)
                self.assertEqual(len(result), len(triples))
                for (source, dest), (x, sx, width) in zip(result, triples):
                    self.assertEqual(source[0], sx)
                    self.assertEqual(source[2:], (width, 30))
                    self.assertEqual(dest, (float(x), 344.0,
                                            float(width), 30.0))
                    self.assertEqual(source[1],
                                     357 if case <= 1 or sx == 278 else 387)

    def test_selector_is_not_inferred_from_controller_or_clock(self):
        for case in (-1, 5, 42, True, 1.0, None, '1'):
            with self.subTest(case=case):
                with self.assertRaises(ValueError):
                    native_prompt_layout(case)

    def test_exact_eu_beta_elf_if_available(self):
        with self.assertRaisesRegex(ValueError, 'EU-beta ELF'):
            verify_press_start_prompt_layout_elf(b'invalid')
        path = os.environ.get('SDBZ_EU_BETA_ELF')
        if not path:
            self.skipTest('Original EU-beta ELF not committed into CI')
        report = verify_press_start_prompt_layout_elf(Path(path).read_bytes())
        self.assertEqual(len(report['cases']), 5)
        self.assertEqual(report['dispatch'], '0x3f7e10')
        self.assertEqual(report['cases'][3]['entry'], '0x3f8214')
        self.assertEqual(report['cases'][4]['quads'],
                         native_prompt_layout(4))


if __name__ == '__main__':
    unittest.main()
