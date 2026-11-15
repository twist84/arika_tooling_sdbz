#!/usr/bin/env python3
"""Compare PCSX2 and Qt menu screenshots in recovered 512x448 coordinates.

Only geometry and broad image differences are measured. Screenshots must
show the same menu item and pose with full-frame 4:3 presentation.
Requires Pillow but no game data or copyrighted screenshot fixtures.

    python compare_menu_captures.py pcsx2.png python.png
"""
import argparse
import json
import math
from pathlib import Path

from PIL import Image

from arika_menu_pixel_comparison import (
    RESAMPLE_MODES, compare_screenshot_pixels, difference_preview,
)

from arika_menu_help_native import (HELP_LINE_ADVANCE,
                                    HELP_SETTLED_COMPONENT_ORIGIN,
                                    HELP_TEXT_OFFSET,
                                    HELP_TEXT_SCALE)

LOGICAL_WIDTH = 512
LOGICAL_HEIGHT = 448
EXPECTED_PRESENTATION_ASPECT = 4.0 / 3.0
FONT_SOURCE_HEIGHT = 24
HELP_TEXT_LINES = 4


def validate_capture(image):
    """Both screenshots must contain full, non-letterboxed 4:3 game view."""
    if image.width <= 0 or image.height <= 0:
        raise ValueError('capture has invalid dimensions')
    aspect = image.width / image.height
    if abs(aspect - EXPECTED_PRESENTATION_ASPECT) > 0.015:
        raise ValueError('capture must use a full-frame 4:3 presentation')


def _text_bounds(image, line_index):
    """Measure near-white text inside the ELF-derived line rectangle.

    0x37C1C0 supplies X/Y, 25-unit stride and 0.75 scale. The glyph
    width and filtering are intentionally not inferred from screenshots.
    """
    x0 = HELP_SETTLED_COMPONENT_ORIGIN[0] + HELP_TEXT_OFFSET[0]
    y0 = (HELP_SETTLED_COMPONENT_ORIGIN[1] + HELP_TEXT_OFFSET[1]
          + line_index * HELP_LINE_ADVANCE)
    y1 = y0 + FONT_SOURCE_HEIGHT * HELP_TEXT_SCALE
    x1 = HELP_SETTLED_COMPONENT_ORIGIN[0] + 464

    l = max(0, min(image.width, math.floor(x0 * image.width / LOGICAL_WIDTH)))
    r = max(0, min(image.width, math.ceil(x1 * image.width / LOGICAL_WIDTH)))
    t = max(0, min(image.height, math.floor(y0 * image.height / LOGICAL_HEIGHT)))
    b = max(0, min(image.height, math.ceil(y1 * image.height / LOGICAL_HEIGHT)))
    if r <= l or b <= t:
        return None

    pixels = image.convert('RGB').load()
    xs = []
    ys = []
    for y in range(t, b):
        for x in range(l, r):
            red, green, blue = pixels[x, y]
            # Broad tolerance allows JPEG artifacts but does not assert
            # GS-equivalent coverage or color.
            if min(red, green, blue) >= 195 and (max(red, green, blue)
                                                  - min(red, green, blue)) <= 56:
                xs.append(x)
                ys.append(y)

    if not xs:
        return None
    return {
        'left': round(min(xs) * LOGICAL_WIDTH / image.width, 3),
        'top': round(min(ys) * LOGICAL_HEIGHT / image.height, 3),
        'right': round((max(xs) + 1) * LOGICAL_WIDTH / image.width, 3),
        'bottom': round((max(ys) + 1) * LOGICAL_HEIGHT / image.height, 3),
        'white_pixels': len(xs),
    }


def compare_menu_captures(reference, candidate):
    validate_capture(reference)
    validate_capture(candidate)
    lines = []
    for index in range(HELP_TEXT_LINES):
        ref_bounds = _text_bounds(reference, index)
        candidate_bounds = _text_bounds(candidate, index)
        if ref_bounds is None or candidate_bounds is None:
            lines.append({'line': index + 1, 'reference': ref_bounds,
                          'candidate': candidate_bounds, 'delta': None})
            continue
        delta = {
            field: round(candidate_bounds[field] - ref_bounds[field], 3)
            for field in ('left', 'top', 'right', 'bottom')
        }
        lines.append({'line': index + 1, 'reference': ref_bounds,
                      'candidate': candidate_bounds, 'delta': delta})

    return {
        'reference_size': [reference.width, reference.height],
        'candidate_size': [candidate.width, candidate.height],
        'native_canvas': [LOGICAL_WIDTH, LOGICAL_HEIGHT],
        'measurement': 'near-white text bounds in logical coordinates',
        'help_lines': lines,
        'warning': ('This measures spatial alignment only, not GS UV, '
                    'filtering, text alpha or pixel-exact compositing.'),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference', type=Path, help='original PCSX2 screenshot')
    parser.add_argument('candidate', type=Path, help='Qt editor screenshot')
    parser.add_argument('--json', action='store_true',
                        help='print the full measurement as structured JSON')
    parser.add_argument('--pixel-metrics', action='store_true',
                        help='also compute output-resolution RGB error, edges and flat regions')
    parser.add_argument('--diff-image', type=Path,
                        help='save a contrast-enhanced difference PNG (reference resolution)')
    parser.add_argument('--resample', choices=tuple(RESAMPLE_MODES),
                        default='bilinear',
                        help='resize the Qt capture to PCSX2 output size for pixel comparison')
    args = parser.parse_args()
    with Image.open(args.reference) as original, Image.open(args.candidate) as preview:
        result = compare_menu_captures(original, preview)
        if args.pixel_metrics or args.diff_image is not None:
            metrics, difference = compare_screenshot_pixels(
                original, preview, resampling=args.resample)
            result['pixel_comparison'] = metrics
            if args.diff_image is not None:
                # Numerical metrics use the unenhanced RGB difference.
                # This 3x-contrast visual is only a diagnostic artifact.
                difference_preview(difference).save(str(args.diff_image), 'PNG')
    if args.json:
        print(json.dumps(result, indent=2))
        return
    print(f"Reference {tuple(result['reference_size'])}; "
          f"candidate {tuple(result['candidate_size'])} (native 512x448)")
    for line in result['help_lines']:
        delta = line['delta']
        if delta is None:
            print(f"Help line {line['line']}: unable to isolate white text")
        else:
            print(f"Help line {line['line']}: "
                  f"left {delta['left']:+.2f}, right {delta['right']:+.2f}, "
                  f"top {delta['top']:+.2f}, bottom {delta['bottom']:+.2f}")
    if 'pixel_comparison' in result:
        metrics = result['pixel_comparison']
        print('Pixel comparison (%s resize to %s):' % (
            metrics['candidate_resize_filter'], metrics['reference_output_size']))
        for name, label in (('all_pixels', 'All pixels'),
                            ('reference_edges', 'Reference edges'),
                            ('reference_flat', 'Reference flat areas')):
            value = metrics[name]
            if value is not None:
                print('  %s: MAE %.3f/255, RMSE %.3f/255' % (
                    label, value['mean_absolute_error'],
                    value['root_mean_square_error']))
        print('  Reference edge-mask coverage: %.2f%%' %
              metrics['edge_pixels_percent'])
        print(metrics['warning'])
    print(result['warning'])


if __name__ == '__main__':
    main()
