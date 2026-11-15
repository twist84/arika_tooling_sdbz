# PCSX2 render comparison controls — EU-beta main menu

Scope: [PR #14](https://github.com/twist84/arika_tooling_sdbz/pull/14),
`arika-py_on_rs/arika_menu_editor.py`. The reference is the user's
PCSX2 Graphics > Rendering screenshot (15 November 2026); **no** emulator
configuration file, game assets or screenshots are included in this repo.

## Recovered reference settings

| PCSX2 control | Screenshot value | Effect in Qt comparison preview |
| --- | --- | --- |
| Graphics API | Direct3D 12 | Reference only; Qt uses QPainter |
| Adapter | NVIDIA GeForce GTX 1660 SUPER | Reference only |
| Internal Resolution | 4x Native (~1440px/QHD in PCSX2 UI) | **Approximate**: supersample 512-wide logical menu canvas at 4x before window presentation |
| Texture Filtering | Bilinear (PS2) | **Approximate**: Qt smooth source texture sampling |
| Trilinear Filtering | Automatic (Default) | Reference only; no mip selection/GS TEX1 emulation |
| Anisotropic Filtering | Off (Default) | Reference only |
| Dithering | Unscaled (Default) | Reference only; no GS 16-bit dithering emulation |
| Blending Accuracy | Basic (Recommended) | Reference only; QPainter has no GS destination-alpha, TEST or ZBUF |
| Mipmapping | Checked | Reference only |
| AA1 | Checked | Reference only |
| Manual Hardware Renderer Fixes | Checked | Reference only |
| Accurate Alpha Test | Unchecked | Reference only |
| Rasterizer Ordered View | Unchecked | Reference only |

These are the **resolved** setting values shown in square brackets
after “Use Global Setting,” not independent per-game overrides.

PCSX2 source `pcsx2/Config.h` provides the corresponding configuration
names (`UpscaleMultiplier`, `TextureFiltering`, `TriFilter`,
`MaxAnisotropy`, `Dithering`, `AccurateBlendingUnit`,
`Mipmap`, `HWAA1`, `ManualUserHacks`, `HWAccurateAlphaTest`,
`HWROV`). This reference is *not* wired to PCSX2's own process.

## Using the editor controls

1. Keep the menu's **Standard (4:3)** presentation for the supplied
   PCSX2 screenshots. Use **Native logical state** if matching the
   settled native help frame, and advance until the help component is
   in phase 2.
2. Choose **PCSX2 graphics…**. Click **Restore screenshot preset** to
   restore every value from the image, check **Use PCSX2 comparison
   preview**, and click OK.
3. **Internal Resolution** controls a Qt QImage render target sized
   `512 * factor` wide by `presentation_height * factor` high
   (4x Standard 4:3 yields **2048×1536**). The game's recovered logical
   geometry remains **512×448** before presentation. This is *not*
   necessarily the same internal GS raster dimensions as PCSX2's 4x
   option; those depend on native framebuffer and display registers.
4. **Texture Filtering** switches nearest/linear
   `QPainter.SmoothPixmapTransform` sampling for sprites, the help
   frame, and the final QImage resize. In particular **Bilinear
   (PS2)** is mapped to linear **only as a visual approximation**:
   the native per-primitive GS TEX1 control is not recovered. The
   existing `Smooth` debug checkbox remains unchanged when PCSX2
   comparison mode is disabled.
5. Use **Capture comparison PNG…** for a *lossless Qt* preview at the
   selected internal canvas size. The sibling
   `.pcsx2-settings.json` file records every requested setting,
   the approximation/reference-only split, image size, presentation,
   selected menu item, and native lifecycle tick when applicable.
   It is **not** a native GS capture or a PCSX2 configuration export.
6. Compare this PNG with a PCSX2 PNG of the same selection and
   lifecycle pose using `compare_menu_captures.py`. That tool measures
   the existing ELF-based help line origins in 512×448 logical
   coordinates even if PCSX2's screenshot dimensions differ.

Example:

```sh
cd arika-py_on_rs
python compare_menu_captures.py original_pcsx2.png qt_comparison.png --json
```

## Strict limits and non-goals

- **No fake GS effects:** toggling dithering, blending accuracy, AA1,
  mipmapping, anisotropy, trilinear filtering, hardware fixes, accurate
  alpha test, or ROV changes the **recorded PCSX2 settings only**.
  It does not alter the Qt image. All are explicitly in the
  dialog's “not emulated by Qt” group.
- **No inferred texture state:** enabling “Bilinear (PS2)” does not
  infer TEX1/MMIN/MMAG from static file data or assign arbitrary
  per-sprite filtering. Actual texture sampling needs runtime GS state.
- **No native timing changes:** comparison mode only redraws from the
  current runtime snapshot and does not advance update clocks.
- **No PCSX2 changes:** dialog values do not read, edit or save the
  emulator's INI; the screenshot profile is a host-side comparison
  record.
- **No copyrighted captures in Git:** tests use synthetic images.

The source menu's native help origin, 25-unit row spacing, 12-unit FFON
ASCII advance and panel texture bounds remain unchanged by this work.

See `NATIVE_MENU_HELP_DRAW.md` for reference screenshot alignment
results, and `NATIVE_MENU_LIFECYCLE_PLAN.md` for the remaining glyph UV
and active-GS-state milestones.
