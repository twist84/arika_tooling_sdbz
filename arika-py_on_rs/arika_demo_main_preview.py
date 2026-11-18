"""Read-only DemoMain entry inspector embedded in the Arika Editor.

It does NOT render movie data or drive the full 0x3E0830 update.
Loader readiness and child choices are independently controlled,
and host callbacks are never executed.
"""
from PySide6 import QtWidgets as W

from arika_app_registry import resolve_app
from arika_demo_main_runtime import c_demo_main_bootstrap, DEMO_MAIN_RESOURCE_GROUPS


class c_demo_main_preview(W.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.m_bootstrap = c_demo_main_bootstrap()
        self.m_last_calls = []
        self.m_last_child = None

        title = W.QLabel('CAppDemoMain — native application ID 6')
        title.setStyleSheet('font-size:18px;font-weight:bold;')
        self.m_route = W.QLabel()
        self.m_route.setWordWrap(True)
        self.m_factories = W.QLabel(
            'Lookup 0x3F1C40 → factory 0x3F2C00 → '
            'constructor 0x3E03E0 → CAppDemoMain. '
            'Child application ID 7 is CAppDemoMovie.')
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
        self.m_status = W.QLabel()
        self.m_status.setWordWrap(True)
        self.m_notice = W.QLabel(
            'This is a verified app-manager/loader inspector, not an '
            'emulated movie player or guessed menu screen. '
            'No game-global allocations, streaming or app switches run.')
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
        layout.addWidget(self.m_notice)
        layout.addStretch(1)
        self.redraw()

    def accept_title_result(self, result):
        if not self.m_bootstrap.accept_title_result(result):
            return False
        self.m_ready.setChecked(False)
        self.m_last_calls = []
        self.m_last_child = None
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
        self.m_bootstrap = c_demo_main_bootstrap()
        self.m_last_calls = []
        self.m_last_child = None
        self.m_ready.setChecked(False)
        self.redraw()

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
