"""Recovered seven-item SDBZ main-menu navigation and destination routing.

Data comes from the checked-in SLES_541.61 ELF extraction. This module models
selection-history-dependent neighbours and app routes, *not* the unverified
transition timing, raw controller input, fades, or application switching.
"""
import json
from pathlib import Path


MENU_ITEM_NAMES = (
    'Original', 'Z Survivor', 'Versus', 'Dragon Summoning',
    'Training', 'Customize', 'Options',
)

# Logical direction IDs from CMenuMainMenu::input (0x00379C80).
# The input helper masks (8,4,1,2) suggest right/left/up/down, but the
# physical controller mapping has not been verified in a runtime trace.
DIRECTION_NAMES = ('Right', 'Left', 'Up', 'Down')
DIRECTION_MASKS = (8, 4, 1, 2)

_ITEM_0_FLAG_OFFSET = 0x710
_ITEM_2_FLAG_OFFSET = 0x830


def read_menu_report(path=None):
    if path is None:
        path = Path(__file__).with_name('research') / 'main_menu_map.json'
    return json.loads(Path(path).read_text(encoding='utf-8'))


class c_menu_navigation:
    def __init__(self, report=None):
        if report is None:
            report = read_menu_report()
        menu = report['menu']
        items = menu['items']
        if menu['entry_count'] != 7 or len(items) != 7:
            raise ValueError('expected seven recovered main-menu items')

        for index, item in enumerate(items):
            if item['index'] != index or len(item['neighbors']) != 4:
                raise ValueError('invalid main-menu item / direction table')
            for neighbor in item['neighbors']:
                if 'value' in neighbor:
                    choices = (neighbor['value'],)
                else:
                    expected_offset = _ITEM_0_FLAG_OFFSET if index == 0 else (
                        _ITEM_2_FLAG_OFFSET if index == 2 else None)
                    if neighbor.get('flag_offset') != expected_offset:
                        raise ValueError('unexpected conditional neighbor flag')
                    choices = (neighbor['if_clear'], neighbor['if_set'])
                if any(not isinstance(value, int) or value < -1 or value >= 7
                       for value in choices):
                    raise ValueError('invalid native neighbor target')

        self.m_items = items
        self.m_selected = 0
        self.m_previous = -1

    def select(self, index):
        """Apply the native selection-history bookkeeping to an explicit item."""
        if not isinstance(index, int) or not 0 <= index < len(self.m_items):
            return False
        self.m_previous = self.m_selected
        self.m_selected = index
        return True

    def neighbor(self, direction):
        """Return the target index or -1 if that logical direction is blocked."""
        if not isinstance(direction, int) or direction < 0 or direction >= 4:
            return -1
        item = self.m_items[self.m_selected]
        entry = item['neighbors'][direction]
        if 'value' in entry:
            return entry['value']
        if self.m_selected == 0 and entry['flag_offset'] == _ITEM_0_FLAG_OFFSET:
            flag = self.m_previous == 2
        elif self.m_selected == 2 and entry['flag_offset'] == _ITEM_2_FLAG_OFFSET:
            flag = self.m_previous in (0, 1, 5)
        else:
            raise ValueError('unrecognized conditional menu neighbor')
        return entry['if_set' if flag else 'if_clear']

    def move(self, direction):
        """Navigate without altering previous-selection history on a failed move."""
        next_index = self.neighbor(direction)
        if next_index < 0:
            return False
        return self.select(next_index)

    def available_directions(self):
        return {DIRECTION_NAMES[index]: self.neighbor(index) for index in range(4)}

    def help_lines(self):
        return [line['text'] for line in self.m_items[self.m_selected]['help_text']['lines']]

    def text_lookup_id(self):
        return self.m_items[self.m_selected]['text_lookup_id']

    def route(self, cancelled=False):
        """Inspect the native exit destination; no app transition is performed."""
        if cancelled:
            return {'mode_selector': None, 'next_app_id': 3, 'cancelled': True}
        route = self.m_items[self.m_selected]['route']
        return {
            'mode_selector': route['mode_selector'],
            'next_app_id': route['next_app_id'],
            'cancelled': False,
        }
