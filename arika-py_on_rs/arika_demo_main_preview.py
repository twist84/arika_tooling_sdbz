"""Read-only DemoMain entry inspector embedded in the Arika Editor.

It does NOT render movie data or drive the full 0x3E0830 update.
Loader readiness and child choices are independently controlled,
and host callbacks are never executed.
"""
from PySide6 import QtCore as C, QtWidgets as W

from arika_app_registry import resolve_app
from arika_demo_main_runtime import c_demo_main_bootstrap, DEMO_MAIN_RESOURCE_GROUPS


class c_demo_main_preview(W.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.m_bootstrap = c_demo_main_bootstrap()
        self.m_last_calls = []
        self.m_last_child = None
        self.m_update_calls = []
        self.m_update_timer = C.QTimer(self)
        self.m_update_timer.setTimerType(C.Qt.TimerType.PreciseTimer)
        # Purely a UI stepping cadence; the original update has no
        # fabricated 60 Hz clock and consumes no elapsed-time argument.
        self.m_update_timer.setInterval(100)
        self.m_update_timer.timeout.connect(self.step_update)

        title = W.QLabel('CAppDemoMain — native application ID 6')
        title.setStyleSheet('font-size:18px;font-weight:bold;')
        self.m_route = W.QLabel()
        self.m_route.setWordWrap(True)
        self.m_factories = W.QLabel(
            'Lookup 0x3F1C40 → factory 0x3F2C00 → '
            'constructor 0x3E03E0 → CAppDemoMain (ID 6). '
            'ID 8 is a separate CAppDemoMain implementation; '
            'ID 9 is CAppDemoPlay; ID 7 is CAppDemoMovie.')
        self.m_factories.setWordWrap(True)

        self.m_ready = W.QCheckBox('External group loader ready (0x2FBEB0)')
        self.m_ready.setToolTip(
            'Use a captured native helper result. It is NOT inferred '
            'from whether the editor opened an archive.')
        self.m_step = W.QPushButton('Step native loader')
        self.m_reset = W.QPushButton('Reset inspector')
        self.m_step.clicked.connect(self.step_loader)
        self.m_reset.clicked.connect(self.reset)

        self.m_child_combo = W.QComboBox()
        for index, child_id in enumerate(self.m_bootstrap.snapshot()['child_candidates']):
            app = resolve_app(child_id)
            label = app['class_name'] if app is not None else 'Unresolved application'
            self.m_child_combo.addItem('%d: %s' % (child_id, label), index)
        self.m_child_button = W.QPushButton('Inspect native child branch')
        self.m_child_button.clicked.connect(self.inspect_child)
        self.m_child_info = W.QLabel()
        self.m_child_info.setWordWrap(True)

        self.m_child_present = W.QCheckBox('Native child pointer exists (+0x2C)')
        self.m_child_pending = W.QCheckBox('0x3DFC60: child still pending')
        self.m_child_pending.setChecked(True)
        self.m_exit_input = W.QCheckBox('Global exit signal (gp−0xFD4, one tick)')
        for control in (self.m_child_present, self.m_child_pending,
                        self.m_exit_input):
            control.setToolTip('Supply an observed native input; not an emulated child.')
        self.m_next_choice = W.QComboBox()
        for index, app_id in enumerate(self.m_bootstrap.snapshot()['child_candidates']):
            app = resolve_app(app_id)
            self.m_next_choice.addItem(
                '%d → ID %d (%s)' %
                (index, app_id, app['class_name']), index)
        self.m_set_choice = W.QPushButton('Set captured next choice')
        self.m_set_choice.setToolTip(
            'Inject the native this+0x29 field at phase 0 for captured '
            'state inspection. Not a gameplay selection or child launch.')
        self.m_set_choice.clicked.connect(self.set_captured_choice)
        self.m_update_step = W.QPushButton('Step native update')
        self.m_update_play = W.QPushButton('Play')
        self.m_update_reset = W.QPushButton('Reset update')
        self.m_update_step.clicked.connect(self.step_update)
        self.m_update_play.clicked.connect(self.toggle_update_playback)
        self.m_update_reset.clicked.connect(self.reset_update)
        self.m_update_status = W.QLabel()
        self.m_update_status.setWordWrap(True)
        self.m_update_trace = W.QLabel()
        self.m_update_trace.setWordWrap(True)

        self.m_status = W.QLabel()
        self.m_status.setWordWrap(True)
        self.m_notice = W.QLabel(
            'The child/pending/global-exit checkboxes are observed inputs. '
            'Play uses a 100 ms Qt diagnostic update cadence (not an '
            'asserted PS2 rate). No movie, streaming, app factory, '
            'rendering or game-global side effects are executed.')
        self.m_notice.setWordWrap(True)

        layout = W.QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(self.m_route)
        layout.addWidget(self.m_factories)
        layout.addSpacing(8)
        groups = W.QLabel(
            'Native resource groups: ' +
            ', '.join(str(group) for group in DEMO_MAIN_RESOURCE_GROUPS))
        groups.setWordWrap(True)
        layout.addWidget(groups)
        controls = W.QHBoxLayout()
        controls.addWidget(self.m_ready)
        controls.addWidget(self.m_step)
        controls.addWidget(self.m_reset)
        controls.addStretch()
        layout.addLayout(controls)
        layout.addWidget(self.m_status)
        child_controls = W.QHBoxLayout()
        child_controls.addWidget(W.QLabel('Native choice'))
        child_controls.addWidget(self.m_child_combo)
        child_controls.addWidget(self.m_child_button)
        child_controls.addStretch()
        layout.addLayout(child_controls)
        layout.addWidget(self.m_child_info)
        layout.addSpacing(10)
        layout.addWidget(W.QLabel('CAppDemoMain update (EE 0x3E0830)'))
        observations = W.QHBoxLayout()
        observations.addWidget(self.m_child_present)
        observations.addWidget(self.m_child_pending)
        observations.addWidget(self.m_exit_input)
        observations.addStretch()
        layout.addLayout(observations)
        update_controls = W.QHBoxLayout()
        update_controls.addWidget(self.m_update_step)
        update_controls.addWidget(self.m_update_play)
        update_controls.addWidget(self.m_update_reset)
        update_controls.addStretch()
        layout.addLayout(update_controls)
        choice_controls = W.QHBoxLayout()
        choice_controls.addWidget(W.QLabel('Captured +0x29'))
        choice_controls.addWidget(self.m_next_choice)
        choice_controls.addWidget(self.m_set_choice)
        choice_controls.addStretch()
        layout.addLayout(choice_controls)
        layout.addWidget(self.m_update_status)
        layout.addWidget(self.m_update_trace)
        layout.addWidget(self.m_notice)
        layout.addStretch(1)
        self.redraw()

    def accept_title_result(self, result):
        if not self.m_bootstrap.accept_title_result(result):
            return False
        self.m_ready.setChecked(False)
        self.m_last_calls = []
        self.m_last_child = None
        self.pause_update_playback()
        self.m_update_calls = []
        self.m_child_present.setChecked(False)
        self.m_child_pending.setChecked(True)
        self.m_exit_input.setChecked(False)
        self.redraw()
        return True

    def load_archive_assets(self, virtual_files):
        # No raw archive assets are loaded by this diagnostic inspector.
        # Reset stale handoffs when the editor switches game archives.
        self.reset()

    def step_loader(self):
        result = self.m_bootstrap.loader_step(self.m_ready.isChecked())
        self.m_last_calls = result['calls']
        self.redraw()

    def inspect_child(self):
        self.m_last_child = self.m_bootstrap.inspect_child(
            self.m_child_combo.currentData())
        self.redraw()

    def reset(self):
        self.pause_update_playback()
        self.m_bootstrap = c_demo_main_bootstrap()
        self.m_last_calls = []
        self.m_last_child = None
        self.m_update_calls = []
        self.m_ready.setChecked(False)
        self.m_child_present.setChecked(False)
        self.m_child_pending.setChecked(True)
        self.m_exit_input.setChecked(False)
        self.redraw()

    def set_captured_choice(self):
        runtime = self.m_bootstrap.m_update
        if runtime.snapshot()['phase'] == 0 and not runtime.snapshot()['finished']:
            runtime.set_captured_next_choice(self.m_next_choice.currentData())
            self.redraw()

    def step_update(self):
        runtime = self.m_bootstrap.m_update
        if runtime.snapshot()['finished']:
            self.pause_update_playback()
            return
        result = runtime.step(
            child_present=self.m_child_present.isChecked(),
            child_pending=self.m_child_pending.isChecked(),
            external_exit=self.m_exit_input.isChecked())
        self.m_update_calls = result['calls']
        self.m_exit_input.setChecked(False)
        if result['finished']:
            self.pause_update_playback()
        self.redraw()

    def toggle_update_playback(self):
        if self.m_update_timer.isActive():
            self.pause_update_playback()
        elif not self.m_bootstrap.m_update.snapshot()['finished']:
            self.m_update_timer.start()
        self.redraw()

    def pause_update_playback(self):
        self.m_update_timer.stop()
        self.m_update_play.setText('Play')

    def reset_update(self):
        from arika_demo_main_update import c_demo_main_update
        self.pause_update_playback()
        self.m_bootstrap.m_update = c_demo_main_update()
        self.m_update_calls = []
        self.m_exit_input.setChecked(False)
        self.redraw()

    def hideEvent(self, event):
        self.pause_update_playback()
        self.redraw()
        super().hideEvent(event)

    def closeEvent(self, event):
        self.pause_update_playback()
        super().closeEvent(event)

    def redraw(self):
        snapshot = self.m_bootstrap.snapshot()
        self.m_route.setText(
            ('Title Screen (ID 2) requested CAppDemoMain (ID 6); '
             'factory dispatch is diagnostic only.'
             if snapshot['handoff_requested'] else
             'No title handoff yet. Finish Title Screen and choose '
             '"Inspect destination (ID 6)", or inspect the loader directly.'))
        self.m_status.setText(
            'Loader phase %d | steps %d | %s | last native callbacks: %s' %
            (snapshot['load_phase'], snapshot['load_updates'],
             'ready' if snapshot['ready'] else 'not ready',
             ', '.join(item['address'] for item in self.m_last_calls)
             if self.m_last_calls else 'none'))
        self.m_step.setEnabled(not snapshot['ready'])
        if self.m_last_child is None:
            self.m_child_info.setText(
                'Native 0x3E0830 child-branch sites can request '
                'IDs 4, 7, 8 or 9 through 0x3DFBD0. '
                'Inspecting a branch does not execute it.')
        else:
            child = self.m_last_child
            self.m_child_info.setText(
                'EE 0x%08X requests ID %d%s through 0x3DFBD0. '
                'Branch selected for inspection only; no native '
                'conditions, game state or child construction asserted.' %
                (child['request_site'], child['requested_child_id'],
                 ' (%s)' % child['registered_class']
                 if child['registered_class'] else ' (unresolved)'))
        update = self.m_bootstrap.m_update.snapshot()
        child = update['last_child']
        child_text = (
            '%d: %s (factory 0x%X)' %
            (child['id'], child['name'], child['factory'])
            if child is not None else 'none')
        self.m_update_status.setText(
            '%s | phase %d | current %d, next %d | '
            'child requests %d | last: %s | return ID %d | ticks %d' %
            ('Complete' if update['finished'] else
             'Playing (diagnostic 100 ms UI cadence)'
             if self.m_update_timer.isActive() else 'Paused',
             update['phase'], update['current_choice'],
             update['next_choice'], update['child_requests'],
             child_text, update['return_app'], update['updates']))
        trace = ', '.join(
            '%s(%s)' % (call['address'], ','.join(map(str,call['arguments'])))
            for call in self.m_update_calls)
        destination = (
            resolve_app(update['last_return'])
            if update['finished'] else None)
        self.m_update_trace.setText(
            'Native calls (recorded, not executed): ' +
            (trace or 'none') +
            (' | Requested parent application ID %d (%s; factory 0x%X)' %
             (update['last_return'], destination['class_name'],
              destination['factory'])
             if destination is not None else ''))
        self.m_update_play.setEnabled(not update['finished'])
        self.m_update_step.setEnabled(
            not update['finished'] and not self.m_update_timer.isActive())
        self.m_update_play.setText(
            'Pause' if self.m_update_timer.isActive() else 'Play')
        self.m_set_choice.setEnabled(
            not update['finished'] and update['phase'] == 0
            and not self.m_update_timer.isActive())
