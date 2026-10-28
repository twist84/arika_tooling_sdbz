# Python/Rust parity test workflow (Windows CMD)

Run these commands from the `arika-rs` directory. In Windows Command Prompt, use **double quotes** for the unittest pattern; single quotes are passed literally and can result in `Ran 0 tests`.

```bat
python -m unittest discover -s ..\arika-py -p "test_*.py" -v
cargo test -p arika_core
cargo test -p arika_core --test validate_assets
```

The Python suite imports the `arika-py` directory as top-level modules. Run from `arika-rs` or set `PYTHONPATH=..\arika-py` if invoking tests from another directory.

Most Python tests do not require a GPU. The pure WebGPU camera/color math tests should remain runnable without `wgpu` installed; constructing the actual renderer still requires the dependencies in `arika-py\requirements_scene_editor.txt`.

## Parity expectations

- Parse the same fixture in Python and Rust and compare normalized JSON structures.
- Compare round-trip output byte-for-byte where the format is lossless (notably INFO encoding/decoding).
- For archive repacks, compare entry names, offsets, lengths, sector alignment, retained archive capacity, and extracted payload bytes. Do not require byte identity for rebuilt archive metadata unless both implementations promise identical layout.
- Keep unsupported formats/features explicitly listed instead of treating a passing Rust-only test as proof of parity.
