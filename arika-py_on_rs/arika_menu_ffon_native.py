"""SDBZ EU-beta native main-menu FFON advances and synthetic raster helper.

The original engine measures glyph *cells*, not trimmed bitmap bounds.
Instruction path: 0x37C1C0 -> 0x2CDCA0 -> font vtable +0x20
(0x199EE0); the font width path is +0x1C (0x19A030), with ASCII
half-width. The installed 0x63BE80 object has width/height 24.

The source glyph alpha and final GS blending are not yet proven pixel
identical. Rasterization below is an isolated host preview, not an
emulation of the GS or of the complete native font command pipeline.
"""
import math
import struct

from PIL import Image

from arika_ffon import decode_glyph, _char_to_glyph_id


FONT_OBJECT_VTABLE = 0x004E3390
NATIVE_FONT_CELL_WIDTH = 24
NATIVE_FONT_CELL_HEIGHT = 24
NATIVE_ASCII_ADVANCE = 12
NATIVE_MENU_FONT_SCALE = 0.75


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def _validate_help_line(text):
    if not isinstance(text, str):
        raise ValueError('native help line must be a string')
    # Original main-menu records only use plain printable ASCII.
    # The 0x19A1B0 iterator has special '$'/newline/multibyte handling;
    # leave these paths unimplemented rather than inventing their output.
    if any(ord(c) < 0x20 or ord(c) > 0x7e or c == '$' for c in text):
        raise ValueError('only native main-menu plain ASCII is supported')


def native_help_glyph_origins(text, scale=NATIVE_MENU_FONT_SCALE):
    """Horizontal offsets relative to a native 0x37C1C0 text origin.

    Calls in 0x19A1B0 use the per-glyph width vtable +0x1C.
    0x19A030 returns 0.5 * the 24-unit cell for codes < 256.
    0x199DC0 uses the same half-cell width for spaces. All current
    main-menu lines are plain ASCII, so the advance is 12 * scale.
    Every ADD.S/MUL.S result rounds to binary32 like the native EE.
    """
    _validate_help_line(text)
    try:
        scale = f32(scale)
    except (TypeError, ValueError, OverflowError, struct.error) as exc:
        raise ValueError('finite positive font scale required') from exc
    if not math.isfinite(scale) or scale <= 0.0:
        raise ValueError('finite positive font scale required')
    advance = f32(float(NATIVE_ASCII_ADVANCE) * scale)
    x = 0.0
    origins = []
    for _ in text:
        origins.append(x)
        x = f32(x + advance)
    return tuple(origins), x


def render_native_help_line(font, font_data, text,
                            clip_ascii_to_half_cell=False):
    """Host preview with native fixed-cell ASCII advances (source size).

    Return an RGBA bitmap in **unscaled source units**. The caller draws
    the entire run at the single native scale 0.75, not each glyph resized
    independently. Spaces take 12 units without drawing a glyph.

    With clip_ascii_to_half_cell=True, each ASCII source glyph is
    limited to the half-width 12-pixel native quad before compositing.
    This prevents the unused right half of a 24px FFON record from
    overlapping the next character; it does not alter native advances.
    The default keeps existing main-menu previews unchanged.

    Bitmap-to-quad UVs and GS alpha remain a presentation approximation;
    no horizontal bbox-trim/kerning or authored 3px spacing is performed.
    """
    _validate_help_line(text)
    if type(clip_ascii_to_half_cell) is not bool:
        raise ValueError('native half-cell clipping flag must be boolean')
    if font.width != NATIVE_FONT_CELL_WIDTH or font.height != NATIVE_FONT_CELL_HEIGHT:
        raise ValueError('expected EU-beta 24x24 native menu font')
    cell_width = NATIVE_ASCII_ADVANCE
    image = Image.new('RGBA', (max(1, len(text) * cell_width),
                               NATIVE_FONT_CELL_HEIGHT), (0, 0, 0, 0))
    for index, ch in enumerate(text):
        if ch == ' ':
            continue
        glyph_id = _char_to_glyph_id(font, ch)
        if glyph_id == 0:
            continue
        source = decode_glyph(font_data, font.glyph_offset(glyph_id - 1),
                              font.width, font.height, font.row_stride)
        # 0x19A030 establishes half-width ASCII advances (12 of 24).
        # The original native per-glyph quad is half-width as well.
        # Keep optional clipping separate from unverified sampler/GS alpha.
        if clip_ascii_to_half_cell:
            source = source.crop((0, 0, cell_width, font.height))
        image.alpha_composite(source, (index * cell_width, 0))
    return image
