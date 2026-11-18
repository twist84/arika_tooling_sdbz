"""Exact EU-beta global UI clock gate used by Press Start prompt drawing.

The clock is owned by the shared UI singleton, not CAppTitleMain. A caller
must supply the native scheduler's delta and whether its update gates fired.
"""
import math
import struct


PRESS_START_CLOCK_UPDATE = 0x002E4E10
PRESS_START_CLOCK_CALLER = 0x002CB710
PRESS_START_PROMPT_GATE = 0x002E5510
PRESS_START_PROMPT_DRAW = 0x003F7E10
PRESS_START_CYCLE_END = 3.0
PRESS_START_VISIBLE_AFTER = 1.0


def _f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


class c_press_start_prompt_clock:
    def __init__(self, phase=0.0):
        self.m_phase = self._validated_phase(phase)
        self.m_ticks = 0

    @staticmethod
    def _validated_phase(phase):
        if type(phase) not in (int, float) or not math.isfinite(phase):
            raise ValueError('native clock phase must be finite')
        if phase < 0.0 or phase > PRESS_START_CYCLE_END:
            raise ValueError('native clock phase must be in [0,3]')
        return _f32(phase)

    @property
    def visible(self):
        return self.m_phase > PRESS_START_VISIBLE_AFTER

    @property
    def phase(self):
        return self.m_phase

    def advance(self, delta_seconds, update_enabled=True):
        if type(delta_seconds) not in (int, float):
            raise ValueError('native clock delta must be numeric')
        if not math.isfinite(delta_seconds) or delta_seconds < 0:
            raise ValueError('native clock delta must be finite/nonnegative')
        if type(update_enabled) is not bool:
            raise ValueError('global scheduler update gate must be boolean')
        if update_enabled:
            try:
                next_phase = _f32(self.m_phase + _f32(delta_seconds))
            except (OverflowError, struct.error) as error:
                raise ValueError('native clock delta outside float32') from error
            # 0x2E4E10 discards overshoot instead of performing modulo 3.
            self.m_phase = 0.0 if next_phase > PRESS_START_CYCLE_END else next_phase
            self.m_ticks += 1
        return self.visible
