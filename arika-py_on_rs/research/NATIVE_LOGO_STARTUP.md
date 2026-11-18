# EU-beta startup logos: CAppLogoMain native lifecycle

Target: original EU-beta `SLES_541.61` (4,180,784 bytes), SHA-256
`80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0`.
The executable was locally hash-verified before disassembly. No binary bytes,
textures, fonts, or screen captures are committed.

## Distinct startup applications

ELF string getters and embedded class-name records reveal at least:

| Name | Evidence | Status |
| --- | --- | --- |
| `CAppLogoMain` | name literal `0x4D91F8`; getter `0x41EC80`; base/phase vtables `0x4F7250`/`0x4F7278` | logo lifecycle recovered below |
| `CAppWarning` | name literal `0x4D8518`; base/phase vtables `0x4F72B0`/`0x4F72D8` | separate next research target |
| `CAppTitleMain` | name literal `0x4D7F90` | separate next research target |

These identities are not evidence of the precise initial app order.
The three logo resource keys are now recovered independently in
[NATIVE_LOGO_RESOURCE_RENDER.md](NATIVE_LOGO_RESOURCE_RENDER.md).
Do not infer boot sequencing from ELF string proximity.

## Logo application vtable and state fields

`0x41E620` constructs the `CAppLogoMain` application and stores the
`0x4F7250` base and `0x4F7278` phase vtables. The phase vtable
contains callbacks `0x41E680` (initialize), `0x41E750` (resource
setup/loading), `0x41E850` (begin), `0x41E890` (update),
`0x41EB00` (release), and `0x41EB90` (sprite render preparation).

| Object offset | Native evidence | Meaning in the isolated model |
| --- | --- | --- |
| `+0x28` | `0x41E8A0` / `0x41E8B0` | clock-object pointer; its `+4` float is added each update |
| `+0xA0` | `0x41E934` / `0x41EC38` | skip input latch |
| `+0xA1` | `0x41E904` | active logo index, copied from `+0xA2` |
| `+0xA2` | `0x41E92C..0x41E93C` | next logo index, wraps through 0,1,2 |
| `+0xA4` | `0x41E8A8` | logical update phase |
| `+0xA8` | `0x41E764..0x41E7E8` | resource loader index; not a display clock |
| `+0xAC` | `0x41E8A4..0x41E8BC` | accumulated float32 age |

All initial zeroes follow explicit stores at `0x41E620..0x41E67C`
or `0x41E680..0x41E748`, not assumed host defaults.

## State transitions at 0x41E890

| Phase | Branch/evidence | Result |
| --- | --- | --- |
| 0 | `0x41E900..0x41E950` | copy next logo into active; advance next mod 3; clear skip and age; phase 1, *falls into phase 1* |
| 1 | `0x41E954..0x41E970` | if `0x2C0C20` nonzero, hold; otherwise age=0, phase 2, *falls into phase 2* |
| 2 | `0x41E974..0x41E990` + `0x41EBF0` | hold until either input gate or `age >= 2.0`; then phase 3, **returns; phase 3 executes next update** |
| 3, logos 0/1 | `0x41E994..0x41E9E4` and `0x41EAC0` | if not skip-latched, invoke two helper calls; phase 4 |
| 3, logo 2 | `0x41E9C0` to `0x41EA78` | invoke final two helper calls; optional `0x3E0B00` if skip-latched; phase 10 |
| 4 | `0x41E9E8..0x41EA08` | hold while `0x2C0C20` nonzero; else age=0, phase 5, **returns; phase 5 executes next update** |
| 5 | `0x41EA0C..0x41EA50` | hold until float32 `age >= 0x3DAAAAAB` (approximately 1/12 second); invoke helpers and restart at phase 0 |
| 10 | `0x41EA54..0x41EA68` | return completion `v0=1` only when `0x2C0C20` returns zero |

The logo's two-second age is measured **after** phase 1's readiness
gate returns zero; phase 1 can take arbitrarily many ticks. The
native implementation falls from phase 0 into phase 1 and 2 within one update,
but **not** from 2 into 3 or from 4 into 5.
An authored 60 FPS transition schedule would be incorrect.

At `0x41EC50`, two input sources read halfwords at offset `+0x22`,
test bit `0x10` and OR the results. Their physical button identity
has not been independently captured. If active, `0x41EBF0` sets
`+0xA0` and returns ready immediately; otherwise it tests age against
exact `2.0f` (`0x41EC10..0x41EC20`). The 1/12-second value is
the raw float32 constant `0x3DAAAAAB` (`0x41EA10..0x41EA20`).

## Implementation

`arika_logo_runtime.py` implements deterministic `c_logo_runtime.step(`
`delta_seconds, audio_busy, controller0, controller1)` with an independent
`begin()`, `snapshot()`, and emitted external-call markers. The external
`audio_busy` boolean is exactly the observed return from `0x2C0C20`,
**not** an assertion that a sound is audible. No wall clock or
Qt timer exists in the model. Age updates round to float32.

Give its CLI a JSON array of observed/synthetic per-update inputs:

```json
[
  {"delta_seconds": 0.0, "audio_busy": false},
  {"delta_seconds": 2.0, "audio_busy": false},
  {"delta_seconds": 0.0, "audio_busy": false}
]
```

```sh
cd arika-py_on_rs
python arika_logo_runtime.py samples.json --elf path/to/EU-beta/SLES_541.61
python -m unittest test_arika_logo_runtime -v
```

Pass `--elf` to hash-check the original input and its key instruction
words. CI does not ship an ELF: without the optional
`SDBZ_EU_BETA_ELF` environment variable, the precise ELF test is skipped.
All other synthetic tests run in Windows/Linux CI.

## Not yet recovered

- The three logo resource **names**, asynchronous loader path and sprite
  rectangle are recovered. Runtime resource object identity, TIM2 chunk
  selection when ambiguous, and actual GS texture bindings are still unknown.
  See [NATIVE_LOGO_RESOURCE_RENDER.md](NATIVE_LOGO_RESOURCE_RENDER.md).
- The downstream app route after phase 10 returns completion.
- The meaning of native helper `0x3E0B00` and whether the two
  `0x2C0C90`/`0x2C08A0` calls directly correspond to audio or fades.
- Exact startup screen pixels, alpha/depth/GS state and native raster
  parity. The native sprite source/destination rectangles are now proven.
- `CAppWarning` initialization/update/draw and `CAppTitleMain` flow.

**Next:** capture runtime resource/GS state for pixel parity and trace
`CAppWarning` plus its handoff into `CAppTitleMain`. The separate
original-asset Qt preview is described in NATIVE_LOGO_RESOURCE_RENDER.md.
