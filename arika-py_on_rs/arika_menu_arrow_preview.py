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


def arrow_direction(geometry):
    """Identify arrow orientation from the recovered atlas-0 UV rectangle.

    The ELF's vertical arrows occupy x=81..113; horizontal arrows occupy
    x=0..37. Mirrored UV endpoints identify up/down and left/right.
    """
    u0, v0, u1, v1 = geometry['uv_endpoints']
    if min(u0, u1) == 81 and max(u0, u1) == 113:
        return (0, -1) if v1 > v0 else (0, 1)
    if min(u0, u1) == 0 and max(u0, u1) == 37:
        return (-1, 0) if u1 > u0 else (1, 0)
    raise ValueError('unrecognised native arrow UV rectangle')


def bobbed_arrow_geometry(geometry, tick, amplitude=3.0, period=32.0):
    """Translate a copy along the arrow's direction of travel.

    This sinusoidal displacement remains an authored preview effect.
    It does not claim to reproduce the native 0x3753A0 animation curve.
    """
    direction_x, direction_y = arrow_direction(geometry)
    offset = amplitude * math.sin(2.0 * math.pi * tick / period)
    dx = direction_x * offset
    dy = direction_y * offset
    result = dict(geometry)
    result['vertices'] = [[x + dx, y + dy] for x, y in geometry['vertices']]
    if 'position' in geometry:
        result['position'] = [
            geometry['position'][0] + dx,
            geometry['position'][1] + dy,
            *geometry['position'][2:],
        ]
    if 'bounds' in geometry:
        left, top, right, bottom = geometry['bounds']
        result['bounds'] = [left + dx, top + dy, right + dx, bottom + dy]
    return result
