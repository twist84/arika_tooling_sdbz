"""Ownership, RNG-order and repaint invariants for EU-beta six-slot particles.

Fixtures use the same ELF-derived template data as native main_menu_map.json.
A deterministic scalar RNG removes backend/DLL dependencies for pool tests.
"""
import json
from pathlib import Path
import unittest

from arika_menu_particles import c_dragon_particle_pool, random_unit, f32


class c_test_rng:
    def __init__(self, seed):
        self.m_state = seed & 0xffffffffffffffff

    def next(self):
        self.m_state = (
            self.m_state * 0x5851F42D4C957F2D + 1
        ) & 0xffffffffffffffff
        return (self.m_state >> 32) & 0x7fffffff

    def get_state(self):
        return self.m_state


class MenuDragonParticleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(
            (Path(__file__).parent / 'research/main_menu_map.json').read_text())
        cls.spec = cls.report['first_components']['particles']
        cls.clip = next(x['value'] for x in cls.report['startup']['position_values']
                        if x['address'] == cls.spec['runtime_clip_boundary_address'])

    def make_pool(self, seed=1):
        return c_dragon_particle_pool(self.spec, c_test_rng(seed), self.clip)

    def test_six_stable_slots_and_fifteen_initialization_rng_calls(self):
        pool = self.make_pool()
        state = pool.snapshot()
        self.assertEqual(len(state['slots']), 6)
        self.assertEqual(tuple(x['index'] for x in state['slots']), tuple(range(6)))
        self.assertEqual(tuple(x['active'] for x in state['slots']),
                         (True, True, True, True, True, False))
        self.assertEqual(state['total_random_draws'], 15)
        self.assertEqual(tuple(role for role, _ in state['random_draws']),
                         ('template', 'y', 'speed') * 5)
        for index, position in enumerate(self.spec['seed_positions']):
            self.assertEqual((state['slots'][index]['x'],
                              state['slots'][index]['y']), tuple(position))
        reference = c_test_rng(1)
        for _ in range(15):
            reference.next()
        self.assertEqual(pool.snapshot()['rng_state'], reference.get_state())

    def test_exact_first_spawn_and_timer_rng_order(self):
        pool = self.make_pool()
        before = pool.snapshot()
        timer = pool.step(0.0)
        state = pool.snapshot()
        self.assertEqual(state['total_random_draws'], 19)
        self.assertEqual(tuple(x[0] for x in state['random_draws']),
                         ('template', 'y', 'speed', 'timer'))
        self.assertTrue(state['slots'][5]['active'])
        self.assertEqual(state['slots'][5]['x'],
                         f32(512.0 - state['slots'][5]['speed']),
                         'the newly spawned slot moves in the same callback')
        self.assertTrue(90.0 <= timer <= 210.0)
        for i in range(5):
            self.assertEqual(state['slots'][i]['x'],
                             f32(before['slots'][i]['x'] -
                                 before['slots'][i]['speed']))
        for _ in range(10):
            timer = pool.step(timer)
        self.assertEqual(pool.snapshot()['total_random_draws'], 19)
        self.assertTrue(pool.snapshot()['slots'][5]['active'])

    def test_full_pool_expiry_consumes_timer_rng_only(self):
        pool = self.make_pool()
        pool.step(0.0)
        before = pool.snapshot()
        timer = pool.step(0.0)
        after = pool.snapshot()
        self.assertEqual(after['total_random_draws'],
                         before['total_random_draws'] + 1)
        self.assertEqual(tuple(x[0] for x in after['random_draws']), ('timer',))
        self.assertGreater(timer, 0)

    def test_expiration_reuses_first_inactive_slot_with_three_rng_inputs(self):
        pool = self.make_pool()
        pool.step(0.0)
        pool.m_slots[1]['x'] = f32(self.clip - 1.0)
        pool.m_slots[1]['uv'][0] = pool.m_slots[1]['uv'][2] - 1
        pool.m_slots[1]['speed'] = 1.0
        # 0x37A8A8 first tests the full pool; the subsequent update
        # retires slot 1. Only the NEXT expired callback can reuse it.
        before = pool.snapshot()['total_random_draws']
        pool.step(0.0)
        self.assertFalse(pool.snapshot()['slots'][1]['active'])
        self.assertEqual(tuple(x[0] for x in pool.snapshot()['random_draws']),
                         ('timer',))
        self.assertEqual(pool.snapshot()['total_random_draws'], before + 1)
        pool.step(0.0)
        after = pool.snapshot()
        self.assertTrue(after['slots'][1]['active'])
        self.assertEqual(after['slots'][1]['x'],
                         f32(512.0 - after['slots'][1]['speed']))
        self.assertEqual(tuple(x[0] for x in after['random_draws']),
                         ('template', 'y', 'speed', 'timer'))
        self.assertEqual(after['total_random_draws'], before + 5)
        self.assertEqual(tuple(s['index'] for s in after['slots']),
                         tuple(range(6)))

    def test_snapshot_and_geometry_are_nonowning_and_repeatable(self):
        pool = self.make_pool()
        before = pool.snapshot()
        geometry = pool.geometry(component_offset=[1.5, 2.5], depth=45.0)
        self.assertEqual(len(geometry), 5)
        self.assertEqual([p['slot'] for p in geometry], list(range(5)))
        self.assertEqual(pool.snapshot(), before)
        self.assertEqual(pool.geometry([1.5, 2.5], 45.0), geometry)
        self.assertEqual(pool.snapshot(), before)
        copy_of_old = pool.snapshot()
        pool.step(0.0)
        self.assertEqual(copy_of_old, before)
        self.assertNotEqual(pool.snapshot(), before)
        self.assertEqual(geometry[0]['geometry']['position'],
                         [f32(before['slots'][0]['x'] + 1.5),
                          f32(before['slots'][0]['y'] + 2.5)])

    def test_independent_instances_and_reset_replay(self):
        a, b, c = self.make_pool(1), self.make_pool(1), self.make_pool(2)
        self.assertEqual(a.snapshot(), b.snapshot())
        self.assertNotEqual(a.snapshot()['rng_state'],
                            c.snapshot()['rng_state'])
        clock_a = clock_b = 0.0
        for _ in range(250):
            clock_a = a.step(clock_a)
            clock_b = b.step(clock_b)
            self.assertEqual(clock_a, clock_b)
            self.assertEqual(a.snapshot(), b.snapshot())
        self.assertNotEqual(a.snapshot(), c.snapshot())
        self.assertEqual(self.make_pool(1).snapshot()['total_random_draws'], 15)

    def test_normalizer_matches_instruction_constant(self):
        self.assertEqual(random_unit(0), 0.0)
        self.assertEqual(random_unit(32767), 1.0)
        self.assertLess(random_unit(1), 1.0)


    def test_elf_phase_two_timer_and_call_order_with_external_pool_stubs(self):
        """Interpret actual 0x37A860 words with pool/RNG as controlled stubs.

        Verifies the EE callback, including both branch delay slots.
        It does not claim native pool-instruction parity.
        """
        from menu_strip_oracle import c_strip_oracle, bits

        # The complete routine 0x37A860..0x37A908, extracted from the
        # SHA-256-verified EU beta ELF; no ELF binary is redistributed.
        words = [
            666763232, 1006780288, 4290707472, 1149372416,
            2142240768, 1149239296, 3296854816, 8421421,
            1174474817, 1174470708, 1157627911, 3833660192,
            202238720, 0, 202238880, 4202541, 268435478,
            4141, 202238720, 0, 202238960, 4202541,
            201736468, 0, 809730047, 1149437952, 1006778368,
            876740864, 1182795872, 1149370368, 3347231640,
            1174470850, 3347166100, 1149239296, 0,
            1174470680, 1174605852, 268500966, 3858760480,
            3753836560, 2075131904, 65011720, 666697760,
        ]

        class c_one_value_rng:
            def __init__(self, value):
                self.m_value = value
                self.m_count = 0

            def next(self):
                self.m_count += 1
                return self.m_value

            def get_state(self):
                return self.m_count

        for timer in (-1.0, 0.0, 0.5, 1.0, 1.5, 90.0):
            for value in (0, 1, 0x7fff, 123456789, 0x7fffffff):
                machine = c_strip_oracle(
                    dict(draw_address=0x37a860, draw_words=words,
                         clock_address=0, clock_words=[]),
                    [0, 0, 1, 1], 0, 0, 1, 1, 0, [0, 0])
                machine.m_registers[28] = 0x4ff370
                machine.m_registers[4] = 0x1000
                machine.write_float(0x1320, timer)
                machine.write_float(0x4fa704, 90.0)
                machine.write_float(0x4fa708, 120.0)
                events = []

                def rng_stub(oracle):
                    events.append('rng')
                    oracle.m_registers[2] = value

                machine.m_direct_stubs = {
                    0x37ac00: {2: 0x2000},
                    0x37afc0: lambda oracle: events.append('scan'),
                    0x190450: rng_stub,
                    0x37ae80: lambda oracle: events.append('update'),
                }
                machine.run(0x37a860)
                expired = not f32(f32(timer) - 1.0) > 0
                self.assertEqual(
                    events,
                    ['scan', 'rng', 'update'] if expired else ['update'])

                pool = self.make_pool()
                pool.m_slots[5].update(active=True, template=0,
                                       uv=[0, 0, 10, 10], x=512.0,
                                       speed=0.0, depth_step=0.0)
                test_rng = c_one_value_rng(value)
                pool.m_rng = test_rng
                computed = pool.step(timer)
                self.assertEqual(
                    bits(computed), machine.read_int(0x1320, 4),
                    (timer, value))
                self.assertEqual(test_rng.m_count, 1 if expired else 0)
                self.assertEqual(pool.snapshot()['total_random_draws'],
                                 15 + (1 if expired else 0))


    def test_elf_particle_movement_clip_and_retirement_oracle(self):
        """Execute real 0x37B210 instructions with sprite setter/reset stubs.

        Delta cases are integral so the test avoids unresolved FCR31
        fractional CVT.W.S rounding modes. This does not test the texture
        setter implementation or EE hardware FPU precision.
        """
        from menu_strip_oracle import c_strip_oracle, bits

        words = [
            666763216, 4290707488, 2142306320, 2142240768,
            2359492768, 274726987, 10520621, 3324051608,
            3323986064, 1174470657, 3860856976, 3347179760,
            3323986064, 1174470708, 1157693448, 0, 2250506280,
            2250440746, 8587306, 270532658, 0, 268435516,
            3753836576, 1174407233, 1006784256, 1149370368,
            0, 1174470710, 1157693445, 0, 1174407204,
            1141047296, 268435464, 811859967, 1174407169,
            1006796800, 1174405156, 1141047296, 0, 6428709,
            811859967, 2250375208, 812711935, 1055804,
            2250637356, 203839, 2250702890, 2250768430,
            4395041, 2787246120, 2386100224, 2250571816,
            2402877468, 52492297, 35659821, 100663300,
            3324051600, 1150287872, 268435464, 1182793760,
            1056834, 839057409, 8593445, 1149501440, 0,
            1182793760, 1174405120, 1174407168, 268500939,
            3860856976, 2386100224, 2402877476, 52492297,
            35659821, 3347174944, 2921332888, 3347109412,
            2921332896, 3860922512, 268500933, 3860856980,
            3753836576, 2075197456, 2075131904, 65011720,
            666697776,
        ]
        self.assertEqual(len(words), (0x37b368 - 0x37b210) // 4)
        cases = [
            (False, 300.0, 1.0, 0, 20),
            (True, 300.0, 0.5, 0, 20),
            (True, 240.0, 1.0, 0, 20),
            (True, 239.0, 1.0, 0, 20),
            (True, 238.0, 1.0, 0, 20),
            (True, 238.0, 1.0, 19, 20),
            (True, 300.0, 1.0, 20, 20),
        ]

        for active, x, speed, left, right in cases:
            machine = c_strip_oracle(
                dict(draw_address=0x37b210, draw_words=words,
                     clock_address=0, clock_words=[]),
                [0, 0, 1, 1], 0, 0, 1, 1, 0, [0, 0])
            machine.m_registers[5] = 0x1000
            machine.m_registers[28] = 0x4ff370
            machine.write_int(0x1000, 0x2000, 4)
            machine.write_int(0x201c, 0xf00024, 4)
            machine.write_int(0x2024, 0xf00028, 4)
            machine.write_float(0x4fdc60, self.clip)
            machine.write_float(0x4fc990, 0.0)
            machine.write_float(0x4fc994, 0.0)
            machine.write_int(0x10a0, int(active), 4)
            machine.write_float(0x1090, x)
            machine.write_float(0x1094, 25.0)
            machine.write_float(0x1098, speed)
            machine.write_int(0x1028, left, 2)
            machine.write_int(0x102a, right, 2)
            machine.write_int(0x102c, 10, 2)
            machine.write_int(0x102e, 40, 2)
            machine.m_indirect_stubs = {
                0xf00024: lambda oracle: None,
                0xf00028: lambda oracle: None,
            }
            machine.run(0x37b210)

            pool = self.make_pool()
            slot = pool.m_slots[0]
            slot.update(active=active, x=x, y=25.0, speed=speed,
                        uv=[left, 10, right, 40])
            pool._update_slot(slot)
            self.assertEqual(slot['active'], bool(machine.read_int(0x10a0, 4)))
            self.assertEqual(slot['uv'][0],
                             machine.read_int(0x1028, 2) -
                             (0x10000 if machine.read_int(0x1028, 2) & 0x8000 else 0))
            for key, offset in [('x', 0x90), ('y', 0x94),
                                ('speed', 0x98)]:
                self.assertEqual(bits(slot[key]),
                                 machine.read_int(0x1000 + offset, 4),
                                 (active, x, speed, left, right, key))


    def test_elf_pool_initialization_call_order_and_seed_positions(self):
        """Interpret 0x37ADB0 with sprite reset/setup and RNG external stubs.

        The native loop controls slot stride, first five activations,
        template selection, RNG ordering and seed position overwrite.
        Sprite construction arithmetic is separately host modeled and is
        NOT validated by substituting the sprite setup stub.
        """
        from menu_strip_oracle import c_strip_oracle, bits
        words = [
            666763184, 4290707520, 2142437424, 2142371872,
            38957, 2142306320, 2142240768, 1007747147,
            8421421, 640786592, 33591341, 33562669,
            202238996, 37759021, 711131141, 341835785,
            0, 0, 645070849, 711131142, 642908336,
            341901301, 640745480, 268435474, 0, 201736468,
            0, 135491, 71368708, 809893891, 281018371,
            33562669, 617021436, 33562669, 202239016,
            37759021, 3323985920, 3862954128, 3323985924,
            268500970, 3862954132, 0, 3753836608,
            2075328560, 2075263008, 2075197456, 2075131904,
            65011720, 666697808,
        ]
        self.assertEqual(len(words), (0x37ae74 - 0x37adb0) // 4)
        oracle = c_strip_oracle(
            dict(draw_address=0x37adb0, draw_words=words,
                 clock_address=0, clock_words=[]),
            [0, 0, 1, 1], 0, 0, 1, 1, 0, [0, 0])
        oracle.m_registers[4] = 0x1000
        for i, (x, y) in enumerate(self.spec['seed_positions']):
            oracle.write_float(self.spec['seed_position_table'] + i * 8, x)
            oracle.write_float(self.spec['seed_position_table'] + i * 8 + 4, y)
        events = []
        fake_rng = c_test_rng(1)

        def reset_slot(machine):
            index = (machine.m_registers[5] - 0x1000) // 0xb0
            events.append(('reset', index))
            machine.write_int(machine.m_registers[5] + 0xa0, 0, 4)

        def draw_rng(machine, role):
            value = fake_rng.next()
            events.append((role, value))
            machine.m_registers[2] = value

        def random_template(machine):
            draw_rng(machine, 'template')

        def sprite_init(machine):
            index = (machine.m_registers[5] - 0x1000) // 0xb0
            events.append(('initialize', index, machine.m_registers[6]))
            machine.write_int(machine.m_registers[5] + 0xa0, 1, 4)
            draw_rng(machine, 'y')
            draw_rng(machine, 'speed')

        oracle.m_direct_stubs = {
            0x37b050: reset_slot,
            0x190450: random_template,
            0x37b0a0: sprite_init,
        }
        oracle.run(0x37adb0)
        pool = self.make_pool(1)
        self.assertEqual(fake_rng.get_state(), pool.snapshot()['rng_state'])
        self.assertEqual([x[1] for x in events if x[0] == 'reset'],
                         list(range(6)))
        initializations = [x for x in events if x[0] == 'initialize']
        self.assertEqual([x[1] for x in initializations], list(range(5)))
        self.assertEqual([x[2] for x in initializations],
                         [pool.m_slots[i]['template'] for i in range(5)])
        self.assertEqual([x[0] for x in events if x[0] in (
            'template', 'y', 'speed')], ['template', 'y', 'speed'] * 5)
        for i, (x, y) in enumerate(self.spec['seed_positions']):
            self.assertEqual(bits(x), oracle.read_int(
                0x1000 + i * 0xb0 + 0x90, 4))
            self.assertEqual(bits(y), oracle.read_int(
                0x1000 + i * 0xb0 + 0x94, 4))
            self.assertEqual(oracle.read_int(0x1000 + i * 0xb0 + 0xa0, 4),
                             1)
        self.assertEqual(oracle.read_int(0x1000 + 5 * 0xb0 + 0xa0, 4), 0)


    def test_elf_sprite_initialize_numeric_fields(self):
        """Execute 0x37B0A0 with only renderer/resource calls stubbed.

        The sprite UV setter is a controlled memory store, not an emulated
        GS draw. Numeric particle fields and RNG call order are compared
        after running the native instructions.
        """
        import struct
        from menu_strip_oracle import c_strip_oracle, bits

        words = [
            666763216, 1006764107, 4290707488, 399616,
            2142306320, 608346208, 2142240768, 10520621,
            202232696, 4423713, 4202541, 202230136,
            604307467, 4204589, 35659821, 12333,
            604438529, 16429, 202110524, 18477,
            2386100224, 35659821, 2402877464, 52492297,
            33564717, 35659821, 202109908, 604307457,
            1149263872, 202109904, 35659821, 1006764109,
            3292580112, 201736468, 3860856976, 809730047,
            1149437952, 1006778368, 876740864, 1182795872,
            1149370368, 2516713478, 71303172, 1174470914,
            1149370368, 268435464, 1182793952, 137282,
            809631745, 6428709, 1149435904, 0,
            1182793952, 1174608064, 3347231648, 3347166108,
            1149239296, 1174605953, 1174470680, 1174671388,
            3860856980, 3321888776, 201736468, 3860856984,
            809730047, 604241921, 1149435904, 3322085388,
            1182793888, 1006843904, 879034624, 1006845388,
            878955725, 2921595040, 1149569024, 1149435904,
            0, 1174538498, 3324117144, 1149241344,
            0, 1174538264, 1174673500, 1174470658,
            3860922520, 3860856988, 3753836576, 2075197456,
            2075131904, 65011720, 666697776,
        ]
        self.assertEqual(len(words), (0x37b20c - 0x37b0a0) // 4)
        for entry in self.spec['templates']:
            for y_value, speed_value in ((0, 0), (32767, 32767),
                                         (1, 12345)):
                machine = c_strip_oracle(
                    dict(draw_address=0x37b0a0, draw_words=words,
                         clock_address=0, clock_words=[]),
                    [0, 0, 1, 1], 0, 0, 1, 1, 0, [0, 0])
                machine.m_registers[4] = 0x1000
                machine.m_registers[5] = 0x1000
                machine.m_registers[6] = entry['index']
                machine.m_registers[28] = 0x4ff370
                machine.write_int(0x1000, 0x2000, 4)
                machine.write_int(0x2018, 0xf00024, 4)
                machine.write_float(0x4cc910, 512.0)
                machine.write_float(0x4fa710, 260.0)
                machine.write_float(0x4fa70c, -30.0)
                machine.write(entry['address'],
                              struct.pack('<4h2f', *entry['uv_xywh'],
                                          entry['speed_base'],
                                          entry['speed_random_span']))
                rng_values = iter((y_value, speed_value))
                draws = []

                def rng_stub(oracle):
                    value = next(rng_values)
                    draws.append(value)
                    oracle.m_registers[2] = value

                def uv_setter(oracle):
                    # Simulate only setter output memory, not the sprite/GS.
                    xywh = struct.unpack('<4h',
                                         oracle.read(oracle.m_registers[5], 8))
                    for i, value in enumerate(
                            (xywh[0], xywh[0] + xywh[2],
                             xywh[1], xywh[1] + xywh[3])):
                        oracle.write_int(0x1028 + i * 2, value, 2)

                machine.m_direct_stubs = {
                    0x374de0: {2: 0x3000},
                    0x3725e0: {2: 0x4000},
                    0x2fd8f0: {},
                    0x2fcf50: {},
                    0x2fcf40: {},
                    0x190450: rng_stub,
                }
                machine.m_indirect_stubs = {0xf00024: uv_setter}
                machine.run(0x37b0a0)
                self.assertEqual(draws, [y_value, speed_value])
                # _activate also consumes template RNG; replace it with a
                # known selector so its next two inputs match this oracle.
                class c_recorded_rng:
                    def __init__(self):
                        self.m_values = iter((entry['index'] << 5,
                                              y_value, speed_value))
                    def next(self):
                        return next(self.m_values)
                    def get_state(self):
                        return 0
                pool = self.make_pool()
                pool.m_rng = c_recorded_rng()
                pool._activate(5)
                slot = pool.m_slots[5]
                for key, offset in [('x', 0x90), ('y', 0x94),
                                    ('speed', 0x98), ('depth_step', 0x9c)]:
                    self.assertEqual(bits(slot[key]),
                                     machine.read_int(0x1000 + offset, 4),
                                     (entry['index'], y_value, speed_value, key))
                self.assertEqual(int(slot['active']),
                                 machine.read_int(0x10a0, 4))
                self.assertEqual(slot['uv'],
                                 [machine.read_int(0x1028 + i*2, 2)
                                  for i in range(4)])


    def test_runtime_pending_interruption_reentry_and_reset_ownership(self):
        from arika_menu_runtime import c_menu_runtime

        runtime = c_menu_runtime(self.report, particle_seed=1)
        pool = runtime.m_particle_pool
        self.assertIsNotNone(pool)
        original = runtime.snapshot()['particles']
        first = runtime.m_first_states[3]
        runtime.m_item_phases[3] = 2
        first.update(phase=2, age=0.0, offset=[0.0, 0.0],
                     particle_timer=0.0, depth=15.0)
        runtime._update_item(3, 'particle_ownership_test')
        active = runtime.snapshot()['particles']
        self.assertNotEqual(active, original)
        self.assertEqual(active['total_random_draws'], 19)
        self.assertIs(runtime.m_particle_pool, pool,
                      'phase-2 update must not allocate a second pool')

        # Pending exit keeps the original owner; inactive first-phase
        # stops callbacks but does not destroy or fork the global pool.
        runtime.m_pending = 3
        runtime.m_selected = 0
        runtime.m_item_phases[3] = 4
        first['phase'] = 4
        self.assertTrue(runtime.particle_geometry(3))
        self.assertEqual(runtime.particle_geometry(3),
                         runtime.particle_geometry(3))
        for _ in range(3):
            runtime._update_item(3, 'particle_ownership_test')
        self.assertEqual(runtime.snapshot()['particles'], active)
        first['phase'] = 0
        self.assertEqual(runtime.particle_geometry(3), [])
        self.assertIs(runtime.m_particle_pool, pool)
        self.assertEqual(runtime.snapshot()['particles'], active)

        # A new runtime instance never shares mutable slots or RNG state.
        other = c_menu_runtime(self.report, particle_seed=1)
        self.assertEqual(other.snapshot()['particles'], original)
        self.assertIsNot(other.m_particle_pool, pool)
        runtime.reset()
        self.assertEqual(runtime.snapshot()['particles'], original)
        self.assertIsNot(runtime.m_particle_pool, pool)
        self.assertEqual(other.snapshot()['particles'], original)


if __name__ == '__main__':
    unittest.main()
