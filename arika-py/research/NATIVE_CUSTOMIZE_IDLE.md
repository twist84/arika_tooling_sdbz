# CUSTOMIZE coupled per-part idle

Report version 21 extends `character_idle` with item 5's concrete callback at `0x0037F7F0`. `step_coupled_idle(primary_age, secondary_age, component)` reconstructs both clocks and the three part-offset pairs. The textured viewer now enables idle motion for four items: ORIGINAL, Z SURVIVOR, TRAINING and CUSTOMIZE.

## Curves and clocks

| Role | Value address | Time address | Values | Times |
|---|---|---|---|---|
| Base motion | `0x004AA3B8` | `0x004AA3C8` | 0, -4, 0 | 0, 80, 160 |
| Secondary sway | `0x004AA3E0` | `0x004AA400` | 0, 0.4, 0, 0.4, 0, 0 | 0, 10, 20, 30, 40, 640 |

The native sample counts are three at GP-19240 and six at GP-19236. Both clocks increment by one on each idle callback and subtract their own period once when greater than or equal to that period. The primary clock is at component +8. The secondary clock is at +488, immediately following the three X/Y part offsets at +464 through +484.

Let the interpolated primary value be B and secondary value be S. The three offsets are (B,B), (B+S,B+2S), and (B-S,B-2S). The Y factor 2 comes from GP-19232. The implementation preserves float32 operation boundaries, including native accumulator multiply/add and multiply/subtract behavior in the two opposed parts. The scalar comparison interpreter gained MSUB.S for the actual callback.

## Initialization scope

The concrete entry-start callback `0x0037F7A0` clears the six part-offset words, but does not clear the secondary timer at +488. Its initialization elsewhere is not established by this pass. The API therefore takes an explicit secondary clock. The integrated diagnostic trace chooses zero initially and records that choice in its limits; this is not presented as a captured native clock value or a verified reset on each selection.

The existing authored viewer timeline begins idle after whole-character entry at sample 22, stops updating idle at the sample-120 exit request, and retains the last offsets during whole-character exit. Changing selection in the viewer selects an independent diagnostic timeline, rather than reconstructing global native state across selection changes.

## Integration and validation

`examples/menu_character_idle_trace.json` now includes the recovered fourth idle callback. The three earlier idle implementations remain unchanged. The viewer's part-idle toggle switches CUSTOMIZE between the coupled motion and zero per-part offsets; whole-character entry/exit remains independently available.

All 81 menu tests pass. New tests compare 400 native CUSTOMIZE callback executions against both updated clocks and every part-offset float bit. Cases cover fractional clocks, both wrap boundaries, secondary pulses, its long quiet interval and out-of-normal-range clocks. The actual native interpolation and accumulator instructions execute in the scalar interpreter. The HTML Canvas test checks that toggling CUSTOMIZE idle changes its rendered parts; prior atlas, UV, depth, sky, visibility and three-item idle checks still pass.

These are host-float32 comparisons, not PS2 hardware FPU/accumulator emulation. Full-browser playback remains untested. VERSUS, DRAGON SUMMONING and OPTIONS idle callbacks, emphasis motion and actual selection scheduling remain pending.
