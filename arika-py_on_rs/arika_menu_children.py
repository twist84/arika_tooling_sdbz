"""Instruction-grounded per-item child lifecycle for EU-beta native menu.

0x375630 dispatches first (0x373A10), character (0x37F100), label
(0x37DF90), in that order. The common first-group entry threshold in
0x373D60 is (gp-0x4DEC: 5.0) + (0x4A9DC0: 12.0) = 17.0.
First-group exit 0x373E60 completes at gp-0x4DCC = 10.0.
Character entry/exit use the times recovered in item_character_animation.
All seven phase-2 vtable callbacks +0x24 have their own periodic age; the
corresponding tested animation kernels are in character_idle. CUSTOMIZE's
secondary +0x1E8 clock is reset by its +0x14 active callback 0x37F7E0,
which runs at the end of character entry, before the first idle update.
The selected item's phase-4 completion check is 0x3756E0.

These ages count logical updates; they do not imply display-frame timings.
"""
from arika_menu_characters import character_offset
from arika_menu_emphasis import emphasis_offset
from arika_menu_layout import f32, pose_part
from arika_menu_banner import sample_curve
from arika_menu_idle import step_idle, step_coupled_idle, step_circular_idle, step_dragon_idle
from arika_menu_strips import step_phase, clipped_strip
from arika_menu_strip_preview import command_quad


# Float values checked against the EU-beta SLES_541.61 instruction operands.
FIRST_ENTRY_AGE = f32(f32(5.0) + f32(12.0))
FIRST_EXIT_AGE = f32(10.0)


def initialize_child():
    # Only the transition to character phase 2 establishes the secondary
    # clock's origin. Constructor contents prior to that are not assumed.
    return dict(phase=0, age=0.0, offset=[0.0, 0.0], depth=0.0,
                secondary_age=None, strip_phase=0.0)


def first_offset(age, component, kernel, exiting=False):
    """Common first-layer (+0x0C/+0x10) displacement recovered from ELF."""
    if not exiting and age >= FIRST_ENTRY_AGE:
        # 0x373E14 explicitly copies two +0.0 reset floats at completion.
        # Multiplying an interpolated +0.0 by direction -1 instead
        # produces -0.0; the EE callback overwrites that sign bit.
        return list(kernel['reset_position'])
    if exiting:
        value = sample_curve(kernel['exit'], age)
    else:
        value = sample_curve(kernel['entry'], age)
        delay = kernel['entry']['times'][-1]
        if age >= delay:
            value = f32(value + sample_curve(
                kernel['bounce'], f32(age - delay)))
    return [f32(value * direction)
            for direction in component['direction']]


def start_first(state, component, kernel):
    # 0x373BA0 -> vtable +0x10, 0x373C50:
    # sets age 0, z 45.0 and samples first approach at t=0 (128 units).
    state.update(phase=1, age=0.0,
                 offset=first_offset(0.0, component, kernel),
                 depth=45.0)


def exit_first(state, kernel):
    # 0x373BC0 -> +0x18, 0x373D20; preserves independent strip clock.
    state.update(phase=4, age=0.0,
                 offset=list(kernel['reset_position']), depth=15.0)


def emphasize_first(state, kernel):
    # 0x373BE0 -> +0x1C, 0x373D40; depth is not overwritten.
    state.update(phase=3, age=0.0,
                 offset=list(kernel['reset_position']))


def step_first(state, component, kernel, strip=None):
    # 0x373A10 increments the first child's +0x08 age before its callback.
    if state['phase'] == 0:
        return
    age = f32(state['age'] + 1.0)
    state['age'] = f32(age - 99999.0) if age > 99999.0 else age
    if state['phase'] == 1:
        state['offset'] = first_offset(state['age'], component, kernel)
        if state['age'] >= FIRST_ENTRY_AGE:
            state.update(phase=2, age=0.0,
                         offset=list(kernel['reset_position']))
    elif state['phase'] == 4:
        state['offset'] = first_offset(
            state['age'], component, kernel, exiting=True)
        if state['age'] >= FIRST_EXIT_AGE:
            state['phase'] = 0
    elif state['phase'] == 3:
        state['offset'], _ = emphasis_offset(
            state['age'], component['direction'], kernel['emphasis'])
    elif state['phase'] == 2:
        # 0x373AC8 -> subclass vtable +0x24. Four call 0x3740D0,
        # two return immediately; item 3 calls the particle/RNG updater,
        # which is intentionally kept separate from these deterministic
        # first-layer offsets.
        if component['item'] in (0, 2, 4, 6):
            if strip is None:
                raise ValueError('missing recovered first-layer strip kernel')
            state['strip_phase'] = step_phase(
                state['strip_phase'], strip['parameters']['period'])
        elif component['item'] == 3:
            state['particle_update_unresolved'] = True


def translate_first_geometry(geometry, offset):
    """Translate a recovered zero-offset first-layer quad in logical pixels."""
    if geometry is None:
        return None
    dx, dy = offset
    result = dict(geometry)
    if 'position' in geometry:
        result['position'] = [
            f32(geometry['position'][0] + dx),
            f32(geometry['position'][1] + dy)]
    if 'vertices' in geometry:
        result['vertices'] = [
            [f32(vertex[0] + dx), f32(vertex[1] + dy)]
            for vertex in geometry['vertices']]
    if 'bounds' in geometry:
        x0, y0, x1, y1 = geometry['bounds']
        result['bounds'] = [
            f32(x0 + dx), f32(y0 + dy), f32(x1 + dx), f32(y1 + dy)]
    return result


def draw_first_strip(state, item, report):
    """Current native strip clock and source geometry for four first groups."""
    if state['phase'] == 0:
        return []
    group = report['first_components']['groups'][item]
    strip = group.get('scroll_strip')
    if strip is None or strip.get('startup_origin') is None:
        return []
    offset = state['offset']
    origin = [f32(base + delta)
              for base, delta in zip(strip['startup_origin'], offset)]
    params = strip['parameters']
    commands = clipped_strip(
        strip['uv_xywh'], params['orientation'], params['start'],
        params['end'], params['period'], state['strip_phase'],
        origin, motion_offset=offset[0], depth=state['depth'])
    anchors = report['composite_layout']['anchors']
    rotation = report['strip_rotation_kernels']
    return [dict(texture_entry=group['texture_entry'],
                 geometry=command_quad(command, anchors, rotation))
            for command in commands['commands']]


def start_character(state, component, kernel):
    # 0x37F240 -> vtable+0x10 -> 0x37F2E0
    state.update(phase=1, age=0.0,
                 offset=character_offset(0.0, component, kernel),
                 depth=45.0, part_offsets=[])


def exit_character(state):
    # 0x37F260 -> vtable+0x18 -> 0x37F310
    state.update(phase=4, age=0.0, offset=[0.0, 0.0], depth=15.0)


def emphasize_character(state):
    # 0x37F280 -> vtable+0x1C -> 0x37F330
    state.update(phase=3, age=0.0, offset=[0.0, 0.0])


def step_character(state, component, kernel, emphasis_kernel=None,
                   idle_component=None):
    # 0x37F100 -> 0x37F350 entry, 0x37F3F0 exit, 0x37F460 emphasis.
    # The phase-2 vtable +0x24 is different for all seven characters.
    if state['phase'] == 2:
        if idle_component is None:
            # Never substitute the global diagnostic clock.
            return
        if component['callbacks'][7] != idle_component['address']:
            raise ValueError('native phase-2 character callback mismatch')
        kind = idle_component.get('kind')
        if kind is None:
            age, offsets = step_idle(state['age'], idle_component)
        elif kind == 'circular':
            age, offsets = step_circular_idle(state['age'], idle_component)
        elif kind == 'combined_circular':
            age, offsets = step_dragon_idle(state['age'], idle_component)
        elif kind == 'coupled':
            # 0x37F7E0 (+0x14 on CUSTOMIZE's character vtable) clears
            # +0x1E8 when phase 1 finishes. 0x37F7F0 then advances both
            # independent ages and all three part offsets. These kernels
            # have independent native-instruction oracle coverage.
            if state['secondary_age'] is None:
                raise ValueError('CUSTOMIZE phase 2 requires entry callback')
            age, secondary, offsets = step_coupled_idle(
                state['age'], state['secondary_age'], idle_component)
            state['secondary_age'] = secondary
        else:
            raise ValueError('unsupported native idle callback kind')
        state['age'] = age
        state['part_offsets'] = offsets
        return
    if state['phase'] not in (1, 3, 4):
        return
    age = f32(state['age'] + 1.0)
    state['age'] = f32(age - 99999.0) if age > 99999.0 else age
    if state['phase'] == 1:
        state['offset'] = character_offset(state['age'], component, kernel)
        threshold = f32(kernel['approach']['times'][-1] +
                        kernel['bounce']['times'][-1])
        if state['age'] >= threshold:
            state.update(phase=2, age=0.0, offset=[0.0, 0.0])
            if component['item'] == 5:
                if component['callbacks'][3] != 0x0037f7e0:
                    raise ValueError('CUSTOMIZE active callback mismatch')
                # 0x37F7E0: sw zero,+0x08(a0) and, in JR delay slot,
                # sw zero,+0x1E8(a0). This is not an assumed init value.
                state['secondary_age'] = 0.0
    elif state['phase'] == 4:
        state['offset'] = character_offset(
            state['age'], component, kernel, exiting=True)
        if state['age'] >= kernel['exit']['times'][-1]:
            state['phase'] = 0
    elif state['phase'] == 3:
        if emphasis_kernel is None:
            raise ValueError('character emphasis requires recovered kernel')
        state['offset'], _ = emphasis_offset(
            state['age'], component['direction'], emphasis_kernel)


def draw_character(state, item, report, include_idle=True):
    """Native common character and phase-2 per-part geometry.

    Both CUSTOMIZE clocks are instruction-backed; circular idle remains
    host-trigonometry approximate rather than bitwise EE libm.
    """
    if state['phase'] == 0:
        return []
    composite = report['composite_layout']['composites'][item]
    anchors = report['composite_layout']['anchors']
    result = []
    for index, part in enumerate(composite['parts']):
        offset = list(state['offset'])
        if item == 2 and index >= 4:
            offset = [-value for value in offset]
        part_offsets = state.get('part_offsets', []) if include_idle else []
        geometry = pose_part(
            composite, part, anchors, component_offset=offset,
            part_offset=(part_offsets[index]
                         if index < len(part_offsets) else [0.0, 0.0]),
            component_depth=state['depth'])
        geometry['depth'] = f32(state['depth'] + 15.0 +
                                part['placement'][2])
        result.append(dict(texture_entry=part['texture_entry'],
                           geometry=geometry))
    return result
