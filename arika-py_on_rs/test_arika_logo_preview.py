"""Asset-free offscreen Qt tests for the separate logo preview."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
import struct
import tempfile
import unittest

from PySide6 import QtGui as G, QtWidgets as W

from arika_logo_preview import (
    c_logo_preview, decode_logo_texture, load_logo_images,
    load_logo_archive_images, render_logo_image,
)
from arika_logo_resources import LOGO_RESOURCE_NAMES, logo_asset_paths


def synthetic_tim2_rgba32(width=512, height=512):
    rgba = bytes((111, 42, 191, 128)) * (width * height)
    header = (struct.pack('<4sBBH', b'TIM2', 4, 0, 1) + bytes(8))
    size = 48 + len(rgba)
    picture = struct.pack('<IIIHHBBBBHH',
                          size, 0, len(rgba), 48, 0, 0, 1, 0, 3,
                          width, height)
    return header + picture + bytes(48 - len(picture)) + rgba


def synthetic_fpix(*textures):
    count = len(textures)
    bodies = []
    for tex in textures:
        chunk = b'XPIX' + struct.pack('<I', 32 + len(tex)) + bytes(24) + tex
        bodies.append(chunk)
    directory_offset = 32 + count * 4
    offsets = []
    position = directory_offset
    for chunk in bodies:
        offsets.append(position)
        position += len(chunk)
    return (b'FPIX' + struct.pack('<III', position, count, 1) + bytes(16) +
            struct.pack('<' + 'I' * count, *offsets) + b''.join(bodies))


class LogoPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m_app = W.QApplication.instance() or W.QApplication([])

    def test_rgba32_original_asset_decoder(self):
        img = decode_logo_texture(synthetic_tim2_rgba32())
        self.assertEqual((img.width(), img.height()), (512, 512))
        pixel = img.pixelColor(0, 0)
        self.assertEqual((pixel.red(), pixel.green(), pixel.blue()),
                         (111, 42, 191))
        self.assertEqual(pixel.alpha(), 255)

    def test_one_entry_fpix_decodes_without_guessing_index(self):
        img = decode_logo_texture(synthetic_fpix(synthetic_tim2_rgba32()))
        self.assertEqual((img.width(), img.height()), (512, 512))
        self.assertEqual(img.pixelColor(200, 200).red(), 111)

    def test_ambiguous_or_unsupported_asset_rejected(self):
        with self.assertRaises(ValueError):
            decode_logo_texture(b'not a texture')
        with self.assertRaises(ValueError):
            decode_logo_texture(synthetic_fpix(
                synthetic_tim2_rgba32(), synthetic_tim2_rgba32()))
        with self.assertRaises(ValueError):
            decode_logo_texture(synthetic_tim2_rgba32(8, 8))

    def test_render_exact_512_by_448_target(self):
        original = G.QImage(512, 512, G.QImage.Format.Format_ARGB32)
        original.fill(G.QColor(0, 0, 255))
        img = render_logo_image(original)
        self.assertEqual((img.width(), img.height()), (512, 448))
        self.assertEqual(img.pixelColor(256, 224).blue(), 255)
        self.assertEqual(img.pixelColor(511, 447).blue(), 255)
        with self.assertRaises(ValueError):
            render_logo_image(G.QImage())

    def test_missing_assets_do_not_get_png_substitutes(self):
        with tempfile.TemporaryDirectory() as root:
            name = logo_asset_paths(root)[1]
            name.parent.mkdir(parents=True)
            name.write_bytes(synthetic_tim2_rgba32())
            images, errors = load_logo_images(root)
            self.assertIsNone(images[0])
            self.assertIsNotNone(images[1])
            self.assertIsNone(images[2])
            self.assertIn(LOGO_RESOURCE_NAMES[0], errors[0])
            self.assertIsNone(errors[1])

    def test_separate_qt_widget_stepping_matches_next_update_gate(self):
        texture = G.QImage(512, 512, G.QImage.Format.Format_ARGB32)
        texture.fill(G.QColor(10, 70, 140))
        widget = c_logo_preview([texture, None, None],
                                [None, 'missing', 'missing'])
        self.assertIsNotNone(widget.m_canvas.pixmap())
        self.assertFalse(widget.m_canvas.pixmap().isNull())
        widget.m_step.click()
        self.assertEqual(widget.m_runtime.snapshot()['phase'], 2)
        widget.m_delta.setValue(2.0)
        widget.m_step.click()
        self.assertEqual(widget.m_runtime.snapshot()['phase'], 3)
        widget.m_delta.setValue(0.0)
        widget.m_step.click()
        self.assertEqual(widget.m_runtime.snapshot()['phase'], 4)
        widget.m_reset.click()
        self.assertEqual(widget.m_runtime.snapshot()['phase'], 0)
        widget.close()

    def test_archive_mapping_accepts_exact_and_pix_suffixed_native_keys(self):
        payload = synthetic_fpix(synthetic_tim2_rgba32())
        archive = {
            'DIS\\D03\\D03T0205.PIX': payload,
            '/dis/d03/d03t0203': payload,
            'dis/d03/d03t0202.pix': payload,
            'dis/main_menu.pix': b'ignored',
        }
        images, errors = load_logo_archive_images(archive)
        self.assertTrue(all(image is not None for image in images))
        self.assertEqual(errors, [None, None, None])
        self.assertEqual(images[0].pixelColor(0, 0).red(), 111)

    def test_archive_mapping_rejects_duplicate_and_wrong_native_assets(self):
        payload = synthetic_tim2_rgba32()
        images, errors = load_logo_archive_images({
            'dis/d03/d03t0205': payload,
            'dis/d03/d03t0205.pix': payload,
            'other/d03t0203.pix': payload,
            'dis/d03/d03t0202.pix': b'invalid',
        })
        self.assertIsNone(images[0])
        self.assertIn('ambiguous', errors[0])
        self.assertIsNone(images[1])
        self.assertIn('not found', errors[1])
        self.assertIsNone(images[2])
        self.assertIn('unsupported', errors[2])
        with self.assertRaises(TypeError):
            load_logo_archive_images([])

    def test_embedded_widget_clears_previous_archive_and_resets_clock(self):
        payload = synthetic_tim2_rgba32()
        widget = c_logo_preview()
        self.assertIsNone(widget.m_images[0])
        self.assertEqual(widget.load_archive_assets({
            'dis/d03/d03t0205.pix': payload,
        }), 1)
        self.assertIsNotNone(widget.m_canvas.pixmap())
        widget.m_step.click()
        self.assertEqual(widget.m_runtime.snapshot()['phase'], 2)
        self.assertEqual(widget.load_archive_assets({}), 0)
        self.assertEqual(widget.m_runtime.snapshot()['phase'], 0)
        self.assertTrue(all(image is None for image in widget.m_images))
        self.assertTrue(widget.m_canvas.pixmap() is None or
                        widget.m_canvas.pixmap().isNull())
        self.assertIn('not found', widget.m_status.text())
        widget.close()

    def test_embedded_tab_resizes_4_by_3_display(self):
        texture = G.QImage(512, 512, G.QImage.Format.Format_ARGB32)
        texture.fill(G.QColor(4, 9, 17))
        tabs = W.QTabWidget()
        widget = c_logo_preview([texture, None, None],
                                [None, 'missing', 'missing'])
        tabs.addTab(widget, 'Startup / Splash')
        tabs.resize(600, 540)
        tabs.show()
        self.m_app.processEvents()
        self.assertIsNotNone(widget.m_canvas.pixmap())
        pixmap = widget.m_canvas.pixmap()
        self.assertLessEqual(pixmap.width(), widget.m_canvas.width())
        self.assertLessEqual(pixmap.height(), widget.m_canvas.height())
        self.assertAlmostEqual(pixmap.width() / pixmap.height(), 4 / 3,
                               delta=0.02)
        tabs.close()

    def test_play_pause_keeps_phase_and_manual_step(self):
        widget = c_logo_preview()
        self.assertEqual(widget.m_play.text(), 'Play')
        self.assertFalse(widget.m_timer.isActive())

        widget.m_play.click()
        self.assertTrue(widget.m_timer.isActive())
        self.assertEqual(widget.m_play.text(), 'Pause')
        self.assertFalse(widget.m_step.isEnabled())

        # Invoke the actual Qt timeout signal without relying on OS timing.
        widget.m_timer.timeout.emit()
        self.assertEqual(widget.m_runtime.snapshot()['phase'], 2)
        updates = widget.m_runtime.snapshot()['updates']
        widget.m_step.click()
        self.assertEqual(widget.m_runtime.snapshot()['updates'], updates)

        widget.m_play.click()
        self.assertFalse(widget.m_timer.isActive())
        self.assertEqual(widget.m_play.text(), 'Play')
        self.assertTrue(widget.m_step.isEnabled())
        self.assertIn('paused', widget.m_status.text())

        widget.m_delta.setValue(2)
        widget.m_step.click()
        self.assertEqual(widget.m_runtime.snapshot()['phase'], 3)
        widget.m_delta.setValue(0)
        widget.m_step.click()
        self.assertEqual(widget.m_runtime.snapshot()['phase'], 4)
        widget.close()

    def test_playback_elapsed_delta_and_resume_reset_clock(self):
        widget = c_logo_preview()
        widget.m_play.click()
        self.assertEqual(widget.m_last_elapsed_ns, 0)
        # Simulate a delayed timer tick; wall-time jitter is accumulated,
        # never replaced with a fabricated 1/60-second native update.
        widget.m_last_elapsed_ns = -2_000_000_000
        widget.advance_playback()
        self.assertGreaterEqual(widget.m_runtime.snapshot()['age_seconds'], 0)
        self.assertEqual(widget.m_runtime.snapshot()['phase'], 2)
        widget.m_play.click()
        widget.m_play.click()
        self.assertEqual(widget.m_last_elapsed_ns, 0)
        widget.m_play.click()
        self.assertFalse(widget.m_timer.isActive())
        widget.close()

    def test_reset_and_new_archive_stop_playback(self):
        widget = c_logo_preview()
        widget.m_play.click()
        self.assertTrue(widget.m_timer.isActive())
        widget.m_reset.click()
        self.assertFalse(widget.m_timer.isActive())
        self.assertEqual(widget.m_play.text(), 'Play')
        self.assertEqual(widget.m_runtime.snapshot()['phase'], 0)
        widget.m_play.click()
        widget.load_archive_assets({})
        self.assertFalse(widget.m_timer.isActive())
        self.assertEqual(widget.m_runtime.snapshot()['updates'], 0)
        self.assertEqual(widget.m_play.text(), 'Play')
        widget.close()

    def test_sequence_completion_auto_pauses_and_disables_controls(self):
        widget = c_logo_preview()
        widget.m_play.click()
        widget.m_runtime.m_phase = 10
        widget.advance_native(0)
        self.assertFalse(widget.m_timer.isActive())
        self.assertTrue(widget.m_runtime.snapshot()['finished'])
        self.assertFalse(widget.m_play.isEnabled())
        self.assertFalse(widget.m_step.isEnabled())
        self.assertIn('complete', widget.m_status.text())
        widget.m_reset.click()
        self.assertFalse(widget.m_runtime.snapshot()['finished'])
        self.assertTrue(widget.m_play.isEnabled())
        widget.close()

    def test_switching_tabs_pauses_hidden_logo_view(self):
        tabs = W.QTabWidget()
        widget = c_logo_preview()
        tabs.addTab(widget, 'Startup / Splash')
        tabs.addTab(W.QWidget(), 'Main menu')
        tabs.resize(800, 600)
        tabs.show()
        self.m_app.processEvents()
        widget.m_play.click()
        self.assertTrue(widget.m_timer.isActive())
        tabs.setCurrentIndex(1)
        self.m_app.processEvents()
        self.assertFalse(widget.m_timer.isActive())
        self.assertEqual(widget.m_play.text(), 'Play')
        tabs.close()


if __name__ == '__main__':
    unittest.main()
