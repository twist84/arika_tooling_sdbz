# Facial animation playback

Python 3.9+, standard library only. Run these commands from the tools directory, with the extracted assets under `extracted`. The supplied European beta SLES_541.61 is the reference build.

## Export animated faces

```sh
python arika_faces.py animate extracted/ply/p01/p01.ani facial.gltf --model extracted/ply/p01/p01a.mdl --group 0 --program 0 --duration 12 --seed 0
```

Combine the face with a skeletal motion in one animation clip:

```sh
python arika_faces.py animate extracted/ply/p01/p01.ani facial_body.gltf --model extracted/ply/p01/p01a.mdl --motion extracted/ply/p01/p01sel.pmt --motion-index 1 --loop-motion --duration 12 --seed 0
```

The sibling `.pix` supplies textures automatically; use `--textures path.pix` to override. The self-contained glTF embeds textures and buffers. `examples/goku_facial_playback.gltf` contains the second example, and `previews/facial_playback.gif` previews it.

Options:

| Option | Meaning |
| --- | --- |
| `--group N --program N` | Zero-based ANI group and program indices; default 0/0 |
| `--duration SECONDS` | Export length, greater than zero and at most 600 seconds |
| `--rate N` | Sampling rate: 25, 30, 50, 60, 100 or 120; default 60 |
| `--seed N` | Unsigned 64-bit random state; decimal or `0x` hexadecimal; default 1 |
| `--no-blink` | Disable automatic idle blinks |
| `--super-form` | Select the super branch and disable idle blinking as in the controller |
| `--left-hand A --right-hand A` | Choose hand variants where available |
| `--motion FILE --motion-index N` | Add a zero-based skeletal motion from an RFSM/MOT2 package |
| `--loop-motion` | Repeat the body motion across the facial clip; requires `--motion` |

Without an explicit duration, the export ends half a second after the last ANI event. Programs with very long holds require an explicit duration. Body and facial clips start together; this does not recover their original gameplay trigger relationship. Hands can follow the motion HandAni track using `--auto-hands`; see ACTION_CONTROL.md. Hair and form remain explicit export choices. External gameplay triggers are not reconstructed.

## Controller behavior

Playback includes timed expression changes, rise/hold/fall phases, randomized speech pulses, idle blinks, END reset, and texture endpoint changes. Events execute in file order, preserving the original nonmonotonic timestamps. Missing head pairs and texture endpoints use the original carry-forward fallback.

The port uses explicit float32 arithmetic and the original 64-bit linear congruential random generator. A seed reproduces the isolated controller. The full game shares random state with other systems, so matching a seed alone does not reproduce an arbitrary gameplay recording. The controller also consumes a random value during initialization for the first blink delay.

`--rate` sets the controller tick interval as well as the sample rate. Frame zero stores the pose after the first tick. A terminal sample is included. Float32 clock accumulation is preserved, including the occasional one-tick difference at an event boundary.

The glTF uses LINEAR morph-weight animation for facial deformation and STEP node-scale animation to switch geometry/material instances. Texture endpoints are selected with the original `int(blend + 0.5)` rule. This matters for eyelids: an AB pair can have identical geometry but different eye textures. No custom glTF extension or runtime plugin is required.

These baked playback files are for viewing and downstream animation work. They duplicate face instances for visibility switches, and are deliberately rejected by the model importer. For importing edits back into the game, export an unbaked model with `arika_models.py` and follow `IMPORT_AND_FACES.md`. Edit ANI events through `arika_faces.py json` / `import-json`.

## Inspect samples or use the Python controller

```sh
python arika_faces.py sample extracted/ply/p01/p01.ani facial_samples.json --duration 12 --seed 0
```

```python
from arika_face_player import c_face_player

player = c_face_player(records, seed=0, blink=True, super_form=False)
pose = player.tick(1 / 60)
print(pose['pair'], pose['blend'], pose['texture_endpoint'])
```

`records` is one parsed ANI program's record list. The JSON sampler also records event index, phase time, flags and random state for inspection.

## Evidence and checks

The original routines used as evidence are controller initialization at `0x1E6480`, program start at `0x1E60A0`, tick at `0x1E6550`, phase helper at `0x1E7680`, face selection at `0x1D5A50`, geometry fallback at `0x1D5730`, and random generator at `0x190450`.

The portable implementation matched state and output pose against a research interpreter executing those original ELF instructions:

- All 325 facial programs: 104,000 compared ticks at 60 Hz with seeds 0 and 1.
- All 325 programs: another 78,000 ticks at 50/120 Hz with seed 13.
- Long holds were advanced equally in both implementations to exercise late events. This is controller equivalence testing, not a complete gameplay replay or a PS2 hardware capture.
- Normal, super-form and 50 Hz glTF samples: zero Khronos validator errors or warnings.
- 38 unit tests pass across archive, model, import and facial tooling.

The reports are `face_reference_validation.json`, `face_rates_validation.json` and `facial_gltf_validation.json`. Reference ELF SHA-256: `80499dc1456e57ce939b150520069b413a6c9b18e529bb2cc8e608c48c031bd0`.
