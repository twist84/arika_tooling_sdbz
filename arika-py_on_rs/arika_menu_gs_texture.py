"""EU-beta SDBZ texture GS register writer 0x10C3E0, context 1.

Input is a captured 48-byte runtime texture record from the 0x4FF8F0
table, NOT TIM2 bytes or assumed menu texture state. The six-register
GIF A+D template is file-backed at 0x439E70.
No executable, proprietary game assets or live GS snapshots are bundled.
"""
import struct

GS_TEXA = 0x3b
GS_TEX1_1 = 0x14
GS_TEX0_1 = 0x06
GS_CLAMP_1 = 0x08
GS_MIPTBP1_1 = 0x34
GS_MIPTBP2_1 = 0x36
GS_TEXTURE_ADDRESSES = (GS_TEXA, GS_TEX1_1, GS_TEX0_1,
                        GS_CLAMP_1, GS_MIPTBP1_1, GS_MIPTBP2_1)
GIF_AD = 0x0e
MASK64 = 0xffffffffffffffff
ELF_DESCRIPTOR_TABLE = 0x4ff8f0
ELF_PACKET_TEMPLATE = 0x439e70


def _s16(record, offset):
    return struct.unpack_from('<h', record, offset)[0]


def _u16(record, offset):
    return struct.unpack_from('<H', record, offset)[0]


def parse_native_texture_record(data):
    """Read only offsets actually accessed by 0x10C3E0/0x10C7C0."""
    if not isinstance(data, bytes) or len(data) != 48:
        raise ValueError('the runtime texture record must contain 48 bytes')
    return dict(
        tbp0=_s16(data, 0x02),
        cbp=_s16(data, 0x04),
        tw=_s16(data, 0x06),
        th=_s16(data, 0x08),
        psm=_u16(data, 0x0e),
        cpsm=_u16(data, 0x10),
        levels=_s16(data, 0x12),
        clut_flag=_s16(data, 0x14),
        width=_s16(data, 0x16),
        height=_s16(data, 0x18),
    )


def _u64(value):
    return value & MASK64


def _mipmap_base(format_value, tbp0, width, height, count):
    """0x10C7C0: add 256-byte-block mip sizes over count halvings.

    R5900 three-operand MULT writes RD. Native 32-bit multiplication
    overflow for invalid/huge dimensions is deliberately unresolved.
    """
    if format_value not in (0, 1, 2, 0x13, 0x14):
        return -1  # Native invalid-format branch at 0x10C808.
    for _ in range(count):
        if width < 0 or height < 0:
            raise ValueError('negative mipmap dimensions unsupported')
        area = width * height
        if format_value in (0, 1):
            byte_count = area * 4
        elif format_value == 2:
            byte_count = area * 2
        elif format_value == 0x14:
            byte_count = area >> 1
        else:
            byte_count = area
        if byte_count > 0x7fffffff:
            raise ValueError('native 32-bit mipmap multiplication overflow')
        tbp0 += (byte_count + 255) >> 8
        width >>= 1
        height >>= 1
    return tbp0


def _mip_registers(record):
    levels = record['levels']
    if levels < 2:
        return (0, 0)
    if levels > 7:
        raise ValueError('native mip table stack only allocates six entries')
    tbps = [0] * 6
    tbws = [0] * 6
    width = record['width'] >> 1
    height = record['height'] >> 1
    for index in range(levels - 1):
        tbps[index] = _mipmap_base(
            record['psm'], record['tbp0'], width, height, index + 1)
        tbws[index] = int(width / 64) or 1
        width >>= 1
        height >>= 1
    packed = []
    for start in (0, 3):
        value = 0
        for i in range(3):
            value |= tbps[start + i] << (20 * i)
            value |= tbws[start + i] << (20 * i + 14)
        packed.append(_u64(value))
    return tuple(packed)


def texture_register_writes(slot, descriptor, filter_flag=0,
                            clamp_flag=0):
    """Replay 0x10C3E0. Return None on its native early-return-zero path.

    The flags are external renderer selection words at BSS 0x4FF470
    and 0x4FF474, not values within the texture descriptor.
    """
    if not isinstance(slot, int) or not 1 <= slot <= 255:
        return None
    record = parse_native_texture_record(descriptor)
    if record['tbp0'] == 0:
        return None
    if record['clut_flag'] and record['cbp'] == 0:
        return None
    if not isinstance(filter_flag, int) or not isinstance(clamp_flag, int):
        raise TypeError('captured texture flags must be integers')

    alpha_type = record['cpsm'] if record['clut_flag'] else record['psm']
    texa = (0x80 << 32) | (0x80 if alpha_type == 1 else 0)
    tex1 = 0x60 if filter_flag else 0

    tbw = int(record['width'] / 64) or 1
    tex0 = (record['tbp0'] | (tbw << 14) |
            (record['psm'] << 20) | (record['tw'] << 26) |
            (record['th'] << 30) | (4 << 32))
    if record['clut_flag']:
        tex0 |= ((record['cbp'] << 37) |
                 (record['cpsm'] << 51) | (1 << 62))

    clamp = (5 | (record['width'] << 14) |
             (record['height'] << 34)) if clamp_flag else 0
    mip1, mip2 = _mip_registers(record)
    values = (texa, tex1, _u64(tex0), _u64(clamp), mip1, mip2)
    return list(zip(GS_TEXTURE_ADDRESSES, values))


def texture_gif_ad_packet(writes):
    """Copy the six-entry template through native submitter 0x103E70.

    The transformed DMA descriptor uses 0x51000007, unlike the earlier
    TEST/ALPHA packet path. This constructs bytes but does not submit.
    """
    if (not isinstance(writes, (tuple, list)) or len(writes) != 6 or
            [address for address, _ in writes] != list(GS_TEXTURE_ADDRESSES)):
        raise ValueError('texture writer requires six native registers')
    if any(not isinstance(value, int) or not 0 <= value <= MASK64
           for _, value in writes):
        raise ValueError('all texture register values must be u64')
    return (struct.pack('<QIIQQ', 0xf0000007, 0x13000000, 0x51000007,
                        0x1000000000008006, GIF_AD) +
            b''.join(struct.pack('<QQ', value, address)
                     for address, value in writes))


def decode_texture_gif_ad_packet(data):
    if not isinstance(data, bytes) or len(data) != 128:
        raise ValueError('expected native six-register GIF DMA packet')
    if struct.unpack_from('<QIIQQ', data) != (
            0xf0000007, 0x13000000, 0x51000007,
            0x1000000000008006, GIF_AD):
        raise ValueError('invalid native texture GIF header')
    writes = [struct.unpack_from('<QQ', data, 32 + i * 16)
              for i in range(6)]
    if tuple(address for _, address in writes) != GS_TEXTURE_ADDRESSES:
        raise ValueError('unexpected texture GS register sequence')
    return [(address, value) for value, address in writes]


def decode_tex0(value):
    if not isinstance(value, int) or not 0 <= value <= MASK64:
        raise ValueError('TEX0 value must be u64')
    return dict(tbp0=value & 0x3fff, tbw=(value >> 14) & 0x3f,
                psm=(value >> 20) & 0x3f, tw=(value >> 26) & 0xf,
                th=(value >> 30) & 0xf, tcc=(value >> 34) & 1,
                tfx=(value >> 35) & 3, cbp=(value >> 37) & 0x3fff,
                cpsm=(value >> 51) & 0xf, csm=(value >> 55) & 1,
                csa=(value >> 56) & 0x1f, cld=(value >> 61) & 7)


def decode_tex1(value):
    if not isinstance(value, int) or not 0 <= value <= MASK64:
        raise ValueError('TEX1 value must be u64')
    return dict(lcm=value & 1, mxl=(value >> 2) & 7,
                mmag=(value >> 5) & 1, mmin=(value >> 6) & 7,
                mtba=(value >> 9) & 1, l=(value >> 19) & 3,
                k=(value >> 32) & 0xfff)


def decode_texa(value):
    if not isinstance(value, int) or not 0 <= value <= MASK64:
        raise ValueError('TEXA value must be u64')
    return dict(ta0=value & 0xff, aem=(value >> 15) & 1,
                ta1=(value >> 32) & 0xff)


def decode_clamp(value):
    if not isinstance(value, int) or not 0 <= value <= MASK64:
        raise ValueError('CLAMP value must be u64')
    return dict(wms=value & 3, wmt=(value >> 2) & 3,
                minu=(value >> 4) & 0x3ff, maxu=(value >> 14) & 0x3ff,
                minv=(value >> 24) & 0x3ff, maxv=(value >> 34) & 0x3ff)


def main():
    """Decode a captured 48-byte runtime descriptor without game art."""
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('record', type=Path, help='48-byte runtime descriptor')
    parser.add_argument('--slot', type=int, required=True,
                        help='native texture resource selector, 1..255')
    parser.add_argument('--filter-flag', type=lambda x: int(x, 0),
                        required=True, help='captured 0x4FF470 word')
    parser.add_argument('--clamp-flag', type=lambda x: int(x, 0),
                        required=True, help='captured 0x4FF474 word')
    parser.add_argument('--gif-output', type=Path,
                        help='optional reconstructed 128-byte GIF/DMA packet')
    args = parser.parse_args()
    try:
        raw = args.record.read_bytes()
        decoded = parse_native_texture_record(raw)
        writes = texture_register_writes(
            args.slot, raw, args.filter_flag, args.clamp_flag)
        if writes is None:
            raise ValueError('native texture descriptor failed validation')
        if args.gif_output is not None:
            args.gif_output.write_bytes(texture_gif_ad_packet(writes))
    except (OSError, ValueError, TypeError) as error:
        parser.error(str(error))

    values = dict(writes)
    print(json.dumps(dict(
        resource_slot=args.slot,
        descriptor_address=hex(ELF_DESCRIPTOR_TABLE + (args.slot - 1) * 48),
        descriptor=decoded,
        filter_flag=args.filter_flag,
        clamp_flag=args.clamp_flag,
        registers=[dict(address=hex(address), value=hex(value))
                   for address, value in writes],
        tex0=decode_tex0(values[GS_TEX0_1]),
        tex1=decode_tex1(values[GS_TEX1_1]),
        texa=decode_texa(values[GS_TEXA]),
        clamp=decode_clamp(values[GS_CLAMP_1]),
        limitations=[
            'Runtime texture-record bytes and flags must be captured.',
            'These are reconstructed register writes, not observed GS state.',
            'Other sprite commands may change these registers later.',
        ]
    ), indent=2))


if __name__ == '__main__':
    main()
