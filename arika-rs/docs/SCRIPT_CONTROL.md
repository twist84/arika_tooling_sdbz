# Script commands, facial groups, and native event bindings

`arika_scripts.py` decodes the SPT bundle directory and token payloads, retains the original byte representation, and can rebuild an unchanged bundle byte-for-byte. Example:

```sh
python arika_scripts.py json ../dat_research/assets/spt/fgt/win04.spt examples/win04.json
python arika_scripts.py registry ../upload/SLES_541.61 examples/script_commands.json
python arika_scripts.py import-json original.spt edited.json rebuilt.spt
```

Rebuilding preserves program sizes and entry points. It does not relocate bytecode if a token changes size, and it does not validate edited command semantics. The 77 supplied SPT files contain 200 programs and 41,886 tokens; all were parsed and rebuilt byte-for-byte. No script calls the confirmed face/form commands 68 or 69, so gameplay action timing is not encoded in these SPT files.

## Native facial slots

The player asset loader at `0x1E8B98` resolves three indexed program pointers from the character ANI resource and stores them at loader offsets `0x5C`, `0x60`, and `0x64`. The player binding function at `0x1EB150` copies these to `player+0x7E4`, `player+0x7F0`, and `player+0x7FC`. Native voice event handlers pair them with voice handles as follows:

| ANI group slot | Player facial handle | Voice handle | Native action slot selected |
| --- | --- | --- | --- |
| 0 | `player+0x7E4` | `player+0x7E0` | action slot 55 |
| 1 | `player+0x7F0` | `player+0x7EC` | action slots 232 or 233, based on player state |
| 2 | `player+0x7FC` | `player+0x7F8` | action slot 235 |

The handlers wait for voice readiness before starting the facial program. The wait is state-driven, not a fixed delay recovered from the asset. The wrapper at `0x1F5810` queries audio channel 15 and discards any apparent incoming context argument; it accepts channel states 0/1. Native script commands 68 and 69 call the face/form and character-face-program paths, but neither is used in the supplied SPT files. The form driver calls the form setter at `0x1E62B0`, which switches both face and hair mesh tables. This release indexes the actual character ANI groups and their program events, but does not assign those event programs to every gameplay action or infer elapsed-time delays.

The face starts are at `0x1ECBC0`, `0x1EC2C8`, and `0x1EC6B0`. For slot 1, the action slot is selected between 232 and 233 from the player's state. Slot 0 uses action slot 55; slot 2 uses 235. Those records then resolve through CHT; Goku logical motion 55 selects m01056m0 rather than a name inferred from 055. Each is started only after the channel-15 readiness gate passes. These are confirmed voice-event bindings; a complete map from ordinary gameplay actions to voice-event selection and per-character ANI indices is still needed.

Generate the catalog from extracted assets:

```sh
python arika_faces.py catalog ../dat_research/assets/ply face_catalog.json
```

It records program indices, event timestamps, expressions, behaviors, and counts for every character ANI group. Groups 0 through 2 are labeled by their verified native slots. Further groups remain indexed without an inferred role. `face_catalog.json` is the reference output for the supplied extracted assets.

For a coordinated body and face export when the ANI group/program is known, use `arika_faces.py animate` with `--motion`, `--motion-index`, and the corresponding `--group` and `--program`. `--face-start` places the program start after export time zero. `timeline-animate` schedules several program starts while preserving the controller's random and phase state; see FACIAL_EVENT_TIMELINES.md. Form switching is supported as a static export option (`--super-form`), while an exact gameplay form-switch timeline remains to be recovered from the native gameplay handlers.
