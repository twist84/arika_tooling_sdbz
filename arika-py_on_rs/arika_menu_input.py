"""EU-beta SDBZ menu pad edge/repeat preprocessing, without a Qt clock.

Provenance: SLES_541.61 0x336240..0x336400, 0x336420..0x336634,
0x379c80..0x379e3c. Fields held/pressed are the *native pad* +0x1e and
+0x22 halfwords, respectively. The optional analog_mask is the *output*
of 0x336640, not a guessed stick/deadzone conversion.

The menu requests edge-only directions (0x336450/60/70/80, a1=1). Repeats
are still computed by the pad preprocessor, but not consumed by this menu.
"""

DIRECTION_PRIORITY = ((1, 2), (2, 3), (8, 0), (4, 1))
DIRECTION_MASKS = (8, 4, 1, 2)
GATE_MASK = 0x80
CONFIRM_MASK = 0x40


def filter_opposite_directions(mask):
    """0x336314..0x336374: prefer bit 1 over 2 and bit 4 over 8."""
    mask &= 0xffff
    if mask & 0x3 == 0x3:
        mask &= ~0x2
    if mask & 0xc == 0xc:
        mask &= ~0x8
    return mask


def repeat_step(counter, held_mask):
    """0x3363c0: native 20-count first repeat, recycle by 4, no clock."""
    if not held_mask:
        return 0, 0
    counter += 1
    if counter >= 20:
        return counter - 4, held_mask & 0xffff
    return counter, 0


class c_menu_pad_input:
    """Tracks two pad records and the aggregate record at 0x005E7AA0.

    A frame is a pair of dictionaries with optional raw native halfwords:
    held (+0x1e), pressed (+0x22), analog_mask (from 0x336640).
    Zero-filling fields is an explicit synthetic test input, not a claimed
    physical gamepad mapping. 'pressed' is *not* synthesized from 'held'.
    """

    def __init__(self):
        self.m_counters = [0, 0]
        self.m_prior_analog = [0, 0]
        self.m_global_counter = 0
        self.m_edges = [0, 0]
        self.m_repeat_edges = [0, 0]
        self.m_aggregate_edge = 0
        self.m_aggregate_repeat_edge = 0

    def step(self, pads):
        if len(pads) != 2:
            raise ValueError('native menu input requires two pad records')
        held_union = 0
        pressed_union = 0
        for index, pad in enumerate(pads):
            raw_held = int(pad.get('held', 0)) & 0xf
            raw_pressed = int(pad.get('pressed', 0)) & 0xf
            analog = int(pad.get('analog_mask', 0)) & 0xf
            held = raw_held | analog
            pressed = raw_pressed | (analog & ~self.m_prior_analog[index])
            self.m_prior_analog[index] = analog
            self.m_counters[index], repeated = repeat_step(self.m_counters[index], held)
            self.m_edges[index] = pressed
            self.m_repeat_edges[index] = pressed | repeated
            held_union |= held
            pressed_union |= pressed

        held_union = filter_opposite_directions(held_union)
        pressed_union = filter_opposite_directions(pressed_union)
        self.m_global_counter, repeated = repeat_step(self.m_global_counter, held_union)
        self.m_aggregate_edge = pressed_union
        self.m_aggregate_repeat_edge = pressed_union | repeated
        return self.snapshot()

    def edge_mask(self, selector):
        if selector == 2:
            return self.m_aggregate_edge
        if selector in (0, 1):
            return self.m_edges[selector]
        raise ValueError('unknown native controller selector')

    def repeat_mask(self, selector):
        if selector == 2:
            return self.m_aggregate_repeat_edge
        if selector in (0, 1):
            return self.m_repeat_edges[selector]
        raise ValueError('unknown native controller selector')

    def snapshot(self):
        return {
            'pad_edge': tuple(self.m_edges),
            'pad_edge_or_repeat': tuple(self.m_repeat_edges),
            'pad_counter': tuple(self.m_counters),
            'aggregate_edge': self.m_aggregate_edge,
            'aggregate_edge_or_repeat': self.m_aggregate_repeat_edge,
            'aggregate_counter': self.m_global_counter,
        }


def decode_menu_input(edge_mask, confirm_mask=0, controller_qualified=True):
    """0x379c80: resolve one frame of *already sampled native* inputs.

    controller_qualified is the result of 0x37a040/0x336420. The exact
    meaning of raw pad +0x22 bit 0x80 needs a pad-producer trace; callers
    should not treat it as an invented Cancel button.
    """
    if not controller_qualified:
        return ('cancel', None)
    if confirm_mask & CONFIRM_MASK:
        return ('confirm', None)
    for mask, direction in DIRECTION_PRIORITY:
        if edge_mask & mask:
            return ('direction', direction)
    return ('none', None)
