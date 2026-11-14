"""Native Super Dragon Ball Z stage background presets, recovered from the EE ELFs.

The values come from CStage00..CStage12 virtual method slot 29 (zero-based).
The returned RGBA vectors are per-stage static data, not texture-edge samples.
All four regional executables (EU, EU beta, JP, US) agree on the RGB bytes.
The game selects the runtime stage class/state; .stg files alone are ambiguous
for s01a, s02a, and s05a.
"""
import re
from pathlib import PurePosixPath


# 13 native classes; 16 RGBA vectors in all, including identical CStage04 states.
STAGE_CLASS_RGB = {
    'CStage00': ((31, 31, 31),),
    'CStage01': ((30, 164, 212),),
    'CStage02': ((31, 159, 234),),
    'CStage03': ((235, 221, 255), (0, 215, 218)),
    'CStage04': ((196, 89, 243), (196, 89, 243)),
    'CStage05': ((90, 164, 54), (31, 71, 40)),
    'CStage06': ((35, 176, 230),),
    'CStage07': ((125, 167, 217),),
    'CStage08': ((20, 4, 29),),
    'CStage09': ((19, 32, 94),),
    'CStage10': ((31, 31, 31),),
    'CStage11': ((30, 164, 212),),
    'CStage12': ((235, 132, 235),),
}

# Two native stage classes reuse each of the s01a/s02a asset sets.
STAGE_ASSET_CLASSES = {
    's00': ('CStage00',),
    's01': ('CStage01', 'CStage08'),
    's02': ('CStage02', 'CStage09'),
    's03': ('CStage03',),
    's04': ('CStage04',),
    's05': ('CStage05',),
    's06': ('CStage06',),
    's07': ('CStage07',),
    's10': ('CStage10',),
    's11': ('CStage11',),
    's12': ('CStage12',),
}


def _stage_asset(path):
    if path is None:
        return None
    filename = PurePosixPath(str(path).replace('\\', '/')).stem.lower()
    match = re.fullmatch(r'(s\d{2})([a-z])', filename)
    return match.groups() if match else None


def stage_background_choices(path):
    """Return native presets applicable to a stage asset (including alternates)."""
    asset = _stage_asset(path)
    if not asset:
        return ()
    stage, suffix = asset
    classes = STAGE_ASSET_CLASSES.get(stage, ())
    result = []
    for class_name in classes:
        for state, rgb in enumerate(STAGE_CLASS_RGB[class_name]):
            key = '%s:%d' % (class_name, state)
            label = '%s — state %d — #%02X%02X%02X' % ((class_name, state) + rgb)
            result.append(dict(key=key, label=label, rgb=rgb))
    return tuple(result)


def default_stage_background(path):
    """Select the normal class/state for this asset.

    s03b/s04b start in state 1; s05a defaults to state 0. Alternate runtime
    classes/states remain selectable in the editor because asset names cannot
    identify them uniquely.
    """
    asset = _stage_asset(path)
    if not asset:
        return None
    stage, suffix = asset
    classes = STAGE_ASSET_CLASSES.get(stage, ())
    if not classes:
        return None
    state = 1 if stage in ('s03', 's04') and suffix == 'b' else 0
    key = '%s:%d' % (classes[0], state)
    return key if any(item['key'] == key for item in stage_background_choices(path)) else None


def stage_background_rgba(key):
    """Convert the game's normalized RGB bytes into the picker's sRGB format."""
    if not isinstance(key, str):
        return None
    class_name, sep, state = key.partition(':')
    variants = STAGE_CLASS_RGB.get(class_name)
    if not sep or not state.isdigit() or variants is None:
        return None
    index = int(state)
    if index >= len(variants):
        return None
    return tuple(value / 255.0 for value in variants[index]) + (1.0,)
