"""EE 0x37B370 per-slot draw-write comparisons for Dragon Summoning.

Draw execution is intentionally isolated from the logical update/RNG stream.
The sprite vtable +0x10 (GS draw) is captured, not emulated.
"""
import json
from pathlib import Path
import struct
import unittest

from arika_menu_particles import c_dragon_particle_pool, f32
from menu_strip_oracle import c_strip_oracle, bits


NATIVE_DRAW_WORDS = [
    666763248, 4290707456, 2361589920, 274726928, 0,
    3300917404, 3299082240, 3301114000, 3298951172,
    3300982932, 1175191552, 1174610112, 1174474816,
    3837984784, 3837853716, 3837788184, 2363031552,
    2402877456, 52492297, 12591149, 3753836544,
    65011720, 666697744,
]


class c_test_rng:
    def __init__(self):
        self.m_state = 1

    def next(self):
        self.m_state = (
            self.m_state * 0x5851F42D4C957F2D + 1
        ) & 0xffffffffffffffff
        return (self.m_state >> 32) & 0x7fffffff

    def get_state(self):
        return self.m_state


class DragonParticleDrawTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = json.loads((Path(__file__).parent /
                             'research/main_menu_map.json').read_text())
        cls.spec = report['first_components']['particles']

    def test_native_draw_presentation_fields_and_inactive_gate(self):
        samples = (
            (True, 260.0, 8.0, 0.1, 0.0, 0.0, 16.0),
            (True, 512.0, 300.0, 0.5, 249.0, 6.5, 16.0),
            (True, -128.5, -39.25, 0.3125, -120.0, 5.0, 45.0),
            (True, 0.125, 0.875, 0.01, -0.25, 0.125, -10.0),
            (True, -0.0, 0.0, 0.0, 0.0, -0.0, 16.0),
            (False, 20.0, 30.0, 0.1, 2.0, 3.0, 16.0),
        )
        for active, x, y, dz, px, py, depth in samples:
            machine = c_strip_oracle(
                dict(draw_address=0x37b370, draw_words=NATIVE_DRAW_WORDS,
                     clock_address=0, clock_words=[]),
                [0, 0, 1, 1], 0, 0, 1, 1, 0, [0, 0])
            # The generic sprite-draw oracle expects a preceding UV
            # setter. 0x37B370 only writes presentation floats; its
            # preexisting sprite UV state is deliberately stubbed here.
            machine.m_rect = [0, 0, 1, 1]
            machine.m_registers[4] = 0x1500
            machine.m_registers[5] = 0x2000
            machine.m_registers[6] = 0x1000
            machine.m_floats[12] = bits(depth)
            machine.write_int(0x1000, 0x3000, 4)
            machine.write_int(0x3010, 0xf00010, 4)
            machine.write_int(0x10a0, int(active), 4)
            for off, value in (
                    (0x90, x), (0x94, y), (0x9c, dz),
                    (0x10, 99.0), (0x14, 98.0), (0x18, 97.0)):
                machine.write_float(0x1000 + off, value)
            machine.write_float(0x2000, px)
            machine.write_float(0x2004, py)
            machine.run(0x37b370)

            pool = c_dragon_particle_pool(self.spec, c_test_rng(), 239.0)
            for slot in pool.m_slots[1:]:
                slot['active'] = False
            slot = pool.m_slots[0]
            slot.update(active=active, x=x, y=y, depth_step=dz)
            before = pool.snapshot()
            geometry = pool.geometry((px, py), depth)
            self.assertEqual(before, pool.snapshot(),
                             'preview drawing cannot alter logical slots or RNG')
            self.assertEqual(len(machine.m_commands), int(active))
            self.assertEqual(len(geometry), int(active))
            for field, off, old in (
                    ('x', 0x10, 99.0),
                    ('y', 0x14, 98.0),
                    ('depth', 0x18, 97.0)):
                actual = machine.read_int(0x1000 + off, 4)
                if active:
                    self.assertEqual(actual, bits(
                        geometry[0]['geometry']['position'][
                            0 if field == 'x' else 1]
                        if field != 'depth' else
                        geometry[0]['geometry']['depth']))
                else:
                    self.assertEqual(actual, bits(old))
            if active:
                command = machine.m_commands[0]
                self.assertEqual([bits(v) for v in command['position']],
                                 [bits(v) for v in geometry[0][
                                     'geometry']['position']])
                self.assertEqual(bits(command['depth']),
                                 bits(geometry[0]['geometry']['depth']))

    def test_initially_seeded_draws_sorted_by_pool_index(self):
        pool = c_dragon_particle_pool(self.spec, c_test_rng(), 239.0)
        initial = pool.snapshot()
        draws = pool.geometry((0, 0), 16.0)
        self.assertEqual([item['slot'] for item in draws],
                         [0, 1, 2, 3, 4])
        self.assertEqual(pool.snapshot(), initial)
        pool.m_slots[0]['active'] = False
        pool.m_slots[2]['active'] = False
        self.assertEqual([item['slot'] for item in pool.geometry()],
                         [1, 3, 4])


if __name__ == '__main__':
    unittest.main()
