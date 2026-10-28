# Native menu strip clock and clipping

`arika_menu_strips.py` ports the isolated strip clock (`0x003740D0`) and clipping/draw-command helper (`0x00374110`) for the supported `SLES_541.61`. It exports timed sprite command traces, not textured images or a complete menu player. The main research report is version 7 and includes the extracted instruction words under `strip_kernels`.

## Use

```sh
python arika_menu_strips.py SLES_541.61 strip2.json --item 2 --steps 2522
python arika_menu_strips.py SLES_541.61 strip6.json --item 6 --steps 2452
python arika_menu_strips.py SLES_541.61 strip0.json --item 0 --origin 0 0 --steps 120
python -m unittest discover -p 'test_arika_menu*.py'
```

All four strip origins can now be derived from the verified startup baseline: items 0/2/4/6 use (0, 0), (128, 86), (0, 134) and (208, 230), with zero component animation offsets. `--origin X Y` remains an explicit override. See `MENU_STARTUP.md`; startup defaults are not captured runtime positions.

`--phase`, `--motion-offset` and `--depth` default to zero and can be supplied explicitly. The trace draws at the current local phase, then steps the strip clock once. This is an explicit isolated schedule; native owner callback ordering and wall-clock tick frequency are not established. There is no inferred FPS or gameplay timing.

## Recovered behavior

The clock rounds to float32, adds one, and subtracts the period once when the new phase reaches or exceeds it. It does not use general modulo: phase 7 and period 3 become 5, matching the helper even though that input is outside an ordinary in-range cycle.

The drawing helper selects a source extent from width for orientation 0 or height for nonzero orientation. It subtracts one from that extent, divides by the period, and offsets the initial X position by negative phase times that rate. It then visits exactly two strip pieces:

1. Copy the original UV rectangle for the piece.
2. Clip the left edge against start + motion offset, adjusting source U or V and the remaining extent.
3. Clip the right edge against end + motion offset, truncating the clipped amount to an integer.
4. Emit a sprite command only if the remaining extent is positive, using remaining extent + 1 as the source width/height.
5. Advance the X position by the remaining extent and increase depth by one, including when no command was emitted.

Signed-16-bit source-coordinate/extent updates and float32 scalar steps are preserved. The port supports the positive signed-16-bit source dimensions used by the recovered descriptors. It rejects invalid periods, non-finite parameters and inverted clip ranges.

Each emitted command contains the clipped UV X/Y/width/height, sprite X/Y position, depth, rotation and anchor mode. Orientation 1 selects float32 pi/2 rotation and anchor mode 3; orientation 0 uses zero rotation and anchor mode 1. The rotation is recorded as a command input; rotated quad rasterization is not implemented here. The phase is unchanged by drawing; the depth increases belong to the embedded sprite's per-draw state, not the strip clock.

## Validation

Thirty menu tests pass. A separate scalar interpreter executes the extracted native clock and complete clipping helper. It handles the helpers' branch delay slots, signed integer shifts/conversions, float comparisons and accumulator operations. The UV-setter and sprite-draw calls are intercepted to capture the emitted commands; their downstream rendering is not emulated.

- 280 clipping cases compare command count, exact UV rectangles, float-bit X/Y and depth, and final embedded-sprite X/depth.
- 280 clock cases compare the resulting phase bits.
- Cases include all four researched strip descriptors at six phase boundaries, plus 256 deterministic synthetic cases covering both orientations, zero-length output, clip edges and fractional/negative offsets.

Both implementations use host float32 arithmetic with a host-modeled accumulator. The checks validate the instruction/control-flow port under those arithmetic semantics. They do **not** establish PS2 hardware FPU/accumulator bit accuracy or native pixel output.

## Included traces

`examples/menu_strip_item2_trace.json` has 2,522 samples and 4,897 clipped sprite commands. `examples/menu_strip_item6_trace.json` has 2,452 samples and 4,544 commands. Both use ELF-derived origins with explicit zero animation/depth inputs; both include the phase wrap back to 0 and then 1. They do not claim to reproduce an actual captured game frame sequence.

## Remaining work

Restricted rotated geometry previews are in `ROTATED_MENU_STRIPS.md`; the shared tiled element's scroll calculation is now in `NATIVE_MENU_TILES.md`. Next: texture sampling, runtime positions and owner animation/visibility/compositing. Companion/particle playback is separate. These previews still do not reconstruct a native menu frame.
