"""Native EU-beta boot-logo resource-table tests with no game files in CI."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from arika_logo_resources import (
    LOGO_RESOURCE_NAMES, LOGO_RESOURCE_POINTERS, LOGO_POINTER_TABLE,
    LOGO_SOURCE_RECT, LOGO_DEST_RECT, LOGO_SAMPLER_BYTES,
    logo_asset_paths, recover_logo_resources,
)


class LogoResourceTests(unittest.TestCase):
    def test_verified_native_addresses_and_order(self):
        self.assertEqual(LOGO_POINTER_TABLE, 0x4b4770)
        self.assertEqual(LOGO_RESOURCE_POINTERS,
                         (0x4d91a0, 0x4d91c0, 0x4d91e0))
        self.assertEqual(LOGO_RESOURCE_NAMES,
                         ('dis/d03/d03t0205', 'dis/d03/d03t0203',
                          'dis/d03/d03t0202'))
        self.assertEqual(LOGO_SOURCE_RECT, (0, 0, 512, 447))
        self.assertEqual(LOGO_DEST_RECT, (0, 0, 512, 448))
        self.assertEqual(LOGO_SAMPLER_BYTES, (0, 1, 0, 0))

    def test_path_mapping_preserves_exact_native_names(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = logo_asset_paths(directory)
            self.assertEqual(len(paths), 3)
            for path, name in zip(paths, LOGO_RESOURCE_NAMES):
                self.assertEqual(path, Path(directory).joinpath(*name.split('/')))
            self.assertEqual(len({str(path) for path in paths}), 3)

    def test_rejects_wrong_elf_or_unverified_bytes(self):
        with self.assertRaises(ValueError):
            recover_logo_resources(b'not the original executable')
        with self.assertRaises(ValueError):
            recover_logo_resources(bytearray())

    def test_verify_original_elf_if_available(self):
        path = os.environ.get('SDBZ_EU_BETA_ELF')
        if not path:
            self.skipTest('exact EU-beta ELF is supplied only by user')
        source = Path(path).read_bytes()
        report = recover_logo_resources(source)
        self.assertEqual([row['name'] for row in report['resources']],
                         list(LOGO_RESOURCE_NAMES))
        self.assertEqual([row['wrapper_object_offset'] for row in
                          report['resources']], ['0x2c', '0x30', '0x34'])
        self.assertEqual(report['sprite']['destination_rect'],
                         list(LOGO_DEST_RECT))
        self.assertEqual(report['sprite']['source_rect'],
                         list(LOGO_SOURCE_RECT))
        self.assertEqual(report['sprite']['initial_sampler_bytes'],
                         list(LOGO_SAMPLER_BYTES))
        self.assertIn('not prove', report['limits'][-2].lower())

    def test_cli_with_user_provided_elf(self):
        path = os.environ.get('SDBZ_EU_BETA_ELF')
        if not path:
            self.skipTest('exact EU-beta ELF is supplied only by user')
        with tempfile.TemporaryDirectory() as root:
            result = subprocess.run([
                sys.executable, str(Path(__file__).with_name(
                    'arika_logo_resources.py')), path, '--assets-root', root],
                check=True, capture_output=True, text=True)
            decoded = json.loads(result.stdout)
            self.assertEqual(decoded['resources'][0]['name'],
                             LOGO_RESOURCE_NAMES[0])
            self.assertFalse(any(row['exists']
                                 for row in decoded['asset_files']))


if __name__ == '__main__':
    unittest.main()
