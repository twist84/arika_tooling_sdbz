"""EU-beta sprite-render context: the verified 0x199500 and 0x199340 boundary.

This is an *engine* state, not direct GS registers. All tables below
are literal file-backed words from SLES_541.61. Backend arguments are
reported as raw integers; callers must not interpret them as GIF/GS
ALPHA, TEST, ZBUF, TEX0, filtering or blend modes without tracing the
backend setters and comparing a captured native graphics session.

The 0x199340 translator uses three indexed tables for state word0
(0x104920) and four for state word6, word8, and byte2 (0x104840).
Unobserved fields, unsupported indices and arbitrary enum values
are never clamped, guessed or converted to presentation semantics.
"""
import struct


STATE_KEYS = ('word0', 'byte2', 'byte3', 'byte4', 'word6', 'word8')

# 0x4630F0, 0x463110, 0x463130: 8 u32 entries each.
WORD0_ARG4 = (1, 2, 2, 2, 1, 4, 0, 0)
WORD0_ARG5 = (0, 3, 1, 1, 1, 5, 0, 0)
WORD0_ARG6 = (0, 0, 0, 2, 1, 0, 0, 0)

# 0x463150: four entries up to 0x463160.
WORD6_ARG4 = (1, 0, 6, 7)

# 0x463160: eight entries up to 0x463180.
BYTE2_ARG6 = (1, 2, 3, 7, 3, 0, 0, 0)

# 0x463180: six verified entries (following words are different data).
BYTE2_ARG7 = (0, 0, 0, 128, 128, 0)

# GP-0x7FC0 (0x4F73B0): two verified initial entries only.
# Neither the full array bound nor its unindexed neighbors is proven.
WORD8_ARG5 = (0, 1)


def decode_render_context(data):
    """0x199500 copies six fields from renderer+0x5C to a 10-byte state.

    Accept the 10-byte image of this region, not the whole renderer.
    A true capture can supply the bytes. Never synthesize a missing
    fourth byte (+0x60) from the constructor's zero-initialized BSS.
    """
    if not isinstance(data, bytes) or len(data) != 10:
        raise ValueError('renderer state must be exactly ten bytes')
    return dict(zip(
        STATE_KEYS,
        struct.unpack('<hbbbxhh', data),
    ))


def _index(table, index, role):
    if index is None:
        return None
    if not isinstance(index, int) or not 0 <= index < len(table):
        raise ValueError(
            '%s index %r is outside verified ELF table bounds' %
            (role, index))
    return table[index]


def resolve_backend_arguments(state):
    """Static translation performed by 0x199340 to two backend setters.

    Each result is either an exact raw tuple or None if required
    state was not provided. Return values are *not* GS register values.
    """
    if not isinstance(state, dict) or set(state) - set(STATE_KEYS):
        raise ValueError('unknown renderer context fields')
    for key in STATE_KEYS:
        if state.get(key) is not None and not isinstance(state[key], int):
            raise ValueError('context state values must be integers or null')

    word0 = state.get('word0')
    word6 = state.get('word6')
    word8 = state.get('word8')
    byte2 = state.get('byte2')

    first = None
    if word0 is not None:
        first = tuple(_index(table, word0, 'word0') for table in
                      (WORD0_ARG4, WORD0_ARG5, WORD0_ARG6))

    second = None
    if word6 is not None and byte2 is not None and word8 is not None:
        second = (
            _index(WORD6_ARG4, word6, 'word6'),
            _index(WORD8_ARG5, word8, 'word8'),
            _index(BYTE2_ARG6, byte2, 'byte2'),
            _index(BYTE2_ARG7, byte2, 'byte2'),
        )
    return dict(
        backend_0x104920=first, backend_0x104840=second,
        note='Raw engine backend arguments; GS semantics unverified',
    )
