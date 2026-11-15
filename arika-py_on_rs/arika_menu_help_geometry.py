"""SDBZ main-menu help preview geometry and 4:3 screenshot coordinates.

The help panel belongs to atlas 4 and glyphs come from the user's FFON
file. The rectangles below are the existing Qt preview measurements,
NOT a recovered native help-panel draw callback. Keep provenance honest:
the main menu's 0x379E60 draw path does not draw this external UI panel.

The native sprite viewport uses 512x448 logical units, while the
captured/interlaced 4:3 image is displayed with *non-square pixels*.
Comparison must scale X and Y independently. Never try to 'fix' a help
frame by uniformly scaling a 4:3 capture to 512x448.
"""
LOGICAL_WIDTH = 512
LOGICAL_HEIGHT = 448

# Provisional screenshot-calibrated editor rectangles, not ELF values.
HELP_PANEL_RECT = (30.0, 272.0, 450.0, 175.0)
HELP_TEXT_CLIP = (76.0, 312.0, 359.0, 116.0)
HELP_TEXT_ORIGIN = (87.0, 324.0)
HELP_LINE_ADVANCE = 25.0
HELP_TEXT_MAX_WIDTH = 303.0


def screenshot_to_logical(point, image_size):
    """Map an uncropped screenshot to 512x448 with independent axes."""
    width, height = image_size
    if (not isinstance(width, (int, float)) or
            not isinstance(height, (int, float)) or
            width <= 0 or height <= 0):
        raise ValueError('positive screenshot dimensions required')
    x, y = point
    return (x * LOGICAL_WIDTH / width, y * LOGICAL_HEIGHT / height)


def logical_to_screenshot(point, image_size):
    width, height = image_size
    if (not isinstance(width, (int, float)) or
            not isinstance(height, (int, float)) or
            width <= 0 or height <= 0):
        raise ValueError('positive screenshot dimensions required')
    x, y = point
    return (x * width / LOGICAL_WIDTH, y * height / LOGICAL_HEIGHT)


def help_text_row_rect(index, width, height, scale=1.0):
    """Place one decoded FFON line; the width is *not* stretched to 303."""
    if not isinstance(index, int) or not 0 <= index < 4:
        raise ValueError('help panel contains at most four text lines')
    if width <= 0 or height <= 0 or scale <= 0:
        raise ValueError('positive FFON glyph bitmap size/scale required')
    return (HELP_TEXT_ORIGIN[0],
            HELP_TEXT_ORIGIN[1] + index * HELP_LINE_ADVANCE,
            width * scale, height * scale)
