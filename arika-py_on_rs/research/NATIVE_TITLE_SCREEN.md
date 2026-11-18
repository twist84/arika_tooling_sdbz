# EU-beta CAppTitleMain — native title screen inside Arika Editor

**Executable:** Super Dragon Ball Z EU-beta `SLES_541.61`, 4,180,784 bytes,
SHA-256 `80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0`.
This binary was independently hash-checked and disassembled locally.
No game executable, proprietary image or font is committed.

## Integrated editor workflow

The existing `arika-py_on_rs/arika_editor.py` **Menu** workspace now
contains four tabs: **Main menu**, **Startup / Splash**,
**Warning / Video Mode**, and **Title Screen**.

Run `launch_editor.bat`, open the EU-beta `INFO.DAT`/`GAME.DAT`
archive via **File → Open archive…**, select the **Menu** workspace
and **Title Screen**. The tab uses the editor's in-memory
`m_virtual_files` archive. No second import or standalone app
is required.

**Play/Pause** schedules native logical updates with measured
`QElapsedTimer` seconds. **Step one update** uses the explicit
`Manual delta` control. **Reset** restarts this application. Pausing
preserves age and phase. Switching tabs, replacing archives, finishing
or closing the widget stops playback. The **External transition busy
(0x2C0C20)** checkbox controls the captured/native readiness input;
no actual PS2 fading/audio emulation is implied.

The original texture is decoded only from the exact
`dis/d03/d03t0202` key (or normal `.pix` archive suffix). In the
same EU-beta game, that key is also the **third** `CAppLogoMain`
splash asset. The editor does not duplicate or embed proprietary
artwork. Missing, multi-chunk/ambiguous, unsupported or undersized
resources produce visible diagnostic status rather than invented art.

The preview's Qt raster uses a 512×448 canvas, displayed in a 4:3
container. It is **not** a PS2 GS framebuffer capture, accurate
texture filtering, or the original game's TV video-mode emulation.

## Recovered class and phase vtable

The name getter at `0x3F86C0` returns the original ELF class
string at `0x4D7F90`: `CAppTitleMain`.

Constructor `0x3F86E0` installs `this+0` base vtable `0x4F66D0`
and `this+4` phase vtable `0x4F66F8`.

| Callback | Virtual address |
| --- | --- |
| Construct | `0x3F86E0` |
| Initialize / allocate clock | `0x3F8740` |
| Load graphics resource | `0x3F8790` |
| Begin transition | `0x3F88D0` |
| Update | `0x3F8900` |
| Release wrapper | `0x3F89F0` |
| Release clock | `0x3F8A50` |
| Draw sprite | `0x3F8A90` |

The exact phase-vtable pointers are verified by the optional
`verify_title_elf` oracle in `arika_title_runtime.py`.

## Title resource and sprite

The loader at `0x3F8790` has native stages **0, 1 and 10**:

- Stage 0 allocates a 12-byte wrapper at `this+0x38`, calls
  `0x2FB9B0` and requests `dis/d03/d03t0202`
  (ELF string at `0x4D7FB0`) through `0x2FB850`.
- Stage 1 calls `0x2FB8C0` to check readiness. Once ready,
  it initializes a sprite at `this+0x40`, unwraps and binds
  the resource through `0x2FB960 → 0x2FD8F0`, and sets both
  source and destination rectangles to **(0, 0, 512, 448)**.
- Stage 10 reports ready.

At draw callback `0x3F8A90`, the sprite's vtable `+0x10`
function is dispatched. Native rendering state (GS `TEX0`,
`TEX1`, `ALPHA`, `TEST`, `ZBUF` and output pixels) is
not captured.

The modeled loader `c_title_runtime.load_step(resource_ready)`
accepts the external readiness input explicitly. The Qt image decoder
does not claim to replay those allocations or game asynchronous IO.

## Exact update lifecycle at 0x3F8900

- `this+0x28`: pointer to clock object; `clock+4` provides
  the native float32 update delta.
- `this+0x2C`: float32 elapsed age, **accumulated on every update**.
- `this+0x30`: native update phase.
- `this+0x34`: loader state, separate from update phase.

| Native phase | Observed behavior |
| ---: | --- |
| **0** | Poll `0x2C0C20`; if zero, set phase 1, **return immediately**. No phase 1 work on the same tick. |
| **1** | If `elapsed <= 4.0f`, return. On **strictly greater than 4.0f**, call `0x2C0C90(0)` and `0x2C08A0(2,15,-1,-1)`; set phase 2. |
| **2** | Poll `0x2C0C20`; when zero, call `0x3DFB00(this,6)` and return completion 1. |

The `0x3F88D0` begin callback invokes
`0x2C08A0(1,15,-1,-1)` and returns 1.

App **ID 6** is the actual call argument at `0x3F89CC`;
it has **not** been identified as a particular next class.
No unsupported interactive Start-button behavior has been invented.
This application is a timed title/logo interval; it is distinct
from the interactive main-menu program.

## Tests

```sh
cd arika-py_on_rs
python -m unittest test_arika_title_runtime test_arika_title_preview -v
```

The optional hash/ELF oracle runs when the user supplies
`SDBZ_EU_BETA_ELF`, or directly via:

```sh
python arika_title_runtime.py SLES_541.61
```

All other tests run against synthetic images or the recovered
control model in Ubuntu and Windows CI. The original game binary
is not shipped with the repository.

**Next milestone:** identify the actual app ID-6 target from the
native app table and trace the handoff between
`CAppTitleMain` and the interactive menu. This requires verifying
the original startup application manager rather than assigning
screen names from the order of ELF strings.
