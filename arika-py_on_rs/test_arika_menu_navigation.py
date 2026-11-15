"""Parity tests against the native seven-item menu graph recovered from ELF."""
import copy
import unittest

from arika_menu_navigation import (
    c_menu_navigation, read_menu_report, DIRECTION_MASKS, MENU_ITEM_NAMES,
)


class MenuNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m_report = read_menu_report()

    def test_direction_bits_and_initial_state(self):
        self.assertEqual(DIRECTION_MASKS, (8, 4, 1, 2))
        self.assertEqual(len(MENU_ITEM_NAMES), 7)
        navigation = c_menu_navigation()
        self.assertEqual((navigation.m_selected, navigation.m_previous), (0, -1))
        self.assertEqual([navigation.neighbor(i) for i in range(4)], [3, -1, -1, 1])

    def test_all_seven_previous_states_against_extracted_elf(self):
        for previous in range(7):
            for selected in range(7):
                navigation = c_menu_navigation(self.m_report)
                self.assertTrue(navigation.select(previous))
                self.assertTrue(navigation.select(selected))
                self.assertEqual((navigation.m_previous, navigation.m_selected),
                                 (previous, selected))
                entries = self.m_report['menu']['items'][selected]['neighbors']
                for direction, entry in enumerate(entries):
                    if 'value' in entry:
                        expected = entry['value']
                    elif entry['flag_offset'] == 0x710:
                        expected = entry['if_set' if previous == 2 else 'if_clear']
                    else:
                        self.assertEqual(entry['flag_offset'], 0x830)
                        expected = entry['if_set' if previous in (0, 1, 5) else 'if_clear']
                    with self.subTest(previous=previous, selected=selected, direction=direction):
                        self.assertEqual(navigation.neighbor(direction), expected)

    def test_selection_history_changes_right_and_left_targets(self):
        navigation = c_menu_navigation()
        self.assertTrue(navigation.move(3))  # 0 -> 1, previous 0
        self.assertTrue(navigation.move(0))  # 1 -> 2, previous 1
        self.assertTrue(navigation.move(2))  # 2 -> 0, previous 2
        self.assertEqual((navigation.m_selected, navigation.m_previous), (0, 2))
        self.assertEqual(navigation.neighbor(3), 2)  # not 1
        self.assertTrue(navigation.move(3))  # 0 -> 2, previous 0
        self.assertEqual(navigation.neighbor(0), 5)  # not 6
        self.assertEqual(navigation.neighbor(1), 1)  # not 4
        self.assertTrue(navigation.move(0))  # 2 -> 5
        self.assertEqual((navigation.m_selected, navigation.m_previous), (5, 2))

    def test_bad_inputs_and_blocked_moves_keep_history(self):
        navigation = c_menu_navigation()
        for index in (-1, 7, 42, '3'):
            self.assertFalse(navigation.select(index))
        self.assertEqual((navigation.m_selected, navigation.m_previous), (0, -1))
        for direction in (-5, 4, None):
            self.assertEqual(navigation.neighbor(direction), -1)
            self.assertFalse(navigation.move(direction))
        self.assertFalse(navigation.move(1))  # no left neighbour from 0
        self.assertEqual((navigation.m_selected, navigation.m_previous), (0, -1))

    def test_confirm_cancel_routes_are_non_destructive(self):
        navigation = c_menu_navigation()
        for item in self.m_report['menu']['items']:
            navigation.select(item['index'])
            route = navigation.route()
            self.assertFalse(route['cancelled'])
            self.assertEqual(route['mode_selector'], item['route']['mode_selector'])
            self.assertEqual(route['next_app_id'], item['route']['next_app_id'])
            self.assertEqual(navigation.route(cancelled=True),
                             {'mode_selector': None, 'next_app_id': 3, 'cancelled': True})
            self.assertEqual(navigation.m_selected, item['index'])
            self.assertEqual(navigation.text_lookup_id(), item['text_lookup_id'])
            self.assertEqual(navigation.help_lines(),
                             [line['text'] for line in item['help_text']['lines']])

    def test_rejects_corrupt_or_unverified_tables(self):
        report = copy.deepcopy(self.m_report)
        report['menu']['items'][0]['neighbors'][3]['flag_offset'] = 0x777
        with self.assertRaisesRegex(ValueError, 'flag'):
            c_menu_navigation(report)
        report = copy.deepcopy(self.m_report)
        report['menu']['items'][5]['neighbors'][3]['value'] = 99
        with self.assertRaisesRegex(ValueError, 'neighbor'):
            c_menu_navigation(report)
        report = copy.deepcopy(self.m_report)
        report['menu']['entry_count'] = 6
        with self.assertRaisesRegex(ValueError, 'seven'):
            c_menu_navigation(report)


if __name__ == '__main__':
    unittest.main()
