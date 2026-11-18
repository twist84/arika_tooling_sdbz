"""Asset-backed, deliberately bounded Press Start renderer for the editor.

Composes verified static and prompt atlas sprites, copyright text and symbols.
This Qt approximation does not emulate GS blending or filtering.
"""
import math

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
    COPYRIGHT_LINES, native_copyright_draws,
)
from arika_press_start_prompt_layout import (
    PRESS_START_PROMPT_CASES, native_prompt_layout,
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
            max([PRESS_START_FOREGROUND_SOURCE_RECT[2]] +
                [rect[0] + rect[2]
                 for _, sources in PRESS_START_PROMPT_CASES.values()
                 for rect in sources]),
            max([PRESS_START_FOREGROUND_SOURCE_RECT[3]] +
                [rect[1] + rect[3]
                 for _, sources in PRESS_START_PROMPT_CASES.values()
                 for rect in sources])),
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
        # The ELF dispatch draws ASCII as 12-source-unit glyph quads.
        # A 24-wide bitmap must not spill into its neighbour's cell.
        bitmap = render_native_help_line(
            font, font_data, line, clip_ascii_to_half_cell=True)
        width, height = bitmap.size
        raw = bitmap.tobytes()
        images.append(G.QImage(raw, width, height, width * 4,
                               G.QImage.Format.Format_RGBA8888).copy())
    return tuple(images)



def tint_press_start_ffon(image, rgb):
    """Apply native FFON RGB as a glyph tint, preserving coverage alpha.

    QPainter.setOpacity scales *alpha*, not source RGB. The native dark
    copyright pass specifies RGB=.25 at full fade alpha; drawing a white
    glyph at opacity .25 would instead produce a pale ghost behind text.
    """
    if not isinstance(image, G.QImage) or image.isNull():
        raise ValueError('expected original FFON glyph raster')
    if type(rgb) not in (int, float) or not 0.0 <= rgb <= 1.0:
        raise ValueError('native FFON tint must be in [0,1]')
    tinted = G.QImage(
        image.size(), G.QImage.Format.Format_ARGB32_Premultiplied)
    tinted.fill(C.Qt.GlobalColor.transparent)
    painter = G.QPainter(tinted)
    try:
        painter.drawImage(C.QPointF(0.0, 0.0), image)
        painter.setCompositionMode(
            G.QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(
            tinted.rect(), G.QColor.fromRgbF(rgb, rgb, rgb, 1.0))
    finally:
        painter.end()
    return tinted



def raster_press_start_copyright_glyph_quads(font, font_data):
    """Decode the original FFON into individual native-width glyph quads.

    The EE string path submits glyphs separately, advancing the pen in
    float32. Resizing a precomposed entire line can blend two adjacent glyph
    cells together and does not preserve each glyph's fractional placement.
    Cache the two original ELF colour passes once per archive load.
    """
    from arika_ffon import decode_glyph, _char_to_glyph_id
    from arika_menu_ffon_native import (
        NATIVE_ASCII_ADVANCE, native_help_glyph_origins,
    )
    from arika_press_start_copyright import COPYRIGHT_FONT_SCALE

    if (font.width, font.height, font.bits_per_pixel) != (24, 24, 4):
        raise ValueError('expected original 24x24 4bpp native font')
    cached = {}
    lines = []
    for text in COPYRIGHT_LINES:
        origins, _ = native_help_glyph_origins(
            text, COPYRIGHT_FONT_SCALE)
        quads = []
        for origin, character in zip(origins, text):
            if character == ' ':
                continue
            glyph_id = _char_to_glyph_id(font, character)
            if glyph_id == 0:
                continue
            if glyph_id not in cached:
                source = decode_glyph(
                    font_data, font.glyph_offset(glyph_id - 1),
                    font.width, font.height, font.row_stride)
                source = source.crop(
                    (0, 0, NATIVE_ASCII_ADVANCE, font.height))
                width, height = source.size
                image = G.QImage(
                    source.tobytes(), width, height, width * 4,
                    G.QImage.Format.Format_RGBA8888).copy()
                cached[glyph_id] = (
                    tint_press_start_ffon(image, 0.25),
                    tint_press_start_ffon(image, 1.0))
            quads.append((origin, *cached[glyph_id]))
        lines.append(tuple(quads))
    return tuple(lines)



# 0x199EE0 applies cvt.w.s separately to glyph width/height and the
# incoming pen x/y before 0x112780. Source-cell advances remain float32.
PRESS_START_FONT_DRAW_QUANTIZATION = {
    0x00199F3C: 0x4600B842,  # scaled ASCII font width (MUL.S)
    0x00199F58: 0x46000824,  # glyph width CVT.W.S
    0x00199F90: 0x4600B842,  # scaled font height (MUL.S)
    0x00199FAC: 0x46000824,  # glyph height CVT.W.S
    0x00199FE0: 0x4600B024,  # incoming x CVT.W.S
    0x00199FF0: 0x4600A824,  # incoming y CVT.W.S
    0x00199FF8: 0x0C0449E0,  # submit glyph via 0x112780
}


def native_press_start_ffon_rect(operation, glyph_origin, glyph):
    """Original per-glyph integer destination, before GS UV/filtering.

    Original code rounds each float32 coordinate/dimension with CVT.W.S.
    EE FPU round-to-nearest is assumed here; nondefault FCR31 modes remain
    a runtime observation item, not a hardcoded screenshot compensation.
    """
    from arika_menu_ffon_native import f32

    if not isinstance(glyph, G.QImage) or glyph.isNull():
        raise ValueError('expected an original FFON glyph image')
    if (type(glyph_origin) not in (int, float)
            or not math.isfinite(glyph_origin)):
        raise ValueError('invalid native FFON glyph origin')
    if (not hasattr(operation, 'get') or
            any(type(operation.get(field)) not in (int, float)
                or not math.isfinite(operation[field])
                for field in ('x', 'y', 'scale')) or
            operation['scale'] <= 0):
        raise ValueError('invalid original FFON draw operation')

    # Round the EE's intermediate ADD.S and MUL.S to single precision,
    # then use integer CVT.W.S rather than Qt's subpixel positioning.
    x = int(round(f32(f32(operation['x']) + f32(glyph_origin))))
    y = int(round(f32(operation['y'])))
    width = int(round(f32(float(glyph.width()) *
                          f32(operation['scale']))))
    height = int(round(f32(float(glyph.height()) *
                           f32(operation['scale']))))
    return C.QRect(x, y, width, height)


def verify_press_start_font_draw_elf(elf):
    """Gate integer-quad assertions against original EU-beta opcodes."""
    from arika_press_start_runtime import verify_press_start_elf
    from arika_app_registry import _word

    verify_press_start_elf(elf)
    for address, expected in PRESS_START_FONT_DRAW_QUANTIZATION.items():
        if _word(elf, address) != expected:
            raise ValueError(
                'Press Start native FFON quad mismatch at 0x%08X' % address)
    return {
        'glyph_draw': '0x199ee0',
        'submit': '0x112780',
        'source_character_advance': 12,
        'quantized_positions_and_dimensions': True,
        'verified_words': len(PRESS_START_FONT_DRAW_QUANTIZATION),
    }


def render_press_start_image(images, copyright_images=None,
                             prompt_visible=False, fade_alpha=1.0,
                             prompt_case=1, copyright_quads=None):
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
    if type(prompt_case) is not int or prompt_case not in PRESS_START_PROMPT_CASES:
        raise ValueError('unsupported native prompt dispatch case')
    if copyright_images is not None:
        if len(copyright_images) != len(COPYRIGHT_LINES) or any(
                not isinstance(image, G.QImage) or image.isNull()
                for image in copyright_images):
            raise ValueError('expected two decoded original FFON strings')
    if copyright_quads is not None:
        if len(copyright_quads) != len(COPYRIGHT_LINES):
            raise ValueError('expected two native FFON glyph quad runs')
        for quads in copyright_quads:
            for quad in quads:
                if (not isinstance(quad, (tuple, list)) or len(quad) != 3
                        or type(quad[0]) not in (int, float)
                        or not math.isfinite(quad[0])
                        or any(not isinstance(image, G.QImage) or
                               image.isNull() for image in quad[1:])):
                    raise ValueError('invalid native FFON glyph quad')
    operations = native_copyright_draws(fade_alpha)
    # Native shadow/text tints are separate from the fade alpha.
    # Tint each glyph mask once per render, not once for each text line.
    text_passes = {}
    if copyright_images is not None:
        for operation in operations:
            if operation['kind'] != 'text':
                continue
            index = COPYRIGHT_LINES.index(operation['text'])
            tint_key = (index, operation['rgb'])
            if tint_key not in text_passes:
                text_passes[tint_key] = tint_press_start_ffon(
                    copyright_images[index], operation['rgb'])
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
                for source, destination in native_prompt_layout(prompt_case):
                    if (images[0].width() >= source[0] + source[2] and
                            images[0].height() >= source[1] + source[3]):
                        painter.drawImage(C.QRectF(*destination), images[0],
                                          C.QRectF(*source))
        # The original FFON submission rasterizes one glyph per PS2 quad.
        # Use separate interpolated sampling for the reduced-size text,
        # keeping the original game sprite atlas sampling unchanged.
        # This is a Qt preview approximation until GS TEX1 is recovered.
        painter.setRenderHint(
            G.QPainter.RenderHint.SmoothPixmapTransform, True)
        for operation in operations:
            if operation['kind'] == 'text' and copyright_quads is not None:
                index = COPYRIGHT_LINES.index(operation['text'])
                painter.setOpacity(operation['alpha'])
                tint_index = 0 if operation['rgb'] == 0.25 else 1
                for origin, shadow, foreground in copyright_quads[index]:
                    image = shadow if tint_index == 0 else foreground
                    painter.drawImage(
                        native_press_start_ffon_rect(
                            operation, origin, image),
                        image, C.QRectF(0, 0, image.width(), image.height()))
            elif operation['kind'] == 'text' and copyright_images is not None:
                index = COPYRIGHT_LINES.index(operation['text'])
                image = text_passes[(index, operation['rgb'])]
                painter.setOpacity(operation['alpha'])
                width = image.width() * operation['scale']
                height = image.height() * operation['scale']
                painter.drawImage(
                    C.QRectF(operation['x'], operation['y'], width, height),
                    image, C.QRectF(0, 0, image.width(), image.height()))
            elif operation['kind'] == 'sprite' and images[2] is not None:
                painter.setRenderHint(
                    G.QPainter.RenderHint.SmoothPixmapTransform, False)
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


def press_start_comparison_metrics(images, hidden_reference,
                                   visible_reference, copyright_images=None,
                                   prompt_case=1, resampling='bilinear',
                                   copyright_quads=None):
    """Measure each available original PCSX2 state against archive layers.

    Each reconstruction uses the SAME original resources with only the
    verified prompt visibility gate changed. No screenshot pixels are
    ever used in reconstruction and no automatic alignment is performed.
    Stats are descriptive, not a claim of GS pixel parity.
    """
    from PIL import Image
    from arika_menu_pixel_comparison import (
        RESAMPLE_MODES, compare_screenshot_pixels,
    )

    def pillow_image(qimage):
        if not isinstance(qimage, G.QImage) or qimage.isNull():
            raise ValueError('expected nonempty QImage reference')
        rgba = qimage.convertToFormat(G.QImage.Format.Format_RGBA8888)
        data = bytes(rgba.bits())
        return Image.frombytes(
            'RGBA', (rgba.width(), rgba.height()), data,
            'raw', 'RGBA', rgba.bytesPerLine(), 1)

    if hidden_reference is None and visible_reference is None:
        raise ValueError('at least one original PCSX2 reference is required')
    results = {}
    for name, show_prompt, reference in (
            ('hidden', False, hidden_reference),
            ('visible', True, visible_reference)):
        if reference is None:
            continue
        candidate = render_press_start_image(
            images, copyright_images=copyright_images,
            prompt_visible=show_prompt, prompt_case=prompt_case,
            copyright_quads=copyright_quads)
        if candidate is None:
            raise ValueError('original game texture layers are required')
        reference_pixels = pillow_image(reference)
        candidate_pixels = pillow_image(candidate)
        metrics, _ = compare_screenshot_pixels(
            reference_pixels, candidate_pixels,
            resampling=resampling)

        # The whole-frame error can conceal locally incorrect FFON glyphs.
        # Measure native copyright geometry separately, without changing
        # registration, sampling, reference or source image.
        native_rect = (60, 375, 480, 416)
        region = (
            round(native_rect[0] * reference_pixels.width / 512),
            round(native_rect[1] * reference_pixels.height / 448),
            round(native_rect[2] * reference_pixels.width / 512),
            round(native_rect[3] * reference_pixels.height / 448),
        )
        if candidate_pixels.size != reference_pixels.size:
            candidate_pixels = candidate_pixels.resize(
                reference_pixels.size, RESAMPLE_MODES[resampling])
        detail, _ = compare_screenshot_pixels(
            reference_pixels.crop(region), candidate_pixels.crop(region),
            resampling=resampling)
        detail['native_rect'] = list(native_rect)
        metrics['copyright_region'] = detail
        results[name] = metrics
    return {
        'prompt_case': prompt_case,
        'reference_states': results,
        'missing_states': [state for state in ('hidden', 'visible')
                           if state not in results],
        'evidence': 'diagnostic only; GS and fade parity not established',
    }
