"""EU-beta CAppTitleMain lifecycle, reconstructed from EE 0x003F8900.

Resources, renderer state and the external transition helper are not
simulated. Exact ELF validation is optional for user-owned game binaries.
No proprietary binary bytes or artwork are embedded here.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct

from arika_logo_runtime import ELF_SHA256


TITLE_CLASS_NAME = 'CAppTitleMain'
TITLE_CLASS_ADDRESS = 0x004D7F90
TITLE_RESOURCE = 'dis/d03/d03t0202'
TITLE_RESOURCE_ADDRESS = 0x004D7FB0
TITLE_BASE_VTABLE = 0x004F66D0
TITLE_PHASE_VTABLE = 0x004F66F8
TITLE_CONSTRUCTOR_ADDRESS = 0x003F86E0
TITLE_INIT_ADDRESS = 0x003F8740
TITLE_LOAD_ADDRESS = 0x003F8790
TITLE_BEGIN_ADDRESS = 0x003F88D0
TITLE_UPDATE_ADDRESS = 0x003F8900
TITLE_RELEASE_ADDRESS = 0x003F89F0
TITLE_CLOCK_RELEASE_ADDRESS = 0x003F8A50
TITLE_DRAW_ADDRESS = 0x003F8A90
TITLE_SOURCE_RECT = (0, 0, 512, 448)
TITLE_DEST_RECT = (0, 0, 512, 448)
TITLE_DURATION = 4.0
TITLE_DESTINATION_APP = 6
ELF_FILE_BIAS = 0xFFF80


def _f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def _word(data, address):
    offset = address - ELF_FILE_BIAS
    if offset < 0 or offset + 4 > len(data):
        raise ValueError('invalid ELF address 0x%08X' % address)
    return struct.unpack_from('<I', data, offset)[0]


def _cstring(data, address, max_length=64):
    offset = address - ELF_FILE_BIAS
    if offset < 0 or offset + max_length > len(data):
        raise ValueError('invalid ELF string address')
    data = data[offset:offset + max_length].split(b'\0', 1)
    if len(data) != 2:
        raise ValueError('unterminated native string')
    return data[0].decode('ascii')


def verify_title_elf(data):
    """Require the exact original EU-beta ELF and key instruction words."""
    if type(data) is not bytes or hashlib.sha256(data).hexdigest() != ELF_SHA256:
        raise ValueError('expected the exact EU-beta SLES_541.61 ELF')
    code_words = {
        0x3F86C0: 0x3C02004D,  # class-name getter
        0x3F86C8: 0x24427F90,
        0x3F86FC: 0x246366D0,  # base vtable
        0x3F8700: 0x244266F8,  # app phase vtable
        0x3F8754: 0xAE020028,  # clock pointer
        0x3F8760: 0xAE00002C,  # elapsed float
        0x3F8720: 0xAE000030,  # phase
        0x3F8724: 0xAE000034,  # loader phase
        0x3F8794: 0x2402000A,  # loader state 10
        0x3F87F0: 0x24A57FB0,  # resource name
        0x3F8804: 0x0C0BEE30,  # resource readiness
        0x3F8868: 0x24070200,  # sprite source width 512
        0x3F8874: 0x240801C0,  # source height 448
        0x3F8894: 0x240801C0,  # destination height 448
        0x3F8898: 0x2402000A,  # load complete
        0x3F88E0: 0x24040001,  # begin transition type
        0x3F88E4: 0x2405000F,  # begin 15
        0x3F8914: 0xC480002C,  # float32 age
        0x3F8918: 0x8C830030,  # update phase
        0x3F8954: 0x14400020,  # busy holds phase zero
        0x3F8970: 0x3C024080,  # exact float32 4.0 threshold
        0x3F8980: 0x45010015,  # only age > 4.0 continues
        0x3F8994: 0x24040002,  # fade type
        0x3F899C: 0x2405000F,  # fade 15
        0x3F89B4: 0xAE020030,  # next update phase
        0x3F89CC: 0x24050006,  # destination app ID 6
        0x3F89D4: 0x24020001,  # completion return
        0x3F8A94: 0x8C590040,  # draw sprite pointer
        0x3F8A9C: 0x8F390010,  # sprite virtual draw dispatch
    }
    for address, expected in code_words.items():
        if _word(data, address) != expected:
            raise ValueError('unexpected title instruction at 0x%08X' % address)
    if _cstring(data, TITLE_CLASS_ADDRESS) != TITLE_CLASS_NAME:
        raise ValueError('wrong title class identifier')
    if _cstring(data, TITLE_RESOURCE_ADDRESS) != TITLE_RESOURCE:
        raise ValueError('wrong title resource')

    vtable_entries = (
        0x3F8AC0, 0x3F8740, 0x3F8790, 0x3F88D0, 0x3F8900,
        0x3F89F0, 0x3DFAC0, 0x3F8A50, 0x3F8A90, 0x3DFAF0,
    )
    for index, expected in enumerate(vtable_entries):
        actual = _word(data, TITLE_PHASE_VTABLE + 8 + index * 4)
        if actual != expected:
            raise ValueError('unexpected title vtable entry %d' % index)

    return {
        'format': 'ARIKA_EU_BETA_TITLE_APPLICATION',
        'elf_sha256': ELF_SHA256,
        'class_name': TITLE_CLASS_NAME,
        'class_address': hex(TITLE_CLASS_ADDRESS),
        'base_vtable': hex(TITLE_BASE_VTABLE),
        'phase_vtable': hex(TITLE_PHASE_VTABLE),
        'callbacks': {
            'construct': hex(TITLE_CONSTRUCTOR_ADDRESS),
            'init': hex(TITLE_INIT_ADDRESS),
            'load': hex(TITLE_LOAD_ADDRESS),
            'begin': hex(TITLE_BEGIN_ADDRESS),
            'update': hex(TITLE_UPDATE_ADDRESS),
            'release': hex(TITLE_RELEASE_ADDRESS),
            'clock_release': hex(TITLE_CLOCK_RELEASE_ADDRESS),
            'draw': hex(TITLE_DRAW_ADDRESS),
        },
        'resource': {
            'name': TITLE_RESOURCE,
            'string_address': hex(TITLE_RESOURCE_ADDRESS),
            'wrapper_offset': '0x38',
            'sprite_offset': '0x40',
            'source_rect': list(TITLE_SOURCE_RECT),
            'destination_rect': list(TITLE_DEST_RECT),
        },
        'update': {
            'phase_offset': '0x30',
            'elapsed_float_offset': '0x2c',
            'native_threshold_seconds': TITLE_DURATION,
            'next_application_id': TITLE_DESTINATION_APP,
            'completion_requires_external_ready': True,
        },
        'limitations': [
            'No native GS state, alpha, filtering, video scan mode or actual framebuffer was captured.',
            'External 0x2C0C20 readiness is an input, not emulated audio.',
            'App ID 6 is a numeric native argument, not an inferred application class name.',
        ],
    }


def _call(address, arguments):
    return {'address': address, 'arguments': arguments}


class c_title_runtime:
    """Native title updater; Play/Pause scheduling belongs in the Qt view."""

    def __init__(self):
        self.m_phase = 0
        self.m_elapsed = _f32(0.0)
        self.m_finished = False
        self.m_updates = 0
        self.m_loader_phase = 0
        self.m_loader_updates = 0

    def begin(self):
        """Native start callback 0x3F88D0."""
        return [_call('0x2c08a0', [1, 15, -1.0, -1.0])]

    def load_step(self, resource_ready=False):
        """Native 0x3F8790 loader: 0 allocate, 1 poll, 10 ready."""
        if type(resource_ready) is not bool:
            raise ValueError('resource_ready must be a captured boolean')
        self.m_loader_updates += 1
        # 0x3F88AC returns zero even on the tick that switches 1 -> 10.
        # Only the following call enters native state 10 and returns one.
        ready_on_entry = self.m_loader_phase == 10
        calls = []
        if self.m_loader_phase == 0:
            calls += [
                _call('0x1110c0', [12]),
                _call('0x2fb9b0', []),
                _call('0x2fb850', [TITLE_RESOURCE]),
            ]
            self.m_loader_phase = 1
        elif self.m_loader_phase == 1 and resource_ready:
            calls += [
                _call('0x2fd910', [1]),
                _call('0x2fb960', []),
                _call('0x2fd8f0', []),
                _call('sprite_set_source_rect', list(TITLE_SOURCE_RECT)),
                _call('sprite_set_dest_rect', list(TITLE_DEST_RECT)),
            ]
            self.m_loader_phase = 10
        return {
            'ready': ready_on_entry,
            'calls': calls,
            'loader_phase': self.m_loader_phase,
        }

    def snapshot(self):
        return {
            'phase': self.m_phase,
            'elapsed_seconds': self.m_elapsed,
            'elapsed_bits': struct.unpack('<I', struct.pack('<f', self.m_elapsed))[0],
            'finished': self.m_finished,
            'updates': self.m_updates,
            'loader_phase': self.m_loader_phase,
            'loader_updates': self.m_loader_updates,
        }

    def step(self, delta_seconds, transition_busy):
        """Execute one call to 0x3F8900 with externally observed inputs."""
        if type(delta_seconds) not in (int, float):
            raise ValueError('delta_seconds must be a finite nonnegative number')
        if not math.isfinite(delta_seconds) or delta_seconds < 0:
            raise ValueError('delta_seconds must be a finite nonnegative number')
        if type(transition_busy) is not bool:
            raise ValueError('transition_busy must be a captured boolean result')
        if self.m_finished:
            raise ValueError('native title update already returned completion')

        self.m_updates += 1
        self.m_elapsed = _f32(self.m_elapsed + _f32(delta_seconds))
        calls = []

        if self.m_phase == 0:
            if not transition_busy:
                self.m_phase = 1
            # 0x3F8964 branches to return. Phase 1 executes next update.

        elif self.m_phase == 1:
            if self.m_elapsed > TITLE_DURATION:
                calls += [
                    _call('0x2c0c90', [0]),
                    _call('0x2c08a0', [2, 15, -1.0, -1.0]),
                ]
                self.m_phase = 2

        elif self.m_phase == 2 and not transition_busy:
            calls += [_call('0x3dfb00', [TITLE_DESTINATION_APP])]
            self.m_finished = True

        return {
            'finished': self.m_finished,
            'calls': calls,
            'snapshot': self.snapshot(),
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path, help='original EU-beta SLES_541.61 ELF')
    parser.add_argument('--steps', type=Path,
                        help='optional JSON list of delta_seconds/transition_busy')
    args = parser.parse_args()
    try:
        report = verify_title_elf(args.elf.read_bytes())
        if args.steps is not None:
            samples = json.loads(args.steps.read_text(encoding='utf-8'))
            if not isinstance(samples, list):
                raise ValueError('steps must be a JSON array')
            runtime = c_title_runtime()
            report['begin_calls'] = runtime.begin()
            report['steps'] = []
            for sample in samples:
                if not isinstance(sample, dict):
                    raise ValueError('sample must be a JSON object')
                state = runtime.step(sample['delta_seconds'],
                                     sample['transition_busy'])
                report['steps'].append(state)
                if state['finished']:
                    break
    except (OSError, ValueError, KeyError, OverflowError, struct.error) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
