"""PCSX2 graphics comparison profile for the native menu Qt preview.

The values describe the user's PCSX2 screenshot, not a claim that the
Qt/QPainter renderer implements the PS2 GS hardware or the PCSX2 backend.
Only the internal render-target scale and a broad source filtering choice
can be approximated by the current preview.
"""
from dataclasses import asdict, dataclass, replace


INTERNAL_RESOLUTIONS = (1, 2, 3, 4, 6)
TEXTURE_FILTERS = (
    ('Nearest', 'nearest'),
    ('Bilinear (PS2)', 'bilinear_ps2'),
    ('Bilinear (Forced)', 'bilinear_forced'),
    ('Bilinear (Forced excluding sprites)', 'bilinear_excluding_sprites'),
)
TRILINEAR_FILTERS = (
    ('Automatic (Default)', 'automatic'),
    ('Off', 'off'),
    ('Trilinear (PS2)', 'ps2'),
    ('Trilinear (Forced)', 'forced'),
)
ANISOTROPIC_FILTERS = (0, 2, 4, 8, 16)
DITHERING_MODES = (('Off', 'off'), ('Scaled', 'scaled'), ('Unscaled', 'unscaled'))
BLENDING_MODES = (
    ('Minimum', 'minimum'), ('Basic', 'basic'), ('Medium', 'medium'),
    ('High', 'high'), ('Full', 'full'), ('Maximum', 'maximum'),
)

# None of the options below is a pixel-accurate GS implementation.
PREVIEW_APPROXIMATE = frozenset(('internal_resolution', 'texture_filtering'))
PREVIEW_REFERENCE_ONLY = frozenset((
    'graphics_api', 'adapter', 'trilinear_filtering',
    'anisotropic_filtering', 'dithering', 'blending_accuracy',
    'mipmapping', 'aa1', 'manual_hardware_fixes',
    'accurate_alpha_test', 'rasterizer_ordered_view',
))


@dataclass(frozen=True)
class s_pcsx2_comparison_settings:
    graphics_api: str = 'Direct3D 12'
    adapter: str = 'NVIDIA GeForce GTX 1660 SUPER'
    internal_resolution: int = 4
    texture_filtering: str = 'bilinear_ps2'
    trilinear_filtering: str = 'automatic'
    anisotropic_filtering: int = 0
    dithering: str = 'unscaled'
    blending_accuracy: str = 'basic'
    mipmapping: bool = True
    aa1: bool = True
    manual_hardware_fixes: bool = True
    accurate_alpha_test: bool = False
    rasterizer_ordered_view: bool = False

    def validate(self):
        if self.internal_resolution not in INTERNAL_RESOLUTIONS:
            raise ValueError('unsupported Qt comparison render scale')
        for name, options in (
            ('texture_filtering', TEXTURE_FILTERS),
            ('trilinear_filtering', TRILINEAR_FILTERS),
            ('dithering', DITHERING_MODES),
            ('blending_accuracy', BLENDING_MODES),
        ):
            if getattr(self, name) not in (value for _, value in options):
                raise ValueError('invalid PCSX2 ' + name)
        if self.anisotropic_filtering not in ANISOTROPIC_FILTERS:
            raise ValueError('invalid PCSX2 anisotropic filtering setting')
        for name in (
            'mipmapping', 'aa1', 'manual_hardware_fixes',
            'accurate_alpha_test', 'rasterizer_ordered_view',
        ):
            if not isinstance(getattr(self, name), bool):
                raise ValueError('invalid PCSX2 ' + name)
        return self

    def with_changes(self, **values):
        return replace(self, **values).validate()

    def internal_canvas_size(self, display_height=384.0):
        """Logical 512-wide canvas supersampled at an integer factor.

        This is *not* the same as PCSX2's actual GS 4x render target,
        which depends on the emulated game's framebuffer properties.
        """
        self.validate()
        if not 0.0 < float(display_height) <= 512.0:
            raise ValueError('invalid logical presentation height')
        scale = self.internal_resolution
        return 512 * scale, round(float(display_height) * scale)

    def approximate_linear_filter(self):
        """Qt's closest source-texture approximation, not PS2 TEX1 logic."""
        return self.texture_filtering != 'nearest'

    def to_metadata(self):
        """Record the exact requested PCSX2 settings and preview caveat."""
        result = asdict(self)
        result['preview_applied_approximately'] = sorted(PREVIEW_APPROXIMATE)
        result['pcsx2_reference_only'] = sorted(PREVIEW_REFERENCE_ONLY)
        result['warning'] = (
            'Qt preview is not PCSX2/GS emulation; its texture filtering '
            'does not apply per-primitive PS2 TEX1 rules, and 4x uses the '
            '512-unit logical viewport rather than PCSX2 framebuffer sizes.'
        )
        return result
