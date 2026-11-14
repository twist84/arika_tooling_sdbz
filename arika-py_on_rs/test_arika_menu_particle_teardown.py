"""EU-beta item-3 pool destructor and lifetime instruction regressions.

Source: SHA-256 verified SLES_541.61, 0x37A820, 0x37AF60, 0x37AD10.
The ELF and native game resources are not redistributed.
"""
import json
from pathlib import Path
import unittest

from arika_menu_particles import c_dragon_particle_pool
from menu_strip_oracle import c_strip_oracle


DESTRUCTOR = [
    666763248, 4290707456, 202238720, 0, 202238936, 4202541,
    202238788, 0, 3753836544, 65011720, 666697744,
]
POOL_DESTROY = [
    666763248, 4290707456, 2407852276, 276824069, 0,
    2358838304, 2402877448, 52492297, 604307457, 3753836544,
    65011720, 666697744,
]
SLOT_RESET_LOOP = [
    666763200, 4290707504, 2142371872, 2142306320, 8425517,
    2142240768, 34861, 37781549, 37756973, 202238996,
    33564717, 640745473, 706936838, 341901306, 638582960,
    3753836592, 2075263008, 2075197456, 2075131904,
    65011720, 666697792,
]


class c_test_rng:
    def __init__(self, state=1):
        self.m_state = state

    def next(self):
        self.m_state = (
            self.m_state * 0x5851F42D4C957F2D + 1
        ) & 0xffffffffffffffff
        return (self.m_state >> 32) & 0x7fffffff

    def get_state(self):
        return self.m_state


class DragonParticleTeardownTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = json.loads(
            (Path(__file__).parent / 'research/main_menu_map.json').read_text())
        cls.spec = report['first_components']['particles']
        cls.boundary = next(
            entry['value'] for entry in report['startup']['position_values']
            if entry['address'] == cls.spec['runtime_clip_boundary_address'])

    def make_pool(self):
        return c_dragon_particle_pool(
            self.spec, c_test_rng(1), self.boundary)

    def test_native_clip_boundary_constructor_writes_both_globals(self):
        """0x4E23B0 must store 204 and 239; the latter is a JR delay slot."""
        from menu_strip_oracle import bits
        initializer = [
            3347166088, 1006846240, 1149435904, 3347231632,
            1174407169, 3884116204, 65011720, 3883985136,
        ]
        oracle = c_strip_oracle(
            dict(draw_address=0x4e23b0, draw_words=initializer,
                 clock_address=0, clock_words=[]),
            [0, 0, 1, 1], 0, 0, 1, 1, 0, [0, 0])
        oracle.m_registers[28] = 0x4ff370
        oracle.write_float(0x4fa6f8, 249.0)
        oracle.write_float(0x4fa700, 204.0)
        oracle.write_float(0x4fdc5c, -999.0)
        oracle.write_float(0x4fdc60, -999.0)
        oracle.run(0x4e23b0)
        self.assertEqual(oracle.read_int(0x4fdc5c, 4), bits(204.0))
        self.assertEqual(oracle.read_int(0x4fdc60, 4), bits(239.0))

    def test_native_destructor_order_and_global_pointer_not_cleared(self):
        oracle = c_strip_oracle(
            dict(draw_address=0x37a820, draw_words=DESTRUCTOR,
                 clock_address=0x37ad10, clock_words=POOL_DESTROY),
            [0, 0, 1, 1], 0, 0, 1, 1, 0, [0, 0])
        oracle.m_code.update({
            0x37af60 + index * 4: word
            for index, word in enumerate(SLOT_RESET_LOOP)
        })
        oracle.m_registers[28] = 0x4ff370
        oracle.m_registers[4] = 0x7777
        # One global pool allocation, plus its vtable pointer at +0x420.
        oracle.write_int(0x4fdc64, 0x1000, 4)
        oracle.write_int(0x1420, 0x3000, 4)
        oracle.write_int(0x3008, 0xf00020, 4)

        events = []

        def reset_slot(machine):
            pointer = machine.m_registers[5]
            events.append(('reset', pointer))
            machine.write_int(pointer + 0xa0, 0, 4)
            machine.write_float(pointer + 0x98, 0)
            machine.write_float(pointer + 0x90, 0)
            machine.write_float(pointer + 0x94, 0)

        def destroy_allocation(machine):
            events.append(('destroy', machine.m_registers[4],
                           machine.m_registers[5]))

        oracle.m_direct_stubs = {
            0x37ac00: {2: 0x1000},
            0x37b050: reset_slot,
        }
        oracle.m_indirect_stubs = {0xf00020: destroy_allocation}

        for index in range(6):
            address = 0x1000 + index * 0xb0
            oracle.write_int(address + 0xa0, int(index < 5), 4)
            oracle.write_float(address + 0x98, 0.3)
        oracle.run(0x37a820)

        self.assertEqual(events, [
            ('reset', 0x1000 + index * 0xb0) for index in range(6)
        ] + [('destroy', 0x1000, 1)])
        self.assertEqual(oracle.read_int(0x4fdc64, 4), 0x1000,
                         'the native wrapper does not null the pointer')
        self.assertEqual(oracle.m_direct_calls.count(0x37b050), 6)
        self.assertEqual(oracle.m_direct_calls.count(0x37ad10), 1)

    def test_host_reset_invalidates_old_pool_without_rng_consumption(self):
        from arika_menu_runtime import c_menu_runtime

        runtime = c_menu_runtime(
            json.loads((Path(__file__).parent /
                        'research/main_menu_map.json').read_text()),
            particle_seed=1)
        old = runtime.m_particle_pool
        before = old.snapshot()
        runtime.reset()
        self.assertFalse(old.m_alive)
        self.assertFalse(old.snapshot()['alive'])
        self.assertEqual(old.snapshot()['total_random_draws'],
                         before['total_random_draws'])
        self.assertEqual(old.snapshot()['rng_state'], before['rng_state'])
        self.assertEqual(len(old.snapshot()['slots']), 6)
        self.assertTrue(all(not slot['active']
                            for slot in old.snapshot()['slots']))
        with self.assertRaisesRegex(RuntimeError, 'destroyed'):
            old.step(0)
        with self.assertRaisesRegex(RuntimeError, 'destroyed'):
            old.geometry()
        with self.assertRaisesRegex(RuntimeError, 'destroyed'):
            old.close()
        self.assertTrue(runtime.m_particle_pool.m_alive)
        self.assertIsNot(runtime.m_particle_pool, old)
        self.assertEqual(runtime.m_particle_pool.snapshot(), before)

    def test_pending_selection_does_not_destroy_pool(self):
        from arika_menu_runtime import c_menu_runtime

        runtime = c_menu_runtime(
            json.loads((Path(__file__).parent /
                        'research/main_menu_map.json').read_text()),
            particle_seed=1)
        old = runtime.m_particle_pool
        runtime._select(3)
        runtime._select(0)
        self.assertIs(runtime.m_particle_pool, old)
        self.assertTrue(old.m_alive)
        self.assertEqual(old.snapshot()['total_random_draws'], 15)


if __name__ == '__main__':
    unittest.main()
