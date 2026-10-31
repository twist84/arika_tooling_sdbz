#!/usr/bin/env python3
"""Read CHT logical-motion mappings without following relocated runtime pointers."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
from arika_models import require
from arika_dat import motion_archive
from arika_import import write_output
import arika_backend as backend


def parse_cht(data):
    return backend.parse_cht(data)


def lookup(document, motion_id, variant):
    require(type(motion_id) is int and 0 <= motion_id < 1000, 'motion ID must be 0..999')
    require(type(variant) is int and variant >= 0, 'variant must be nonnegative')
    action = next((a for a in reversed(document['actions']) if a['motion_id'] == motion_id), None)
    require(action is not None, 'logical motion ID is absent from CHT')
    require(variant < len(action['variants']), 'motion variant is absent from CHT')
    return action['variants'][variant]


def runtime_motion_name(name):
    return backend.runtime_motion_name(name)


def load_banks(specifications):
    banks = {}
    for specification in specifications:
        key, separator, path = specification.partition('=')
        require(separator and key.isdecimal() and path, 'bank must be INDEX=package.pmt')
        index = int(key)
        require(0 <= index <= 0xFFFF and index not in banks, 'invalid or duplicate bank index')
        data = Path(path).read_bytes()
        package = motion_archive(data)
        names = {}
        for motion in package['motions']:
            names.setdefault(runtime_motion_name(motion['name']), motion)
        banks[index] = dict(path=str(Path(path)), sha256=hashlib.sha256(data).hexdigest(), names=names)
    return banks


def resolve(record, banks):
    result = dict(record)
    bank = banks.get(record['resource_bank'])
    if bank is None:
        result.update(status='missing_bank')
        return result
    result.update(package=bank['path'], package_sha256=bank['sha256'])
    motion = bank['names'].get(record['motion_name'])
    if motion is None:
        result.update(status='missing_motion')
    else:
        result.update(status='resolved', package_index=motion['index'], package_motion=motion['name'])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    for command in ('json', 'map'):
        p = subs.add_parser(command); p.add_argument('cht'); p.add_argument('output')
        if command == 'map':
            p.add_argument('--bank', action='append', required=True)
    args = parser.parse_args()
    try:
        result = parse_cht(Path(args.cht).read_bytes()); inputs = [args.cht]
        if args.command == 'map':
            banks = load_banks(args.bank); inputs += [b['path'] for b in banks.values()]
            for action in result['actions']:
                action['variants'] = [resolve(v, banks) for v in action['variants']]
        write_output(args.output, json.dumps(result, indent=2).encode(), inputs)
        print('Wrote ' + args.output)
    except (OSError, ValueError, KeyError, TypeError, struct.error) as error:
        print('error: ' + str(error), file=sys.stderr); return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
