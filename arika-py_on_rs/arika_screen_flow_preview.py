"""One guided game-screen preview flow, reusing the existing Qt tabs.

The original ELF's factory calls are NOT executed. Manual tour jumps are
distinct from verified native request edges, and unresolved transitions never
automatically claim to enter the next game application.
"""
import math

from PySide6 import QtCore as C, QtWidgets as W

from arika_app_registry import title_handoff_request
from arika_native_ee_trace import load_native_ee_trace
from arika_screen_flow import (
    SCREEN_SEQUENCE, SCREEN_TAB_ORDER, SCREEN_LABELS,
    native_view_request, observed_screen_completion, screen_step,
)


class c_native_screen_flow(W.QWidget):
    """Connect the existing six screen previews without replacing them."""

    def __init__(self, tabs, views, parent=None):
        super().__init__(parent)
        if not isinstance(tabs, W.QTabWidget):
            raise TypeError('expected existing game-screen tab widget')
        if set(views) != set(SCREEN_TAB_ORDER):
            raise ValueError('all six existing game-screen views are required')
        if any(tabs.indexOf(view) < 0 for view in views.values()):
            raise ValueError('each flow view must belong to the existing tabs')
        self.m_tabs = tabs
        self.m_views = dict(views)
        # Reorder the original tab widgets in place; their canvases,
        # native runtimes, connected signals and archive assets survive.
        # The first five positions follow the annotated guided sequence;
        # Demo Main remains a separate, out-of-sequence inspector.
        for target_index, screen in enumerate(SCREEN_TAB_ORDER):
            original_index = tabs.indexOf(self.m_views[screen])
            if original_index != target_index:
                tabs.tabBar().moveTab(original_index, target_index)
            tabs.setTabText(target_index, SCREEN_LABELS[screen])
        self.m_switching = False
        self.m_reason = 'Select Start tour or use the individual tabs.'
        self.m_runner_timer = C.QTimer(self)
        self.m_runner_timer.setTimerType(C.Qt.TimerType.PreciseTimer)
        self.m_runner_timer.setInterval(16)
        self.m_runner_timer.timeout.connect(self.advance_playback)
        self.m_elapsed = C.QElapsedTimer()
        self.m_last_elapsed_ns = 0

        controls = W.QHBoxLayout(self)
        controls.setContentsMargins(6, 3, 6, 3)
        self.m_start = W.QPushButton('Start screen tour')
        self.m_start.clicked.connect(self.start_tour)
        controls.addWidget(self.m_start)
        self.m_previous = W.QPushButton('Previous preview')
        self.m_previous.clicked.connect(self.previous_preview)
        controls.addWidget(self.m_previous)
        self.m_next = W.QPushButton('Next preview')
        self.m_next.clicked.connect(self.next_preview)
        controls.addWidget(self.m_next)
        self.m_play = W.QPushButton('Play active screen')
        self.m_play.clicked.connect(self.toggle_play)
        self.m_play.setToolTip(
            'Advance the existing original-state runtime using measured '
            'elapsed monotonic time. Automatically traverse ONLY verified '
            'native application requests; pause at unknown transitions.')
        controls.addWidget(self.m_play)
        self.m_step = W.QPushButton('Step active')
        self.m_step.clicked.connect(self.step_active)
        controls.addWidget(self.m_step)
        self.m_cancel = W.QPushButton('Main menu cancel')
        self.m_cancel.setToolTip(
            'Inspect the recovered main-menu cancel route to app ID 3. '
            'This does not run the original factory or inject a controller.')
        self.m_cancel.clicked.connect(self.menu_cancel)
        controls.addWidget(self.m_cancel)
        self.m_trace_summary = None
        self.m_import_ee_trace = W.QPushButton('Import EE trace')
        self.m_import_ee_trace.setToolTip(
            'Read a user-captured original EU-beta EE debugger trace. '
            'Show factory-entry and root-write evidence without executing '
            'the game or switching preview tabs.')
        self.m_import_ee_trace.clicked.connect(self.choose_ee_trace)
        controls.addWidget(self.m_import_ee_trace)
        self.m_status = W.QLabel()
        self.m_status.setWordWrap(True)
        self.m_status.setMinimumWidth(140)
        controls.addWidget(self.m_status, 1)

        self.m_tabs.currentChanged.connect(self.on_tab_changed)

        # The original widgets emit only completed native update events,
        # never an invented factory call. This also covers their own
        # manual Step/Play controls, not merely this flow's timer.
        self.m_views['warning'].transition_completed.connect(
            self.on_warning_completed)
        self.m_views['startup'].sequence_completed.connect(
            self.on_startup_completed)
        self.m_views['title'].native_transition_completed.connect(
            self.on_title_completed)
        self.m_views['press_start'].native_transition_completed.connect(
            self.on_press_start_completed)
        self.m_views['warning'].m_confirm.clicked.connect(
            self.on_warning_confirm)
        self.m_views['press_start'].m_start_0.clicked.connect(
            self.on_press_start_input)
        self.m_views['press_start'].m_start_1.clicked.connect(
            self.on_press_start_input)
        self.refresh()

    def active_screen(self):
        view = self.m_tabs.currentWidget()
        for screen, candidate in self.m_views.items():
            if view is candidate:
                return screen
        return None

    def _pause_view(self, screen):
        view = self.m_views.get(screen)
        if view is None:
            return
        if hasattr(view, 'pause_playback'):
            view.pause_playback()
        if hasattr(view, 'pause_update_playback'):
            view.pause_update_playback()
        if getattr(view, 'm_playing', False) and hasattr(view, 'toggle_play'):
            view.toggle_play()

    def pause_playback(self):
        self.m_runner_timer.stop()
        self.m_last_elapsed_ns = 0
        self.m_play.setText('Play active screen')

    def refresh(self):
        screen = self.active_screen()
        ready = screen is not None
        playable = screen in ('startup', 'warning', 'title', 'press_start')
        self.m_previous.setEnabled(
            ready and screen_step(screen, -1) is not None)
        self.m_next.setEnabled(
            ready and screen_step(screen, 1) is not None)
        self.m_play.setEnabled(playable)
        self.m_step.setEnabled(playable and
                               not self.m_runner_timer.isActive())
        self.m_cancel.setEnabled(screen == 'main_menu')
        title = (SCREEN_LABELS[screen] if ready else 'Unknown game screen')
        self.m_status.setText(title + ' | ' + self.m_reason)
        self.m_status.setToolTip(
            'Manual preview order is NOT a claim of native boot order. '
            'A native request only switches to a registered preview; '
            'original application factories, streaming and GS are not run.')

    def import_ee_trace(self, path):
        """Inspect a PCSX2 EE capture without altering the editor tour."""
        try:
            result = load_native_ee_trace(path)
        except (OSError, ValueError) as error:
            self.m_reason = 'EE trace rejected: %s' % error
            self.refresh()
            return None
        self.m_trace_summary = result
        description = 'synthetic fixture' if result['synthetic_fixture'] else (
            'user-reported debugger evidence')
        self.m_reason = (
            'EE trace imported (%s): %d matched factory entry hits, '
            '%d post-write active-root observations. '
            'No screen transition or allocation is inferred.' %
            (description, result['factory_entry_count'],
             result['root_write_count']))
        self.refresh()
        return result

    def choose_ee_trace(self):
        """Open an explicitly selected debugger JSON capture for read-only use."""
        path, _filter = W.QFileDialog.getOpenFileName(
            self, 'Open original EU-beta EE trace', '',
            'EE debugger captures (*.json);;All files (*)')
        if not path:
            return None
        return self.import_ee_trace(path)

    def on_tab_changed(self, _index):
        if not self.m_switching:
            self.pause_playback()
            self.m_reason = 'Selected directly; standalone screen controls remain available.'
        self.refresh()

    def _navigate(self, screen, reason, reset=True):
        if screen not in self.m_views:
            raise ValueError('unavailable game-screen preview')
        self.pause_playback()
        self._pause_view(self.active_screen())
        destination = self.m_views[screen]
        if reset:
            if hasattr(destination, 'reset'):
                destination.reset()
            elif hasattr(destination, 'reset_native'):
                destination.reset_native()
        self.m_switching = True
        try:
            self.m_tabs.setCurrentWidget(destination)
        finally:
            self.m_switching = False
        self.m_reason = reason
        self.refresh()
        return screen

    def start_tour(self):
        """Restart the editor tour without asserting an original boot path."""
        self.pause_playback()
        for screen in SCREEN_TAB_ORDER:
            self._pause_view(screen)
            view = self.m_views[screen]
            if hasattr(view, 'reset'):
                view.reset()
            elif hasattr(view, 'reset_native'):
                view.reset_native()
        return self._navigate(
            'warning', 'Annotated preview order 1–5; '
            'original native boot handoffs are not yet verified.',
            reset=False)

    def move_preview(self, offset):
        current = self.active_screen()
        target = screen_step(current, offset) if current else None
        if target is None:
            return None
        return self._navigate(
            target,
            'Manual preview jump (%s → %s); NOT a native app request.' %
            (SCREEN_LABELS[current], SCREEN_LABELS[target]))

    def previous_preview(self):
        return self.move_preview(-1)

    def next_preview(self):
        return self.move_preview(1)

    def route_native(self, source, destination_id, result=None):
        """Only a supported native request can switch tabs automatically."""
        route = native_view_request(source, destination_id)
        target = route['destination']
        if target is None:
            self.pause_playback()
            self.m_reason = route['message']
            self.refresh()
            return route
        if source == 'title':
            # The title's completed 0x3DFB00(6) event must be present.
            handoff = title_handoff_request(result) if result is not None else None
            demo = self.m_views[target]
            if handoff is None or not hasattr(demo, 'accept_title_result') or (
                    not demo.accept_title_result(result)):
                self.pause_playback()
                self.m_reason = ('Title → DemoMain requires its completed '
                                 'native request result; no factory executed.')
                self.refresh()
                return dict(route, destination=None,
                            verified_preview_route=False)
            self._navigate(target, route['message'], reset=False)
        else:
            self._navigate(target, route['message'])
        return route

    def _resume_handoff_playback(self, was_playing):
        """Retain a running flow across visual screen changes only."""
        if was_playing and self.active_screen() in (
                'startup', 'warning', 'title', 'press_start'):
            preview = self.m_views[self.active_screen()]
            if not preview.m_runtime.snapshot()['finished']:
                self._begin_playback()

    def on_warning_completed(self, app_id):
        if self.active_screen() != 'warning':
            return None
        if (app_id != 1 or not
                self.m_views['warning'].m_runtime.snapshot()['finished']):
            return None
        was_playing = self.m_runner_timer.isActive()
        route = self.route_native('warning', app_id)
        self._resume_handoff_playback(was_playing)
        return route

    def on_startup_completed(self):
        if self.active_screen() != 'startup':
            return None
        if not self.m_views['startup'].m_runtime.snapshot()['finished']:
            return None
        route = observed_screen_completion('startup')
        if route is None:
            return None
        was_playing = self.m_runner_timer.isActive()
        self._navigate(route['destination'], route['message'])
        self._resume_handoff_playback(was_playing)
        return route

    def on_title_completed(self, result):
        """Preserve native ID-6 handoff, show observed next visible screen."""
        if self.active_screen() != 'title':
            return None
        evidence = title_handoff_request(result)
        if evidence is None or evidence['target']['id'] != 6:
            return None
        demo = self.m_views['demo']
        if not demo.accept_title_result(result):
            self.pause_playback()
            self.m_reason = ('Native Title → ID 6 request was recorded, '
                             'but DemoMain could not accept its handoff.')
            self.refresh()
            return None
        was_playing = self.m_runner_timer.isActive()
        self._navigate('press_start',
                       'Title completed with native app ID 6 '
                       '(DemoMain handoff recorded); proceeding to '
                       'the user-observed Press Start screen. '
                       'EU-beta DemoMain (ID 6) has an ELF-verified '
                       'conditional exit to ID 3, but its child '
                       'completion and actual request were not run here. '
                       'DemoMain factory was NOT executed.')
        self._resume_handoff_playback(was_playing)
        return evidence

    def on_press_start_completed(self, app_id):
        if self.active_screen() != 'press_start':
            return None
        runtime = self.m_views['press_start'].m_runtime.snapshot()
        if not runtime['finished'] or runtime['destination_id'] != app_id:
            return None
        was_playing = self.m_runner_timer.isActive()
        route = self.route_native('press_start', app_id)
        self._resume_handoff_playback(was_playing)
        return route

    def on_warning_confirm(self):
        """Resume the warning exit fade only for actual To Game selection."""
        if self.active_screen() != 'warning':
            return
        state = self.m_views['warning'].m_runtime.snapshot()
        if (state['selection'] == 3 and state['phase'] in (3, 4)
                and not state['finished']
                and not self.m_runner_timer.isActive()):
            self._begin_playback()

    def on_press_start_input(self):
        """Finish the original transition after a valid Start input."""
        if self.active_screen() != 'press_start':
            return
        state = self.m_views['press_start'].m_runtime.snapshot()
        if (state['phase'] != 0 and not state['finished']
                and not self.m_runner_timer.isActive()):
            self._begin_playback()

    def menu_cancel(self):
        if self.active_screen() != 'main_menu':
            return None
        menu = self.m_views['main_menu']
        if getattr(menu, 'm_native_mode', False):
            # The native menu queues an input and consumes it on its own
            # update; a queued cancellation is not a completed app request.
            menu.inspect_route(True)
            self.m_reason = ('Native cancel input queued in the existing '
                             'menu runtime; target not assumed yet.')
            self.refresh()
            return None
        route = menu.inspect_route(True)
        if route is None or route.get('next_app_id') != 3:
            self.m_reason = 'No supported native menu cancel route.'
            self.refresh()
            return None
        return self.route_native('main_menu', 3)

    def advance_active(self, delta_seconds):
        """One tick of the selected *existing* screen controller."""
        if (type(delta_seconds) not in (float, int) or
                not math.isfinite(delta_seconds) or delta_seconds < 0):
            raise ValueError('finite, nonnegative elapsed time required')
        screen = self.active_screen()
        if screen not in ('startup', 'warning', 'title', 'press_start'):
            self.pause_playback()
            self.m_reason = ('This screen has no supported common timed '
                             'update; use its own native inspector.')
            self.refresh()
            return None
        preview = self.m_views[screen]
        if preview.m_runtime.snapshot()['finished']:
            self.pause_playback()
            return None
        # The existing preview owns its state, visual rendering and
        # external busy/controller observations. Do not create a second
        # runtime or infer resource loading from the editor archive.
        preview.advance_native(delta_seconds)
        # A completed native callback can route synchronously via the
        # preview's completion signal. Never process the old view twice.
        if self.active_screen() != screen:
            return {'completed_screen': screen,
                    'active_screen': self.active_screen()}
        state = preview.m_runtime.snapshot()
        if not state['finished']:
            if screen == 'warning' and state['phase'] == 2:
                self.pause_playback()
                self.m_reason = (
                    'Warning selection is interactive; use its original '
                    'choice controls, then resume the common flow.')
            self.refresh()
            return state

        # Completion signals already carry the original event evidence.
        # An unsupported result stays on its screen; no inferred route.
        self.pause_playback()
        self.refresh()
        return state

    def step_active(self):
        if not self.m_runner_timer.isActive():
            # A controllable diagnostic step, NOT a claimed EE scheduler tick.
            return self.advance_active(1.0 / 60.0)
        return None

    def _begin_playback(self):
        screen = self.active_screen()
        if screen not in ('startup', 'warning', 'title', 'press_start'):
            return
        if self.m_views[screen].m_runtime.snapshot()['finished']:
            return
        self._pause_view(screen)
        self.m_last_elapsed_ns = 0
        self.m_elapsed.start()
        self.m_runner_timer.start()
        self.m_play.setText('Pause flow')
        self.refresh()

    def toggle_play(self):
        if self.m_runner_timer.isActive():
            self.pause_playback()
        else:
            self._begin_playback()
        self.refresh()

    def advance_playback(self):
        if not self.m_runner_timer.isActive():
            return
        now = self.m_elapsed.nsecsElapsed()
        delta = max(0, now - self.m_last_elapsed_ns) / 1_000_000_000.0
        self.m_last_elapsed_ns = now
        self.advance_active(delta)

    def archive_changed(self):
        """Stop all clocks before an archive is cleared or replaced."""
        self.pause_playback()
        for screen in SCREEN_TAB_ORDER:
            self._pause_view(screen)
        self.m_reason = 'Archive changed; restart the tour to use new assets.'
        self.refresh()

    def hideEvent(self, event):
        self.pause_playback()
        super().hideEvent(event)

    def closeEvent(self, event):
        self.pause_playback()
        super().closeEvent(event)
