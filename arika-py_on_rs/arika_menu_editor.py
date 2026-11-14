"""Native 2D preview/editor for the recovered Super Dragon Ball Z menu."""
import base64
import json
import math
import re
from pathlib import Path

from PySide6 import QtCore as C, QtGui as G, QtWidgets as W

from arika_menu_navigation import c_menu_navigation, MENU_ITEM_NAMES, DIRECTION_NAMES, DIRECTION_MASKS


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
        self.m_time = 70.0
        self.m_item = 0
        self.m_navigation = c_menu_navigation()
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
        self.m_bounds = False
        self.m_smooth = False

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
                           ('Smooth', 'm_smooth')):
            box = W.QCheckBox(name)
            box.setChecked(getattr(self, attr))
            box.toggled.connect(lambda value, a=attr: setattr(self, a, value))
            box.toggled.connect(lambda _value: self.m_canvas.update())
            layers.addWidget(box)
        layout.addLayout(layers)

        self.m_canvas = c_menu_canvas(self)
        layout.addWidget(self.m_canvas, 1)
        self.m_help_text = W.QLabel('')
        self.m_help_text.setWordWrap(True)
        self.m_help_text.setMaximumHeight(42)
        self.m_help_text.setToolTip('Original ELF text description for the selected item')
        layout.addWidget(self.m_help_text)

        self.load_data()
        self.update_navigation_status()

    def load_data(self):
        # Locate the bundled preview independently of the caller's cwd:
        # root/launch_editor.bat and arika-py_on_rs/launch_editor.bat both work.
        candidates = (
            Path(__file__).resolve().parent / 'previews' / 'menu_textured.html',
            Path(__file__).resolve().parent.parent / 'previews' / 'menu_textured.html',
            Path.cwd() / 'previews' / 'menu_textured.html',
        )
        path = next((candidate for candidate in candidates if candidate.is_file()), None)
        if path is None:
            return
        html = path.read_text(encoding='utf-8')
        match = re.search(r'const DATA=(.*?);\nconst \$', html, re.S)
        if not match:
            return
        self.m_data = json.loads(match.group(1))
        self.m_time_slider.setMaximum(len(self.m_data['frames']) - 1)
        for t in self.m_data['textures']:
            pixmap = G.QPixmap()
            pixmap.loadFromData(base64.b64decode(t['png'].split(',', 1)[1]))
            self.m_textures[t['index']] = pixmap
        self.m_time = min(self.m_time, len(self.m_data['frames']) - 1)
        self.m_time_slider.setValue(self.m_time)
        self.m_canvas.update()

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

    def set_item(self, index):
        if not self.m_navigation.select(index):
            return
        self.m_item = self.m_navigation.m_selected
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
        else:
            self.m_timer.stop()

    def update_timer(self):
        self.m_timer.setInterval(1000 // 60)

    def advance(self):
        if not self.m_data:
            return
        rate = self.m_rate_combo.currentData() or 1.0
        n = len(self.m_data['frames'])
        self.m_time = (self.m_time + rate) % n
        self.m_time_slider.blockSignals(True)
        self.m_time_slider.setValue(int(round(self.m_time)))
        self.m_time_slider.blockSignals(False)
        self.m_status.setText('Sample %s' % (int(self.m_time) if self.m_time == int(self.m_time) else round(self.m_time, 2)))
        self.m_canvas.update()

    def render(self, painter, rect):
        painter.fillRect(rect, G.QColor('#10151c'))
        if not self.m_data:
            painter.setPen(G.QColor('#e8edf3'))
            painter.drawText(rect, C.Qt.AlignmentFlag.AlignCenter, 'Menu data not found')
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
            for t in frame['tiles']:
                enqueue(2, t, 85)
            for s in frame['small']:
                enqueue(3, s, 5)
        if self.m_tint and not frame['hidden']:
            enqueue(8, self.m_data['tint'], 10, frame['alpha'])

        active_characters = frame['idle_characters' if self.m_idle else 'characters'][self.m_item]
        active_labels = frame['labels']

        if self.m_middle:
            group_checked = True
        else:
            group_checked = False

        for group in ('first', 'middle', 'overlay', 'arrows'):
            checked = {'first': self.m_first, 'middle': self.m_middle, 'overlay': self.m_overlay, 'arrows': self.m_arrows}[group]
            if not checked:
                continue
            if group == 'middle' and self.m_character_motion:
                parts = active_characters
            elif group == 'middle':
                parts = item['middle']
            else:
                parts = item[group]
            for p in parts:
                geometry = p['geometry']
                if group == 'overlay' and self.m_label_motion:
                    geometry = active_labels[self.m_item]
                enqueue(p['texture_entry'], geometry, 47 if group == 'first' else 60 if group == 'middle' else 70)

        if self.m_first:
            for p in frame['strips'][self.m_item]:
                enqueue(p['texture_entry'], p['geometry'], 45)

        draw_queue.sort(key=lambda q: q['depth'])

        scale = min(rect.width() / 512.0, rect.height() / 448.0)
        offset_x = rect.x() + (rect.width() - 512 * scale) / 2
        offset_y = rect.y() + (rect.height() - 448 * scale) / 2

        painter.save()
        painter.setRenderHint(G.QPainter.RenderHint.SmoothPixmapTransform, self.m_smooth)
        painter.translate(offset_x, offset_y)
        painter.scale(scale, scale)

        for q in draw_queue:
            self.draw_sprite(painter, q['entry'], q['geometry'], q['alpha'])

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
        painter.setClipPath(path)
        transform = G.QTransform(a, b, c, d, tx, ty)
        painter.setTransform(transform, True)
        painter.drawPixmap(0, 0, pixmap)
        painter.restore()

        if self.m_bounds:
            painter.save()
            painter.setPen(G.QPen(G.QColor('#ffb347'), 0.7))
            painter.drawPath(path)
            painter.restore()