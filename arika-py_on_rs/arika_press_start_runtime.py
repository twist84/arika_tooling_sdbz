"""EU-beta Press Start application (ID 3), native EE reconstruction.

The original game registers another CAppTitleMain at ID 2. ID 3
uses constructor 0x3F7150 and update 0x3F76A0, not the timed
four-second title splash. All external game helpers are explicit
diagnostic observations or unexecuted event records.

Source executable: EU-beta SLES_541.61, SHA-256 in arika_logo_runtime.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct

from arika_logo_runtime import ELF_SHA256
from arika_app_registry import _word, resolve_app


PRESS_START_APP_ID = 3
PRESS_START_CLASS = 'CAppTitleMain'
PRESS_START_CONSTRUCTOR = 0x003F7150
PRESS_START_INIT = 0x003F71E0
PRESS_START_LOAD = 0x003F7320
PRESS_START_BEGIN = 0x003F7680
PRESS_START_UPDATE = 0x003F76A0
PRESS_START_RELEASE = 0x003F79A0
PRESS_START_DRAW = 0x003F7AA0
PRESS_START_BASE_VTABLE = 0x004F6670
PRESS_START_PHASE_VTABLE = 0x004F6698
PRESS_START_RESOURCE_GROUPS = (2, 3, 4, 5, 7, 8, 10, 11, 15)
PRESS_START_TEXTURE_SIZE = (512, 448)
PRESS_START_BUTTON_BIT = 0x10
PRESS_START_ONE_SHOT_SECONDS = 1.0
PRESS_START_IDLE_SECONDS = 20.0
PRESS_START_ACCEPT_APP_ID = 42
PRESS_START_ATTRACT_APP_ID = 6
PRESS_START_SOUND_KEY = 'snd/etceff'
PRESS_START_SOUND_KEY_ADDR = 0x004D7F80

PHASE_WAIT_FOR_START = 0
PHASE_START_TRANSITION = 1
PHASE_START_WAIT = 2
PHASE_ATTRACT_WAIT = 10

# Original binary word checks are deliberately anchored at control
# sites, not an unverified inferred animation or guessed duration.
PRESS_START_WORDS = {
    0x3F716C: 0x24636670,  # separate ID-3 base vtable
    0x3F7170: 0x24426698,  # separate ID-3 phase vtable
    0x3F71A4: 0xAE000028,  # clock initially null
    0x3F71B0: 0xAE000030,  # additional per-app field initially zero
    0x3F7334: 0x80830034,  # loader state byte
    0x3F7374: 0x0C0BEED8,  # 0x2FBB60
    0x3F7384: 0x0C0BEF70,  # resource group registration
    0x3F73C8: 0x2404000F,  # last group 15
    0x3F7404: 0x0C0BEFAC,  # group readiness 0x2FBEB0
    0x3F744C: 0x0C0BEF8C,  # resource-group readiness 0x2FBE30
    0x3F74E4: 0x8F390020,  # 512x448 sprite source/dest
    0x3F75CC: 0x8F390020,  # third sprite
    0x3F75E8: 0x24060061,  # third sprite subrectangle
    0x3F7610: 0x3C02BF80,  # startup fade
    0x3F7660: 0xA2000034,  # loader phase reset
    0x3F7688: 0x0C0FAE18,  # 0x3EB860(0) begin
    0x3F76AC: 0x8C830028,  # clock pointer at this+0x28
    0x3F76B0: 0xC480002C,  # elapsed age this+0x2C
    0x3F76B4: 0x90820036,  # one-shot latch at this+0x36
    0x3F76C8: 0xE480002C,  # float32 age write
    0x3F76CC: 0x3C023F80,  # 1.0f
    0x3F76D8: 0x460C0034,  # age < 1.0f check
    0x3F7740: 0xA2020036,  # set one-shot latch
    0x3F7750: 0x82030034,  # transition phase at +0x34
    0x3F7754: 0x2402000A,  # phase 10
    0x3F7798: 0x30420010,  # controller0 Start bit
    0x3F77A8: 0x0C0FAC10,  # 0x3EB040
    0x3F77E8: 0x0C0B0324,  # 0x2C0C90
    0x3F7800: 0x0C0B0228,  # 0x2C08A0
    0x3F7818: 0x0C0B0228,
    0x3F7858: 0x0C0B0308,  # transition busy poll
    0x3F786C: 0x0C0F7EC0,  # request app 42
    0x3F787C: 0x0C0B0308,  # attract transition busy
    0x3F7898: 0x0C0F7EC0,  # request app 6
    0x3F789C: 0x24050006,
    0x3F78BC: 0x0C0ABEB4,  # second controller eligibility
    0x3F78D0: 0x94420022,  # second controller input word
    0x3F78D4: 0x30420010,
    0x3F7928: 0x0C0ABF4C,  # idle timer reset helper
    0x3F7938: 0xC601002C,  # elapsed age
    0x3F7940: 0x44820000,  # 20.0f
    0x3F7948: 0x46000834,  # age < 20.0f
    0x3F7954: 0x0C0B0324,  # attract fade
    0x3F7984: 0xAE00002C,  # reset elapsed age
    0x3F7AB4: 0x24070200,  # draw 512 width
    0x3F7ABC: 0x240801C0,  # draw 448 height
}
PHASE_VTABLE_ENTRIES = (
    0x3F86D0, 0x3F71E0, 0x3F7320, 0x3F7680, 0x3F76A0,
    0x3F79A0, 0x3F7A80, 0x3F7A90, 0x3F7AA0, 0x3F86B0,
)


def _f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def _call(address, arguments=None, **metadata):
    result = {
        'address': address,
        'arguments': [] if arguments is None else arguments,
        'executed': False,
    }
    result.update(metadata)
    return result


def verify_press_start_elf(elf):
    """Fail closed if a different region, build, or code layout is supplied."""
    if type(elf) is not bytes or hashlib.sha256(elf).hexdigest() != ELF_SHA256:
        raise ValueError('expected exact Super Dragon Ball Z EU-beta ELF')
    app = resolve_app(PRESS_START_APP_ID)
    if app is None or app['constructor'] != PRESS_START_CONSTRUCTOR:
        raise ValueError('app registry does not identify Press Start ID 3')
    for addr, expected in PRESS_START_WORDS.items():
        if _word(elf, addr) != expected:
            raise ValueError('Press Start instruction mismatch at 0x%08X' % addr)
    for index, value in enumerate(PHASE_VTABLE_ENTRIES):
        if _word(elf, PRESS_START_PHASE_VTABLE + 8 + index * 4) != value:
            raise ValueError('Press Start phase vtable mismatch at %d' % index)
    offset = PRESS_START_SOUND_KEY_ADDR - 0xFFF80
    if elf[offset:offset + len(PRESS_START_SOUND_KEY) + 1] != (
            PRESS_START_SOUND_KEY.encode('ascii') + b'\0'):
        raise ValueError('Press Start original sound key changed')
    return {
        'format': 'ARIKA_EU_BETA_PRESS_START',
        'elf_sha256': ELF_SHA256,
        'app_id': PRESS_START_APP_ID,
        'class': PRESS_START_CLASS,
        'constructor': hex(PRESS_START_CONSTRUCTOR),
        'phase_vtable': hex(PRESS_START_PHASE_VTABLE),
        'callbacks': {
            'init': hex(PRESS_START_INIT),
            'load': hex(PRESS_START_LOAD),
            'begin': hex(PRESS_START_BEGIN),
            'update': hex(PRESS_START_UPDATE),
            'release': hex(PRESS_START_RELEASE),
            'draw': hex(PRESS_START_DRAW),
        },
        'sprite_canvas': list(PRESS_START_TEXTURE_SIZE),
        'loader_groups': list(PRESS_START_RESOURCE_GROUPS),
        'button_bit': PRESS_START_BUTTON_BIT,
        'one_shot_threshold': PRESS_START_ONE_SHOT_SECONDS,
        'idle_threshold': PRESS_START_IDLE_SECONDS,
        'start_target_id': PRESS_START_ACCEPT_APP_ID,
        'attract_target_id': PRESS_START_ATTRACT_APP_ID,
        'verified_words': len(PRESS_START_WORDS),
        'limitations': [
            'Screen visuals depend on original streamed resources/GS state.',
            'The two uploaded PCSX2 captures are reference images, not decoded game textures.',
            'No native prompt blink cycle is asserted without frame or GS evidence.',
            'Native readiness and controller words are supplied diagnostic inputs.',
        ],
    }


class c_press_start_runtime:
    """Deterministic native app-ID-3 update (0x3F76A0), without host effects."""

    def __init__(self):
        self.m_phase = PHASE_WAIT_FOR_START
        self.m_elapsed = _f32(0)
        self.m_one_shot = False
        self.m_finished = False
        self.m_updates = 0
        self.m_destination = None
        self.m_loader_phase = 0
        self.m_loader_updates = 0
        self.m_loader_ready = False

    def begin(self):
        return [_call('0x3eb860', [0])]

    def snapshot(self):
        return {
            'phase': self.m_phase,
            'elapsed_seconds': self.m_elapsed,
            'elapsed_bits': struct.unpack('<I', struct.pack('<f', self.m_elapsed))[0],
            'one_shot': self.m_one_shot,
            'finished': self.m_finished,
            'updates': self.m_updates,
            'destination_id': self.m_destination,
            'loader_phase': self.m_loader_phase,
            'loader_ready': self.m_loader_ready,
            'loader_updates': self.m_loader_updates,
        }

    def load_step(self, group_ready=False, stage_ready=False,
                  sprite_ready=False):
        """Native loader phases 0→1→2→3→4; helper outcomes are external."""
        if any(type(value) is not bool for value in (
                group_ready, stage_ready, sprite_ready)):
            raise ValueError('loader observations must be booleans')
        self.m_loader_updates += 1
        calls = []
        if self.m_loader_phase == 0:
            calls = [_call('0x2fbb60'), _call('0x2fcba0')]
            calls += [_call('0x2fbdc0', [g]) for g in PRESS_START_RESOURCE_GROUPS]
            self.m_loader_phase = 1
        elif self.m_loader_phase == 1:
            calls = [_call('0x2fbeb0', [], observed_result=group_ready)]
            if group_ready:
                calls += [_call('0x2fbcc0', [7, PRESS_START_SOUND_KEY]),
                          _call('0x32a510'), _call('0x32a7a0'),
                          _call('0x2fbcc0', [8])]
                self.m_loader_phase = 2
        elif self.m_loader_phase == 2:
            calls = [_call('0x2fbe30', [16], observed_result=stage_ready)]
            if stage_ready:
                self.m_loader_phase = 3
        elif self.m_loader_phase == 3:
            calls = [_call('0x3ef6c0', [], observed_result=sprite_ready)]
            if sprite_ready:
                calls += [
                    _call('0x2fd910', [1]),
                    _call('0x2fb960'),
                    _call('0x2fd8f0'),
                    _call('sprite_set_source_dest', [512, 448]),
                ] * 3
                self.m_loader_phase = 4
        elif self.m_loader_phase == 4:
            calls = [_call('0x2c08a0', [1, 15, -1.0, -1.0])]
            self.m_loader_phase = 0
            self.m_loader_ready = True
        return {
            'ready': self.m_loader_ready,
            'calls': calls,
            'snapshot': self.snapshot(),
        }

    def step(self, delta_seconds, transition_busy=False,
             controller0=0, controller1=0, controller0_ready=True,
             controller1_ready=True, idle_reset=False):
        if (type(delta_seconds) not in (int, float) or
                not math.isfinite(delta_seconds) or delta_seconds < 0):
            raise ValueError('delta_seconds must be finite and nonnegative')
        if any(type(x) is not bool for x in (
                transition_busy, controller0_ready, controller1_ready,
                idle_reset)):
            raise ValueError('readiness observations must be boolean')
        if (any(type(x) is not int or x < 0 or x > 0xffff
                for x in (controller0, controller1))):
            raise ValueError('controller words must be unsigned 16-bit integers')
        if self.m_finished:
            raise ValueError('Press Start application has already completed')

        self.m_updates += 1
        self.m_elapsed = _f32(self.m_elapsed + _f32(delta_seconds))
        calls = []

        if not self.m_one_shot and self.m_elapsed >= PRESS_START_ONE_SHOT_SECONDS:
            # Native 0x3F76CC..0x3F7740: one-shot helper/audio branch.
            calls.append(_call('0x2fc840', [8],
                               native_site='0x3f7734'))
            self.m_one_shot = True

        # 0x3F85A0 observes a separate global input sequence. Its
        # side-effects aren't reproduced; this event is trace-only.
        calls.append(_call('0x3f85a0'))

        if self.m_phase == PHASE_WAIT_FOR_START:
            selected_controller = None
            if controller0_ready and (controller0 & PRESS_START_BUTTON_BIT):
                selected_controller = 0
            elif controller1_ready and (controller1 & PRESS_START_BUTTON_BIT):
                selected_controller = 1

            if selected_controller is not None:
                calls.extend([
                    _call('0x3eb040', [selected_controller, 1]),
                    _call('0x3f55f0'),
                    _call('0x2fc990', [7, 13]),
                    _call('0x2e4b30'),
                    _call('0x2e5570', [0]),
                ])
                self.m_phase = PHASE_START_TRANSITION
            else:
                calls.append(_call('0x2afd30', [0, 2],
                                   observed_result=idle_reset))
                if idle_reset:
                    self.m_elapsed = _f32(0.0)
                elif self.m_elapsed >= PRESS_START_IDLE_SECONDS:
                    calls.extend([
                        _call('0x2c0c90', [0]),
                        _call('0x2c08a0', [2, 15, -1.0, -1.0]),
                    ])
                    self.m_phase = PHASE_ATTRACT_WAIT

        elif self.m_phase == PHASE_START_TRANSITION:
            calls.extend([
                _call('0x2c0c90', [0]),
                _call('0x2c08a0', [0, 0, -1.0, -1.0]),
                _call('0x2c08a0', [2, 3, 0.0, -1.0]),
            ])
            self.m_phase = PHASE_START_WAIT

        elif self.m_phase == PHASE_START_WAIT:
            calls.append(_call('0x2c0c20', [],
                               observed_result=transition_busy))
            if not transition_busy:
                calls.append(_call('0x3dfb00', [PRESS_START_ACCEPT_APP_ID]))
                self.m_destination = PRESS_START_ACCEPT_APP_ID
                self.m_finished = True

        elif self.m_phase == PHASE_ATTRACT_WAIT:
            calls.append(_call('0x2c0c20', [],
                               observed_result=transition_busy))
            if not transition_busy:
                calls.extend([
                    _call('0x3e0b10', [2]),
                    _call('0x3dfb00', [PRESS_START_ATTRACT_APP_ID]),
                ])
                self.m_destination = PRESS_START_ATTRACT_APP_ID
                self.m_finished = True

        return {
            'finished': self.m_finished,
            'calls': calls,
            'snapshot': self.snapshot(),
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('elf', type=Path)
    parser.add_argument('--steps', type=Path,
                        help='optional JSON array of native update inputs')
    args = parser.parse_args()
    try:
        report = verify_press_start_elf(args.elf.read_bytes())
        if args.steps:
            entries = json.loads(args.steps.read_text(encoding='utf-8'))
            if not isinstance(entries, list):
                raise ValueError('steps must be a JSON array')
            runtime = c_press_start_runtime()
            report['begin_events'] = runtime.begin()
            report['steps'] = []
            for entry in entries:
                result = runtime.step(**entry)
                report['steps'].append(result)
                if result['finished']:
                    break
    except (OSError, ValueError, KeyError, OverflowError, struct.error) as error:
        parser.error(str(error))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
