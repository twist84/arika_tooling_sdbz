# Shared banner motion

Small-component motion is now available in `NATIVE_MENU_SMALL.md`; add `--small` to the integrated example. Earlier examples retain their original behavior by default.

Report version 15 adds `shared_banner`. `arika_menu_banner.py` ports the shared banner's entry and exit curves, phase dispatch and plain-sprite geometry. The integrated shared-scheduler example can now run real banner updates alongside the recovered tile/companion owner. Small-component animation callbacks remain unresolved.

## Native evidence

| Role | Address |
|---|---|
| Initial phase/age/offset writes | `0x003783C0` |
| Banner update | `0x00378480` |
| Entry curve callback | `0x00378590` |
| Active callback (returns zero) | `0x00378610` |
| Exit curve callback | `0x00378620` |
| Draw placement | `0x003786A0` |
| Start entry / start exit | `0x003786F0` / `0x00378700` |
| Scalar interpolation helper | `0x002C2C10` |

Table `0x004F1C30` contains entry/active/exit callbacks at offsets 8/12/16. The extractor verifies these and the six initialization words. Initialization writes phase +112 and float age +116 to zero, X offset +120 to -512, and Y offset +124 to zero. Source setup uses resource entry 2, UV X/Y/W/H (0, 256, 264, 48) and depth 99.

## Curves and transitions

| Curve | Value address | Time address | Sample count | Values | Times |
|---|---|---|---:|---|---|
| Entry | `0x004FA680` | `0x004FA688` | 2 | -256, 0 | 0, 10 |
| Exit | `0x004FA698` | `0x004FA6A0` | 2 | 0, -256 | 0, 5 |

For these verified finite, increasing two-sample curves, the native helper linearly interpolates inside the interval and returns endpoint values outside it. The port rounds subtraction, division, multiplication and addition to host float32. The supported API rejects non-finite values, mismatched arrays and non-increasing times; it does not claim to reproduce malformed/native out-of-bounds curve behavior. The native helper reads a trailing time word on its fallback path; test memory includes the actual adjacent sample-count word.

Start entry writes phase 1 and age zero without changing offsets. Consequently the banner remains at initial X=-512 on the start pass. The following update increments age to 1 and samples entry, producing X approximately -230.4. This jump is preserved rather than smoothing from -512. At age 10, entry snaps to its last sample, sets phase 2 and resets age. Active returns zero, so the banner remains active.

Start exit writes phase 3 and age zero, also preserving offsets. Exit reaches -256 at age 5, then sets phase/age to zero. Inactive updates leave all fields unchanged. Every nonzero phase increments age and subtracts 99999 once only when the result is strictly greater than 99999; unsupported nonzero phase values increment age without invoking a curve callback.

Drawing adds base (0, 16) to the offsets. The native shared draw calls banner drawing independently of its update phase, so an inactive banner still has a geometry position. The port does not invent phase-based hiding. Texture sampling, viewport clipping, alpha and final scene depth ordering are outside this diagnostic geometry.

## Integrated example

```sh
python examples/menu_shared_schedule.py examples/menu_shared_banner_trace.json --banner
```

`--banner` enables recovered banner start/update/exit callbacks in the shared-scheduler example. Its default behavior and older trace are preserved. The version 2 trace records banner phase, age, offsets and geometry each sample. Shared activation at sample zero, native RNG seed 1, and shared exit request at sample 120 remain authored choices. Small-component animation callbacks remain explicit no-ops; their scheduler phase writes are retained.

The entry completes at sample 10. Shared exit starts banner exit at sample 120 after that pass's banner update; the banner completes exit at sample 125. The parent continues updating through sample 129. `previews/menu_shared_banner.svg` contains the resulting banner-only geometry animation, sampled every update. Its 60 ticks/s is an authored display rate, not a native timing measurement. The SVG renderer now supports the single-piece banner preview without changing previous strip/tile/companion behavior.

## Validation

All 69 menu tests pass. New tests compare 520 curve samples against the actual interpolation instructions, including before/after endpoints and fractional ages. Another 180 lifecycle cases compare banner phase, age and both offsets against actual update/callback/interpolation instructions, including real nested native calls, inactive/unknown phases and age wrapping. Start/exit helpers are checked for offset preservation and return-delay writes. Tests also verify endpoint geometry and invalid input rejection.

The original shared-scheduler example regenerates identically with banner motion disabled. The integrated banner example checks entry/exit endpoint samples. A mid-entry SVG sample was rendered for static inspection; interactive playback remains untested. These comparisons use host float32 and do not establish PS2 hardware FPU/accumulator bit accuracy or native rendered pixels.

Remaining work: small-component curves and lifecycle, actual outer activation/exit timing, captured global RNG synchronization, texture selection/sampling, clipping and full compositing.
