# FFON font format notes — `5-24-2.fon`

These observations are validated against the supplied 340,192-byte file.

## File layout

All multi-byte integers are little-endian.

| Offset | Size | Type | Observed meaning |
|---:|---:|---|---|
| `0x00` | 4 | char[4] | Magic: `FFON` |
| `0x04` | 4 | u32 | Unknown: `0x00052360` |
| `0x08` | 4 | u32 | Version-like field: `1` |
| `0x0C` | 4 | u32 | Unknown: `0x100` |
| `0x10` | 4 | u32 | Character-map page count: `40` |
| `0x14` | 4 | u32 | Last column index: `95` (96 columns/page) |
| `0x18` | 4 | u32 | Glyph count: `0x482` = `1154` |
| `0x1C` | 1 | u8 | Glyph width: `24` |
| `0x1D` | 1 | u8 | Glyph height: `24` |
| `0x1E` | 1 | u8 | Bits per pixel: `4` |
| `0x1F` | 1 | u8 | Bytes per row: `12` |
| `0x20` | 4 | u32 | Unknown flags/value: `1` |
| `0x24` | `0x1C` | bytes | Zero-filled/reserved in this sample |
| `0x40` | `0x60` | u8[96] | Secondary byte remap table; semantics not yet identified |
| `0xA0` | `0x1E00` | u16[3840] | Main character-to-glyph map (`40 * 96`) |
| `0x1EA0` | `0x51240` | bytes | 1,154 fixed-size glyph bitmap records |

The main map ends at:

`0xA0 + (40 * 96 * 2) = 0x1EA0`

The glyph data size is:

`1154 * 24 * 24 / 2 = 332352 = 0x513C0`

Therefore:

`0x1EA0 + 0x51240 = 0x530E0` (the exact file size).

There is no trailing data after the bitmap records.

## Character map

The main map is an array of 3,840 little-endian `u16` values.

```text
slot = row * 96 + column
glyph_id = map[slot]
```

- `glyph_id == 0`: no glyph / unmapped cell.
- `glyph_id` values are 1-based and cover every value from `1` through `1154` exactly once.
- Bitmap record index is `glyph_id - 1`.

The layout is strongly consistent with a JIS X 0208-style row/cell grid:

- Row 0 is the single-byte ASCII row. Columns 0–94 map space through `~`; column 95 is unused.
- Rows 1–39 are double-byte character rows. Columns 1–94 contain the 94 cells; columns 0 and 95 are padding/reserved.
- The glyph sequence corroborates the row ordering: punctuation/symbol rows, full-width alphanumerics, hiragana, katakana, then kanji.
- For rows 1–39, the corresponding JIS-style bytes are `row_byte = 0x20 + row` and `cell_byte = 0x20 + column`.

This establishes the map's row/cell organisation. It does **not** by itself prove which external byte encoding the game's text stream uses; a Shift-JIS-to-JIS conversion may be required by the caller.

## Glyph bitmap records

Each record is exactly 288 bytes:

```text
24 pixels * 24 pixels * 4 bits / 8 = 288 bytes
```

The pixels are stored row-major, with a 12-byte row stride.

For pixel `(x, y)`:

```text
byte_offset = glyph_data_offset + record_index * 288 + y * 12 + x / 2

if (x & 1) == 0:
    pixel = data[byte_offset] & 0x0F
else:
    pixel = data[byte_offset] >> 4
```

The nibble is a 4-bit coverage/intensity value. The preview decoder expands it to 8-bit grayscale with `value * 17`.

The first bitmap record is the blank space glyph. This is why map value `1` points to record `0`; the map stores 1-based glyph IDs.

## Still unknown

- The meaning of header field `u32 @ 0x04` (`0x52360`). It is not the file size.
- The meaning of header field `u32 @ 0x0C` (`256`).
- The meaning of `u32 @ 0x20` (`1`).
- The exact input-code semantics of the 96-byte table at `0x40`. Its nonzero values are sparse and appear to refer to low glyph IDs, but the key encoding is not established.

## Decoder

`decode_ffon.py` reads the header, validates the exact calculated file size, and exports:

- `*_glyph_atlas.png` — labelled glyph contact sheet.
- `*_char_map.csv` — page/column, JIS-style row/cell, glyph ID, and bitmap-record index.
- `*_byte_map.csv` — raw 96-byte table at `0x40`.
