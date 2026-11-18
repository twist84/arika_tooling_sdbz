"""Narrow original-EU-beta CAppDemoMain entry/loader model.

This is NOT a movie player or a full implementation of the 0x3E0830
update callback. It exposes only the verified bootstrap load gate and
the distinct child-request sites, leaving external helper results
explicit and refusing to pretend the game's asynchronous IO ran.
"""
from arika_app_registry import (
    DEMO_MAIN_CHILD_CHOICES, DEMO_MAIN_CHOICE_SITES,
    resolve_app, title_handoff_request,
)


DEMO_MAIN_INIT_ADDRESS = 0x003E0440
DEMO_MAIN_LOAD_ADDRESS = 0x003E04A0
DEMO_MAIN_BEGIN_ADDRESS = 0x003E07F0
DEMO_MAIN_UPDATE_ADDRESS = 0x003E0830
DEMO_MAIN_RESOURCE_GROUPS = (2, 3, 4, 5, 7, 8, 10, 11, 15)
DEMO_MAIN_GROUP_REGISTER = '0x2fbdc0'
DEMO_MAIN_GROUP_READY = '0x2fbeb0'


class c_demo_main_bootstrap:
    """State of the stage 0→1→0 resource loader and title handoff."""

    def __init__(self):
        self.m_load_phase = 0
        self.m_load_updates = 0
        self.m_ready = False
        self.m_title_request = None
        self.m_entry_report = []

    def accept_title_result(self, result):
        handoff = title_handoff_request(result)
        if handoff is None:
            return False
        self.m_title_request = handoff
        self.m_load_phase = 0
        self.m_load_updates = 0
        self.m_ready = False
        self.m_entry_report = [
            {'address': '0x3f1c40', 'arguments': [6], 'executed': False},
            {'address': '0x3f2c00', 'arguments': [], 'executed': False},
            {'address': '0x3e03e0', 'arguments': [], 'executed': False},
        ]
        return True

    def snapshot(self):
        return {
            'source_id': 2 if self.m_title_request else None,
            'destination_id': 6,
            'destination_class': resolve_app(6)['class_name'],
            'handoff_requested': self.m_title_request is not None,
            'constructor_executed': False,
            'load_phase': self.m_load_phase,
            'load_updates': self.m_load_updates,
            'ready': self.m_ready,
            'child_candidates': list(DEMO_MAIN_CHILD_CHOICES),
        }

    def loader_step(self, external_ready):
        """Reproduce 0x3E04A0 stages for this+0x29 initially 0/1.

        Stage 0 registers the nine explicit native resource groups and
        changes 0→1 without reporting completion. Stage 1 calls the
        external readiness helper and returns one only when ready.
        """
        if type(external_ready) is not bool:
            raise ValueError('external_ready must be a captured bool')
        calls = []
        if self.m_ready:
            return {'ready': True, 'calls': [], 'snapshot': self.snapshot()}

        self.m_load_updates += 1
        if self.m_load_phase == 0:
            calls.append({'address': '0x2fcba0', 'arguments': []})
            calls.extend({'address': DEMO_MAIN_GROUP_REGISTER,
                          'arguments': [resource_group]}
                         for resource_group in DEMO_MAIN_RESOURCE_GROUPS)
            self.m_load_phase = 1
        elif self.m_load_phase == 1:
            calls.append({'address': DEMO_MAIN_GROUP_READY, 'arguments': []})
            if external_ready:
                self.m_ready = True
                self.m_load_phase = 0
        return {'ready': self.m_ready, 'calls': calls,
                'snapshot': self.snapshot()}

    def inspect_child(self, choice_index):
        if type(choice_index) is not int or not 0 <= choice_index < 4:
            raise ValueError('child choice must be an index 0..3')
        app_id = DEMO_MAIN_CHILD_CHOICES[choice_index]
        return {
            'source_class': 'CAppDemoMain',
            'source_address': DEMO_MAIN_UPDATE_ADDRESS,
            'request_address': 0x003DFBD0,
            'request_site': DEMO_MAIN_CHOICE_SITES[choice_index],
            'requested_child_id': app_id,
            'registered_class': resolve_app(app_id)['class_name']
                                if resolve_app(app_id) else None,
            'executed': False,
            'automatic_selection_proven': False,
        }
