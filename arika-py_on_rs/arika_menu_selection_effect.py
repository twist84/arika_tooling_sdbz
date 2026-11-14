"""Selection-triggered preview of the recovered ELF emphasis displacement curves.

The curves themselves are recovered, but the event trigger used here is an
editor convenience, not a verified native selection transition schedule.
"""
EMPHASIS_START_TICK = 80
EMPHASIS_DURATION = 15


def emphasis_geometry(current, baseline, emphasized):
    """Add the recovered vertex/position delta to the live preview geometry."""
    if not current or not baseline or not emphasized:
        return current
    result = dict(current)
    for name in ('position', 'bounds'):
        src = current.get(name)
        base = baseline.get(name)
        effect = emphasized.get(name)
        if (isinstance(src, list) and isinstance(base, list) and
                isinstance(effect, list) and len(src) == len(base) == len(effect)):
            result[name] = [v + (e - b) for v, b, e in zip(src, base, effect)]
    src = current.get('vertices')
    base = baseline.get('vertices')
    effect = emphasized.get('vertices')
    if (isinstance(src, list) and isinstance(base, list) and
            isinstance(effect, list) and len(src) == len(base) == len(effect)):
        result['vertices'] = [
            [v + (e - b) for v, b, e in zip(point, before, after)]
            for point, before, after in zip(src, base, effect)
        ]
    return result


def emphasis_sample(frames, age):
    """Find the baked relative-age sample, independent of global playback time."""
    if age is None or age < 0 or age >= EMPHASIS_DURATION:
        return None
    tick = EMPHASIS_START_TICK + int(age)
    if tick >= len(frames):
        return None
    frame = frames[tick]
    if frame.get('tick') != tick:
        return None
    return frame
