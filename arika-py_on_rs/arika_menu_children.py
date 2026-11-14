"""Instruction-grounded per-item child lifecycle for EU-beta native menu.

0x375630 dispatches first (0x373A10), character (0x37F100), label
(0x37DF90), in that order. The common first-group entry threshold in
0x373D60 is (gp-0x4DEC: 5.0) + (0x4A9DC0: 12.0) = 17.0.
First-group exit 0x373E60 completes at gp-0x4DCC = 10.0.
Character entry/exit use the times recovered in item_character_animation.
All seven phase-2 vtable callbacks +0x24 have their own periodic age; the
corresponding tested animation kernels are in character_idle. CUSTOMIZE's
secondary +0x1E8 clock remains uninitialized without an external observation.
The selected item's phase-4 completion check is 0x3756E0.

These ages count logical updates; they do not imply display-frame timings.
"""
from arika_menu_characters import character_offset
from arika_menu_emphasis import emphasis_offset
from arika_menu_layout import f32, pose_part
from arika_menu_banner import sample_curve
from arika_menu_idle import step_idle, step_circular_idle, step_dragon_idle


# Float values checked against the EU-beta SLES_541.61 instruction operands.
FIRST_ENTRY_AGE = f32(f32(5.0) + f32(12.0))
FIRST_EXIT_AGE = f32(10.0)


def initialize_child():
    return dict(phase=0, age=0.0, offset=[0.0, 0.0], depth=0.0)


def start_first(state):
    # 0x373BA0 -> first vtable+0x10 (0x373C50)
    state.update(phase=1, age=0.0)


def exit_first(state):
    # 0x373BC0 -> first vtable+0x18 (0x373D20)
    state.update(phase=4, age=0.0)


def emphasize_first(state):
    # 0x373BE0 -> first vtable+0x1C (0x373D40)
    state.update(phase=3, age=0.0)


def step_first(state):
    # 0x373A10 increments a float32 age before dispatching vtable callbacks.
    if state['phase'] == 0:
        return
    age = f32(state['age'] + 1.0)
    state['age'] = f32(age - 99999.0) if age > 99999.0 else age
    if state['phase'] == 1 and state['age'] >= FIRST_ENTRY_AGE:
        state.update(phase=2, age=0.0)
    elif state['phase'] == 4 and state['age'] >= FIRST_EXIT_AGE:
        state['phase'] = 0
    # Phase 2 callbacks differ by item; none are promoted to 4 here.
    # Phase 3 remains active until another request, as in 0x373A10.


def start_character(state, component, kernel):
    # 0x37F240 -> vtable+0x10 -> 0x37F2E0
    state.update(phase=1, age=0.0,
                 offset=character_offset(0.0, component, kernel),
                 depth=45.0)


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
            # 0x37F7F0 uses a second independent +0x1E8 float age.
            # Its construction-time value is not verified; reproduce only
            # the primary period and first part's unambiguous displacement.
            age = f32(state['age'] + 1.0)
            period = idle_component['curve']['times'][-1]
            if age >= period:
                age = f32(age - period)
            value = sample_curve(idle_component['curve'], age)
            offsets = [[value, value], [0.0, 0.0], [0.0, 0.0]]
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


def draw_character(state, item, report):
    """Native character pose (common component motion only, no authored clock).

    Per-part idle oscillation is deliberately not injected here until the
    character-local secondary clock and phase-2 callbacks have ELF parity.
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
        part_offsets = state.get('part_offsets', [])
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
