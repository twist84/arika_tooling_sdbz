"""EU-beta SDBZ CAppLogoMain update, recovered from EE 0x0041E890.

The runtime models the *application state* only; it does not synthesize
sprite resources, audio progress, screen output or elapsed wall time.
Each step receives the game's observed float delta, audio-helper result and
controller words, then follows the recovered MIPS branches and delay slots.

The matching ELF is SLES_541.61 SHA-256
80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct


ELF_SHA256 = '80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0'
LOGO_UPDATE_ADDRESS = 0x0041E890
LOGO_BEGIN_ADDRESS = 0x0041E850
LOGO_INPUT_ADDRESS = 0x0041EC50
LOGO_WAIT_ADDRESS = 0x0041EBF0
LOGO_DURATION = 2.0  # lui 0x4000 at 0x41EC10
LOOP_PAUSE_BITS = 0x3DAAAAAB  # 0x41EA10..0x41EA14
LOOP_PAUSE = struct.unpack('<f', struct.pack('<I', LOOP_PAUSE_BITS))[0]


def _f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def _word16(value, name):
    if type(value) is not int or not 0 <= value <= 0xffff:
        raise ValueError('%s must be a 16-bit controller word' % name)
    return value


def verify_logo_elf(data):
    """Check the exact EU-beta binary and critical control words.

    Program PT_LOAD layout of the supported binary places EE VA 0x100000
    at file offset 0x80. No ELF bytes are stored with the implementation.
    """
    if type(data) is not bytes or hashlib.sha256(data).hexdigest() != ELF_SHA256:
        raise ValueError('expected the exact EU-beta SLES_541.61 ELF')

    checks = {
        # main update: +0xA4 phase; +0xAC float age
        0x41E8A4: (0xC48000AC, 0xffffffff),  # lwc1 f0, +0xac(a0)
        0x41E8B8: (0x10A20066, 0xffffffff),  # beq a1,v0, state 10
        0x41E900: (0x820200A2, 0xffffffff),  # lb v0,+0xa2(s0)
        0x41E94C: (0x24420001, 0xffffffff),  # phase++
        0x41EA10: (0x3C023DAA, 0xffffffff),  # phase-5 threshold hi
        0x41EA14: (0x3442AAAB, 0xffffffff),  # phase-5 threshold lo
        0x41EC10: (0x3C024000, 0xffffffff),  # 2-second threshold
        0x41EC58: (0x30420010, 0xffffffff),  # pad 0 bit 0x10
        0x41EC70: (0x30420010, 0xffffffff),  # pad 1 bit 0x10
    }
    for address, (expected, mask) in checks.items():
        offset = address - 0x100000 + 0x80
        actual = struct.unpack_from('<I', data, offset)[0]
        if (actual & mask) != (expected & mask):
            raise ValueError('unexpected logo instruction at EE 0x%08X' % address)
    return True


class c_logo_runtime:
    """Minimal stateful projection of CAppLogoMain 0x41E680/0x41E890.

    Returned 'finished' is the native update's V0, not an app switch.
    'audio_busy' is exactly the bool result of native 0x2C0C20;
    it does not mean the game is necessarily audible.
    """

    def __init__(self):
        self.m_phase = 0  # +0xA4, initialized at 0x41E6A4
        self.m_current_logo = 0  # +0xA1, initialized at 0x41E660
        self.m_next_logo = 0  # +0xA2, initialized at 0x41E660
        self.m_skip_latched = False  # +0xA0, initialized at 0x41E670
        self.m_age = _f32(0.0)  # +0xAC, initialized at 0x41E6A0
        self.m_finished = False
        self.m_updates = 0

    def begin(self):
        """Externally invoked phase callback 0x41E850, not a timer tick."""
        return [
            {'address': '0x2c0c90', 'arguments': [1]},
            {'address': '0x2c08a0', 'arguments': [1, 60, 1.0, -1.0]},
        ]

    def snapshot(self):
        return {
            'phase': self.m_phase,
            'current_logo': self.m_current_logo,
            'next_logo': self.m_next_logo,
            'skip_latched': self.m_skip_latched,
            'age_bits': struct.unpack('<I', struct.pack('<f', self.m_age))[0],
            'age_seconds': self.m_age,
            'finished': self.m_finished,
            'updates': self.m_updates,
        }

    def step(self, delta_seconds, audio_busy, controller0=0, controller1=0):
        """Execute one native update; only phases 0→1→2 can fall through.

        'delta_seconds' mirrors (this+0x28)->+0x04, not host wall time.
        The native skip-test reads bit 0x10 of both controller +0x22
        fields. Button identity is intentionally not assumed.
        """
        if isinstance(delta_seconds, bool) or not isinstance(delta_seconds, (int, float)):
            raise ValueError('delta_seconds must be finite and nonnegative')
        if not math.isfinite(delta_seconds) or delta_seconds < 0:
            raise ValueError('delta_seconds must be finite and nonnegative')
        if type(audio_busy) is not bool:
            raise ValueError('audio_busy must be a captured boolean result')
        _word16(controller0, 'controller0')
        _word16(controller1, 'controller1')
        if self.m_finished:
            raise ValueError('native logo update already returned completion')
        events = []
        self.m_updates += 1
        self.m_age = _f32(self.m_age + _f32(delta_seconds))

        if self.m_phase == 0:
            self.m_current_logo = self.m_next_logo
            self.m_next_logo = (self.m_next_logo + 1) % 3
            self.m_skip_latched = False
            self.m_age = _f32(0.0)
            self.m_phase = 1

        if self.m_phase == 1:
            if audio_busy:
                return {'finished': False, 'calls': events, 'snapshot': self.snapshot()}
            self.m_phase = 2
            self.m_age = _f32(0.0)

        if self.m_phase == 2:
            if controller0 & 0x10 or controller1 & 0x10:
                self.m_skip_latched = True
                self.m_phase = 3
            elif not self.m_age < LOGO_DURATION:
                self.m_phase = 3
            # 0x41E98C branches to the return even when the gate succeeds.
            # Phase 3 executes on the next update, not on this one.
            return {'finished': False, 'calls': events, 'snapshot': self.snapshot()}

        if self.m_phase == 3:
            if self.m_current_logo == 2:
                events.extend([
                    {'address': '0x2c0c90', 'arguments': [0]},
                    {'address': '0x2c08a0', 'arguments': [2, 60, -1.0, -1.0]},
                ])
                if self.m_skip_latched:
                    events.append({'address': '0x3e0b00', 'arguments': []})
                self.m_phase = 10
            else:
                if not self.m_skip_latched:
                    events.extend([
                        {'address': '0x2c0c90', 'arguments': [1]},
                        {'address': '0x2c08a0', 'arguments': [2, 60, -1.0, -1.0]},
                    ])
                self.m_phase = 4

        elif self.m_phase == 4:
            if not audio_busy:
                self.m_age = _f32(0.0)
                self.m_phase = 5
                # 0x41EA04 branches to return; phase 5 starts next tick.
            return {'finished': False, 'calls': events, 'snapshot': self.snapshot()}

        elif self.m_phase == 5:
            if not self.m_age < LOOP_PAUSE:
                self.m_phase = 0
                events.extend([
                    {'address': '0x2c0c90', 'arguments': [1]},
                    {'address': '0x2c08a0', 'arguments': [1, 60, -1.0, -1.0]},
                ])

        elif self.m_phase == 10:
            if not audio_busy:
                self.m_finished = True

        return {'finished': self.m_finished, 'calls': events,
                'snapshot': self.snapshot()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path,
                        help='JSON array of observed delta_seconds/audio_busy/controller words')
    parser.add_argument('--elf', type=Path, help='optionally verify matching user-owned EU-beta ELF')
    args = parser.parse_args()
    try:
        if args.elf is not None:
            verify_logo_elf(args.elf.read_bytes())
        steps = json.loads(args.input.read_text(encoding='utf-8'))
        if not isinstance(steps, list):
            raise ValueError('input must be a JSON list of per-update measurements')
        runtime = c_logo_runtime()
        output = {'format': 'ARIKA_EU_BETA_LOGO_TRACE',
                  'begin_calls': runtime.begin(), 'steps': []}
        for index, sample in enumerate(steps):
            if not isinstance(sample, dict):
                raise ValueError('step %d must be an object' % index)
            result = runtime.step(sample['delta_seconds'], sample['audio_busy'],
                                  sample.get('controller0', 0), sample.get('controller1', 0))
            output['steps'].append(result)
            if result['finished']:
                break
    except (OSError, ValueError, TypeError, KeyError, struct.error) as error:
        parser.error(str(error))
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
