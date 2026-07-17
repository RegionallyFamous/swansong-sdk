"""Small deterministic PNG-to-WonderSwan 2BPP tile converter.

This deliberately supports the ordinary, non-interlaced PNG formats produced by
pixel-art tools. It has no third-party runtime dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct
import zlib


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
HFLIP = 0x4000
VFLIP = 0x8000


class PNGError(ValueError):
    pass


@dataclass(frozen=True)
class Image:
    width: int
    height: int
    pixels: tuple[tuple[int, int, int, int], ...]


@dataclass(frozen=True)
class Tileset:
    width_tiles: int
    height_tiles: int
    palette: tuple[tuple[int, int, int, int], ...]
    tiles: tuple[bytes, ...]
    tilemap: tuple[int, ...]


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else b if pb <= pc else c


def _unfilter(raw: bytes, width_bytes: int, height: int, bpp: int) -> list[bytes]:
    rows: list[bytes] = []
    offset = 0
    previous = bytes(width_bytes)
    for _ in range(height):
        if offset + 1 + width_bytes > len(raw):
            raise PNGError("truncated PNG image data")
        filter_type = raw[offset]
        source = raw[offset + 1:offset + 1 + width_bytes]
        offset += 1 + width_bytes
        row = bytearray(width_bytes)
        for index, value in enumerate(source):
            left = row[index - bpp] if index >= bpp else 0
            above = previous[index]
            upper_left = previous[index - bpp] if index >= bpp else 0
            if filter_type == 0:
                result = value
            elif filter_type == 1:
                result = value + left
            elif filter_type == 2:
                result = value + above
            elif filter_type == 3:
                result = value + ((left + above) >> 1)
            elif filter_type == 4:
                result = value + _paeth(left, above, upper_left)
            else:
                raise PNGError(f"unsupported PNG filter {filter_type}")
            row[index] = result & 0xFF
        previous = bytes(row)
        rows.append(previous)
    if offset != len(raw):
        raise PNGError("unexpected trailing decompressed PNG data")
    return rows


def read_png(path: str | Path) -> Image:
    payload = Path(path).read_bytes()
    if not payload.startswith(PNG_SIGNATURE):
        raise PNGError("file is not a PNG")
    offset = len(PNG_SIGNATURE)
    header: tuple[int, int, int, int, int, int, int] | None = None
    palette: list[tuple[int, int, int, int]] = []
    transparency = b""
    compressed = bytearray()
    while offset + 12 <= len(payload):
        length = struct.unpack(">I", payload[offset:offset + 4])[0]
        kind = payload[offset + 4:offset + 8]
        body = payload[offset + 8:offset + 8 + length]
        expected_crc = struct.unpack(">I", payload[offset + 8 + length:offset + 12 + length])[0]
        if zlib.crc32(kind + body) & 0xFFFFFFFF != expected_crc:
            raise PNGError(f"CRC mismatch in {kind.decode('ascii', 'replace')} chunk")
        offset += 12 + length
        if kind == b"IHDR":
            if length != 13:
                raise PNGError("invalid IHDR")
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            if length % 3:
                raise PNGError("invalid PLTE")
            palette = [(body[i], body[i + 1], body[i + 2], 255) for i in range(0, length, 3)]
        elif kind == b"tRNS":
            transparency = body
        elif kind == b"IDAT":
            compressed.extend(body)
        elif kind == b"IEND":
            break
    if header is None:
        raise PNGError("PNG has no IHDR")
    width, height, depth, color_type, compression, filter_method, interlace = header
    if width <= 0 or height <= 0:
        raise PNGError("PNG dimensions must be positive")
    if compression != 0 or filter_method != 0 or interlace != 0:
        raise PNGError("only non-interlaced standard PNG compression is supported")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type)
    if channels is None or depth not in ({1, 2, 4, 8} if color_type in (0, 3) else {8}):
        raise PNGError(f"unsupported PNG color type/depth: {color_type}/{depth}")
    scanline_bits = width * channels * depth
    row_bytes = (scanline_bits + 7) // 8
    filter_bpp = max(1, (channels * depth + 7) // 8)
    try:
        raw = zlib.decompress(bytes(compressed))
    except zlib.error as exc:
        raise PNGError(f"invalid PNG compression: {exc}") from exc
    rows = _unfilter(raw, row_bytes, height, filter_bpp)
    if transparency and color_type == 3:
        palette = [
            (r, g, b, transparency[i] if i < len(transparency) else 255)
            for i, (r, g, b, _) in enumerate(palette)
        ]
    pixels: list[tuple[int, int, int, int]] = []
    for row in rows:
        if color_type in (0, 3) and depth < 8:
            samples: list[int] = []
            mask = (1 << depth) - 1
            per_byte = 8 // depth
            for byte in row:
                samples.extend((byte >> ((per_byte - 1 - i) * depth)) & mask for i in range(per_byte))
            samples = samples[:width]
        else:
            samples = list(row)
        if color_type == 0:
            maximum = (1 << depth) - 1
            pixels.extend((v * 255 // maximum, v * 255 // maximum, v * 255 // maximum, 255) for v in samples[:width])
        elif color_type == 3:
            if not palette:
                raise PNGError("indexed PNG has no palette")
            try:
                pixels.extend(palette[v] for v in samples[:width])
            except IndexError as exc:
                raise PNGError("indexed PNG references a missing palette entry") from exc
        else:
            stride = channels
            for x in range(width):
                values = samples[x * stride:(x + 1) * stride]
                if color_type == 2:
                    pixels.append((values[0], values[1], values[2], 255))
                elif color_type == 4:
                    pixels.append((values[0], values[0], values[0], values[1]))
                else:
                    pixels.append((values[0], values[1], values[2], values[3]))
    return Image(width, height, tuple(pixels))


def _flip(tile: tuple[int, ...], horizontal: bool, vertical: bool) -> tuple[int, ...]:
    rows = [tile[index:index + 8] for index in range(0, 64, 8)]
    if horizontal:
        rows = [row[::-1] for row in rows]
    if vertical:
        rows.reverse()
    return tuple(value for row in rows for value in row)


def _pack_2bpp(tile: tuple[int, ...]) -> bytes:
    packed = bytearray()
    for row in range(8):
        plane0 = 0
        plane1 = 0
        for column in range(8):
            value = tile[row * 8 + column]
            plane0 |= (value & 1) << (7 - column)
            plane1 |= ((value >> 1) & 1) << (7 - column)
        packed.extend((plane0, plane1))
    return bytes(packed)


def convert_2bpp(image: Image, *, flip_dedupe: bool = True) -> Tileset:
    palette: list[tuple[int, int, int, int]] = []
    indices: list[int] = []
    for color in image.pixels:
        if color not in palette:
            if len(palette) == 4:
                raise PNGError("2BPP artwork may use at most four RGBA colors")
            palette.append(color)
        indices.append(palette.index(color))
    width_tiles = (image.width + 7) // 8
    height_tiles = (image.height + 7) // 8
    canonical: list[tuple[int, ...]] = []
    packed: list[bytes] = []
    tilemap: list[int] = []
    for tile_y in range(height_tiles):
        for tile_x in range(width_tiles):
            tile = tuple(
                indices[y * image.width + x] if x < image.width and y < image.height else 0
                for y in range(tile_y * 8, tile_y * 8 + 8)
                for x in range(tile_x * 8, tile_x * 8 + 8)
            )
            match: int | None = None
            flags = 0
            candidates = ((False, False, 0),)
            if flip_dedupe:
                candidates += ((True, False, HFLIP), (False, True, VFLIP), (True, True, HFLIP | VFLIP))
            for index, existing in enumerate(canonical):
                for horizontal, vertical, candidate_flags in candidates:
                    if tile == _flip(existing, horizontal, vertical):
                        match, flags = index, candidate_flags
                        break
                if match is not None:
                    break
            if match is None:
                match = len(canonical)
                canonical.append(tile)
                packed.append(_pack_2bpp(tile))
            tilemap.append(match | flags)
    while len(palette) < 4:
        palette.append((0, 0, 0, 0))
    return Tileset(width_tiles, height_tiles, tuple(palette), tuple(packed), tuple(tilemap))


def rgb444(color: tuple[int, int, int, int]) -> int:
    red, green, blue, _ = color
    return ((red >> 4) << 8) | ((green >> 4) << 4) | (blue >> 4)
