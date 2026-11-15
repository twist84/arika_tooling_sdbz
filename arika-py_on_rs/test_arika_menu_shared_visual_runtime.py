"""Outer shared draw clocks follow the recovered native child callbacks.

This composes the independently native-word-tested banner, seven small
sprites and two tile quads with the existing 0x377DE0 shared scheduler.
No diagnostic frame index is allowed to set a native child clock.
"""
import json
from pathlib import Path
import unittest

from arika_menu_runtime import c_menu_runtime
from arika_menu_banner import draw_banner, initialize_banner, step_banner
from arika_menu_small import initialize_small, step_small, draw_small
from arika_menu_tiles import tile_draw


class NativeSharedVisualRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(
            (Path(__file__).parent / 'research/main_menu_map.json').read_text())

    def make_runtime(self, seed=1):
        return c_menu_runtime(self.report, particle_seed=seed)

    def test_entry_callback_order_and_exact_child_progression(self):
        runtime = self.make_runtime()
        banner = initialize_banner(self.report['shared_banner'])
        small = [initialize_small() for _ in range(7)]
        self.assertEqual(runtime.snapshot()['banner']['offset'], (-512.0, 0.0))
        self.assertTrue(all(item['phase'] == 0
                            for item in runtime.snapshot()['small']))
        # 0x379A40 first updates shared children, THEN 0x379B50 starts
        # the parent; the following update invokes native 0x3786F0.
        initial = runtime.step()
        self.assertEqual(initial['shared_phase'], 1)
        self.assertEqual(initial['banner']['phase'], 0)
        second = runtime.step()
        self.assertEqual(second['banner']['phase'], 1)
        self.assertEqual(second['banner']['age'], 0.0)

        start_small = []
        for tick in range(65):
            prev = runtime.snapshot()
            result = runtime.step()
            roles = [event['event'] for event in result['calls']]
            self.assertEqual(roles[:4], [
                'shared_update', 'shared_update_banner',
                'shared_update_owner', 'shared_update_small'])
            for index in range(7):
                self.assertEqual(
                    result['small'][index]['phase'],
                    runtime.m_shared['small_phases'][index])
            for event in result['calls']:
                if event['event'] == 'shared_start_small':
                    start_small.append((tick, event['index']))
            if prev['banner']['phase'] != 0:
                expected = dict(phase=prev['banner']['phase'],
                                age=prev['banner']['age'],
                                offset=list(prev['banner']['offset']))
                step_banner(expected, self.report['shared_banner'])
                self.assertEqual(
                    result['banner'],
                    dict(phase=expected['phase'], age=expected['age'],
                         offset=tuple(expected['offset'])))
        self.assertEqual([index for _, index in start_small],
                         [0, 6, 3, 4, 1, 5, 2])
        self.assertTrue(all(item['phase'] == 2
                            for item in runtime.snapshot()['small']))
        self.assertEqual(runtime.snapshot()['banner']['phase'], 2)
        self.assertEqual(runtime.snapshot()['banner']['offset'], (0.0, 0.0))
        self.assertEqual(runtime.snapshot()['shared_phase'], 2)

    def test_native_shared_draw_uses_child_fields_not_timeline(self):
        runtime = self.make_runtime()
        for _ in range(60):
            runtime.step()
        before = runtime.snapshot()

        banner = runtime.shared_banner_geometry()
        self.assertEqual(
            banner, draw_banner(runtime.m_banner_state,
                                self.report['shared_banner']))
        self.assertEqual(banner['texture_entry'], 2)
        self.assertEqual(banner['depth'], 99)

        owner = runtime.m_companion_state
        tile_kernel = self.report['tile_scroll_kernel']
        native = runtime.shared_tile_geometry()
        reference = tile_draw(
            owner['phase'], tile_kernel['base_position'],
            owner['offset'], tile_kernel['uv_xywh'],
            tile_kernel['initial_depth'])
        self.assertEqual(len(native), 2)
        for actual, quad in zip(native, reference['quads']):
            self.assertEqual(actual['texture_entry'], 2)
            self.assertEqual(actual['geometry'], quad)
            self.assertEqual(actual['geometry']['depth'], 85)

        small = runtime.shared_small_geometry()
        expected = [
            draw_small(state, component)
            for state, component in zip(
                runtime.m_small_states,
                self.report['shared_small_animation']['components'])
            if state['phase'] != 0
        ]
        self.assertEqual(small, expected)
        self.assertEqual(len(small), 7)
        self.assertEqual([item['piece'] for item in small], list(range(7)))
        self.assertTrue(all(item['texture_entry'] == 3 and
                            item['depth'] == 5 for item in small))
        for _ in range(3):
            self.assertEqual(runtime.shared_banner_geometry(), banner)
            self.assertEqual(runtime.shared_tile_geometry(), native)
            self.assertEqual(runtime.shared_small_geometry(), small)
        self.assertEqual(before, runtime.snapshot(),
                         'pure draw functions cannot step clocks or RNG')

    def test_tile_scroll_comes_from_owner_phase_even_when_no_companion_spawn(self):
        runtime = self.make_runtime()
        for _ in range(5):
            runtime.step()
        owner = runtime.m_companion_state
        self.assertEqual(owner['owner_phase'], 2)
        owner['timer'] = 500.0
        for slot in owner['slots']:
            slot['active'] = True
        owner['phase'] = 2047.0
        before = runtime.shared_tile_geometry()
        self.assertEqual(before[1]['geometry']['position'], [0.25, 320.0])
        rng = runtime.snapshot()['context_rng_state']
        runtime.step()
        after = runtime.shared_tile_geometry()
        self.assertEqual(owner['phase'], 0.0)
        self.assertEqual(after[1]['geometry']['position'], [512.0, 320.0])
        self.assertNotEqual(before, after)
        self.assertEqual(rng, runtime.snapshot()['context_rng_state'],
                         'non-expired owner event consumes no RNG')

    def test_exit_banner_and_reset_do_not_use_diagnostic_age(self):
        runtime = self.make_runtime()
        for _ in range(70):
            runtime.step()
        before = runtime.snapshot()
        self.assertEqual(before['shared_phase'], 2)
        runtime._begin_exit(True)
        self.assertEqual(runtime.snapshot()['shared_phase'], 3)
        state = runtime.step()
        self.assertEqual(state['banner']['phase'], 3)
        self.assertEqual(state['banner']['age'], 0.0)
        for _ in range(5):
            state = runtime.step()
        self.assertEqual(state['banner']['phase'], 0)
        self.assertEqual(state['banner']['offset'], (-256.0, 0.0))
        runtime.reset()
        reset = runtime.snapshot()
        self.assertEqual(reset['banner']['phase'], 0)
        self.assertEqual(reset['banner']['offset'], (-512.0, 0.0))
        self.assertTrue(all(x['phase'] == 0 for x in reset['small']))
        self.assertEqual(reset['shared_overlay_alpha'], 0.0)
        self.assertTrue(reset['shared_overlay_hidden'])

    def test_unseeded_runtime_tracks_banner_and_small_without_claiming_rng(self):
        runtime = self.make_runtime(seed=None)
        for _ in range(65):
            runtime.step()
        snapshot = runtime.snapshot()
        self.assertIsNone(snapshot['context_rng_state'])
        self.assertIsNone(snapshot['companions'])
        self.assertEqual(runtime.shared_tile_geometry(), [],
                         'unmodeled owner must not invent tile phase')
        self.assertEqual(snapshot['banner']['phase'], 2)
        self.assertEqual(len(runtime.shared_small_geometry()), 7)


if __name__ == '__main__':
    unittest.main()
