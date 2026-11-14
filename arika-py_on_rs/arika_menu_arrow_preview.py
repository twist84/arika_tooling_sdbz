"""Main-menu arrow layouts from the ELF, with preview-only idle bob.

The recovered base positions, UV rectangles, history variants, and the
40-tick interpolation curve are extracted from the EU beta ELF at 0x3753A0.
Only the binding of the native object's +0xB0 age to the editor's preview
timeline remains an unverified scheduling approximation.
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


# Native float tables referenced by the helper at ELF 0x003753A0:
# times @ 0x004A9E80 = (0, 10, 30, 40)
# values @ 0x004A9E90 = (0, 3, -3, 0)
# The object stores its animation clock as float at offset +0xB0.
NATIVE_ARROW_PERIOD = 40.0
NATIVE_ARROW_TIMES = (0.0, 10.0, 30.0, 40.0)
NATIVE_ARROW_VALUES = (0.0, 3.0, -3.0, 0.0)


def native_arrow_displacement(age):
    """Reconstruct 0x3753A0's fmod and four-key scalar interpolation.

    The MIPS routine calls the libm remainder at 0x185E50 and the scalar
    interpolation helper 0x2C2C10. This models their finite, nonnegative
    animation-age behavior; it does not infer the object's clock origin.
    """
    phase = math.fmod(float(age), NATIVE_ARROW_PERIOD)
    for index in range(len(NATIVE_ARROW_TIMES) - 1):
        start = NATIVE_ARROW_TIMES[index]
        finish = NATIVE_ARROW_TIMES[index + 1]
        if start <= phase < finish:
            fraction = (phase - start) / (finish - start)
            return (NATIVE_ARROW_VALUES[index] +
                    (NATIVE_ARROW_VALUES[index + 1] -
                     NATIVE_ARROW_VALUES[index]) * fraction)
    # Matches the interpolation helper's first-value fallback for a
    # negative fmod remainder (normal animation ages are nonnegative).
    return NATIVE_ARROW_VALUES[0]


def bobbed_arrow_geometry(geometry, tick):
    """Apply the native arrow displacement to a copy of the base quad.

    'tick' is an editor sample clock; the native component's +0xB0 age
    phase at the moment a menu opens is not yet runtime-verified.
    """
    direction_x, direction_y = arrow_direction(geometry)
    displacement = native_arrow_displacement(tick)
    dx = direction_x * displacement
    dy = direction_y * displacement
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
