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

## 15 November 2026: 4x internal PNG capture pair

The user supplied two **lossless PNGs** of the ORIGINAL selection:

| Capture | Resolution | SHA-256 |
| --- | --- | --- |
| PCSX2 D3D12 4x | 958×719 | `053a2f214f493e12f747b18b3fc0e5e6b3d962413b57bb04fff7a85235fae740` |
| Qt comparison 4x | 2048×1536 | `05e0573ed17566bc93d4f5286d998d2b5cadd621c97bb243c88024d00385753b` |

These screenshots remain **user-owned**, and are **not checked in**.
The Qt PNG is its internal supersampled render target; the PCSX2 PNG
is the emulator's 958×719 output capture. Compare at a **common
final output resolution**, not pixel-for-pixel at their distinct native
sizes.

The new optional pixel comparison resizes the Qt image to 958×719 with
a fixed **bilinear** output filter, does **not** auto-register/align
the screenshots, and measures RGB absolute error. A reference-luminance
3×3 min/max gradient of at least 20/255 defines edge regions; all
other pixels are counted as flatter regions.

| Statistic | RGB mean absolute error | RGB RMS error |
| --- | ---: | ---: |
| Full frame | 16.613/255 | 32.545/255 |
| Reference edges (50.198% of pixels) | 29.345/255 | 44.514/255 |
| Reference flatter regions | 3.779/255 | 11.377/255 |

This provides useful evidence that visible differences are concentrated
on outlines, FFON glyph edges, sprite alpha transitions and texture
sampling rather than large uniform fills. For instance, PCSX2's sky
sample (110,200,201) and the corresponding normalized Qt sample
(111,200,201) differ in red by only one value. **Do not**
assume an exact native GS filter or fix the output by modifying
verified coordinates; native animation ages, sampling mode, blending,
rendering APIs and capture post-processing may all differ.

Usage:

```sh
cd arika-py_on_rs
python compare_menu_captures.py original.png menu_comparison.png \
    --pixel-metrics --diff-image render_diff.png --json
```

The PNG heatmap is a contrast-enhanced visual aid. Quantitative
metrics are computed from the **original unenhanced** RGB differences.
The default command remains the original native help-text line-bound
comparison for regression compatibility. Test fixtures are synthetic;
the two PNGs and all copyrighted textures remain outside the repo.

**PCSX2 semantics:** Bilinear (PS2) follows the game's per-draw
filtering choice. It is not an instruction to force linear filtering
on all 2D sprites. The current Qt "Bilinear (PS2)" preset is still
only a global approximate linear filter; matching the emulator's
per-draw sampling requires actual GS TEX1 state and draw-command
consumer recovery. Do not claim filtering parity based on this
reference pair alone.

## Native help-line count and initializer-filter follow-up

The capture comparator now accepts `--item` (default `original`)
with the seven ELF-derived menu item names. It reads the
`NATIVE_HELP_RECORDS` count for that selection rather than always
scanning four lines. **VERSUS** and **OPTIONS** have exactly three
text rows, and no fourth row is measured. Every menu selection is
covered by synthetic report-backed tests:

```sh
python compare_menu_captures.py pcsx2_versus.png qt_versus.png --item versus --json
python compare_menu_captures.py pcsx2_options.png qt_options.png --item options --pixel-metrics
```

The original `--item original` four-line baseline remains the
default. The pixel-difference metrics are still computed over the
**entire** screenshot rather than just the help text.

Further native sprite research in `NATIVE_MENU_GS_SAMPLING.md`
has now recovered four **specific** texture-attachment initializer
sites, including the banner and help panel. All four initialize
filter selector 1 (linear), clamp selector 0 (enabled).
The original-ELF bounded **menu-adjacent** code scan now resolves
**66 initial-linear and 11 initial-nearest** setter callsites.
Fifty-nine linear and seven nearest sites follow an adjacent
literal-argument pattern; eleven further sites were audited
instruction-by-instruction (seven linear, four nearest).
All eleven nearest callsites have containing-routine and
external-caller provenance, but these are **not** 77 proven
main-menu-owned draw sprites.
This does **not** establish active draw-time GS state, so Qt's
comparison preset has **not** been silently changed.
