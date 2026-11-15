"""Execute actual EU-beta 0x379B50 MIPS words against the Python exit runtime.

Uses the existing test-only scalar R5900 interpreter. The ELF is supplied
locally; no proprietary code bytes, texture data or sound files are bundled.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

from menu_strip_oracle import c_strip_oracle, bits, real
from arika_menu_runtime import c_menu_runtime

EXPECTED_ELF_SHA256 = '80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0'
EXPECTED_GP = 0x004ff370
BASE_ADDRESS = 0x00100000
FILE_OFFSET = 0x80
EXIT_ADDRESS = 0x00379b50
EXIT_END = 0x00379c7c


def load_exit_words(elf_path):
    data = Path(elf_path).read_bytes()
    if hashlib.sha256(data).hexdigest() != EXPECTED_ELF_SHA256:
        raise ValueError('expected exact EU-beta SLES_541.61 SHA-256')
    if (data[:6] != b'\x7fELF\x01\x01' or
            struct.unpack_from('<I', data, 0x3fc9d8 + 20)[0] != EXPECTED_GP):
        raise ValueError('invalid EU-beta ELF header / GP')

    def offset(address):
        return FILE_OFFSET + (address - BASE_ADDRESS)

    threshold = struct.unpack_from('<f', data, offset(EXPECTED_GP - 0x4cc4))[0]
    audio_threshold = struct.unpack_from('<f', data, offset(EXPECTED_GP - 0x4cc0))[0]
    if (threshold, audio_threshold) != (10.0, 60.0):
        raise ValueError('native constant did not match GP-relative load')

    count = (EXIT_END - EXIT_ADDRESS) // 4
    return list(struct.unpack_from('<%dI' % count, data, offset(EXIT_ADDRESS)))


class c_menu_exit_oracle(c_strip_oracle):
    def __init__(self, words, phase, age, fade_busy):
        super().__init__(
            {'draw_address': 0, 'draw_words': [],
             'clock_address': 0, 'clock_words': []},
            [0, 0, 1, 1], 0, 0, 1, 1, 0, [0, 0])
        self.m_code.update({EXIT_ADDRESS + i * 4: word
                            for i, word in enumerate(words)})
        self.m_registers[28] = EXPECTED_GP
        self.write_int(0x1000 + 0xc8, phase, 4)
        self.write_float(0x1000 + 0xcc, age)
        self.write_float(EXPECTED_GP - 0x4cc4, 10.0)
        self.m_events = []

        def fade_reset(machine):
            self.m_events.append(('fade_reset',))

        def fade_start(machine):
            self.m_events.append((
                'fade_start', machine.m_registers[4], machine.m_registers[5],
                real(machine.m_floats[12]), real(machine.m_floats[13])))

        def fade_poll(machine):
            machine.m_registers[2] = int(bool(fade_busy))

        self.m_direct_stubs = {
            0x002c0c90: fade_reset,
            0x002c08a0: fade_start,
            0x002c0c20: fade_poll,
        }

    def invoke(self):
        self.run(EXIT_ADDRESS)
        return {
            'return': self.m_registers[2],
            'phase': self.read_int(0x1000 + 0xc8, 4),
            'age_bits': self.read_int(0x1000 + 0xcc, 4),
            'effects': self.m_events,
        }


def compare_native_exit(elf_path):
    """96 native MIPS invocations with stubbed external fade completion."""
    words = load_exit_words(elf_path)
    count = 0
    for phase in (0, 1, 2, 3, 30, 99):
        for age in (0., 0.5, 1., 8., 9., 9.5, 10., 99999.):
            for fade_busy in (False, True):
                native = c_menu_exit_oracle(words, phase, age, fade_busy).invoke()
                runtime = c_menu_runtime()
                runtime.m_outer_phase = 3
                runtime.m_exit_phase = phase
                runtime.m_exit_age = age
                runtime.m_selected = 0
                runtime.m_navigation.m_selected = 0
                runtime._update_exit(fade_busy)
                effects = []
                for call in runtime.m_last_calls:
                    if call['event'] == 'fade_reset':
                        effects.append(('fade_reset',))
                    elif call['event'] == 'fade_start':
                        effects.append((
                            'fade_start', call['mode'], call['duration'],
                            call['x'], call['y']))
                expected_return = int(runtime.m_outer_phase == 4)
                matches = (
                    native['return'] == expected_return and
                    native['phase'] == runtime.m_exit_phase and
                    native['age_bits'] == bits(runtime.m_exit_age) and
                    native['effects'] == effects
                )
                if not matches:
                    raise AssertionError('ELF divergence: %r' % {
                        'phase': phase, 'age': age, 'fade_busy': fade_busy,
                        'native': native, 'runtime': runtime.snapshot(),
                        'runtime_effects': effects,
                    })
                count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    args = parser.parse_args()
    count = compare_native_exit(args.elf)
    print(json.dumps({
        'elf_sha256': EXPECTED_ELF_SHA256,
        'native_exit_cases_passed': count,
        'external_fade_stub': 'fixed boolean for each test case',
    }, indent=2))


if __name__ == '__main__':
    main()
