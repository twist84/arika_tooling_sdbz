"""Main-menu arrow layouts from the ELF, with preview-only idle bob.

The recovered base positions, UV rectangles, and history variants are exact
to the saved research. The periodic bob is an authored visual approximation
until the arrow helper at 0x3753A0 is fully recovered.
"""
import math


def arrow_variant(item_index, previous_index):
    if item_index == 0:
        return int(previous_index == 2)
    if item_index == 2:
        return int(previous_index in (0, 1, 5))
    return 0


def arrow_parts(report, item_index, previous_index):
    items = report['arrow_baselines']['items']
    variant = arrow_variant(item_index, previous_index)
    return items[item_index]['variants'][variant]


def bobbed_arrow_geometry(geometry, tick, amplitude=3.0, period=32.0):
    """Make a translated copy without mutating cached ELF geometry."""
    offset = amplitude * math.sin(2.0 * math.pi * tick / period)
    result = dict(geometry)
    result['vertices'] = [[x, y + offset] for x, y in geometry['vertices']]
    if 'position' in geometry:
        result['position'] = [geometry['position'][0], geometry['position'][1] + offset]
    if 'bounds' in geometry:
        left, top, right, bottom = geometry['bounds']
        result['bounds'] = [left, top + offset, right, bottom + offset]
    return result
