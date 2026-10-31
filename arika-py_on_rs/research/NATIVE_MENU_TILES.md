# Shared tiled-element scroll

`arika_menu_tiles.py` ports the isolated shared-menu tile phase and two-copy placement calculation. The version 9 main report includes the relevant native words and constants in `tile_scroll_kernel`.

```sh
python arika_menu_tiles.py SLES_541.61 tiles.json --svg tiles.svg
python arika_menu_tiles.py SLES_541.61 tiles_offset.json --phase 1024 --offset 20 -10 --steps 120
python -m unittest discover -p 'test_arika_menu*.py'
```

The tool uses the supported ELF's recovered base position (0, 320), resource entry 2, source rectangle (0, 384, 512, 128), and initial sprite depth 85. X/Y animation offsets default to explicit zero and can be supplied using `--offset`. This is not an integrated owner animation/state simulation.

## Native placement

Draw helper `0x00376290` computes the horizontal span as signed source U1 minus signed source U0. For the researched asset, that is 512 pixels. It divides this span by 2048 and computes:

```
x = base_x + offset_x - phase * (span / 2048)
y = base_y + offset_y
```

It draws at (x, y), increments X by one span, draws again, then increments X by one more span even though there is no third draw. The port preserves this final embedded-sprite position as well as the two emitted quads. Signed endpoint spacing is kept separate from the absolute source extent used by plain-sprite geometry.

The update helper `0x003761B0` advances the float phase by one and subtracts 2048 once when it reaches or exceeds that value. The isolated tool reuses the already-ported float32 single-subtraction clock. It does not replace this with general modulo.

At phase 2047 with zero offsets, the two X positions are -511.75 and 0.25, and the final stored X is 512.25. The next ordinary phase is zero. The source dimensions and positions remain float32 inputs to the diagnostic geometry; there is no texture sampling or native scissor/compositing pass.

## Companion behavior remains separate

The same native update routine decrements a separate random-event timer and may call a companion spawn path before advancing phase. That behavior is not ported. The native draw helper also calls `0x003763B0` and `0x00376600` after drawing both tiles; the latter visits ten 112-byte companion slots. These calls are recorded, not executed by the exporter.

The scalar test interpreter stubs those two direct calls and captures the two tile sprite draws. Clock comparisons initialize the event timer to a positive value so the event does not fire. Accordingly, the validation covers the no-event phase path, not the random-event branch or companion rendering. This shared companion system is distinct from the six-slot item-3 particle system documented in `MENU_FIRST_COMPONENTS.md`.

## Validation

Forty menu tests pass:

- 264 tile draw cases match interpreted native positions, depths, final stored position and companion-call sequence.
- 264 phase updates match the native no-event path, with the event timer's decrement also checked.
- Additional tests cover seam/wrap boundaries, signed endpoint spacing and invalid inputs.

The interpreter and port use host float32 arithmetic. The comparisons do not establish PS2 FPU/accumulator hardware bit accuracy, texture sampling or native pixel output.

## Included example

`examples/menu_tile_trace.json` contains 2,050 samples and 4,100 quads, including phases 2047, 0 and 1 across the wrap. `previews/menu_tile_scroll.svg` is its animated geometry preview. It uses the existing discrete SVG renderer with an authored display rate of 60 ticks/s and sample stride 15; those values do not establish the game's tick frequency.

The SVG's initial sample was rendered for static visual inspection. Interactive browser playback remains untested here. Open it in a browser supporting SVG animation; static viewers may show just the first sample. Viewport clipping, textures, visibility and depth ordering are not rendered.

The tile pass remains separate from the static menu diagrams because its positions depend on phase. `plain_sprite_geometry.separate_passes` now identifies that export path rather than calling the calculation unresolved.

## Next work

Shared companion lifecycle rules are now ported in `NATIVE_MENU_COMPANIONS.md` with explicit diagnostic random inputs. Next: runtime positions/global RNG synchronization, textures and owner animation/visibility/compositing. The exporter still does not reproduce a full native menu frame.
