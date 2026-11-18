"""Pure, non-executing diagnostic view of the EU-beta EE app scheduler.

All branch/virtual-call evidence is in native_app_registry_eu_beta.json,
and independently checked by arika_native_app_extract against the exact ELF.
These helpers do NOT execute native app factories, callbacks, or transitions.
"""
import math
import struct

from arika_app_registry import APP_ENTRIES, APP_NATIVE_REGISTRY


LIFECYCLE = APP_NATIVE_REGISTRY['native_lifecycle']
NATIVE_SENTINEL_ID = LIFECYCLE['data_structure']['unregistered_sentinel']
NATIVE_PHASE_CALLBACKS = {
    callback['phase']: callback
    for callback in LIFECYCLE['phase_virtual_dispatch']
}


def _app(app_id):
    if type(app_id) is not int or app_id not in APP_ENTRIES:
        raise ValueError('expected registered native application ID 1..47')
    return APP_ENTRIES[app_id]


def _app_or_sentinel(app_id):
    if type(app_id) is not int or (
            app_id not in APP_ENTRIES and app_id != NATIVE_SENTINEL_ID):
        raise ValueError('expected app ID 1..47 or native 0x30 sentinel')
    return app_id


def _flags(flags):
    if type(flags) is not int or not 0 <= flags <= 255:
        raise ValueError('flags must be a byte')
    return flags


def _phase(phase):
    if type(phase) is not int or not 0 <= phase <= 6:
        raise ValueError('phase must be an EE lifecycle phase 0..6')
    return phase


def describe_native_phase(app_id, phase):
    """Map phases 2..5 to ELF-called vtable offsets for one exact app ID.

    A callback pointer identifies the *potential* target, not proof that
    the object's callbacks, resource loading or update have executed.
    """
    app = _app(app_id)
    phase = _phase(phase)
    call = NATIVE_PHASE_CALLBACKS.get(phase)
    if call is None:
        return None
    offset = call['vt_offset']
    callback = app['base_slots']['0x%02x' % offset]
    return {
        'app_id': app_id,
        'class_name': app['class_name'],
        'phase': phase,
        'vtable_address': app['base_vtable'],
        'virtual_offset': offset,
        'native_callsite': call['callsite'],
        'callback_address': callback,
        'callback_is_null': callback == 0,
        'guard': call['guard'],
        'callback_executed': False,
    }


def inspect_native_phase_gate(app_id, phase, callback_result, flags, status_word):
    """Resolve phase 2/3/4 success guards from explicitly supplied state.

    This does not invoke or assume the callback. It only evaluates whether
    a *supplied* result, flags and status would allow phase advancement.
    """
    _app(app_id)
    _phase(phase)
    _flags(flags)
    if phase not in (2, 3, 4):
        raise ValueError('phase gate is defined only for phases 2..4')
    if type(callback_result) is not bool:
        raise ValueError('callback result must be an observed boolean')
    if type(status_word) is not int or not 0 <= status_word <= 0xFFFFFFFF:
        raise ValueError('status word must be a 32-bit unsigned integer')
    advances = (callback_result and (flags & 2) == 0 and
                (status_word & 0x80000000) == 0)
    return {
        'app_id': app_id,
        'phase': phase,
        'next_phase': phase + 1 if advances else phase,
        'would_advance': advances,
        'callback_site': NATIVE_PHASE_CALLBACKS[phase]['callsite'],
        'reason': ('ready' if advances else
                   'callback_blocked' if not callback_result else
                   'transition_flag' if flags & 2 else 'status_busy'),
        'simulated_from_explicit_observations': True,
        'factory_executed': False,
    }


def inspect_native_transition_request(app_id, phase, flags, requested_id,
                                      child_id=NATIVE_SENTINEL_ID):
    """Model only the literal 0x3DFB00 phase switch and pending-ID writes.

    A request cannot be interpreted as completed factory dispatch. For
    phases 1..4, recursive sentinel propagation is contingent on an
    existing child lookup actually succeeding in the original runtime.
    """
    _app(app_id)
    _phase(phase)
    _flags(flags)
    _app_or_sentinel(requested_id)
    _app_or_sentinel(child_id)
    if flags & 1:
        return {
            'accepted': False, 'phase': phase, 'flags': flags,
            'pending_id': None, 'recursive_cancel_possible': False,
            'factory_executed': False, 'native_api': 0x3DFB00,
        }
    next_flags = flags & ~4
    if phase in (1, 2, 3, 4):
        next_phase = 5
        next_flags |= 2
        recursive = child_id != NATIVE_SENTINEL_ID
    else:
        next_phase = phase
        recursive = False
    return {
        'accepted': True, 'phase': next_phase, 'flags': next_flags,
        'pending_id': requested_id, 'recursive_cancel_possible': recursive,
        'recursive_cancel_value': NATIVE_SENTINEL_ID if recursive else None,
        'factory_executed': False, 'native_api': 0x3DFB00,
    }


def inspect_demo_main_exit(previous_choice, current_exit_target=3,
                           child_is_active=False, prior_exit_flag=False):
    """Inspect ID 6's *conditional* target field at original 0x3E09E0.

    Native initialization sets exit target +0x2A to 3. When a previous
    choice 1 finishes, its global exit flag is set without changing that
    field. Choice 3 instead sets target 6. This does not run a factory,
    infer a child's runtime state, or assert an exit actually happened.
    """
    if type(previous_choice) is not int or previous_choice not in range(4):
        raise ValueError('DemoMain previous choice must be 0..3')
    if type(current_exit_target) is not int or current_exit_target not in (3, 6):
        raise ValueError('DemoMain exit target must be native ID 3 or 6')
    if type(child_is_active) is not bool or type(prior_exit_flag) is not bool:
        raise ValueError('observed DemoMain child/exit flags must be boolean')
    elf = APP_NATIVE_REGISTRY['demo_main_exit']
    target = current_exit_target
    exit_flag = prior_exit_flag
    if not child_is_active:
        if previous_choice == 1:
            exit_flag = True
        elif previous_choice == 3:
            target = elf['alternate_target_id']
            exit_flag = True
    return {
        'source_id': 6,
        'previous_choice': previous_choice,
        'exit_target_field': elf['exit_target_byte'],
        'next_target_id': target,
        'native_request_id': target if exit_flag else None,
        'native_callsite': (elf['transition_callsite']
                            if exit_flag else None),
        'pending_global_exit_flag': exit_flag,
        'child_is_active_observed': child_is_active,
        'factory_executed': False,
        'native_condition_reconstructed_from_elf': True,
    }


def inspect_fight_result_child(selector, condition_for_single=None):
    """Describe ID 28's conditional child request at 0x0040BD0C.

    The external selector result must be observed; this does not invoke
    0x32A5E0, the 0x3EBCE0 subpredicate, or any child factory.
    Unrecognised signed integer selectors deliberately retain the native 0x30 sentinel.
    """
    if (type(selector) is not int or
            selector < -(1 << 31) or selector > (1 << 31) - 1):
        raise ValueError('FightResult selector must be a signed EE 32-bit value')
    if condition_for_single is not None and type(condition_for_single) is not bool:
        raise ValueError('FightResult selector subcondition must be boolean')
    target = NATIVE_SENTINEL_ID
    if selector == 1:
        if condition_for_single is None:
            return {
                'source_id': 28,
                'native_request_id': None,
                'candidate_child_ids': (29, 30),
                'selector': selector,
                'needs_external_subcondition': True,
                'native_callsite': 0x40BD0C,
                'factory_executed': False,
            }
        target = 30 if condition_for_single else 29
    elif selector == 2:
        target = 34
    elif selector == 3:
        target = 38
    return {
        'source_id': 28,
        'native_request_id': target,
        'candidate_child_ids': (target,) if target != NATIVE_SENTINEL_ID else (),
        'selector': selector,
        'needs_external_subcondition': False,
        'native_callsite': 0x40BD0C,
        'factory_executed': False,
    }


def inspect_native_child_forward(parent_id, parent_flags, child_id,
                                 requested_id, existing_child_resolved):
    """Examine the 0x3DFBD0 forwarded-ID path using *observed* lookup data.

    Resolving an existing child is provided by the caller; this code does
    not construct native objects, run factory lookups or execute callbacks.
    """
    _app(parent_id)
    _flags(parent_flags)
    _app_or_sentinel(child_id)
    _app_or_sentinel(requested_id)
    if type(existing_child_resolved) is not bool:
        raise ValueError('existing child resolution must be observed bool')
    if existing_child_resolved and child_id == NATIVE_SENTINEL_ID:
        raise ValueError('the native sentinel cannot resolve a child object')
    if parent_flags & 0x02:
        action = 'parent_transition_busy'
        forwarded = None
        stored = None
        flags = parent_flags
    elif existing_child_resolved:
        action = 'forward_to_existing_child'
        forwarded = requested_id
        stored = None
        flags = parent_flags & ~0x04
    else:
        action = 'store_new_child_id_and_attempt_lookup'
        forwarded = None
        stored = requested_id
        flags = parent_flags
    return {
        'parent_id': parent_id,
        'prior_child_id': child_id,
        'requested_id': requested_id,
        'action': action,
        'forwarded_request_id': forwarded,
        'parent_child_id_to_store': stored,
        'parent_flags_after_branch': flags,
        'native_child_helper': 0x003DFBD0,
        'existing_child_lookup_site': 0x003DFBFC,
        'forward_callsite': (0x003DFC1C if forwarded is not None else None),
        'child_store_site': (0x003DFC30 if stored is not None else None),
        'source_elf_verified': True,
        'factory_executed': False,
    }


def inspect_fight_demo_end_timeout(timer_after_update):
    """Check ID 25's float32 threshold branch from an observed timer value.

    The native callback can itself accumulate frame delta before this
    comparison. Supply the *post-update* duration; no frame timing is
    invented by this helper.
    """
    if isinstance(timer_after_update, bool) or not isinstance(
            timer_after_update, (int, float)):
        raise ValueError('timer must be a floating-point observation')
    threshold_bits = APP_NATIVE_REGISTRY['cancel_and_forward_dispatch'][
        'fight_demo_end_timeout']['threshold_float32_bits']
    threshold = struct.unpack('<f', struct.pack('<I', threshold_bits))[0]
    measured = float(timer_after_update)
    cancel = math.isnan(measured) or measured > threshold
    return {
        'app_id': 25,
        'post_update_timer': measured,
        'threshold_float32': threshold,
        'comparison_unordered': math.isnan(measured),
        'native_request_id': NATIVE_SENTINEL_ID if cancel else None,
        'native_callsite': 0x003E4C54 if cancel else None,
        'request_executed': False,
        'factory_executed': False,
    }


def inspect_fight_play_single_finish(state, predicate_nonzero=None):
    """Inspect ID 20's state-9 completion gate to sentinel 0x30.

    The state is a signed byte in the original EE app. The completion
    predicate comes from 0x2C0C20 and must be supplied by its observer
    only when state 9 is reached.
    """
    if type(state) is not int or not -128 <= state <= 127:
        raise ValueError('native state must be a signed byte')
    if predicate_nonzero is not None and type(predicate_nonzero) is not bool:
        raise ValueError('predicate must be an observed boolean or None')
    is_case_nine = state == 9
    need_predicate = is_case_nine and predicate_nonzero is None
    cancel = is_case_nine and predicate_nonzero is False
    return {
        'app_id': 20,
        'state': state,
        'state_9_case': is_case_nine,
        'needs_predicate_observation': need_predicate,
        'native_request_id': NATIVE_SENTINEL_ID if cancel else None,
        'predicate_callsite': 0x003E91D4 if is_case_nine else None,
        'native_callsite': 0x003E920C if cancel else None,
        'request_executed': False,
        'factory_executed': False,
    }


def describe_native_root_factory(requested_id):
    """Describe the original 0x3F1BA0 ID-indexed root factory branch.

    The native routine uses the low eight bits of its input, accepts
    1..47, initializes the registry and can call an actual factory via
    jalr at 0x3F1BE0. This function does NONE of those native operations.
    """
    if type(requested_id) is not int or not 0 <= requested_id <= 255:
        raise ValueError('root factory target must be an unsigned byte')
    root = APP_NATIVE_REGISTRY['native_root_factory_dispatch']
    app = APP_ENTRIES.get(requested_id)
    return {
        'requested_id': requested_id,
        'registered_target': app is not None,
        'class_name': app['class_name'] if app else None,
        'factory_address': app['factory'] if app else None,
        'factory_table_entry': (root['factory_table_base'] + 4 * requested_id
                                if app else None),
        'native_root_handoff_function': root['root_handoff_function'],
        'native_indirect_factory_callsite': (root['indirect_factory_callsite']
                                             if app else None),
        'fallback_pointer': (root['factory_fallback_pointer'] if app
                             else root['invalid_id_fallback_pointer']),
        'active_root_pointer_slot': root['active_root_pointer_slot'],
        'would_attempt_factory_if_native_path_runs': app is not None,
        'factory_executed': False,
        'active_root_pointer_written': False,
    }


def inspect_native_phase_five_root_handoff(
        app_id, parent_id, child_id, pending_id, flags, callback_result=None,
        status_word=0):
    """Inspect phase 5's root-vs-nested successor gate from supplied state.

    The original callback at base vtable +0x44 is allowed only without
    an active child, or with parent flag 0x04 set. On completion, the
    native scheduler calls 0x3F1BA0 for a sentinel parent, or changes a
    nested app to phase 6. No callback or factory is executed here.
    """
    _app(app_id)
    _app_or_sentinel(parent_id)
    _app_or_sentinel(child_id)
    _flags(flags)
    if type(pending_id) is not int or not 0 <= pending_id <= 255:
        raise ValueError('pending ID must be an unsigned native byte')
    if callback_result is not None and type(callback_result) is not bool:
        raise ValueError('phase 5 callback result must be observed bool/None')
    if type(status_word) is not int or not 0 <= status_word <= 0xFFFFFFFF:
        raise ValueError('status word must be a 32-bit unsigned integer')
    callback_eligible = (child_id == NATIVE_SENTINEL_ID or bool(flags & 4))
    eligible_result = callback_eligible and callback_result is True
    ready = eligible_result and (status_word & 0x80000000) == 0
    is_root = parent_id == NATIVE_SENTINEL_ID
    root = ready and is_root
    next_phase = 6 if ready and not is_root else 5
    return {
        'app_id': app_id,
        'phase': 5,
        'parent_id': parent_id,
        'child_id': child_id,
        'callback_eligible': callback_eligible,
        'needs_callback_observation': (callback_eligible and
                                       callback_result is None),
        'callback_virtual_offset': 0x44 if callback_eligible else None,
        'callback_callsite': 0x3DFDC0 if callback_eligible else None,
        'native_root_handoff_eligible': root,
        'native_root_handoff_callsite': 0x3DFF34 if root else None,
        'root_factory': (describe_native_root_factory(pending_id)
                         if root else None),
        'next_phase': next_phase,
        'factory_executed': False,
        'callback_executed': False,
    }


def inspect_native_child_successor(parent_id, child_id, child_phase,
                                   child_pending_id=NATIVE_SENTINEL_ID,
                                   parent_flags=0):
    """Inspect exact 0x3DFF60 child-completion routing without invoking it.

    If the active child is in phase 6, its pending ID becomes the
    parent's child ID and the completed child receives its teardown
    virtual call. A new child is only *eligible* for a subsequent lookup.
    """
    parent = _app(parent_id)
    _app_or_sentinel(child_id)
    _app_or_sentinel(child_pending_id)
    _phase(child_phase)
    _flags(parent_flags)
    if parent_flags & 4:
        outcome = 'parent_child_processing_suspended'
        next_child_id = child_id
        invoke_child_teardown = False
    elif child_id == NATIVE_SENTINEL_ID:
        outcome = 'no_active_child'
        next_child_id = child_id
        invoke_child_teardown = False
    elif child_phase != 6:
        outcome = 'child_not_complete'
        next_child_id = child_id
        invoke_child_teardown = False
    else:
        outcome = 'child_successor_selected'
        next_child_id = child_pending_id
        invoke_child_teardown = True
    return {
        'parent_id': parent_id,
        'parent_class': parent['class_name'],
        'previous_child_id': child_id,
        'next_child_id': next_child_id,
        'next_child_registered': next_child_id in APP_ENTRIES,
        'outcome': outcome,
        'invoke_child_teardown': invoke_child_teardown,
        'teardown_virtual_offset': 0x14 if invoke_child_teardown else None,
        'teardown_instruction_site': 0x3DFFB4 if invoke_child_teardown else None,
        'parent_child_id_store_site': (0x3DFFAC if invoke_child_teardown
                                       else None),
        'successor_factory_executed': False,
        'native_owner_function': 0x3DFF60,
    }
