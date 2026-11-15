"""Compare EU-beta parent menu dispatch 0x333920 with executable MIPS words.

Requires the user's own SHA-validated SLES_541.61. Callback implementations
are controlled stubs, not claims that full render/audio/GPU state is emulated.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

from menu_strip_oracle import c_strip_oracle

ELF_SHA256 = '80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0'
PARENT_START = 0x00333920
PARENT_END = 0x00333aa4
BASE_VA = 0x00100000
BASE_FILE = 0x80
CALLBACKS = {
    0x40: 'child', 0x30: 'start', 0x44: 'ready', 0x34: 'entry',
    0x48: 'input', 0x4c: 'exit', 0x58: 'complete',
}


def load_parent_words(elf):
    data = Path(elf).read_bytes()
    if hashlib.sha256(data).hexdigest() != ELF_SHA256:
        raise ValueError('expected exact EU-beta SLES_541.61 SHA-256')
    offset = BASE_FILE + PARENT_START - BASE_VA
    count = (PARENT_END - PARENT_START) // 4
    return struct.unpack_from('<%dI' % count, data, offset)


class c_parent_oracle(c_strip_oracle):
    def __init__(self, words, phase, ready=False, input_return=False,
                 exit_completed=False, indirect_exit=False, next_complete=True):
        super().__init__(
            dict(draw_address=0, draw_words=[], clock_address=0, clock_words=[]),
            [0, 0, 1, 1], 0, 0, 1, 1, 0, [0, 0])
        self.m_code.update({
            PARENT_START + i * 4: word for i, word in enumerate(words)
        })
        self.m_registers[4] = 0x1000
        self.write_int(0x1000, 0x6000, 4)
        self.write_int(0x1000 + 0x14, phase, 4)
        # Nonnull parent owner; 0x333C10 post-exit check is a controlled stub.
        self.write_int(0x1000 + 0x10, 0x7000, 4)
        self.write_int(0x1000 + 0x18, 0, 4)
        self.m_events = []

        for index, (slot, name) in enumerate(CALLBACKS.items()):
            address = 0xf10000 + 16 * index
            self.write_int(0x6000 + slot, address, 4)

            def callback(name):
                def call(machine):
                    self.m_events.append(name)
                    if name == 'ready':
                        machine.m_registers[2] = int(ready)
                    elif name == 'input':
                        machine.m_registers[2] = int(input_return)
                        if indirect_exit:
                            # Real 0x379C80 returns zero after it invokes
                            # the confirm/cancel handler, which changes +14.
                            self.write_int(0x1000 + 0x14, 3, 4)
                    elif name == 'exit':
                        machine.m_registers[2] = int(exit_completed)
                return call

            self.m_indirect_stubs[address] = callback(name)

        def begin_exit(machine):
            self.m_events.append('begin_exit')
            self.write_int(0x1000 + 0x14, 3, 4)

        def finish_check(machine):
            self.m_events.append('finish_check')
            machine.m_registers[2] = int(next_complete)

        self.m_direct_stubs[0x00333b70] = begin_exit
        self.m_direct_stubs[0x00333c10] = finish_check

    def invoke(self):
        self.run(PARENT_START)
        return self.read_int(0x1000 + 0x14, 4), self.m_events


def expected_parent(phase, ready, input_return, exit_completed, indirect_exit):
    """Independently authored branch specification from 0x333920 disassembly."""
    if phase == 4:
        return 4, []
    calls = ['child']
    if phase == 0:
        calls.append('start')
        phase = 1
    if phase == 1:
        calls.append('ready')
        if not ready:
            return 1, calls
        phase = 2
        calls.append('entry')
    if phase == 2:
        calls.append('input')
        if input_return:
            calls.append('begin_exit')
            phase = 3
        elif indirect_exit:
            # No fall-through to +0x4C after an indirect input callback.
            return 3, calls
        else:
            return 2, calls
    if phase == 3:
        calls.append('exit')
        if exit_completed:
            calls.extend(('finish_check', 'complete'))
            return 4, calls
        return 3, calls
    return phase, calls


def compare_parent(elf):
    words = load_parent_words(elf)
    count = 0
    for phase in (0, 1, 2, 3, 4, 99):
        for bits in range(16):
            ready = bool(bits & 1)
            input_return = bool(bits & 2)
            exit_completed = bool(bits & 4)
            indirect_exit = bool(bits & 8) and not input_return
            native = c_parent_oracle(
                words, phase, ready, input_return, exit_completed,
                indirect_exit)
            actual = native.invoke()
            expected = expected_parent(
                phase, ready, input_return, exit_completed, indirect_exit)
            if actual != expected:
                raise AssertionError(
                    'ELF parent divergence at phase=%d bits=0x%x: %r vs %r'
                    % (phase, bits, actual, expected))
            count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    args = parser.parse_args()
    print(json.dumps({
        'elf_sha256': ELF_SHA256,
        'native_parent_cases_passed': compare_parent(args.elf),
        'callback_status': 'stubbed external menu/component callbacks',
    }, indent=2))


if __name__ == '__main__':
    main()
