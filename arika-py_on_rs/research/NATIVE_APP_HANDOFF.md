# EU-beta title handoff → CAppDemoMain

**Original executable:** `SLES_541.61` EU beta, SHA-256
`80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0`.
Do not infer the executable region from the filename; EU retail
also uses `SLES_541.61`.

## Result: the native destination is DemoMain, not DemoMovie

The original application factory installs handlers beginning with
**application ID 1** — the table is indexed by application ID, not
by a zero-based enumeration of adjacent class strings.

| Actual app ID | Factory | Constructor | Class getter | Native class |
| ---: | --- | --- | --- | --- |
| 2 | `0x3F2D80` | `0x3F86E0` | `0x3F86C0` | `CAppTitleMain` |
| 4 | `0x3F2CC0` | `0x41E620` | `0x41EC80` | `CAppLogoMain` |
| 5 | `0x3F2C60` | `0x41ECA0` | `0x41F580` | `CAppWarning` |
| **6** | **`0x3F2C00`** | **`0x3E03E0`** | **`0x3E0D10`** | **`CAppDemoMain`** |
| 7 | `0x3F2BA0` | `0x3E1BD0` | `0x3E2080` | `CAppDemoMovie` |
| **8** | **`0x3F2B40`** | **`0x3E2160`** | **`0x3E26B0`** | **`CAppDemoMain` (distinct implementation)** |
| **9** | **`0x3F2AE0`** | **`0x3E0DF0`** | **`0x3E1AE0`** | **`CAppDemoPlay`** |

The factory initialization in `0x3F1580` writes pointers to the
native BSS table at `0x6217E0 + 4 × application_id` and registers
each ID with `0x3DFA60`. Application lookup at `0x3F1C40`
checks the ID range and calls the registered factory. The name
getters and class strings are independently verified by the
optional exact-ELF oracle in `arika_app_registry.py`.

**Distinction:** ID 9 *is* the separately registered
`CAppDemoPlay`, while `CCardDemo` is a helper class.
**IDs 6 and 8 both have native class name `CAppDemoMain` but
different factory addresses, constructors, vtables and name-string
pointers.** Do not combine their C++ class identities or assume ID 8
runs the same logic as the ID-6 `0x3E0830` callback.

## Source title callback and transition

The already implemented `CAppTitleMain` callback `0x3F8900`
ends by calling `0x3DFB00(this, 6)` after its native
four-second gate and external fade helper readiness. The
immediate at `0x3F89CC` is literally `6`.

Thus, the **verified requested transition** is

```text
CAppTitleMain — application ID 2
  update 0x3F8900
    -> call 0x3DFB00(this, 6)
       -> application lookup 0x3F1C40
       -> factory 0x3F2C00
       -> CAppDemoMain constructor 0x3E03E0
```

This documents the factory and its requested destination; it
does **not** assert that a Qt diagnostic actually constructs
the game runtime or that a particular movie plays next.

## DemoMain bootstrap and child request sites

The original `CAppDemoMain` initialization callback is
`0x3E0440`; its resource-loader callback at `0x3E04A0`
takes native sub-states using `this+0x29` and `this+0x30`.
The supported initial route (sub-state 0 or 1, internal
stage 0→1) is:

1. Call `0x2FCBA0` to prepare loading; register native group
   IDs **2, 3, 4, 5, 7, 8, 10, 11, 15** through `0x2FBDC0`;
   advance stage 0→1.
2. Call the external helper `0x2FBEB0`; while it returns
   false, remain waiting. On readiness, reset stage to 0
   and return completion true.

Other `this+0x29` sub-states 2/3 and later
`this+0x34` loader branches are **not** modeled. The
inspector never equates “archive contains a file” with
the actual native readiness result.

The `CAppDemoMain` update callback at `0x3E0830`
has several independent child paths. It can request
these IDs through **`0x3DFBD0`**:

| Branch site | Child ID | Identity established here |
| --- | ---: | --- |
| `0x3E08B4` | 4 | `CAppLogoMain` |
| `0x3E08CC` | 7 | `CAppDemoMovie` |
| `0x3E08E4` | 8 | `CAppDemoMain` (alternate factory `0x3F2B40`) |
| `0x3E08F4` | 9 | `CAppDemoPlay` (factory `0x3F2AE0`) |

The exact selection predicate has now been recovered:
`this+0x29` holds the **next choice** (0..3), copied to
`this+0x28` at dispatch. After requesting a child, the next
choice increments modulo four. The child-completion and parent
transition rules are in
[NATIVE_DEMO_MAIN_UPDATE.md](NATIVE_DEMO_MAIN_UPDATE.md).
The current Qt simulation still does not execute any native app,
media decoder or GS draw.

## Existing editor integration

There are now **five views** inside `arika-py_on_rs` → **Menu**:
Main menu, Startup / Splash, Warning / Video Mode, Title Screen,
and **Demo Main**.

1. Launch `launch_editor.bat` and open the EU-beta
   `INFO.DAT`/`GAME.DAT` archive, as before.
2. Select the Menu workspace and its **Title Screen** tab.
   **Play** or manually advance until the title runtime
   finishes; the original transition is surfaced as
   **“CAppDemoMain (ID 6)”**.
3. Click **Inspect destination (ID 6)**. The editor switches
   to its **Demo Main** tab. This is a *diagnostic tab
   switch*, not execution of an application factory.
4. Use **Step native loader** to inspect the recorded group
   registrations. The **External group loader ready**
   checkbox explicitly controls the native readiness result.
5. Use **Inspect native child branch** to view four candidate
   child IDs and their addresses without triggering movie
   playback. The additional **Step native update** controls
   trace the recovered EE 0x3E0830 dispatch, including explicit
   child-pending and global-exit observations.

Changing the loaded archive resets any earlier title
handoff/loader inspector. No additional game assets are bundled.
The main-menu, warning and splash views remain independent.

## Verification

```sh
cd arika-py_on_rs
python -m unittest test_arika_app_registry test_arika_demo_main_preview -v
```

For a locally owned verified EU-beta executable:

```sh
python arika_app_registry.py SLES_541.61
```

Set `SDBZ_EU_BETA_ELF` for the opt-in regression oracle.
The oracle checks original code words at factory registration,
lookup, class getter/vtable and child request sites; synthetic
unit tests and Qt GUI tests run in both Ubuntu and Windows CI.

**Next:** recover the full original ID-6 `CAppDemoMain`
loader sub-states, distinguish alternate ID-8 demo behaviour,
and correlate an actual runtime capture before reconstructing
native movie graphics or audio.
