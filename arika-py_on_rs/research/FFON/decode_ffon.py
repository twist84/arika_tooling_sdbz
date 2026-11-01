#!/usr/bin/env python3
"""Decode the observed FFON font container used by 5-24-2.fon.

Requires Pillow:
    python -m pip install Pillow

Example:
    python decode_ffon.py 5-24-2.fon
    python decode_ffon.py 5-24-2.fon --out-dir extracted
"""

from __future__ import annotations

import argparse
import csv
import math
import struct
from pathlib import Path

from PIL import Image, ImageDraw


HEADER_SIZE = 0x40
BYTE_MAP_OFFSET = 0x40
BYTE_MAP_SIZE = 0x60
CHAR_MAP_OFFSET = 0xA0


def read_u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def decode_glyph(data: bytes, offset: int, width: int, height: int,
                 row_stride: int) -> Image.Image:
    """Decode one row-major 4bpp glyph; even x uses the low nibble."""
    pixels = bytearray(width * height)

    for y in range(height):
        row_offset = offset + y * row_stride
        for x in range(width):
            packed = data[row_offset + (x // 2)]
            if (x & 1) == 0:
                value = packed & 0x0F
            else:
                value = packed >> 4

            pixels[y * width + x] = value * 17

    return Image.frombytes("L", (width, height), bytes(pixels))


def get_slot_code(row: int, column: int) -> tuple[str, str]:
    """Return a human-readable code for the observed row/column layout."""
    if row == 0:
        code = 0x20 + column
        return "ASCII", f"{code:02X}"

    if 1 <= column <= 94:
        jis_row = 0x20 + row
        jis_cell = 0x20 + column
        return "JIS-like", f"{jis_row:02X}{jis_cell:02X}"

    return "reserved", ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Decode an FFON font file.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--columns", type=int, default=32)
    parser.add_argument("--scale", type=int, default=2)
    args = parser.parse_args()

    data = args.input.read_bytes()
    if len(data) < HEADER_SIZE or data[:4] != b"FFON":
        raise ValueError("Not an FFON file.")

    unknown_04 = read_u32(data, 0x04)
    version = read_u32(data, 0x08)
    unknown_0c = read_u32(data, 0x0C)
    page_count = read_u32(data, 0x10)
    last_column = read_u32(data, 0x14)
    glyph_count = read_u32(data, 0x18)

    width = data[0x1C]
    height = data[0x1D]
    bits_per_pixel = data[0x1E]
    row_stride = data[0x1F]
    flags = read_u32(data, 0x20)

    if bits_per_pixel != 4:
        raise ValueError(f"Unsupported bpp: {bits_per_pixel}")

    expected_stride = (width * bits_per_pixel + 7) // 8
    if row_stride != expected_stride:
        raise ValueError(
            f"Unexpected row stride {row_stride}; expected {expected_stride}"
        )

    columns_per_page = last_column + 1
    char_map_count = page_count * columns_per_page
    char_map_size = char_map_count * 2
    glyph_data_offset = CHAR_MAP_OFFSET + char_map_size
    bytes_per_glyph = row_stride * height
    expected_size = glyph_data_offset + glyph_count * bytes_per_glyph

    if expected_size != len(data):
        raise ValueError(
            f"Size mismatch: expected 0x{expected_size:X}, "
            f"file is 0x{len(data):X}"
        )

    char_map = struct.unpack_from(
        "<" + ("H" * char_map_count), data, CHAR_MAP_OFFSET
    )
    used_glyph_ids = sorted(value for value in char_map if value != 0)
    if used_glyph_ids != list(range(1, glyph_count + 1)):
        raise ValueError("Character map does not contain sequential 1-based IDs.")

    out_dir = args.out_dir or args.input.with_suffix("").parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.input.stem

    byte_map_path = out_dir / f"{stem}_byte_map.csv"
    with byte_map_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(("slot", "value"))
        for slot, value in enumerate(data[BYTE_MAP_OFFSET:
                                          BYTE_MAP_OFFSET + BYTE_MAP_SIZE]):
            writer.writerow((slot, value))

    char_map_path = out_dir / f"{stem}_char_map.csv"
    with char_map_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow((
            "page",
            "column",
            "slot",
            "code_type",
            "code",
            "glyph_id",
            "bitmap_record",
        ))

        for slot, glyph_id in enumerate(char_map):
            page, column = divmod(slot, columns_per_page)
            code_type, code = get_slot_code(page, column)
            writer.writerow((
                page,
                column,
                slot,
                code_type,
                code,
                glyph_id,
                glyph_id - 1 if glyph_id else "",
            ))

    atlas_columns = max(1, args.columns)
    scale = max(1, args.scale)
    cell_width = width * scale
    cell_height = height * scale
    label_height = 14
    atlas_rows = math.ceil(glyph_count / atlas_columns)

    atlas = Image.new(
        "RGB",
        (
            atlas_columns * cell_width,
            atlas_rows * (cell_height + label_height),
        ),
        (24, 24, 24),
    )
    draw = ImageDraw.Draw(atlas)

    for record_index in range(glyph_count):
        glyph_id = record_index + 1
        glyph_offset = glyph_data_offset + record_index * bytes_per_glyph
        glyph = decode_glyph(
            data, glyph_offset, width, height, row_stride
        )
        glyph = glyph.resize(
            (cell_width, cell_height), Image.Resampling.NEAREST
        ).convert("RGB")

        x = (record_index % atlas_columns) * cell_width
        y = (record_index // atlas_columns) * (cell_height + label_height)
        atlas.paste(glyph, (x, y))
        draw.text(
            (x + 2, y + cell_height),
            f"{glyph_id:04d}",
            fill=(230, 230, 230),
        )

    atlas_path = out_dir / f"{stem}_glyph_atlas.png"
    atlas.save(atlas_path, optimize=True)

    print(f"File size:        {len(data)}")
    print(f"Version:          {version}")
    print(f"Unknown @ 0x04:   0x{unknown_04:X}")
    print(f"Unknown @ 0x0C:   {unknown_0c}")
    print(f"Unknown flags:    0x{flags:X}")
    print(f"Map dimensions:   {page_count} x {columns_per_page}")
    print(f"Glyphs:           {glyph_count}")
    print(f"Glyph dimensions: {width} x {height} @ {bits_per_pixel}bpp")
    print(f"Glyph data:       0x{glyph_data_offset:X}")
    print(f"Bytes per glyph:  {bytes_per_glyph}")
    print(f"Wrote:            {atlas_path}")
    print(f"Wrote:            {char_map_path}")
    print(f"Wrote:            {byte_map_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
