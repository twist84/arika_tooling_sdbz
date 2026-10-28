# VERSUS per-part idle

Report version 22 adds item 2 to `character_idle`, bringing verified idle support to five items. Its callback `0x00381210` updates nine independent part-offset pairs at component +1328 onward. The existing textured viewer idle toggle now includes VERSUS.

## Curve and native switch

The curve values (0,4,0) begin at `0x004AA818`, and times (0,60,120) at `0x004AA828`. The sample-count byte at GP-19088 is three. Each callback increments float age, subtracting 120 once when age is at least 120, then samples the native scalar interpolation helper.

The decompiler presents another false infinite loop. Native jump table `0x004CC9A0` contains nine finite cases. These apply the following X/Y weights to the curve value, in sprite-record order:

| Part | X weight | Y weight |
|---:|---:|---:|
| 0 | -0.3 | 0.75 |
| 1 | 0 | 0.5 |
| 2 | 0 | 0.75 |
| 3 | 0 | 0.5 |
| 4 | 0.25 | 0.5 |
| 5 | 0 | 0.5 |
| 6 | -0.2 | 0.5 |
| 7 | 0 | 0.5 |
| 8 | 0 | 0.5 |

The -0.3 and -0.2 literals use their actual float32 values, and native explicit zero stores remain positive zero. The report includes the callback words, count/curve locations and all jump-table targets. These offsets flow through the existing `pose_part` part-offset fields. Item 2's separate component-offset subtraction convention is preserved for whole-character entry/exit.

## Integration and validation

`examples/menu_character_idle_trace.json` and the offline textured viewer now include VERSUS motion. As before, the diagnostic timeline starts idle after whole-character entry at sample 22 and retains the last part offsets during its authored exit. DRAGON SUMMONING and OPTIONS remain at zero per-part idle offsets; emphasis and native selection scheduling remain unresolved.

All 82 menu tests pass. The linear idle test now executes 840 actual native updates across items 0,1,2,4, including VERSUS's nine-case switch, fractional phases, wrap boundaries and out-of-normal-range ages. CUSTOMIZE's 400 independent coupled-clock comparisons remain passing. A new VERSUS test checks relative part weights at the curve peak and phase wrap. The actual HTML JavaScript Canvas validator also checks that the VERSUS idle toggle changes the rendered parts while all previous layer/depth/sky/visibility checks still pass.

Comparisons use host float32, not PS2 hardware FPU/accumulator emulation. Full-browser playback remains untested. Next are the circular/trigonometric idle paths for OPTIONS and DRAGON SUMMONING, followed by emphasis and native activation timing.
