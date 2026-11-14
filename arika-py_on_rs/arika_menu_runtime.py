"""ELF-backed outer main-menu lifecycle shell, not an authored sample timeline.

One step is one logical update. The remaining item-animation callbacks and
fade-completion query are injected instead of inventing their durations.
Native evidence: 0x333920, 0x379A40, 0x379B50, 0x379C80.
"""
import struct

from arika_menu_navigation import c_menu_navigation, read_menu_report
from arika_menu_shared import initialize_shared, request_exit, step_shared
from arika_menu_input import decode_menu_input


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


class c_menu_runtime:
    """The verified parent/shared state machines with explicit child oracles.

    child_callback(role, index) receives native shared scheduler child calls.
    item_update(index, phase, age) returns the phase actually reached by an
    externally verified item animation update. No guessed completion is used.
    fade_busy is the return of native 0x2C0C20; None means unobserved/busy.
    sound_busy is the return of native 0x2FCC00; None retains the sound latch.
    input_mask is native pressed-edge bits from 0x336600, not auto-repeat bits.
    """

    def __init__(self, report=None, child_callback=None, item_update=None):
        if report is None:
            report = read_menu_report()
        self.m_report = report
        self.m_shared_kernel = report['shared_scheduler']
        self.m_child_callback = child_callback
        self.m_item_update = item_update
        self.reset()

    def reset(self):
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
        self.m_updates = 0
        self.m_last_calls = []
        self.m_completion = None

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
            if self.m_item_update is not None:
                new_phase = self.m_item_update(index, phase, age)
                if new_phase is not None:
                    self.m_item_phases[index] = int(new_phase)
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
            self._emit('request_old_item_exit', index=old_index)
        self.m_navigation.select(new_index)
        self.m_selected = new_index
        self.m_item_phases[new_index] = 1
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
                self._emit('request_selected_exit', index=self.m_selected)
            request_exit(self.m_shared)
            self._emit('request_shared_exit')
            self._emit('fade_start', mode=2, duration=15,
                       x=-1.0, y=-1.0)
        else:
            if self.m_selected >= 0:
                self.m_item_phases[self.m_selected] = 3
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
            'shared_phase': self.m_shared['phase'],
            'shared_subphase': self.m_shared['subphase'],
            'shared_age': self.m_shared['age'],
            'shared_started_count': self.m_shared['started_count'],
            'completion': self.m_completion,
            'calls': list(self.m_last_calls),
        }
