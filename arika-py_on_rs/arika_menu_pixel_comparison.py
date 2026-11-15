"""Resolution-matched screenshot differences, independent of proprietary assets.

Pixel errors are descriptive, not proof of GS correctness. Candidate frames
are resized to the reference screenshot's output resolution; there is no
geometric realignment, color correction, or automatic error minimization.
"""
import math

from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps, ImageStat


RESAMPLE_MODES = {
    'nearest': Image.Resampling.NEAREST,
    'bilinear': Image.Resampling.BILINEAR,
    'bicubic': Image.Resampling.BICUBIC,
    'lanczos': Image.Resampling.LANCZOS,
}


def _stat(diff, mask=None):
    stats = ImageStat.Stat(diff, mask=mask)
    return {
        'mean_absolute_error': round(sum(stats.mean) / 3.0, 3),
        'root_mean_square_error': round(math.sqrt(
            sum(component * component for component in stats.rms) / 3.0), 3),
        'channel_mean_absolute_error': [round(v, 3) for v in stats.mean],
    }


def compare_screenshot_pixels(reference, candidate, resampling='bilinear',
                              edge_threshold=20):
    """Return descriptive pixel-error stats and a raw RGB difference image.

    The full-frame 4:3 geometry is validated by the caller. An edge pixel
    is one whose local 3x3 reference luminance range >= edge_threshold.
    Edge/flat masks distinguish sampling-sensitive boundaries from broad
    fill regions; no PS2 GS texture or filtering state is inferred.
    """
    if resampling not in RESAMPLE_MODES:
        raise ValueError('unsupported output resampling mode')
    if type(edge_threshold) is not int or not 1 <= edge_threshold <= 255:
        raise ValueError('edge threshold must be an integer in 1..255')
    source = reference.convert('RGB')
    target = candidate.convert('RGB')
    if target.size != source.size:
        target = target.resize(source.size, RESAMPLE_MODES[resampling])
    diff = ImageChops.difference(source, target)
    gray = source.convert('L')
    local_range = ImageChops.subtract(gray.filter(ImageFilter.MaxFilter(3)),
                                      gray.filter(ImageFilter.MinFilter(3)))
    edges = local_range.point(lambda value: 255 if value >= edge_threshold else 0)
    flat = ImageOps.invert(edges)
    edge_count = edges.histogram()[255]
    total = source.width * source.height
    return {
        'reference_output_size': list(source.size),
        'candidate_source_size': list(candidate.size),
        'candidate_resize_filter': resampling,
        'registration': 'none',
        'edge_threshold_luma_3x3': edge_threshold,
        'edge_pixels_percent': round(100.0 * edge_count / total, 3),
        'all_pixels': _stat(diff),
        'reference_edges': _stat(diff, mask=edges) if edge_count else None,
        'reference_flat': _stat(diff, mask=flat) if edge_count < total else None,
        'warning': ('Different output scaling and temporal poses cause error; '
                    'edge and flat metrics are descriptive, not GS parity.'),
    }, diff


def difference_preview(diff):
    """Return a 3x-contrast heatmap; never use it for numerical stats."""
    return ImageEnhance.Contrast(diff.convert('RGB')).enhance(3.0)
