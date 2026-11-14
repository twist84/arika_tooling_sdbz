"""ELF-backed outer main-menu lifecycle, including common child phases.

One step is one logical update. Shared per-item first/character/label entry and
exit transitions are recovered; item-specific phase-2 effects, fade completion
and native sound queries remain externally supplied or explicitly unresolved.
Native evidence: 0x333920, 0x379A40, 0x375630, 0x379B50, 0x379C80.
"""
import struct

from arika_menu_navigation import c_menu_navigation, read_menu_report
from arika_menu_shared import initialize_shared, request_exit, step_shared
from arika_menu_input import decode_menu_input
from arika_menu_children import (
    initialize_child, start_first, exit_first, emphasize_first, step_first,
    start_character, exit_character, emphasize_character, step_character,
    draw_character, translate_first_geometry, draw_first_strip,
)
from arika_menu_labels import (
    initialize_label, start_label, exit_label, emphasize_label,
    step_label, draw_label,
)


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


class c_menu_runtime:
    """The verified parent/shared state machines with explicit child oracles.

    child_callback(role, index) receives native shared scheduler child calls.
    item_update(index, phase, age) optionally overrides native item-phase
    transitions; otherwise complete first/character/label children drive the
    verified item phase-1/4 transitions when their kernels are available.
    fade_busy is the return of native 0x2C0C20; None means unobserved/busy.
    sound_busy is the return of native 0x2FCC00; None retains the sound latch.
    input_mask is native pressed-edge bits from 0x336600, not auto-repeat bits.
    """

    def __init__(self, report=None, child_callback=None, item_update=None,
                 particle_seed=None):
        if report is None:
            report = read_menu_report()
        self.m_report = report
        self.m_shared_kernel = report['shared_scheduler']
        self.m_label_kernel = report.get('item_label_animation')
        self.m_label_emphasis = (
            report.get('item_emphasis', {}).get('kernels', {}).get('labels'))
        self.m_child_callback = child_callback
        self.m_item_update = item_update
        # Isolated deterministic RNG seed, NOT a captured game-context seed.
        # None leaves the native-global particle state explicitly unresolved.
        self.m_particle_seed = particle_seed
        # Learned from a decoded game TIM2/PIX, never guessed from the
        # diagnostic 512x448 display coordinate system.
        self.m_particle_texture_dimensions = None
        self.m_first_kernel = report.get('first_components', {}).get('animation')
        self.m_character_kernel = report.get('item_character_animation')
        self.m_idle_components = {
            component['item']: component
            for component in report.get('character_idle', {}).get(
                'components', [])}
        self.m_character_emphasis = (
            report.get('item_emphasis', {}).get('kernels', {}).get('characters'))
        self.m_native_children = (
            self.m_character_kernel is not None and
            self.m_first_kernel is not None and
            self.m_label_kernel is not None and
            'composite_layout' in report)
        self.reset()

    def reset(self):
        # The editor's reset represents destruction/reconstruction of the
        # native menu object, not a selection transition. 0x37A820 tears
        # down the one global pool before 0x37A7D0 constructs a new one.
        previous_pool = getattr(self, 'm_particle_pool', None)
        if previous_pool is not None and previous_pool.m_alive:
            previous_pool.close()
        self.m_navigation = c_menu_navigation(self.m_report)
        self.m_navigation.m_selected = -1
        self.m_navigation.m_previous = -1
        self.m_outer_phase = 0
        self.m_shared = initialize_shared()
        self.m_selected = -1
        self.m_pending = -1
        self.m_exit_phase = 0
        self.m_exit_age = 0.0
        self.m_audio_age = 0.0
        self.m_flags = 0
        self.m_confirm = 0
        self.m_controller = 0
        self.m_item_phases = [0] * 7
        self.m_item_ages = [0.0] * 7
        self.m_label_states = [initialize_label() for _ in range(7)]
        self.m_first_states = [initialize_child() for _ in range(7)]
        self.m_particle_pool = None
        if self.m_native_children and self.m_particle_seed is not None:
            particle_spec = self.m_report['first_components'].get('particles')
            if particle_spec is not None:
                # The boundary is a native runtime global; its verified
                # startup-constructor value is used only for isolated replay.
                clip = next((entry['value'] for entry in
                             self.m_report.get('startup', {}).get(
                                 'position_values', [])
                             if entry['address'] == particle_spec[
                                 'runtime_clip_boundary_address'] and
                             entry['source'] == 'startup_constructor'), None)
                if clip is not None:
                    from arika_menu_rng import c_native_rng
                    from arika_menu_particles import c_dragon_particle_pool
                    # A single context stream and a single global-pool
                    # abstraction for this entire runtime instance.
                    self.m_particle_pool = c_dragon_particle_pool(
                        particle_spec, c_native_rng(self.m_particle_seed),
                        clip, texture_dimensions=self.m_particle_texture_dimensions)
        self.m_character_states = [initialize_child() for _ in range(7)]
        self.m_updates = 0
        self.m_last_calls = []
        self.m_completion = None

    def set_particle_texture_dimensions(self, dimensions):
        """Supply texture-entry 11 dimensions from the opened native PIX.

        This is presentation metadata; changing it cannot run menu logic,
        consume the native RNG, or advance the particle spawn clock.
        reset() retains the latest validated texture dimensions.
        """
        if dimensions is not None:
            from arika_menu_particles import normalized_sprite_uv
            normalized_sprite_uv((0, 0, 0, 0), dimensions)
            dimensions = tuple(dimensions)
        self.m_particle_texture_dimensions = dimensions
        if self.m_particle_pool is not None:
            self.m_particle_pool.set_texture_dimensions(dimensions)

    def set_item_phase(self, index, phase):
        """Accept phase reached by a separately recovered native callback."""
        if not 0 <= index < 7:
            raise IndexError(index)
        self.m_item_phases[index] = int(phase)

    def _emit(self, event, **fields):
        self.m_last_calls.append(dict(event=event, **fields))

    def _update_item(self, index, role):
        phase = self.m_item_phases[index]
        if phase:
            age = f32(self.m_item_ages[index] + 1.0)
            if age > 99999.0:
                age = f32(age - 99999.0)
            self.m_item_ages[index] = age
            self._emit(role, index=index, phase=phase, age=age)
            # 0x374FF4 -> item vtable +0x20 (0x375630):
            # first 0x373A10, character 0x37F100, label 0x37DF90.
            if self.m_native_children:
                first = self.m_first_states[index]
                character = self.m_character_states[index]
                step_first(
                    first, self.m_first_kernel['components'][index],
                    self.m_first_kernel,
                    self.m_report['first_components']['groups'][index].get(
                        'scroll_strip'),
                    particle_update=(self.m_particle_pool.step
                                     if index == 3 and
                                     self.m_particle_pool is not None else None))
                step_character(
                    character, self.m_character_kernel['components'][index],
                    self.m_character_kernel, self.m_character_emphasis,
                    self.m_idle_components.get(index))
                self._emit('first_update', index=index,
                           phase=first['phase'], age=first['age'])
                self._emit('character_update', index=index,
                           phase=character['phase'], age=character['age'])
            if self.m_label_kernel is not None:
                step_label(
                    self.m_label_states[index],
                    self.m_label_kernel['components'][index],
                    self.m_label_kernel,
                    self.m_label_emphasis)
                self._emit(
                    'label_update', index=index,
                    phase=self.m_label_states[index]['phase'],
                    age=self.m_label_states[index]['age'])
            if self.m_item_update is not None:
                new_phase = self.m_item_update(index, phase, age)
                if new_phase is not None:
                    self.m_item_phases[index] = int(new_phase)
            elif self.m_native_children:
                # 0x374FB0: entry polls 0x375690 (first child phase 2).
                # Exit polls 0x3756E0 (all three child phases zero).
                if phase == 1 and self.m_first_states[index]['phase'] == 2:
                    self.m_item_phases[index] = 2
                elif (phase == 4 and
                      self.m_first_states[index]['phase'] == 0 and
                      self.m_character_states[index]['phase'] == 0 and
                      self.m_label_states[index]['phase'] == 0):
                    self.m_item_phases[index] = 0
        else:
            self._emit(role, index=index, phase=0, age=self.m_item_ages[index])

    def _update_components(self):
        # vtable +0x40: shared -> pending old item -> current -> inner.
        self._emit('shared_update', phase=self.m_shared['phase'])

        def child(role, index):
            self._emit('shared_' + role, index=index)
            if self.m_child_callback is not None:
                self.m_child_callback(role, index)

        step_shared(self.m_shared, self.m_shared_kernel, child)
        if self.m_pending >= 0:
            previous = self.m_pending
            self._update_item(previous, 'pending_arrow_update')
            self._emit('pending_item_poll', index=previous,
                       phase=self.m_item_phases[previous])
            # 0x375250 is zero precisely when item phase +0x04 is zero.
            if self.m_item_phases[previous] == 0:
                self._emit('shared_remove_item', index=previous)
                self.m_pending = -1
        if self.m_selected >= 0:
            self._update_item(self.m_selected, 'current_arrow_update')
        self._emit('inner_update')

    def _select(self, new_index):
        old_index = self.m_selected
        self.m_pending = old_index  # 0x379F24 delay-slot store
        if old_index >= 0:
            self.m_item_phases[old_index] = 4
            if self.m_native_children:
                exit_first(self.m_first_states[old_index],
                           self.m_first_kernel)
                exit_character(self.m_character_states[old_index])
            if self.m_label_kernel is not None:
                exit_label(self.m_label_states[old_index],
                           self.m_label_kernel)
            self._emit('request_old_item_exit', index=old_index)
        self.m_navigation.select(new_index)
        self.m_selected = new_index
        self.m_item_phases[new_index] = 1
        if self.m_native_children:
            start_first(
                self.m_first_states[new_index],
                self.m_first_kernel['components'][new_index],
                self.m_first_kernel)
            start_character(
                self.m_character_states[new_index],
                self.m_character_kernel['components'][new_index],
                self.m_character_kernel)
        if self.m_label_kernel is not None:
            start_label(
                self.m_label_states[new_index],
                self.m_label_kernel['components'][new_index],
                self.m_label_kernel)
        self._emit('start_new_item', index=new_index, previous=old_index)
        self._emit('inner_select', index=new_index)
        if self.m_flags & 2:
            self._emit('selection_sound')
        self.m_audio_age = 0.0
        self.m_flags &= ~2

    def _begin_exit(self, confirm):
        self.m_confirm = int(confirm)
        self.m_outer_phase = 3
        self.m_exit_phase = 0
        self.m_exit_age = 0.0
        self._emit('begin_exit', confirmed=bool(confirm))
        if confirm:
            # 0x3799FC writes 30, bypassing the 0..3 cancel path.
            self.m_exit_phase = 30
            if self.m_selected >= 0:
                self.m_item_phases[self.m_selected] = 4
                if self.m_native_children:
                    exit_first(self.m_first_states[self.m_selected],
                               self.m_first_kernel)
                    exit_character(self.m_character_states[self.m_selected])
                if self.m_label_kernel is not None:
                    exit_label(self.m_label_states[self.m_selected],
                               self.m_label_kernel)
                self._emit('request_selected_exit', index=self.m_selected)
            request_exit(self.m_shared)
            self._emit('request_shared_exit')
            self._emit('fade_start', mode=2, duration=15,
                       x=-1.0, y=-1.0)
        else:
            if self.m_selected >= 0:
                self.m_item_phases[self.m_selected] = 3
                if self.m_native_children:
                    emphasize_first(self.m_first_states[self.m_selected],
                                    self.m_first_kernel)
                    emphasize_character(
                        self.m_character_states[self.m_selected])
                if self.m_label_kernel is not None:
                    emphasize_label(
                        self.m_label_states[self.m_selected],
                        self.m_label_kernel)
                self._emit('request_selected_cancel', index=self.m_selected)
        self._emit('inner_exit_start')

    def _update_audio(self, sound_busy):
        if self.m_flags & 1:
            self._emit('audio_latch_poll')
            if sound_busy is False:
                self.m_flags &= ~1
            return
        self.m_audio_age = min(9999.0, f32(self.m_audio_age + 1.0))
        if not self.m_flags & 2 and self.m_audio_age >= 60.0:
            self.m_flags |= 2
            self._emit('selection_sound_ready', index=self.m_selected)

    def _update_exit(self, fade_busy):
        self._emit('exit_poll', phase=self.m_exit_phase)
        if self.m_exit_phase == 0:
            self._emit('fade_reset')
            self._emit('fade_start', mode=1, duration=5, x=1.0, y=-1.0)
            self.m_exit_phase = 1
        elif self.m_exit_phase == 1:
            if fade_busy is False:
                self.m_exit_age = 0.0
                self.m_exit_phase = 2
        elif self.m_exit_phase == 2:
            self.m_exit_age = f32(self.m_exit_age + 1.0)
            if not self.m_exit_age < 10.0:
                self.m_exit_phase = 3
        elif self.m_exit_phase == 3:
            self._emit('fade_reset')
            self._emit('fade_start', mode=2, duration=15, x=-1.0, y=-1.0)
            self.m_exit_phase = 30
        elif self.m_exit_phase == 30:
            if fade_busy is False:
                self.m_outer_phase = 4
                self.m_completion = self.m_navigation.route(
                    cancelled=not self.m_confirm)
                self._emit('exit_complete', route=self.m_completion)

    def step(self, input_mask=0, confirm_mask=0, controller_qualified=True,
             controller=0, fade_busy=None, sound_busy=None):
        """Advance one native logical update. No invented FPS or animation phase."""
        self.m_last_calls = []
        self.m_updates += 1
        if self.m_outer_phase == 4:
            return self.snapshot()

        self._update_components()  # always first unless already finished
        if self.m_outer_phase == 0:
            self.m_exit_phase = 0
            self.m_shared.update(phase=1, subphase=0, age=0.0,
                                 started_count=0)
            self._emit('start_shared')
            self.m_outer_phase = 1

        if self.m_outer_phase == 1:
            self._emit('entry_poll', shared_phase=self.m_shared['phase'])
            if self.m_exit_phase != 0 or self.m_shared['phase'] != 2:
                return self.snapshot()
            self.m_outer_phase = 2
            self.m_flags |= 1
            self._emit('entry_sound')
            self._select(0)
            self._emit('inner_entry_start')
            # Native parent immediately falls through to input on entry-ready.

        if self.m_outer_phase == 2:
            self.m_controller = int(controller)
            action, direction = decode_menu_input(
                input_mask, confirm_mask, controller_qualified)
            self._emit('input_poll', action=action, direction=direction)
            if action == 'cancel':
                self._begin_exit(False)
            elif action == 'confirm':
                self._begin_exit(True)
            elif action == 'direction':
                new_index = self.m_navigation.neighbor(direction)
                self._emit('resolve_neighbor', index=new_index)
                if new_index >= 0:
                    self._select(new_index)
                self._update_audio(sound_busy)
            else:
                self._update_audio(sound_busy)
            # 0x379C80 returns zero. Indirect exit begins on *next* update.
        elif self.m_outer_phase == 3:
            self._update_exit(fade_busy)
        return self.snapshot()

    def label_geometry(self, item):
        """Native selected-item label geometry, not diagnostic frame samples."""
        if self.m_label_kernel is None or not 0 <= item < 7:
            return None
        return draw_label(
            self.m_label_states[item],
            self.m_label_kernel['components'][item])

    def first_geometry(self, item, geometry, component_index=None):
        """Translate first-layer geometry; preserve recovered item-3 Z order."""
        if not self.m_native_children or not 0 <= item < 7:
            return geometry
        state = self.m_first_states[item]
        if state['phase'] == 0:
            return None
        result = translate_first_geometry(geometry, state['offset'])
        if item == 3 and component_index is not None:
            # 0x37A9B4 / 0x37A9E0: two literal sprites at first+0x14.
            # 0x37AA24: six decorations at first+0x14 + 10.0f.
            # 0x37A980 -> 0x37B370: particles at first+0x14 + 1.0f
            # plus their own 0.1f*speed.
            result['depth'] = f32(
                state['depth'] + (10.0 if component_index >= 2 else 0.0))
        return result

    def first_strip_geometry(self, item):
        """Return native phase-driven strip quads (not diagnostic frames)."""
        if not self.m_native_children or not 0 <= item < 7:
            return []
        return draw_first_strip(self.m_first_states[item], item,
                                self.m_report)

    def particle_geometry(self, item):
        """Pure six-slot presentation. A paint event cannot advance RNG."""
        if item != 3 or self.m_particle_pool is None:
            return []
        first = self.m_first_states[3]
        if first['phase'] == 0:
            return []
        # 0x37A980 computes 1.0f + first depth; 0x37AA5C
        # supplies first+0x0C XY directly to the pool draw.
        return self.m_particle_pool.geometry(
            first['offset'], f32(f32(1.0) + first['depth']))

    def character_geometry(self, item, include_idle=True):
        """Return current native character quads, not diagnostic sample 70."""
        if not self.m_native_children or not 0 <= item < 7:
            return None
        return draw_character(self.m_character_states[item], item,
                              self.m_report, include_idle=include_idle)

    def snapshot(self):
        return {
            'update': self.m_updates,
            'outer_phase': self.m_outer_phase,
            'exit_phase': self.m_exit_phase,
            'exit_age': self.m_exit_age,
            'audio_age': self.m_audio_age,
            'flags': self.m_flags,
            'confirm': self.m_confirm,
            'controller': self.m_controller,
            'selected': self.m_selected,
            'previous': self.m_navigation.m_previous,
            'pending': self.m_pending,
            'item_phases': tuple(self.m_item_phases),
            'item_ages': tuple(self.m_item_ages),
            'first_phases': tuple(state['phase']
                                  for state in self.m_first_states),
            'first_ages': tuple(state['age']
                                for state in self.m_first_states),
            'first_offsets': tuple(tuple(state['offset'])
                                   for state in self.m_first_states),
            'first_strip_phases': tuple(state['strip_phase']
                                        for state in self.m_first_states),
            'particle_timer': self.m_first_states[3]['particle_timer'],
            'particles': (self.m_particle_pool.snapshot()
                          if self.m_particle_pool is not None else None),
            'first_particles_unresolved': tuple(
                bool(state.get('particle_update_unresolved'))
                for state in self.m_first_states),
            'character_phases': tuple(state['phase']
                                      for state in self.m_character_states),
            'character_ages': tuple(state['age']
                                    for state in self.m_character_states),
            'character_secondary_ages': tuple(state['secondary_age']
                                              for state in self.m_character_states),
            'character_offsets': tuple(tuple(state['offset'])
                                       for state in self.m_character_states),
            'character_part_offsets': tuple(
                tuple(tuple(offset) for offset in
                      state.get('part_offsets', ()))
                for state in self.m_character_states),
            'label_phases': tuple(state['phase']
                                  for state in self.m_label_states),
            'label_ages': tuple(state['age']
                                for state in self.m_label_states),
            'label_offsets': tuple(tuple(state['offset'])
                                   for state in self.m_label_states),
            'shared_phase': self.m_shared['phase'],
            'shared_subphase': self.m_shared['subphase'],
            'shared_age': self.m_shared['age'],
            'shared_started_count': self.m_shared['started_count'],
            'completion': self.m_completion,
            'calls': list(self.m_last_calls),
        }
