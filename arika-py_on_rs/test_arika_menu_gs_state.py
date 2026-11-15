"""EU beta sprite command-state boundary, extracted from ELF instructions.

This is the ENGINE command serializer, not a decoded PS2 GS register map.
The byte modes cannot be translated to GS ALPHA/TEST/ZBUF or Qt blending
without tracing their consumers. The native instruction oracle deliberately
does not infer or change blend rules.
"""
import unittest
from menu_strip_oracle import c_strip_oracle, bits


# 0x2FDA00..0x2FDA88, exact file-backed EU-beta MIPS words.
SPRITE_RESET_WORDS = [
    0x24030003, 0x3c063f80, 0xac830058, 0x24050001, 0x24030002,
    0xac800010, 0xa083004c, 0x24030200, 0xac800014, 0xa4830050,
    0x240301c0, 0xac800018, 0xac86001c, 0xa4830054, 0xac860020,
    0xac860024, 0xa480002a, 0xa4800028, 0xa480002e, 0xa480002c,
    0xac860030, 0xac860034, 0xac860038, 0xac86003c, 0xac800044,
    0xa0800048, 0xa0850049, 0xa080004a, 0xa080004b, 0xa0800040,
    0xa085005c, 0xa085004d, 0xa480004e, 0x03e00008, 0xa4800052,
]

# 0x2FD8A0..0x2FD8E4, sprite vtable +0x10 dispatcher. +0x40
# selects vtable+0x28 (zero) or vtable+0x30 (nonzero).
SPRITE_DRAW_DISPATCH_WORDS = [
    0x27bdfff0, 0xffbf0000, 0x90820040, 0x10400007, 0x00000000,
    0x8c990000, 0x8f390030, 0x0320f809, 0x00000000, 0x10000006,
    0xdfbf0000, 0x8c990000, 0x8f390028, 0x0320f809, 0x00000000,
    0xdfbf0000, 0x03e00008, 0x27bd0010,
]

# 0x2FD8F0..0x2FD904, exact texture-handle and sampler flag writes.
BIND_TEXTURE_WORDS = [
    0xac850044, 0xa0860048, 0xa0870049,
    0xa088004a, 0x03e00008, 0xa089004b,
]


def machine_for(address, words):
    return c_strip_oracle(
        dict(draw_address=address, draw_words=words,
             clock_address=0, clock_words=[]),
        [0, 0, 1, 1], 0, 0, 1, 1, 0, [0, 0])


class MenuGsStateBoundaryTests(unittest.TestCase):
    def test_native_reset_defaults_only_asserts_raw_engine_fields(self):
        self.assertEqual(len(SPRITE_RESET_WORDS),
                         (0x2fda8c - 0x2fda00) // 4)
        machine = machine_for(0x2fda00, SPRITE_RESET_WORDS)
        machine.m_registers[4] = 0x1000
        machine.run(0x2fda00)

        # Raw engine sprite fields, NOT decoded GS modes.
        for offset, value, size in (
                (0x10, 0, 4), (0x14, 0, 4), (0x18, 0, 4),
                (0x28, 0, 2), (0x2a, 0, 2),
                (0x2c, 0, 2), (0x2e, 0, 2),
                (0x40, 0, 1), (0x44, 0, 4),
                (0x48, 0, 1), (0x49, 1, 1),
                (0x4a, 0, 1), (0x4b, 0, 1),
                (0x4c, 2, 1), (0x4d, 1, 1),
                (0x4e, 0, 2), (0x50, 512, 2),
                (0x52, 0, 2), (0x54, 448, 2),
                (0x58, 3, 4), (0x5c, 1, 1)):
            self.assertEqual(
                machine.read_int(0x1000 + offset, size),
                value, (hex(offset), size))
        for offset in (0x1c, 0x20, 0x24, 0x30, 0x34, 0x38, 0x3c):
            self.assertEqual(machine.read_int(0x1000 + offset, 4),
                             bits(1.0), hex(offset))

    def test_texture_binding_preserves_four_distinct_sampler_bytes(self):
        self.assertEqual(len(BIND_TEXTURE_WORDS),
                         (0x2fd908 - 0x2fd8f0) // 4)
        for address, flags in (
                (0x4000, (0, 1, 0, 0)),
                (0x5abc, (1, 0, 3, 4)),
                (0, (255, 128, 4, 42)),
                (0x7fff, (2, 3, 4, 5))):
            machine = machine_for(0x2fd8f0, BIND_TEXTURE_WORDS)
            machine.m_registers[4] = 0x1000
            for reg, value in zip(range(5, 10), (address,) + flags):
                machine.m_registers[reg] = value
            machine.run(0x2fd8f0)
            self.assertEqual(machine.read_int(0x1044, 4), address)
            self.assertEqual(
                tuple(machine.read_int(0x1048 + i, 1) for i in range(4)),
                flags)

    def test_sprite_draw_dispatch_selects_correct_native_method(self):
        self.assertEqual(len(SPRITE_DRAW_DISPATCH_WORDS),
                         (0x2fd8e8 - 0x2fd8a0) // 4)
        for mode, expected in ((0, 'immediate'), (1, 'packet'),
                               (2, 'packet'), (255, 'packet')):
            machine = machine_for(0x2fd8a0, SPRITE_DRAW_DISPATCH_WORDS)
            machine.m_registers[4] = 0x1000
            machine.write_int(0x1000, 0x3000, 4)
            machine.write_int(0x1040, mode, 1)
            machine.write_int(0x3028, 0xf00028, 4)
            machine.write_int(0x3030, 0xf00030, 4)
            dispatched = []

            def immediate(oracle):
                dispatched.append('immediate')

            def packet(oracle):
                dispatched.append('packet')

            machine.m_indirect_stubs = {
                0xf00028: immediate, 0xf00030: packet,
            }
            machine.run(0x2fd8a0)
            self.assertEqual(dispatched, [expected])


if __name__ == '__main__':
    unittest.main()
