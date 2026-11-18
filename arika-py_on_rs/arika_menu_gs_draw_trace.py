"""Inspect explicitly captured PS2 GS A+D writes at individual menu draws.

This consumes a *caller-produced* chronological JSON trace, not the
intermediate ARIKA opcode-1 engine packet or a screenshot. Unknown registers
stay unknown; no static ELF initializer is substituted for live GS state.
A draw's GS context must be supplied by the capture (not guessed from PRIM).
"""
import argparse
import json
from pathlib import Path

from arika_menu_gs_registers import decode_gs_alpha, decode_gs_test
from arika_menu_gs_texture import (
    decode_clamp, decode_tex0, decode_tex1, decode_texa,
)


TRACE_FORMAT = 'ARIKA_GS_AD_DRAW_TRACE'
TRACE_VERSION = 1

# GS A+D register addresses. Values in each pair are contexts 1 and 2.
CONTEXT_REGISTERS = {
    'tex0': (0x06, 0x07),
    'tex1': (0x14, 0x15),
    'clamp': (0x08, 0x09),
    'test': (0x47, 0x48),
    'alpha': (0x42, 0x43),
    'zbuf': (0x4E, 0x4F),
}
GLOBAL_REGISTERS = {'texa': 0x3B}
DECODERS = {
    'tex0': decode_tex0,
    'tex1': decode_tex1,
    'clamp': decode_clamp,
    'texa': decode_texa,
    'test': decode_gs_test,
    'alpha': decode_gs_alpha,
}
MIN_FILTERS = (
    'nearest', 'linear', 'nearest_mipmap_nearest',
    'nearest_mipmap_linear', 'linear_mipmap_nearest',
    'linear_mipmap_linear', 'reserved_6', 'reserved_7',
)


def _unsigned(value, bits, field):
    if type(value) is int:
        result = value
    elif isinstance(value, str):
        try:
            result = int(value, 0)
        except ValueError as error:
            raise ValueError('%s must be a numeric integer or string' % field) from error
    else:
        raise ValueError('%s must be a numeric integer or string' % field)
    if not 0 <= result < (1 << bits):
        raise ValueError('%s exceeds unsigned %d-bit range' % (field, bits))
    return result


def analyze_trace(trace):
    """Replay caller-observed GS register writes without synthesizing defaults.

    Events must be ordered as observed by a GS debugger or decoded GIF
    stream. Each draw must explicitly identify its *observed* GS context.
    There is no automatic correspondence with an ARIKA sprite or PIX atlas.
    """
    if (not isinstance(trace, dict) or trace.get('format') != TRACE_FORMAT or
            type(trace.get('version')) is not int or
            trace['version'] != TRACE_VERSION or
            not isinstance(trace.get('events'), list)):
        raise ValueError('expected ARIKA_GS_AD_DRAW_TRACE version 1 with events')

    state = {}
    draws = []
    write_count = 0
    other_writes = 0
    recognized = set(GLOBAL_REGISTERS.values())
    for pair in CONTEXT_REGISTERS.values():
        recognized.update(pair)

    for index, event in enumerate(trace['events']):
        if not isinstance(event, dict):
            raise ValueError('event %d must be an object' % index)
        kind = event.get('kind')
        if kind == 'write':
            address = _unsigned(event.get('address'), 7,
                                'event %d address' % index)
            value = _unsigned(event.get('value'), 64,
                              'event %d value' % index)
            state[address] = value
            write_count += 1
            if address not in recognized:
                other_writes += 1
        elif kind == 'draw':
            context = event.get('context')
            if type(context) is not int or context not in (1, 2):
                raise ValueError('event %d draw needs observed context 1 or 2' % index)
            label = event.get('label')
            if label is not None and not isinstance(label, str):
                raise ValueError('event %d label must be a string' % index)
            raw = {
                name: state.get(pair[context - 1])
                for name, pair in CONTEXT_REGISTERS.items()
            }
            for name, address in GLOBAL_REGISTERS.items():
                raw[name] = state.get(address)
            fields = {
                name: DECODERS[name](raw[name])
                if raw[name] is not None and name in DECODERS else None
                for name in (*CONTEXT_REGISTERS, *GLOBAL_REGISTERS)
            }
            tex1 = fields['tex1']
            sampling = {
                'status': 'captured' if tex1 is not None else 'unknown',
                'magnification': ('linear' if tex1['mmag'] else 'nearest')
                                 if tex1 is not None else None,
                'minification': MIN_FILTERS[tex1['mmin']]
                                if tex1 is not None else None,
            }
            draws.append({
                'event_index': index,
                'label': label,
                'context': context,
                'registers': {
                    name: hex(value) if value is not None else None
                    for name, value in raw.items()
                },
                'fields': fields,
                'sampling': sampling,
            })
        else:
            raise ValueError('event %d has unsupported kind %r' % (index, kind))

    return {
        'format': 'ARIKA_GS_DRAW_STATE_REPORT',
        'version': 1,
        'write_events': write_count,
        'unreported_register_types': other_writes,
        'draw_events': len(draws),
        'draws': draws,
        'limitations': [
            'Only writes present in the supplied chronological trace are known.',
            'A missing register does not mean its GS reset/default value.',
            'Draw context is externally observed; PRIM/PRMODE selection is not inferred.',
            'The trace does not identify an ARIKA sprite, PIX atlas or engine opcode.',
            'This is a register-state report, not GS rasterization or Qt filter parity.',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', type=Path,
                        help='JSON list of chronological GS writes and draw markers')
    args = parser.parse_args()
    try:
        result = analyze_trace(json.loads(args.trace.read_text(encoding='utf-8')))
    except (OSError, ValueError, TypeError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
