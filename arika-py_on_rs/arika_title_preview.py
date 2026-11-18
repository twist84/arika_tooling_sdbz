"""CAppTitleMain Qt diagnostic inside Arika Editor's existing Menu workspace.

Uses only original archived dis/d03/d03t0202 when unambiguously decoded.
The native sprite occupies 512x448. Playback runs the exact title
logical phases, but Qt does not execute the game's external fade,
GS or application-switch subsystems.
"""
from PySide6 import QtCore as C, QtGui as G, QtWidgets as W

from arika_logo_preview import decode_logo_texture
from arika_app_registry import title_handoff_request, resolve_app
from arika_title_runtime import (
    TITLE_RESOURCE, TITLE_SOURCE_RECT, TITLE_DEST_RECT, c_title_runtime,
)


def load_title_archive_image(virtual_files):
    """Require exact ELF-declared resource, with optional archive .pix suffix."""
    if not hasattr(virtual_files, 'items'):
        raise TypeError('expected editor virtual archive mapping')
    matches = []
    for name, payload in virtual_files.items():
        if not isinstance(name, str):
            continue
        key = name.replace('\\', '/').lstrip('/').lower()
        if key in (TITLE_RESOURCE, TITLE_RESOURCE + '.pix'):
            matches.append((name, payload))
    if len(matches) != 1:
        return None, (
            TITLE_RESOURCE + ': ' +
            ('not found in opened archive' if not matches else
             'ambiguous resource key')
        )
    try:
        image = decode_logo_texture(matches[0][1])
        if (image.width() < TITLE_SOURCE_RECT[2] or
                image.height() < TITLE_SOURCE_RECT[3]):
            raise ValueError('title asset smaller than verified native source rectangle')
        return image, None
    except (TypeError, ValueError) as error:
        return None, TITLE_RESOURCE + ': ' + str(error)


def title_diagnostic_canvas(image):
    """Draw the original asset with the title app's exact sprite rectangle."""
    canvas = G.QImage(TITLE_DEST_RECT[2], TITLE_DEST_RECT[3],
                      G.QImage.Format.Format_ARGB32_Premultiplied)
    canvas.fill(G.QColor(0, 0, 0))
    if image is not None:
        painter = G.QPainter(canvas)
        try:
            painter.setRenderHint(G.QPainter.RenderHint.SmoothPixmapTransform, True)
            painter.drawImage(C.QRectF(*TITLE_DEST_RECT), image,
                              C.QRectF(*TITLE_SOURCE_RECT))
        finally:
            painter.end()
    return canvas


class c_title_preview(W.QWidget):
    """Original-title app preview, embedded beside logos and warning."""

    handoff_requested = C.Signal(object)
    # Distinct from the manual Inspect Destination action.
    native_transition_completed = C.Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.m_runtime = c_title_runtime()
        self.m_image = None
        self.m_asset_error = 'Open an EU-beta INFO.DAT / GAME.DAT archive'
        self.m_last_calls = []
        self.m_last_result = None
        self.m_handoff = None

        self.m_timer = C.QTimer(self)
        self.m_timer.setTimerType(C.Qt.TimerType.PreciseTimer)
        self.m_timer.setInterval(16)
        self.m_timer.timeout.connect(self.advance_playback)
        self.m_elapsed = C.QElapsedTimer()
        self.m_last_elapsed_ns = 0

        self.m_canvas = W.QLabel()
        self.m_canvas.setAlignment(C.Qt.AlignmentFlag.AlignCenter)
        self.m_canvas.setMinimumSize(220, 165)
        self.m_canvas.setSizePolicy(W.QSizePolicy.Policy.Ignored,
                                    W.QSizePolicy.Policy.Ignored)
        self.m_canvas.setStyleSheet('background-color: black;')
        self.m_canvas.installEventFilter(self)

        self.m_delta = W.QDoubleSpinBox()
        self.m_delta.setRange(0.0, 60.0)
        self.m_delta.setDecimals(6)
        self.m_delta.setSingleStep(1.0 / 60.0)
        self.m_delta.setValue(0.0)
        self.m_delta.setSuffix(' seconds')

        self.m_busy = W.QCheckBox('External transition busy (0x2C0C20)')
        self.m_busy.setToolTip(
            'Supply the observed native transition-helper result. '
            'This does not recreate the original fade or audio subsystem.')

        self.m_step = W.QPushButton('Step one update')
        self.m_play = W.QPushButton('Play')
        self.m_reset = W.QPushButton('Reset')
        self.m_destination = W.QPushButton('Inspect destination (ID 6)')
        self.m_destination.setToolTip(
            'Open the registered CAppDemoMain factory/loader inspector; '
            'no game app switch or movie playback is executed.')
        self.m_destination.clicked.connect(self.inspect_destination)
        self.m_step.clicked.connect(self.step)
        self.m_play.clicked.connect(self.toggle_play)
        self.m_reset.clicked.connect(self.reset)

        self.m_status = W.QLabel()
        self.m_status.setWordWrap(True)
        self.m_notice = W.QLabel(
            'Native four-second app lifecycle; original sprite if available. '
            'Qt raster is diagnostic, not PS2 GS output. No real app switch.')
        self.m_notice.setWordWrap(True)

        layout = W.QVBoxLayout(self)
        layout.addWidget(self.m_canvas, 1)
        controls = W.QHBoxLayout()
        controls.addWidget(W.QLabel('Manual delta'))
        controls.addWidget(self.m_delta)
        controls.addWidget(self.m_busy)
        controls.addWidget(self.m_step)
        controls.addWidget(self.m_play)
        controls.addWidget(self.m_reset)
        controls.addWidget(self.m_destination)
        controls.addStretch()
        layout.addLayout(controls)
        layout.addWidget(self.m_status)
        layout.addWidget(self.m_notice)
        self.redraw()

    def eventFilter(self, watched, event):
        if watched is self.m_canvas and event.type() == C.QEvent.Type.Resize:
            self.draw_canvas()
        return super().eventFilter(watched, event)

    def load_archive_assets(self, virtual_files):
        self.pause_playback()
        self.m_image, self.m_asset_error = load_title_archive_image(virtual_files)
        self.m_runtime = c_title_runtime()
        self.m_busy.setChecked(False)
        self.m_last_calls = []
        self.m_last_result = None
        self.m_handoff = None
        self.redraw()
        return int(self.m_image is not None)

    def draw_canvas(self):
        image = title_diagnostic_canvas(self.m_image)
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
        calls = (', '.join(call['address'] for call in self.m_last_calls)
                 if self.m_last_calls else 'none')
        self.m_status.setText(
            '%s | phase %d | elapsed %.5f s | updates %d | %s | '
            'external calls: %s' %
            (state, snapshot['phase'], snapshot['elapsed_seconds'],
             snapshot['updates'],
             self.m_asset_error or 'original title image decoded', calls))
        self.m_step.setEnabled(not snapshot['finished'] and
                               not self.m_timer.isActive())
        self.m_play.setEnabled(not snapshot['finished'])
        self.m_play.setText('Pause' if self.m_timer.isActive() else 'Play')
        self.m_destination.setEnabled(self.m_handoff is not None)
        if self.m_handoff is not None:
            self.m_status.setText(
                self.m_status.text() +
                ' | native next: %s (ID 6; factory 0x3F2C00)' %
                self.m_handoff['target']['class_name'])

    def inspect_destination(self):
        if self.m_handoff is not None and self.m_last_result is not None:
            self.handoff_requested.emit(self.m_last_result)

    def advance_native(self, delta_seconds):
        if self.m_runtime.snapshot()['finished']:
            return
        result = self.m_runtime.step(delta_seconds, self.m_busy.isChecked())
        self.m_last_calls = result['calls']
        self.m_last_result = result
        self.m_handoff = title_handoff_request(result)
        if result['finished']:
            self.pause_playback()
        self.redraw()
        if result['finished'] and self.m_handoff is not None:
            self.native_transition_completed.emit(result)

    def step(self):
        if not self.m_timer.isActive():
            self.advance_native(self.m_delta.value())

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
        self.m_runtime = c_title_runtime()
        self.m_last_calls = []
        self.m_last_result = None
        self.m_handoff = None
        self.redraw()

    def hideEvent(self, event):
        self.pause_playback()
        self.redraw()
        super().hideEvent(event)

    def closeEvent(self, event):
        self.pause_playback()
        super().closeEvent(event)
