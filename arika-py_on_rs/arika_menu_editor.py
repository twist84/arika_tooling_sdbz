"""Native 2D preview/editor for the recovered Super Dragon Ball Z menu."""
import base64
import json
import math
import re
from pathlib import Path

from PySide6 import QtCore as C, QtGui as G, QtWidgets as W


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
        self.setMinimumSize(0, 0)
        self.setSizePolicy(W.QSizePolicy.Policy.Expanding, W.QSizePolicy.Policy.Expanding)

    def paintEvent(self, event):
        painter = G.QPainter(self)
        self.m_editor.render(painter, self.rect())
        painter.end()


class c_menu_editor(W.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.m_data = None
        self.m_textures = {}
        self.m_time = 70.0
        self.m_item = 0
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
        for i in range(7):
            self.m_item_combo.addItem('%d' % i)
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

        layers = W.QHBoxLayout()
        for name, attr in (('Background', 'm_background'), ('Motion', 'm_motion'), ('Tint', 'm_tint'),
                           ('Scenery', 'm_first'), ('Characters', 'm_middle'), ('Label', 'm_overlay'),
                           ('Idle', 'm_idle'), ('Char motion', 'm_character_motion'),
                           ('Label motion', 'm_label_motion'), ('Arrows', 'm_arrows'), ('Bounds', 'm_bounds'),
                           ('Smooth', 'm_smooth')):
            box = W.QCheckBox(name)
            box.setChecked(getattr(self, attr))
            box.toggled.connect(lambda value, a=attr: setattr(self, a, value))
            box.toggled.connect(lambda _value: self.update())
            layers.addWidget(box)
        layout.addLayout(layers)

        self.m_canvas = c_menu_canvas(self)
        layout.addWidget(self.m_canvas, 1)

        self.load_data()

    def load_data(self):
        path = Path(__file__).with_name('previews') / 'menu_textured.html'
        if not path.exists():
            path = Path.cwd() / 'previews' / 'menu_textured.html'
        if not path.exists():
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
        self.update()

    def set_item(self, index):
        self.m_item = index
        self.update()

    def set_time(self, value):
        self.m_time = float(value)
        self.m_status.setText('Sample %s' % (int(self.m_time) if self.m_time == int(self.m_time) else round(self.m_time, 2)))
        self.update()

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
        self.update()

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