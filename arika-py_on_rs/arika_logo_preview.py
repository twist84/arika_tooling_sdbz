"""Standalone EU-beta original-asset startup logo diagnostic preview.

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


class c_logo_preview(W.QWidget):
    """Separate boot-logo laboratory, not an extension of main-menu Qt."""
    def __init__(self, images, errors, parent=None):
        super().__init__(parent)
        if len(images) != 3 or len(errors) != 3:
            raise ValueError('expected three logo image slots')
        self.m_images = tuple(images)
        self.m_errors = tuple(errors)
        self.m_runtime = c_logo_runtime()
        self.setWindowTitle('Super Dragon Ball Z (EU beta) — native logo preview')
        self.m_canvas = W.QLabel()
        self.m_canvas.setFixedSize(640, 480)
        self.m_canvas.setAlignment(C.Qt.AlignmentFlag.AlignCenter)
        self.m_canvas.setStyleSheet('background-color: black; color: white;')
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
        self.m_reset = W.QPushButton('Reset')
        self.m_step.clicked.connect(self.step)
        self.m_reset.clicked.connect(self.reset)

        controls = W.QHBoxLayout()
        controls.addWidget(self.m_delta)
        controls.addWidget(self.m_busy)
        controls.addWidget(self.m_skip)
        controls.addWidget(self.m_step)
        controls.addWidget(self.m_reset)
        controls.setContentsMargins(0, 0, 0, 0)
        layout = W.QVBoxLayout(self)
        layout.addWidget(self.m_canvas, alignment=C.Qt.AlignmentFlag.AlignHCenter)
        layout.addLayout(controls)
        layout.addWidget(self.m_status)
        self.redraw()

    def redraw(self):
        snap = self.m_runtime.snapshot()
        index = snap['current_logo']
        original = self.m_images[index]
        if original is not None:
            img = render_logo_image(original)
            pixmap = G.QPixmap.fromImage(img).scaled(
                640, 480, C.Qt.AspectRatioMode.IgnoreAspectRatio,
                C.Qt.TransformationMode.SmoothTransformation)
            self.m_canvas.setPixmap(pixmap)
        else:
            self.m_canvas.clear()
            self.m_canvas.setText('Original native logo asset unavailable')
        warning = self.m_errors[index] or 'Original resource decoded'
        self.m_status.setText(
            'Logo %d: %s | phase %d | age %.6f | updates %d | %s. '
            '4:3 QPainter diagnostic only; no native GS fades or filter parity.'
            % (index, LOGO_RESOURCE_NAMES[index], snap['phase'],
               snap['age_seconds'], snap['updates'], warning))
        self.m_step.setEnabled(not snap['finished'])

    def step(self):
        if self.m_runtime.snapshot()['finished']:
            return
        sample = self.m_runtime.step(
            self.m_delta.value(), self.m_busy.isChecked(),
            0x10 if self.m_skip.isChecked() else 0)
        self.m_skip.setChecked(False)
        self.redraw()
        if sample['calls']:
            addresses = ', '.join(call['address'] for call in sample['calls'])
            self.m_status.setText(self.m_status.text() + ' | calls: ' + addresses)

    def reset(self):
        self.m_runtime = c_logo_runtime()
        self.m_skip.setChecked(False)
        self.redraw()


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
