"""EU-beta GS register writes at 0x103F20 (TEST/ZBUF) and 0x104210 (ALPHA).

The PS2 GS register addresses and bit layouts are public hardware definitions.
The conversion tables and bit operations are recovered from the EU-beta ELF.

This module reconstructs outgoing GIF A+D register writes. It does not
recover the game's active framebuffer/zbuffer allocations, the live sprite
render state, or every intervening draw, and does not emulate the GS.
No executable bytes or proprietary textures are bundled.
"""
import hashlib
import struct

ELF_SHA256 = '80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0'

GS_ALPHA_1 = 0x42
GS_ALPHA_2 = 0x43
GS_TEST_1 = 0x47
GS_TEST_2 = 0x48
GS_ZBUF_1 = 0x4e
GS_ZBUF_2 = 0x4f
GS_GIF_REG_AD = 0x0e

# Native jump tables at 0x4B4B90 and 0x4B4BB0.
NATIVE_ZTST = (0, 1, 1, 1, 1, 1, 3, 2)
NATIVE_ATST = (0, 1, 4, 7, 2, 3, 5, 6)

# 0x104210 selects mode a6 and indexes [a4 * 30 + a5 * 5].
# The five bytes select GS ALPHA A, B, C, D, FIX.
ALPHA_TABLE_ADDRESS = (0x439290, 0x439350, 0x439410)
ELF_FILE_SEGMENT_BIAS = 0xfff80  # ELF PT_LOAD vaddr 0x100000, file offset 0x80.


def _u32(value):
    return value & 0xffffffff


def _contexts(mode):
    if mode == 0:
        return (0,)
    if mode == 1:
        return (1,)
    if mode == 2:
        return (0, 1)
    raise ValueError('ELF emitter context mode must be 0, 1, or 2')


def make_gs_test(z_test, z_write, alpha_compare, alpha_reference):
    """0x103F20: exact GS TEST register from four raw engine arguments.

    a4 selects ZTST, a5 sets ZMSK=0 only when exactly 1, a6 selects
    ATST, and a7 supplies byte AREF. Context a8 selects register targets.
    """
    if not isinstance(z_test, int) or not 0 <= z_test < 8:
        raise ValueError('unverified native Z-test selector')
    if not isinstance(z_write, int):
        raise TypeError('native Z-mask selector must be an integer')
    if not isinstance(alpha_compare, int) or not 0 <= alpha_compare < 8:
        raise ValueError('unverified native alpha-test selector')
    if not isinstance(alpha_reference, int) or not 0 <= alpha_reference <= 0xff:
        raise ValueError('native alpha reference must be a byte')
    reference = (0x80 if alpha_reference == 0xff else
                 max(1, alpha_reference >> 1) if alpha_reference else 0)
    return (1 | (NATIVE_ATST[alpha_compare] << 1) |
            (reference << 4) | (1 << 16) | (NATIVE_ZTST[z_test] << 17))


def make_gs_zbuf(z_write, raw_zbp_word, raw_psm_word):
    """0x103F20 using captured BSS words 0x4FF3BC (ZBP), 0x4FF3B0 (PSM).

    These raw words are runtime globals, not available in the ELF file.
    Never substitute an arbitrary ZBP/PSM as a purported game default.
    """
    for value in (raw_zbp_word, raw_psm_word):
        if not isinstance(value, int) or not 0 <= value <= 0xffffffff:
            raise ValueError('raw GS initialization word must be u32')
    return (((raw_zbp_word >> 5) |
             (_u32(raw_psm_word) << 24) |
             ((int(z_write != 1)) << 32)) & 0xffffffffffffffff)


def depth_register_writes(z_test, z_write, alpha_compare,
                          alpha_reference, context_mode=2,
                          raw_zbp_word=None, raw_psm_word=None):
    """GS A+D pairs in native submit order; uncaptured ZBUF stays None."""
    contexts = _contexts(context_mode)
    test = make_gs_test(z_test, z_write, alpha_compare, alpha_reference)
    if (raw_zbp_word is None) != (raw_psm_word is None):
        raise ValueError('ZBP and PSM BSS words must be supplied together')
    zbuf = (None if raw_zbp_word is None else
            make_gs_zbuf(z_write, raw_zbp_word, raw_psm_word))
    return [
        (address, value)
        for index in contexts
        for address, value in ((GS_ZBUF_1 + index, zbuf),
                               (GS_TEST_1 + index, test))
    ]


def extract_alpha_preset(elf_data, preset_a, preset_b, native_mode):
    """Read 0x104210's five-byte recipe from the user's exact EU-beta ELF.

    Native tables have six known 30-byte rows; each row has six entries.
    A first-byte sentinel 0xff makes the native emitter skip the write.
    """
    if not isinstance(elf_data, bytes) or hashlib.sha256(elf_data).hexdigest() != ELF_SHA256:
        raise ValueError('expected the exact EU-beta ELF (SHA256 mismatch)')
    if not all(isinstance(value, int) for value in
               (preset_a, preset_b, native_mode)):
        raise TypeError('preset indices must be integers')
    if native_mode not in (0, 1, 2):
        raise ValueError('native ALPHA table mode must be 0,1,2')
    if not 0 <= preset_a <= 5 or not 0 <= preset_b <= 5:
        raise ValueError('ALPHA table index exceeds verified bounds')
    offset = (ALPHA_TABLE_ADDRESS[native_mode] - ELF_FILE_SEGMENT_BIAS +
              30 * preset_a + 5 * preset_b)
    result = elf_data[offset:offset+5]
    if len(result) != 5:
        raise ValueError('native ALPHA table truncated')
    return tuple(result)


def make_gs_alpha(recipe):
    """Pack native five-byte A/B/C/D/FIX recipe as 64-bit GS ALPHA."""
    if (not isinstance(recipe, (tuple, list)) or len(recipe) != 5 or
            any(not isinstance(v, int) or not 0 <= v <= 255 for v in recipe)):
        raise ValueError('five raw u8 ALPHA recipe values required')
    a, b, c, d, fix = recipe
    if a == 0xff:
        return None
    if any(v > 3 for v in (a, b, c, d)):
        raise ValueError('native ALPHA recipe contains unexpected selection')
    return a | (b << 2) | (c << 4) | (d << 6) | (fix << 32)


def alpha_register_writes(recipe, context_mode=2):
    alpha = make_gs_alpha(recipe)
    if alpha is None:
        return []
    return [(GS_ALPHA_1 + index, alpha) for index in _contexts(context_mode)]


def decode_gs_test(raw):
    if not isinstance(raw, int) or raw < 0 or raw > 0xffffffffffffffff:
        raise ValueError('GS TEST value must be u64')
    return dict(ate=raw & 1, atst=(raw >> 1) & 7,
                aref=(raw >> 4) & 0xff, afail=(raw >> 12) & 3,
                date=(raw >> 14) & 1, datm=(raw >> 15) & 1,
                zte=(raw >> 16) & 1, ztst=(raw >> 17) & 3)


def decode_gs_alpha(raw):
    if not isinstance(raw, int) or raw < 0 or raw > 0xffffffffffffffff:
        raise ValueError('GS ALPHA value must be u64')
    return dict(a=raw & 3, b=(raw >> 2) & 3,
                c=(raw >> 4) & 3, d=(raw >> 6) & 3,
                fix=(raw >> 32) & 0xff)


def make_gif_ad_dma(register_writes):
    """Serialize the native DMA/GIF packed A+D subset from these emitters."""
    if not isinstance(register_writes, (tuple, list)) or not 1 <= len(register_writes) <= 4:
        raise ValueError('this native packet emitter supports 1..4 registers')
    for address, value in register_writes:
        if (not isinstance(address, int) or not 0 <= address <= 0x7f or
                not isinstance(value, int) or not 0 <= value <= 0xffffffffffffffff):
            raise ValueError('all register addresses and values must be observed integers')
    n = len(register_writes)
    header = struct.pack('<QII', 0xf0000000 | (n + 1),
                         0x13000000, 0x50000000 | (n + 1))
    tag = struct.pack('<QQ', (1 << 60) | (1 << 15) | n, GS_GIF_REG_AD)
    values = b''.join(struct.pack('<QQ', value, address)
                      for address, value in register_writes)
    return header + tag + values


def decode_gif_ad_dma(data):
    """Strict decoder for the 0x103F20/0x104210 A+D DMA/GIF packet subset."""
    if not isinstance(data, bytes) or len(data) < 48 or len(data) % 16 != 0:
        raise ValueError('expected a complete native A+D packet')
    dma, dma_high0, dma_high1, tag, desc = struct.unpack_from('<QIIQQ', data)
    n = tag & 0x7fff
    if (n not in (1, 2, 4) or len(data) != (n + 2) * 16 or
            tag != ((1 << 60) | (1 << 15) | n) or
            desc != GS_GIF_REG_AD or
            dma != (0xf0000000 | (n + 1)) or
            dma_high0 != 0x13000000 or dma_high1 != (0x50000000 | (n + 1))):
        raise ValueError('unsupported native A+D GIF packet header')
    return [(struct.unpack_from('<Q', data, 32 + i*16 + 8)[0],
             struct.unpack_from('<Q', data, 32 + i*16)[0])
            for i in range(n)]


def main():
    """Inspect register writes using the exact user-owned EU-beta ELF."""
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', type=Path, required=True)
    parser.add_argument('--alpha-mode', type=int, default=0)
    parser.add_argument('--alpha-a', type=int, default=2)
    parser.add_argument('--alpha-b', type=int, default=3)
    parser.add_argument('--z-test', type=int, default=7)
    parser.add_argument('--z-write', type=int, default=1)
    parser.add_argument('--alpha-compare', type=int, default=3)
    parser.add_argument('--alpha-reference', type=int, default=0)
    parser.add_argument('--context-mode', type=int, default=2)
    parser.add_argument('--raw-zbp-word', type=lambda v: int(v, 0))
    parser.add_argument('--raw-psm-word', type=lambda v: int(v, 0))
    args = parser.parse_args()
    try:
        preset = extract_alpha_preset(
            args.elf.read_bytes(), args.alpha_a, args.alpha_b,
            args.alpha_mode)
        alpha_writes = alpha_register_writes(preset, args.context_mode)
        depth_writes = depth_register_writes(
            args.z_test, args.z_write, args.alpha_compare,
            args.alpha_reference, args.context_mode,
            args.raw_zbp_word, args.raw_psm_word)
    except (OSError, ValueError, TypeError) as error:
        parser.error(str(error))

    print(json.dumps(dict(
        alpha_recipe=preset,
        alpha_value=make_gs_alpha(preset),
        alpha_writes=alpha_writes,
        test_fields=decode_gs_test(
            make_gs_test(args.z_test, args.z_write,
                         args.alpha_compare, args.alpha_reference)),
        depth_writes=depth_writes,
        limitations=[
            'Selector defaults shown are inferred from renderer startup',
            'The live PS2 graphics context is not captured',
            'Missing raw ZBP/PSM BSS words remain null',
            'Qt drawing remains a software depth approximation',
        ]), indent=2))


if __name__ == '__main__':
    main()
