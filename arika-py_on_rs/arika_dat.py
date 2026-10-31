#!/usr/bin/env python3
"""Inspect, extract and rebuild Super Dragon Ball Z's INFO.DAT / GAME.DAT."""
import argparse
import binascii
import csv
import fnmatch
import json
from pathlib import Path, PurePosixPath
import struct
import sys
import tempfile
import zlib

import arika_backend as backend

MAGIC = b"\x7fwww.arika.co.jp"
SECTOR = 2048
HEADER = 0x30
RECORD = 0x30


def swap_nibbles(value):
    return ((value & 15) << 4) | (value >> 4)


def decode_info(data):
    return backend.decode_info(data)


def encode_info(data):
    return backend.encode_info(data)


def relative_name(name):
    path = PurePosixPath(name.replace("\\", "/"))
    if not name or path.is_absolute() or ".." in path.parts or ":" in name or any(ord(c) < 32 for c in name):
        raise ValueError("unsafe asset path: " + repr(name))
    return path


def asset_path(root, name):
    path = root.joinpath(*relative_name(name).parts)
    path.resolve().relative_to(root.resolve())
    return path


class Entry:
    def __init__(self, index, name, unknown, sector, sectors, size, offset=0):
        self.index = index
        self.name = name
        self.unknown = unknown
        self.sector = sector
        self.sectors = sectors
        self.size = size
        self._offset = offset

    @property
    def offset(self):
        return self._offset

    def __repr__(self):
        return f"Entry(index={self.index}, name={self.name!r}, size={self.size})"


class Archive:
    def __init__(self, info, game=None):
        self.info = Path(info)
        self.game = Path(game) if game else None
        self._archive = backend.Archive(str(self.info), str(self.game) if self.game else None)
        self._entries = None
        self._used_bytes = None

    @property
    def entries(self):
        if self._entries is None:
            self._entries = self._archive.entries
        return self._entries

    @property
    def used_bytes(self):
        if self._used_bytes is None:
            self._used_bytes = self._archive.used_bytes
        return self._used_bytes

    def rebuild(self, destination, replacements=None):
        self._archive.rebuild(destination, replacements)

    def extract(self, destination, patterns=(), overwrite=False):
        self._archive.extract(destination, patterns, overwrite)

    def manifest(self):
        result = []
        source = self.game.open("rb") if self.game else None
        try:
            for entry in self.entries:
                row = dict(
                    index=entry.index,
                    name=entry.name,
                    unknown=entry.unknown,
                    sector=entry.sector,
                    offset=entry.offset,
                    sectors=entry.sectors,
                    size=entry.size,
                )
                if source:
                    source.seek(entry.offset)
                    signature = source.read(min(4, entry.size))
                    row["magic_hex"] = signature.hex()
                    row["magic_ascii"] = "".join(
                        chr(c) if 32 <= c < 127 else "." for c in signature
                    )
                result.append(row)
        finally:
            if source:
                source.close()
        return result


def exact_copy(source, output, count):
    while count:
        chunk = source.read(min(count, 4 << 20))
        if not chunk:
            raise ValueError("unexpected end of input file")
        output.write(chunk)
        count -= len(chunk)


def extract(archive, destination, patterns=(), overwrite=False):
    archive.extract(Path(destination), patterns, overwrite)


def rebuild(archive, destination, replacements=None):
    archive.rebuild(Path(destination), replacements)


def container(data):
    if len(data) < 32 or data[:4] not in [b"FPIX", b"FMDL"]:
        raise ValueError("expected FPIX or FMDL")
    size, count, version = struct.unpack_from("<III", data, 4)
    if size != len(data) or not count or 32 + count * 4 > size:
        raise ValueError("invalid container header")
    offsets = struct.unpack_from("<" + "I" * count, data, 32)
    if offsets[0] != 32 + count * 4:
        raise ValueError("unexpected container table layout")
    chunks = []
    for index, offset in enumerate(offsets):
        end = offsets[index + 1] if index + 1 < count else size
        if not offset < end <= size or end - offset < 8:
            raise ValueError("invalid container chunk extent")
        chunk_size, = struct.unpack_from("<I", data, offset + 4)
        if chunk_size != end - offset:
            raise ValueError("chunk size does not match offset table")
        chunks.append(dict(index=index, magic=data[offset:offset + 4].decode("ascii"), offset=offset, size=chunk_size))
    return dict(magic=data[:4].decode("ascii"), size=size, version=version, chunks=chunks)


def split_container(path, destination, overwrite=False):
    data = Path(path).read_bytes()
    metadata = container(data)
    root = Path(destination)
    files = [(root / "container.json", json.dumps(metadata, indent=2).encode())]
    for chunk in metadata["chunks"]:
        tag = chunk["magic"]
        if not tag.isascii() or not tag.isalnum():
            raise ValueError("unsafe chunk tag")
        body = data[chunk["offset"]:chunk["offset"] + chunk["size"]]
        files.append((root / ("%04d.%s" % (chunk["index"], tag)), body))
        if tag == "XPIX" and body[32:36] == b"TIM2":
            files.append((root / ("%04d.tm2" % chunk["index"]), body[32:]))
    for filename, _ in files:
        if filename.exists() and not overwrite:
            raise ValueError("output exists: " + str(filename))
    root.mkdir(parents=True, exist_ok=True)
    for filename, body in files:
        filename.write_bytes(body)
    print("Split %d chunks to %s" % (len(metadata["chunks"]), root))


def motion_archive(data):
    if len(data) < 16 or data[:6] != b"RFSML3":
        raise ValueError("expected RFSM/L3")
    count, = struct.unpack_from("<H", data, 6)
    shared, shared_end = struct.unpack_from("<II", data, 8)
    if shared != 16 + count * 32 or not shared + 16 <= shared_end <= len(data):
        raise ValueError("invalid RFSM shared block")
    shared_count, bones, names, bindings, flags = struct.unpack_from("<HHIII", data, shared)
    if shared_count != count or names != shared + 16 or bindings != names + bones * 16 or shared_end != flags + bones or not bindings <= flags <= len(data):
        raise ValueError("unexpected RFSM skeleton layout")
    bone_list = [dict(index=index, name=data[names + index * 16:names + (index + 1) * 16].split(b"\0", 1)[0].decode("cp932"), flags=data[flags + index]) for index in range(bones)]
    motions = []
    for index in range(count):
        at = 16 + index * 32
        name = data[at:at + 16].split(b"\0", 1)[0].decode("cp932")
        relative_name(name)
        offset, size, unknown, format_value = struct.unpack_from("<4I", data, at + 16)
        if offset < shared_end or offset + size > len(data) or size < 8 or data[offset:offset + 4] != b"MOT2" or struct.unpack_from("<I", data, offset + 4)[0] != size:
            raise ValueError("invalid MOT2 extent")
        motions.append(dict(index=index, name=name, offset=offset, size=size, unknown=unknown, format_value=format_value))
    return dict(magic="RFSM", tag="L3", count=count, shared_offset=shared, shared_end=shared_end,
        bone_names_offset=names, bindings_offset=bindings, bone_flags_offset=flags, bones=bone_list, motions=motions)


def split_motion_archive(path, destination, overwrite=False):
    data = Path(path).read_bytes()
    metadata = motion_archive(data)
    root = Path(destination)
    files = [(root / "motion_archive.json", json.dumps(metadata, indent=2, ensure_ascii=False).encode("utf-8")),
        (root / "shared.bin", data[metadata["shared_offset"]:(metadata["shared_end"] + 15) & ~15])]
    for motion in metadata["motions"]:
        name = "%04d_%s" % (motion["index"], PurePosixPath(motion["name"]).name)
        files.append((root / name, data[motion["offset"]:motion["offset"] + motion["size"]]))
    for filename, _ in files:
        if filename.exists() and not overwrite:
            raise ValueError("output exists: " + str(filename))
    root.mkdir(parents=True, exist_ok=True)
    for filename, body in files:
        filename.write_bytes(body)
    print("Split %d MOT2 motions and %d bone names to %s" % (metadata["count"], len(metadata["bones"]), root))


def tim2_rgba(data, linear_clut=False):
    if len(data) < 16 or data[:4] != b"TIM2":
        raise ValueError("expected TIM2")
    version, format_value, pictures = struct.unpack_from("<BBH", data, 4)
    if format_value not in (0, 1) or pictures != 1:
        raise ValueError("PNG preview supports a single TIM2 picture")
    at = 128 if format_value == 1 else 16
    if at + 48 > len(data):
        raise ValueError("truncated TIM2 picture")
    total, clut_size, image_size, header_size, colors, picture_format, mipmaps, clut_type, image_type, width, height = struct.unpack_from("<IIIHHBBBBHH", data, at)
    if mipmaps != 1 or not width or not height or header_size < 48 or header_size + image_size + clut_size > total or at + total > len(data):
        raise ValueError("unsupported/truncated TIM2 layout")
    image = data[at + header_size:at + header_size + image_size]
    palette = data[at + header_size + image_size:at + header_size + image_size + clut_size]
    output = bytearray()
    if image_type == 3:
        if len(image) != width * height * 4:
            raise ValueError("unexpected RGBA32 image size")
        for index in range(0, len(image), 4):
            output += image[index:index + 3] + bytes([min(255, image[index + 3] * 2)])
    elif image_type in (4, 5):
        if (clut_type & 0x3F) != 3 or len(palette) < colors * 4:
            raise ValueError("preview requires RGBA32 palette entries")
        expected = (width * height + 1) // 2 if image_type == 4 else width * height
        if len(image) != expected:
            raise ValueError("unexpected indexed image size")
        for pixel in range(width * height):
            color = image[pixel // 2] >> ((pixel & 1) * 4) & 15 if image_type == 4 else image[pixel]
            if image_type == 5 and not linear_clut and not clut_type & 0x80:
                color = (color & ~0x18) | ((color & 8) << 1) | ((color & 16) >> 1)
            if color >= colors:
                raise ValueError("palette index out of range")
            entry = palette[color * 4:color * 4 + 4]
            output += entry[:3] + bytes([min(255, entry[3] * 2)])
    else:
        raise ValueError("preview supports the sample's RGBA32, indexed4 and indexed8 image types")
    return width, height, bytes(output)


def tim2_png_bytes(data, linear_clut=False):
    """Decode one TIM2 picture to PNG bytes without temporary files."""
    width, height, rgba = tim2_rgba(data, linear_clut)

    def chunk(tag, body):
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", binascii.crc32(tag + body) & 0xFFFFFFFF)

    scanlines = b"".join(b"\0" + rgba[row * width * 4:(row + 1) * width * 4] for row in range(height))
    return (b"\x89PNG\r\n\x1a\n" +
        chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) +
        chunk(b"IDAT", zlib.compress(scanlines)) + chunk(b"IEND", b""))


def tim2_png(path, output, linear_clut=False):
    if Path(path).resolve() == Path(output).resolve():
        raise ValueError("PNG output must differ from input")
    Path(output).write_bytes(tim2_png_bytes(Path(path).read_bytes(), linear_clut))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    listing = subs.add_parser("list")
    listing.add_argument("info"); listing.add_argument("--game"); listing.add_argument("--json", type=Path); listing.add_argument("--csv", type=Path)
    decoding = subs.add_parser("decode-info")
    decoding.add_argument("info", type=Path); decoding.add_argument("output", type=Path)
    encoding = subs.add_parser("encode-info")
    encoding.add_argument("info", type=Path); encoding.add_argument("output", type=Path)
    extracting = subs.add_parser("extract")
    extracting.add_argument("info"); extracting.add_argument("game"); extracting.add_argument("output"); extracting.add_argument("--pattern", action="append", default=[]); extracting.add_argument("--overwrite", action="store_true")
    repacking = subs.add_parser("repack")
    repacking.add_argument("info"); repacking.add_argument("game"); repacking.add_argument("output"); repacking.add_argument("--replacements")
    splitting = subs.add_parser("split-container")
    splitting.add_argument("input"); splitting.add_argument("output"); splitting.add_argument("--overwrite", action="store_true")
    motions = subs.add_parser("split-rfsm")
    motions.add_argument("input"); motions.add_argument("output"); motions.add_argument("--overwrite", action="store_true")
    preview = subs.add_parser("tim2-png")
    preview.add_argument("input"); preview.add_argument("output"); preview.add_argument("--linear-clut", action="store_true")
    args = parser.parse_args()
    try:
        if args.command in ("decode-info", "encode-info"):
            if args.output.resolve() == args.info.resolve():
                raise ValueError("decoded output must differ from input")
            transform = decode_info if args.command == "decode-info" else encode_info
            args.output.write_bytes(transform(args.info.read_bytes()))
        elif args.command == "split-container":
            split_container(args.input, args.output, args.overwrite)
        elif args.command == "split-rfsm":
            split_motion_archive(args.input, args.output, args.overwrite)
        elif args.command == "tim2-png":
            tim2_png(args.input, args.output, args.linear_clut)
        else:
            archive = Archive(args.info, args.game)
            if args.command == "extract":
                extract(archive, args.output, args.pattern, args.overwrite)
            elif args.command == "repack":
                rebuild(archive, args.output, args.replacements)
            else:
                rows = archive.manifest()
                if args.json:
                    args.json.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
                if args.csv:
                    with args.csv.open("w", encoding="utf-8-sig", newline="") as out:
                        writer = csv.DictWriter(out, fieldnames=list(rows[0]) if rows else ["index", "name"])
                        writer.writeheader(); writer.writerows(rows)
                if not args.json and not args.csv:
                    for row in rows:
                        print("%4d %10d %10d %s" % (row["index"], row["offset"], row["size"], row["name"]))
                print("%d assets; indexed extent %d bytes" % (len(rows), archive.used_bytes), file=sys.stderr)
    except (OSError, ValueError, UnicodeError, struct.error) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
