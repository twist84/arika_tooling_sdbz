# Audio export

Requires Python 3; no external modules or programs.

```bash
python arika_dat.py extract INFO.DAT GAME.DAT extracted
python arika_audio.py extracted wavs
```

For one bank or music stream:

```bash
python arika_audio.py extracted/ply/p01/p01.ase wavs
python arika_audio.py extracted/sqm/menu_lp.ams wavs
```

ASE banks produce one mono WAV per sample, e.g. `wavs/ply/p01/p01.ase/000.wav`.
AMS files produce one stereo WAV, e.g. `wavs/sqm/menu_lp.ams.wav`.
Existing WAV destinations are overwritten. Inputs are read only.
The batch continues after a file fails, reports failures, writes `audio_manifest.json`,
and exits with failure status if any file failed. Large batches can take several minutes.

Both formats store Sony PS ADPCM (16 bytes to 28 signed samples). Export is
16-bit PCM, without normalization, resampling, fades, added loops, or game mixing.
Prediction uses FFmpeg-compatible truncation and unclamped history; hardware
SPU2 rounding, interpolation, pitch modulation, effects and game volume are not reproduced.
Sample rates use the stored SPU2 pitch: `pitch * 48000 // 4096`.
Fractional rates are truncated to integer Hz, as required by the WAV header.

## ASE version 100

Little-endian header, padded to 0x800 bytes:

| Offset | Meaning |
|---|---|
| 0x00 | Version: 100 |
| 0x04 | Sample count |
| 0x08 | Payload byte count |
| 0x0C | Repeated pairs: pitch, payload-relative byte offset |

Sample lengths come from the next offset, or payload size for the final sample.
Every sample in the supplied archive begins with flag 4 and ends with flag 3.
The exporter decodes each sample once, including its final frame. These flags
are preserved in the source; they do not cause infinite repetition in the WAV.

## AMS version 120

Little-endian header, padded to 0x800 bytes:

| Offset | Meaning |
|---|---|
| 0x00 | Version: 120 |
| 0x04 | Pitch |
| 0x08 | Valid ADPCM bytes per channel |
| 0x0C | Count of physical 0x20000-byte units |

Each unit contains two 0x10000-byte stereo blocks. Play even-indexed blocks in
ascending order, then odd-indexed blocks in descending order. Each block contains
0x8000 left-channel bytes followed by 0x8000 right-channel bytes. Preserve the
ADPCM predictor history per channel across all reordered blocks. Trim each
channel to its declared valid size before decoding.

AMS is streamed audio, not an action-control script. `_in` and `_lp` names
usually distinguish intro and loop segments; this tool exports them separately.
Gameplay-controlled repetition and transitions are not reconstructed.

## References and verification

AMS layout was independently described by almendaz (2020):
https://hcs64.com/mboard/forum.php?showthread=45469
https://hcs64.com/mboard/forum.php?showthread=45469&lastpage=

Decoder comparison reference:
https://github.com/FFmpeg/FFmpeg/blob/master/libavcodec/adpcm.c
https://github.com/vgmstream/vgmstream/blob/master/src/coding/psx_decoder.c

Run unit tests: `python -m unittest test_arika_audio -v`.
See `audio_validation.json` for the supplied-archive export and decoder comparison results.

# Rebuild audio from WAV

The companion `arika_audio_import.py` imports edited WAVs using the original
extracted assets as templates. It encodes Sony PS ADPCM, rebuilds ASE offsets,
and reorders AMS stereo blocks back into their physical storage order.

```bash
python arika_audio_import.py extracted wavs audio_replacements
python arika_dat.py repack INFO.DAT GAME.DAT rebuilt --replacements audio_replacements
```

Run repack only after import reports zero errors. Use a fresh replacement folder
for a new mod; unrelated files already in that folder are not removed.
The original archive and extracted assets are read only. Import writes complete
replacement assets using atomic per-file writes. Batch failures can leave other
successfully rebuilt assets in the output directory; inspect the summary and
`audio_import_manifest.json` before repacking.

You may supply just your edited WAVs in a separate folder, maintaining these paths:

- `wavs/ply/p01/p01.ase/000.wav`: replaces ASE sample slot 0.
- `wavs/sqm/menu_lp.ams.wav`: replaces the stereo AMS stream.

Files absent from that WAV folder retain their original compressed samples.
Unknown asset paths and unknown ASE sample numbers are rejected. The number
and order of ASE slots never change. Mono WAV is required for ASE and stereo
WAV for AMS; both must be uncompressed signed 16-bit PCM. Float/24-bit WAVs,
MP3 and other formats must be converted before importing. No automatic channel
conversion, normalization or resampling is performed.

By default, sample rate and exact frame count must match the original export.
This retains existing event durations and bank sizes. Do not trim exported
silence or append samples unless you deliberately enable duration changes:

```bash
python arika_audio_import.py extracted edited_wavs audio_replacements --allow-duration-change
```

With this option, rates are converted to the closest representable SPU2 pitch,
lengths are padded to complete 28-sample ADPCM frames, and tiny ASE clips are
padded to at least two frames for separate start/end markers. ASE bank offsets,
AMS valid sizes and padded block counts are recalculated. The archive repacker
updates sectors and sizes. Larger rebuilt archives must fit the original
GAME.DAT capacity; loading a larger ASE bank may also exceed an in-game sound
buffer whose capacity is not yet known. Game scripts, music sequencing,
loop transitions and facial timings are not updated. Keep original lengths
for initial in-game tests.

Encoding is lossy. Unchanged PCM, however, reuses the original ADPCM bytes;
unchanged WAV exports rebuild byte-identically, without another compression
pass. Changing only the WAV sample rate can reuse compressed data while
updating its pitch field. Unchanged AMS channel bytes are also reused when
only the other channel is edited. Original header bytes outside known fields
are preserved. Padding is retained for unchanged AMS files and zero-filled
when an AMS stream is rebuilt.

The encoder evaluates the five standard filters with quantizer feedback and
nearby scales for each frame. It uses the same predictor convention as the
exporter. This is a software encoder; it does not reproduce the original
encoder's exact decisions or the SPU2 mixer. Long music replacements can take
several minutes in pure Python.

Run tests:

```bash
python -m unittest test_arika_audio test_arika_audio_import -v
```

See `audio_import_validation.json` for full no-op reconstruction, edited-audio
FFmpeg decoder comparisons and archive replacement verification. In-game
playback of rebuilt audio has not yet been tested.
