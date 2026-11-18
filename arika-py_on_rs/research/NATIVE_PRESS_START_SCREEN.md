# Native EU-beta Press Start (application ID 3)

## Scope and evidence

M1 reconstructs the **existing Arika Editor → Menu → Press Start** tab.
Target: Super Dragon Ball Z **Europe beta** `SLES_541.61`, exact ELF SHA-256
`80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0`.
EU retail has the same executable basename: **never infer region from filename**.
No copyrighted ELF, PIX, FFON, or PCSX2 captures are embedded in this repository.

All recovery functions fail closed against the original ELF hash, then
site-specific MIPS words/string pointers. CI uses synthetic source assets;
local optional-ELF tests use `SDBZ_EU_BETA_ELF`.

The two user-provided 1920×1040 PCSX2 windows depict the Press Start prompt
hidden and visible. **The complete gameplay picture is the crop
`(357,111,1206,903)`**, measured on these captures. The previous
`(307,96,1040,778)` rectangle was incorrect: it included window chrome
and cut off the copyright text. The new crop preserves both copyright lines.
It is a **screenshot-specific** viewport, not an extracted GS display register.
The native logical canvas remains **512×448**, presented at **4:3**;
native 512:448 coordinates must not be mistaken for a display aspect ratio.

## Application identity and native lifecycle

Both application IDs 2 and 3 use the name `CAppTitleMain`, but are separate
factories:

| ID | Factory | Constructor | Phase vtable | Role |
|---|---|---|---|---|
| 2 | `0x3F2D80` | `0x3F86E0` | `0x4F66F8` | Four-second title interval |
| **3** | `0x3F2D20` | `0x3F7150` | `0x4F6698` | **Interactive Press Start** |

App-ID-3 callbacks: init `0x3F71E0`, loader `0x3F7320`, begin
`0x3F7680`, update **`0x3F76A0`**, release `0x3F79A0`,
draw **`0x3F7AA0`**.

Loader phases 0→1→2→3→4 use `this+0x34`:

- Register groups **2,3,4,5,7,8,10,11,15** through `0x2FBDC0`.
- Poll `0x2FBEB0`, associate group 7 with `snd/etceff` and register group 8.
- Poll `0x2FBE30(16)`.
- Resolve resources through `0x3EF140`, construct sprites at
  `this+0x40`, `this+0xA0`, `this+0x100`.
- Begin transition, then report loader ready.

The native app-local float32 elapsed age `this+0x2C` drives its 1-second
one-shot callback and 20-second idle timeout; **it does not control prompt
blinking**. Start input is controller word `+0x22`, bit `0x10`, subject
to eligibility helper `0x2AFAD0`. Controller 1 is checked separately.

| App phase | Verified transition |
|---|---|
| 0 | Eligible Start takes precedence over idle and enters phase 1; otherwise `0x2AFD30` may reset age, or age ≥20 seconds starts attract fade, phase 10 |
| 1 | `0x2C0C90` and two `0x2C08A0` calls; enter phase 2 |
| 2 | When `0x2C0C20` is no longer busy, request app ID **42** through `0x3DFB00` |
| 10 | When fade finishes, `0x3E0B10(2)` and app ID **6** (`CAppDemoMain`) |

The editor records native call events; it does not execute the game factories.
Follow-up investigation of app ID 42 remains **out of M1 scope**.

## Resource recovery, binding and draw order

`0x3EF6C0` registers three exact ELF string keys through `0x2FB850`.
`0x3F7320` resolves handles through `0x2FB960` and attaches original
textures through `0x2FD8F0`.

| Wrapper handle | Sprite | Key pointer | Exact archive key | Native use |
|---|---|---|---|---|
| `+0x10` | `this+0x40` | `0x4D7740` | `dis/d03/d03t0101` | Foreground logo and prompt atlas |
| `+0x14` | `this+0xA0` | `0x4D7760` | `dis/d03/d03t0103` | Landscape background |
| `+0x18` | `this+0x100` | `0x4D7780` | `dis/d05/d05t0101` | Copyright symbol |

Known `0x3F7AA0` draw order:

1. Background sprite `+0xA0`, source/destination `(0,0,512,448)`,
   initially tinted RGB **(0.6,0.6,0.6)**, alpha 1.
2. Foreground sprite `+0x40`, source `(0,0,257,306)`, destination
   `(128,28,257,306)`.
3. Conditional prompt, drawn from the **foreground atlas** by
   `0x3F7E10`. The two supplied captures match the native case-1
   layout, with three source rectangles `(0,357,99,30)`,
   `(204,357,74,30)`, `(99,357,105,30)`, placed at
   x=`116,217,293` and y=`344`. **All five** ELF dispatch layouts
   have now been recovered (see below); the controller-service state that
   selects each case is still unobserved.
4. Two copyright lines rendered using original FFON text, in shadow
   and white passes; two copyright-symbol sprites from third resource.

All rects are logical native coordinates, not screenshot-calibrated
coordinates. Exact GS source sampling, texture filtering and blending
remain unverified. Current Qt composition is therefore an **asset-backed
approximation**, not proven pixel parity.

## Copyright and original game font

Native original ELF pointer table at `0x4F9454` identifies the strings:

- `0x4C9820`: `1989 BIRD STUDIO/SHUEISHA, TOEI ANIMATION`
- `0x4C9850`: `2006 NAMCO BANDAI GAMES`

Using `0x2CDCA0`, the draw callback submits a dark pass RGB `0.25`
at `(88,383)` and `(88,400)`, followed by white RGB `1.0` at
`(86,381)`, `(86,398)`, with native float32 font scale
`0x3F2B851F` (~0.67), alpha from the native fade helper
`0x2C0C70`. The two copyright symbols use source rectangle
`(15,97,17,17)` at x=68, with native fade-dependent y
`383 - (1-alpha)` and `400 - (1-alpha)`.
No generalized interpolation or invented asset key is used.

The existing editor's exact `font/5-24-2.fon` **24×24, 4bpp**
loader and native half-cell FFON raster path are reused.
Unsupported/missing or ambiguous source fonts fail closed.
FFON source-cell placement and final PS2 GS alpha/UV still require
runtime image comparison.

## Prompt blink mechanism: independent global clock

The original native update `0x2CB710` drives a **shared UI clock**.
`0x2E4E10` accumulates its float32 phase and sets it to **0** if the
sum exceeds **3.0**; it does *not* use modulo arithmetic.
`0x2E5510` returns prompt-visible if and only if phase is **>1.0**.
`0x3F7AA0` checks this visibility gate before invoking
`0x3F7E10` to draw the atlas sprites.

At continuous permitted updates this is approximately **1 second hidden,
2 seconds visible**, with strict boundaries (phase 1 hidden, phase 3
visible), then reset on next crossing update. The original global phase
**when entering application ID 3** and the circumstances that suppress
the external scheduler remain unknown.

The embedded preview's `c_press_start_prompt_clock` uses deterministic
float32 steps, discards >3-second overshoot, supports a diagnostic
**Native UI clock updates** gate, and remains independent from
`c_press_start_runtime`'s idle/transition age. The default phase 0 is
a **deterministic diagnostic initial condition**, **not** an assertion
about actual in-game entry phase. Play/Pause, Step and Reset use the
existing editor UI. The manual Show PRESS START checkbox still switches
only **PCSX2 reference capture state**, not the rebuilt clock.

## All prompt dispatch layouts (M1 follow-up, 2026-11-18)

A direct disassembly of exact EU-beta `0x3F7E10` shows five selector
branches returned from `0x3F7D40` (controller service helpers
`0x2AFB70`, `0x2AFB80`, `0x2AFAD0`, `0x2AFC80`).
The cases are **not controller indices**. These source and destination
rectangles are recovered from original instruction immediates and
sprite-geometry return values, not hand positioned to match captures.

| Case | Native branch | Initial logical x | Atlas source rectangles (x,y,w,h) |
|---|---|---:|---|
| 0 | `0x3F7E60` | 154 | `(0,357,99,30)`, `(99,357,105,30)` |
| 1 | `0x3F7F2C` | 116 | `(0,357,99,30)`, `(204,357,74,30)`, `(99,357,105,30)` |
| 2 | `0x3F8068` | 88 | `(278,357,92,30)`, `(0,387,39,30)`, `(80,387,90,30)`, `(170,387,110,30)` |
| 3 | `0x3F8214` | 86 | `(278,357,92,30)`, `(39,387,41,30)`, `(80,387,90,30)`, `(170,387,110,30)` |
| 4 | `0x3F83C0` | 118 | `(278,357,92,30)`, `(80,387,90,30)`, `(170,387,110,30)` |

For every case, native y=`344`, height=`30`, and the next quad
begins at the previous quad's destination x + width + **2 pixels**.
Case destinations therefore have x sequences:
`(154,255)`, `(116,217,293)`, `(88,182,223,315)`,
`(86,180,223,315)`, and `(118,212,304)`.

`arika_press_start_prompt_layout.py` supplies pure case-specific quad
lists and a full-SHA-256 plus opcode-gated ELF oracle.
The reconstruction now supports each case via a clearly labelled
**manual diagnostic** selector in the existing Press Start tab. It
defaults to case 1 (the variant observed in the screenshots), resets
to case 1 on archive swaps and does **not** infer a case from the
existing gamepad eligibility controls. Native prompt blink timing
continues to come exclusively from the recovered global UI clock.
All five variants are regression-tested on both CI platforms.

**Outstanding observation:** record the original return from
`0x3F7D40` alongside the controller-service state and a GS prompt draw
to establish when each case appears naturally. Without that capture,
automatic selection or mapping case numbers to specific controller
configurations would be guessed behavior.

## Editor implementation and testing

- `arika_press_start_resources.py` and
  `arika_press_start_copyright.py` verify original keys, opcode
  callsites, text pointers, draw arguments and case-1 atlas selectors.
- `arika_press_start_rendering.py` loads the **exact three** resource
  keys from the already opened archive, either extensionless or `.pix`;
  accepts only a single unambiguous FPIX/XPIX/TIM2 or bare TIM2 texture;
  rejects missing, ambiguous, undersized and unsupported files instead
  of substituting guessed assets. It composites sprite layers, case-1
  prompt, original font runs and copyright symbols.
- `arika_press_start_preview.py` keeps all existing controller input,
  lifecycle, traces, play/pause, manual stepping, tab-switch pause,
  archive-change resets and two optional PCSX2 reference captures.
  Reconstruction, capture-only, and side-by-side modes never copy
  reference screenshot pixels into a native sprite layer.
- Every archive swap discards old PIX, font and screenshot content and
  resets native clocks to prevent stale or mismatched resources.

Run CI-equivalent tests with:

```sh
cd arika-py_on_rs
python -m unittest test_arika_press_start_runtime test_arika_press_start_resources test_arika_press_start_preview test_arika_press_start_rendering test_arika_press_start_animation test_arika_press_start_copyright test_arika_press_start_prompt_layout -v
```

On local original ELF builds set `SDBZ_EU_BETA_ELF` for additional
SHA-256/opcode/string-gated tests. Windows and Ubuntu GitHub Actions
execute the synthetic regression suites and compile all new modules.

## Unresolved evidence / completion blockers

M1 is **not yet complete**. The archived `GAME EU BETA.zip` and
`sdbz_eu_beta.7z` were discoverable in the owner's project files but
their raw contents were not authorized for access from this environment.
Consequently the three **actual game PIX payloads** and native FFON
could not be decoded/visually inspected here. The two user PCSX2
screenshots were inspected to correct the reference crop, but **no
reconstructed-image-to-original pixel parity has been measured**.

To complete M1, run the real archive through the integrated Qt tab,
validate each texture's XPIX/TIM2 structure and palette/alpha, verify
font glyphs and the case-1 prompt visually against *both* PCSX2
reference states, recover measured GS filtering/blending/fade behavior,
and document residual per-layer/pixel error. Exact native entry phase and the controller-service-state to
prompt-case mapping still lack runtime capture evidence. Passing synthetic CI is necessary but **not**
sufficient to claim original visual parity.

Keep PR #25 in **draft/unmerged** until the evidence criteria are met.
Do not expand the PR into app ID 42, unrelated screens, audio or a
general-purpose PS2 emulator.
