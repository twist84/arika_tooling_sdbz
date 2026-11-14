"""Ownership, RNG-order and repaint invariants for EU-beta six-slot particles.

Fixtures use the same ELF-derived template data as native main_menu_map.json.
A deterministic scalar RNG removes backend/DLL dependencies for pool tests.
"""
import json
from pathlib import Path
import unittest

from arika_menu_particles import c_dragon_particle_pool, random_unit, f32


class c_test_rng:
    def __init__(self, seed):
        self.m_state = seed & 0xffffffffffffffff

    def next(self):
        self.m_state = (
            self.m_state * 0x5851F42D4C957F2D + 1
        ) & 0xffffffffffffffff
        return (self.m_state >> 32) & 0x7fffffff

    def get_state(self):
        return self.m_state


class MenuDragonParticleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(
            (Path(__file__).parent / 'research/main_menu_map.json').read_text())
        cls.spec = cls.report['first_components']['particles']
        cls.clip = next(x['value'] for x in cls.report['startup']['position_values']
                        if x['address'] == cls.spec['runtime_clip_boundary_address'])

    def make_pool(self, seed=1):
        return c_dragon_particle_pool(self.spec, c_test_rng(seed), self.clip)

    def test_six_stable_slots_and_fifteen_initialization_rng_calls(self):
        pool = self.make_pool()
        state = pool.snapshot()
        self.assertEqual(len(state['slots']), 6)
        self.assertEqual(tuple(x['index'] for x in state['slots']), tuple(range(6)))
        self.assertEqual(tuple(x['active'] for x in state['slots']),
                         (True, True, True, True, True, False))
        self.assertEqual(state['total_random_draws'], 15)
        self.assertEqual(tuple(role for role, _ in state['random_draws']),
                         ('template', 'y', 'speed') * 5)
        for index, position in enumerate(self.spec['seed_positions']):
            self.assertEqual((state['slots'][index]['x'],
                              state['slots'][index]['y']), tuple(position))
        reference = c_test_rng(1)
        for _ in range(15):
            reference.next()
        self.assertEqual(pool.snapshot()['rng_state'], reference.get_state())

    def test_exact_first_spawn_and_timer_rng_order(self):
        pool = self.make_pool()
        before = pool.snapshot()
        timer = pool.step(0.0)
        state = pool.snapshot()
        self.assertEqual(state['total_random_draws'], 19)
        self.assertEqual(tuple(x[0] for x in state['random_draws']),
                         ('template', 'y', 'speed', 'timer'))
        self.assertTrue(state['slots'][5]['active'])
        self.assertEqual(state['slots'][5]['x'], 512.0)
        self.assertTrue(90.0 <= timer <= 210.0)
        for i in range(5):
            self.assertEqual(state['slots'][i]['x'],
                             f32(before['slots'][i]['x'] -
                                 before['slots'][i]['speed']))
        for _ in range(10):
            timer = pool.step(timer)
        self.assertEqual(pool.snapshot()['total_random_draws'], 19)
        self.assertTrue(pool.snapshot()['slots'][5]['active'])

    def test_full_pool_expiry_consumes_timer_rng_only(self):
        pool = self.make_pool()
        pool.step(0.0)
        before = pool.snapshot()
        timer = pool.step(0.0)
        after = pool.snapshot()
        self.assertEqual(after['total_random_draws'],
                         before['total_random_draws'] + 1)
        self.assertEqual(tuple(x[0] for x in after['random_draws']), ('timer',))
        self.assertGreater(timer, 0)

    def test_expiration_reuses_first_inactive_slot_with_three_rng_inputs(self):
        pool = self.make_pool()
        pool.step(0.0)
        pool.m_slots[1]['x'] = f32(self.clip - 1.0)
        pool.m_slots[1]['uv'][0] = pool.m_slots[1]['uv'][2] - 1
        pool.m_slots[1]['speed'] = 1.0
        # Native order: retire on the update pass, then reuse slot 1.
        before = pool.snapshot()['total_random_draws']
        pool.step(0.0)
        after = pool.snapshot()
        self.assertTrue(after['slots'][1]['active'])
        self.assertEqual(after['slots'][1]['x'], 512.0)
        self.assertEqual(tuple(x[0] for x in after['random_draws']),
                         ('template', 'y', 'speed', 'timer'))
        self.assertEqual(after['total_random_draws'], before + 4)
        self.assertEqual(tuple(s['index'] for s in after['slots']),
                         tuple(range(6)))

    def test_snapshot_and_geometry_are_nonowning_and_repeatable(self):
        pool = self.make_pool()
        before = pool.snapshot()
        geometry = pool.geometry(component_offset=[1.5, 2.5], depth=45.0)
        self.assertEqual(len(geometry), 5)
        self.assertEqual([p['slot'] for p in geometry], list(range(5)))
        self.assertEqual(pool.snapshot(), before)
        self.assertEqual(pool.geometry([1.5, 2.5], 45.0), geometry)
        self.assertEqual(pool.snapshot(), before)
        copy_of_old = pool.snapshot()
        pool.step(0.0)
        self.assertEqual(copy_of_old, before)
        self.assertNotEqual(pool.snapshot(), before)
        self.assertEqual(geometry[0]['geometry']['position'],
                         [f32(before['slots'][0]['x'] + 1.5),
                          f32(before['slots'][0]['y'] + 2.5)])

    def test_independent_instances_and_reset_replay(self):
        a, b, c = self.make_pool(1), self.make_pool(1), self.make_pool(2)
        self.assertEqual(a.snapshot(), b.snapshot())
        self.assertNotEqual(a.snapshot()['rng_state'],
                            c.snapshot()['rng_state'])
        clock_a = clock_b = 0.0
        for _ in range(250):
            clock_a = a.step(clock_a)
            clock_b = b.step(clock_b)
            self.assertEqual(clock_a, clock_b)
            self.assertEqual(a.snapshot(), b.snapshot())
        self.assertNotEqual(a.snapshot(), c.snapshot())
        self.assertEqual(self.make_pool(1).snapshot()['total_random_draws'], 15)

    def test_normalizer_matches_instruction_constant(self):
        self.assertEqual(random_unit(0), 0.0)
        self.assertEqual(random_unit(32767), 1.0)
        self.assertLess(random_unit(1), 1.0)


if __name__ == '__main__':
    unittest.main()
