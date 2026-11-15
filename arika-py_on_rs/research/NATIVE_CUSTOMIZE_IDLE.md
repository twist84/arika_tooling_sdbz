# CUSTOMIZE coupled per-part idle

Report version 21 extends `character_idle` with item 5's concrete callback at `0x0037F7F0`. `step_coupled_idle(primary_age, secondary_age, component)` reconstructs both clocks and the three part-offset pairs. The textured viewer now enables idle motion for four items: ORIGINAL, Z SURVIVOR, TRAINING and CUSTOMIZE.

## Curves and clocks

| Role | Value address | Time address | Values | Times |
|---|---|---|---|---|
| Base motion | `0x004AA3B8` | `0x004AA3C8` | 0, -4, 0 | 0, 80, 160 |
| Secondary sway | `0x004AA3E0` | `0x004AA400` | 0, 0.4, 0, 0.4, 0, 0 | 0, 10, 20, 30, 40, 640 |

The native sample counts are three at GP-19240 and six at GP-19236. Both clocks increment by one on each idle callback and subtract their own period once when greater than or equal to that period. The primary clock is at component +8. The secondary clock is at +488, immediately following the three X/Y part offsets at +464 through +484.

Let the interpolated primary value be B and secondary value be S. The three offsets are (B,B), (B+S,B+2S), and (B-S,B-2S). The Y factor 2 comes from GP-19232. The implementation preserves float32 operation boundaries, including native accumulator multiply/add and multiply/subtract behavior in the two opposed parts. The scalar comparison interpreter gained MSUB.S for the actual callback.

## Initialization and re-entry update (15 November 2026)

The concrete entry-start callback `0x0037F7A0` clears the six part-offset words, but does **not** clear the secondary age at +488. This historical observation remains valid; the *constructor's initial value* has not been established.

The later **phase-2 active callback at `0x0037F7E0` is now verified**. The entry-phase dispatcher calls this vtable +0x14 method on completion of character entry; the function consists of:

```mips
0x0037F7E0  sw   $zero, 0x8($a0)
0x0037F7E4  jr   $ra
0x0037F7E8  sw   $zero, 0x1E8($a0)  # return delay slot
```

Therefore **every normal entry/re-entry into active idle resets both the primary and secondary age to zero**, regardless of any stale secondary value left by the constructor or previous selection. `arika_menu_children.step_character` already models this; `test_arika_menu_runtime.py` checks the 22-step entry and re-entry, and `test_arika_menu_coupled_idle.py` now executes the three literal ELF instruction words to verify both stores and neighboring-field preservation.

The independent authored diagnostic trace can still choose its own initial secondary clock. That trace is not evidence about the object's pre-entry constructor bytes. Do not conflate these distinct timelines or assume that the constructor itself resets +488.

The existing authored viewer timeline begins idle after whole-character entry at sample 22, stops updating idle at the sample-120 exit request, and retains the last offsets during whole-character exit. Changing selection in the viewer selects an independent diagnostic timeline, rather than reconstructing global native state across selection changes.

## Integration and validation

`examples/menu_character_idle_trace.json` now includes the recovered fourth idle callback. The three earlier idle implementations remain unchanged. The viewer's part-idle toggle switches CUSTOMIZE between the coupled motion and zero per-part offsets; whole-character entry/exit remains independently available.

All 81 menu tests pass. New tests compare 400 native CUSTOMIZE callback executions against both updated clocks and every part-offset float bit. Cases cover fractional clocks, both wrap boundaries, secondary pulses, its long quiet interval and out-of-normal-range clocks. The actual native interpolation and accumulator instructions execute in the scalar interpreter. The HTML Canvas test checks that toggling CUSTOMIZE idle changes its rendered parts; prior atlas, UV, depth, sky, visibility and three-item idle checks still pass.

These are host-float32 comparisons, not PS2 hardware FPU/accumulator emulation. Full-browser playback remains untested. VERSUS, DRAGON SUMMONING and OPTIONS idle callbacks, emphasis motion and actual selection scheduling remain pending.
