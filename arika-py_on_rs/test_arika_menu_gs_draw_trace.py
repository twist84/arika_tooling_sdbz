"""Asset-free GS draw-state trace regressions."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from arika_menu_gs_draw_trace import (
    TRACE_FORMAT, analyze_trace,
)


def report(*events):
    return analyze_trace({
        'format': TRACE_FORMAT,
        'version': 1,
        'events': list(events),
    })


def write(address, value):
    return {'kind': 'write', 'address': address, 'value': value}


def draw(context, label=None):
    return {'kind': 'draw', 'context': context, 'label': label}


class GsDrawTraceTests(unittest.TestCase):
    def test_missing_register_writes_remain_unknown(self):
        result = report(draw(1, 'original'))
        self.assertEqual(result['write_events'], 0)
        self.assertEqual(result['draw_events'], 1)
        sample = result['draws'][0]
        self.assertEqual(sample['event_index'], 0)
        self.assertEqual(sample['label'], 'original')
        self.assertEqual(sample['sampling']['status'], 'unknown')
        self.assertIsNone(sample['sampling']['magnification'])
        self.assertIsNone(sample['sampling']['minification'])
        self.assertTrue(all(value is None
                            for value in sample['registers'].values()))
        self.assertTrue(all(value is None
                            for value in sample['fields'].values()))

    def test_independent_contexts_and_global_texa(self):
        result = report(
            write('0x14', '0x60'),  # TEX1_1, bilinear without mipmaps
            write(0x3b, 0x8000000000),  # global TEXA
            write(0x47, 0x0005000f),  # TEST_1
            draw(1, 'first'),
            draw(2, 'other context'),
            write(0x15, 0),  # TEX1_2, nearest
            write(0x43, 0x44),  # ALPHA_2
            draw(2),
            draw(1, 'still context 1'),
        )
        first, other, next_other, later = result['draws']
        self.assertEqual(first['sampling']['status'], 'captured')
        self.assertEqual(first['sampling']['magnification'], 'linear')
        self.assertEqual(first['sampling']['minification'], 'linear')
        self.assertEqual(first['fields']['texa']['ta1'], 0x80)
        self.assertEqual(first['fields']['test']['ate'], 1)
        self.assertEqual(first['registers']['tex1'], '0x60')
        self.assertIsNone(other['registers']['tex1'])
        self.assertEqual(other['sampling']['status'], 'unknown')
        self.assertEqual(other['registers']['texa'], first['registers']['texa'])
        self.assertEqual(next_other['sampling']['magnification'], 'nearest')
        self.assertEqual(next_other['sampling']['minification'], 'nearest')
        self.assertEqual(next_other['fields']['alpha']['fix'], 0)
        self.assertEqual(later['registers']['tex1'], '0x60')
        self.assertIsNone(later['registers']['alpha'])
        self.assertEqual(result['write_events'], 5)
        self.assertEqual(result['draw_events'], 4)

    def test_tex1_minification_codes_not_reduced_to_one_bilinear_bit(self):
        modes = (
            'nearest', 'linear', 'nearest_mipmap_nearest',
            'nearest_mipmap_linear', 'linear_mipmap_nearest',
            'linear_mipmap_linear', 'reserved_6', 'reserved_7',
        )
        events = []
        for value in range(8):
            events.extend((write(0x14, value << 6), draw(1)))
        result = report(*events)
        self.assertEqual([d['sampling']['minification'] for d in result['draws']],
                         list(modes))
        self.assertTrue(all(d['sampling']['magnification'] == 'nearest'
                            for d in result['draws']))

    def test_unrelated_writes_do_not_infer_sampler_state(self):
        result = report(write(0x71, 0), write(0x06, 0x100),
                        draw(1), draw(2))
        self.assertEqual(result['unreported_register_types'], 1)
        self.assertEqual(result['draws'][0]['fields']['tex0']['tbp0'], 0x100)
        self.assertEqual(result['draws'][0]['sampling']['status'], 'unknown')
        self.assertIsNone(result['draws'][1]['fields']['tex0'])

    def test_invalid_trace_and_context_rejected(self):
        bad = [
            None, {}, {'format': TRACE_FORMAT, 'version': True, 'events': []},
            {'format': TRACE_FORMAT, 'version': 2, 'events': []},
            {'format': TRACE_FORMAT, 'version': 1, 'events': {}},
        ]
        for item in bad:
            with self.subTest(item=item), self.assertRaises(ValueError):
                analyze_trace(item)
        for context in (0, 3, True, '1', None):
            with self.subTest(context=context), self.assertRaises(ValueError):
                report(draw(context))
        with self.assertRaises(ValueError):
            report({'kind': 'frame_end'})
        with self.assertRaises(ValueError):
            report('unexpected')
        with self.assertRaises(ValueError):
            report({'kind': 'draw', 'context': 1, 'label': 123})

    def test_rejects_register_overflow_and_noninteger_values(self):
        for address, value in (
            (128, 0), (-1, 0), (True, 0), ('0xGG', 0),
            (0x14, -1), (0x14, 1 << 64), (0x14, False),
            (0x14, 0.5), (0x14, 'not a number'),
        ):
            with self.subTest(address=address, value=value):
                with self.assertRaises(ValueError):
                    report(write(address, value))

    def test_json_cli_roundtrip_without_proprietary_data(self):
        data = {'format': TRACE_FORMAT, 'version': 1,
                'events': [write(0x14, 0x60), draw(1, 'synthetic')]}
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'trace.json'
            source.write_text(json.dumps(data), encoding='utf-8')
            executable = Path(__file__).with_name('arika_menu_gs_draw_trace.py')
            output = subprocess.run(
                [sys.executable, str(executable), str(source)],
                text=True, capture_output=True, check=True)
            result = json.loads(output.stdout)
            self.assertEqual(result['draws'][0]['sampling']['status'], 'captured')
            self.assertEqual(result['draws'][0]['label'], 'synthetic')
            self.assertIn('not GS rasterization', result['limitations'][-1])


if __name__ == '__main__':
    unittest.main()
