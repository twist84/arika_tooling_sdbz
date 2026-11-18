"""EU-beta stage kind-6 *hypothetical* switched/restored state previews.

All instructions are from exact EU-beta SLES_541.61. The actual game
may never reach the 0x240710 phase-1 gate for a particular object.
Input phase/event flags are explicitly hypothetical editor scenarios,
not recorded EE execution or complete destruction/collision handling.
"""
import hashlib
import struct

from arika_native_stage_controls import (
    ELF_BIAS, ELF_SHA256, FLAG_WORD_OFFSET, INITIAL_MASK,
    _descendants, inspect_native_initial_stage_state,
    native_initial_preview_hidden_nodes, native_stage_preview_hidden_nodes,
    verify_native_stage_control_elf,
)

# Original exact 32-bit MIPS instruction words. Avoid treating proximity to
# these functions as evidence that the game actually calls them in a run.
ELF_SWITCH_WORDS = {
    0x240710: 0x27BDFFD0,  # alternate state callback entry
    0x240720: 0x8C830054,  # lw v1,0x54(a0)
    0x240724: 0x10620003,  # beq v1,1,0x240734 (gate)
    0x240734: 0x8E03006C,  # primary object pointer
    0x240750: 0x34420300,  # primary: set 0x300
    0x240754: 0xAC620028,  # sw updated +0x28
    0x240764: 0x8E080070,  # secondary object pointer
    0x240788: 0x00831024,  # secondary: clear 0x300
    0x24078C: 0xAD020028,  # sw updated +0x28
    0x240838: 0x8E020054,  # phase/status counter
    0x240840: 0xAE020054,  # store incremented phase/status
    0x240910: 0x27BDFFE0,  # direct restore helper
    0x240928: 0x8D040028,  # primary object flag word
    0x240940: 0x00831024,  # primary: clear 0x300
    0x240944: 0xAD020028,  # sw updated +0x28
    0x240970: 0x34420300,  # secondary: set 0x300
    0x240974: 0xAC620028,  # sw updated +0x28
    0x2409F0: 0x27BDFFE0,  # distinct event callback
    0x240A00: 0x8C860024,  # object event flags
    0x240A04: 0x00C31024,  # bit 0x08000000 tested
    0x240A08: 0x1440000F,  # dispatch reset subpath if nonzero
    0x240A10: 0x30C20020,  # unrelated flag 0x20 subpath
    0x240A14: 0x1040000A,  # gate flag 0x20 subpath
    0x240A64: 0x2402FCFF,  # event reset clears primary
    0x240A6C: 0x00621024,
    0x240A70: 0xAC820028,
    0x240A9C: 0x34420300,  # event reset sets secondary
    0x240AA0: 0xAC620028,
}

SCENARIO_NAMES = ('initial', 'switched', 'restored')
ALTERNATE_FUNCTION = 0x240710
RESTORE_FUNCTION = 0x240910
EVENT_FUNCTION = 0x2409F0
EVENT_RESET_FLAG = 0x08000000
EVENT_SECONDARY_FLAG = 0x20


def verify_native_stage_switch_elf(data):
    """Verify exact original executable and both previous/new opcode tables."""
    original = verify_native_stage_control_elf(data)
    if type(data) is not bytes or hashlib.sha256(data).hexdigest() != ELF_SHA256:
        raise ValueError('exact EU-beta ELF SHA-256 required')
    for address, expected in ELF_SWITCH_WORDS.items():
        offset = address - ELF_BIAS
        if offset < 0 or offset + 4 > len(data):
            raise ValueError('stage state-switch opcode outside mapped ELF')
        if struct.unpack_from('<I', data, offset)[0] != expected:
            raise ValueError('stage state-switch opcode mismatch at 0x%08X' %
                             address)
    return {
        'verified_initial_words': original['verified_original_instruction_words'],
        'verified_switch_words': len(ELF_SWITCH_WORDS),
        'initial_flag_mask': INITIAL_MASK,
        'original_runtime_executed': False,
    }


def inspect_native_stage_event_callback(object_flags, supplied_a1=None):
    """Classify 0x2409F0's entry gate, not the caller/GS/collision effects.

    Bit 0x08000000 selects a reset subpath. Otherwise bit 0x20 may invoke
    helpers 0x1ABD30 / 0x1ABD70 with a mask of 0x10 depending on a1.
    Those helpers are NOT interpreted as a collision or render toggle here.
    """
    if type(object_flags) is not int or not 0 <= object_flags <= 0xFFFFFFFF:
        raise ValueError('object flags must be unsigned 32-bit')
    if supplied_a1 is not None and type(supplied_a1) is not bool:
        raise ValueError('supplied a1 condition must be bool/None')
    reset = bool(object_flags & EVENT_RESET_FLAG)
    other = not reset and bool(object_flags & EVENT_SECONDARY_FLAG)
    return {
        'function': EVENT_FUNCTION,
        'object_flags': object_flags,
        'reset_mask_path': reset,
        'initial_mask_assignment_eligible': reset,
        'secondary_mask_helper_eligible': other,
        'secondary_mask_helper': (
            (0x1ABD30 if supplied_a1 else 0x1ABD70)
            if other and supplied_a1 is not None else None),
        'helper_mask': 0x10 if other else None,
        'native_event_executed': False,
        'render_or_collision_effect_proven': False,
    }


def inspect_native_stage_scenario(scene, scenario, assumed_phase_word=None):
    """Inspect original initial/switch/restore masks for live kind-6 controls.

    The phase+0x54==1 condition is mandatory for the 0x240710 switch.
    Without an explicitly supplied value of one, the switched outcome is
    unknown; hiding nothing is safer than claiming a hypothetical branch ran.
    All simulated outcomes are static previews, NOT recorded native events.
    """
    if scenario not in SCENARIO_NAMES:
        raise ValueError('unknown stage kind-6 scenario')
    if assumed_phase_word is not None and (
            type(assumed_phase_word) is not int or
            not 0 <= assumed_phase_word <= 0xFFFFFFFF):
        raise ValueError('phase word must be unsigned 32-bit integer/None')
    initial = inspect_native_initial_stage_state(scene)
    if scenario == 'initial':
        return dict(
            initial, scenario='initial',
            native_callback=0x240290,
            requested_phase_word=assumed_phase_word,
            phase_gate_satisfied=True,
            gate_evidence='initial setter uses null-pointer guards',
            outcome_inferred_from_assumed_state=False,
            runtime_transition_observed=False,
        )
    eligible = scenario == 'restored' or assumed_phase_word == 1
    enabled_role = 'secondary' if scenario == 'switched' else 'primary'
    suppressed_role = 'primary' if scenario == 'switched' else 'secondary'
    source_function = (
        ALTERNATE_FUNCTION if scenario == 'switched' else RESTORE_FUNCTION)
    actions = []
    enabled_roots = set()
    suppressed_candidates = []
    warnings = list(initial['conflicts_or_unresolved'])
    if eligible:
        for action in initial['native_mask_actions']:
            role = action['role']
            target = action['target_node']
            operation = 'clear' if role == enabled_role else 'set'
            site = (
                (0x240788 if role == 'secondary' else 0x240750)
                if scenario == 'switched'
                else (0x240940 if role == 'primary' else 0x240970))
            actions.append(dict(
                action, operation=operation, elf_instruction_site=site))
            if role == enabled_role:
                enabled_roots.add(target)
            elif role == suppressed_role:
                suppressed_candidates.append((action['controller_node'],
                                              target))
    elif scenario == 'switched':
        warnings.append(
            '0x240710 requires controller +0x54 == 1; no eligible '
            'switch outcome without that condition')
    suppressed = []
    for controller, target in suppressed_candidates:
        if _descendants(scene['nodes'], target) & enabled_roots:
            warnings.append(
                'control %d: suppressed target %d overlaps enabled target; '
                'preview not hidden' % (controller, target))
            continue
        if target not in suppressed:
            suppressed.append(target)
    hidden = set()
    for target in suppressed:
        hidden.update(_descendants(scene['nodes'], target))
    return {
        'scenario': scenario,
        'native_callback': source_function,
        'native_control_count': initial['native_control_count'],
        'native_mask_actions': actions,
        'preview_suppressed_root_nodes': sorted(suppressed),
        'preview_suppressed_stage_nodes': sorted(hidden),
        'conflicts_or_unresolved': warnings,
        'mask': INITIAL_MASK,
        'runtime_flag_offset': FLAG_WORD_OFFSET,
        'requested_phase_word': assumed_phase_word,
        'phase_gate_satisfied': eligible,
        'gate_evidence': (
            'original controller +0x54 == 1 required'
            if scenario == 'switched' else
            'restore helper invoked: no +0x54 branch in this routine'),
        'outcome_inferred_from_assumed_state': scenario == 'switched' and eligible,
        'runtime_transition_observed': False,
        'native_render_visibility_proven': False,
        'native_collision_suppression_proven': False,
        'preview_only': True,
    }


def native_stage_scenario_preview_hidden_nodes(
        scene, document, scenario='initial', assumed_phase_word=None):
    """Map a static scenario to the same exact glTF source offsets as M2."""
    if scenario == 'initial':
        preview = native_initial_preview_hidden_nodes(scene, document)
        result = inspect_native_stage_scenario(scene, scenario)
        preview['stage_state'] = result
        return preview
    state = inspect_native_stage_scenario(
        scene, scenario, assumed_phase_word=assumed_phase_word)
    return native_stage_preview_hidden_nodes(
        scene, document, state['preview_suppressed_root_nodes'], state)
