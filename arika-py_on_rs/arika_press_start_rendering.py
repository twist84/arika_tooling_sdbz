"""Asset-backed, deliberately bounded Press Start renderer for the editor.

Only the first two statically positioned native sprites are composited.
The third sprite, FFON text and prompt animation remain evidence-gated.
This Qt approximation does not emulate GS blending or filtering.
"""
from PySide6 import QtCore as C, QtGui as G

from arika_dat import container, tim2_rgba
from arika_press_start_resources import (
    PRESS_START_RESOURCE_KEYS, PRESS_START_BACKGROUND_KEY,
    PRESS_START_FOREGROUND_KEY, PRESS_START_CANVAS_SIZE,
    PRESS_START_BACKGROUND_RECT, PRESS_START_BACKGROUND_RGBA,
    PRESS_START_FOREGROUND_SOURCE_RECT, PRESS_START_FOREGROUND_DEST_RECT,
)


def decode_press_start_texture(payload):
    """Decode a uniquely selected TIM2 picture without guessing FPIX indices."""
    if type(payload) is not bytes:
        raise TypeError('expected original archive resource bytes')
    if payload.startswith(b'FPIX'):
        parts = container(payload)['chunks']
        if len(parts) != 1 or parts[0]['magic'] != 'XPIX':
            raise ValueError('FPIX needs one unambiguous XPIX picture')
        part = parts[0]
        chunk = payload[part['offset']:part['offset'] + part['size']]
        if len(chunk) < 36 or chunk[32:36] != b'TIM2':
            raise ValueError('XPIX missing a supported TIM2 payload')
        texture = chunk[32:]
    elif payload.startswith(b'TIM2'):
        texture = payload
    else:
        raise ValueError('unsupported original resource format')
    width, height, pixels = tim2_rgba(texture)
    return G.QImage(pixels, width, height, width * 4,
                    G.QImage.Format.Format_RGBA8888).copy()


def load_press_start_archive_images(virtual_files):
    """Strictly match three ELF resource paths; reject missing and duplicates."""
    if not hasattr(virtual_files, 'items'):
        raise TypeError('expected editor virtual archive mapping')
    matches = {key: [] for key in PRESS_START_RESOURCE_KEYS}
    for name, data in virtual_files.items():
        if not isinstance(name, str):
            continue
        normalized = name.replace('\\', '/').lstrip('/').lower()
        for key in PRESS_START_RESOURCE_KEYS:
            if normalized in (key, key + '.pix'):
                matches[key].append((name, data))
    images = []
    errors = []
    minimum_sizes = {
        PRESS_START_BACKGROUND_KEY: (
            PRESS_START_BACKGROUND_RECT[2], PRESS_START_BACKGROUND_RECT[3]),
        PRESS_START_FOREGROUND_KEY: (
            PRESS_START_FOREGROUND_SOURCE_RECT[2],
            PRESS_START_FOREGROUND_SOURCE_RECT[3]),
    }
    for key in PRESS_START_RESOURCE_KEYS:
        found = matches[key]
        if len(found) != 1:
            images.append(None)
            errors.append(key + ': ' +
                          ('not found in opened archive' if not found else
                           'ambiguous duplicate resource paths'))
            continue
        try:
            image = decode_press_start_texture(found[0][1])
            min_width, min_height = minimum_sizes.get(key, (1, 1))
            if image.width() < min_width or image.height() < min_height:
                raise ValueError('texture smaller than native sprite source')
            images.append(image)
            errors.append(None)
        except (TypeError, ValueError, IndexError) as error:
            images.append(None)
            errors.append(key + ': ' + str(error))
    return images, errors


def render_press_start_image(images):
    """Compose only ELF-proven background and foreground sprite rectangles.

    The 0.6f background tint is preserved as painter opacity over black.
    This is a diagnostic approximation of GS colour/alpha behaviour, not
    a claim of parity. Native dynamic third-sprite/font/prompt draws are
    intentionally omitted rather than synthesised.
    """
    if len(images) != len(PRESS_START_RESOURCE_KEYS):
        raise ValueError('expected exactly three resource image slots')
    if all(image is None for image in images[:2]):
        return None
    for image in images:
        if image is not None and (not isinstance(image, G.QImage) or
                                  image.isNull()):
            raise ValueError('invalid original texture image')
    canvas = G.QImage(*PRESS_START_CANVAS_SIZE,
                      G.QImage.Format.Format_ARGB32_Premultiplied)
    canvas.fill(G.QColor(0, 0, 0))
    painter = G.QPainter(canvas)
    try:
        # Filtering remains unknown; avoid asserting a GS sampler value.
        painter.setRenderHint(G.QPainter.RenderHint.SmoothPixmapTransform, False)
        if images[1] is not None:
            painter.setOpacity(PRESS_START_BACKGROUND_RGBA[0])
            painter.drawImage(C.QRectF(*PRESS_START_BACKGROUND_RECT),
                              images[1], C.QRectF(*PRESS_START_BACKGROUND_RECT))
        painter.setOpacity(1.0)
        if images[0] is not None:
            painter.drawImage(C.QRectF(*PRESS_START_FOREGROUND_DEST_RECT),
                              images[0],
                              C.QRectF(*PRESS_START_FOREGROUND_SOURCE_RECT))
    finally:
        painter.end()
    return canvas


def press_start_comparison_image(reconstructed, reference):
    """Side-by-side display only, never use the capture as a render layer."""
    if (reconstructed is None or reconstructed.isNull() or
            reference is None or reference.isNull()):
        raise ValueError('both native rendering and reference are required')
    size = C.QSize(640, 480)
    canvas = G.QImage(1280, 480, G.QImage.Format.Format_ARGB32_Premultiplied)
    canvas.fill(G.QColor(0, 0, 0))
    painter = G.QPainter(canvas)
    try:
        painter.drawImage(C.QRect(0, 0, size.width(), size.height()),
                          reconstructed)
        painter.drawImage(C.QRect(640, 0, size.width(), size.height()),
                          reference)
    finally:
        painter.end()
    return canvas
