"""Asset-free regressions for the six GS registers emitted by 0x10C3E0.

Synthetic 48-byte texture descriptors are used in CI. With
SDBZ_EU_BETA_ELF set to an exact user-owned ELF, the optional tests
execute native words directly and compare 240 deterministic records.
"""
import os
import random
import struct
import unittest
from pathlib import Path

from arika_menu_gs_texture import (
    GS_TEXTURE_ADDRESSES, GS_TEXA, GS_TEX0_1, GS_TEX1_1,
    GS_CLAMP_1, GS_MIPTBP1_1, GS_MIPTBP2_1,
    ELF_DESCRIPTOR_TABLE, ELF_PACKET_TEMPLATE, parse_native_texture_record,
    texture_register_writes, texture_gif_ad_packet,
    decode_texture_gif_ad_packet, decode_tex0, decode_tex1, decode_texa,
    decode_clamp,
)


def fake_record(tbp0=0x120, cbp=0, tw=9, th=9, psm=0, cpsm=0,
                levels=1, clut_flag=0, width=512, height=512):
    data = bytearray(48)
    for offset, value in ((2, tbp0), (4, cbp), (6, tw), (8, th),
                          (0x12, levels), (0x14, clut_flag),
                          (0x16, width), (0x18, height)):
        struct.pack_into('<h', data, offset, value)
    struct.pack_into('<H', data, 0x0e, psm)
    struct.pack_into('<H', data, 0x10, cpsm)
    return bytes(data)


class TextureGsNativeTests(unittest.TestCase):
    def test_six_file_backed_register_addresses_and_resource_stride(self):
        self.assertEqual(ELF_DESCRIPTOR_TABLE, 0x4ff8f0)
        self.assertEqual(ELF_PACKET_TEMPLATE, 0x439e70)
        self.assertEqual(GS_TEXTURE_ADDRESSES,
                         (0x3b, 0x14, 0x06, 0x08, 0x34, 0x36))
        self.assertEqual(ELF_DESCRIPTOR_TABLE + (255 - 1) * 48,
                         0x502890)

    def test_direct_rgba_texture_pack_and_two_runtime_flags(self):
        record = fake_record()
        parsed = parse_native_texture_record(record)
        self.assertEqual(parsed, dict(
            tbp0=0x120, cbp=0, tw=9, th=9, psm=0, cpsm=0,
            levels=1, clut_flag=0, width=512, height=512))
        writes = texture_register_writes(1, record, filter_flag=1,
                                         clamp_flag=1)
        self.assertEqual([a for a, _ in writes], list(GS_TEXTURE_ADDRESSES))
        texa, tex1, tex0, clamp, mip1, mip2 = (v for _, v in writes)
        self.assertEqual(decode_texa(texa),
                         dict(ta0=0, aem=0, ta1=0x80))
        self.assertEqual(tex1, 0x60)
        self.assertEqual(decode_tex1(tex1)['mmag'], 1)
        self.assertEqual(decode_tex1(tex1)['mmin'], 1)
        self.assertEqual(decode_tex0(tex0), dict(
            tbp0=0x120, tbw=8, psm=0, tw=9, th=9,
            tcc=1, tfx=0, cbp=0, cpsm=0, csm=0, csa=0, cld=0))
        self.assertEqual(decode_clamp(clamp), dict(
            wms=1, wmt=1, minu=0, maxu=512, minv=0, maxv=512))
        self.assertEqual((mip1, mip2), (0, 0))
        disabled = texture_register_writes(1, record, 0, 0)
        self.assertEqual(disabled[1], (GS_TEX1_1, 0))
        self.assertEqual(disabled[3], (GS_CLAMP_1, 0))
        self.assertEqual(disabled[2], writes[2])
        self.assertEqual(disabled[0], writes[0])

    def test_clut_texture_special_texa_and_tex0_cbp_fields(self):
        palette = fake_record(tbp0=0x240, cbp=0x155, tw=8, th=7,
                              psm=0x13, cpsm=1, clut_flag=1,
                              width=256, height=128)
        writes = texture_register_writes(63, palette, 1, 1)
        self.assertEqual(writes[0], (GS_TEXA, 0x8000000080))
        fields = decode_tex0(writes[2][1])
        self.assertEqual((fields['psm'], fields['cpsm'], fields['cbp'],
                          fields['cld'], fields['tbw'], fields['tcc']),
                         (0x13, 1, 0x155, 2, 4, 1))
        self.assertEqual(writes[3][0], GS_CLAMP_1)
        self.assertEqual(decode_clamp(writes[3][1])['maxv'], 128)
        self.assertEqual(decode_texa(
            texture_register_writes(1, fake_record(psm=1))[0][1])['ta0'], 128)
        self.assertEqual(decode_texa(texture_register_writes(
            1, fake_record(psm=1, cbp=0x88,
                           clut_flag=1, cpsm=0))[0][1])['ta0'], 0)

    def test_bounded_invalid_and_resource_failure_paths(self):
        valid = fake_record()
        for slot in (0, -1, 256, 500):
            self.assertIsNone(texture_register_writes(slot, valid))
        self.assertIsNone(texture_register_writes(1, fake_record(tbp0=0)))
        self.assertIsNone(texture_register_writes(
            1, fake_record(clut_flag=1, cbp=0)))
        self.assertIsNotNone(texture_register_writes(
            1, fake_record(clut_flag=0, cbp=0)))
        self.assertEqual(decode_tex0(
            texture_register_writes(1, fake_record(width=48))[2][1])['tbw'], 1)
        for invalid in (b'', bytes(47), bytes(49), bytearray(48)):
            with self.assertRaises(ValueError):
                parse_native_texture_record(invalid)
        with self.assertRaises(ValueError):
            texture_register_writes(1, fake_record(levels=8))
        with self.assertRaises(TypeError):
            texture_register_writes(1, valid, filter_flag='yes')
        for fn in (decode_tex0, decode_tex1, decode_texa, decode_clamp):
            with self.assertRaises(ValueError):
                fn(-1)

    def test_mipmap_tbps_and_widths_match_native_0x10c7c0(self):
        rec = fake_record(tbp0=0x100, width=512, height=256,
                          tw=9, th=8, psm=1, levels=4)
        mip1 = texture_register_writes(1, rec)[4][1]
        mip2 = texture_register_writes(1, rec)[5][1]
        # Native helper restarts TBP from 0x100 for each already-halved
        # dimension: TBPs=0x300,0x1A0,0x12A; widths=4,2,1.
        expected = (0x300 | (4 << 14) | (0x1a0 << 20) |
                    (2 << 34) | (0x12a << 40) | (1 << 54))
        self.assertEqual(mip1, expected)
        self.assertEqual(mip2, 0)
        self.assertEqual(texture_register_writes(
            1, fake_record(psm=0x14, levels=2, width=128,
                           height=128))[4][1] & 0x3fff, 0x120 + 8)
        self.assertEqual(texture_register_writes(
            1, fake_record(psm=0x3f, levels=2))[4][1] & 0x3fff, 0x3fff)

    def test_exact_six_register_texture_dma_gif_packet(self):
        writes = texture_register_writes(1, fake_record(), 1, 1)
        data = texture_gif_ad_packet(writes)
        self.assertEqual(len(data), 128)
        self.assertEqual(struct.unpack_from('<QIIQQ', data),
                         (0xf0000007, 0x13000000, 0x51000007,
                          0x1000000000008006, 0x0e))
        self.assertEqual(struct.unpack_from('<QQ', data, 32),
                         (writes[0][1], GS_TEXA))
        self.assertEqual(struct.unpack_from('<QQ', data, 112),
                         (0, GS_MIPTBP2_1))
        self.assertEqual(decode_texture_gif_ad_packet(data), writes)
        for mutation in (data[:-1], data[:15] + b'\xff' + data[16:],
                         data[:40] + b'\xff' + data[41:]):
            with self.assertRaises(ValueError):
                decode_texture_gif_ad_packet(mutation)
        with self.assertRaises(ValueError):
            texture_gif_ad_packet(writes[:5])

    @unittest.skipUnless(os.environ.get('SDBZ_EU_BETA_ELF'),
                         'requires user-owned EU-beta ELF path')
    def test_differential_against_elf_240_runtime_descriptors(self):
        """Execute native 0x10C3E0/0x10C7C0 words, not emulated GS state."""
        from arika_menu_gs_texture_elf_oracle import c_native_texture_elf_oracle

        elf = Path(os.environ['SDBZ_EU_BETA_ELF']).read_bytes()
        random_state = random.Random(20261115)
        for index in range(240):
            slot = random_state.randrange(1, 256)
            cbp = (random_state.randrange(1, 0x500)
                   if random_state.randrange(2) else 0)
            rec = fake_record(
                tbp0=random_state.randrange(1, 0x400), cbp=cbp,
                tw=random_state.randrange(0, 11),
                th=random_state.randrange(0, 11),
                psm=random_state.choice((0, 1, 2, 0x13, 0x14)),
                cpsm=random_state.randrange(0, 3),
                levels=random_state.randrange(0, 8),
                clut_flag=random_state.randrange(2),
                width=random_state.choice(
                    (16, 32, 48, 64, 128, 192, 256, 512, 768, 1024)),
                height=random_state.choice(
                    (16, 32, 48, 64, 128, 192, 256, 512)))
            filter_flag = random_state.randrange(2)
            clamp_flag = random_state.randrange(2)
            native = c_native_texture_elf_oracle(elf)
            success, native_words = native.native_writes(
                slot, rec, filter_flag, clamp_flag)
            expected = texture_register_writes(
                slot, rec, filter_flag, clamp_flag)
            if expected is None:
                self.assertEqual(success, 0, index)
            else:
                self.assertEqual(success, 1, index)
                self.assertEqual(native_words,
                                 [value for _, value in expected],
                                 (index, hex(slot),
                                  parse_native_texture_record(rec)))

    @unittest.skipUnless(os.environ.get('SDBZ_EU_BETA_ELF'),
                         'requires user-owned EU-beta ELF path')
    def test_actual_elf_gif_template_bytes(self):
        import hashlib
        data = Path(os.environ['SDBZ_EU_BETA_ELF']).read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(),
                         '80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0')
        offset = ELF_PACKET_TEMPLATE - 0xfff80
        values = data[offset:offset+128]
        self.assertEqual(struct.unpack_from('<QIIQQ', values),
                         (0x70000007, 0, 0,
                          0x1000000000008006, 0x0e))
        self.assertEqual([struct.unpack_from('<Q', values, 40 + i*16)[0]
                          for i in range(6)], list(GS_TEXTURE_ADDRESSES))


if __name__ == '__main__':
    unittest.main()
