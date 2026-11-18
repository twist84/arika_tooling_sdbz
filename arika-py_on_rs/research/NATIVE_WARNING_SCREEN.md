# EU-beta CAppWarning — native video-mode/warning screen

**Target:** Original Super Dragon Ball Z EU-beta \`SLES_541.61\` (4,180,784 bytes).
SHA-256: \`80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0\`.
The executable was independently hash-checked and disassembled for this work.
No game executable, graphics, or font data are committed.

## Editor integration

The existing **\`arika-py_on_rs/arika_editor.py\`** has a third tab under
**Menu → Warning / Video Mode**, beside **Main menu** and
**Startup / Splash**.

1. Run \`launch_editor.bat\`, then **File → Open archive…** with the EU-beta
   \`INFO.DAT\`/\`GAME.DAT\` pair.
2. Select the **Menu** workspace and the **Warning / Video Mode** tab.
3. Press **Play** or **Step one update** to advance the ELF-derived phase
   machine. **Pause** retains the selection and all counters; **Reset**
   returns to the initial state.
4. Use **Next option (bit 0x2)**, **Previous option (bit 0x1)** and
   **Confirm (bit 0x80)** to explore native choices.
5. The **External transition busy (0x2C0C20)** checkbox supplies the
   *observed* asynchronous helper result; unchecked simulates readiness.
   No native audio or GPU work is performed by that checkbox.

The tab uses the same in-memory archive as the main-menu and splash tabs,
so selecting another archive immediately stops playback, clears the prior
warning image, and resets state. It also pauses when hidden. It does not
open a second editor window.

The drawn option labels are a **diagnostic Qt representation**, not
the native FFON/GS font output. The original bitmap is displayed during
the \`TEST\` image phase when its resource can be unambiguously decoded.
Missing/ambiguous FPIX resources are reported rather than substituted.

## Actual ELF resource and drawing

At \`0x0041EDB0\`, \`CAppWarning::load\` creates a 12-byte wrapper at
\`this+0x40\` using \`0x1110C0\`/\`0x2FB9B0\`, and calls \`0x2FB850\`
with the **exact** resource string at \`0x004D9230\`:

\`\`\`text
dis/d03/d03t0801
\`\`\`

The wrapper is polled through \`0x2FB8C0\`. Once ready, the sprite at
\`this+0x50\` is initialized using \`0x2FD910\`, attached through
\`0x2FB960 → 0x2FD8F0\`, and configured with:

| Native setter | EE site | Recovered rectangle |
| --- | --- | --- |
| source, vtable \`+0x14\` | \`0x41EE78..0x41EE94\` | (0, 0, 512, 448) |
| destination, vtable \`+0x20\` | \`0x41EE98..0x41EEB4\` | (0, 0, 512, 448) |

The \`0x41F310\` draw callback skips output when phase is 10; when
\`this+0x38\` is nonzero and \`this+0x40\` is ready, it calls the
sprite's vtable \`+0x10\`. Otherwise it issues **four text draws**
via \`0x2CDCA0\`, using a choice table at \`0x4B4780\`.
The exact, space-preserving text strings are:

| Index | String pointer | Text | |
| ---: | --- | --- | --- |
| 0 | \`0x4D9248\` | \` 50Hz\` | Video-mode selection |
| 1 | \`0x4D9250\` | \` 60Hz\` | Video-mode selection |
| 2 | \`0x4D9258\` | \` TEST\` | Start a timed image test |
| 3 | \`0x4D9260\` | \`To Game\` | Request application exit |

The precise font glyphs/colors and PS2 GS filtering/blending/FB output
have **not** been reconstructed. These strings are not authored labels.

## Recovered update flow at EE 0x0041EF00

Native phase field is \`this+0x30\`, choice index \`this+0x34\`,
image flag \`this+0x38\`, resource-loader phase \`this+0x3C\`,
test countdown \`this+0x2C\`. The clock pointer lives at \`this+0x28\`
and its float \`+4\` is the native update delta, not a fixed 60 FPS value.

| Phase | Verified effect |
| ---: | --- |
| 0 | Clear selection and flags; phase 1, **falls through to phase 1** |
| 1 | Poll \`0x2C0C20\`; hold if busy, else phase 2 |
| 2 | Read controller \`+0x22\`: bit \`0x2\` = selection+1 mod 4, bit \`0x1\` = selection−1 mod 4, bit \`0x80\` = confirm. Priority \`0x2 → 0x1 → 0x80\` |
| 3 | Invoke \`0x2C0C90(0)\` and \`0x2C08A0(2, 60, −1, −1)\`; phase 4 |
| 4 | Poll \`0x2C0C20\`; if ready, call \`0x3DFB00(this, 1)\` and return completion |
| 10 | For options 0/1, call \`0x1BF560\` with 50.0/60.0 and \`0x1998A0\` with mode IDs \`0x36\`/\`0x35\`, selected dimensions 512×512/512×448; return to phase 2 |
| 20 | Begin TEST transition; phase 21 |
| 21 | Poll readiness; once clear, set image flag 1, invoke next transition, phase 22 |
| 22 | Poll readiness; once clear, set float32 countdown to **5.0**, phase 23 |
| 23 | Subtract native clock delta; only if **strictly negative**, clear countdown, begin transition and set phase 24 |
| 24 | Poll readiness; once clear, clear image flag and transition back to phase 1 |

Confirming options 0 or 1 takes phase 10; confirming option 2 takes
phase 20; confirming option 3 takes phase 3. No other numeric phases
are synthesized. The real calls to \`0x1BF560\`, \`0x1998A0\` and
\`0x3DFB00\` are **recorded as events**, not executed against the editor
or host operating system.

The label "50Hz" or "60Hz" does **not** make the preview change video
mode. It only reveals the native branch and its arguments. Likewise
"To Game" does not currently instantiate \`CAppTitleMain\`.

## Validation and use

\`arika_warning_runtime.py\` models the recovered state machine using
float32 arithmetic and explicit boolean readiness. A hash- and
instruction-gated report can be generated with a user-owned ELF:

\`\`\`sh
cd arika-py_on_rs
python arika_warning_runtime.py SLES_541.61
python -m unittest test_arika_warning_runtime test_arika_warning_preview -v
\`\`\`

To exercise the exact-ELF regression cases locally, set
\`SDBZ_EU_BETA_ELF\` to the EU-beta executable path. CI runs all
synthetic cases without committing that file.

The Qt tab uses a \`QTimer\` for presentation scheduling and a
\`QElapsedTimer\` to pass monotonic elapsed seconds to the state
machine. No 60 Hz *game* clock or invented fade timing is asserted.
During TEST, Qt decodes an unambiguous FPIX/XPIX/TIM2 or standalone
TIM2 asset with the existing texture decoder, using the proven
512×448 native source/destination rectangle.

**Next:** determine the game startup application order and handoff,
recover \`CAppTitleMain\`, and correlate the warning's native FFON
text draws and sprite GS packets with an actual runtime capture.
