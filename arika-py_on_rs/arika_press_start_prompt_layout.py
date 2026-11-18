"""EU-beta Press Start prompt sprite layouts from 0x003F7E10.

These are *render cases* 0..4, not gamepad numbers. The selector is returned
by 0x003F7D40 and depends on controller-service calls; the editor must not
claim a chosen case corresponds to an observed controller configuration.
"""
import struct

from arika_press_start_runtime import verify_press_start_elf
from arika_app_registry import _word


# Every source rectangle is a difference of the four literal native corner
# arguments supplied to sprite virtual slot +0x14. No guessed atlas glyphs.
# (case, initial logical X, source rectangles in native submission order).
PRESS_START_PROMPT_CASES = {
    0: (154.0, ((0, 357, 99, 30), (99, 357, 105, 30))),
    1: (116.0, ((0, 357, 99, 30), (204, 357, 74, 30),
                 (99, 357, 105, 30))),
    2: (88.0, ((278, 357, 92, 30), (0, 387, 39, 30),
                (80, 387, 90, 30), (170, 387, 110, 30))),
    3: (86.0, ((278, 357, 92, 30), (39, 387, 41, 30),
                (80, 387, 90, 30), (170, 387, 110, 30))),
    4: (118.0, ((278, 357, 92, 30), (80, 387, 90, 30),
                 (170, 387, 110, 30))),
}
PRESS_START_PROMPT_Y = 344.0
PRESS_START_PROMPT_SPACING = 2.0
PRESS_START_PROMPT_DISPATCH = 0x003F7E10
PRESS_START_PROMPT_SELECTOR = 0x003F7D40
PRESS_START_PROMPT_CASE_ENTRY = {
    0: 0x003F7E60, 1: 0x003F7F2C, 2: 0x003F8068,
    3: 0x003F8214, 4: 0x003F83C0,
}

# Dispatch/first-draw and subsequent source-corner immediates, selected
# from each case's distinct original machine-code sequence.
PRESS_START_PROMPT_LAYOUT_WORDS = {
    0x003F7D48: 0x0C0ABEDC,  # service 0x2AFB70
    0x003F7D60: 0x0C0ABEE0,  # service 0x2AFB80
    0x003F7D70: 0x0C0ABEB4,  # eligibility service 0x2AFAD0
    0x003F7D88: 0x0C0ABEB4,
    0x003F7D94: 0x0C0ABEB4,
    0x003F7D9C: 0x1200000C,  # branch on first eligibility
    0x003F7DA4: 0x16000003,  # branch to second-case decision
    0x003F7DB4: 0x24030002,
    0x003F7DB8: 0x1000000E,
    0x003F7DC0: 0x0C0ABF20,  # fallback service 0x2AFC80
    0x003F7DD8: 0x0C0ABF20,
    0x003F7DE4: 0x0C0ABF20,
    0x003F7E2C: 0x10430164,  # case 4
    0x003F7E34: 0x104300F7,  # case 3
    0x003F7E40: 0x10430089,  # case 2
    0x003F7E48: 0x10430038,  # case 1
    0x003F7E50: 0x10400003,  # case 0
    0x003F7E64: 0x3C03431A,  # case 0 x = 154.0f
    0x003F7E84: 0x24060165,  # case 0 first upper Y=357
    0x003F7E88: 0x24070063,  # case 0 first right=99
    0x003F7ED4: 0x24050063,  # case 0 second left=99
    0x003F7ED8: 0x24060165,  # case 0 second upper Y=357
    0x003F7EDC: 0x24070069,  # case 0 second right delta? actually 105
    0x003F7F30: 0x3C0342E8,  # case 1 x = 116.0f
    0x003F7F50: 0x24060165,
    0x003F7FA0: 0x240500CC,
    0x003F7FA8: 0x2407004A,
    0x003F8010: 0x24050063,
    0x003F8018: 0x24070069,
    0x003F806C: 0x3C0342B0,  # case 2 x = 88.0f
    0x003F8088: 0x24050116,  # 278
    0x003F8090: 0x2407005C,  # 92
    0x003F80E0: 0x24060183,  # y 387
    0x003F80E4: 0x24070027,  # 39
    0x003F814C: 0x24050050,  # 80
    0x003F8154: 0x2407005A,  # 90
    0x003F81BC: 0x240500AA,  # 170
    0x003F81C4: 0x2407006E,  # 110
    0x003F8218: 0x3C0342AC,  # case 3 x = 86.0f
    0x003F8234: 0x24050116,
    0x003F823C: 0x2407005C,
    0x003F8288: 0x24050027,  # 39
    0x003F8290: 0x24070029,  # 41
    0x003F82F8: 0x24050050,
    0x003F8300: 0x2407005A,
    0x003F8368: 0x240500AA,
    0x003F8370: 0x2407006E,
    0x003F83C4: 0x3C0342EC,  # case 4 x = 118.0f
    0x003F83E0: 0x24050116,
    0x003F83E8: 0x2407005C,
    0x003F8434: 0x24050050,
    0x003F843C: 0x2407005A,
    0x003F84A4: 0x240500AA,
    0x003F84AC: 0x2407006E,
}


def native_prompt_layout(case):
    """Native ordered (source, destination) quads for a dispatch case.

    This is a diagnostic selector, not an inference about connected pads.
    """
    if type(case) is not int or case not in PRESS_START_PROMPT_CASES:
        raise ValueError('expected native prompt case in [0,4]')
    x, sources = PRESS_START_PROMPT_CASES[case]
    result = []
    for source in sources:
        result.append((
            source, (x, PRESS_START_PROMPT_Y, float(source[2]),
                     float(source[3]))))
        x = struct.unpack('<f', struct.pack('<f',
                            x + float(source[2]) +
                            PRESS_START_PROMPT_SPACING))[0]
    return tuple(result)



def native_prompt_case_from_service_results(
        b70, b80, eligibility0=False, eligibility1=False,
        fallback0=False, fallback1=False):
    """Reproduce the decision tree in 0x003F7D40 from observed helper results.

    Arguments are *return values* from the original native helpers, not
    inferred controller counts or Qt checkbox settings. In particular,
    fallback values represent 0x2AFC80(0/1). Only values reachable along
    the selected original branch affect the result.
    """
    for value in (b70, b80, eligibility0, eligibility1,
                  fallback0, fallback1):
        if type(value) is not bool:
            raise ValueError('native service observations must be boolean')
    if b70:
        return 4
    if not b80:
        if eligibility0:
            return 4
        return int(fallback0)
    if eligibility0:
        return 4 if eligibility1 else 2
    if eligibility1:
        return 3
    return int(fallback0 or fallback1)


def verify_press_start_prompt_layout_elf(elf):
    verify_press_start_elf(elf)
    for address, expected in PRESS_START_PROMPT_LAYOUT_WORDS.items():
        if _word(elf, address) != expected:
            raise ValueError(
                'Press Start prompt dispatch mismatch at 0x%08X' % address)
    return {
        'selector': hex(PRESS_START_PROMPT_SELECTOR),
        'dispatch': hex(PRESS_START_PROMPT_DISPATCH),
        'cases': {
            case: {'entry': hex(PRESS_START_PROMPT_CASE_ENTRY[case]),
                   'quads': native_prompt_layout(case)}
            for case in PRESS_START_PROMPT_CASES
        },
        'known_limitation': (
            'Native selector depends on controller service state not '
            'observed by the editor; case choice is diagnostic'),
        'verified_words': len(PRESS_START_PROMPT_LAYOUT_WORDS),
    }
