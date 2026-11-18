"""Asset-backed EU-beta Press Start inside the existing Arika Editor.

Known sprite layers use original game resources. Captures remain separate
references rather than replacements for unsupported native GS operations.
"""
from PySide6 import QtCore as C, QtGui as G, QtWidgets as W

from arika_press_start_runtime import (
    PRESS_START_APP_ID, PRESS_START_UPDATE, PRESS_START_BUTTON_BIT,
    PHASE_WAIT_FOR_START, c_press_start_runtime,
)
from arika_app_registry import resolve_app
from arika_press_start_rendering import (
    load_press_start_archive_images, load_press_start_archive_font,
    raster_press_start_copyright, render_press_start_image,
    press_start_comparison_image, press_start_comparison_metrics,
)
from arika_press_start_animation import c_press_start_prompt_clock
from arika_press_start_prompt_layout import PRESS_START_PROMPT_CASES


# Actual viewport bounds measured from the user's 1920x1040 PCSX2
# screenshots. This only crops a reference; it is NOT a native
# GS register/viewport assertion or a generally valid capture crop.
PCSX2_REFERENCE_SIZE = (1920, 1040)
PCSX2_REFERENCE_RECT = (357, 111, 1206, 903)


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
        self.m_images = (None, None, None)
        self.m_asset_errors = (
            'Open an EU-beta INFO.DAT / GAME.DAT archive',) * 3
        self.m_copyright_images = None
        self.m_font_error = 'Original game FFON not loaded'
        self.m_prompt_clock = c_press_start_prompt_clock()

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
            'Select the original visible/hidden PCSX2 reference independently '
            'of the native shared prompt clock.')
        self.m_prompt_visible.toggled.connect(self.redraw)
        self.m_clock_enabled = W.QCheckBox('Native UI clock updates')
        self.m_clock_enabled.setChecked(True)
        self.m_clock_enabled.setToolTip(
            'Models the external 0x2CB710 scheduler gate using the supplied '
            'step delta. The clock is global, not the application idle age.')
        self.m_view_mode = W.QComboBox()
        self.m_view_mode.addItems((
            'Reconstruction', 'Side-by-side comparison', 'Reference capture'))
        self.m_view_mode.setToolTip(
            'Reference screenshots are never used as native sprite textures.')
        self.m_view_mode.currentIndexChanged.connect(self.redraw)
        self.m_prompt_case = W.QComboBox()
        for case in sorted(PRESS_START_PROMPT_CASES):
            self.m_prompt_case.addItem('Native prompt case %d' % case, case)
        self.m_prompt_case.setCurrentIndex(1)
        self.m_prompt_case.setToolTip(
            'Manual diagnostic selection of ELF dispatch cases 0..4. '
            'Actual controller-service state to case mapping is unverified.')
        self.m_prompt_case.currentIndexChanged.connect(self.invalidate_comparison)
        self.m_load_hidden = W.QPushButton('Load PCSX2 capture: no prompt')
        self.m_load_visible = W.QPushButton('Load PCSX2 capture: prompt')
        self.m_load_hidden.clicked.connect(self.choose_hidden_capture)
        self.m_load_visible.clicked.connect(self.choose_visible_capture)
        self.m_measure = W.QPushButton('Measure both PCSX2 states')
        self.m_measure.setToolTip(
            'Compute unaligned pixel differences from original archive sprites; '
            'this does not establish PS2 GS pixel parity.')
        self.m_measure.clicked.connect(self.measure_both_captures)
        self.m_comparison_stats = W.QLabel()
        self.m_comparison_stats.setWordWrap(True)
        self.m_comparison_stats.setText('Comparison metrics: not measured')

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
            'Decoded original sprites, copyright symbols and FFON text are '
            'placed using recovered ELF draw arguments. The shared native '
            'clock gates the atlas-backed prompt. This is NOT recreated '
            'native GS output. Global clock phase at screen entry, final '
            'GS blending/filtering, other controller variants and pixel '
            'parity remain unverified.')
        self.m_notice.setWordWrap(True)

        layout = W.QVBoxLayout(self)
        layout.addWidget(self.m_canvas, 1)
        references = W.QHBoxLayout()
        references.addWidget(self.m_load_hidden)
        references.addWidget(self.m_load_visible)
        references.addWidget(self.m_prompt_visible)
        references.addWidget(self.m_clock_enabled)
        references.addWidget(self.m_view_mode)
        references.addWidget(self.m_measure)
        references.addWidget(self.m_prompt_case)
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
        layout.addWidget(self.m_comparison_stats)
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
        self.m_comparison_stats.setText('Comparison metrics: not measured')
        self.redraw()
        return selected

    def invalidate_comparison(self):
        self.m_comparison_stats.setText('Comparison metrics: not measured')
        self.redraw()

    def measure_both_captures(self):
        """Only report measurable differences; never auto-claim parity."""
        try:
            result = press_start_comparison_metrics(
                self.m_images, self.m_reference_hidden,
                self.m_reference_visible, self.m_copyright_images,
                prompt_case=self.m_prompt_case.currentData())
            hidden = result['reference_states']['hidden']['all_pixels']
            visible = result['reference_states']['visible']['all_pixels']
            self.m_comparison_stats.setText(
                'Measured (bilinear resize, no registration; NOT GS parity): '
                'hidden MAE %.3f RMSE %.3f | '
                'visible MAE %.3f RMSE %.3f' %
                (hidden['mean_absolute_error'],
                 hidden['root_mean_square_error'],
                 visible['mean_absolute_error'],
                 visible['root_mean_square_error']))
        except (ValueError, TypeError) as error:
            self.m_comparison_stats.setText(
                'Comparison unavailable: ' + str(error))

    def clear_reference_captures(self):
        self.m_reference_hidden = None
        self.m_reference_visible = None
        self.m_comparison_stats.setText('Comparison metrics: not measured')
        self.m_reference_error = None
        self.redraw()

    def load_archive_assets(self, virtual_files):
        """Swap in only ELF-backed resources; discard stale archive state."""
        self.pause_playback()
        self.m_images = (None, None, None)
        self.m_asset_errors = ('Archive not loaded',) * 3
        self.m_comparison_stats.setText('Comparison metrics: not measured')
        self.m_copyright_images = None
        self.m_font_error = 'Archive not loaded'
        self.m_prompt_clock = c_press_start_prompt_clock()
        self.m_reference_hidden = None
        self.m_reference_visible = None
        self.m_reference_error = None
        self.m_runtime = c_press_start_runtime()
        self.m_last_calls = self.m_runtime.begin()
        self.m_prompt_visible.setChecked(True)
        self.m_transition_busy.setChecked(False)
        self.m_idle_reset.setChecked(False)
        self.m_view_mode.setCurrentIndex(0)
        self.m_prompt_case.setCurrentIndex(1)
        images, errors = load_press_start_archive_images(virtual_files)
        self.m_images = tuple(images)
        self.m_asset_errors = tuple(errors)
        font, font_data, error = load_press_start_archive_font(virtual_files)
        self.m_font_error = error
        if font is not None:
            try:
                self.m_copyright_images = raster_press_start_copyright(
                    font, font_data)
            except (ValueError, TypeError) as failure:
                self.m_font_error = str(failure)
        self.redraw()
        return sum(image is not None for image in images)

    def current_reconstruction(self):
        """Return decoded original sprite pixels, never screenshot pixels."""
        return render_press_start_image(
            self.m_images, self.m_copyright_images,
            prompt_visible=self.m_prompt_clock.visible, fade_alpha=1.0,
            prompt_case=self.m_prompt_case.currentData())

    def draw_canvas(self):
        show_prompt = (self.m_prompt_visible.isChecked() and
                       self.m_runtime.snapshot()['phase'] ==
                       PHASE_WAIT_FOR_START)
        reference = (self.m_reference_visible if show_prompt else
                     self.m_reference_hidden)
        reconstruction = self.current_reconstruction()
        mode = self.m_view_mode.currentIndex()
        if mode == 2 and reference is not None:
            image = reference
        elif mode == 1 and reference is not None and reconstruction is not None:
            image = press_start_comparison_image(reconstruction, reference)
        elif reconstruction is not None:
            image = reconstruction
        else:
            # A reference frame must not fill in missing native game artwork.
            image = press_start_diagnostic_canvas(show_prompt)
        comparison_ready = (mode == 1 and reference is not None and
                            reconstruction is not None)
        aspect = (C.QSize(1280, 480) if comparison_ready else C.QSize(640, 480))
        size = aspect.scaled(
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
            'reference captures %d/2 | decoded resources %d/3 | '
            'native prompt %.4f s (%s) | prompt case %d | FFON %s%s' %
            (state, PRESS_START_APP_ID, snapshot['phase'],
             snapshot['elapsed_seconds'], snapshot['updates'],
             'done' if snapshot['one_shot'] else 'pending',
             target_name, capture_count,
             sum(image is not None for image in self.m_images),
             self.m_prompt_clock.phase,
             'visible' if self.m_prompt_clock.visible else 'hidden',
             self.m_prompt_case.currentData(),
             'loaded' if self.m_copyright_images is not None else 'missing',
             ' | ' + self.m_reference_error if self.m_reference_error else ''))
        self.m_measure.setEnabled(
            self.m_reference_hidden is not None and
            self.m_reference_visible is not None and
            any(image is not None for image in self.m_images[:2]))
        self.m_notice.setToolTip(
            '\n'.join([error for error in self.m_asset_errors if error] +
                      ([self.m_font_error] if self.m_font_error else [])))
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
        self.m_prompt_clock.advance(
            delta_seconds, self.m_clock_enabled.isChecked())
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
        self.m_prompt_clock = c_press_start_prompt_clock()
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
