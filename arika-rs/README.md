# arika-rs

Rust rewrite of the **Super Dragon Ball Z** (SLES-541.61 / Arika) INFO.DAT / GAME.DAT toolkit.

## Crates

| Crate          | Purpose |
|----------------|---------|
| `arika_core`   | Formats + glTF export with embedded PNG textures |
| `arika_cli`    | `arika` CLI |
| `arika_editor` | Bevy viewport + egui; **load FMDL/PIX into the 3D scene** |

## Build

```bash
cargo build -p arika_core -p arika_cli
cargo build -p arika_editor   # needs GPU deps / larger download
```

## CLI

```bash
arika list|extract|info|rebuild …
arika model-json|model-obj|model-gltf path.mdl out […]
arika motion-json|stg-json|hit-json|hit-obj|texture-ppm|face-json …
```

`model-gltf` now embeds TIM2/XPIX textures as PNG data-URIs and wires `baseColorTexture` on materials.

## Editor

```bash
cargo run -p arika_editor
```

1. Enter FMDL (+ optional PIX) → **Load model**  
2. Or enter STG (+ MDL/PIX) → **Load stage** (places kind-2 mesh instances)  
3. Select in outliner → edit T/R/S in Properties → **Apply transform**  
4. Axis helpers draw on the selection; camera frames bounds  
5. MMB orbit · Shift+MMB pan · +/- zoom · Home reset  

`arika stage-gltf s01a.stg out.gltf` exports MDL geometry with instance list in extras.


## Seedless rebuild with original US archive capacities

For the original US SLUS_214.42 archive (1,930 entries), the observed container
sizes are 98,304 bytes for INFO.DAT and 732,073,984 bytes for GAME.DAT.
The indexed GAME.DAT extent is 695,373,824 bytes. The trailing GAME.DAT
reserve is 35 MiB of zeroes; the unused encoded INFO.DAT tail is filled
with byte `0x40`.

To preserve the original total sizes when rebuilding from extracted assets:

```bash
arika rebuild --assets extracted --version usa \
  --out-info rebuilt/INFO.DAT --out-game rebuilt/GAME.DAT \
  --info-size 98304 --game-size 732073984
```

These limits are optional and apply only to **seedless** builds. With no
explicit sizes, the files are minimal as before. Values below the required
indexed extent are rejected. The original full-size files still need
game-side validation; matching lengths does not guarantee byte-identical
record layout or runtime compatibility. The GUI/frontend is maintained in
`arika-py_on_rs`; the standalone Rust editor is legacy.

## Implemented

- INFO/GAME archive (extract + rebuild)
- FMDL geometry, hierarchy, skinning, materials
- FPIX/TIM2 decode + **PNG encode**
- **glTF with embedded textures**, skins, animations
- RFSM/MOT2, STG, HIT, facial ANI
- **Bevy FMDL loader** (meshes + textures + outliner)

## Still open

- Full facial morph/texture endpoints in glTF animations
- Menu reconstruction, audio
- Interactive drag gizmos / undo stack (panel Apply transform is available)
- Hierarchical STG parent transforms (kind-2 instances are placed)


Docs from the original research: `docs/`.

## Validation

```bash
cargo test -p arika_core --test validate_assets
```

Uses real EU-beta `INFO.decoded.bin` (1934 entries) + `files.json`, plus synthetic TIM2/XPIX/HIT/STG/MOT2 fixtures.

Verified:
- Full INFO encode↔decode byte-identical roundtrip (98,304 bytes)
- All 1934 entry names/sectors/sizes match `files.json`
- Used region 693,350,400 bytes (matches archive research)
- CLI `arika info` / `list` on re-encoded INFO.DAT

FMDL/PMT/real STG payloads need a GAME.DAT extract (not shipped in the tools package).
