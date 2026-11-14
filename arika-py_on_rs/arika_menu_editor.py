"""Native 2D preview/editor for the recovered Super Dragon Ball Z menu."""
import base64
import json
import math
import re
from pathlib import Path

from PySide6 import QtCore as C, QtGui as G, QtWidgets as W

from arika_menu_navigation import c_menu_navigation, MENU_ITEM_NAMES, DIRECTION_NAMES, DIRECTION_MASKS
from arika_menu_selection_effect import EMPHASIS_DURATION, emphasis_geometry, emphasis_sample
from arika_menu_arrow_preview import arrow_parts, bobbed_arrow_geometry
from arika_menu_navigation import read_menu_report
import arika_ffon
from arika_menu_frame_match import normalize_reference, rank_samples
from PIL import Image


def lerp_values(a, b, t):
    if isinstance(a, bool) or isinstance(b, bool):
        return a
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a + (b - a) * t
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        if a and isinstance(a[0], (int, float)) and not isinstance(a[0], bool):
            return [a[i] + (b[i] - a[i]) * t for i in range(len(a))]
        return [lerp_values(a[i], b[i], t) for i in range(len(a))]
    if isinstance(a, dict) and isinstance(b, dict):
        out = {}
        for key in a:
            if key in b:
                if key in ('texture_entry', 'depth', 'uv_endpoints', 'tick', 'entry'):
                    out[key] = a[key]
                else:
                    out[key] = lerp_values(a[key], b[key], t)
            else:
                out[key] = a[key]
        return out
    return a


def interpolate_frames(f0, f1, frac):
    if frac <= 0:
        return f0
    if frac >= 1:
        return f1
    return lerp_values(f0, f1, frac)


class c_menu_canvas(W.QWidget):
    def __init__(self, editor):
        super().__init__()
        self.m_editor = editor
        self.setFocusPolicy(C.Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(0, 0)
        self.setSizePolicy(W.QSizePolicy.Policy.Expanding, W.QSizePolicy.Policy.Expanding)

    def paintEvent(self, event):
        painter = G.QPainter(self)
        self.m_editor.render(painter, self.rect())
        painter.end()

    def mousePressEvent(self, event):
        self.setFocus(C.Qt.FocusReason.MouseFocusReason)
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        # Key mapping is a preview convenience, not a controller trace.
        directions = {
            C.Qt.Key.Key_Right: 0, C.Qt.Key.Key_Left: 1,
            C.Qt.Key.Key_Up: 2, C.Qt.Key.Key_Down: 3,
        }
        direction = directions.get(event.key())
        if direction is not None:
            self.m_editor.navigate(direction)
        elif event.key() in (C.Qt.Key.Key_Return, C.Qt.Key.Key_Enter):
            self.m_editor.inspect_route(False)
        elif event.key() == C.Qt.Key.Key_Escape:
            self.m_editor.inspect_route(True)
        else:
            super().keyPressEvent(event)
            return
        event.accept()


class c_menu_editor(W.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.m_data = None
        self.m_textures = {}
        self.m_help_panel_uv = None
        self.m_presentation = 'tv_4_3'
        self.m_scan_mode = 'interlaced'
        self.m_time = 70.0
        self.m_item = 0
        self.m_navigation = c_menu_navigation()
        self.m_menu_report = read_menu_report()
        self.m_help_font = None
        self.m_help_font_data = None
        self.m_help_lines_pixmaps = {}
        self.m_reference_matches = []
        self.m_reference_match_index = 0
        self.m_selection_age = None
        self.m_selection_effect = True
        self.m_playing = False
        self.m_timer = C.QTimer(self)
        self.m_timer.timeout.connect(self.advance)
        self.m_timer.setInterval(1000 // 60)

        self.m_background = True
        self.m_motion = True
        self.m_tint = True
        self.m_first = True
        self.m_middle = True
        self.m_overlay = True
        self.m_idle = True
        self.m_character_motion = True
        self.m_label_motion = True
        self.m_arrows = True
        self.m_arrow_bob = True
        self.m_help_panel = True
        self.m_bounds = False
        self.m_smooth = True

        layout = W.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        controls = W.QHBoxLayout()
        self.m_item_combo = W.QComboBox()
        for i, name in enumerate(MENU_ITEM_NAMES):
            self.m_item_combo.addItem('%d %s' % (i, name))
        self.m_item_combo.currentIndexChanged.connect(self.set_item)
        controls.addWidget(W.QLabel('Item'))
        controls.addWidget(self.m_item_combo)

        self.m_play_button = W.QPushButton('Play')
        self.m_play_button.clicked.connect(self.toggle_play)
        controls.addWidget(self.m_play_button)

        self.m_rate_combo = W.QComboBox()
        for rate in ('0.01', '0.05', '0.10', '0.15', '0.25', '0.5', '1', '2'):
            self.m_rate_combo.addItem(rate + 'x', float(rate))
        self.m_rate_combo.setCurrentIndex(2)
        self.m_rate_combo.currentIndexChanged.connect(self.update_timer)
        controls.addWidget(W.QLabel('Rate'))
        controls.addWidget(self.m_rate_combo)

        # PCSX2-style display choices are presentation only. The active GS
        # video mode has not yet been observed in a running main menu.
        self.m_presentation_combo = W.QComboBox()
        for title, mode in (
            ('Fit to Window / Fullscreen', 'fit'),
            ('Auto Standard (4:3 Interlaced / 3:2 Progressive)', 'auto'),
            ('Standard (4:3)', 'tv_4_3'),
            ('Widescreen (16:9)', 'wide_16_9'),
            ('Native/Full (10:7)', 'native_10_7'),
            ('Square capture (debug)', 'square'),
            ('Raw 512×448 (debug)', 'raw'),
        ):
            self.m_presentation_combo.addItem(title, mode)
        self.m_presentation_combo.setCurrentIndex(
            self.m_presentation_combo.findData(self.m_presentation))
        self.m_presentation_combo.currentIndexChanged.connect(
            self.set_presentation)
        self.m_scan_combo = W.QComboBox()
        self.m_scan_combo.addItem('Interlaced (4:3)', 'interlaced')
        self.m_scan_combo.addItem('Progressive (3:2)', 'progressive')
        self.m_scan_combo.setToolTip(
            'Manual scan-mode assumption for Auto Standard; '
            'the game\'s active GS scan mode is not yet detected.')
        self.m_scan_combo.currentIndexChanged.connect(self.set_scan_mode)
        self.m_scan_combo.setVisible(False)
        controls.addWidget(W.QLabel('Display'))
        controls.addWidget(self.m_presentation_combo)
        controls.addWidget(self.m_scan_combo)

        match_button = W.QPushButton('Match pose...')
        match_button.setToolTip(
            'Compare the character region against a cropped 4:3 game screenshot. '
            'This finds the nearest preview sample, not the native animation time.')
        match_button.clicked.connect(self.match_reference_pose)
        controls.addWidget(match_button)
        next_match_button = W.QPushButton('Next match')
        next_match_button.setToolTip('Inspect the next-best matching animation sample')
        next_match_button.clicked.connect(self.next_reference_match)
        controls.addWidget(next_match_button)
        self.m_match_status = W.QLabel('')
        self.m_match_status.setToolTip(
            'Lower score means a closer visual match; the screenshot may have '
            'different filtering, blending, or runtime animation phases.')
        controls.addWidget(self.m_match_status)

        self.m_time_slider = W.QSlider(C.Qt.Orientation.Horizontal)
        self.m_time_slider.setMinimum(0)
        self.m_time_slider.setMaximum(139)
        self.m_time_slider.valueChanged.connect(self.set_time)
        controls.addWidget(self.m_time_slider, 1)
        self.m_status = W.QLabel('Sample 0')
        controls.addWidget(self.m_status)
        layout.addLayout(controls)

        navigation = W.QHBoxLayout()
        navigation.addWidget(W.QLabel('Native graph'))
        for label, direction in (('←', 1), ('↑', 2), ('↓', 3), ('→', 0)):
            button = W.QPushButton(label)
            button.setFixedWidth(32)
            button.setToolTip('%s: ELF direction %d, input mask 0x%X' %
                              (DIRECTION_NAMES[direction], direction, DIRECTION_MASKS[direction]))
            button.clicked.connect(lambda _checked=False, d=direction: self.navigate(d))
            navigation.addWidget(button)
        confirm = W.QPushButton('Confirm route')
        confirm.setToolTip('Inspect the original destination; does not launch an app')
        confirm.clicked.connect(lambda _checked=False: self.inspect_route(False))
        navigation.addWidget(confirm)
        cancel = W.QPushButton('Cancel route')
        cancel.setToolTip('Inspect the native cancel destination (app 3)')
        cancel.clicked.connect(lambda _checked=False: self.inspect_route(True))
        navigation.addWidget(cancel)
        self.m_navigation_status = W.QLabel('')
        self.m_navigation_status.setMinimumWidth(160)
        navigation.addWidget(self.m_navigation_status, 1)
        layout.addLayout(navigation)

        layers = W.QHBoxLayout()
        for name, attr in (('Background', 'm_background'), ('Motion', 'm_motion'), ('Tint', 'm_tint'),
                           ('Scenery', 'm_first'), ('Characters', 'm_middle'), ('Label', 'm_overlay'),
                           ('Idle', 'm_idle'), ('Char motion', 'm_character_motion'),
                           ('Label motion', 'm_label_motion'), ('Arrows', 'm_arrows'), ('Bounds', 'm_bounds'),
                           ('Smooth', 'm_smooth'), ('Selection pulse (preview)', 'm_selection_effect'),
                           ('Arrow bob (preview)', 'm_arrow_bob'), ('Help panel', 'm_help_panel')):
            box = W.QCheckBox(name)
            box.setChecked(getattr(self, attr))
            box.toggled.connect(lambda value, a=attr: setattr(self, a, value))
            box.toggled.connect(lambda _value: self.m_canvas.update())
            layers.addWidget(box)
        layout.addLayout(layers)

        self.m_canvas = c_menu_canvas(self)
        layout.addWidget(self.m_canvas, 1)
        self.m_texture_status = W.QLabel('Menu textures: open INFO.DAT + GAME.DAT')
        self.m_texture_status.setToolTip('Textures are decoded from your own dis/main_menu.pix; no game artwork is bundled')
        layout.addWidget(self.m_texture_status)
        self.m_help_text = W.QLabel('')
        self.m_help_text.setWordWrap(True)
        self.m_help_text.setMaximumHeight(42)
        self.m_help_text.setToolTip('Original ELF text description for the selected item')
        layout.addWidget(self.m_help_text)

        self.load_data()
        self.update_navigation_status()

    def load_data(self):
        """Load recovered animation and geometry, not copyrighted texture data."""
        root = Path(__file__).resolve().parent.parent / 'previews'
        manifest = root / 'menu_layout.json'
        if not manifest.is_file():
            self.m_texture_status.setText('Menu layout data missing: ' + str(manifest))
            return
        data = json.loads(manifest.read_text(encoding='utf-8'))
        if data.get('format') != 'arika-menu-layout' or data.get('version') != 1:
            raise ValueError('unsupported menu layout manifest')
        frames = []
        for name in data.pop('frame_files'):
            # The fixed-name manifest is checked into the repo; refuse paths
            # outside the layout directory if a local copy is edited.
            if not re.fullmatch(r'menu_frames_[0-9]{3}\.json', name):
                raise ValueError('invalid menu frame filename: ' + name)
            frames.extend(json.loads((root / name).read_text(encoding='utf-8')))
        if len(frames) != data['frame_count']:
            raise ValueError('menu layout frame-count mismatch')
        data['frames'] = frames
        self.m_data = data
        self.m_time_slider.setMaximum(len(frames) - 1)
        self.m_time = min(self.m_time, len(frames) - 1)
        self.m_time_slider.setValue(int(self.m_time))
        self.m_canvas.update()

    def load_help_font(self, font_data=None):
        """Use the same native FFON decoder as the existing Fonts panel."""
        self.m_help_font = None
        self.m_help_font_data = None
        self.m_help_lines_pixmaps.clear()
        if font_data:
            self.m_help_font = arika_ffon.parse_ffon(font_data)
            self.m_help_font_data = font_data
        self.m_canvas.update()
        return self.m_help_font is not None

    def help_line_pixmap(self, text):
        if self.m_help_font is None or self.m_help_font_data is None:
            return None
        if text not in self.m_help_lines_pixmaps:
            image = arika_ffon.render_text(self.m_help_font, self.m_help_font_data,
                                          text, spacing=3)
            self.m_help_lines_pixmaps[text] = arika_ffon.image_to_qpixmap(image)
        return self.m_help_lines_pixmaps[text]

    def load_textures(self, pix_data=None):
        """Decode dis/main_menu.pix from an opened game archive, entirely in memory.

        Clears old textures first to avoid displaying copyrighted assets from
        a previously opened archive when the new one has no menu PIX.
        """
        self.m_textures.clear()
        self.m_help_panel_uv = None
        if not pix_data:
            self.m_texture_status.setText('Menu textures: open INFO.DAT + GAME.DAT')
            self.m_canvas.update()
            return False
        try:
            from arika_dat import container, tim2_rgba
            metadata = container(pix_data)
            if metadata['magic'] != 'FPIX':
                raise ValueError('menu asset is not FPIX')
            chunks = metadata['chunks']
            expected = self.m_data['expected_texture_count']
            if len(chunks) != expected:
                raise ValueError('expected %d menu atlases, got %d' % (expected, len(chunks)))
            decoded = {}
            help_panel_uv = None
            for chunk in chunks:
                start = chunk['offset']
                body = pix_data[start:start + chunk['size']]
                if chunk['magic'] != 'XPIX' or body[32:36] != b'TIM2':
                    raise ValueError('invalid XPIX/TIM2 chunk %d' % chunk['index'])
                width, height, rgba = tim2_rgba(body[32:])
                if len(rgba) != width * height * 4:
                    raise ValueError('invalid RGBA buffer size')
                image = G.QImage(rgba, width, height, width * 4,
                                 G.QImage.Format.Format_RGBA8888).copy()
                if image.isNull():
                    raise ValueError('unable to create texture image')
                decoded[chunk['index']] = G.QPixmap.fromImage(image)
                if chunk['index'] == 4:
                    # Atlas 4 contains the actual help frame with transparent
                    # padding. Its nonempty rectangle is much smaller than
                    # the 512x512 atlas, so drawing the whole atlas crushes
                    # the frame vertically.
                    from PIL import Image
                    bounds = Image.frombytes('RGBA', (width, height), rgba).getchannel('A').getbbox()
                    if bounds is not None:
                        left, top, right, bottom = bounds
                        help_panel_uv = C.QRectF(left, top, right - left, bottom - top)
            self.m_textures = decoded
            self.m_help_panel_uv = help_panel_uv
            self.m_texture_status.setText('Menu textures: %d atlases from opened GAME.DAT' % len(decoded))
            self.m_canvas.update()
            return True
        except (ValueError, RuntimeError, KeyError, TypeError) as error:
            self.m_texture_status.setText('Menu texture decoding failed: %s' % error)
            self.m_canvas.update()
            return False

    def update_navigation_status(self, action=None):
        selected = self.m_navigation.m_selected
        previous = self.m_navigation.m_previous
        route = self.m_navigation.route()
        title = '%d %s' % (selected, MENU_ITEM_NAMES[selected])
        source = 'from %d' % previous if previous >= 0 else 'initial'
        if action:
            text = '%s | %s' % (action, title)
        else:
            text = '%s (%s) | app %d, mode %d' % (
                title, source, route['next_app_id'], route['mode_selector'])
        self.m_navigation_status.setText(text)
        lines = self.m_navigation.help_lines()
        self.m_help_text.setText('ELF help: ' + ' '.join(lines))
        self.m_help_text.setToolTip('\n'.join(lines))
        directions = self.m_navigation.available_directions()
        self.m_navigation_status.setToolTip(
            '%s\nELF help ID %d:\n%s\n\nNeighbours: %s\n'
            'Confirm: app %d, mode %d; cancel: app 3' %
            (title, self.m_navigation.text_lookup_id(), '\n'.join(lines),
             ', '.join('%s=%d' % item for item in directions.items()),
             route['next_app_id'], route['mode_selector']))

    def trigger_selection_effect(self):
        # Event timing is authored; displacement samples come from the ELF curves.
        if self.m_data is not None:
            self.m_selection_age = 0.0
            if not self.m_timer.isActive():
                self.m_timer.start()

    def set_item(self, index):
        if not self.m_navigation.select(index):
            return
        self.m_item = self.m_navigation.m_selected
        self.trigger_selection_effect()
        self.update_navigation_status()
        self.m_canvas.update()

    def navigate(self, direction):
        old = self.m_navigation.m_selected
        if not self.m_navigation.move(direction):
            action = '%s: no neighbour' % DIRECTION_NAMES[direction] if 0 <= direction < 4 else 'Invalid direction'
            self.update_navigation_status(action)
            self.m_canvas.setFocus()
            return False
        self.m_item = self.m_navigation.m_selected
        blocked = self.m_item_combo.blockSignals(True)
        try:
            self.m_item_combo.setCurrentIndex(self.m_item)
        finally:
            self.m_item_combo.blockSignals(blocked)
        self.trigger_selection_effect()
        self.update_navigation_status('%s: %d → %d' %
                                      (DIRECTION_NAMES[direction], old, self.m_item))
        self.m_canvas.setFocus()
        self.m_canvas.update()
        return True

    def inspect_route(self, cancelled=False):
        route = self.m_navigation.route(cancelled)
        if cancelled:
            action = 'Cancel → app %d (selector unchanged)' % route['next_app_id']
        else:
            action = 'Confirm → app %d, mode %d' % (
                route['next_app_id'], route['mode_selector'])
        self.update_navigation_status(action)
        self.m_canvas.setFocus()
        return route

    def set_time(self, value):
        self.m_time = float(value)
        self.m_status.setText('Sample %s' % (int(self.m_time) if self.m_time == int(self.m_time) else round(self.m_time, 2)))
        self.m_canvas.update()

    def toggle_play(self):
        self.m_playing = not self.m_playing
        self.m_play_button.setText('Pause' if self.m_playing else 'Play')
        if self.m_playing:
            self.update_timer()
            self.m_timer.start()
        elif self.m_selection_age is None:
            self.m_timer.stop()

    def update_timer(self):
        self.m_timer.setInterval(1000 // 60)

    def advance(self):
        if not self.m_data:
            self.m_timer.stop()
            return
        rate = self.m_rate_combo.currentData() or 1.0
        if self.m_playing:
            n = len(self.m_data['frames'])
            self.m_time = (self.m_time + rate) % n
            self.m_time_slider.blockSignals(True)
            self.m_time_slider.setValue(min(n - 1, int(round(self.m_time))))
            self.m_time_slider.blockSignals(False)
            self.m_status.setText('Sample %s' % (int(self.m_time) if self.m_time == int(self.m_time) else round(self.m_time, 2)))
        if self.m_selection_age is not None:
            self.m_selection_age += rate
            if self.m_selection_age >= EMPHASIS_DURATION:
                self.m_selection_age = None
                if not self.m_playing:
                    self.m_timer.stop()
        self.m_canvas.update()

    def match_reference_pose(self):
        """Seek to the best visual match, without modifying recovered frames."""
        filename, _filter = W.QFileDialog.getOpenFileName(
            self, 'Choose cropped 4:3 menu screenshot', '',
            'Images (*.png *.jpg *.jpeg *.bmp)')
        if not filename:
            return
        try:
            with Image.open(filename) as image:
                reference = normalize_reference(image)
            self.match_reference_image(reference)
        except (OSError, ValueError, TypeError) as error:
            W.QMessageBox.warning(self, 'Menu frame match', str(error))

    def match_reference_image(self, reference):
        """Compare settled samples 23..119 in the 4:3 presentation only."""
        if not self.m_data or not self.m_textures:
            raise ValueError('load the main-menu PIX textures first')
        if reference.size != (256, 192):
            raise ValueError('normalize the screenshot before matching')

        old_time = self.m_time
        old_presentation = self.m_presentation
        old_selection_age = self.m_selection_age
        self.m_reference_matches = []
        W.QApplication.setOverrideCursor(C.Qt.CursorShape.WaitCursor)
        try:
            self.m_presentation = 'tv_4_3'
            self.m_selection_age = None

            def frames():
                # The baked timeline has authored entry/exit periods.
                # Compare only the settled middle period, not the startup
                # or exit, against an unknown screenshot timestamp.
                for tick in range(23, min(120, len(self.m_data['frames']))):
                    self.m_time = float(tick)
                    canvas = G.QImage(
                        512, 384, G.QImage.Format.Format_RGBA8888)
                    canvas.fill(G.QColor('#10151c'))
                    painter = G.QPainter(canvas)
                    try:
                        self.render(painter, C.QRect(0, 0, 512, 384))
                    finally:
                        painter.end()
                    pixels = Image.frombytes(
                        'RGBA', (512, 384), bytes(canvas.constBits()))
                    yield tick, normalize_reference(pixels)

            matches = rank_samples(reference, frames(), top_n=5)
        finally:
            self.m_time = old_time
            self.m_presentation = old_presentation
            self.m_selection_age = old_selection_age
            W.QApplication.restoreOverrideCursor()
        if not matches:
            raise ValueError('no settled animation samples available')
        self.m_reference_matches = matches
        self.m_reference_match_index = 0
        self.show_reference_match()

    def show_reference_match(self):
        if not self.m_reference_matches:
            return
        score, tick = self.m_reference_matches[self.m_reference_match_index]
        if self.m_playing:
            self.toggle_play()
        self.m_time_slider.setValue(tick)
        self.m_time = float(tick)
        self.m_match_status.setText(
            'Match %d/%d: %d (%.2f)' %
            (self.m_reference_match_index + 1,
             len(self.m_reference_matches), tick, score))
        self.m_canvas.update()

    def next_reference_match(self):
        if not self.m_reference_matches:
            return
        self.m_reference_match_index = (
            self.m_reference_match_index + 1) % len(self.m_reference_matches)
        self.show_reference_match()

    def set_presentation(self, index):
        mode = self.m_presentation_combo.itemData(index)
        if mode in ('fit', 'auto', 'tv_4_3', 'wide_16_9',
                    'native_10_7', 'square', 'raw'):
            self.m_presentation = mode
            self.m_scan_combo.setVisible(mode == 'auto')
            self.m_canvas.update()

    def set_scan_mode(self, index):
        mode = self.m_scan_combo.itemData(index)
        if mode in ('interlaced', 'progressive'):
            self.m_scan_mode = mode
            self.m_canvas.update()

    def presentation_height(self):
        # Virtual display units at width 512. Source geometry remains 512x448.
        if self.m_presentation == 'auto':
            return 384.0 if self.m_scan_mode == 'interlaced' else 512.0 * 2.0 / 3.0
        return {
            'square': 512.0, 'raw': 448.0,
            'tv_4_3': 384.0, 'wide_16_9': 288.0,
            'native_10_7': 512.0 * 7.0 / 10.0,
        }.get(self.m_presentation, 448.0)

    def render(self, painter, rect):
        painter.fillRect(rect, G.QColor('#10151c'))
        if not self.m_data or not self.m_textures:
            painter.setPen(G.QColor('#e8edf3'))
            text = 'Recovered menu layout not found' if not self.m_data else (
                'Open INFO.DAT and GAME.DAT to display original menu textures')
            painter.drawText(rect, C.Qt.AlignmentFlag.AlignCenter, text)
            return
        n = len(self.m_data['frames'])
        t = self.m_time % n
        i0 = int(t)
        i1 = min(i0 + 1, n - 1)
        frac = t - i0
        frame = interpolate_frames(self.m_data['frames'][i0], self.m_data['frames'][i1], frac)
        item = self.m_data['items'][self.m_item]

        draw_queue = []

        def enqueue(entry, geometry, depth, alpha=1.0):
            if geometry and alpha > 0:
                draw_queue.append({'entry': entry, 'geometry': geometry, 'depth': geometry.get('depth', depth), 'alpha': alpha})

        if self.m_background:
            enqueue(1, self.m_data['background'], 0)
        if self.m_motion:
            enqueue(2, frame['banner'], 99)
            for tile in frame['tiles']:
                enqueue(2, tile, 85)
            for s in frame['small']:
                enqueue(3, s, 5)
        if self.m_tint and not frame['hidden']:
            enqueue(8, self.m_data['tint'], 10, frame['alpha'])

        active_characters = frame['idle_characters' if self.m_idle else 'characters'][self.m_item]
        active_labels = frame['labels']
        selection_sample = emphasis_sample(self.m_data['frames'], self.m_selection_age) if self.m_selection_effect else None

        if self.m_middle:
            group_checked = True
        else:
            group_checked = False

        for group in ('first', 'middle', 'overlay'):
            checked = {'first': self.m_first, 'middle': self.m_middle, 'overlay': self.m_overlay, 'arrows': self.m_arrows}[group]
            if not checked:
                continue
            if group == 'middle' and self.m_character_motion:
                parts = active_characters
            elif group == 'middle':
                parts = item['middle']
            else:
                parts = item[group]
            for part_index, p in enumerate(parts):
                geometry = p['geometry']
                if group == 'overlay' and self.m_label_motion:
                    geometry = active_labels[self.m_item]
                if selection_sample and group == 'middle' and self.m_character_motion:
                    sample_group = 'idle_characters' if self.m_idle else 'characters'
                    pulse_group = 'emphasis_idle_characters' if self.m_idle else 'emphasis_characters'
                    baseline = selection_sample[sample_group][self.m_item]
                    emphasized = selection_sample[pulse_group][self.m_item]
                    if emphasized is not None and part_index < len(baseline) and part_index < len(emphasized):
                        geometry = emphasis_geometry(geometry, baseline[part_index]['geometry'],
                                                    emphasized[part_index]['geometry'])
                elif selection_sample and group == 'overlay' and self.m_label_motion:
                    pulse_label = selection_sample['emphasis_labels']
                    if pulse_label is not None:
                        geometry = emphasis_geometry(geometry, selection_sample['labels'][self.m_item],
                                                    pulse_label[self.m_item])
                enqueue(p['texture_entry'], geometry, 47 if group == 'first' else 60 if group == 'middle' else 70)

        if self.m_arrows:
            for part in arrow_parts(self.m_menu_report, self.m_item, self.m_navigation.m_previous):
                geometry = part['geometry']
                if self.m_arrow_bob:
                    geometry = bobbed_arrow_geometry(geometry, self.m_time)
                enqueue(0, geometry, 95)

        if self.m_first:
            for p in frame['strips'][self.m_item]:
                enqueue(p['texture_entry'], p['geometry'], 45)

        draw_queue.sort(key=lambda q: q['depth'])

        # 512x448 recovered coordinates never change. Fit deliberately fills
        # the complete widget; the remaining choices preserve their aspect ratio.
        display_height = self.presentation_height()
        if self.m_presentation == 'fit':
            scale_x = rect.width() / 512.0
            scale_y = rect.height() / 448.0
            offset_x, offset_y = rect.x(), rect.y()
        else:
            scale = min(rect.width() / 512.0, rect.height() / display_height)
            scale_x = scale
            scale_y = scale * display_height / 448.0
            offset_x = rect.x() + (rect.width() - 512.0 * scale) / 2.0
            offset_y = rect.y() + (rect.height() - display_height * scale) / 2.0

        painter.save()
        painter.setRenderHint(G.QPainter.RenderHint.SmoothPixmapTransform, self.m_smooth)
        painter.translate(offset_x, offset_y)
        painter.scale(scale_x, scale_y)
        painter.setClipRect(C.QRectF(0, 0, 512, 448))

        for q in draw_queue:
            self.draw_sprite(painter, q['entry'], q['geometry'], q['alpha'])

        if self.m_help_panel:
            self.draw_help_panel(painter)

        painter.restore()

    def draw_help_panel(self, painter):
        """Draw recovered help strings with the archive's native FFON font.

        The frame itself must use recovered PIX sprite UVs; no QPainter
        imitation of copyrighted texture art or system font substitution.
        """
        painter.save()
        painter.setRenderHint(G.QPainter.RenderHint.SmoothPixmapTransform, False)
        # Atlas 4 is the native framed help panel (research/TEXTURED_MENU.md).
        # Placement/crop are provisional until its draw helper is traced.
        # Render the game texture, never a synthetic QPainter border.
        panel = self.m_textures.get(4)
        if panel is not None and not panel.isNull() and self.m_help_panel_uv is not None:
            painter.drawPixmap(C.QRectF(30, 272, 450, 175), panel,
                               self.m_help_panel_uv)
        if self.m_help_font is None:
            painter.restore()
            return
        painter.setClipRect(C.QRectF(76, 312, 359, 116), C.Qt.ClipOperation.IntersectClip)
        # The four ELF lines share one font scale. Scaling each line to the
        # maximum width independently makes every line equally long and does
        # not match the original game's fixed glyph advance.
        pixmaps = [self.help_line_pixmap(line)
                   for line in self.m_navigation.help_lines()[:4]]
        widths = [pixmap.width() for pixmap in pixmaps
                  if pixmap is not None and not pixmap.isNull()]
        if widths:
            scale = min(1.0, 303.0 / max(widths))
            for index, pixmap in enumerate(pixmaps):
                if pixmap is None or pixmap.isNull():
                    continue
                painter.drawPixmap(C.QRectF(87, 324 + index * 25,
                                           pixmap.width() * scale,
                                           pixmap.height() * scale),
                                   pixmap, C.QRectF(0, 0, pixmap.width(), pixmap.height()))
        painter.restore()

    def draw_sprite(self, painter, entry, geometry, alpha):
        pixmap = self.m_textures.get(entry)
        if pixmap is None or pixmap.isNull():
            return
        uv = geometry['uv_endpoints']
        verts = geometry['vertices']
        du = uv[2] - uv[0]
        dv = uv[3] - uv[1]
        if not du or not dv:
            return
        p0 = verts[0]
        p1 = verts[1]
        p2 = verts[2]
        a = (p1[0] - p0[0]) / du
        b = (p1[1] - p0[1]) / du
        c = (p2[0] - p0[0]) / dv
        d = (p2[1] - p0[1]) / dv
        tx = p0[0] - uv[0] * a - uv[1] * c
        ty = p0[1] - uv[0] * b - uv[1] * d

        path = G.QPainterPath()
        path.moveTo(p0[0], p0[1])
        path.lineTo(p1[0], p1[1])
        path.lineTo(verts[3][0], verts[3][1])
        path.lineTo(p2[0], p2[1])
        path.closeSubpath()

        painter.save()
        painter.setRenderHint(G.QPainter.RenderHint.SmoothPixmapTransform, self.m_smooth or ((abs(du) == 1 and abs(dv) > 4) or (abs(dv) == 1 and abs(du) > 4)))
        painter.setOpacity(alpha)
        painter.setClipPath(path, C.Qt.ClipOperation.IntersectClip)
        transform = G.QTransform(a, b, c, d, tx, ty)
        painter.setTransform(transform, True)
        painter.drawPixmap(0, 0, pixmap)
        painter.restore()

        if self.m_bounds:
            painter.save()
            painter.setPen(G.QPen(G.QColor('#ffb347'), 0.7))
            painter.drawPath(path)
            painter.restore()