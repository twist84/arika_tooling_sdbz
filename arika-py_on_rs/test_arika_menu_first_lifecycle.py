"""Instruction differential of the EU-beta first-layer entry/exit callbacks.

Uses only MIPS words and constants independently extracted from the verified
ELF into research/main_menu_map.json; no game executable is included.
"""
import json
from pathlib import Path
import unittest

from arika_menu_children import (
    initialize_child, start_first, exit_first, emphasize_first, step_first,
    first_offset, draw_first_strip, translate_first_geometry,
)
from test_arika_menu_banner import c_banner_oracle
from menu_strip_oracle import bits


class c_first_oracle(c_banner_oracle):
    def __init__(self, report, component, age):
        super().__init__(report['shared_banner'])
        kernel = report['first_components']['animation']
        for function in kernel['functions'].values():
            self.m_code.update({
                function['address'] + i * 4: word
                for i, word in enumerate(function['words'])})
        for curve in (kernel['entry'], kernel['bounce'], kernel['exit']):
            for name in ('times', 'values'):
                for i, value in enumerate(curve[name]):
                    self.write_float(curve[name + '_address'] + i * 4, value)
        for i, value in enumerate(kernel['reset_position']):
            self.write_float(self.m_registers[28] - 0x29e0 + i * 4, value)
        for i, direction in enumerate(component['direction']):
            self.write_int(0x1018 + i, direction, 1)
        self.m_registers[4] = 0x1000
        self.write_float(0x1008, age)
        self.write_float(0x100c, 99.0)
        self.write_float(0x1010, 98.0)


class MenuFirstLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(
            (Path(__file__).parent / 'research/main_menu_map.json').read_text())
        cls.kernel = cls.report['first_components']['animation']

    def test_all_seven_entry_and_exit_offsets_match_native_mips(self):
        ages = [-1., 0., 1., 2., 4.5, 5., 6., 7., 12., 16.,
                16.5, 17., 18., 22., 32., 99999.]
        count = 0
        for component in self.kernel['components']:
            for age in ages:
                for fn, exiting, threshold in (
                    ('entry', False, 17.0), ('exit', True, 10.0)):
                    machine = c_first_oracle(self.report, component, age)
                    machine.run(self.kernel['functions'][fn]['address'])
                    offset = first_offset(age, component, self.kernel,
                                          exiting=exiting)
                    for i, value in enumerate(offset):
                        self.assertEqual(
                            bits(value), machine.read_int(0x100c + i * 4, 4),
                            (component['item'], fn, age, i))
                    self.assertEqual(
                        int(age >= threshold), machine.m_registers[2])
                    count += 1
        self.assertEqual(count, 7 * len(ages) * 2)

    def test_all_seven_first_start_and_exit_start_match_native(self):
        for component in self.kernel['components']:
            state = initialize_child()
            machine = c_first_oracle(self.report, component, 82.0)
            machine.run(self.kernel['functions']['start']['address'])
            start_first(state, component, self.kernel)
            self.assertEqual(state['phase'], 1)
            self.assertEqual(bits(state['age']), machine.read_int(0x1008, 4))
            self.assertEqual(bits(state['depth']), machine.read_int(0x1014, 4))
            for i, value in enumerate(state['offset']):
                self.assertEqual(bits(value), machine.read_int(0x100c + 4*i, 4))
            machine = c_first_oracle(self.report, component, 82.0)
            machine.run(self.kernel['functions']['exit_start']['address'])
            exit_first(state, self.kernel)
            self.assertEqual(state['phase'], 4)
            for address, value in ((0x1008, state['age']),
                                   (0x1014, state['depth']),
                                   (0x100c, state['offset'][0]),
                                   (0x1010, state['offset'][1])):
                self.assertEqual(bits(value), machine.read_int(address, 4))

    def test_native_strips_start_at_zero_and_advance_only_in_phase_two(self):
        for item in (0, 2, 4, 6):
            component = self.kernel['components'][item]
            strip = self.report['first_components']['groups'][item]['scroll_strip']
            state = initialize_child()
            start_first(state, component, self.kernel)
            self.assertEqual(state['strip_phase'], 0.0)
            for _ in range(16):
                step_first(state, component, self.kernel, strip)
            self.assertEqual(state['strip_phase'], 0.0)
            step_first(state, component, self.kernel, strip)
            self.assertEqual((state['phase'], state['age'],
                              state['strip_phase']), (2, 0.0, 0.0))
            self.assertTrue(draw_first_strip(state, item, self.report))
            step_first(state, component, self.kernel, strip)
            self.assertEqual(state['strip_phase'], 1.0)
            period = strip['parameters']['period']
            state['strip_phase'] = period - 1.0
            step_first(state, component, self.kernel, strip)
            self.assertEqual(state['strip_phase'], 0.0)
            # The native first-state phase 4 stops the strip clock.
            exit_first(state, self.kernel)
            step_first(state, component, self.kernel, strip)
            self.assertEqual(state['strip_phase'], 0.0)
            self.assertEqual(state['phase'], 4)

    def test_first_geometry_translation_does_not_mutate_diagnostic_reference(self):
        original = self.report['plain_sprite_geometry']['first_groups'][0]['parts'][0]['geometry']
        copied = translate_first_geometry(original, [-128., -128.])
        self.assertEqual(original['position'], [0, 0])
        self.assertEqual(copied['position'], [-128, -128])
        self.assertEqual(copied['vertices'][0], [-128, -128])
        self.assertEqual(original['vertices'][0], [0, 0])

    def test_dragon_first_rng_effect_is_explicitly_unresolved(self):
        component = self.kernel['components'][3]
        state = initialize_child()
        start_first(state, component, self.kernel)
        for _ in range(18):
            step_first(state, component, self.kernel)
        self.assertEqual(state['phase'], 2)
        self.assertTrue(state['particle_update_unresolved'])
        self.assertEqual(state['strip_phase'], 0.0)


if __name__ == '__main__':
    unittest.main()
