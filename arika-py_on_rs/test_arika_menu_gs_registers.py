"""EU-beta GS TEST/ALPHA/ZBUF GIF emission from recovered ELF branches.

The actual SLES_541.61 is optional user-supplied input at runtime, so
CI does not bundle game files or guess BSS resources.
"""
import struct
import unittest

from arika_menu_gs_registers import (
    GS_ALPHA_1, GS_ALPHA_2, GS_TEST_1, GS_TEST_2,
    GS_ZBUF_1, GS_ZBUF_2,
    NATIVE_ATST, NATIVE_ZTST, ALPHA_TABLE_ADDRESS,
    make_gs_test, decode_gs_test, make_gs_zbuf,
    depth_register_writes, make_gs_alpha, decode_gs_alpha,
    alpha_register_writes, extract_alpha_preset,
    make_gif_ad_dma, decode_gif_ad_dma,
)


class NativeGsEmitterTests(unittest.TestCase):
    def test_native_selector_jump_tables_and_gs_test_fields(self):
        # Native 0x4B4B90 / 0x4B4BB0 jump entries extracted from ELF.
        self.assertEqual(NATIVE_ZTST, (0, 1, 1, 1, 1, 1, 3, 2))
        self.assertEqual(NATIVE_ATST, (0, 1, 4, 7, 2, 3, 5, 6))
        self.assertEqual(ALPHA_TABLE_ADDRESS,
                         (0x439290, 0x439350, 0x439410))
        self.assertEqual(make_gs_test(7, 1, 3, 0), 0x0005000f)
        # ATST=7 NOTEQUAL, AREF=0; ZTST=2 GEQUAL.
        self.assertEqual(decode_gs_test(0x0005000f), dict(
            ate=1, atst=7, aref=0, afail=0,
            date=0, datm=0, zte=1, ztst=2))
        for ztest in range(8):
            for atest in range(8):
                v = make_gs_test(ztest, 1, atest, 0)
                dec = decode_gs_test(v)
                self.assertEqual(dec['ztst'], NATIVE_ZTST[ztest])
                self.assertEqual(dec['atst'], NATIVE_ATST[atest])
                self.assertEqual(dec['ate'], 1)
                self.assertEqual(dec['zte'], 1)
                self.assertEqual(dec['afail'], 0)

    def test_alpha_reference_special_case_and_zbuf_source_words(self):
        self.assertEqual(decode_gs_test(make_gs_test(7, 0, 3, 0))['aref'], 0)
        self.assertEqual(decode_gs_test(make_gs_test(7, 0, 3, 1))['aref'], 1)
        self.assertEqual(decode_gs_test(make_gs_test(7, 0, 3, 4))['aref'], 2)
        self.assertEqual(decode_gs_test(make_gs_test(7, 0, 3, 255))['aref'], 128)
        self.assertEqual(make_gs_zbuf(1, 0x400, 0x30), 0x30000020)
        self.assertEqual(make_gs_zbuf(0, 0x400, 0x30), 0x130000020)
        self.assertEqual(make_gs_zbuf(2, 0x400, 0x30), 0x130000020)
        self.assertEqual(depth_register_writes(7, 1, 3, 0, 2),
                         [(GS_ZBUF_1, None), (GS_TEST_1, 0x5000f),
                          (GS_ZBUF_2, None), (GS_TEST_2, 0x5000f)])
        self.assertEqual(depth_register_writes(7, 1, 3, 0, 0,
                                               0x400, 0x30),
                         [(GS_ZBUF_1, 0x30000020),
                          (GS_TEST_1, 0x5000f)])
        self.assertEqual(depth_register_writes(7, 1, 3, 0, 1,
                                               0x400, 0x30),
                         [(GS_ZBUF_2, 0x30000020),
                          (GS_TEST_2, 0x5000f)])

    def test_native_alpha_lookup_sample_and_gif_equation(self):
        # ELF 0x439290 + 30*2 + 5*3 contains [0,1,0,1,0].
        # GS ALPHA=(Cs-Cd)*As+Cd. Engine writes both contexts.
        preset = (0, 1, 0, 1, 0)
        self.assertEqual(make_gs_alpha(preset), 0x44)
        self.assertEqual(decode_gs_alpha(0x44),
                         dict(a=0, b=1, c=0, d=1, fix=0))
        self.assertEqual(alpha_register_writes(preset),
                         [(GS_ALPHA_1, 0x44), (GS_ALPHA_2, 0x44)])
        self.assertEqual(alpha_register_writes(preset, 0),
                         [(GS_ALPHA_1, 0x44)])
        self.assertEqual(alpha_register_writes(preset, 1),
                         [(GS_ALPHA_2, 0x44)])
        self.assertEqual(alpha_register_writes((0xff, 0, 0, 0, 0)), [])
        self.assertEqual(make_gs_alpha((2, 0, 0, 1, 128)),
                         0x8000000042)

    def test_exact_native_dma_giftag_and_ad_pair_layout(self):
        regs = [(GS_ZBUF_1, 0x30000020), (GS_TEST_1, 0x5000f),
                (GS_ZBUF_2, 0x30000020), (GS_TEST_2, 0x5000f)]
        packet = make_gif_ad_dma(regs)
        self.assertEqual(len(packet), 0x60)
        self.assertEqual(struct.unpack_from('<QIIQQ', packet),
                         (0xf0000005, 0x13000000, 0x50000005,
                          0x1000000000008004, 0xe))
        self.assertEqual(struct.unpack_from('<QQ', packet, 0x20),
                         (0x30000020, 0x4e))
        self.assertEqual(struct.unpack_from('<QQ', packet, 0x50),
                         (0x5000f, 0x48))
        self.assertEqual(decode_gif_ad_dma(packet), regs)
        alpha = [(GS_ALPHA_1, 0x44), (GS_ALPHA_2, 0x44)]
        packet = make_gif_ad_dma(alpha)
        self.assertEqual(len(packet), 0x40)
        self.assertEqual(struct.unpack_from('<QIIQQ', packet),
                         (0xf0000003, 0x13000000, 0x50000003,
                          0x1000000000008002, 0xe))
        self.assertEqual(decode_gif_ad_dma(packet), alpha)

    def test_unknown_runtime_zbuf_cannot_be_assumed(self):
        with self.assertRaises(ValueError):
            make_gif_ad_dma(depth_register_writes(7, 1, 3, 0, 2))
        for fn, args in ((make_gs_test, (8, 1, 3, 0)),
                         (make_gs_test, (7, 1, 8, 0)),
                         (make_gs_test, (7, 1, 3, 256)),
                         (make_gs_zbuf, (1, -1, 0)),
                         (alpha_register_writes, ((0, 1, 0, 1, 0), 3)),
                         (make_gs_alpha, ((255, 256, 0, 1, 0),))):
            with self.assertRaises((ValueError, TypeError)):
                fn(*args)
        for data in (b'', b'\0' * 16, b'\0' * 48,
                     make_gif_ad_dma([(0x42, 0x44)])[:-1]):
            with self.assertRaises(ValueError):
                decode_gif_ad_dma(data)
        # Never interpret a different build's lookup bytes as EU beta.
        with self.assertRaises(ValueError):
            extract_alpha_preset(b'not an EU beta ELF', 2, 3, 0)

    def test_stable_equal_depth_and_screen_occlusion_example(self):
        # Supplied PCSX2 screenshot shows banner Z=99 surviving a
        # later small sprite Z=5. GS GEQUAL is consistent with that.
        test = decode_gs_test(make_gs_test(7, 1, 3, 0))
        self.assertEqual(test['ztst'], 2)
        self.assertFalse(5 >= 99)
        self.assertTrue(99 >= 5)


if __name__ == '__main__':
    unittest.main()
