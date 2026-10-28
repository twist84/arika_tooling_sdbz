# Plain-sprite geometry

Version 6 introduced `plain_sprite_geometry`; the version 12 startup model expands the SVG to 66 item quads plus ten shared-layer quads. These remain startup-baseline diagrams at zero explicit animation offsets, not a complete or visibility-correct menu frame. See `MENU_STARTUP.md` for the correction from raw file data.

```sh
python arika_menu_plain.py SLES_541.61 plain_sprites.json
python arika_menu_layout.py SLES_541.61 menu_layout.svg --json menu_layout.json
python -m unittest discover -p 'test_arika_menu*.py'
```

## Recovered calculation

The plain sprite type uses draw helper `0x002FDDB0`, unlike the centered/anchored component sprite helper `0x002FD4A0`. Its first emitted point is the sprite's X/Y position. Its second point is:

```
right  = x + scale_x * abs(u1 - u0)
bottom = y + scale_y * abs(v1 - v0)
```

Thus the plain sprite has a top-left origin at positive scale. Negative scale reverses geometry; reversed UV endpoints reverse sampling without changing the absolute source extent. The native size setter `0x002FD970` stores 16-bit endpoint sums, so `plain_sprite()` preserves signed-16-bit wrapping when converting X/Y/width/height to endpoints. Pixel UV endpoints remain in the report; normalized texture coordinates and sampling are outside this port.

The scalar endpoint block at `0x002FE138` through `0x002FE1AC` is included as 30 extracted instruction words. The test interprets its integer, conversion, ADDA.S and MADD.S operations using host float32 accumulator arithmetic and compares float bits against the port. It now covers 31 recovered geometries and 128 deterministic synthetic cases. All 159 comparisons match. This does not establish PS2 hardware accumulator/FPU bit accuracy or validate texture sampling/command rendering.

Fifty-seven menu tests pass. The geometry SVG is also rendered for visual inspection.

## First-group results

All 21 first-group static sprites now have startup-baseline positions. The three formerly omitted sprites are resolved as follows:

| Item | Sprite | Initial value |
|---:|---|---|
| 0 | Literal 0 | Base (0, 0), from verified zero-fill |
| 3 | Literal 0 | Additional Y offset 0; fixed Y scale 204 |
| 3 | Literal 1 | Additional Y offset 204, from constructor |

Item 4's second literal sprite adds the constant X/Y offset (164, 9). Decoration scale is applied independently, including X scale 21.5 in item 4. The report preserves UV orientation and vertex/bounds data. Zero-valued positions come from verified startup initialization, not a guess about captured runtime state.

These 21 quads join 38 middle-group parts and seven third-group overlays, making 66 item quads. Each diagram is fitted independently; the seven items are not asserted to be simultaneously visible.

In the SVG, `F:L0` denotes first-group literal sprite 0 and `F:D0` denotes first-group decoration 0. Short labels keep the denser diagrams readable.

## Shared results

Ten shared plain-sprite geometries are recovered: the background, conditional overlay, banner, and all seven small components. The banner uses its base with zero animation offsets, not its initial animated position. The conditional overlay scales to 512 by 448, but its draw gate and state-driven alpha are not applied.

Small component 2 now uses its verified zero-fill base (0, 0). The tiled element remains a separate phase-dependent pass in `arika_menu_tiles.py`. Static shared geometry has its own panel with visibility gates unapplied. Native call order in `MENU_LAYERS.md` is not a recovered final compositing order.

## Remaining work

Isolated strip clock/clipping traces are in `NATIVE_MENU_STRIPS.md`, rotated geometry previews in `ROTATED_MENU_STRIPS.md`, and tile scroll traces in `NATIVE_MENU_TILES.md`. Next: textured rendering, runtime position initialization, then owner animation/visibility/compositing. Companion/particle playback remains separate. No textures or full menu renderer are added by this update.
