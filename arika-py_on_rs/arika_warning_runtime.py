"""EU-beta CAppWarning app state recovered from SLES_541.61.

Native addresses are verified against the exact EU beta ELF via
recover_warning_elf(). External 0x2C0C20 readiness, rendering and
video-mode/system callbacks are INPUTS or event markers, not emulated.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct

from arika_logo_runtime import ELF_SHA256, _f32


WARNING_RESOURCE = 'dis/d03/d03t0801'
WARNING_RESOURCE_ADDRESS = 0x004D9230
WARNING_OPTIONS = (' 50Hz', ' 60Hz', ' TEST', 'To Game')
WARNING_LABEL_POINTER_TABLE = 0x004B4780
WARNING_LABEL_ADDRESSES = (0x004D9248, 0x004D9250, 0x004D9258, 0x004D9260)
WARNING_SOURCE_RECT = (0, 0, 512, 448)
WARNING_DEST_RECT = (0, 0, 512, 448)
WARNING_UPDATE_ADDRESS = 0x0041EF00
WARNING_LOAD_ADDRESS = 0x0041EDB0
WARNING_DRAW_ADDRESS = 0x0041F310
WARNING_TEST_SECONDS = 5.0
ELF_FILE_BIAS = 0xFFF80

# Native phase IDs, not a sequential authored timeline.
PHASE_INITIAL = 0
PHASE_WAIT_BEGIN = 1
PHASE_SELECTION = 2
PHASE_EXIT_START = 3
PHASE_EXIT_WAIT = 4
PHASE_VIDEO_MODE = 10
PHASE_TEST_FADE_OUT = 20
PHASE_TEST_WAIT_OUT = 21
PHASE_TEST_WAIT_IN = 22
PHASE_TEST_DISPLAY = 23
PHASE_TEST_FADE_BACK = 24

PAD_NEXT = 0x2
PAD_PREVIOUS = 0x1
PAD_CONFIRM = 0x80


def _word(elf, address):
    offset = address - ELF_FILE_BIAS
    if offset < 0 or offset + 4 > len(elf):
        raise ValueError('unmapped ELF address 0x%08X' % address)
    return struct.unpack_from('<I', elf, offset)[0]


def _string(elf, address):
    offset = address - ELF_FILE_BIAS
    if offset < 0 or offset + 64 > len(elf):
        raise ValueError('unmapped ELF string at 0x%08X' % address)
    raw = elf[offset:offset + 64].split(b'\0', 1)
    if len(raw) != 2:
        raise ValueError('unterminated ELF warning label')
    return raw[0].decode('ascii')


def recover_warning_elf(elf):
    """Verify native code and recover the exact resource/choice strings."""
    if type(elf) is not bytes or hashlib.sha256(elf).hexdigest() != ELF_SHA256:
        raise ValueError('expected the exact EU beta SLES_541.61 ELF')

    checks = {
        0x41ECC0: 0x244272D8,  # warning phase vtable
        0x41EE10: 0x24A59230,  # resource key address
        0x41EE88: 0x24070200,  # source width=512
        0x41EE94: 0x240801C0,  # source height=448
        0x41EEA8: 0x24070200,  # destination width=512
        0x41EEB4: 0x240801C0,  # destination height=448
        0x41EF18: 0x8C830030,  # phase at +0x30
        0x41EFC4: 0x94430022,  # controller word +0x22
        0x41EFC8: 0x30620002,  # next option
        0x41EFD0: 0x30620001,  # previous option
        0x41EFDC: 0x30620080,  # confirm
        0x41F180: 0xAE02002C,  # 5.0f countdown
        0x41F1A0: 0x46020841,  # countdown -= delta
        0x41F1A8: 0x4500001E,  # only negative countdown passes
        0x41F240: 0x30620003,  # modulo-four movement
        0x41F268: 0x30620003,
        0x41F380: 0x8E830038,  # warning image draw flag
    }
    for address, expected in checks.items():
        if _word(elf, address) != expected:
            raise ValueError('warning instruction mismatch at 0x%08X' % address)
    if _string(elf, WARNING_RESOURCE_ADDRESS) != WARNING_RESOURCE:
        raise ValueError('native warning resource mismatch')
    pointers = tuple(_word(elf, WARNING_LABEL_POINTER_TABLE + index * 4)
                     for index in range(4))
    if pointers != WARNING_LABEL_ADDRESSES:
        raise ValueError('native warning label pointers changed')
    labels = tuple(_string(elf, ptr) for ptr in pointers)
    if labels != WARNING_OPTIONS:
        raise ValueError('native warning labels changed')

    return {
        'format': 'ARIKA_EU_BETA_WARNING_SCREEN',
        'elf_sha256': ELF_SHA256,
        'callbacks': {
            'begin': '0x41ed10',
            'load': '0x41edb0',
            'update': '0x41ef00',
            'release': '0x41f2a0',
            'draw': '0x41f310',
        },
        'resource': {
            'name': WARNING_RESOURCE,
            'address': hex(WARNING_RESOURCE_ADDRESS),
            'wrapper_offset': '0x40',
            'source_rect': list(WARNING_SOURCE_RECT),
            'destination_rect': list(WARNING_DEST_RECT),
        },
        'choice_table': [
            {'index': index, 'address': hex(address), 'text': label}
            for index, (address, label) in enumerate(zip(pointers, labels))
        ],
        'input_mask': {
            'next': PAD_NEXT, 'previous': PAD_PREVIOUS, 'confirm': PAD_CONFIRM,
        },
        'state': {
            'phase_offset': '0x30', 'selection_offset': '0x34',
            'image_flag_offset': '0x38',
            'loader_phase_offset': '0x3c', 'countdown_offset': '0x2c',
            'test_duration_float': WARNING_TEST_SECONDS,
        },
        'limitations': [
            'No PS2 render state or font atlas is captured.',
            'Video-mode and app switch calls are event markers only.',
            'External 0x2c0c20 ready/busy signal is user supplied.',
            'Native choice text and input masks are not a controller-layout guess.',
        ],
    }


def _event(address, arguments=None, **observed):
    entry = {'address': address, 'arguments': arguments or []}
    if observed:
        entry['observed'] = observed
    return entry


class c_warning_runtime:
    """Native phase decisions; no implicit Qt or game-global state."""

    def __init__(self):
        self.m_phase = PHASE_INITIAL
        self.m_selection = 0
        self.m_image_visible = False
        self.m_countdown = _f32(0)
        self.m_finished = False
        self.m_updates = 0

    def begin(self):
        return [
            _event('0x2c0c90', [0]),
            _event('0x2c08a0', [1, 15, 0.0, -1.0]),
        ]

    def snapshot(self):
        return {
            'phase': self.m_phase,
            'selection': self.m_selection,
            'choice_text': WARNING_OPTIONS[self.m_selection],
            'image_visible': self.m_image_visible,
            'countdown_seconds': self.m_countdown,
            'countdown_bits': struct.unpack('<I', struct.pack('<f', self.m_countdown))[0],
            'finished': self.m_finished,
            'updates': self.m_updates,
        }

    def step(self, delta_seconds, busy, controller0=0):
        if (type(delta_seconds) not in (float, int) or
                not math.isfinite(delta_seconds) or delta_seconds < 0):
            raise ValueError('delta_seconds must be finite and nonnegative')
        if type(busy) is not bool:
            raise ValueError('busy must be the captured 0x2c0c20 boolean')
        if type(controller0) is not int or not 0 <= controller0 <= 0xffff:
            raise ValueError('controller0 must be a 16-bit unsigned word')
        if self.m_finished:
            raise ValueError('native warning update already returned completion')
        dt = _f32(delta_seconds)
        events = []
        self.m_updates += 1

        if self.m_phase == PHASE_INITIAL:
            self.m_selection = 0
            self.m_image_visible = False
            self.m_phase = PHASE_WAIT_BEGIN
            # 0x41EF9C falls directly into 0x41EFA0 in this same call.

        if self.m_phase == PHASE_WAIT_BEGIN:
            if not busy:
                self.m_phase = PHASE_SELECTION

        elif self.m_phase == PHASE_SELECTION:
            # First matching input branch wins, per 0x41EFC8..0x41EFE4.
            if controller0 & PAD_NEXT:
                self.m_selection = (self.m_selection + 1) & 3
            elif controller0 & PAD_PREVIOUS:
                self.m_selection = (self.m_selection + 3) & 3
            elif controller0 & PAD_CONFIRM:
                self.m_phase = (
                    PHASE_VIDEO_MODE if self.m_selection < 2 else
                    PHASE_TEST_FADE_OUT if self.m_selection == 2 else
                    PHASE_EXIT_START)

        elif self.m_phase == PHASE_VIDEO_MODE:
            # The real calls change game-global video state. Record but
            # do not apply them to the host/editor.
            hz = 50.0 if self.m_selection == 0 else 60.0
            height = 512 if self.m_selection == 0 else 448
            mode = 0x36 if self.m_selection == 0 else 0x35
            events += [
                _event('0x1bf560', [hz]),
                _event('0x1998a0', [], width=512, height=height,
                       mode_selector=mode),
            ]
            self.m_phase = PHASE_SELECTION

        elif self.m_phase == PHASE_EXIT_START:
            events += [
                _event('0x2c0c90', [0]),
                _event('0x2c08a0', [2, 60, -1.0, -1.0]),
            ]
            self.m_phase = PHASE_EXIT_WAIT

        elif self.m_phase == PHASE_EXIT_WAIT:
            if not busy:
                events.append(_event('0x3dfb00', [1]))
                self.m_finished = True

        elif self.m_phase == PHASE_TEST_FADE_OUT:
            events += [
                _event('0x2c0c90', [0]),
                _event('0x2c08a0', [2, 30, -1.0, -1.0]),
            ]
            self.m_phase = PHASE_TEST_WAIT_OUT

        elif self.m_phase == PHASE_TEST_WAIT_OUT:
            if not busy:
                self.m_image_visible = True
                events += [
                    _event('0x2c0c90', [0]),
                    _event('0x2c08a0', [1, 30, -1.0, -1.0]),
                ]
                self.m_phase = PHASE_TEST_WAIT_IN

        elif self.m_phase == PHASE_TEST_WAIT_IN:
            if not busy:
                self.m_countdown = _f32(WARNING_TEST_SECONDS)
                self.m_phase = PHASE_TEST_DISPLAY

        elif self.m_phase == PHASE_TEST_DISPLAY:
            self.m_countdown = _f32(self.m_countdown - dt)
            if self.m_countdown < 0.0:
                self.m_countdown = _f32(0.0)
                events += [
                    _event('0x2c0c90', [0]),
                    _event('0x2c08a0', [2, 30, 0.0, -1.0]),
                ]
                self.m_phase = PHASE_TEST_FADE_BACK

        elif self.m_phase == PHASE_TEST_FADE_BACK:
            if not busy:
                self.m_image_visible = False
                events += [
                    _event('0x2c0c90', [0]),
                    _event('0x2c08a0', [1, 30, 0.0, -1.0]),
                ]
                self.m_phase = PHASE_WAIT_BEGIN

        return {
            'finished': self.m_finished,
            'events': events,
            'snapshot': self.snapshot(),
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--steps', type=Path,
                        help='optional JSON list with delta_seconds, busy, controller0')
    args = parser.parse_args()
    try:
        report = recover_warning_elf(args.elf.read_bytes())
        if args.steps is not None:
            samples = json.loads(args.steps.read_text(encoding='utf-8'))
            if not isinstance(samples, list):
                raise ValueError('--steps expects a JSON list')
            runtime = c_warning_runtime()
            report['begin_events'] = runtime.begin()
            report['steps'] = []
            for sample in samples:
                if not isinstance(sample, dict):
                    raise ValueError('each step must be an object')
                result = runtime.step(sample['delta_seconds'], sample['busy'],
                                      sample.get('controller0', 0))
                report['steps'].append(result)
                if result['finished']:
                    break
    except (OSError, ValueError, KeyError, OverflowError, struct.error) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
