"""ELF-backed EU-beta Press Start resource and sprite evidence.

No copyrighted assets are embedded here. The exact EU-beta ELF is optional
for local verification and deliberately absent from CI.
"""
from arika_press_start_runtime import verify_press_start_elf
from arika_app_registry import _word


PRESS_START_RESOURCE_KEYS = (
    'dis/d03/d03t0101',
    'dis/d03/d03t0103',
    'dis/d05/d05t0101',
)
PRESS_START_RESOURCE_POINTERS = (
    0x004D7740, 0x004D7760, 0x004D7780,
)
PRESS_START_RESOURCE_HANDLES = (0x10, 0x14, 0x18)
PRESS_START_SPRITE_OFFSETS = (0x40, 0xA0, 0x100)
PRESS_START_CANVAS_SIZE = (512, 448)

# The initialised and drawn sprite at this+0xA0 is the full-frame layer.
PRESS_START_BACKGROUND_KEY = PRESS_START_RESOURCE_KEYS[1]
PRESS_START_BACKGROUND_RECT = (0, 0, 512, 448)
PRESS_START_BACKGROUND_RGBA = (0.6, 0.6, 0.6, 1.0)

# Draw callback 0x3F7B0C..0x3F7B54 supplies this+0x40's placement.
PRESS_START_FOREGROUND_KEY = PRESS_START_RESOURCE_KEYS[0]
PRESS_START_FOREGROUND_SOURCE_RECT = (0, 0, 257, 306)
PRESS_START_FOREGROUND_DEST_RECT = (128, 28, 257, 306)

# Initial source for this+0x100; its subsequent positions are dynamic.
PRESS_START_THIRD_SOURCE_RECT = (15, 97, 17, 17)

# Exact instructions along resource-table writes, sprite attachment and draw.
PRESS_START_RENDER_WORDS = {
    0x003EF71C: 0xAE020010,
    0x003EF724: 0x0C0BEE14,
    0x003EF764: 0xAE020014,
    0x003EF76C: 0x0C0BEE14,
    0x003EF7B0: 0xAE020018,
    0x003EF7B8: 0x0C0BEE14,
    0x003F7488: 0x8C510010,
    0x003F74C8: 0x0C0BF63C,
    0x003F74F8: 0x8C510014,
    0x003F7510: 0xAE0300D0,
    0x003F7514: 0xAE0200DC,
    0x003F7518: 0xAE0300D4,
    0x003F7558: 0x24070200,
    0x003F7564: 0x240801C0,
    0x003F7570: 0x8C510018,
    0x003F75E4: 0x2405000F,
    0x003F75E8: 0x24060061,
    0x003F7AEC: 0x8E1900A0,
    0x003F7B10: 0x26110040,
    0x003F7B14: 0xAE020050,
    0x003F7B24: 0xAE020054,
    0x003F7B30: 0x24070101,
    0x003F7B44: 0x24080132,
}


def recover_press_start_resource_evidence(elf):
    """Verify the exact executable and recover named sprite associations."""
    verify_press_start_elf(elf)
    for address, expected in PRESS_START_RENDER_WORDS.items():
        if _word(elf, address) != expected:
            raise ValueError('Press Start rendering mismatch at 0x%08X' %
                             address)
    for name, address in zip(PRESS_START_RESOURCE_KEYS,
                             PRESS_START_RESOURCE_POINTERS):
        offset = address - 0xFFF80
        expected = name.encode('ascii') + b'\0'
        if elf[offset:offset + len(expected)] != expected:
            raise ValueError('Press Start resource key mismatch at 0x%08X' %
                             address)
    return {
        'resource_bindings': [
            {'sprite_offset': hex(sprite),
             'handle_offset': hex(handle),
             'key_pointer': hex(pointer),
             'resource_key': name}
            for sprite, handle, pointer, name in zip(
                PRESS_START_SPRITE_OFFSETS, PRESS_START_RESOURCE_HANDLES,
                PRESS_START_RESOURCE_POINTERS, PRESS_START_RESOURCE_KEYS)
        ],
        'background': {
            'resource_key': PRESS_START_BACKGROUND_KEY,
            'source_rect': list(PRESS_START_BACKGROUND_RECT),
            'destination_rect': list(PRESS_START_BACKGROUND_RECT),
            'initial_rgba': list(PRESS_START_BACKGROUND_RGBA),
        },
        'foreground': {
            'resource_key': PRESS_START_FOREGROUND_KEY,
            'source_rect': list(PRESS_START_FOREGROUND_SOURCE_RECT),
            'destination_rect': list(PRESS_START_FOREGROUND_DEST_RECT),
        },
        'third_sprite': {
            'resource_key': PRESS_START_RESOURCE_KEYS[2],
            'initial_source_rect': list(PRESS_START_THIRD_SOURCE_RECT),
            'dynamic_draw_helper': '0x3f8510',
        },
        'unverified': [
            'Complete GS alpha blending, texture filtering, and UV sampling',
            'Dynamic third-sprite positions and timing',
            'Original font strings and Press Start prompt rendering/blink',
        ],
        'verified_render_words': len(PRESS_START_RENDER_WORDS),
    }
