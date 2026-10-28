# Stage-loading chunk performance patch

This is a **surgical patch** for the current Arika tool tree. It deliberately does not replace `arika_models.py` with a full older copy, preserving newer local changes.

## Apply

1. Extract `arika_stage_chunk_performance.patch` into `C:\Dev\ps2-web-recomp\games\arika_dat_tools`.
2. Open a terminal in that directory and run:

   ```powershell
   git apply --check arika_stage_chunk_performance.patch
   git apply arika_stage_chunk_performance.patch
   ```

   If this folder is not a Git working tree, `git apply` still applies ordinary unified patches; alternatively use `patch -p1 < arika_stage_chunk_performance.patch` if GNU patch is installed.
3. Run tests:

   ```powershell
   python -m unittest test_arika_dat test_arika_models
   ```

## What it changes

The stage preview's texture path used to split every FPIX chunk into a temporary directory, write each TIM2 image as a PNG, then read that PNG back into the glTF JSON. It now reads the FPIX archive once, visits only `XPIX` chunks containing `TIM2`, converts them to PNG bytes in memory, and embeds them directly. Existing texture ordering is preserved by iterating the original chunk table in order.

The patch adds `tim2_png_bytes()` while retaining the existing `tim2_png(path, output)` API, and adds a regression test that fails if stage export attempts to call `split_container()`.

This removes unnecessary temporary-file I/O. Model parsing, TIM2 decoding, PNG compression, and base64 embedding still happen synchronously, so this is a targeted improvement rather than a claim that all stage loading is instant.
