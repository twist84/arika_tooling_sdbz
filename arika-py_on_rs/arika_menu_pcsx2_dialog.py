"""Qt dialog recording PCSX2 rendering choices for capture comparisons.

Only supersampling and a broad nearest/linear texture filter have a Qt
preview effect. All other controls describe the PCSX2 reference session
and are intentionally NOT portrayed as emulated GS/renderer switches.
"""
from PySide6 import QtCore as C, QtWidgets as W

from arika_menu_pcsx2_comparison import (
    ANISOTROPIC_FILTERS, BLENDING_MODES, DITHERING_MODES,
    INTERNAL_RESOLUTIONS, TEXTURE_FILTERS, TRILINEAR_FILTERS,
    s_pcsx2_comparison_settings,
)


class c_pcsx2_comparison_dialog(W.QDialog):
    def __init__(self, settings, enabled=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle('PCSX2 graphics comparison')
        self.setMinimumWidth(620)
        self.m_choices = {}
        self.m_checks = {}
        self.m_settings = settings.validate()

        root = W.QVBoxLayout(self)
        intro = W.QLabel(
            'Reference: PCSX2 EU-beta screenshot (D3D12, 4x native, '
            'Bilinear PS2). Only two options are approximated in Qt; '
            'all remaining options are recorded for repeatable captures.')
        intro.setWordWrap(True)
        root.addWidget(intro)

        self.m_enabled = W.QCheckBox(
            'Use PCSX2 comparison preview (supersampled render target)')
        self.m_enabled.setChecked(bool(enabled))
        root.addWidget(self.m_enabled)

        reference = W.QGroupBox('PCSX2 reference hardware (record only)')
        reference_layout = W.QFormLayout(reference)
        self.m_api = W.QLineEdit(settings.graphics_api)
        self.m_api.setReadOnly(True)
        self.m_adapter = W.QLineEdit(settings.adapter)
        self.m_adapter.setReadOnly(True)
        reference_layout.addRow('Graphics API', self.m_api)
        reference_layout.addRow('Adapter', self.m_adapter)
        root.addWidget(reference)

        approx = W.QGroupBox('Preview approximations (affect Qt output)')
        approx_form = W.QFormLayout(approx)
        self._add_choice(
            approx_form, 'Internal Resolution', 'internal_resolution',
            [(f'{factor}x native', factor) for factor in INTERNAL_RESOLUTIONS],
            settings.internal_resolution,
            'Qt supersampling of 512-unit menu geometry; not the PCSX2 GS render target.')
        self._add_choice(
            approx_form, 'Texture Filtering', 'texture_filtering',
            TEXTURE_FILTERS, settings.texture_filtering,
            'Nearest versus QPainter linear filtering. Bilinear (PS2) '
            'is only an approximation without per-draw GS TEX1 state.')
        root.addWidget(approx)

        reference_only = W.QGroupBox('PCSX2 reference settings (not emulated by Qt)')
        reference_form = W.QFormLayout(reference_only)
        self._add_choice(reference_form, 'Trilinear Filtering',
                         'trilinear_filtering', TRILINEAR_FILTERS,
                         settings.trilinear_filtering,
                         'No native mip-filtering emulation in QPainter.')
        self._add_choice(
            reference_form, 'Anisotropic Filtering', 'anisotropic_filtering',
            [('Off' if value == 0 else f'{value}x', value)
             for value in ANISOTROPIC_FILTERS],
            settings.anisotropic_filtering,
            'No anisotropic sampling emulation in QPainter.')
        self._add_choice(reference_form, 'Dithering', 'dithering',
                         DITHERING_MODES, settings.dithering,
                         'No PS2 framebuffer dithering emulation in QPainter.')
        self._add_choice(reference_form, 'Blending Accuracy',
                         'blending_accuracy', BLENDING_MODES,
                         settings.blending_accuracy,
                         'Qt alpha compositing is not the GS ALPHA/TEST/ZBUF pipeline.')

        toggles = W.QGridLayout()
        for row, (title, name) in enumerate((
            ('Mipmapping', 'mipmapping'),
            ('AA1', 'aa1'),
            ('Manual Hardware Renderer Fixes', 'manual_hardware_fixes'),
            ('Accurate Alpha Test', 'accurate_alpha_test'),
            ('Rasterizer Ordered View', 'rasterizer_ordered_view'),
        )):
            check = W.QCheckBox(title)
            check.setChecked(getattr(settings, name))
            check.setToolTip(
                'Recorded PCSX2 reference setting only; Qt does not '
                'implement this GS or PCSX2 hardware feature.')
            self.m_checks[name] = check
            toggles.addWidget(check, row // 2, row % 2)
        reference_form.addRow(toggles)
        root.addWidget(reference_only)

        note = W.QLabel(
            'For fair comparisons, keep the same menu selection, animation '
            'tick, aspect ratio, and capture resolution. Export lossless PNGs. '
            '4x here means Qt rendering at 2048 logical horizontal pixels; '
            'it is not proof of identical native PCSX2 raster dimensions.')
        note.setWordWrap(True)
        root.addWidget(note)

        buttons = W.QDialogButtonBox(
            W.QDialogButtonBox.StandardButton.Ok |
            W.QDialogButtonBox.StandardButton.Cancel)
        self.m_restore_button = W.QPushButton('Restore screenshot preset')
        buttons.addButton(
            self.m_restore_button, W.QDialogButtonBox.ButtonRole.ResetRole)
        self.m_restore_button.clicked.connect(self.restore_screenshot_preset)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _add_choice(self, layout, label, name, values, selected, tooltip):
        combo = W.QComboBox()
        for title, value in values:
            combo.addItem(title, value)
        index = combo.findData(selected)
        if index < 0:
            raise ValueError('unsupported PCSX2 graphics setting: ' + name)
        combo.setCurrentIndex(index)
        combo.setToolTip(tooltip)
        self.m_choices[name] = combo
        layout.addRow(label, combo)

    def restore_screenshot_preset(self):
        settings = s_pcsx2_comparison_settings()
        self.m_enabled.setChecked(True)
        for name, combo in self.m_choices.items():
            combo.setCurrentIndex(combo.findData(getattr(settings, name)))
        for name, check in self.m_checks.items():
            check.setChecked(getattr(settings, name))

    def selected_settings(self):
        values = {
            name: combo.currentData()
            for name, combo in self.m_choices.items()
        }
        values.update({
            name: check.isChecked()
            for name, check in self.m_checks.items()
        })
        return self.m_settings.with_changes(**values)
