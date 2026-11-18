# Original EU-beta boot logos: resource names, loading and sprite setup

Target: verified **EU beta** `SLES_541.61`, 4,180,784 bytes, SHA-256
`80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0`.

This work builds upon [NATIVE_LOGO_STARTUP.md](NATIVE_LOGO_STARTUP.md)
and deliberately avoids main-menu rendering. All addresses are original
EE virtual addresses. Do not substitute the similarly named retail EU ELF.

## Three exact resources, in native display order

At `0x41E754..0x41E77C`, `CAppLogoMain::load` retrieves three
**32-bit address values**, encoded through `lwc1` and stores them
into stack slots. The pointer words are at `0x4B4770..0x4B4778`.
The loader uses the current `this+0xA8` index to select the
corresponding name and 12-byte resource wrapper.

| Logo index | Pointer table | String address | Native resource key | Wrapper pointer field |
| ---: | --- | --- | --- | --- |
| 0 | `0x4B4770` | `0x4D91A0` | `dis/d03/d03t0205` | `this+0x2C` |
| 1 | `0x4B4774` | `0x4D91C0` | `dis/d03/d03t0203` | `this+0x30` |
| 2 | `0x4B4778` | `0x4D91E0` | `dis/d03/d03t0202` | `this+0x34` |

These are **actual embedded resource keys**, not guesses from artwork.
They do not include file extensions in the ELF. Do not use the
similarly named `dis/main_menu` resource.

## Native resource lifecycle

- `0x41E7B4` obtains the active wrapper pointer from
  `this+0x2C+4*loader_index`. When present, `0x41E7C0`
  calls `0x2FB8C0` to test whether it is ready. Only then is
  `+0xA8` incremented.
- If no wrapper exists, `0x41E7F0` calls allocator `0x1110C0`
  **with length 12**. It initializes the wrapper via `0x2FB9B0`
  and invokes `0x2FB850 → 0x2FB560` with the selected string.
  `0x1110C0` is an allocator, not a resource ID 12.
- `0x41E7E0..0x41E7E8` returns ready only after
  **all three** indexed wrappers have finished loading.
- The release callback `0x41EB00` iterates the three wrappers,
  uses `0x2FB860` to clear them, and releases the application clock.
- `0x2FB960` unwraps a ready resource through wrapper `+0x08`,
  then record `+0x34` and its first pointer. An unready wrapper
  returns zero. That result is **not a proven PIX index**.

The display-phase logo index `this+0xA1` is distinct from the loader
index `this+0xA8`. Do not mix them.

## One native sprite instance, re-bound for each draw

The class initializes exactly one embedded generic sprite at
`this+0x40` in `0x41E680`.

| Native call | Implementation | Recovered sprite fields |
| --- | --- | --- |
| `0x41E6E8` | `0x2FD910` | `sprite+0x4D = 1` |
| vtable `+0x14` at `0x41E708` | `0x2FD970` | source bounds `(0, 0, 512, 447)`, stored at `+0x28..+0x2E` |
| vtable `+0x20` at `0x41E728` | `0x2FD920` | destination bounds `(0, 0, 512, 448)`, stored at `+0x4E..+0x54` |

At draw callback `0x41EB90`:
1. Read active index `this+0xA1` and pick the corresponding wrapper.
2. Call `0x2FB960` and pass the returned resource pointer to
   `0x2FD8F0`, with four **initial** sampler bytes `(0,1,0,0)`.
3. Dispatch the sprite's vtable `+0x10` draw function `0x2FD8A0`.

This confirms which **logical resource** is attached to the sprite
and which texture/screen rectangles were initialized. The actual
runtime resource object, intermediate opcode-1 commands, GS
`TEX0/TEX1/CLAMP/ALPHA/TEST/ZBUF` and framebuffer output require
captured execution. Initial selector 1 is consistent with an
initial linear preference, **not** evidence of final per-draw GS state.

## Integrated Arika Editor startup/splash view

The existing `arika_editor.py` **Menu** workspace now has two independent
tabs: **Main menu** and **Startup / Splash**. To use it:

1. Start `launch_editor.bat` as usual.
2. Use **File → Open archive…** and select your EU-beta
   `INFO.DAT` / `GAME.DAT` pair.
3. Select **Menu** in the workspace bar (or **Menu Editor** in the view
   dropdown), then **Startup / Splash**.
4. Use **Step one native update**, **Observed delta**, **busy** and
   the controller input toggle to inspect the recovered lifecycle.
   Reset restarts the logo state without reloading the archive.

The logo viewer consumes the **same** `m_virtual_files` mapping as the
existing main-menu preview. No additional file dialogs, writes to disk,
proprietary assets in Git, or separate process are needed. Archive
replacement clears the prior logo images, missing keys and ambiguous
resource matches are reported, and the Qt canvas fits the editor tab
while preserving the diagnostic 4:3 presentation.

The original loader names extensionless resource keys. The integrated
archive matcher accepts those keys and their standard `.pix` archive
suffix, normalized for slashes/case; it never searches by basename or
silently chooses an atlas. This is still a **logo application**
diagnostic, separate from the already recovered main-menu state machine.

The standalone `arika_logo_preview.py` CLI remains available if
needed. Supply extracted assets whose names match the native keys:

```text
extracted/dis/d03/d03t0205
extracted/dis/d03/d03t0203
extracted/dis/d03/d03t0202
```

```sh
cd arika-py_on_rs
python arika_logo_preview.py --assets-root extracted --elf SLES_541.61
```

Alternatively use the user's original archive pair:

```sh
python arika_logo_preview.py --info INFO.DAT --game GAME.DAT --elf SLES_541.61
```

The standalone tool extracts those exact keys with the existing archive
backend, if supplied. Both preview modes support only a single unambiguous
FPIX/XPIX/TIM2 image (or standalone TIM2); multiple texture entries
are **reported as unresolved**, not silently mapped to entry zero.
Missing or unsupported resources show an explicit message.

The display uses the proven native rectangles in a 512×448 logical
canvas presented as 4:3. A **manual logical-step** control accepts
`delta_seconds`, the external `0x2C0C20` busy result, and bit
`0x10` controller input for one update. No authored global frame
clock, synthetic fade timings, system-font substitute, or guessed
sprite selection schedule is introduced.

**Known visual limitations:** Qt uses its own sampling and blending;
the comparison display stretches 512×448 to 4:3, and the real game
may apply further GS state and presentation processing. The result
is a resource/placement diagnostic, not a PCSX2 pixel-perfect match.

## Reproducibility

```sh
python arika_logo_resources.py SLES_541.61 --assets-root extracted
python -m unittest test_arika_logo_runtime test_arika_logo_resources test_arika_logo_preview -v
```

The exact-ELF tests opt into the private binary through
`SDBZ_EU_BETA_ELF`. CI uses only generated synthetic TIM2/FPIX
images and verifies the Qt output offscreen; no proprietary data
or screenshots are committed.

## Further scope

Next examine `CAppWarning` and `CAppTitleMain` launch
and handoff callsites, along with the boot-logo asset data and
observed native GS commands if original PCSX2 captures are available.
Do not infer application order solely from ELF string proximity.
