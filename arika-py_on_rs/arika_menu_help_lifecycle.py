"""Stateful main-menu help-owner clocks recovered from the EU-beta ELF.

One step equals one native logical update. All curve knots and state
transitions are read from SLES_541.61; see research/NATIVE_MENU_HELP_DRAW.md.
No 140-frame diagnostic-timeline samples or wall-clock timers are involved.
"""
from arika_menu_help_native import _f32, HELP_SETTLED_COMPONENT_ORIGIN


# 0x37C020: the first 0x2C2C10 call uses 0x4FA778 / 0x4FA780.
HELP_ENTRY_TIMES = (10.0, 15.0)
HELP_ENTRY_OFFSETS = (224.0, 0.0)

# Second 0x2C2C10 call at 0x37C0C8, once age >= 15.
HELP_BOUNCE_TIMES = tuple(float(i) for i in range(13))
HELP_BOUNCE_OFFSETS = (
    0.0, 3.0, 6.0, 3.0, 0.0, 2.0, 4.0,
    2.0, 0.0, 1.0, 2.0, 1.0, 0.0,
)
HELP_ENTRY_COMPLETE = 27.0  # 15+12 from 0x37C058 / 0x37C098

# 0x37C0F0: 0x2C2C10 call uses 0x4FA788 / 0x4FA790.
HELP_EXIT_TIMES = (0.0, 5.0)
HELP_EXIT_OFFSETS = (0.0, 224.0)
HELP_EXIT_COMPLETE = 5.0


def initialize_help():
    """Initial unentered owner. Its constructor XY is not asserted here."""
    return {'phase': 0, 'age': 0.0, 'x': 0.0, 'y': 0.0}


def _set_phase(state, phase):
    """Derived vtable +0x40 / 0x37C160, including reset-on-phase writes."""
    state['phase'] = phase
    state['age'] = 0.0
    if phase == 1:
        # Native 0x37C194 writes Y=-448 in a jump delay slot.
        # The value of X remains unchanged until the first entry update.
        state['y'] = -448.0
    elif phase == 2:
        state['x'], state['y'] = HELP_SETTLED_COMPONENT_ORIGIN


def start_help(state):
    """vtable +0x08 (0x35F7C0) begins entry phase 1."""
    _set_phase(state, 1)


def exit_help(state):
    """vtable +0x10 (0x35F800) begins exit phase 3."""
    _set_phase(state, 3)


def _interpolate_native(times, values, t):
    """Piecewise-linear 0x2C2C10 for validated strictly increasing knots.

    Each individual EE FPU operation rounds to f32. This function is used
    only for finite fixed ELF arrays, not as an arbitrary generic spline.
    """
    t = _f32(t)
    for i in range(len(times) - 1):
        if times[i] <= t < times[i + 1]:
            delta = _f32(t - times[i])
            duration = _f32(times[i + 1] - times[i])
            fraction = _f32(delta / duration)
            value_delta = _f32(values[i + 1] - values[i])
            return _f32(values[i] + _f32(value_delta * fraction))
    return values[0] if t < times[0] else values[-1]


def step_help(state):
    """Vtable +0x14 / 0x35F820: one component update, not one paint."""
    phase = state['phase']
    if phase == 1:
        age = _f32(state['age'] + 1.0)
        state['age'] = age
        offset = _interpolate_native(
            HELP_ENTRY_TIMES, HELP_ENTRY_OFFSETS, age)
        if age >= HELP_ENTRY_TIMES[-1]:
            # The bounce is evaluated with t = age-15; sum in float32.
            bounce_age = _f32(age - HELP_ENTRY_TIMES[-1])
            bounce = _interpolate_native(
                HELP_BOUNCE_TIMES, HELP_BOUNCE_OFFSETS, bounce_age)
            offset = _f32(offset + bounce)
        state['x'] = HELP_SETTLED_COMPONENT_ORIGIN[0]
        state['y'] = _f32(HELP_SETTLED_COMPONENT_ORIGIN[1] + offset)
        if age >= HELP_ENTRY_COMPLETE:
            _set_phase(state, 2)
    elif phase == 3:
        age = _f32(state['age'] + 1.0)
        state['age'] = age
        offset = _interpolate_native(
            HELP_EXIT_TIMES, HELP_EXIT_OFFSETS, age)
        state['x'] = HELP_SETTLED_COMPONENT_ORIGIN[0]
        state['y'] = _f32(HELP_SETTLED_COMPONENT_ORIGIN[1] + offset)
        if age >= HELP_EXIT_COMPLETE:
            _set_phase(state, 0)


def help_draw_state(state):
    """Native vtable +0x1C gates panel and +0x20 gates FFON text."""
    return {
        'visible': state['phase'] != 0,
        'draw_text': state['phase'] == 2,
        'position': (state['x'], state['y']),
        'phase': state['phase'],
        'age': state['age'],
    }
