"""EU-beta original-asset startup logo diagnostic, also embedded in Arika Editor.

Run with extracted loose native asset keys, or supply INFO.DAT/GAME.DAT.
The ELF establishes three resource names, a 512x447 texture rectangle
and 512x448 target rectangle. Qt composition is a DIAGNOSTIC
approximation, not measured GS alpha/filter/pixel parity.

    python arika_logo_preview.py --assets-root extracted
    python arika_logo_preview.py --info INFO.DAT --game GAME.DAT
"""
import argparse
from pathlib import Path
import sys
import tempfile

from PySide6 import QtCore as C, QtGui as G, QtWidgets as W

from arika_logo_resources import (
    LOGO_RESOURCE_NAMES, LOGO_SOURCE_RECT, LOGO_DEST_RECT,
    logo_asset_paths, recover_logo_resources,
)
from arika_logo_runtime import c_logo_runtime


def decode_logo_texture(raw):
    """Decode one *unambiguous* FPIX/XPIX/TIM2 or TIM2 asset.

    The ELF names the resource but does not tell us a FPIX chunk index.
    Multi-picture containers therefore fail instead of guessing which
    atlas the runtime resolved. Actual PS2 sampler state is not emulated.
    """
    from arika_dat import container, tim2_rgba

    if not isinstance(raw, bytes):
        raise TypeError('logo asset must be bytes')
    if raw.startswith(b'FPIX'):
        description = container(raw)
        chunks = description['chunks']
        if len(chunks) != 1 or chunks[0]['magic'] != 'XPIX':
            raise ValueError('logo FPIX requires a single unambiguous XPIX chunk')
        part = chunks[0]
        body = raw[part['offset']:part['offset'] + part['size']]
        if body[32:36] != b'TIM2':
            raise ValueError('logo XPIX has no supported TIM2 payload')
        tim2 = body[32:]
    elif raw.startswith(b'TIM2'):
        tim2 = raw
    else:
        raise ValueError('unsupported logo resource; expected FPIX or TIM2')

    width, height, pixels = tim2_rgba(tim2)
    if (width < LOGO_SOURCE_RECT[2] or
            height < LOGO_SOURCE_RECT[3]):
        raise ValueError('logo asset does not cover native source rectangle')
    return G.QImage(pixels, width, height, width * 4,
                    G.QImage.Format.Format_RGBA8888).copy()


def render_logo_image(texture):
    """Render the ELF-derived rectangles (not a cycle/fade compositor)."""
    if not isinstance(texture, G.QImage) or texture.isNull():
        raise ValueError('a decoded original logo texture is required')
    if texture.width() < LOGO_SOURCE_RECT[2] or texture.height() < LOGO_SOURCE_RECT[3]:
        raise ValueError('texture cannot cover ELF source rectangle')
    target = G.QImage(LOGO_DEST_RECT[2], LOGO_DEST_RECT[3],
                      G.QImage.Format.Format_ARGB32_Premultiplied)
    target.fill(G.QColor(0, 0, 0))
    painter = G.QPainter(target)
    try:
        # Actual filtering must be measured; no game-specific sampler
        # policy is inferred from the screenshot or initial attachment.
        painter.setRenderHint(G.QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawImage(
            C.QRectF(*LOGO_DEST_RECT), texture, C.QRectF(*LOGO_SOURCE_RECT))
    finally:
        painter.end()
    return target


def load_logo_images(root):
    """Require exact native keys; do not invent filenames or PNG fallbacks."""
    images = []
    errors = []
    for name, path in zip(LOGO_RESOURCE_NAMES, logo_asset_paths(root)):
        try:
            images.append(decode_logo_texture(path.read_bytes()))
            errors.append(None)
        except (OSError, TypeError, ValueError) as error:
            images.append(None)
            errors.append('%s: %s' % (name, error))
    return images, errors

def load_logo_archive_images(virtual_files):
    """Decode only the three ELF resource keys from the editor's open archive.

    The game loader names extensionless resources; archive entries may have
    the .pix storage suffix. Never select an unrelated basename, guess a
    FPIX chunk, or reuse an image from a previously opened archive.
    """
    if not hasattr(virtual_files, 'items'):
        raise TypeError('expected the editor virtual file mapping')

    indexed = {}
    native_keys = set(LOGO_RESOURCE_NAMES)
    valid_keys = native_keys | {name + '.pix' for name in native_keys}
    for original_name, data in virtual_files.items():
        if not isinstance(original_name, str):
            continue
        key = original_name.replace('\\', '/').lstrip('/').lower()
        if key in valid_keys:
            indexed.setdefault(key, []).append((original_name, data))

    images = []
    errors = []
    for name in LOGO_RESOURCE_NAMES:
        matches = indexed.get(name, []) + indexed.get(name + '.pix', [])
        if len(matches) != 1:
            images.append(None)
            errors.append(
                '%s: %s' % (name,
                           'not found in opened archive' if not matches else
                           'ambiguous duplicate resource paths'))
            continue
        try:
            images.append(decode_logo_texture(matches[0][1]))
            errors.append(None)
        except (ValueError, TypeError) as error:
            images.append(None)
            errors.append('%s: %s' % (name, error))
    return images, errors


class c_logo_preview(W.QWidget):
    """Embeddable boot-logo viewer; no authored startup timings or art."""
    def __init__(self, images=None, errors=None, parent=None):
        super().__init__(parent)
        if images is None:
            images = [None] * 3
        if errors is None:
            errors = ['Open an INFO.DAT / GAME.DAT archive in Arika Editor'] * 3
        if len(images) != 3 or len(errors) != 3:
            raise ValueError('expected three logo image slots')
        self.m_images = tuple(images)
        self.m_errors = tuple(errors)
        self.m_runtime = c_logo_runtime()
        # Qt schedules UI updates; the runtime receives measured monotonic
        # elapsed seconds, not a fabricated native fixed-frame delta.
        self.m_timer = C.QTimer(self)
        self.m_timer.setTimerType(C.Qt.TimerType.PreciseTimer)
        self.m_timer.setInterval(16)
        self.m_timer.timeout.connect(self.advance_playback)
        self.m_elapsed = C.QElapsedTimer()
        self.m_last_elapsed_ns = 0
        self.setWindowTitle('Super Dragon Ball Z (EU beta) — native logo preview')
        self.m_canvas = W.QLabel()
        self.m_canvas.setMinimumSize(220, 165)
        self.m_canvas.setSizePolicy(W.QSizePolicy.Policy.Ignored,
                                    W.QSizePolicy.Policy.Ignored)
        self.m_canvas.setAlignment(C.Qt.AlignmentFlag.AlignCenter)
        self.m_canvas.setStyleSheet('background-color: black; color: white;')
        self.m_canvas.installEventFilter(self)
        self.m_status = W.QLabel()
        self.m_status.setWordWrap(True)
        self.m_delta = W.QDoubleSpinBox()
        self.m_delta.setRange(0, 60)
        self.m_delta.setDecimals(6)
        self.m_delta.setSingleStep(1 / 60)
        self.m_delta.setValue(0)
        self.m_delta.setSuffix(' seconds')
        self.m_busy = W.QCheckBox('0x2C0C20 busy (observed input)')
        self.m_skip = W.QCheckBox('Controller +0x22 bit 0x10 (one update)')
        self.m_step = W.QPushButton('Step one native update')
        self.m_play = W.QPushButton('Play')
        self.m_play.setToolTip(
            'Automatically step with elapsed real time (diagnostic playback, '
            'not measured PS2 update timing). Pause preserves the native state.')
        self.m_reset = W.QPushButton('Reset')
        self.m_step.clicked.connect(self.step)
        self.m_play.clicked.connect(self.toggle_play)
        self.m_reset.clicked.connect(self.reset)

        clock_controls = W.QHBoxLayout()
        clock_controls.addWidget(W.QLabel('Observed delta'))
        clock_controls.addWidget(self.m_delta)
        clock_controls.addWidget(self.m_busy)
        clock_controls.addStretch()
        input_controls = W.QHBoxLayout()
        input_controls.addWidget(self.m_skip)
        input_controls.addWidget(self.m_step)
        input_controls.addWidget(self.m_play)
        input_controls.addWidget(self.m_reset)
        input_controls.addStretch()
        layout = W.QVBoxLayout(self)
        layout.addWidget(self.m_canvas, 1)
        layout.addLayout(clock_controls)
        layout.addLayout(input_controls)
        layout.addWidget(self.m_status)
        self.redraw()

    def eventFilter(self, watched, event):
        if watched is self.m_canvas and event.type() == C.QEvent.Type.Resize:
            self.draw_canvas()
        return super().eventFilter(watched, event)

    def load_archive_assets(self, virtual_files):
        """Swap in-memory logo assets on archive open and reset the sequence."""
        self.pause_playback()
        images, errors = load_logo_archive_images(virtual_files)
        self.m_images = tuple(images)
        self.m_errors = tuple(errors)
        self.m_runtime = c_logo_runtime()
        self.m_skip.setChecked(False)
        self.m_busy.setChecked(False)
        self.redraw()
        return sum(image is not None for image in self.m_images)

    def draw_canvas(self):
        snap = self.m_runtime.snapshot()
        original = self.m_images[snap['current_logo']]
        if original is not None:
            img = render_logo_image(original)
            display_size = C.QSize(640, 480).scaled(
                self.m_canvas.size(), C.Qt.AspectRatioMode.KeepAspectRatio)
            pixmap = G.QPixmap.fromImage(img).scaled(
                display_size, C.Qt.AspectRatioMode.IgnoreAspectRatio,
                C.Qt.TransformationMode.SmoothTransformation)
            self.m_canvas.setPixmap(pixmap)
        else:
            self.m_canvas.clear()
            self.m_canvas.setText('Original native logo asset unavailable')

    def redraw(self):
        snap = self.m_runtime.snapshot()
        index = snap['current_logo']
        self.draw_canvas()
        warning = self.m_errors[index] or 'Original resource decoded'
        self.m_status.setText(
            'Logo %d: %s | phase %d | age %.6f | updates %d | %s. '
            'Playback: %s. 4:3 QPainter diagnostic only; '
            'no native GS fades or filter parity.'
            % (index, LOGO_RESOURCE_NAMES[index], snap['phase'],
               snap['age_seconds'], snap['updates'], warning,
               'running' if self.m_timer.isActive() else
               'complete' if snap['finished'] else 'paused'))
        self.m_step.setEnabled(not snap['finished'] and
                               not self.m_timer.isActive())
        self.m_play.setEnabled(not snap['finished'])
        self.m_play.setText('Pause' if self.m_timer.isActive() else 'Play')

    def advance_native(self, delta_seconds):
        """One update, shared by manual stepping and automatic playback."""
        if self.m_runtime.snapshot()['finished']:
            return
        sample = self.m_runtime.step(
            delta_seconds, self.m_busy.isChecked(),
            0x10 if self.m_skip.isChecked() else 0)
        self.m_skip.setChecked(False)
        if sample['finished']:
            self.pause_playback()
        self.redraw()
        if sample['calls']:
            addresses = ', '.join(call['address'] for call in sample['calls'])
            self.m_status.setText(self.m_status.text() + ' | calls: ' + addresses)

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
        """Deliver elapsed monotonic time, accounting for timer jitter."""
        if not self.m_timer.isActive():
            return
        now_ns = self.m_elapsed.nsecsElapsed()
        elapsed_ns = max(0, now_ns - self.m_last_elapsed_ns)
        self.m_last_elapsed_ns = now_ns
        self.advance_native(elapsed_ns / 1000000000.0)

    def pause_playback(self):
        self.m_timer.stop()
        self.m_last_elapsed_ns = 0
        self.m_play.setText('Play')
        self.m_step.setEnabled(not self.m_runtime.snapshot()['finished'])

    def reset(self):
        self.pause_playback()
        self.m_runtime = c_logo_runtime()
        self.m_skip.setChecked(False)
        self.redraw()

    def hideEvent(self, event):
        # Switching away from the editor's startup tab should not advance
        # a hidden game-screen simulation.
        self.pause_playback()
        super().hideEvent(event)

    def closeEvent(self, event):
        self.pause_playback()
        super().closeEvent(event)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    location = parser.add_mutually_exclusive_group(required=True)
    location.add_argument('--assets-root', type=Path)
    location.add_argument('--info', type=Path, help='INFO.DAT; pass --game too')
    parser.add_argument('--game', type=Path)
    parser.add_argument('--elf', type=Path, help='verify exact EU-beta executable')
    args = parser.parse_args()
    if args.game is not None and args.info is None:
        parser.error('--game requires --info')
    try:
        if args.elf is not None:
            recover_logo_resources(args.elf.read_bytes())
        with tempfile.TemporaryDirectory(prefix='sdbz_logo_') as temporary:
            root = args.assets_root or Path(temporary)
            if args.info is not None:
                from arika_archive_paths import resolve_archive_paths
                from arika_dat import Archive
                info, game = resolve_archive_paths(args.info, args.game)
                Archive(info, game).extract(root, patterns=LOGO_RESOURCE_NAMES)
            app = W.QApplication.instance() or W.QApplication(sys.argv[:1])
            images, errors = load_logo_images(root)
            window = c_logo_preview(images, errors)
            window.show()
            return app.exec()
    except (OSError, TypeError, ValueError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    sys.exit(main())
