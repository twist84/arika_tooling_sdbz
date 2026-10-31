# Per-part character idle: first verified callbacks

CUSTOMIZE coupled idle is now covered by `NATIVE_CUSTOMIZE_IDLE.md`; this document records the first three callbacks.

Report version 20 adds `character_idle`. `arika_menu_idle.py` reconstructs concrete idle callbacks for ORIGINAL (Cell), Z SURVIVOR (Gohan) and TRAINING (Goku). The textured viewer enables these by default with a separate comparison toggle. Other character idle callbacks and emphasis remain pending.

## Native callbacks

| Item | Callback | Values | Times | Part offset array |
|---:|---|---|---|---:|
| 0 | `0x0037FFE0` | 0, 4, 0 | 0, 60, 120 | +1040 |
| 1 | `0x003809A0` | 0, -2, 0 | 0, 60, 120 | +608 |
| 4 | `0x00380D50` | 0, 3, 0 | 0, 40, 80 | +752 |

Each callback increments its own float age by one, subtracting the period once when age is greater than or equal to the final time. It then uses the existing scalar interpolation helper. This differs from the generic 99999-age wrapping in other menu components. The report records the original function words, curve addresses and sample-count bytes.

The interpolated value is multiplied by these per-part X/Y weights, in source record order:

| Item | Per-part weights |
|---:|---|
| 0 | (0,2), (0,3), (0,3), (0,3), (0,1), (0,2), (0,2) |
| 1 | (0,2), (0,1), (0,3), (0,3) |
| 4 | (0,2), (0,1.5), (0,1), (-0.5,2), (0.5,2) |

Cell's decompiled callback incorrectly appears to loop forever and apply one weight. Native jump table `0x004CC920` selects seven finite cases. Its targets and instructions are included in the comparison; different parts actually use factors 1, 2 or 3. Native explicit zero stores are preserved as positive zero, including when the interpolated value is negative.

## Viewer integration

`trace_characters(report, idle=True)` adds verified per-part offsets through the existing `pose_part` geometry builder. The authored timeline finishes whole-character entry at sample 22; idle callbacks begin on sample 23. Exit is requested at sample 120. Last idle offsets are retained during whole-character exit because exit-start does not clear the part arrays. Character geometry becomes inactive at sample 130.

`examples/menu_character_idle_trace.json` contains the integrated trace. Items 2, 3, 5 and 6 retain zero part offsets; their trigonometric/multiple-curve callbacks are not approximated. The original `menu_character_trace.json` and default `trace_characters` behavior retain zero idle offsets for comparison.

The textured viewer's **Part idle: ORIGINAL / Z SURVIVOR / TRAINING** toggle switches the enabled items between animated and zero-offset parts. Whole-character motion must also be enabled. Existing scenery strips, shared layers, labels and depth ordering remain intact. The static reference-layout PNG remains the zero-idle baseline; an arbitrary idle sample can move parts relative to that baseline.

## Validation

All 80 menu tests pass. Added tests execute 630 native idle updates with the real interpolation helper, across the three callbacks, fractional ages, wrap boundaries and out-of-normal-range ages. Every stored part offset and updated timer matches float32 bits. Cell's native jump table executes in the interpreter; its loop is bounded. The scalar interpreter gained SLTIU support for that switch dispatch.

Trace tests verify idle begins after entry, only supported items change, and exit still removes character geometry. The actual HTML JavaScript Canvas checks also verify that toggling idle changes the rendered character while retaining all previous layer, sky coverage, UV and exit checks. The new default render was visually inspected. Full-browser playback remains untested; host float32 is not PS2 hardware FPU/accumulator emulation.

Next: remaining concrete idle callbacks, emphasis/shake, and native activation/selection timing. No complete per-part animation coverage is claimed by this subset.
