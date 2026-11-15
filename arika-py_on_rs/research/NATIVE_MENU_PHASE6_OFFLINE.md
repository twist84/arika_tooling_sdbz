# Offline Phase 6 audit — native character idle and help text

EU-beta ELF: `SLES_541.61`, SHA256
`80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0`.
Review checkpoint: 15 November 2026, PR #14,
`feature/main-menu-native-navigation`. No game art,
fonts, screenshots or ELF bytes are committed.

## Character idle: already implemented, precision work outstanding

The 2026-11-15 Phase 6 plan was written before the later
character-idle milestones. The checked-in recovery code
`arika_menu_idle.py` and `arika_menu_children.py`
already implement **all seven** per-part callbacks:

| Item | Name | Idle callback | Native motion | Checked code |
| ---: | --- | --- | --- | --- |
| 0 | ORIGINAL | `0x0037FFE0` | 7 scalar-weighted parts | `step_idle` |
| 1 | Z SURVIVOR | `0x003809A0` | 4 scalar-weighted parts | `step_idle` |
| 2 | VERSUS | `0x00381210` | 9 scalar-weighted parts | `step_idle` |
| 3 | DRAGON SUMMONING | `0x00380450` | 8 parts: two circles and sway | `step_dragon_idle` |
| 4 | TRAINING | `0x00380D50` | 5 scalar-weighted parts | `step_idle` |
| 5 | CUSTOMIZE | `0x0037F7F0` | 3 parts with independent 160/640-clock curves | `step_coupled_idle` |
| 6 | OPTIONS | `0x0037FC00` | 2 circular parts | `step_circular_idle` |

The recovered native runtime calls each item's vtable +0x24
phase-two callback; the code verifies its target against the
ELF report. The scalar and coupled models have bitwise
float32 instruction-oracle tests, while OPTIONS and
DRAGON SUMMONING have **controlled-trigonometry** oracle
tests. Their original library functions at `0x1859D8`
(cosine) and `0x185C78` (sine) have not been ported;
the preview uses `math.cos/math.sin` rounded to
float32, so **last-bit EE libm parity remains unproven**.

The historical Phase 6 language "recover VERSUS,
DRAGON SUMMONING and OPTIONS" is no longer an
implementation backlog item. This milestone adds the
four previously omitted native idle suites
(`test_arika_menu_idle`,
`test_arika_menu_circular_idle`,
`test_arika_menu_dragon_idle`,
`test_arika_menu_emphasis`) to cross-platform CI.

### CUSTOMIZE's +488 reset is verified

The constructor value at +0x1E8 is still not proven.
`0x0037F7A0` entry start clears six part offsets.
But the active callback `0x0037F7E0` then performs
`sw zero,+8(a0)`, `jr ra`, and `sw zero,+0x1E8(a0)`
in its return delay slot. As a result, **normal
entry and re-entry into phase 2 reset both clocks**.
The runtime already models this and the new regression
directly executes the three native words. See
[NATIVE_CUSTOMIZE_IDLE.md](NATIVE_CUSTOMIZE_IDLE.md).
Do not infer the constructor's bytes from an observed
post-entry reset.

## Help panel: the apparent vertical displacement is mostly pixel aspect

The user supplied two ORIGINAL menu captures: PCSX2
**958×719** and the Qt editor **706×529**, both
approximately 4:3 displayed. The game artwork occupies
**512×448 logical coordinates** in the editor. The
horizontal and vertical image scales therefore differ.
For a screenshot of width `W`, height `H`:

```text
logical_x = screenshot_x * (512 / W)
logical_y = screenshot_y * (448 / H)
```

Do **not** use the horizontal factor for Y or compare
raw screenshot pixel coordinates. The differing pixel
aspect would create an apparent help-text Y error of
roughly **40–45 logical units** near its first line.

Approximate screenshot anchor picks (the pixels
are estimates, not byte-perfect original measurements):

| Anchor | PCSX2 pixels (958×719) | Qt pixels (706×529) | PCSX2 logical XY | Qt logical XY |
| --- | --- | --- | --- | --- |
| Outer help-frame upper-left | (55,447) | (43,324) | (29.4,278.5) | (31.2,274.4) |
| Text line 1 start | (165,524) | (121,386) | (88.2,326.5) | (87.8,326.9) |
| Text line 2 start | (165,564) | (121,416) | (88.2,351.4) | (87.8,352.3) |
| Text line 3 start | (165,606) | (121,446) | (88.2,377.6) | (87.8,377.7) |
| Text line 4 start | (165,647) | (121,475) | (88.2,403.1) | (87.8,402.3) |

This supports the current Qt help-text origin
`(87,324)` and line advance `25` logical Y
as **visually close**, and does not justify
changing panel Y or hardcoding a new "fix".

The frame itself is taken from **atlas entry 4**
of the user's `dis/main_menu.pix`, with its
source rectangle computed from actual decoded alpha
bounds rather than a drawn substitute. Glyphs
come from the user's FFON, not a system font.

`arika_menu_help_geometry.py` makes the already
existing preview rectangle, clip and FFON placement
explicitly testable and provides
`screenshot_to_logical`/
`logical_to_screenshot` helpers. Qt now reuses
these constants without changing output.
`test_arika_menu_help_geometry.py` checks
both screenshot anchor sets, the different axis
scales, 25-unit line spacing, fixed horizontal
glyph positioning and invalid inputs. The
regression uses **only numeric pixel picks**, not
copyrighted image assets.

### Actual font resource startup call recovered

Additional disassembly of the exact EU-beta ELF confirms that the
font already being loaded by the editor is the right *asset path*:

- The file-backed NUL-terminated string at EE VA
  `0x004CAFA0` is **`font/5-24-2.fon`**.
- The shared initializer `0x00326370` constructs
  that string address with `lui a0,0x4D` at
  `0x3263C4` and `addiu a0,a0,-0x5060` at
  `0x3263CC`, then calls the resource loader
  `0x001C6930` at `0x3263D8`.
- Its direct startup caller is at `0x3268F4`.
  This is a **shared program initialization path**,
  not a help-panel-local draw callback.
- `arika_editor.py` already loads precisely
  `font/5-24-2.fon` from the user's archive
  into the menu FFON decoder; no filename/path
  change is required.

This verifies the *resource source*, not the native
glyph-advance formula, layout rectangle or text
compositor. The initializer's file-read state
machine must not be mistaken for a glyph draw
callback. Next, trace consumers of the successfully
created font resource and the separate menu help
overlay owner.

### Native help-panel implementation is still unknown

`0x00379E60`, the original menu object's draw
callback, submits the shared visual owner, pending
old item, current item and arrows. It does **not**
directly issue the separately composited help-frame
artwork or FFON text in the inspected path.
The app wraps that callback, and some UI components
may be drawn by a different owner. The actual
native help-panel rectangle, sprite resource
lookup, line advance and font glyph metrics
have **not** yet been proven by tracing that
external call chain. The Qt rectangle and text
spacing are screenshot-calibrated estimates,
not native ELF assertions. See
[TEXTURED_MENU.md](TEXTURED_MENU.md).

## Further work without PCSX2

1. Trace font/help UI ownership and draw callbacks
   beyond `0x379E60`. Locate actual native
   sprite source UV, text positioning and glyph
   spacing, or retain explicit unknown provenance.
2. Trace native `cos/sin` leaf kernels and
   argument reduction if bit-exact EE idle motion
   is required; the existing controlled trig
   differential covers callback logic already.
3. Expand menu input/transition replay and
   offscreen UI/FFON tests without changing
   the 140-frame authored diagnostic clock.
4. Continue static GS `PRIM`, `RGBAQ`,
   `XYZ`, `UV/ST` and framebuffer code traces.
5. Ultimately capture active GS registers,
   runtime texture record bytes and full-frame
   pixels using PCSX2. Static ELF data cannot
   stand in for those runtime values.

No guessed animation timing was introduced, and
the existing Qt editor/native preview remain functional.
