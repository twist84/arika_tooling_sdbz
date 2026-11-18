"""Grounded EU-beta app factory IDs, title completion and DemoMain bootstrap."""
import os
from pathlib import Path
import subprocess
import sys
import unittest

from arika_app_registry import (
    APP_FACTORY_TABLE, APP_FACTORIES, APP_TRANSITION_REQUEST,
    APP_REGISTRY_COUNT, recover_registered_app_ids_elf,
    DEMO_MAIN_CHILD_CHOICES, resolve_app, title_handoff_request,
    verify_app_registry_elf,
)
from arika_demo_main_runtime import (
    DEMO_MAIN_RESOURCE_GROUPS, c_demo_main_bootstrap,
)
from arika_title_runtime import c_title_runtime


def finished_title_result():
    title = c_title_runtime()
    title.step(0, False)
    title.step(4.1, False)
    return title.step(0, False)


class RegistryTests(unittest.TestCase):
    def test_original_ids_are_not_zero_based_list_offsets(self):
        expected = {
            1: 'CAppWarning',
            2: 'CAppCRISofdec',
            3: 'CAppTitleMain',
            4: 'CAppLogoMain',
            5: 'CAppMonitorSelect',
            6: 'CAppDemoMain',
            7: 'CAppDemoMovie',
            8: 'CAppDemoMain',
            9: 'CAppDemoPlay',
            42: 'CAppMenuMain',
            43: 'CAppShenronMain',
        }
        self.assertEqual(set(record[0] for record in APP_FACTORIES),
                         set(range(1, 48)))
        for app_id, name in expected.items():
            with self.subTest(app_id=app_id):
                self.assertEqual(resolve_app(app_id)['class_name'], name)
        self.assertIsNone(resolve_app(0))
        self.assertEqual(resolve_app(1)['factory'], 0x3F2DE0)
        self.assertEqual(resolve_app(1)['constructor'], 0x3FA9A0)
        self.assertEqual(resolve_app(2)['class_name'], 'CAppCRISofdec')
        self.assertEqual(resolve_app(5)['class_name'], 'CAppMonitorSelect')
        self.assertNotEqual(resolve_app(1)['base_vtable'], resolve_app(5)['base_vtable'])
        self.assertNotEqual(resolve_app(2)['base_vtable'], resolve_app(3)['base_vtable'])
        self.assertEqual(resolve_app(42)['factory'], 0x3F1F40)
        self.assertEqual(resolve_app(42)['constructor'], 0x3FDD60)
        self.assertEqual(resolve_app(42)['name_getter'], 0x3FE330)
        self.assertEqual(resolve_app(42)['name_address'], 0x4D85F0)
        self.assertEqual(resolve_app(43)['factory'], 0x3F1EE0)
        self.assertNotEqual(resolve_app(42)['class_name'],
                            resolve_app(43)['class_name'])
        self.assertIsNone(resolve_app(48))
        self.assertNotEqual(resolve_app(2)['constructor'],
                            resolve_app(3)['constructor'])
        self.assertEqual(resolve_app(3)['factory'], 0x3f2d20)
        self.assertEqual(resolve_app(3)['constructor'], 0x3f7150)
        self.assertNotEqual(resolve_app(8)['factory'],
                            resolve_app(6)['factory'])
        self.assertNotEqual(resolve_app(8)['constructor'],
                            resolve_app(6)['constructor'])
        self.assertNotEqual(resolve_app(8)['name_address'],
                            resolve_app(6)['name_address'])
        self.assertEqual(resolve_app(8)['name_getter'], 0x3e26b0)
        self.assertEqual(resolve_app(9)['name_getter'], 0x3e1ae0)
        self.assertEqual(resolve_app(6)['factory'], 0x3f2c00)
        self.assertEqual(resolve_app(7)['factory'], 0x3f2ba0)
        self.assertEqual(APP_FACTORY_TABLE, 0x6217e0)

    def test_no_implicit_factory_identity_for_invalid_ids(self):
        for app_id in ('6', 6.0, True, None):
            with self.subTest(app_id=app_id):
                with self.assertRaises(ValueError):
                    resolve_app(app_id)

    def test_title_request_uses_native_completion_call_only(self):
        title = c_title_runtime()
        self.assertIsNone(title_handoff_request(title.step(0, False)))
        self.assertIsNone(title_handoff_request(title.step(4.1, False)))
        result = title.step(0, False)
        self.assertTrue(result['finished'])
        handoff = title_handoff_request(result)
        self.assertEqual(handoff['request_address'], APP_TRANSITION_REQUEST)
        self.assertEqual(handoff['target']['id'], 6)
        self.assertEqual(handoff['target']['class_name'], 'CAppDemoMain')
        self.assertFalse(handoff['executed'])

        for fake in (
            {'finished': False, 'calls': [
                {'address': '0x3dfb00', 'arguments': [6]}]},
            {'finished': True, 'calls': [
                {'address': '0x3dfb00', 'arguments': [7]}]},
            {'finished': True, 'calls': [
                {'address': '0x3dfbd0', 'arguments': [6]}]},
            {'finished': True, 'calls': []},
        ):
            self.assertIsNone(title_handoff_request(fake))
        with self.assertRaises(TypeError):
            title_handoff_request('not a result')

    def test_demo_main_accepts_title_completion_but_does_not_run_factory(self):
        demo = c_demo_main_bootstrap()
        initial = demo.snapshot()
        self.assertFalse(initial['handoff_requested'])
        self.assertEqual(initial['destination_id'], 6)
        self.assertEqual(initial['destination_class'], 'CAppDemoMain')
        self.assertFalse(initial['constructor_executed'])
        self.assertFalse(demo.accept_title_result({
            'finished': True, 'calls': []}))
        self.assertTrue(demo.accept_title_result(finished_title_result()))
        after = demo.snapshot()
        self.assertTrue(after['handoff_requested'])
        self.assertEqual(after['source_id'], 2)
        self.assertFalse(after['constructor_executed'])
        self.assertEqual(
            [event['address'] for event in demo.m_entry_report],
            ['0x3f1c40', '0x3f2c00', '0x3e03e0'])
        self.assertTrue(all(not entry['executed']
                            for entry in demo.m_entry_report))

    def test_demo_main_stage_zero_resource_groups_and_external_readiness(self):
        demo = c_demo_main_bootstrap()
        self.assertEqual(DEMO_MAIN_RESOURCE_GROUPS,
                         (2, 3, 4, 5, 7, 8, 10, 11, 15))
        first = demo.loader_step(True)
        self.assertFalse(first['ready'])
        self.assertEqual(first['snapshot']['load_phase'], 1)
        self.assertEqual(first['calls'][0]['address'], '0x2fcba0')
        self.assertEqual(
            [call['arguments'][0] for call in first['calls'][1:]],
            list(DEMO_MAIN_RESOURCE_GROUPS))
        self.assertEqual(len(first['calls']), 10)

        blocked = demo.loader_step(False)
        self.assertFalse(blocked['ready'])
        self.assertEqual(blocked['calls'][0]['address'], '0x2fbeb0')
        self.assertEqual(blocked['snapshot']['load_phase'], 1)

        done = demo.loader_step(True)
        self.assertTrue(done['ready'])
        self.assertEqual(done['snapshot']['load_phase'], 0)
        self.assertEqual(done['snapshot']['load_updates'], 3)
        self.assertTrue(demo.loader_step(False)['ready'])
        with self.assertRaises(ValueError):
            c_demo_main_bootstrap().loader_step(1)

    def test_child_request_is_inspection_only(self):
        demo = c_demo_main_bootstrap()
        self.assertEqual(DEMO_MAIN_CHILD_CHOICES, (4, 7, 8, 9))
        for index, app_id in enumerate(DEMO_MAIN_CHILD_CHOICES):
            with self.subTest(index=index):
                child = demo.inspect_child(index)
                self.assertEqual(child['requested_child_id'], app_id)
                self.assertEqual(child['request_address'], 0x3dfbd0)
                self.assertFalse(child['executed'])
                self.assertFalse(child['automatic_selection_proven'])
                if app_id == 4:
                    self.assertEqual(child['registered_class'], 'CAppLogoMain')
                elif app_id == 7:
                    self.assertEqual(child['registered_class'], 'CAppDemoMovie')
                elif app_id == 8:
                    self.assertEqual(child['registered_class'], 'CAppDemoMain')
                else:
                    self.assertEqual(child['registered_class'], 'CAppDemoPlay')
        for index in (-1, 4, True, '0'):
            with self.subTest(index=index):
                with self.assertRaises(ValueError):
                    demo.inspect_child(index)
        self.assertFalse(demo.snapshot()['handoff_requested'])

    def test_user_owned_original_elf_oracle_if_supplied(self):
        path = os.environ.get('SDBZ_EU_BETA_ELF')
        if not path:
            self.skipTest('exact user-owned EU-beta ELF not in CI')
        data = Path(path).read_bytes()
        result = verify_app_registry_elf(data)
        self.assertEqual(result['title_handoff']['destination'], 'CAppDemoMain')
        self.assertEqual(result['title_handoff']['next_child_choices'],
                         [4, 7, 8, 9])
        self.assertEqual(result['registered_count'], APP_REGISTRY_COUNT)
        self.assertEqual(sorted(result['registered_ids']), list(range(1, 48)))
        self.assertEqual(len(result['registered']), 47)
        from arika_native_app_extract import verify as verify_complete_metadata
        from arika_app_registry import APP_NATIVE_REGISTRY
        self.assertEqual(verify_complete_metadata(data, APP_NATIVE_REGISTRY)
                         ['verified_applications'], 47)
        self.assertEqual(sorted(recover_registered_app_ids_elf(data)),
                         list(range(1, 48)))
        catalog = {app['id']: app for app in result['registered']}
        self.assertEqual(catalog[1]['class_name'], 'CAppWarning')
        self.assertEqual(catalog[42]['class_name'], 'CAppMenuMain')
        self.assertEqual(catalog[43]['class_name'], 'CAppShenronMain')
        self.assertEqual(catalog[6]['class_name'], 'CAppDemoMain')
        proc = subprocess.run([
            sys.executable,
            str(Path(__file__).with_name('arika_app_registry.py')), path,
        ], capture_output=True, text=True, check=True)
        self.assertIn('CAppDemoMain', proc.stdout)

    def test_wrong_elf_rejected(self):
        with self.assertRaisesRegex(ValueError, 'exact EU-beta'):
            verify_app_registry_elf(b'mismatched')


if __name__ == '__main__':
    unittest.main()
