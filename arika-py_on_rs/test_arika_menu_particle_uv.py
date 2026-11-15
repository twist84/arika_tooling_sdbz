"""Instruction regressions for Dragon Summoning's texture-backed sprite.

EU beta SLES_541.61, SHA256:
80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0

0x2FCCB0 constructs the particle's 0x4EDCB0 subclass vtable.
+0x18 -> 0x2FCDD0 (XYWH setter), +0x1C -> 0x2FCE20 (UV edge+normalization),
+0x24 -> 0x2FDA00 (sprite reset). The pixel atlas is not distributed.
"""
import json
from pathlib import Path
import unittest

from arika_menu_particles import (
    c_dragon_particle_pool, normalized_sprite_uv, f32)
from menu_strip_oracle import c_strip_oracle, bits


# 0x2FCE20..0x2FCF38, including call into 0x2FD9E0 and the final JR delay.
SUBCLASS_SETTER = [
    666763216, 4290707488, 2142240784, 8421421, 202110584,
    3887333376, 2382626884, 276824122, 0, 2358837248,
    2402877504, 52492297, 0, 71303172, 137282,
    1149370368, 268435463, 1182795040, 809631745,
    6428709, 1149435904, 0, 1182795040, 1175758080,
    2382626884, 2358837248, 2402877508, 52492297,
    0, 71303172, 139330, 1149370368, 268435463,
    1182794016, 809697281, 8593445, 1149501440,
    0, 1182794016, 1174675712, 2248540204, 2248474664,
    2248409130, 2248343598, 1149634560, 1149566976,
    0, 1182795872, 1174669507, 1182793760, 1175715971,
    1149503488, 1149435904, 0, 1182795872, 1175717955,
    1182793760, 1174667267, 3858890848, 3858890864,
    3858956388, 3858956396, 3858825320, 3858825336,
    3858759796, 3858759804, 3753836576, 3350462464,
    2075131920, 65011720, 666697776,
]
BASE_SETTER = [2760179752, 2760245292, 2760310826,
               65011720, 2760376366]
SPRITE_RESET = [
    604176387, 1007042432, 2894266456, 604307457,
    604176386, 2894069776, 2692939852, 604176896,
    2894069780, 2760048720, 604176832, 2894069784,
    2894463004, 2760048724, 2894463008, 2894463012,
    2759852074, 2759852072, 2759852078, 2759852076,
    2894463024, 2894463028, 2894463032, 2894463036,
    2894069828, 2692743240, 2693070921, 2692743242,
    2692743243, 2692743232, 2693070940, 2693070925,
    2759852110, 65011720, 2759852114,
]
UV_NATIVE_FLOATS = (
    (0x60, 0), (0x64, 1), (0x68, 2), (0x6c, 1),
    (0x70, 0), (0x74, 3), (0x78, 2), (0x7c, 3),
)


class c_test_rng:
    def __init__(self):
        self.m_state = 1

    def next(self):
        self.m_state = (
            self.m_state * 0x5851F42D4C957F2D + 1
        ) & 0xffffffffffffffff
        return (self.m_state >> 32) & 0x7fffffff

    def get_state(self):
        return self.m_state


class DragonSpriteSetterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = json.loads((Path(__file__).parent /
                             'research/main_menu_map.json').read_text())
        cls.spec = report['first_components']['particles']

    def native_sprite(self, uv, dimensions):
        self.assertEqual(len(SUBCLASS_SETTER),
                         (0x2fcf3c - 0x2fce20) // 4)
        self.assertEqual(len(BASE_SETTER),
                         (0x2fd9f4 - 0x2fd9e0) // 4)
        machine = c_strip_oracle(
            dict(draw_address=0x2fce20, draw_words=SUBCLASS_SETTER,
                 clock_address=0x2fd9e0, clock_words=BASE_SETTER),
            [0, 0, 1, 1], 0, 0, 1, 1, 0, [0, 0])
        machine.m_code.update({
            0x2fda00 + i * 4: word
            for i, word in enumerate(SPRITE_RESET)
        })
        machine.m_registers[4] = 0x1000
        for reg, value in zip((5, 6, 7, 8), uv):
            machine.m_registers[reg] = value
        for off, _ in UV_NATIVE_FLOATS:
            machine.write_float(0x1000 + off, 123.0)
        getter_calls = []
        if dimensions is not None:
            machine.write_int(0x1044, 0x2000, 4)
            machine.write_int(0x2000, 0x3000, 4)
            machine.write_int(0x3040, 0xf00040, 4)
            machine.write_int(0x3044, 0xf00044, 4)

            def get_width(oracle):
                getter_calls.append('width')
                oracle.m_registers[2] = dimensions[0]

            def get_height(oracle):
                getter_calls.append('height')
                oracle.m_registers[2] = dimensions[1]

            machine.m_indirect_stubs = {
                0xf00040: get_width,
                0xf00044: get_height,
            }
        machine.run(0x2fce20)
        return machine, getter_calls

    def test_no_texture_updates_only_short_uv_edges(self):
        for uv in ((0, 320, 256, 432),
                   (136, 432, 248, 488),
                   (-8, 20, 11, -10)):
            machine, calls = self.native_sprite(uv, None)
            self.assertEqual(calls, [])
            for off, value in zip((0x28, 0x2c, 0x2a, 0x2e), uv):
                actual = machine.read_int(0x1000 + off, 2)
                self.assertEqual(actual, value & 0xffff)
            for off, _ in UV_NATIVE_FLOATS:
                self.assertEqual(machine.read_int(0x1000 + off, 4),
                                 bits(123.0),
                                 'the null texture early exit retains floats')

    def test_attached_texture_getters_and_exact_eight_floats(self):
        atlas_cases = (
            (512, 512), (512, 256), (256, 512),
            (1024, 1024), (640, 384), (800, 448),
        )
        uv_cases = (
            (0, 320, 256, 432),
            (256, 320, 416, 407),
            (136, 432, 248, 488),
            (0, 0, 1, 1),
            (-4, 12, 11, 49),
            (511, 320, 512, 504),
        )
        total = 0
        for dimensions in atlas_cases:
            for uv in uv_cases:
                machine, calls = self.native_sprite(uv, dimensions)
                self.assertEqual(calls, ['width', 'height'])
                normalized = normalized_sprite_uv(uv, dimensions)
                for off, index in UV_NATIVE_FLOATS:
                    self.assertEqual(
                        machine.read_int(0x1000 + off, 4),
                        bits(normalized[index]),
                        (uv, dimensions, off))
                for off, value in zip((0x28, 0x2c, 0x2a, 0x2e), uv):
                    self.assertEqual(machine.read_int(0x1000 + off, 2),
                                     value & 0xffff)
                total += 1
        self.assertEqual(total, 36)

    def test_native_reset_clears_edges_but_not_normalized_floats(self):
        machine, calls = self.native_sprite(
            (11, 22, 33, 44), (512, 512))
        normalized_before = [
            machine.read_int(0x1000 + off, 4)
            for off, _ in UV_NATIVE_FLOATS
        ]
        # Invoke the actual native 0x2FDA00 method with the same sprite.
        machine.m_registers[4] = 0x1000
        machine.m_registers[31] = 0xf00000
        machine.run(0x2fda00)
        self.assertEqual(calls, ['width', 'height'])
        self.assertEqual([machine.read_int(0x1000 + off, 2)
                          for off in (0x28, 0x2a, 0x2c, 0x2e)],
                         [0, 0, 0, 0])
        self.assertEqual([machine.read_int(0x1000 + off, 4)
                          for off, _ in UV_NATIVE_FLOATS],
                         normalized_before)

    def test_pool_recomputes_only_verified_presentation_metadata(self):
        pool = c_dragon_particle_pool(self.spec, c_test_rng(), 239.0)
        old = pool.snapshot()
        self.assertIsNone(old['texture_dimensions'])
        self.assertTrue(all(slot['uv_normalized'] is None
                            for slot in old['slots']))
        pool.set_texture_dimensions((640, 384))
        after = pool.snapshot()
        self.assertEqual(after['rng_state'], old['rng_state'])
        self.assertEqual(after['total_random_draws'],
                         old['total_random_draws'])
        for before, slot in zip(old['slots'], after['slots']):
            self.assertEqual(slot['uv'], before['uv'])
            self.assertEqual((slot['x'], slot['y'], slot['speed']),
                             (before['x'], before['y'], before['speed']))
            if slot['active']:
                self.assertEqual(slot['uv_normalized'],
                                 normalized_sprite_uv(
                                     slot['uv'], (640, 384)))
        # Native 0x37B210 calls subclass UV setter during left cropping.
        target = pool.m_slots[0]
        left = target['uv'][0]
        target['x'] = f32(239.0 + target['speed'] - 2.625)
        pool._update_slot(target)
        self.assertEqual(target['uv'][0], left + 2)
        self.assertEqual(
            target['uv_normalized'],
            normalized_sprite_uv(target['uv'], (640, 384)))
        self.assertEqual(pool.snapshot()['total_random_draws'],
                         old['total_random_draws'])

        last_uv = target['uv_normalized']
        pool._retire(target)
        self.assertEqual(target['uv'], [0, 0, 0, 0])
        self.assertEqual(target['uv_normalized'], last_uv)
        pool.set_texture_dimensions(None)
        self.assertIsNone(pool.snapshot()['texture_dimensions'])
        self.assertIsNone(pool.m_slots[0]['uv_normalized'])
        with self.assertRaises(ValueError):
            pool.set_texture_dimensions((0, 512))

    def test_runtime_texture_rebinding_survives_reset_without_rng(self):
        from arika_menu_runtime import c_menu_runtime
        report = json.loads((Path(__file__).parent /
                             'research/main_menu_map.json').read_text())
        runtime = c_menu_runtime(report, particle_seed=1)
        initial = runtime.m_particle_pool.snapshot()
        runtime.set_particle_texture_dimensions((640, 384))
        self.assertEqual(runtime.m_particle_pool.snapshot()['rng_state'],
                         initial['rng_state'])
        runtime.reset()
        self.assertEqual(runtime.m_particle_pool.m_texture_dimensions,
                         (640, 384))
        self.assertEqual(runtime.m_particle_pool.snapshot()[
            'total_random_draws'], 15)
        self.assertEqual(runtime.m_particle_pool.m_slots[0][
            'uv_normalized'],
            normalized_sprite_uv(
                runtime.m_particle_pool.m_slots[0]['uv'], (640, 384)))


if __name__ == '__main__':
    unittest.main()
