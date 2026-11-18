"""Read-only, evidence-bounded SDBZ EU-beta EE factory execution traces.

Accepts manually recorded PCSX2 EE debugger observations, optionally from
another debugger capable of capturing the same EE CPU state. This module
never attaches to PCSX2, invokes native game code, or manufactures events.

A breakpoint *before* jalr is not proof that its target executed. A
reported breakpoint on the factory's first instruction establishes a
stronger execution observation, and a post-write memory watchpoint is
required to claim the active-root slot changed.
"""
import argparse
import json
from pathlib import Path

from arika_app_registry import APP_ENTRIES, APP_NATIVE_REGISTRY


TRACE_FORMAT = 'sdbz-eu-beta-ee-factory-trace-v1'
ELF_SHA256 = APP_NATIVE_REGISTRY['elf_sha256']
PROVIDER_DISPATCH = 0x003F1C78
ROOT_DISPATCH = 0x003F1BE0
PROVIDER_RETURN = 0x003F1C80
ROOT_RETURN = 0x003F1BE8
ROOT_HANDOFF = 0x003F1BA0
ROOT_STORE = 0x003F1C04
FALLBACK_STORE = 0x003F1C30
ROOT_SLOT = 0x0063BE38
ROOT_NULL_FALLBACK = 0x004FCAD4
ROOT_INVALID_FALLBACK = 0x005E1AC0
MAX_EVENTS = 50000
FACTORY_BY_ADDRESS = {app['factory']: app for app in APP_ENTRIES.values()}


def _u32(value, field):
    if type(value) is int:
        number = value
    elif type(value) is str and value.startswith('0x'):
        try:
            number = int(value, 16)
        except ValueError:
            raise ValueError('%s must be an unsigned 32-bit integer' % field)
    else:
        raise ValueError('%s must be an integer or 0x-prefixed string' % field)
    if not 0 <= number <= 0xFFFFFFFF:
        raise ValueError('%s exceeds 32-bit unsigned range' % field)
    return number


def _item(event, key):
    if key not in event:
        raise ValueError('missing trace event field: %s' % key)
    return _u32(event[key], key)


def _register(event, name):
    registers = event.get('registers')
    if not isinstance(registers, dict) or name not in registers:
        raise ValueError('missing EE register %s' % name)
    return _u32(registers[name], 'registers.%s' % name)


def inspect_native_ee_trace(document):
    """Validate observed EE breakpoint events against original 47 factories.

    Returned evidence is *reported debugger observations*, not proof of
    where a UI preview navigated, frame-perfect timing or fresh allocation.
    The user-supplied 'source' cannot be independently authenticated.
    """
    if not isinstance(document, dict):
        raise ValueError('EE trace must be a JSON object')
    if document.get('format') != TRACE_FORMAT:
        raise ValueError('unknown EE trace format')
    if document.get('elf_sha256') != ELF_SHA256:
        raise ValueError('exact original EU-beta ELF SHA-256 is required')
    origin = document.get('source')
    if origin not in ('pcsx2-ee-debugger', 'pcsx2-ee-gdb',
                      'synthetic-test-fixture'):
        raise ValueError('EE trace source must be explicitly identified')
    events = document.get('events')
    if not isinstance(events, list) or len(events) > MAX_EVENTS:
        raise ValueError('EE trace requires an events array within size limit')

    stack = []
    reported_entries = []
    observed_returns = []
    root_writes = []
    handoffs = []
    warnings = []
    rows = []
    last_sequence = -1
    last_root_return = None
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise ValueError('event %d is not an object' % index)
        seq = event.get('sequence')
        if type(seq) is not int or seq <= last_sequence or seq < 0:
            raise ValueError('event sequence must be increasing integers')
        last_sequence = seq
        kind = event.get('kind')
        if kind not in ('root_handoff', 'factory_dispatch', 'factory_entry',
                        'factory_return', 'root_write'):
            raise ValueError('unknown EE trace event kind at %d' % seq)
        row = {'sequence': seq, 'kind': kind}
        if kind == 'root_handoff':
            pc = _item(event, 'pc')
            target = _register(event, 'a0') & 0xFF
            ra = _register(event, 'ra')
            if pc != ROOT_HANDOFF:
                raise ValueError('root handoff PC mismatch')
            row.update(requested_id=target,
                       scheduler_caller=(ra == 0x003DFF3C),
                       registered=target in APP_ENTRIES)
            handoffs.append(row)
        elif kind == 'factory_dispatch':
            pc = _item(event, 'pc')
            if pc not in (PROVIDER_DISPATCH, ROOT_DISPATCH):
                raise ValueError('unexpected factory dispatch PC')
            requested = _register(event, 's0') & 0xFF
            target = _register(event, 'v0')
            if requested > 47 or (pc == ROOT_DISPATCH and requested == 0):
                raise ValueError('factory dispatch ID rejected by EE bounds')
            app = APP_ENTRIES.get(requested)
            if app is not None and target != app['factory']:
                raise ValueError('factory pointer differs from original ID table')
            if not target or (target % 4):
                raise ValueError('factory dispatch must have aligned target')
            frame = {'sequence': seq, 'dispatch_pc': pc,
                     'return_pc': pc + 8, 'requested_id': requested,
                     'factory_pc': target, 'entered': False}
            stack.append(frame)
            row.update(requested_id=requested, factory_pc=target,
                       class_name=app['class_name'] if app else None,
                       path='root' if pc == ROOT_DISPATCH else 'provider',
                       execution_confirmed=False)
        elif kind == 'factory_entry':
            pc = _item(event, 'pc')
            ra = _register(event, 'ra')
            # Only a matching in-flight jalr proves this particular
            # dispatch reached the registered factory's first instruction.
            if not stack:
                raise ValueError('factory entry has no captured dispatch')
            frame = stack[-1]
            if frame['entered'] or pc != frame['factory_pc'] or (
                    ra != frame['return_pc']):
                raise ValueError('factory entry does not match pending jalr')
            frame['entered'] = True
            app = APP_ENTRIES.get(frame['requested_id'])
            row.update(requested_id=frame['requested_id'],
                       class_name=app['class_name'] if app else None,
                       dispatch_sequence=frame['sequence'],
                       execution_confirmed=True)
            reported_entries.append(row)
        elif kind == 'factory_return':
            pc = _item(event, 'pc')
            value = _register(event, 'v0')
            if pc not in (ROOT_RETURN, PROVIDER_RETURN):
                raise ValueError('unexpected factory return PC')
            frame = stack[-1] if stack else None
            if frame is not None and frame['return_pc'] == pc:
                stack.pop()
                row.update(dispatch_sequence=frame['sequence'],
                           requested_id=frame['requested_id'],
                           entry_observed=frame['entered'],
                           object_pointer=value)
            else:
                # Sparse manual breakpoint capture is allowed, but a
                # return without its dispatch remains *uncorrelated*.
                warnings.append('unpaired return at event %d' % seq)
                row.update(dispatch_sequence=None, requested_id=None,
                           entry_observed=False, object_pointer=value)
            if pc == ROOT_RETURN:
                last_root_return = row
            observed_returns.append(row)
        else:
            site = _item(event, 'store_pc')
            address = _item(event, 'address')
            value = _item(event, 'value')
            a0 = _register(event, 'a0')
            if site not in (ROOT_STORE, FALLBACK_STORE) or address != ROOT_SLOT:
                raise ValueError('not an original active-root pointer store')
            if event.get('post_write') is not True:
                raise ValueError('root write requires post-write memory observation')
            if value != a0:
                raise ValueError('root pointer memory does not match stored a0')
            if site == FALLBACK_STORE and value != ROOT_INVALID_FALLBACK:
                raise ValueError('invalid-ID fallback pointer mismatch')
            correlation = None
            if site == ROOT_STORE and last_root_return is not None:
                returned = last_root_return['object_pointer']
                expected = returned if returned else ROOT_NULL_FALLBACK
                if value != expected:
                    raise ValueError('root write differs from captured return/fallback')
                correlation = last_root_return['sequence']
                last_root_return = None
            if site == FALLBACK_STORE:
                last_root_return = None
            row.update(store_pc=site, root_pointer=value,
                       correlated_return_sequence=correlation,
                       post_write_observed=True)
            root_writes.append(row)
        rows.append(row)

    for frame in stack:
        warnings.append('dispatch at event %d has no captured return' %
                        frame['sequence'])
    unique_ids = sorted({e['requested_id'] for e in reported_entries
                         if e['requested_id'] in APP_ENTRIES})
    return {
        'format': TRACE_FORMAT,
        'capture_source': origin,
        'source_is_user_reported': True,
        'synthetic_fixture': origin == 'synthetic-test-fixture',
        'event_count': len(rows),
        'root_handoff_count': len(handoffs),
        'factory_dispatch_count': len([e for e in rows
                                       if e['kind'] == 'factory_dispatch']),
        'factory_entry_count': len(reported_entries),
        'factory_return_count': len(observed_returns),
        'root_write_count': len(root_writes),
        'observed_factory_ids': unique_ids,
        'last_root_pointer': (root_writes[-1]['root_pointer']
                              if root_writes else None),
        'warnings': warnings,
        'events': rows,
        'visual_transition_verified': False,
        'new_allocation_proven': False,
    }


def load_native_ee_trace(path):
    """Load a saved debugger recording; does not communicate with PCSX2."""
    path = Path(path)
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError('EE trace exceeds 16 MiB')
    with path.open('r', encoding='utf-8') as stream:
        return inspect_native_ee_trace(json.load(stream))


def pcsx2_ee_symbols():
    """Produce PCSX2 .sym navigation labels from the verified registry.

    .sym labels help navigate the debugger; importing them does not
    automatically create breakpoints or record EE instructions.
    """
    specials = {
        0x003DFD34: 'ee_root_phase5_handoff_jal',
        ROOT_HANDOFF: 'ee_root_factory_handoff_entry',
        ROOT_DISPATCH: 'ee_root_factory_jalr',
        ROOT_RETURN: 'ee_root_factory_return',
        ROOT_STORE: 'ee_root_store_after_factory',
        FALLBACK_STORE: 'ee_root_store_invalid_id',
        PROVIDER_DISPATCH: 'ee_provider_factory_jalr',
        PROVIDER_RETURN: 'ee_provider_factory_return',
        ROOT_SLOT: 'ee_active_root_global',
    }
    labels = dict(specials)
    for app_id, app in APP_ENTRIES.items():
        address = app['factory']
        if address in labels:
            raise ValueError('factory address collides with debugger label')
        class_name = ''.join(ch if ch.isalnum() else '_'
                             for ch in app['class_name'])
        labels[address] = 'ee_app_%02d_%s_factory' % (app_id, class_name)
    if len(labels) != len(APP_ENTRIES) + len(specials):
        raise ValueError('native debugger symbol set is incomplete')
    return ''.join('%08X %s\n' % (address, name)
                   for address, name in sorted(labels.items()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', nargs='?', type=Path,
                        help='user-recorded EE debugger JSON capture')
    parser.add_argument('--write-pcsx2-symbols', type=Path,
                        help='write a .sym label file for 47 native factories')
    args = parser.parse_args()
    try:
        if args.write_pcsx2_symbols is not None:
            args.write_pcsx2_symbols.write_text(
                pcsx2_ee_symbols(), encoding='utf-8')
        if args.trace is not None:
            summary = load_native_ee_trace(args.trace)
            print(json.dumps(summary, indent=2))
        elif args.write_pcsx2_symbols is None:
            parser.error('supply an EE trace or --write-pcsx2-symbols')
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
