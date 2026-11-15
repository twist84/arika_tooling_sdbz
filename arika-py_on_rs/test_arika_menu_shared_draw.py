"""Native 0x378170 shared compositor: exact callback and layer gates.

Uses 39 word-for-word EU-beta instructions. Embedded sprite/GS draws
and child functions are isolated stubs so only native ordering is claimed.
"""
import unittest

from menu_strip_oracle import c_strip_oracle


SHARED_DRAW_WORDS = [
    666763200, 4290707504, 2142371872, 2142306320, 8425517,
    2142240768, 2388197392, 2402877456, 52492297, 641990672,
    202236328, 641990912, 202234020, 641991040, 34861,
    37781549, 202234632, 2382627044, 640745473, 638582788,
    706936839, 341901306, 0, 2453864672, 274726915,
    0, 268435463, 3753836592, 2388197488, 2402877456,
    52492297, 641990768, 268500985, 0, 2075263008,
    2075197456, 2075131904, 65011720, 666697792,
]


class NativeSharedDrawOracleTests(unittest.TestCase):
    def test_native_background_banner_tiles_small_and_overlay_order(self):
        self.assertEqual(len(SHARED_DRAW_WORDS),
                         (0x37820c - 0x378170) // 4)
        for hidden in (True, False):
            machine = c_strip_oracle(
                dict(draw_address=0x378170,
                     draw_words=SHARED_DRAW_WORDS,
                     clock_address=0, clock_words=[]),
                [0, 0, 1, 1], 0, 0, 1, 1, 0, [0, 0])
            machine.m_registers[4] = 0x1000
            machine.write_int(0x1010, 0x3000, 4)
            machine.write_int(0x3010, 0xf00020, 4)
            machine.write_int(0x1070, 0x3100, 4)
            machine.write_int(0x3110, 0xf00024, 4)
            machine.write_int(0x10e0, int(hidden), 1)
            for i in range(7):
                machine.write_int(0x10e4 + i * 4, 0x4000 + i * 0x70, 4)
            events = []

            def background(oracle):
                events.append(('background', oracle.m_registers[4]))

            def banner(oracle):
                events.append(('banner', oracle.m_registers[4]))

            def tile_and_companions(oracle):
                events.append(('tiles_and_companions', oracle.m_registers[4]))

            def small(oracle):
                events.append(('small', oracle.m_registers[4]))

            def overlay(oracle):
                events.append(('overlay', oracle.m_registers[4]))

            machine.m_indirect_stubs = {
                0xf00020: background,
                0xf00024: overlay,
            }
            machine.m_direct_stubs = {
                0x3786a0: banner,
                0x376290: tile_and_companions,
                0x376c20: small,
            }
            machine.run(0x378170)
            expected = [
                ('background', 0x1010),
                ('banner', 0x1100),
                ('tiles_and_companions', 0x1180),
            ]
            expected.extend(
                ('small', 0x4000 + i * 0x70)
                for i in range(7))
            if not hidden:
                expected.append(('overlay', 0x1070))
            self.assertEqual(events, expected)
            self.assertEqual(
                machine.m_direct_calls,
                [0x3786a0, 0x376290] + [0x376c20] * 7)


if __name__ == '__main__':
    unittest.main()
