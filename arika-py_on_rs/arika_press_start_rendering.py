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
    PRESS_START_THIRD_SOURCE_RECT,
)
from arika_press_start_copyright import (
    COPYRIGHT_LINES, native_copyright_draws, native_prompt_case_one,
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
            max(PRESS_START_FOREGROUND_SOURCE_RECT[2], 278),
            max(PRESS_START_FOREGROUND_SOURCE_RECT[3], 387)),
        PRESS_START_RESOURCE_KEYS[2]: (
            PRESS_START_THIRD_SOURCE_RECT[0] + PRESS_START_THIRD_SOURCE_RECT[2],
            PRESS_START_THIRD_SOURCE_RECT[1] + PRESS_START_THIRD_SOURCE_RECT[3]),
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


def load_press_start_archive_font(virtual_files):
    """Reuse original FFON only from the exact game-font archive path."""
    from arika_ffon import parse_ffon

    if not hasattr(virtual_files, 'items'):
        raise TypeError('expected editor virtual archive mapping')
    matches = [(key, data) for key, data in virtual_files.items()
               if isinstance(key, str) and
               key.replace('\\', '/').lstrip('/').lower() ==
               'font/5-24-2.fon']
    if len(matches) != 1:
        return None, None, (
            'font/5-24-2.fon: not found in opened archive'
            if not matches else 'font/5-24-2.fon: ambiguous duplicate font')
    data = matches[0][1]
    try:
        font = parse_ffon(data)
        if (font.width, font.height, font.bits_per_pixel) != (24, 24, 4):
            raise ValueError('expected original 24x24 4bpp native font')
        return font, data, None
    except (TypeError, ValueError) as error:
        return None, None, 'font/5-24-2.fon: ' + str(error)


def raster_press_start_copyright(font, font_data):
    """Raster original ELF strings using the existing native FFON helper."""
    from arika_menu_ffon_native import render_native_help_line

    images = []
    for line in COPYRIGHT_LINES:
        bitmap = render_native_help_line(font, font_data, line)
        width, height = bitmap.size
        raw = bitmap.tobytes()
        images.append(G.QImage(raw, width, height, width * 4,
                               G.QImage.Format.Format_RGBA8888).copy())
    return tuple(images)


def render_press_start_image(images, copyright_images=None,
                             prompt_visible=False, fade_alpha=1.0):
    """Compose original static sprites, proven text/icon calls and prompt case.

    Copyright glyph pixels are rasterised with the existing game FFON helper.
    GS blend/filter/UV parity is not asserted. Prompt case 1 is selected from
    the PCSX2-observed three-part source layout; other controller cases are
    not silently approximated.
    """
    if len(images) != len(PRESS_START_RESOURCE_KEYS):
        raise ValueError('expected exactly three resource image slots')
    if all(image is None for image in images[:2]):
        return None
    for image in images:
        if image is not None and (not isinstance(image, G.QImage) or
                                  image.isNull()):
            raise ValueError('invalid original texture image')
    if type(prompt_visible) is not bool:
        raise ValueError('prompt visibility must be boolean')
    if copyright_images is not None:
        if len(copyright_images) != len(COPYRIGHT_LINES) or any(
                not isinstance(image, G.QImage) or image.isNull()
                for image in copyright_images):
            raise ValueError('expected two decoded original FFON strings')
    operations = native_copyright_draws(fade_alpha)
    canvas = G.QImage(*PRESS_START_CANVAS_SIZE,
                      G.QImage.Format.Format_ARGB32_Premultiplied)
    canvas.fill(G.QColor(0, 0, 0))
    painter = G.QPainter(canvas)
    try:
        # The real GS sampler is still unknown. These are bounded Qt draws.
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
            if prompt_visible:
                for source, destination in native_prompt_case_one():
                    if (images[0].width() >= source[0] + source[2] and
                            images[0].height() >= source[1] + source[3]):
                        painter.drawImage(C.QRectF(*destination), images[0],
                                          C.QRectF(*source))
        for operation in operations:
            if operation['kind'] == 'text' and copyright_images is not None:
                index = COPYRIGHT_LINES.index(operation['text'])
                image = copyright_images[index]
                painter.setOpacity(operation['alpha'] * operation['rgb'])
                width = image.width() * operation['scale']
                height = image.height() * operation['scale']
                painter.drawImage(
                    C.QRectF(operation['x'], operation['y'], width, height),
                    image, C.QRectF(0, 0, image.width(), image.height()))
            elif operation['kind'] == 'sprite' and images[2] is not None:
                sx, sy, sw, sh = operation['source_rect']
                if (images[2].width() >= sx + sw and
                        images[2].height() >= sy + sh):
                    painter.setOpacity(operation['alpha'])
                    painter.drawImage(C.QRectF(*operation['dest_rect']),
                                      images[2], C.QRectF(sx, sy, sw, sh))
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
        painter.drawImage(C.QRectF(0, 0, size.width(), size.height()),
                          reconstructed,
                          C.QRectF(0, 0, reconstructed.width(),
                                   reconstructed.height()))
        painter.drawImage(C.QRectF(640, 0, size.width(), size.height()),
                          reference,
                          C.QRectF(0, 0, reference.width(), reference.height()))
    finally:
        painter.end()
    return canvas
