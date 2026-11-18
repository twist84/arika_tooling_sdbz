"""EU-beta CAppDemoMain (factory ID 6) native update projection.

This is the EE 0x003E0830 dispatch state machine, not the other
CAppDemoMain constructor registered under app ID 8.

External child presence (this+0x2C), 0x3DFC60 completion result and
the global -0xFD4($gp) exit flag are explicit diagnostic inputs.
Calls are trace entries, NOT executed in the host editor.
"""
import hashlib
import struct

from arika_app_registry import (
    DEMO_MAIN_CHILD_CHOICES, DEMO_MAIN_CHOICE_SITES, APP_CHILD_REQUEST,
    APP_TRANSITION_REQUEST, resolve_app, _word,
)
from arika_logo_runtime import ELF_SHA256


DEMO_MAIN_UPDATE_ADDRESS = 0x003E0830
DEMO_MAIN_BEGIN_ADDRESS = 0x003E07F0
DEMO_MAIN_WAIT_HELPER = 0x003DFC60
DEMO_MAIN_INITIAL_RETURN_APP = 3

# Actual words in the verified EU-beta ELF, covering the decision sites
# rather than assuming a selected child from an app name or screenshot.
UPDATE_WORDS = {
    0x3E0840: 0x8C84002C,  # this+0x2c child/service pointer
    0x3E0850: 0x8F390018,  # virtual +0x18 when present
    0x3E0864: 0x0C0FAE18,  # no-child path -> 0x3EB860
    0x3E0874: 0xA2030028,  # this+0x28 = this+0x29
    0x3E08A8: 0xA2020029,  # choice 0 sets next=1
    0x3E08B4: 0x24050004,  # ID 4
    0x3E08C0: 0xA2030029,  # choice 1 sets next=2
    0x3E08CC: 0x24050007,  # ID 7
    0x3E08D8: 0xA2020029,  # choice 2 sets next=3
    0x3E08E4: 0x24050008,  # ID 8
    0x3E08F4: 0x24050009,  # ID 9
    0x3E08FC: 0xA2000029,  # choice 3 wraps next to 0 (delay slot)
    0x3E0904: 0x24420001,  # update phase increments to 1
    0x3E0908: 0xAE020030,  # this+0x30
    0x3E090C: 0x0C0F7F18,  # 0x3DFC60 child-pending predicate
    0x3E0914: 0x14400019,  # pending -> skip completion handling
    0x3E091C: 0x92030028,  # prior choice
    0x3E0924: 0x10620011,  # prior 3: return to app 6
    0x3E0928: 0x24020006,  # app 6 for prior choice 3
    0x3E0930: 0x1062000C,  # prior 2: reset phase
    0x3E0938: 0x10620007,  # prior 1: set exit global
    0x3E0958: 0xAE000030,  # prior 1 resets phase
    0x3E0964: 0x10000005,  # prior 2 resets phase
    0x3E096C: 0xAE000030,  # prior 3 resets phase
    0x3E0970: 0xA202002A,  # prior 3 sets destination ID 6
    0x3E0978: 0xA382F02C,  # set global exit flag
    0x3E097C: 0x9382F02C,  # read global exit flag
    0x3E09B0: 0x0C0FBC50,  # cleanup callback 0x3EF140
    0x3E09B4: 0xA380F02C,  # clear global flag
    0x3E09D0: 0x2402FFFE,  # clear bit 0 of child pointer flag
    0x3E09DC: 0x8205002A,  # signed destination this+0x2A
    0x3E09E0: 0x0C0F7EC0,  # request 0x3DFB00
    0x3E09E8: 0x24020001,  # update reports completion
    0x3E0998: 0x1062FFDC,  # phase 1 -> check child pending
    0x3E09A0: 0x1060FFB0,  # phase 0 -> launch next child
}


def verify_demo_main_update_elf(elf):
    """Hash-gated original-code oracle for the ID-6 update branches."""
    if type(elf) is not bytes or hashlib.sha256(elf).hexdigest() != ELF_SHA256:
        raise ValueError('expected the exact EU-beta SLES_541.61 ELF')
    for address, expected in UPDATE_WORDS.items():
        if _word(elf, address) != expected:
            raise ValueError('DemoMain update instruction mismatch at 0x%08X'
                             % address)
    return {
        'elf_sha256': ELF_SHA256,
        'update': hex(DEMO_MAIN_UPDATE_ADDRESS),
        'phase_offset': '0x30',
        'current_choice_offset': '0x28',
        'next_choice_offset': '0x29',
        'return_app_offset': '0x2a',
        'child_pointer_offset': '0x2c',
        'child_pending_helper': hex(DEMO_MAIN_WAIT_HELPER),
        'global_exit_flag_gp_offset': '-0xfd4',
        'initial_return_application_id': DEMO_MAIN_INITIAL_RETURN_APP,
        'child_ids': list(DEMO_MAIN_CHILD_CHOICES),
        'return_app_after_child': {'1': 3, '3': 6},
        'verified_words': len(UPDATE_WORDS),
    }


def _call(address, arguments=None, **fields):
    result = {'address': address, 'arguments': [] if arguments is None else arguments,
              'executed': False}
    result.update(fields)
    return result


class c_demo_main_update:
    """Execute only verified native state/control-flow side effects.

    Each step:
      child_present: whether this+0x2C points to an active child/service
      child_pending: captured bool from 0x3DFC60 (True means wait)
      external_exit: captured nonzero global flag at gp-0xFD4
    No child object is allocated or video/audio played by this class.
    """

    def __init__(self):
        self.m_phase = 0              # this+0x30, reset in begin callback
        self.m_current_choice = 0     # this+0x28
        self.m_next_choice = 0        # this+0x29, constructor
        self.m_return_app = DEMO_MAIN_INITIAL_RETURN_APP  # this+0x2A, init
        self.m_exit_flag = False      # shared gp flag, modeled locally
        self.m_finished = False
        self.m_updates = 0
        self.m_child_requests = 0
        self.m_last_child = None
        self.m_last_return = None

    def snapshot(self):
        return {
            'phase': self.m_phase,
            'current_choice': self.m_current_choice,
            'next_choice': self.m_next_choice,
            'return_app': self.m_return_app,
            'exit_flag': self.m_exit_flag,
            'finished': self.m_finished,
            'updates': self.m_updates,
            'child_requests': self.m_child_requests,
            'last_child': self.m_last_child,
            'last_return': self.m_last_return,
        }

    def set_captured_next_choice(self, index):
        """Inject an observed +0x29 value at a native phase-0 boundary.

        Enables investigating a captured session which starts on a later
        child; this is NOT a claim that gameplay selects the given child.
        """
        if type(index) is not int or not 0 <= index < 4:
            raise ValueError('captured choice must be 0..3')
        if self.m_phase != 0 or self.m_finished:
            raise ValueError('captured choice can only be set at phase 0')
        self.m_next_choice = index

    def step(self, child_present=False, child_pending=True, external_exit=False):
        if any(type(value) is not bool for value in (
                child_present, child_pending, external_exit)):
            raise ValueError('all native external observations must be booleans')
        if self.m_finished:
            raise ValueError('native DemoMain update already completed')

        self.m_updates += 1
        calls = []
        self.m_exit_flag = self.m_exit_flag or external_exit

        # 0x3E0840..0x3E0860 checks the pointer and updates its virtual
        # +0x18 callback when present. It does not always launch a child.
        if child_present:
            calls.append(_call('child_vtable+0x18', [],
                               native_site='0x3e0854'))
        if self.m_phase == 0:
            if not child_present:
                calls.append(_call('0x3eb860', [0]))
            self.m_current_choice = self.m_next_choice
            index = self.m_current_choice

            if 0 <= index < len(DEMO_MAIN_CHILD_CHOICES):
                child_id = DEMO_MAIN_CHILD_CHOICES[index]
                self.m_next_choice = (index + 1) & 3
                self.m_child_requests += 1
                self.m_last_child = {
                    'choice': index,
                    'id': child_id,
                    'name': resolve_app(child_id)['class_name'],
                    'factory': resolve_app(child_id)['factory'],
                    'request_site': DEMO_MAIN_CHOICE_SITES[index],
                }
                calls.append(_call('0x3dfbd0', [child_id],
                                   native_site=hex(DEMO_MAIN_CHOICE_SITES[index])))
            self.m_phase += 1

        if self.m_phase == 1:
            # This call follows 0x3E0908 *on the same update*. It is
            # also the only work on updates that enter with phase 1.
            calls.append(_call('0x3dfc60', [], observed_result=child_pending))
            if not child_pending:
                if self.m_current_choice == 1:
                    self.m_phase = 0
                    self.m_exit_flag = True
                elif self.m_current_choice == 3:
                    self.m_phase = 0
                    self.m_return_app = 6
                    self.m_exit_flag = True
                elif self.m_current_choice in (0, 2):
                    self.m_phase = 0

        if self.m_exit_flag:
            # Shared gp flag is cleared; global subsystem cleanup,
            # optional child-bit clear and parent app request follow.
            calls.extend((
                _call('0x3ef140'),
                _call('0x3ef4d0'),
                _call('child_flags_clear_bit0', [],
                      native_site='0x3e09cc', conditional=True),
                _call('0x3dfb00', [self.m_return_app]),
            ))
            self.m_exit_flag = False
            self.m_finished = True
            self.m_last_return = self.m_return_app

        return {
            'finished': self.m_finished,
            'calls': calls,
            'snapshot': self.snapshot(),
        }
