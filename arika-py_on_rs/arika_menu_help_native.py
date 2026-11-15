"""ELF-derived relative layout for the SDBZ EU-beta main-menu help owner.

This models the actual text-record mapping, panel sprite bounds and
float32 FFON line placement. It deliberately does not choose an absolute
component position: that owner state has not yet been recovered.

Source: SLES_541.61, see research/NATIVE_MENU_HELP_DRAW.md.
"""
import math
import struct


# (text ID, address of native record, number of description lines).
# The selection-to-ID table is at 0x004A9FA0. In particular TRAINING
# precedes VERSUS in the text records, not in selection order.
NATIVE_HELP_RECORDS = (
    (0x11C, 0x004FC180, 4),  # ORIGINAL
    (0x11D, 0x004FC194, 4),  # Z SURVIVOR
    (0x11F, 0x004FC1BC, 3),  # VERSUS
    (0x120, 0x004FC1CC, 4),  # DRAGON SUMMONING
    (0x11E, 0x004FC1A8, 4),  # TRAINING
    (0x121, 0x004FC1E0, 4),  # CUSTOMIZE
    (0x122, 0x004FC1F4, 3),  # OPTIONS
)

# 0x37BEB0 sprite setup, and 0x37C1C0 FFON loop.
HELP_FRAME_TEXTURE_INDEX = 4
HELP_FRAME_SOURCE_BOUNDS = (0, 0, 464, 176)
HELP_FRAME_DEPTH = 97.0
# State 2 in 0x37C160 writes these native component coordinates.
HELP_SETTLED_COMPONENT_ORIGIN = (24.0, 272.0)
HELP_TEXT_OFFSET = (64.0, 52.0)
HELP_TEXT_SCALE = 0.75
HELP_LINE_ADVANCE = 25.0


def _f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def help_record(selection):
    """Return (native text ID, record address, line count)."""
    if not isinstance(selection, int) or isinstance(selection, bool):
        raise ValueError('selection must be a main-menu item index')
    if selection < 0 or selection >= len(NATIVE_HELP_RECORDS):
        raise ValueError('selection must be a main-menu item index')
    return NATIVE_HELP_RECORDS[selection]


def native_help_layout(selection, component_x, component_y):
    """Describe the native help draw relative to its *actual* component XY.

    The EE uses ADD.S for each coordinate and *repeated* ADD.S on Y per
    line. Rounding each step to binary32 prevents 64-bit Python float
    arithmetic from silently changing the recovered loop semantics.
    No diagnostic-timeline frame, animation age, or screenshot origin
    participates in these coordinates.
    """
    text_id, record_address, line_count = help_record(selection)
    try:
        x = _f32(component_x)
        y = _f32(component_y)
    except (TypeError, ValueError, OverflowError, struct.error) as exc:
        raise ValueError('finite component coordinates required') from exc
    if not math.isfinite(x) or not math.isfinite(y):
        raise ValueError('finite component coordinates required')

    text_x = _f32(x + HELP_TEXT_OFFSET[0])
    text_y = _f32(y + HELP_TEXT_OFFSET[1])
    text_origins = []
    for _ in range(line_count):
        text_origins.append((text_x, text_y))
        text_y = _f32(text_y + HELP_LINE_ADVANCE)

    return {
        'text_id': text_id,
        'record_address': record_address,
        'line_count': line_count,
        'panel_texture': HELP_FRAME_TEXTURE_INDEX,
        'panel_rect': (
            x, y, HELP_FRAME_SOURCE_BOUNDS[2], HELP_FRAME_SOURCE_BOUNDS[3]),
        'panel_depth': HELP_FRAME_DEPTH,
        'font_scale': HELP_TEXT_SCALE,
        'line_origins': tuple(text_origins),
    }
