"""ELF-verified copyright composition and PCSX2-observed prompt variant.

The Font/5-24-2 FFON glyph coverage and GS sampler/alpha remain to be
compared at runtime. Native arguments and source rectangles are fixed facts.
"""
import math
import struct

from arika_press_start_runtime import verify_press_start_elf
from arika_app_registry import _word

COPYRIGHT_TEXT_TABLE = 0x004F9454
COPYRIGHT_TEXT_POINTERS = (0x004C9820, 0x004C9850)
COPYRIGHT_LINES = (
    '1989 BIRD STUDIO/SHUEISHA, TOEI ANIMATION',
    '2006 NAMCO BANDAI GAMES',
)
COPYRIGHT_TEXT_CALLER = 0x003F7AA0
COPYRIGHT_TEXT_LOOKUP = 0x002D1F10
COPYRIGHT_TEXT_DRAW = 0x002CDCA0
COPYRIGHT_FONT_SCALE = struct.unpack('<f', struct.pack('<I', 0x3F2B851F))[0]
COPYRIGHT_SHADOW_RGB = 0.25
COPYRIGHT_TEXT_RGB = 1.0

COPYRIGHT_SYMBOL_SOURCE = (15, 97, 17, 17)
COPYRIGHT_SYMBOL_X = 68.0
COPYRIGHT_SYMBOL_Y = (383.0, 400.0)
COPYRIGHT_SYMBOL_DRAW_HELPER = 0x003F8510

# Controller-state case 1 in 0x3F7E10, matching the three-part source
# widths of the visible PCSX2 "PRESS START button" capture. The exact
# relationship between controller service state and this case is not proven.
PRESS_START_CAPTURE_VARIANT = 1
PRESS_START_CAPTURE_PROMPT_Y = 344.0
PRESS_START_CAPTURE_PROMPT_X = 116.0
PRESS_START_CAPTURE_PROMPT_SOURCES = (
    (0, 357, 99, 30),
    (204, 357, 74, 30),
    (99, 357, 105, 30),
)
PRESS_START_PROMPT_GAP = 2.0

# Key original opcode sites, checked only with the exact EU-beta ELF.
PRESS_START_COPYRIGHT_WORDS = {
    0x002D1F1C: 0x2782A0E4,
    0x002D1F24: 0x03E00008,
    0x003F7B90: 0x0C0B031C,
    0x003F7B98: 0x3C023E80,
    0x003F7BB0: 0x3C023F80,
    0x003F7BE0: 0x3C034190,
    0x003F7BEC: 0x3C0243BF,
    0x003F7C08: 0x0C0B47C4,
    0x003F7C18: 0x3C023F2B,
    0x003F7C30: 0x0C0B3728,
    0x003F7C3C: 0x3C0243C8,
    0x003F7C4C: 0x0C0B47C4,
    0x003F7C74: 0x0C0B3728,
    0x003F7C7C: 0x26730001,
    0x003F7C88: 0x1440FFD2,
    0x003F7CC8: 0xE7B40070,
    0x003F7CCC: 0x0C0FE144,
    0x003F7D04: 0x0C0FE144,
    0x003F8510: 0x27BDFFE0,
}


# Case-dispatch and three atlas quads selected for controller case 1.
# The bounds at 0x3F7F50/54, 0x3F7FA0/A8 and 0x3F8010/18 are literal
# native MIPS source corners; 0x42E80000 is destination x=116.0f.
PRESS_START_PROMPT_CASE_WORDS = {
    0x003F7E20: 0x0C0FDF50,
    0x003F7E44: 0x24030001,
    0x003F7E48: 0x10430038,
    0x003F7F30: 0x3C0342E8,
    0x003F7F44: 0xAE030010,
    0x003F7F50: 0x24060165,
    0x003F7F54: 0x24070063,
    0x003F7FA0: 0x240500CC,
    0x003F7FA4: 0x24060165,
    0x003F7FA8: 0x2407004A,
    0x003F8010: 0x24050063,
    0x003F8014: 0x24060165,
    0x003F8018: 0x24070069,
}


def _f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def native_copyright_draws(alpha=1.0):
    """Return original ordered text/shadow and copyright symbol operations.

    Alpha is a caller-supplied observation of 0x2C0C70's return value.
    No fade timing is invented and text geometry is not screenshot-calibrated.
    """
    if type(alpha) not in (float, int) or not math.isfinite(alpha):
        raise ValueError('observed native fade alpha must be finite')
    if not (0.0 <= alpha <= 1.0):
        raise ValueError('observed native fade alpha must be in [0,1]')
    alpha = _f32(alpha)
    operations = []
    for index in (0, 2):
        tint = COPYRIGHT_SHADOW_RGB if index == 0 else COPYRIGHT_TEXT_RGB
        x = _f32(_f32(88.0) - float(index))
        for y, content in zip(COPYRIGHT_SYMBOL_Y, COPYRIGHT_LINES):
            operations.append(dict(
                kind='text', text=content, x=x, y=_f32(y-float(index)),
                scale=COPYRIGHT_FONT_SCALE, rgb=tint, alpha=alpha,
            ))
    for y in COPYRIGHT_SYMBOL_Y:
        operations.append(dict(
            kind='sprite', source_rect=COPYRIGHT_SYMBOL_SOURCE,
            dest_rect=(COPYRIGHT_SYMBOL_X, _f32(y-alpha),
                       COPYRIGHT_SYMBOL_SOURCE[2], COPYRIGHT_SYMBOL_SOURCE[3]),
            alpha=alpha,
        ))
    return tuple(operations)


def native_prompt_case_one():
    """Build exact case-one source/destination rectangles in draw order."""
    x = PRESS_START_CAPTURE_PROMPT_X
    result = []
    for source in PRESS_START_CAPTURE_PROMPT_SOURCES:
        result.append((source, (x, PRESS_START_CAPTURE_PROMPT_Y,
                                float(source[2]), float(source[3]))))
        x = _f32(x + float(source[2]) + PRESS_START_PROMPT_GAP)
    return tuple(result)


def verify_press_start_copyright_elf(elf):
    verify_press_start_elf(elf)
    for address, expected in {
            **PRESS_START_COPYRIGHT_WORDS,
            **PRESS_START_PROMPT_CASE_WORDS}.items():
        if _word(elf, address) != expected:
            raise ValueError('Press Start text/prompt instruction mismatch at 0x%08X' %
                             address)
    for index, (pointer, content) in enumerate(zip(
            COPYRIGHT_TEXT_POINTERS, COPYRIGHT_LINES)):
        actual = _word(elf, COPYRIGHT_TEXT_TABLE + index * 4)
        if actual != pointer:
            raise ValueError('Press Start copyright text pointer mismatch')
        raw = content.encode('ascii') + b'\0'
        offset = pointer - 0xFFF80
        if elf[offset:offset + len(raw)] != raw:
            raise ValueError('Press Start original copyright text mismatch')
    return {
        'table': hex(COPYRIGHT_TEXT_TABLE),
        'pointers': [hex(p) for p in COPYRIGHT_TEXT_POINTERS],
        'strings': COPYRIGHT_LINES,
        'text_scale': COPYRIGHT_FONT_SCALE,
        'draws': native_copyright_draws(),
        'capture_variant': native_prompt_case_one(),
    }
