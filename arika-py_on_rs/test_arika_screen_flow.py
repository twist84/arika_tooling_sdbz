"""Asset-free cross-platform tests of the six-screen integrated editor tour."""
import json
from pathlib import Path
import tempfile
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import shiboken6
import unittest

from PySide6 import QtWidgets as W

from arika_app_registry import resolve_app, APP_ENTRIES
from arika_native_ee_trace import TRACE_FORMAT, ELF_SHA256, ROOT_SLOT
from arika_screen_flow import (
    SCREEN_SEQUENCE, SCREEN_TAB_ORDER, SCREEN_APP_IDS, SCREEN_LABELS,
    NATIVE_VIEW_ROUTES, OBSERVED_SCREEN_COMPLETIONS,
    native_request_sites, native_dynamic_request_sites,
    native_view_request, observed_screen_completion, screen_step,
)
from arika_screen_flow_preview import c_native_screen_flow
from arika_logo_preview import c_logo_preview
from arika_warning_preview import c_warning_preview
from arika_title_preview import c_title_preview
from arika_press_start_preview import c_press_start_preview
from arika_demo_main_preview import c_demo_main_preview
from arika_menu_editor import c_menu_editor


class ScreenFlowModelTests(unittest.TestCase):
    def test_editor_order_is_not_claimed_native_order(self):
        self.assertEqual(SCREEN_SEQUENCE, (
            'warning', 'startup', 'title', 'press_start', 'main_menu'))
        self.assertEqual(SCREEN_TAB_ORDER, SCREEN_SEQUENCE + ('demo',))
        self.assertIsNone(screen_step('demo', 1))
        self.assertIsNone(screen_step('demo', -1))
        self.assertEqual(SCREEN_APP_IDS['startup'], 4)
        self.assertEqual(SCREEN_APP_IDS['warning'], 5)
        self.assertEqual(SCREEN_APP_IDS['title'], 2)
        self.assertEqual(SCREEN_APP_IDS['demo'], 6)
        self.assertEqual(SCREEN_APP_IDS['press_start'], 3)
        self.assertEqual(SCREEN_APP_IDS['main_menu'], 42)
        for i, screen in enumerate(SCREEN_SEQUENCE):
            self.assertIsNotNone(SCREEN_LABELS[screen])
            self.assertEqual(screen_step(screen, 1),
                             SCREEN_SEQUENCE[i + 1]
                             if i + 1 < len(SCREEN_SEQUENCE) else None)
            self.assertEqual(screen_step(screen, -1),
                             SCREEN_SEQUENCE[i - 1] if i else None)
        with self.assertRaises(ValueError):
            screen_step('wrong', 1)

    def test_recovered_app_requests_and_user_observed_handoffs(self):
        self.assertEqual(NATIVE_VIEW_ROUTES, {
            ('warning', 1): 'startup',
            ('press_start', 42): 'main_menu',
            ('title', 6): 'demo',
            ('demo', 3): 'press_start',
            ('press_start', 6): 'demo',
            ('main_menu', 3): 'press_start',
        })
        for (source, app_id), screen in NATIVE_VIEW_ROUTES.items():
            with self.subTest(source=source, target=app_id):
                result = native_view_request(source, app_id)
                self.assertEqual(result['destination'], screen)
                self.assertTrue(result['verified_preview_route'])
                self.assertFalse(result['factory_executed'])
                self.assertEqual(resolve_app(app_id)['id'], app_id)
        for source, app_id in (
                ('startup', 5), ('demo', 7), ('warning', 42)):
            result = native_view_request(source, app_id)
            self.assertIsNone(result['destination'])
            self.assertFalse(result['verified_preview_route'])
            self.assertFalse(result['factory_executed'])
        self.assertEqual(
            native_view_request('warning', 1)['app_class'],
            'CAppWarning')
        self.assertEqual(
            native_view_request('press_start', 42)['app_class'],
            'CAppMenuMain')
        self.assertIn(0x3F786C, native_request_sites('press_start', 42))
        self.assertIn(0x41F070, native_request_sites('warning', 1))
        self.assertIn(0x3F89C8, native_request_sites('title', 6))
        self.assertIn(0x3FE21C, native_request_sites('main_menu', 3))
        self.assertEqual(native_request_sites('demo', 3), ())
        self.assertTrue(native_view_request('press_start', 42)
                        ['native_literal_edge_confirmed'])
        self.assertEqual(native_view_request('title', 6)
                         ['native_source_class'], 'CAppCRISofdec')
        self.assertEqual(native_view_request('warning', 1)
                         ['native_source_class'], 'CAppMonitorSelect')
        self.assertEqual(
            native_view_request('press_start', 42)['provenance'],
            'user-observed visual transition plus native request ID')
        self.assertFalse(native_view_request('demo', 3)
                         ['provisional_parent_return'])
        self.assertFalse(native_view_request('demo', 3)
                         ['native_literal_edge_confirmed'])
        self.assertTrue(native_view_request('demo', 3)
                        ['native_dynamic_edge_confirmed'])
        self.assertEqual(native_dynamic_request_sites('demo', 3),
                         (0x3E09E0,))
        self.assertEqual(native_dynamic_request_sites('demo', 6),
                         (0x3E09E0,))
        self.assertEqual(native_dynamic_request_sites('press_start', 42),
                         ())
        self.assertTrue(native_view_request('demo', 3)
                        ['native_source_attribution_verified'])
        self.assertIn('ELF-verified conditional',
                      native_view_request('demo', 3)['provenance'])
        self.assertFalse(native_view_request('warning', 1)
                         ['native_source_attribution_verified'])
        self.assertFalse(native_view_request('press_start', 42)
                         ['provisional_parent_return'])
        self.assertEqual(OBSERVED_SCREEN_COMPLETIONS,
                         {'startup': 'title'})
        logo = observed_screen_completion('startup')
        self.assertIsNone(logo['destination_id'])
        self.assertEqual(logo['destination'], 'title')
        self.assertFalse(logo['factory_executed'])
        self.assertIsNone(observed_screen_completion('warning'))
        with self.assertRaises(ValueError):
            native_view_request('missing', 6)
        with self.assertRaises(ValueError):
            native_view_request('press_start', True)


class ScreenFlowWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m_app = W.QApplication.instance() or W.QApplication([])

    def setUp(self):
        self.m_tabs = W.QTabWidget()
        self.m_views = {
            'main_menu': c_menu_editor(),
            'startup': c_logo_preview(),
            'warning': c_warning_preview(),
            'title': c_title_preview(),
            'press_start': c_press_start_preview(),
            'demo': c_demo_main_preview(),
        }
        for screen in (
                'main_menu', 'startup', 'warning',
                'title', 'press_start', 'demo'):
            self.m_tabs.addTab(self.m_views[screen], SCREEN_LABELS[screen])
        self.m_flow = c_native_screen_flow(self.m_tabs, self.m_views)
        self.m_tabs.resize(1000, 640)
        self.m_tabs.show()
        self.m_app.processEvents()

    def tearDown(self):
        self.m_flow.pause_playback()
        self.m_tabs.close()
        self.m_flow.close()
        if shiboken6.isValid(self.m_tabs):
            shiboken6.delete(self.m_tabs)
        if shiboken6.isValid(self.m_flow):
            shiboken6.delete(self.m_flow)
        self.m_app.processEvents()

    def test_import_original_ee_trace_does_not_switch_or_run_previews(self):
        flow = self.m_flow
        flow.start_tour()
        before = flow.active_screen()
        sample = {
            'format': TRACE_FORMAT,
            'elf_sha256': ELF_SHA256,
            'source': 'synthetic-test-fixture',
            'events': [
                {'sequence': 1, 'kind': 'factory_dispatch',
                 'pc': '0x3f1be0', 'registers': {
                     's0': 3, 'v0': APP_ENTRIES[3]['factory']}},
                {'sequence': 2, 'kind': 'factory_entry',
                 'pc': APP_ENTRIES[3]['factory'],
                 'registers': {'ra': '0x3f1be8'}},
                {'sequence': 3, 'kind': 'factory_return',
                 'pc': '0x3f1be8', 'registers': {'v0': '0x123450'}},
                {'sequence': 4, 'kind': 'root_write',
                 'store_pc': '0x3f1c04', 'address': ROOT_SLOT,
                 'value': '0x123450',
                 'registers': {'a0': '0x123450'},
                 'post_write': True},
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'observations.json'
            path.write_text(json.dumps(sample), encoding='utf-8')
            result = flow.import_ee_trace(path)
            self.assertIsNotNone(result)
            self.assertEqual(result['factory_entry_count'], 1)
            self.assertEqual(result['root_write_count'], 1)
            self.assertIs(flow.m_trace_summary, result)
            self.assertIn('synthetic fixture', flow.m_status.text())
            self.assertIn('No screen transition', flow.m_status.text())
            self.assertEqual(flow.active_screen(), before)
            self.assertFalse(flow.m_runner_timer.isActive())
            self.assertTrue(flow.m_import_ee_trace.isEnabled())
            # Rejected input cannot fabricate new trace evidence.
            path.write_text('{"format": "invalid"}', encoding='utf-8')
            self.assertIsNone(flow.import_ee_trace(path))
            self.assertIn('EE trace rejected', flow.m_status.text())
            self.assertIs(flow.m_trace_summary, result)
            self.assertEqual(flow.active_screen(), before)

    def test_manual_preview_tour_uses_existing_widgets_without_loading_art(self):
        flow = self.m_flow
        self.assertEqual(flow.start_tour(), 'warning')
        self.assertIs(self.m_tabs.currentWidget(), self.m_views['warning'])
        self.assertIn('Annotated preview order', flow.m_status.text())
        self.assertEqual(flow.next_preview(), 'startup')
        self.assertEqual(flow.next_preview(), 'title')
        self.assertEqual(flow.next_preview(), 'press_start')
        self.assertEqual(flow.next_preview(), 'main_menu')
        self.assertIsNone(flow.next_preview())
        self.assertEqual(flow.previous_preview(), 'press_start')
        self.assertIn('Manual preview jump', flow.m_status.text())
        self.assertFalse(flow.m_runner_timer.isActive())
        self.assertTrue(all(not v.m_timer.isActive() for name, v in
                            self.m_views.items() if name in (
                                'startup', 'warning', 'title', 'press_start')))
        self.assertEqual(self.m_views['startup'].m_images, (None, None, None))

    def test_actual_tabs_match_annotated_order_and_preserve_widgets(self):
        self.assertEqual(self.m_tabs.count(), len(SCREEN_TAB_ORDER))
        self.assertEqual(
            tuple(self.m_tabs.widget(i) for i in range(self.m_tabs.count())),
            tuple(self.m_views[screen] for screen in SCREEN_TAB_ORDER))
        self.assertEqual(
            tuple(self.m_tabs.tabText(i) for i in range(self.m_tabs.count())),
            tuple(SCREEN_LABELS[screen] for screen in SCREEN_TAB_ORDER))
        self.assertEqual(
            tuple(SCREEN_SEQUENCE), (
                'warning', 'startup', 'title', 'press_start', 'main_menu'))

    def test_demo_main_remains_a_separate_inspector_not_sixth_step(self):
        flow = self.m_flow
        self.m_tabs.setCurrentWidget(self.m_views['demo'])
        self.assertFalse(flow.m_previous.isEnabled())
        self.assertFalse(flow.m_next.isEnabled())
        self.assertIsNone(flow.next_preview())
        self.assertIsNone(flow.previous_preview())
        self.assertIn('Demo Main', flow.m_status.text())
        route = flow.route_native('demo', 3)
        self.assertEqual(route['destination'], 'press_start')
        self.assertEqual(flow.active_screen(), 'press_start')

    def test_title_native_request_preserves_demo_handoff_then_shows_press_start(self):
        flow = self.m_flow
        flow.start_tour()
        flow.next_preview()  # startup: editor-only manual jump
        flow.next_preview()  # title: editor-only manual jump
        title = self.m_views['title']
        flow.advance_active(0.0)
        flow.advance_active(5.0)
        flow.advance_active(0.0)
        self.assertIs(self.m_tabs.currentWidget(), self.m_views['press_start'])
        self.assertTrue(self.m_views['demo'].m_bootstrap.snapshot()
                        ['handoff_requested'])
        self.assertFalse(self.m_views['demo'].m_bootstrap.snapshot()
                         ['constructor_executed'])
        self.assertIn('native app ID 6', flow.m_status.text())
        self.assertIn('Press Start', flow.m_status.text())
        self.assertIn('NOT executed', flow.m_status.text())
        self.assertFalse(flow.m_runner_timer.isActive())
        self.assertTrue(title.m_runtime.snapshot()['finished'])

    def test_title_handoff_must_have_finished_request_proof(self):
        flow = self.m_flow
        flow._navigate('title', 'test')
        result = flow.route_native('title', 6, result=None)
        self.assertIsNone(result['destination'])
        self.assertIs(flow.m_tabs.currentWidget(), self.m_views['title'])
        self.assertFalse(self.m_views['demo'].m_bootstrap.snapshot()
                         ['handoff_requested'])

    def test_press_start_native_id_42_enters_registered_main_menu(self):
        flow = self.m_flow
        flow._navigate('press_start', 'test')
        flow.advance_active(0.0)
        self.m_views['press_start'].press_start_0()
        flow.advance_active(0.0)
        flow.advance_active(0.0)
        self.assertEqual(self.m_views['press_start'].m_runtime.snapshot()
                         ['destination_id'], 42)
        self.assertIs(self.m_tabs.currentWidget(), self.m_views['main_menu'])
        self.assertIn('ID 42', flow.m_status.text())
        self.assertIn('CAppMenuMain', native_view_request(
            'press_start', 42)['app_class'])
        self.assertFalse(flow.m_runner_timer.isActive())

    def test_press_start_attract_request_can_show_demo_main(self):
        flow = self.m_flow
        flow._navigate('press_start', 'test')
        flow.advance_active(20.0)
        flow.advance_active(0.0)
        self.assertEqual(flow.active_screen(), 'demo')
        self.assertIn('ID 6', flow.m_status.text())
        self.assertFalse(flow.m_runner_timer.isActive())

    def test_warning_to_game_completed_id_one_opens_startup_splash(self):
        flow = self.m_flow
        flow._navigate('warning', 'test')
        flow.advance_active(0.0)
        self.assertFalse(flow.m_runner_timer.isActive())
        self.assertIn('interactive', flow.m_status.text())
        warning = self.m_views['warning']
        warning.m_previous.click()  # original choice index 3: To Game
        self.assertEqual(warning.m_runtime.snapshot()['selection'], 3)
        warning.m_confirm.click()
        self.assertTrue(flow.m_runner_timer.isActive(),
                        'To Game should automatically continue exit fade')
        flow.advance_active(0.0)
        flow.advance_active(0.0)
        self.assertEqual(flow.active_screen(), 'startup')
        self.assertTrue(warning.m_runtime.snapshot()['finished'])
        self.assertIn('ID 1', flow.m_status.text())
        self.assertTrue(flow.m_runner_timer.isActive(),
                        'running flow should continue into startup splash')

    def test_startup_logo_completion_opens_title_screen(self):
        flow = self.m_flow
        flow._navigate('startup', 'test')
        logo = self.m_views['startup']
        for index in range(3):
            logo.m_delta.setValue(0.0)
            logo.m_step.click()  # phase 0 -> 1 -> 2
            logo.m_delta.setValue(2.0)
            logo.m_step.click()  # original 2-second sprite gate -> 3
            logo.m_delta.setValue(0.0)
            logo.m_step.click()  # 3 -> 4, or final 3 -> 10
            if index < 2:
                logo.m_step.click()  # 4 -> 5
                logo.m_delta.setValue(2.0)
                logo.m_step.click()  # 5 -> 0 after native pause
            else:
                logo.m_step.click()  # 10 returns original completion
        self.assertTrue(logo.m_runtime.snapshot()['finished'])
        self.assertEqual(flow.active_screen(), 'title')
        self.assertIn('Observed', flow.m_status.text())
        self.assertIn('Title Screen', flow.m_status.text())

    def test_standalone_screen_buttons_route_completed_native_callbacks(self):
        flow = self.m_flow
        flow._navigate('title', 'test')
        title = self.m_views['title']
        title.m_step.click()
        title.m_delta.setValue(5.0)
        title.m_step.click()
        title.m_step.click()
        self.assertTrue(title.m_runtime.snapshot()['finished'])
        self.assertEqual(flow.active_screen(), 'press_start')
        press = self.m_views['press_start']
        press.m_start_0.click()
        self.assertTrue(flow.m_runner_timer.isActive(),
                        'original Start should continue the exit fade')
        flow.advance_active(0.0)
        flow.advance_active(0.0)
        self.assertEqual(flow.active_screen(), 'main_menu')
        self.assertEqual(press.m_runtime.snapshot()['destination_id'], 42)
        self.assertFalse(flow.m_runner_timer.isActive())

    def test_manual_title_inspect_still_opens_demo_inspector(self):
        flow = self.m_flow
        flow._navigate('title', 'test')
        title = self.m_views['title']
        title.m_runtime.step(0.0, False)
        title.m_runtime.step(5.0, False)
        result = title.m_runtime.step(0.0, False)
        route = flow.route_native('title', 6, result=result)
        self.assertEqual(route['destination'], 'demo')
        self.assertEqual(flow.active_screen(), 'demo')
        self.assertTrue(self.m_views['demo'].m_bootstrap.snapshot()
                        ['handoff_requested'])

    def test_diagnostic_main_menu_cancel_routes_back_to_press_start(self):
        flow = self.m_flow
        flow._navigate('main_menu', 'test')
        result = flow.menu_cancel()
        self.assertEqual(result['destination'], 'press_start')
        self.assertEqual(flow.active_screen(), 'press_start')
        self.assertIn('ID 3', flow.m_status.text())

    def test_hidden_timers_and_archive_changes_stop_shared_runner(self):
        flow = self.m_flow
        flow.start_tour()
        flow.m_play.click()
        self.assertTrue(flow.m_runner_timer.isActive())
        self.m_tabs.setCurrentWidget(self.m_views['startup'])
        self.assertFalse(flow.m_runner_timer.isActive())
        self.assertIn('Selected directly', flow.m_status.text())
        flow.m_play.click()
        self.assertTrue(flow.m_runner_timer.isActive())
        flow.archive_changed()
        self.assertFalse(flow.m_runner_timer.isActive())
        self.assertIn('Archive changed', flow.m_status.text())
        self.assertFalse(self.m_views['warning'].m_timer.isActive())

    def test_runner_pauses_for_unimplemented_demo_and_menu_update(self):
        flow = self.m_flow
        flow._navigate('demo', 'test')
        self.assertFalse(flow.m_play.isEnabled())
        self.assertIsNone(flow.advance_active(0.0))
        self.assertIn('no supported common timed update',
                      flow.m_status.text())
        flow._navigate('main_menu', 'test')
        self.assertFalse(flow.m_play.isEnabled())
        self.assertFalse(flow.m_step.isEnabled())
        with self.assertRaises(ValueError):
            flow.advance_active(float('nan'))


if __name__ == '__main__':
    unittest.main()
