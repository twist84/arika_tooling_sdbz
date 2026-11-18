"""Conservative, deterministic EU-beta kind-6 *diagnostic* runtime model.

This is not an EE interpreter. Only existing SHA-256-guarded instruction
effects are reproduced. The clock, external callback dispatch, GS and
collision flag consumers are NOT established; no invented timebase is used.
All target flag words are in-memory copies, never authored STG properties.
"""

from arika_native_stage_controls import (
    INITIAL_MASK, _descendants, inspect_native_initial_stage_state,
    native_stage_preview_hidden_nodes,
)
from arika_native_stage_state_switch import (
    ALTERNATE_FUNCTION, EVENT_FUNCTION, EVENT_RESET_FLAG,
    RESTORE_FUNCTION, inspect_native_stage_event_callback,
)

UINT32_MAX = 0xFFFFFFFF


def _word(value, description):
    if type(value) is not int or not 0 <= value <= UINT32_MAX:
        raise ValueError('%s must be an unsigned 32-bit integer' % description)
    return value


class c_native_stage_state_runtime:
    """A separate, opt-in record of verified mask and phase operations.

    A timer reaching the 0x2404B0 assignment cannot yet be derived from
    frame counts. observe_timer_ready() is therefore an explicitly labelled
    *diagnostic injection*, not a simulated native timer update.
    """

    def __init__(self, scene, initial_target_flags=None, countdown_sources=None):
        self.m_scene = scene
        self.m_initial = inspect_native_initial_stage_state(scene)
        self.m_actions = {}
        self.m_controllers = {}
        self.m_intents = {}
        self.m_target_flags = {}
        self.m_events = []
        self.m_unknowns = list(self.m_initial['conflicts_or_unresolved'])
        self.m_baseline = {}
        active = set()
        for root in (scene['effect_root'], scene['stage_root']):
            active.update(_descendants(scene['nodes'], root))
        for node in scene['nodes']:
            if node['index'] in active and 'state_control' in node:
                key = node['index']
                self.m_controllers[key] = {
                    'phase': 0, 'countdown_source': None, 'countdown': None,
                }
                self.m_actions[key] = []
                self.m_intents[key] = {}
        for action in self.m_initial['native_mask_actions']:
            self.m_actions[action['controller_node']].append(dict(action))
            self.m_target_flags.setdefault(action['target_node'], 0)
        supplied = initial_target_flags or {}
        if not isinstance(supplied, dict):
            raise ValueError('initial target flags must be a mapping')
        for key, value in supplied.items():
            if type(key) is not int or key not in self.m_target_flags:
                raise ValueError('initial flag target is not resolved')
            self.m_target_flags[key] = _word(value, 'target flags')
        self.m_baseline = dict(self.m_target_flags)
        sources = countdown_sources or {}
        if not isinstance(sources, dict):
            raise ValueError('countdown sources must be a mapping')
        for key, value in sources.items():
            self._controller(key)['countdown_source'] = _word(
                value, 'countdown source')
        self.reset_to_initial()

    def _controller(self, controller_node):
        if type(controller_node) is not int or controller_node not in self.m_controllers:
            raise ValueError('unknown kind-6 controller node')
        return self.m_controllers[controller_node]

    def _record(self, controller_node, event, pc, applied, reason=''):
        report = {
            'controller_node': controller_node, 'event': event,
            'pc': pc, 'applied': applied, 'reason': reason,
            'emulated_ee_execution': False,
        }
        self.m_events.append(report)
        return dict(report)

    def _assign_masks(self, controller_node, primary, secondary):
        # Preserve the original source-tree order and all other flag bits.
        for action in self.m_actions[controller_node]:
            target = action['target_node']
            operation = primary if action['role'] == 'primary' else secondary
            value = self.m_target_flags[target]
            self.m_target_flags[target] = (
                (value | INITIAL_MASK) if operation == 'set'
                else (value & (~INITIAL_MASK & UINT32_MAX)))
            self.m_intents[controller_node][target] = operation

    def reset_to_initial(self):
        """Editor reset: replay constructor phase and 0x240290 mask effects.

        This is a reset of diagnostic state, NOT a claim that the original
        0x240860 callback ran or that the native countdown had a zero value.
        """
        self.m_target_flags = dict(self.m_baseline)
        for key in self.m_controllers:
            self.m_controllers[key]['phase'] = 0
            self.m_controllers[key]['countdown'] = None
            self.m_intents[key] = {}
            self._assign_masks(key, 'clear', 'set')
        self.m_events = []
        return self.snapshot()

    def advance(self, frames=1):
        """Do not decrement a clock whose source or timebase is unverified."""
        if type(frames) is not int or frames < 1:
            raise ValueError('frames must be a positive integer')
        return {
            'applied': False, 'frames_requested': frames,
            'reason': '0x2403D0 countdown update predicate/timebase unresolved',
            'original_clock_emulated': False,
        }

    def observe_timer_ready(self, controller_node, diagnostic=False):
        """Inject only the proven +0x54=1 *effect*, not its unknown gate."""
        controller = self._controller(controller_node)
        if diagnostic is not True:
            return self._record(controller_node, 'timer_ready', 0x2404B0,
                                False, 'native timer predicate unresolved')
        controller['phase'] = 1
        return self._record(controller_node, 'timer_ready_diagnostic',
                            0x2404B0, True,
                            'forced branch outcome; native event unobserved')

    def switch(self, controller_node):
        """Invoke the vtable +0x18 callback's proven phase-1 path."""
        controller = self._controller(controller_node)
        if controller['phase'] != 1:
            return self._record(controller_node, 'switch', ALTERNATE_FUNCTION,
                                False, 'controller +0x54 != 1')
        self._assign_masks(controller_node, 'set', 'clear')
        controller['phase'] = (controller['phase'] + 1) & UINT32_MAX
        return self._record(controller_node, 'switch', ALTERNATE_FUNCTION, True)

    def restore(self, controller_node):
        """Apply verified 0x240910 mask effects (caller remains unresolved)."""
        self._controller(controller_node)
        self._assign_masks(controller_node, 'clear', 'set')
        return self._record(controller_node, 'direct_restore',
                            RESTORE_FUNCTION, True,
                            'diagnostic invocation; original caller unresolved')

    def callback(self, controller_node, event_flags, supplied_a1=None):
        """Dispatch only verified 0x2409F0 effects using supplied event flags."""
        self._controller(controller_node)
        branch = inspect_native_stage_event_callback(
            _word(event_flags, 'event flags'), supplied_a1)
        if branch['reset_mask_path']:
            self._assign_masks(controller_node, 'clear', 'set')
            return self._record(controller_node, 'event_reset',
                                EVENT_FUNCTION, True,
                                'supplied object +0x24 flag; caller unknown')
        if branch['secondary_mask_helper_eligible']:
            return self._record(controller_node, 'event_helper_unresolved',
                                EVENT_FUNCTION, False,
                                '0x1ABD30/0x1ABD70 effects not modelled')
        return self._record(controller_node, 'event_no_mask_effect',
                            EVENT_FUNCTION, False, 'no verified mask branch')

    def reset_countdown_callback(self, controller_node, diagnostic=False):
        """Model 0x2408DC/+0x2408E0 writes only under diagnostic invocation."""
        controller = self._controller(controller_node)
        if diagnostic is not True:
            return self._record(controller_node, 'reset_countdown', 0x2408DC,
                                False, '0x240860 caller/gate unresolved')
        controller['phase'] = 0
        controller['countdown'] = controller['countdown_source']
        return self._record(controller_node, 'reset_countdown_diagnostic',
                            0x2408DC, True,
                            'diagnostic path; +0x5C origin and caller unknown')

    def snapshot(self):
        return {
            'controllers': {
                key: dict(value) for key, value in self.m_controllers.items()
            },
            'target_flags': dict(self.m_target_flags),
            'mask': INITIAL_MASK,
            'unresolved': list(self.m_unknowns),
            'event_count': len(self.m_events),
            'original_runtime_executed': False,
            'native_render_visibility_proven': False,
            'native_collision_suppression_proven': False,
            'preview_only': True,
        }

    def preview(self, document):
        """Render-only suppression hypothesis, safely source-mapped to glTF.

        Shared-target disagreements and overlapping enabled/suppressed
        subtrees are left visible rather than arbitrarily resolved.
        Collision clones are handled by the existing mapping helper.
        """
        desired = {}
        for intents in self.m_intents.values():
            for target, operation in intents.items():
                desired.setdefault(target, set()).add(operation)
        conflicts = {
            target for target, operations in desired.items()
            if len(operations) > 1
        }
        # Multiple roles within a single controller also make preview
        # intent ambiguous, regardless of which native write happened last.
        for actions in self.m_actions.values():
            roles = {}
            for action in actions:
                roles.setdefault(action['target_node'], set()).add(
                    action['role'])
            conflicts.update(target for target, named in roles.items()
                             if len(named) > 1)
        enabled = set()
        suppressed = []
        warnings = list(self.m_unknowns)
        for target, flags in self.m_target_flags.items():
            masked = flags & INITIAL_MASK
            if masked == 0:
                enabled.add(target)
            elif masked == INITIAL_MASK:
                suppressed.append(target)
            else:
                warnings.append('target %d: partially set 0x300 mask' % target)
        hidden_roots = []
        for target in sorted(suppressed):
            subtree = _descendants(self.m_scene['nodes'], target)
            if target in conflicts or subtree & enabled:
                warnings.append(
                    'target %d: overlapping or conflicting mask claims; not hidden'
                    % target)
            else:
                hidden_roots.append(target)
        state = self.snapshot()
        state['conflicts_or_unresolved'] = warnings
        state['preview_suppressed_root_nodes'] = list(hidden_roots)
        state['runtime_transition_observed'] = False
        return native_stage_preview_hidden_nodes(
            self.m_scene, document, hidden_roots, state)
