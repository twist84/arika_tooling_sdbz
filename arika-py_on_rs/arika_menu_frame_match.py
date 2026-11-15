"""Rank recovered menu animation poses against a user's 4:3 screenshot.

This is a *visual comparison* of diagnostic preview frames, NOT recovered
runtime animation timing. No screenshot or game art is stored by the tool.
"""
from PIL import Image, ImageChops, ImageFilter, ImageStat

REFERENCE_SIZE = (256, 192)
# Central character region in a 4:3 presentation, excluding the help frame,
# moving cloud strip, banner, and most changing labels.
CELL_REGION = (75, 6, 227, 146)


def normalize_reference(image):
    """Crop-free: require a game-only 4:3 screenshot."""
    if image.width < 64 or image.height < 48:
        raise ValueError('reference screenshot is too small')
    ratio = image.width / image.height
    if abs(ratio - 4.0 / 3.0) > 0.025:
        raise ValueError('crop screenshot to the 4:3 game image first')
    return image.convert('RGB').resize(REFERENCE_SIZE, Image.Resampling.BILINEAR)


def pose_score(reference, candidate, region=CELL_REGION):
    """Lower is better; compare colors and structure in a fixed screen area."""
    if reference.size != REFERENCE_SIZE or candidate.size != REFERENCE_SIZE:
        raise ValueError('images must be normalized to 256x192')
    if not (0 <= region[0] < region[2] <= 256 and
            0 <= region[1] < region[3] <= 192):
        raise ValueError('invalid comparison region')
    ref = reference.convert('RGB').crop(region)
    cur = candidate.convert('RGB').crop(region)
    # Color fidelity and edge alignment help tolerate different capture
    # filters without letting anti-aliasing dominate the result.
    color = sum(ImageStat.Stat(ImageChops.difference(ref, cur)).mean) / 3
    ref_edges = ref.convert('L').filter(ImageFilter.FIND_EDGES)
    cur_edges = cur.convert('L').filter(ImageFilter.FIND_EDGES)
    edge = ImageStat.Stat(ImageChops.difference(ref_edges, cur_edges)).mean[0]
    return color * 0.35 + edge * 0.65


def rank_samples(reference, candidates, top_n=5):
    """Candidates: iterable of (sample_index, normalized_pillow_image)."""
    if top_n < 1:
        raise ValueError('top_n must be positive')
    ranked = [(pose_score(reference, image), int(index))
              for index, image in candidates]
    return sorted(ranked, key=lambda entry: (entry[0], entry[1]))[:top_n]
