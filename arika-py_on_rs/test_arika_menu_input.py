"""Synthetic MIPS-field traces for EU-beta input helper semantics."""
import unittest

from arika_menu_input import (
    c_menu_pad_input, decode_menu_input, filter_opposite_directions,
    repeat_step, DIRECTION_MASKS,
)


class MenuInputTests(unittest.TestCase):
    def test_exact_elf_direction_helper_order(self):
        self.assertEqual(DIRECTION_MASKS, (8, 4, 1, 2))
        self.assertEqual(decode_menu_input(0xf), ('direction', 2))
        self.assertEqual(decode_menu_input(0xe), ('direction', 3))
        self.assertEqual(decode_menu_input(0xc), ('direction', 0))
        self.assertEqual(decode_menu_input(0x4), ('direction', 1))
        self.assertEqual(decode_menu_input(0xf, 0x40), ('confirm', None))
        self.assertEqual(decode_menu_input(0xff, 0x40, False), ('cancel', None))
        self.assertEqual(decode_menu_input(0, 0), ('none', None))

    def test_opposites_are_removed_before_priority(self):
        self.assertEqual(filter_opposite_directions(0xf), 0x5)
        self.assertEqual(filter_opposite_directions(0xc), 0x4)
        self.assertEqual(filter_opposite_directions(0x3), 0x1)
        self.assertEqual(filter_opposite_directions(0x41), 0x41)

    def test_native_repeat_counter_20_then_every_four(self):
        counter = 0
        hits = []
        for tick in range(1, 61):
            counter, repeated = repeat_step(counter, 0x4)
            if repeated:
                hits.append(tick)
        self.assertEqual(hits, list(range(20, 61, 4)))
        self.assertEqual(repeat_step(counter, 0), (0, 0))

    def test_menu_consumes_edges_not_auto_repeat(self):
        inp = c_menu_pad_input()
        events = []
        for tick in range(1, 61):
            frame = inp.step([{'held': 0x8, 'pressed': 0x8 if tick == 1 else 0}, {}])
            if decode_menu_input(inp.edge_mask(0))[0] == 'direction':
                events.append(tick)
            if tick == 20:
                self.assertEqual(inp.repeat_mask(0) & 0x8, 0x8)
                self.assertEqual(inp.edge_mask(0), 0)
        self.assertEqual(events, [1])
        self.assertEqual(inp.step([{}, {}])['pad_counter'], (0, 0))

    def test_analog_rising_edge_and_release(self):
        inp = c_menu_pad_input()
        frame = inp.step([{'analog_mask': 0x2}, {}])
        self.assertEqual(frame['pad_edge'], (2, 0))
        self.assertEqual(inp.step([{'analog_mask': 0x2}, {}])['pad_edge'], (0, 0))
        self.assertEqual(inp.step([{}, {}])['pad_edge'], (0, 0))
        self.assertEqual(inp.step([{'analog_mask': 0x2}, {}])['pad_edge'], (2, 0))

    def test_two_controller_aggregation_and_priority(self):
        inp = c_menu_pad_input()
        frame = inp.step([{'pressed': 2}, {'pressed': 1 | 4}])
        self.assertEqual(frame['pad_edge'], (2, 5))
        self.assertEqual(frame['aggregate_edge'], 5)
        self.assertEqual(inp.edge_mask(2), 5)
        self.assertEqual(decode_menu_input(inp.edge_mask(2)), ('direction', 2))
        self.assertEqual(decode_menu_input(inp.edge_mask(0)), ('direction', 3))
        self.assertEqual(decode_menu_input(inp.edge_mask(1)), ('direction', 2))

    def test_repeat_mask_is_edge_or_repeat_for_each_pad(self):
        inp = c_menu_pad_input()
        inp.step([{'held': 1, 'pressed': 1}, {}])
        self.assertEqual(inp.repeat_mask(0), 1)
        self.assertEqual(inp.edge_mask(0), 1)
        self.assertEqual(inp.step([{'held': 1}, {}])['pad_edge_or_repeat'][0], 0)
        for _ in range(18):
            frame = inp.step([{'held': 1}, {}])
        self.assertEqual(frame['pad_edge_or_repeat'][0], 1)
        self.assertEqual(frame['aggregate_edge_or_repeat'], 1)
        self.assertEqual(inp.edge_mask(0), 0)


if __name__ == '__main__':
    unittest.main()
