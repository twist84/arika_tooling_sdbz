"""CAppWarning screen inside the existing EU-beta Arika Editor workspace.

The original warning resource is resolved from the editor archive; the
visible choice labels are a Qt diagnostic, NOT a reproduction of the
game's native FFON/GS text draws. No video-mode or app-switch effects
are executed on the host computer.
"""
from PySide6 import QtCore as C, QtGui as G, QtWidgets as W

from arika_logo_preview import decode_logo_texture
from arika_warning_runtime import (
    WARNING_RESOURCE, WARNING_OPTIONS, WARNING_SOURCE_RECT,
    WARNING_DEST_RECT, c_warning_runtime, PHASE_SELECTION, PHASE_VIDEO_MODE,
    PAD_NEXT, PAD_PREVIOUS, PAD_CONFIRM,
)


def load_warning_archive_image(virtual_files):
    """Require the exact native asset key, with optional .pix suffix."""
    if not hasattr(virtual_files, 'items'):
        raise TypeError('expected an editor archive file mapping')
    matches = []
    for path, data in virtual_files.items():
        if not isinstance(path, str):
            continue
        key = path.replace('\\', '/').lstrip('/').lower()
        if key in (WARNING_RESOURCE, WARNING_RESOURCE + '.pix'):
            matches.append((path, data))
    if not matches:
        return None, WARNING_RESOURCE + ': not found in opened archive'
    if len(matches) != 1:
        return None, WARNING_RESOURCE + ': ambiguous duplicate resource'
    try:
        image = decode_logo_texture(matches[0][1])
        if image.width() < WARNING_SOURCE_RECT[2] or image.height() < WARNING_SOURCE_RECT[3]:
            raise ValueError('native warning rectangle exceeds texture dimensions')
        return image, None
    except (TypeError, ValueError) as error:
        return None, WARNING_RESOURCE + ': ' + str(error)


def warning_diagnostic_canvas(snapshot, image):
    """Draw verified 512x448 sprite bounds or clearly diagnostic choice text."""
    canvas = G.QImage(WARNING_DEST_RECT[2], WARNING_DEST_RECT[3],
                      G.QImage.Format.Format_ARGB32_Premultiplied)
    canvas.fill(G.QColor(0, 0, 0))
    painter = G.QPainter(canvas)
    try:
        if snapshot['phase'] == PHASE_VIDEO_MODE:
            # Native draw does nothing in phase 10.
            pass
        elif snapshot['image_visible']:
            if image is not None:
                painter.setRenderHint(G.QPainter.RenderHint.SmoothPixmapTransform, True)
                painter.drawImage(C.QRectF(*WARNING_DEST_RECT), image,
                                  C.QRectF(*WARNING_SOURCE_RECT))
            else:
                painter.setPen(G.QColor(220, 220, 220))
                painter.drawText(canvas.rect(), C.Qt.AlignmentFlag.AlignCenter,
                                 'Original warning image unavailable')
        else:
            # The native callback draws four text entries using 0x2CDCA0.
            # Their labels and selected index are verified; fonts, colors
            # and exact resulting glyph positions have NOT been recovered.
            painter.setFont(G.QFont('Sans Serif', 20))
            for index, label in enumerate(WARNING_OPTIONS):
                y = 112 + index * 40
                selected = index == snapshot['selection']
                painter.setPen(G.QColor(245, 245, 245) if selected else
                               G.QColor(160, 160, 160))
                painter.drawText(C.QPointF(112, y), label.strip())
                if selected:
                    painter.drawRect(C.QRectF(94, y - 27, 340, 34))
    finally:
        painter.end()
    return canvas


class c_warning_preview(W.QWidget):
    """Native warning flow, manual stepping and optional timed playback."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.m_runtime = c_warning_runtime()
        self.m_image = None
        self.m_error = 'Open an EU-beta INFO.DAT / GAME.DAT archive'
        self.m_events = []

        self.m_timer = C.QTimer(self)
        self.m_timer.setTimerType(C.Qt.TimerType.PreciseTimer)
        self.m_timer.setInterval(16)
        self.m_timer.timeout.connect(self.advance_playback)
        self.m_elapsed = C.QElapsedTimer()
        self.m_last_elapsed_ns = 0

        self.m_canvas = W.QLabel()
        self.m_canvas.setMinimumSize(220, 165)
        self.m_canvas.setSizePolicy(W.QSizePolicy.Policy.Ignored,
                                    W.QSizePolicy.Policy.Ignored)
        self.m_canvas.setAlignment(C.Qt.AlignmentFlag.AlignCenter)
        self.m_canvas.setStyleSheet('background-color: black;')
        self.m_canvas.installEventFilter(self)

        self.m_delta = W.QDoubleSpinBox()
        self.m_delta.setRange(0.0, 60.0)
        self.m_delta.setDecimals(6)
        self.m_delta.setSingleStep(1.0 / 60.0)
        self.m_delta.setValue(0)
        self.m_delta.setSuffix(' seconds')
        self.m_busy = W.QCheckBox('External transition busy (0x2C0C20)')
        self.m_busy.setToolTip(
            'Manually supply the game transition helper result. '
            'The preview does not run the native audio/fade subsystem.')

        self.m_next = W.QPushButton('Next option (bit 0x2)')
        self.m_previous = W.QPushButton('Previous option (bit 0x1)')
        self.m_confirm = W.QPushButton('Confirm (bit 0x80)')
        self.m_next.clicked.connect(lambda: self.press_input(PAD_NEXT))
        self.m_previous.clicked.connect(lambda: self.press_input(PAD_PREVIOUS))
        self.m_confirm.clicked.connect(lambda: self.press_input(PAD_CONFIRM))

        self.m_step = W.QPushButton('Step one update')
        self.m_play = W.QPushButton('Play')
        self.m_reset = W.QPushButton('Reset')
        self.m_step.clicked.connect(self.step)
        self.m_play.clicked.connect(self.toggle_play)
        self.m_reset.clicked.connect(self.reset)

        self.m_status = W.QLabel()
        self.m_status.setWordWrap(True)
        self.m_provenance = W.QLabel(
            'ELF-derived options and timing; Qt diagnostic labels only. '
            'Original video-mode and application calls are reported, not executed.')
        self.m_provenance.setWordWrap(True)

        layout = W.QVBoxLayout(self)
        layout.addWidget(self.m_canvas, 1)
        inputs = W.QHBoxLayout()
        inputs.addWidget(self.m_previous)
        inputs.addWidget(self.m_next)
        inputs.addWidget(self.m_confirm)
        inputs.addStretch()
        layout.addLayout(inputs)
        controls = W.QHBoxLayout()
        controls.addWidget(W.QLabel('Manual delta'))
        controls.addWidget(self.m_delta)
        controls.addWidget(self.m_busy)
        controls.addWidget(self.m_step)
        controls.addWidget(self.m_play)
        controls.addWidget(self.m_reset)
        controls.addStretch()
        layout.addLayout(controls)
        layout.addWidget(self.m_status)
        layout.addWidget(self.m_provenance)
        self.redraw()

    def eventFilter(self, watched, event):
        if watched is self.m_canvas and event.type() == C.QEvent.Type.Resize:
            self.draw_canvas()
        return super().eventFilter(watched, event)

    def load_archive_assets(self, virtual_files):
        self.pause_playback()
        self.m_image, self.m_error = load_warning_archive_image(virtual_files)
        self.m_runtime = c_warning_runtime()
        self.m_busy.setChecked(False)
        self.m_events = []
        self.redraw()
        return int(self.m_image is not None)

    def draw_canvas(self):
        image = warning_diagnostic_canvas(self.m_runtime.snapshot(), self.m_image)
        size = C.QSize(640, 480).scaled(
            self.m_canvas.size(), C.Qt.AspectRatioMode.KeepAspectRatio)
        pixmap = G.QPixmap.fromImage(image).scaled(
            size, C.Qt.AspectRatioMode.IgnoreAspectRatio,
            C.Qt.TransformationMode.SmoothTransformation)
        self.m_canvas.setPixmap(pixmap)

    def redraw(self):
        snapshot = self.m_runtime.snapshot()
        self.draw_canvas()
        available = self.m_error or 'native warning image decoded'
        events = ', '.join(event['address'] for event in self.m_events)
        self.m_status.setText(
            '%s | option %d: %s | phase %d | test remaining %.4f s | '
            'update %d | %s | %s%s' %
            ('Complete' if snapshot['finished'] else
             'Playing' if self.m_timer.isActive() else 'Paused',
             snapshot['selection'], snapshot['choice_text'].strip(),
             snapshot['phase'], snapshot['countdown_seconds'],
             snapshot['updates'], available,
             'TEST image' if snapshot['image_visible'] else 'Choice text (debug)',
             ' | calls: ' + events if events else ''))
        self.m_step.setEnabled(not snapshot['finished'] and
                               not self.m_timer.isActive())
        self.m_play.setEnabled(not snapshot['finished'])
        self.m_play.setText('Pause' if self.m_timer.isActive() else 'Play')
        for button in (self.m_next, self.m_previous, self.m_confirm):
            button.setEnabled(snapshot['phase'] == PHASE_SELECTION and
                              not snapshot['finished'])

    def advance_native(self, delta_seconds, input_mask=0):
        if self.m_runtime.snapshot()['finished']:
            return
        result = self.m_runtime.step(
            delta_seconds, self.m_busy.isChecked(), input_mask)
        self.m_events = result['events']
        if result['finished']:
            self.pause_playback()
        self.redraw()

    def step(self):
        if not self.m_timer.isActive():
            self.advance_native(self.m_delta.value())

    def press_input(self, mask):
        if self.m_runtime.snapshot()['phase'] != PHASE_SELECTION:
            return
        if self.m_timer.isActive():
            now = self.m_elapsed.nsecsElapsed()
            seconds = max(0, now - self.m_last_elapsed_ns) / 1000000000.0
            self.m_last_elapsed_ns = now
        else:
            seconds = self.m_delta.value()
        self.advance_native(seconds, mask)

    def toggle_play(self):
        if self.m_timer.isActive():
            self.pause_playback()
        elif not self.m_runtime.snapshot()['finished']:
            self.m_last_elapsed_ns = 0
            self.m_elapsed.start()
            self.m_timer.start()
        self.redraw()

    def advance_playback(self):
        if not self.m_timer.isActive():
            return
        now = self.m_elapsed.nsecsElapsed()
        seconds = max(0, now - self.m_last_elapsed_ns) / 1000000000.0
        self.m_last_elapsed_ns = now
        self.advance_native(seconds)

    def pause_playback(self):
        self.m_timer.stop()
        self.m_last_elapsed_ns = 0
        self.m_play.setText('Play')
        self.m_step.setEnabled(not self.m_runtime.snapshot()['finished'])

    def reset(self):
        self.pause_playback()
        self.m_runtime = c_warning_runtime()
        self.m_events = []
        self.redraw()

    def hideEvent(self, event):
        self.pause_playback()
        self.redraw()
        super().hideEvent(event)

    def closeEvent(self, event):
        self.pause_playback()
        super().closeEvent(event)
