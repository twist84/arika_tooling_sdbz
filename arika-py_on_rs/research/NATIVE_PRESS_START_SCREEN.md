# Native EU-beta Press Start (application ID 3)

## Evidence and visual references

The target is the **Super Dragon Ball Z (Europe) beta** ELF, SLES_541.61, SHA-256 **80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0**. EU retail uses the same filename and must not be substituted.

The two user-provided PCSX2 screenshots show the same landscape/logo/copyright screen in two states: with and without the blue **PRESS START button** prompt. The captured PCSX2 window is 1920×1040; the measured gameplay picture in these particular captures is (307, 96, 1040, 778), displayed at 4:3. This crop is a screenshot-specific reference, not a GS viewport register. Neither image is committed.

## Separate application factories

The ELF returns the same CAppTitleMain class-name string for distinct registered applications:

| ID | Factory | Constructor | Phase vtable | Role |
|---:|---|---|---|---|
| 2 | 0x3F2D80 | 0x3F86E0 | 0x4F66F8 | Timed four-second title interval |
| **3** | **0x3F2D20** | **0x3F7150** | **0x4F6698** | **Interactive Press Start** |

The ID-3 phase vtable contains: init 0x3F71E0, loader 0x3F7320, begin 0x3F7680, **update 0x3F76A0**, release 0x3F79A0, draw 0x3F7AA0. App ID 3 is also the native parent requested on the ID-7 child completion path of Demo Main (ID 6). The editor navigation follows this verified ID, never a class-name-only match.

## Native loader

Native loader phases are 0 → 1 → 2 → 3 → 4 (field this+0x34).

- Phase 0 registers resource groups **2,3,4,5,7,8,10,11,15** through 0x2FBDC0.
- Phase 1 polls 0x2FBEB0, associates group 7 with the original sound key **snd/etceff** at 0x4D7F80, and registers group 8.
- Phase 2 polls 0x2FBE30(16).
- Phase 3 fetches render resource pointers through 0x3EF140 and creates three sprite objects at this+0x40, +0xA0, +0x100. Draw callback uses a **512×448** logical rectangle.
- Phase 4 begins the original transition and reports loader completion.

The exact asset-group-to-PIX and complete GS compositing have **not** been recovered. The editor does not replace them with a guessed asset key or pretend the earlier d03t0202 splash texture is the Press Start background.

## Native update: EE 0x3F76A0

The float32 elapsed clock is accumulated in this+0x2C each native update. A separate one-shot event at **at least 1.0 second** sets a latch at this+0x36 and invokes 0x2FC840. The input handler at 0x3F85A0 also executes, but its complete side effects remain out of scope.

Start uses **controller word offset +0x22, bit 0x10**, subject to the native 0x2AFAD0 eligibility helper. The alternative controller word is checked separately.

| Phase, this+0x34 | Native behavior |
|---:|---|
| 0 | When an eligible Start input is pressed, call 0x3EB040 plus UI/sound helpers, then enter phase 1. Otherwise call idle reset helper 0x2AFD30(0,2); if it returns true, reset the elapsed clock. If false and age is **at least 20.0 seconds**, start a fade and enter phase 10. Start takes precedence over the idle timeout on that tick. |
| 1 | Start transition: invoke 0x2C0C90 and two 0x2C08A0 calls, then enter phase 2. |
| 2 | When 0x2C0C20 is no longer busy, request native application **ID 42** through 0x3DFB00 and report completion. The class of app 42 is not assumed here. |
| 10 | When 0x2C0C20 is no longer busy, call 0x3E0B10(2) and request **ID 6, CAppDemoMain**. Report completion. |

All native calls in the editor are **trace events, not executed PS2 operations**.

The original blink timing and exact sprite/alpha output are not established from these two screenshots or the recovered update code. The UI therefore exposes a **manual prompt-visible toggle**, not a guessed native blinking animation.

## Arika Editor integration

Within the existing Arika Editor Menu workspace, **Press Start** is a new tab beside Main menu, Startup / Splash, Warning / Video Mode, Title Screen and Demo Main. No separate viewer is launched.

After opening the EU-beta INFO.DAT/GAME.DAT archive, choose **Menu → Press Start**:

- Start (controller 0) and Start (controller 1) use the verified input bit, with separate eligibility checkboxes.
- Transition busy and external idle reset are explicitly supplied native observations.
- Step one native update, Play/Pause and Reset preserve the native state machine. Autoplay uses measured QElapsedTimer deltas with a 16 ms **Qt scheduling target**, not a fabricated native frame duration.
- Load PCSX2 capture: no prompt / prompt lets you select **local screenshots** or cropped 4:3 images, then toggle between the exact two reference frames. The screenshots are never bundled, written into an archive, or represented as GS output.
- Inspect destination is enabled only on completion. For ID 6 it opens the existing Demo Main inspector; from Demo Main, Inspect returned parent can navigate back to the Press Start tab when the verified return ID is 3.

Without capture images, the panel displays a clearly labeled diagnostic placeholder. Switching archives clears stale capture references. Switching tabs pauses playback.

## Validation

Run locally:

    cd arika-py_on_rs
    python -m unittest test_arika_press_start_runtime test_arika_press_start_preview -v

When the exact user-owned EU beta ELF is available, set environment variable SDBZ_EU_BETA_ELF or run:

    python arika_press_start_runtime.py SLES_541.61

The optional original-ELF oracle checks SHA-256, the phase vtable, original instructions for Start bit 0x10, 1-second latch, 20-second idle timeout, render dimensions and transition IDs. CI runs synthetic tests without original game assets.

**Next:** recover group→texture mapping, exact native GS composition and prompt alpha/blink period, then compare rendered pixels against the two supplied PCSX2 captures.


## M1 rendering recovery — original sprites (2026-11-18)

This milestone is **in progress**, not pixel-complete. The exact original EU-beta
ELF was recovered from the owner's ELF archive and matched SHA-256
`80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0`.
The version/region is **not** inferred from the name `SLES_541.61`.

At `0x003EF6C0`, original strings and calls `0x2FB850` assign the resources
to handles in the original singleton returned by `0x3EF140`. At
`0x003F7320` (loader phase 3), `0x2FB960` resolves each handle and
`0x2FD8F0` attaches it to a sprite.

| Resource handle | App sprite | ELF key pointer | Verified key | Result |
|---|---|---|---|---|
| `+0x10` | `this+0x40` | `0x4D7740` | `dis/d03/d03t0101` | Foreground sprite, drawn second |
| `+0x14` | `this+0xA0` | `0x4D7760` | `dis/d03/d03t0103` | Full-frame sprite, drawn first |
| `+0x18` | `this+0x100` | `0x4D7780` | `dis/d05/d05t0101` | Dynamic sprite; destination not yet proven |

ELF addresses and instructions used by the optional oracle live in
`arika_press_start_resources.py`. It verifies all three original strings,
specific resource-handle stores, sprite setup and geometry instructions,
**after** checking the entire executable SHA-256.

### Geometry and draw order

1. At `0x3F7AEC` through `0x3F7B08`, the game submits `this+0xA0`
   first, covering source/destination `(0,0,512,448)` from the loader's
   `0x3F7548..0x3F7564` setup. Its initial colour channels are three
   `0x3F19999A` floats (0.6f RGB), with alpha 1.0f, set at
   `0x3F7504..0x3F7520`.
2. At `0x3F7B0C..0x3F7B54`, `this+0x40` is moved to `(128,28)`,
   scaled by 1.0 and submitted with sprite rectangle `(0,0,257,306)`.
3. `this+0x100` has its initial source subrectangle `(15,97,17,17)`
   at `0x3F75D8..0x3F75F0`. Its later draw placement is computed by
   `0x3F8510` calls in `0x3F7C90..`. No static placement is substituted.
4. Additional font/text and dynamic draw calls follow the two verified
   static sprites. The `0x2E4B30 → 0x2E5510` gate at `0x3F7B58`
   conditionally invokes `0x3F7E10`. Its exact relation to the prompt,
   blink period, alpha evolution, and resulting GS state are **unverified**.

The 512×448 game logical coordinates are stretched to an **independent
4:3 presentation** in the editor; 512/448 itself is not the display ratio.
The existing 1920×1040 capture crop remains `(307,96,1040,778)`, which
is a PCSX2-window measurement, **not** a native GS viewport register.

### M1 editor implementation (partial visual reconstruction)

- `arika_press_start_rendering.py` decodes only the three literal ELF keys
  from the open editor archive, supporting a single unambiguous
  FPIX/XPIX/TIM2 or directly supplied TIM2. Exact extensionless and
  `.pix` matches work; duplicate/missing/unsupported keys fail closed.
  No different PIX file, guessed FPIX chunk or replacement artwork is used.
- The existing **Menu → Press Start** tab renders the known first two sprite
  layers from those decoded pixels on a 512×448 QImage. The 0.6f
  background RGB is approximated via painter opacity against black.
  **This is not verified PS2 GS alpha, filtering or texture sampling.**
- Reference controls permit reconstructed output, original capture only,
  and native/capture side-by-side comparison, without mixing reference
  screenshot pixels into a game sprite.
- Archive swaps discard stale decoded images and captures, stop playback,
  and reset the native state, preserving manual step and Start controls.
- The dynamic third sprite, copyright and prompt text are intentionally
  absent from generated output until native draw/font bindings are proven.
  The prompt checkbox remains a manual **reference-frame switch**, not
  fabricated animation. No blink timing is claimed.

### Verification and remaining blockers

Run synthetic offscreen tests (Windows and Ubuntu CI):

```shell
cd arika-py_on_rs
python -m unittest test_arika_press_start_resources test_arika_press_start_rendering test_arika_press_start_runtime test_arika_press_start_preview -v
```

With the *exact* ELF supplied locally, set `SDBZ_EU_BETA_ELF` to run
additional ELF-gated tests. The original game archive and two reference
screenshots must be loaded locally; **none are committed**.

As of this milestone checkpoint, the original `GAME EU BETA.zip` and
`sdbz_eu_beta.7z` archives are discoverable in the owner's project files
but the available file service refuses raw-byte materialisation. Their
contents could not be inspected to validate all three actual PIX
container layouts, source alpha or visual parity. The two original
PCSX2 captures are available for comparison, but comparing two screenshots
to each other **does not establish reconstruction parity**.

**Completion gates still open:** successfully decode all three original
textures from the EU-beta game archive; recover and render original
copyright and prompt font calls; trace dynamic sprite positions and
visibility timing; recover GS blend/filter/UV state; measure pixel
differences against both captures; pass final Windows/Ubuntu CI. Until
those are done, the PR must remain unmerged or explicitly marked
incomplete. App ID 42 remains out of scope.
