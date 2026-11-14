#!/usr/bin/env python3
"""FFON font container reader for the Arika editor.

Implements the observed FFON font format (see research/FFON/5-24-2_FFON_format.md):
  * 0x00 magic "FFON", header fields, 96-byte secondary remap table at 0x40
  * 3840-entry u16 char map at 0xA0 (40 pages x 96 columns, 1-based glyph ids)
  * fixed-size 4bpp glyph bitmap records (24x24 default, 12-byte row stride)

Provides parsing plus Pillow image rendering for preview/atlas export.
Pillow is already a project dependency (requirements_scene_editor.txt).
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

MAGIC = b"FFON"
HEADER_SIZE = 0x40
BYTE_MAP_OFFSET = 0x40
BYTE_MAP_SIZE = 0x60
CHAR_MAP_OFFSET = 0xA0


class FFONError(ValueError):
    """Raised when data is not a valid FFON font or fails validation."""


def read_u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def read_u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def decode_glyph(data: bytes, offset: int, width: int, height: int,
                 row_stride: int) -> Image.Image:
    """Decode one row-major 4bpp glyph; even x uses the low nibble.

    Returns an "RGBA" image where RGB = nibble value * 17 and alpha = nibble
    value * 17, so empty pixels (value 0) are fully transparent instead of
    pure black.
    """
    pixels = bytearray(width * height * 4)
    for y in range(height):
        row_offset = offset + y * row_stride
        for x in range(width):
            packed = data[row_offset + (x // 2)]
            value = (packed & 0x0F) if (x & 1) == 0 else (packed >> 4)
            intensity = value * 17
            base = (y * width + x) * 4
            pixels[base] = intensity
            pixels[base + 1] = intensity
            pixels[base + 2] = intensity
            pixels[base + 3] = intensity
    return Image.frombytes("RGBA", (width, height), bytes(pixels))


@dataclass
class c_ffon_font:
    """Parsed FFON font container."""

    width: int = 24
    height: int = 24
    bits_per_pixel: int = 4
    row_stride: int = 12
    page_count: int = 40
    last_column: int = 95
    glyph_count: int = 0
    columns_per_page: int = 96
    char_map: list[int] = None  # type: ignore[assignment]
    byte_map: list[int] = None  # type: ignore[assignment]
    glyph_data_offset: int = 0
    bytes_per_glyph: int = 0
    version: int = 0
    unknown_04: int = 0
    unknown_0c: int = 0
    flags: int = 0

    def __post_init__(self) -> None:
        if self.char_map is None:
            self.char_map = []
        if self.byte_map is None:
            self.byte_map = []
        self.columns_per_page = self.last_column + 1

    @property
    def char_map_count(self) -> int:
        return self.page_count * self.columns_per_page

    def glyph_offset(self, record_index: int) -> int:
        return self.glyph_data_offset + record_index * self.bytes_per_glyph

    def mapped_cells(self) -> list[tuple[int, int, int]]:
        """Return (page, column, glyph_id) for every nonzero map entry."""
        out = []
        for slot, glyph_id in enumerate(self.char_map):
            if glyph_id:
                out.append((slot // self.columns_per_page,
                            slot % self.columns_per_page, glyph_id))
        return out

    def byte_map_nonzero(self) -> list[tuple[int, int]]:
        return [(slot, value) for slot, value in enumerate(self.byte_map) if value]


def parse_ffon(data: bytes) -> c_ffon_font:
    """Parse and validate an FFON font buffer."""
    if len(data) < HEADER_SIZE or data[:4] != MAGIC:
        raise FFONError("Not an FFON file: missing magic.")

    version = read_u32(data, 0x08)
    unknown_04 = read_u32(data, 0x04)
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
        raise FFONError(f"Unsupported bpp: {bits_per_pixel}")

    expected_stride = (width * bits_per_pixel + 7) // 8
    if row_stride != expected_stride:
        raise FFONError(
            f"Unexpected row stride {row_stride}; expected {expected_stride}")

    columns_per_page = last_column + 1
    char_map_count = page_count * columns_per_page
    char_map_size = char_map_count * 2
    glyph_data_offset = CHAR_MAP_OFFSET + char_map_size
    bytes_per_glyph = row_stride * height
    expected_size = glyph_data_offset + glyph_count * bytes_per_glyph

    if len(data) < expected_size:
        raise FFONError(
            f"File too small: have {len(data)} bytes, need 0x{expected_size:X}")

    char_map = list(struct.unpack_from(
        "<" + ("H" * char_map_count), data, CHAR_MAP_OFFSET))

    used = sorted(v for v in char_map if v != 0)
    if used != list(range(1, glyph_count + 1)):
        raise FFONError("Character map does not contain sequential 1-based IDs.")

    byte_map = list(data[BYTE_MAP_OFFSET:BYTE_MAP_OFFSET + BYTE_MAP_SIZE])

    font = c_ffon_font(
        width=width, height=height, bits_per_pixel=bits_per_pixel,
        row_stride=row_stride, page_count=page_count, last_column=last_column,
        glyph_count=glyph_count, columns_per_page=columns_per_page,
        char_map=char_map, byte_map=byte_map,
        glyph_data_offset=glyph_data_offset, bytes_per_glyph=bytes_per_glyph,
        version=version, unknown_04=unknown_04, unknown_0c=unknown_0c,
        flags=flags,
    )
    return font


def render_atlas(font: c_ffon_font, data: bytes, columns: int = 32,
                 scale: int = 2) -> Image.Image:
    """Render a labelled glyph contact-sheet atlas as an RGB image."""
    columns = max(1, columns)
    scale = max(1, scale)
    cell_w = font.width * scale
    cell_h = font.height * scale
    label_h = 14
    rows = math.ceil(font.glyph_count / columns)

    atlas = Image.new("RGB", (columns * cell_w, rows * (cell_h + label_h)),
                      (24, 24, 24))
    from PIL import ImageDraw
    draw = ImageDraw.Draw(atlas)

    for record_index in range(font.glyph_count):
        glyph_id = record_index + 1
        glyph = decode_glyph(data, font.glyph_offset(record_index),
                             font.width, font.height, font.row_stride)
        glyph = glyph.resize((cell_w, cell_h), Image.Resampling.NEAREST)

        x = (record_index % columns) * cell_w
        y = (record_index // columns) * (cell_h + label_h)
        # Composite using a binary alpha mask: glyph pixels copy at full
        # intensity, empty pixels show the atlas background instead of black.
        mask = glyph.getchannel("A").point(lambda p: 255 if p else 0)
        atlas.paste(glyph.convert("RGB"), (x, y), mask=mask)
        draw.text((x + 2, y + cell_h), f"{glyph_id:04d}",
                  fill=(230, 230, 230))
    return atlas


def _char_to_glyph_id(font: c_ffon_font, ch: str) -> int:
    """Look up the 1-based glyph id for a single character (page 0 ASCII)."""
    code = ord(ch)
    if 0x20 <= code <= 0x7E:
        column = code - 0x20
        slot = column  # page 0, ASCII row
        if 0 <= slot < len(font.char_map):
            return font.char_map[slot]
    return 0


def render_text(font: c_ffon_font, data: bytes, text: str,
                spacing: int = 3, max_width: int | None = None) -> Image.Image:
    """Render user text as glyphs in rows (RGB image).

    Newlines (``\\n`` and ``\\r\\n``) start a new row. When ``max_width`` is
    given, each explicit line is word-wrapped so no row exceeds it. Only
    page-0 ASCII characters (0x20-0x7E) have defined glyphs; unmapped
    characters are skipped. The em/en dash is replaced by a hyphen.

    Glyphs are trimmed to their content bounding box before placement so
    narrow characters do not carry empty cell padding, producing tighter
    text spacing that matches the source game.
    """
    cell_w = font.width
    cell_h = font.height
    text = text.replace("\u2014", "-").replace("\u2013", "-")
    explicit_lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    def gid(ch: str) -> int:
        return _char_to_glyph_id(font, ch)

    # Cache trimmed glyphs: record_index -> (image, width, height)
    _trimmed_cache: dict[int, tuple[Image.Image, int, int]] = {}

    def get_trimmed(record_index: int) -> tuple[Image.Image, int, int]:
        if record_index not in _trimmed_cache:
            glyph = decode_glyph(data, font.glyph_offset(record_index),
                                 font.width, font.height, font.row_stride)
            bbox = glyph.getbbox()
            if bbox is None:
                trimmed = Image.new("RGBA", (1, cell_h), (0, 0, 0, 0))
            else:
                # Keep full cell height to preserve ascender/descender
                # spacing between lines; only trim horizontal padding.
                trimmed = glyph.crop((bbox[0], 0, bbox[2], cell_h))
            _trimmed_cache[record_index] = (trimmed, trimmed.width, trimmed.height)
        return _trimmed_cache[record_index]

    def char_width(ch: str) -> int:
        g = gid(ch)
        if not g:
            return 0
        _, w, _ = get_trimmed(g - 1)
        return w

    def space_width() -> int:
        """Minimum width for a space so words stay separated."""
        return max(8, cell_w // 3)

    def segment_width(seg: str) -> int:
        total = 0
        first = True
        for ch in seg:
            if ch == " ":
                continue  # spaces handled as segment separators
            cw = char_width(ch)
            if cw == 0:
                continue
            if not first:
                total += spacing
            total += cw
            first = False
        return total

    def row_width(segments: list[str]) -> int:
        right_edge = 0
        have_content = False
        first = True
        for seg in segments:
            if not first:
                right_edge += spacing + space_width() + spacing
            first = False
            sw = segment_width(seg)
            if sw > 0:
                right_edge += sw
                have_content = True
        return right_edge if have_content else 0

    # Build rows: each row is a list of segments (strings) separated by
    # single space cells. For max_width=None each explicit line is one row.
    rows: list[list[str]] = []
    for line in explicit_lines:
        if max_width:
            words = [w for w in line.split(" ") if any(gid(ch) for ch in w)]
            if not words:
                rows.append([])  # preserve blank explicit lines
                continue
            current: list[str] = []
            for word in words:
                if current:
                    combined = row_width(current + [word])
                    if combined > max_width:
                        rows.append(current)
                        current = [word]
                    else:
                        current.append(word)
                else:
                    current = [word]
            rows.append(current)
        else:
            rows.append(line.split(' '))

    if not rows:
        return Image.new("RGBA", (cell_w, cell_h), (0, 0, 0, 0))

    total_h = len(rows) * cell_h
    max_w = max(row_width(row) for row in rows)
    if max_w == 0:
        return Image.new("RGBA", (cell_w, cell_h), (0, 0, 0, 0))

    img = Image.new("RGBA", (max_w, total_h), (0, 0, 0, 0))
    y = 0
    for row in rows:
        x = 0
        first_seg = True
        for seg in row:
            if not first_seg:
                # A space is an advance, not glyph record zero.
                x += space_width() + 2 * spacing
            first_seg = False
            first_char = True
            for ch in seg:
                if ch == " ":
                    continue  # spaces handled as segment separators
                g = gid(ch)
                if not g:
                    continue
                cw = char_width(ch)
                if cw == 0:
                    continue
                trimmed, tw, _ = get_trimmed(g - 1)
                mask = trimmed.getchannel("A").point(lambda p: 255 if p else 0)
                img.paste(trimmed.convert("RGB"), (x, y), mask=mask)
                x += tw + spacing
                first_char = False
        y += cell_h
    return img


def font_info_text(path: str, font: c_ffon_font, data_len: int) -> str:
    """Human-readable summary of the font."""
    mapped = len(font.mapped_cells())
    lines = [
        f"Entry: {path}",
        "Kind: font (FFON)",
        f"Size: {data_len} bytes",
        f"Magic: FFON",
        f"Version: {font.version}",
        f"Unknown @ 0x04: 0x{font.unknown_04:X}",
        f"Unknown @ 0x0C: {font.unknown_0c}",
        f"Unknown flags @ 0x20: 0x{font.flags:X}",
        f"Map dimensions: {font.page_count} x {font.columns_per_page}",
        f"Glyphs: {font.glyph_count}",
        f"Glyph dimensions: {font.width} x {font.height} @ {font.bits_per_pixel}bpp",
        f"Row stride: {font.row_stride}, bytes per glyph: {font.bytes_per_glyph}",
        f"Glyph data offset: 0x{font.glyph_data_offset:X}",
        f"Mapped cells: {mapped} / {font.char_map_count}",
        f"Byte-map (0x40) nonzero entries: {len(font.byte_map_nonzero())}",
    ]
    nonzero = font.byte_map_nonzero()
    if nonzero:
        lines.append("Byte-map nonzero: " + ", ".join(
            f"{s}:{v}" for s, v in nonzero[:16]) +
            (f" ... (+{len(nonzero)-16} more)" if len(nonzero) > 16 else ""))
    return "\n".join(lines)


def image_to_qpixmap(image: Image.Image):
    """Convert a Pillow image to a QPixmap without writing to disk.

    Uses PNG buffering so QImage never has to guess row alignment from raw
    RGB bytes (which breaks when 3*width is not a multiple of 4).
    """
    from PySide6 import QtGui as G
    import io
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    img = G.QImage.fromData(buffer.read())
    return G.QPixmap.fromImage(img)


def parse_ffon_file(path) -> c_ffon_font:
    return parse_ffon(Path(path).read_bytes())


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Decode an FFON font file.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--columns", type=int, default=32)
    parser.add_argument("--scale", type=int, default=2)
    args = parser.parse_args()

    font = parse_ffon_file(args.input)
    data = args.input.read_bytes()
    out_dir = args.out_dir or args.input.with_suffix("").parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.input.stem

    atlas = render_atlas(font, data, columns=args.columns, scale=args.scale)
    atlas_path = out_dir / f"{stem}_glyph_atlas.png"
    atlas.save(atlas_path, optimize=True)

    char_map_path = out_dir / f"{stem}_char_map.csv"
    import csv
    with char_map_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(("page", "column", "slot", "glyph_id", "bitmap_record"))
        for page, column, glyph_id in font.mapped_cells():
            slot = page * font.columns_per_page + column
            writer.writerow((page, column, slot, glyph_id, glyph_id - 1))

    byte_map_path = out_dir / f"{stem}_byte_map.csv"
    with byte_map_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(("slot", "value"))
        for slot, value in enumerate(font.byte_map):
            writer.writerow((slot, value))

    print(font_info_text(str(args.input), font, len(data)))
    print(f"Wrote: {atlas_path}")
    print(f"Wrote: {char_map_path}")
    print(f"Wrote: {byte_map_path}")
    raise SystemExit(0)