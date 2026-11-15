"""Cross-owner native RNG interleaving, using recovered update callbacks.

EU beta:
  0x379A40 -> 0x377DE0 shared update -> 0x376080 companion owner,
  then pending/selected item -> 0x373A10 -> 0x37A860 particle callback.
  0x377FB0 first shared-entry callback invokes 0x376390 start-owner.
Context seed 1 is an explicit isolated replay input, NOT a captured seed.
"""
import json
from pathlib import Path
import unittest

from arika_menu_rng import c_native_rng
from arika_menu_runtime import c_menu_runtime


class DragonCompanionRngTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(
            (Path(__file__).parent / 'research/main_menu_map.json').read_text())

    def make_runtime(self):
        return c_menu_runtime(self.report, particle_seed=1)

    def test_one_shared_rng_and_entry_callback_order(self):
        runtime = self.make_runtime()
        pool = runtime.m_particle_pool
        self.assertIsNotNone(pool)
        self.assertIs(pool.m_rng, runtime.m_context_rng)
        self.assertIsNotNone(runtime.m_companion_state)
        self.assertEqual(runtime.snapshot()['companions'][
            'total_random_draws'], 0)
        self.assertEqual(pool.snapshot()['total_random_draws'], 15)
        reference = c_native_rng(1)
        first_fifteen = [reference.next() for _ in range(15)]
        self.assertEqual(runtime.m_context_rng.get_state(),
                         reference.get_state())
        self.assertEqual(
            [value for _, value in pool.snapshot()['random_draws']],
            first_fifteen)

        # 0x379A40 does not start the shared owner until the second
        # parent callback. The owner itself first receives an inactive
        # update, then an entry update, then an active event.
        runtime.step()
        self.assertEqual(runtime.m_companion_state['owner_phase'], 0)
        runtime.step()
        self.assertEqual(runtime.m_companion_state['owner_phase'], 1)
        runtime.step()
        self.assertEqual(runtime.m_companion_state['owner_phase'], 2)
        self.assertEqual(runtime.m_companion_total_draws, 0)
        runtime.step()
        comp = runtime.companion_snapshot()
        self.assertEqual(comp['owner_phase'], 2)
        self.assertEqual(comp['total_random_draws'], 4)
        self.assertEqual(comp['last_event']['spawned'], 0)
        self.assertEqual([role for role, _ in comp['random_draws']],
                         ['template', 'height', 'speed', 'timer'])
        self.assertEqual(
            [value for _, value in comp['random_draws']],
            [reference.next() for _ in range(4)])
        self.assertEqual(runtime.m_context_rng.get_state(),
                         reference.get_state())
        self.assertEqual(pool.snapshot()['total_random_draws'], 15)
        self.assertEqual(pool.snapshot()['rng_state'],
                         reference.get_state())

    def test_same_frame_companion_draws_precede_dragon_spawn(self):
        runtime = self.make_runtime()
        for _ in range(4):
            runtime.step()
        # Prepare an established shared phase-2, a free companion slot
        # and Dragon's item-3 first-component phase-2 callback. These
        # are native state fields, not authored wall-clock timings.
        runtime.m_shared['phase'] = 2
        runtime.m_selected = 3
        runtime.m_navigation.m_selected = 3
        runtime.m_outer_phase = 2
        runtime.m_item_phases[3] = 2
        first = runtime.m_first_states[3]
        first.update(phase=2, age=0.0, offset=[0.0, 0.0],
                     particle_timer=0.0, depth=15.0)
        runtime.m_companion_state['timer'] = 0.0

        # Every call to 0x190450 must be shared across the two owners.
        reference = c_native_rng(1)
        for _ in range(19):
            reference.next()
        companion_expected = [reference.next() for _ in range(4)]
        particle_expected = [reference.next() for _ in range(4)]

        state = runtime.step()
        comp = state['companions']
        pool = state['particles']
        self.assertEqual(comp['total_random_draws'], 8)
        self.assertEqual(pool['total_random_draws'], 19)
        self.assertEqual(
            [v for _, v in comp['random_draws']], companion_expected)
        self.assertEqual(
            [v for _, v in pool['random_draws']], particle_expected)
        self.assertEqual(comp['last_event']['spawned'], 1)
        self.assertTrue(pool['slots'][5]['active'])
        self.assertEqual(runtime.m_context_rng.get_state(),
                         reference.get_state())
        self.assertEqual(state['context_rng_state'], pool['rng_state'])

    def test_companion_draw_callback_matches_native_active_slot_writes(self):
        """Execute the native 0x376950 per-slot draw with a GS stub."""
        from arika_menu_companions import spawn_slot
        from menu_strip_oracle import c_strip_oracle, bits

        kernel = self.report['shared_companions']
        self.assertEqual(kernel['draw_address'], 0x376950)
        self.assertEqual(len(kernel['draw_words']), 16)
        runtime = self.make_runtime()
        samples = (
            (False, 0.0, 0.0, 86.0),
            (True, 576.0, 320.0, 86.0),
            (True, 250.25, 340.5, 87.0625),
            (True, -239.75, 300.25, 88.125),
            (False, 77.0, 88.0, 89.0),
        )
        for active, x, y, z in samples:
            machine = c_strip_oracle(
                dict(draw_address=kernel['draw_address'],
                     draw_words=kernel['draw_words'],
                     clock_address=0, clock_words=[]),
                [0, 0, 1, 1], 0, 0, 1, 1, 0, [0, 0])
            machine.m_registers[4] = 0x2000
            machine.m_registers[5] = 0x1000
            machine.write_int(0x1000, 0x3000, 4)
            machine.write_int(0x3010, 0xf00010, 4)
            machine.write_int(0x106c, int(active), 4)
            for off, value in ((0x60, x), (0x64, y),
                               (0x10, 11.0), (0x14, 22.0),
                               (0x18, z)):
                machine.write_float(0x1000 + off, value)
            machine.m_rect = [0, 0, 1, 1]
            machine.run(kernel['draw_address'])

            state = runtime.m_companion_state
            state['slots'] = [
                spawn_slot(kernel['templates'][0], 0, 0)
                if i == 0 else
                dict(active=False, uv_xywh=[0, 0, 0, 0],
                     x=0, y=0, depth=0, speed=0, template=None)
                for i in range(10)
            ]
            state['slots'][0].update(active=active, x=x, y=y, depth=z)
            before = runtime.snapshot()
            parts = runtime.companion_geometry()
            self.assertEqual(runtime.snapshot(), before)
            self.assertEqual(len(parts), int(active))
            self.assertEqual(len(machine.m_commands), int(active))
            if active:
                self.assertEqual([bits(v) for v in parts[0]['geometry']['position']],
                                 [machine.read_int(0x1010, 4),
                                  machine.read_int(0x1014, 4)])
                self.assertEqual(bits(parts[0]['geometry']['depth']),
                                 machine.read_int(0x1018, 4))
                self.assertEqual(parts[0]['texture_entry'], 2)
            else:
                self.assertEqual(machine.read_int(0x1010, 4), bits(11.0))
                self.assertEqual(machine.read_int(0x1014, 4), bits(22.0))

    def test_companion_draw_reads_ten_slots_in_index_order(self):
        from arika_menu_companions import spawn_slot

        runtime = self.make_runtime()
        kernel = runtime.m_companion_spec
        reference = runtime.snapshot()
        slots = runtime.m_companion_state['slots']
        for i in (0, 4, 9):
            slots[i] = spawn_slot(kernel['templates'][i % 3], 1, 32767)
        before = runtime.snapshot()
        quads = runtime.companion_geometry()
        self.assertEqual([q['slot'] for q in quads], [0, 4, 9])
        self.assertEqual([q['texture_entry'] for q in quads], [2, 2, 2])
        self.assertTrue(all(q['geometry']['vertices'] for q in quads))
        self.assertEqual(before, runtime.snapshot())
        self.assertEqual(before['context_rng_state'],
                         reference['context_rng_state'])
        self.assertEqual(runtime.companion_geometry(), quads)

    def test_snapshots_reset_and_missing_seed_do_not_fork_state(self):
        runtime = self.make_runtime()
        for _ in range(4):
            runtime.step()
        snap = runtime.snapshot()
        self.assertIsNotNone(snap['companions'])
        self.assertEqual(snap['context_rng_state'],
                         snap['particles']['rng_state'])
        snap['companions']['slots'][0]['x'] = 99999.0
        self.assertNotEqual(runtime.snapshot()['companions']['slots'][0]['x'],
                            99999.0)
        other = self.make_runtime()
        self.assertEqual(other.snapshot()['companions'][
            'total_random_draws'], 0)
        self.assertIsNot(other.m_context_rng, runtime.m_context_rng)
        runtime.reset()
        self.assertEqual(runtime.snapshot()['companions'][
            'total_random_draws'], 0)
        self.assertEqual(runtime.snapshot()['companions']['owner_phase'], 0)
        self.assertEqual(runtime.snapshot()['particles'][
            'total_random_draws'], 15)
        self.assertEqual(runtime.snapshot()['context_rng_state'],
                         other.snapshot()['context_rng_state'])
        # A request without a seed does not silently invent a global RNG.
        unseeded = c_menu_runtime(self.report)
        self.assertIsNone(unseeded.snapshot()['companions'])
        self.assertIsNone(unseeded.snapshot()['particles'])
        self.assertIsNone(unseeded.snapshot()['context_rng_state'])


if __name__ == '__main__':
    unittest.main()
