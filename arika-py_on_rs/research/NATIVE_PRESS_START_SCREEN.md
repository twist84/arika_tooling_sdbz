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
