"""Press Start (original EU-beta app ID 3) inside the existing editor.

The game scene is composed from dynamically streamed resources and GS
draws. The editor does not claim to render them. Optionally load the
user's two PCSX2 captures as exact visual references, one with and
one without the PRESS START button prompt. No image is bundled.
"""
from PySide6 import QtCore as C, QtGui as G, QtWidgets as W

from arika_press_start_runtime import (
    PRESS_START_APP_ID, PRESS_START_UPDATE, PRESS_START_BUTTON_BIT,
    PHASE_WAIT_FOR_START, c_press_start_runtime,
)
from arika_app_registry import resolve_app


# Actual viewport bounds measured from the user's 1920x1040 PCSX2
# screenshots. This only crops a reference; it is NOT a native
# GS register/viewport assertion or a generally valid capture crop.
PCSX2_REFERENCE_SIZE = (1920, 1040)
PCSX2_REFERENCE_RECT = (307, 96, 1040, 778)


def extract_press_start_reference(image):
    """Return 4:3 game picture, removing PCSX2 chrome on known captures."""
    if image is None or image.isNull():
        raise ValueError('reference image is empty or unsupported')
    width = image.width()
    height = image.height()
    if (width, height) == PCSX2_REFERENCE_SIZE:
        return image.copy(C.QRect(*PCSX2_REFERENCE_RECT))
    ratio = width / height
    if abs(ratio - 4.0 / 3.0) > 0.025:
        raise ValueError(
            'expected a 4:3 game-only image or the user-provided '
            '1920x1040 PCSX2 screenshot layout')
    return image.copy()


def press_start_diagnostic_canvas(show_prompt):
    """Explicit approximate fallback — no background/logo art invented."""
    canvas = G.QImage(640, 480, G.QImage.Format.Format_ARGB32)
    canvas.fill(G.QColor(16, 24, 33))
    painter = G.QPainter(canvas)
    try:
        painter.setPen(G.QColor(180, 195, 206))
        painter.setFont(G.QFont('Sans Serif', 12))
        painter.drawText(
            canvas.rect().adjusted(40, 35, -40, -220),
            C.Qt.AlignmentFlag.AlignCenter | C.Qt.TextFlag.TextWordWrap,
            'Press Start (native app ID 3)\n'
            'Open both reference captures for the original scene.')
        if show_prompt:
            font = G.QFont('Sans Serif', 25)
            font.setBold(True)
            painter.setFont(font)
            bounds = C.QRectF(30, 360, 580, 54)
            painter.setPen(G.QPen(G.QColor(0, 0, 0), 5))
            painter.drawText(bounds.translated(2, 2),
                             C.Qt.AlignmentFlag.AlignCenter,
                             'PRESS START button')
            painter.setPen(G.QColor(54, 166, 255))
            painter.drawText(bounds, C.Qt.AlignmentFlag.AlignCenter,
                             'PRESS START button')
        painter.setPen(G.QColor(140, 160, 177))
        painter.setFont(G.QFont('Sans Serif', 10))
        painter.drawText(
            C.QRectF(20, 430, 600, 30),
            C.Qt.AlignmentFlag.AlignCenter,
            'Diagnostic placeholder; not decoded PS2 graphics')
    finally:
        painter.end()
    return canvas


class c_press_start_preview(W.QWidget):
    """Native lifecycle + optional exact capture frame comparison."""

    # A diagnostic notification; no automatic game factory execution.
    transition_requested = C.Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.m_runtime = c_press_start_runtime()
        self.m_last_calls = self.m_runtime.begin()
        self.m_reference_hidden = None
        self.m_reference_visible = None
        self.m_reference_error = None

        self.m_timer = C.QTimer(self)
        self.m_timer.setTimerType(C.Qt.TimerType.PreciseTimer)
        self.m_timer.setInterval(16)
        self.m_timer.timeout.connect(self.advance_playback)
        self.m_elapsed_clock = C.QElapsedTimer()
        self.m_last_elapsed_ns = 0

        self.m_canvas = W.QLabel()
        self.m_canvas.setAlignment(C.Qt.AlignmentFlag.AlignCenter)
        self.m_canvas.setSizePolicy(W.QSizePolicy.Policy.Ignored,
                                    W.QSizePolicy.Policy.Ignored)
        self.m_canvas.setMinimumSize(240, 180)
        self.m_canvas.setStyleSheet('background-color:black;')
        self.m_canvas.installEventFilter(self)

        self.m_prompt_visible = W.QCheckBox('Show PRESS START prompt')
        self.m_prompt_visible.setChecked(True)
        self.m_prompt_visible.setToolTip(
            'Choose the visible/hidden reference frame manually. '
            'The native prompt blink timing is not yet verified.')
        self.m_prompt_visible.toggled.connect(self.redraw)
        self.m_load_hidden = W.QPushButton('Load PCSX2 capture: no prompt')
        self.m_load_visible = W.QPushButton('Load PCSX2 capture: prompt')
        self.m_load_hidden.clicked.connect(self.choose_hidden_capture)
        self.m_load_visible.clicked.connect(self.choose_visible_capture)

        self.m_delta = W.QDoubleSpinBox()
        self.m_delta.setRange(0, 60)
        self.m_delta.setDecimals(6)
        self.m_delta.setSingleStep(1.0 / 60.0)
        self.m_delta.setSuffix(' seconds')
        self.m_delta.setValue(0.0)

        self.m_controller0_ready = W.QCheckBox('Controller 0 eligible')
        self.m_controller1_ready = W.QCheckBox('Controller 1 eligible')
        self.m_controller0_ready.setChecked(True)
        self.m_controller1_ready.setChecked(True)
        self.m_transition_busy = W.QCheckBox('Native transition busy')
        self.m_idle_reset = W.QCheckBox('External idle-timer reset (0x2AFD30)')
        self.m_idle_reset.setToolTip(
            'When the native 0x2AFD30 helper returns true, '
            'the elapsed idle timer is reset on that update.')

        self.m_start_0 = W.QPushButton('Start (controller 0, bit 0x10)')
        self.m_start_1 = W.QPushButton('Start (controller 1, bit 0x10)')
        self.m_start_0.clicked.connect(self.press_start_0)
        self.m_start_1.clicked.connect(self.press_start_1)

        self.m_step = W.QPushButton('Step one native update')
        self.m_play = W.QPushButton('Play')
        self.m_reset = W.QPushButton('Reset')
        self.m_step.clicked.connect(self.step)
        self.m_play.clicked.connect(self.toggle_play)
        self.m_reset.clicked.connect(self.reset)
        self.m_inspect = W.QPushButton('Inspect destination')
        self.m_inspect.clicked.connect(self.inspect_destination)

        self.m_status = W.QLabel()
        self.m_status.setWordWrap(True)
        self.m_calls = W.QLabel()
        self.m_calls.setWordWrap(True)
        self.m_notice = W.QLabel(
            'The original background, logo, and copyright graphics are '
            'not synthesized. Loaded PCSX2 images are pixel-reference '
            'captures, NOT recreated native GS rendering. '
            'Prompt visibility is manually selectable; no blink rate '
            'has been guessed.')
        self.m_notice.setWordWrap(True)

        layout = W.QVBoxLayout(self)
        layout.addWidget(self.m_canvas, 1)
        references = W.QHBoxLayout()
        references.addWidget(self.m_load_hidden)
        references.addWidget(self.m_load_visible)
        references.addWidget(self.m_prompt_visible)
        references.addStretch()
        layout.addLayout(references)
        inputs = W.QHBoxLayout()
        inputs.addWidget(self.m_controller0_ready)
        inputs.addWidget(self.m_controller1_ready)
        inputs.addWidget(self.m_transition_busy)
        inputs.addWidget(self.m_idle_reset)
        inputs.addStretch()
        layout.addLayout(inputs)
        start_buttons = W.QHBoxLayout()
        start_buttons.addWidget(self.m_start_0)
        start_buttons.addWidget(self.m_start_1)
        start_buttons.addStretch()
        layout.addLayout(start_buttons)
        playback = W.QHBoxLayout()
        playback.addWidget(W.QLabel('Manual delta'))
        playback.addWidget(self.m_delta)
        playback.addWidget(self.m_step)
        playback.addWidget(self.m_play)
        playback.addWidget(self.m_reset)
        playback.addWidget(self.m_inspect)
        playback.addStretch()
        layout.addLayout(playback)
        layout.addWidget(self.m_status)
        layout.addWidget(self.m_calls)
        layout.addWidget(self.m_notice)
        self.redraw()

    def eventFilter(self, watched, event):
        if watched is self.m_canvas and event.type() == C.QEvent.Type.Resize:
            self.draw_canvas()
        return super().eventFilter(watched, event)

    def choose_hidden_capture(self):
        self.choose_capture(False)

    def choose_visible_capture(self):
        self.choose_capture(True)

    def choose_capture(self, visible):
        path, _ = W.QFileDialog.getOpenFileName(
            self, 'Choose user-owned PCSX2 capture',
            '', 'Images (*.png *.jpg *.jpeg *.bmp *.webp)')
        if path:
            try:
                self.load_reference_capture(path, visible)
            except ValueError as error:
                self.m_reference_error = str(error)
                self.redraw()

    def load_reference_capture(self, image_or_path, visible):
        """Load screenshot pixels locally, never save them into the repo."""
        if type(visible) is not bool:
            raise ValueError('visible must be a boolean')
        image = (image_or_path if isinstance(image_or_path, G.QImage) else
                 G.QImage(str(image_or_path)))
        selected = extract_press_start_reference(image)
        if visible:
            self.m_reference_visible = selected
        else:
            self.m_reference_hidden = selected
        self.m_reference_error = None
        self.redraw()
        return selected

    def clear_reference_captures(self):
        self.m_reference_hidden = None
        self.m_reference_visible = None
        self.m_reference_error = None
        self.redraw()

    def load_archive_assets(self, virtual_files):
        # The original scene is a composite of streamed game objects,
        # not a single proven PIX key. Never invent an archive key.
        self.pause_playback()
        self.m_reference_hidden = None
        self.m_reference_visible = None
        self.m_reference_error = None
        self.m_runtime = c_press_start_runtime()
        self.m_last_calls = self.m_runtime.begin()
        self.m_prompt_visible.setChecked(True)
        self.m_transition_busy.setChecked(False)
        self.m_idle_reset.setChecked(False)
        self.redraw()

    def draw_canvas(self):
        show_prompt = (self.m_prompt_visible.isChecked() and
                       self.m_runtime.snapshot()['phase'] ==
                       PHASE_WAIT_FOR_START)
        image = (self.m_reference_visible if show_prompt else
                 self.m_reference_hidden)
        if image is None:
            # The unmatched reference is NOT a substitute for native art.
            image = press_start_diagnostic_canvas(show_prompt)
        size = C.QSize(640, 480).scaled(
            self.m_canvas.size(), C.Qt.AspectRatioMode.KeepAspectRatio)
        pixmap = G.QPixmap.fromImage(image).scaled(
            size, C.Qt.AspectRatioMode.IgnoreAspectRatio,
            C.Qt.TransformationMode.SmoothTransformation)
        self.m_canvas.setPixmap(pixmap)

    def redraw(self):
        snapshot = self.m_runtime.snapshot()
        self.draw_canvas()
        state = ('Complete' if snapshot['finished'] else
                 'Playing' if self.m_timer.isActive() else 'Paused')
        target = snapshot['destination_id']
        app = resolve_app(target) if target is not None else None
        target_name = ('%d (%s)' % (target, app['class_name'])
                       if app else str(target) if target is not None
                       else 'none')
        capture_count = int(self.m_reference_hidden is not None) + int(
            self.m_reference_visible is not None)
        self.m_status.setText(
            '%s | native app ID %d | phase %d | idle age %.4f s | '
            'updates %d | one-shot %s | destination %s | '
            'reference captures %d/2%s' %
            (state, PRESS_START_APP_ID, snapshot['phase'],
             snapshot['elapsed_seconds'], snapshot['updates'],
             'done' if snapshot['one_shot'] else 'pending',
             target_name, capture_count,
             ' | ' + self.m_reference_error if self.m_reference_error else ''))
        self.m_calls.setText(
            'Original calls (recorded, NOT executed): ' +
            (', '.join(call['address'] for call in self.m_last_calls)
             if self.m_last_calls else 'none'))
        self.m_play.setEnabled(not snapshot['finished'])
        self.m_play.setText('Pause' if self.m_timer.isActive() else 'Play')
        self.m_step.setEnabled(not snapshot['finished'] and
                               not self.m_timer.isActive())
        active = snapshot['phase'] == PHASE_WAIT_FOR_START
        self.m_start_0.setEnabled(active and not snapshot['finished'])
        self.m_start_1.setEnabled(active and not snapshot['finished'])
        self.m_inspect.setEnabled(snapshot['finished'])

    def advance_native(self, delta_seconds, controller=0):
        if self.m_runtime.snapshot()['finished']:
            return
        result = self.m_runtime.step(
            delta_seconds,
            transition_busy=self.m_transition_busy.isChecked(),
            controller0=(PRESS_START_BUTTON_BIT if controller == 1 else 0),
            controller1=(PRESS_START_BUTTON_BIT if controller == 2 else 0),
            controller0_ready=self.m_controller0_ready.isChecked(),
            controller1_ready=self.m_controller1_ready.isChecked(),
            idle_reset=self.m_idle_reset.isChecked())
        self.m_last_calls = result['calls']
        if result['finished']:
            self.pause_playback()
        self.redraw()

    def step(self):
        if not self.m_timer.isActive():
            self.advance_native(self.m_delta.value())

    def _press_start(self, controller):
        if self.m_runtime.snapshot()['phase'] != PHASE_WAIT_FOR_START:
            return
        if self.m_timer.isActive():
            now = self.m_elapsed_clock.nsecsElapsed()
            delta = max(0, now - self.m_last_elapsed_ns) / 1000000000.0
            self.m_last_elapsed_ns = now
        else:
            delta = self.m_delta.value()
        self.advance_native(delta, controller)

    def press_start_0(self):
        self._press_start(1)

    def press_start_1(self):
        self._press_start(2)

    def toggle_play(self):
        if self.m_timer.isActive():
            self.pause_playback()
        elif not self.m_runtime.snapshot()['finished']:
            self.m_last_elapsed_ns = 0
            self.m_elapsed_clock.start()
            self.m_timer.start()
        self.redraw()

    def advance_playback(self):
        if not self.m_timer.isActive():
            return
        now = self.m_elapsed_clock.nsecsElapsed()
        delta = max(0, now - self.m_last_elapsed_ns) / 1000000000.0
        self.m_last_elapsed_ns = now
        self.advance_native(delta)

    def pause_playback(self):
        self.m_timer.stop()
        self.m_last_elapsed_ns = 0
        self.m_play.setText('Play')
        self.m_step.setEnabled(not self.m_runtime.snapshot()['finished'])

    def reset(self):
        self.pause_playback()
        self.m_runtime = c_press_start_runtime()
        self.m_last_calls = self.m_runtime.begin()
        self.m_transition_busy.setChecked(False)
        self.m_idle_reset.setChecked(False)
        self.redraw()

    def inspect_destination(self):
        target = self.m_runtime.snapshot()['destination_id']
        if target is not None:
            self.transition_requested.emit(target)

    def hideEvent(self, event):
        self.pause_playback()
        self.redraw()
        super().hideEvent(event)

    def closeEvent(self, event):
        self.pause_playback()
        super().closeEvent(event)
