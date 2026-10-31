# Rotated strip quads and animated geometry previews

`arika_menu_strip_preview.py` converts isolated strip command traces into rotated vertex data and animated SVG diagrams. It supports the two recovered strip rotations only: zero and float32 pi/2. No textures, alpha/state playback or native compositing are rendered.

## Run

```sh
python arika_menu_strip_preview.py SLES_541.61 examples/menu_strip_item2_trace.json strip2.svg --json strip2_quads.json
python arika_menu_strip_preview.py SLES_541.61 examples/menu_strip_item6_trace.json strip6.svg --stride 1 --ticks-per-second 120
python -m unittest discover -p 'test_arika_menu*.py'
```

The trace must match the supported ELF's SHA-256. Generate the command trace with `arika_menu_strips.py` first; see `NATIVE_MENU_STRIPS.md`. Input/output paths must differ, and the exporter rejects unsupported rotations, invalid piece IDs and non-finite command positions/depths.

The examples `previews/menu_strip_item2.svg` and `previews/menu_strip_item6.svg` are included, along with full quad traces in `examples/menu_strip_item2_quads.json` and `examples/menu_strip_item6_quads.json`. Open the SVGs in a browser that supports SVG animation. Static image viewers may show only the initial sample.

## Rotation and anchors

The component-sprite geometry helper `0x002FD4A0` passes **negative sprite rotation** to matrix builder `0x001074E0`. The native matrix construction uses a polynomial and square-root sequence, then builds its two-dimensional basis. The version 8 report stores the polynomial constants from `0x00439520` and the relevant VU arithmetic words under `strip_rotation_kernels`.

The port evaluates that polynomial/basis with host float32 arithmetic for the two supported inputs. Under those semantics, the recovered bases are:

| Command rotation | Local X axis in screen coordinates | Local Y axis in screen coordinates |
|---|---|---|
| 0 | (1, 0) | (0, 1) |
| float32 pi/2 | (0, -1) | (1, 0) |

Vertices begin with the native anchor table scaled by absolute source UV extents. The basis is applied before adding the sprite position. The rotated strip uses anchor mode 3, whose local rectangle runs from -width to zero in X and from zero to height in Y. Thus a rotated source of width 100 and height 20 becomes a screen rectangle 20 wide and 100 high, extending right/down from its sprite position. Pixel UV endpoints preserve their source order; depth is retained as metadata.

This is a restricted geometry port, not a general arbitrary-angle VU trigonometry implementation.

## Animation semantics

The SVG uses discrete sample changes, not interpolated geometry. `--stride` defaults to 15 trace ticks between retained samples; the last sample is always included. `--ticks-per-second` defaults to 60 as an **authored diagnostic display rate**, not a recovered game tick frequency. Change it to speed up or slow down the preview. Per-sample timing uses the trace's tick positions, including a shorter final interval.

Each of the two strip pieces has its own polygon and visibility animation. A piece is hidden when that sample emitted no command. Cyan denotes piece 0 and orange piece 1. The 512 by 448 outline is a reference region; geometry is not raster-clipped or depth-sorted to reproduce the game.

## Validation and limits

Thirty-five menu tests pass. A separate masked-vector interpreter executes the extracted VU polynomial and basis-building words using host float32 arithmetic. Both supported bases match. All 9,441 commands from the two included full-cycle traces also match a separate transform using the interpreted matrices, including every emitted corner. Tests cover rotation direction, anchors, discrete SVG key times, missing-piece visibility and invalid input.

Both SVGs were rendered for static visual inspection. Interactive browser playback has not been checked here. The interpreter does not emulate VU flags, pipeline timing or hardware accumulator precision; these comparisons do **not** establish PS2 hardware bit accuracy. They also do not validate native texture sampling or pixel output.

The shared tiled element's scroll-position arithmetic is now ported in `NATIVE_MENU_TILES.md`. Next: runtime position initialization, textures, and menu animation/visibility/compositing integration. Companion/particle playback remains separate.
