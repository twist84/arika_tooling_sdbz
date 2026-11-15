"""EU-beta libm wrapper dispatch tests, asset-independent except opt-in ELF.

The optional source-inspection case checks JAL addresses, the threshold
and NEG.S sites against the exact user-owned executable. CI exercises
the pure dispatcher without distributing ELF instructions/assets.
"""
import hashlib
import os
import struct
import unittest
from pathlib import Path

from arika_menu_native_trig import (
    NATIVE_COSINE, NATIVE_SINE, NATIVE_REDUCER, NATIVE_COS_KERNEL,
    NATIVE_SIN_KERNEL, SMALL_ANGLE_ABS_BITS, trig_dispatch,
    apply_native_neg_s, float_bits, float_value,
)


class MenuNativeTrigDispatchTests(unittest.TestCase):
    def test_both_wrappers_bypass_reducer_at_or_below_pi_over_four(self):
        self.assertEqual(SMALL_ANGLE_ABS_BITS, 0x3f490fd8)
        for angle in (0, 0x80000000, 0x3f000000, 0xbf000000,
                      SMALL_ANGLE_ABS_BITS,
                      SMALL_ANGLE_ABS_BITS | 0x80000000):
            for wrapper, kernel in ((NATIVE_COSINE, NATIVE_COS_KERNEL),
                                    (NATIVE_SINE, NATIVE_SIN_KERNEL)):
                with self.subTest(angle=hex(angle), wrapper=hex(wrapper)):
                    result = trig_dispatch(wrapper, angle)
                    self.assertEqual(result['kernel'], kernel)
                    self.assertIsNone(result['reducer'])
                    self.assertIsNone(result['quadrant'])
                    self.assertEqual(result['input_high_bits'], angle)
                    self.assertEqual(result['input_low_bits'], 0)
                    self.assertFalse(result['negated'])
                    if wrapper == NATIVE_SINE:
                        self.assertEqual(result['sine_mode'], 0)
                    with self.assertRaises(ValueError):
                        trig_dispatch(wrapper, angle, 0)

    def test_all_quadrants_match_elf_branch_targets(self):
        for wrapper, expected in (
                (NATIVE_COSINE, (
                    (NATIVE_COS_KERNEL, False, None),
                    (NATIVE_SIN_KERNEL, True, 1),
                    (NATIVE_COS_KERNEL, True, None),
                    (NATIVE_SIN_KERNEL, False, 1))),
                (NATIVE_SINE, (
                    (NATIVE_SIN_KERNEL, False, 1),
                    (NATIVE_COS_KERNEL, False, None),
                    (NATIVE_SIN_KERNEL, True, 1),
                    (NATIVE_COS_KERNEL, True, None)))):
            for q, (kernel, negate, mode) in enumerate(expected):
                for raw_q in (q, q + 4, q - 4):
                    result = trig_dispatch(
                        wrapper, SMALL_ANGLE_ABS_BITS + 1, raw_q)
                    self.assertEqual(result['reducer'], NATIVE_REDUCER)
                    self.assertEqual(
                        (result['quadrant'], result['kernel'],
                         result['negated'], result['sine_mode']),
                        (q, kernel, negate, mode))
                    self.assertEqual(result['input_source'],
                                     'reducer_sp_0_and_4')
                    self.assertIsNone(result['input_high_bits'])
                    self.assertIsNone(result['input_low_bits'])

    def test_wrapper_neg_s_flips_ieee_sign_bit_including_zero(self):
        negative = trig_dispatch(
            NATIVE_COSINE, 0x3f800000, reduced_quadrant=1)
        positive = trig_dispatch(
            NATIVE_COSINE, 0x3f800000, reduced_quadrant=3)
        for value in (0, 0x80000000, float_bits(0.25),
                      float_bits(-0.25), 0x7fc00000):
            self.assertEqual(apply_native_neg_s(value, negative),
                             value ^ 0x80000000)
            self.assertEqual(apply_native_neg_s(value, positive), value)
        self.assertEqual(float_bits(float_value(0x80000000)), 0x80000000)

    def test_unobserved_quadrant_or_invalid_call_cannot_be_guessed(self):
        for wrapper in (NATIVE_COSINE, NATIVE_SINE):
            with self.assertRaises(ValueError):
                trig_dispatch(wrapper, 0x3f490fd9)
            for invalid in (0.0, None, '1'):
                with self.assertRaises(ValueError):
                    trig_dispatch(wrapper, 0x3f490fd9, invalid)
        with self.assertRaises(ValueError):
            trig_dispatch(0x1234, 0x3f000000)
        with self.assertRaises(ValueError):
            trig_dispatch(NATIVE_COSINE, -1)
        with self.assertRaises(ValueError):
            trig_dispatch(NATIVE_COSINE, 1 << 32)
        with self.assertRaises(ValueError):
            apply_native_neg_s(0, {})
        with self.assertRaises(ValueError):
            apply_native_neg_s(-1, {'negated': True})

    @unittest.skipUnless(os.environ.get('SDBZ_EU_BETA_ELF'),
                         'requires exact user-owned EU-beta ELF')
    def test_source_elf_wrapper_calls_and_negation_sites(self):
        data = Path(os.environ['SDBZ_EU_BETA_ELF']).read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(),
                         '80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0')
        def word(address):
            return struct.unpack_from('<I', data, address - 0xfff80)[0]
        def jal(address, target):
            self.assertEqual(word(address), 0x0c000000 | (target >> 2),
                             (hex(address),hex(target)))
        for address in (0x1859f8, 0x185c98):
            self.assertEqual(word(address), 0x34630fd8,
                             hex(address))
        for site, target in (
                (0x185a10, NATIVE_COS_KERNEL),
                (0x185a20, NATIVE_REDUCER),
                (0x185a60, NATIVE_COS_KERNEL),
                (0x185a78, NATIVE_SIN_KERNEL),
                (0x185a88, NATIVE_COS_KERNEL),
                (0x185a98, NATIVE_SIN_KERNEL),
                (0x185cb0, NATIVE_SIN_KERNEL),
                (0x185cc0, NATIVE_REDUCER),
                (0x185d04, NATIVE_SIN_KERNEL),
                (0x185d1c, NATIVE_COS_KERNEL),
                (0x185d34, NATIVE_SIN_KERNEL),
                (0x185d48, NATIVE_COS_KERNEL)):
            jal(site, target)
        for address in (0x185a84, 0x185a94,
                        0x185d40, 0x185d50):
            self.assertEqual(word(address), 0x46000007, hex(address))


if __name__ == '__main__':
    unittest.main()
