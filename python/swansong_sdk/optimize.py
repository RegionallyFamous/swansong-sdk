"""Non-destructive asset optimization and mono-preview analysis."""

from __future__ import annotations

import base64
from collections import Counter
from dataclasses import dataclass
import hashlib
from pathlib import Path
import struct
from typing import Any, Mapping
import zlib

from .png2bpp import Image, read_png


SCHEMA = "swansong-asset-optimization-report-v1"


class OptimizationError(ValueError):
    pass


@dataclass(frozen=True)
class AssetOptimizationReport:
    assets: tuple[Mapping[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        exact = sum(int(asset["tiles"]["exactUnique"]) for asset in self.assets)
        flipped = sum(int(asset["tiles"]["flipUnique"]) for asset in self.assets)
        return {
            "schema": SCHEMA,
            "assets": [dict(asset) for asset in self.assets],
            "totals": {
                "sourceTiles": sum(int(asset["tiles"]["sourceTiles"]) for asset in self.assets),
                "exactUniqueTiles": exact,
                "flipUniqueTiles": flipped,
                "flipDedupeSavingsTiles": exact - flipped,
                "flipDedupeSavingsBytes2Bpp": (exact - flipped) * 16,
            },
        }


def _rgba_hex(color: tuple[int, int, int, int]) -> str:
    return "#" + "".join(f"{value:02X}" for value in color)


def _image_digest(image: Image) -> str:
    digest = hashlib.sha256()
    digest.update(struct.pack(">II", image.width, image.height))
    for color in image.pixels:
        digest.update(bytes(color))
    return digest.hexdigest()


def _tiles(image: Image) -> list[tuple[tuple[int, int, int, int], ...]]:
    width_tiles = (image.width + 7) // 8
    height_tiles = (image.height + 7) // 8
    transparent = (0, 0, 0, 0)
    return [
        tuple(
            image.pixels[y * image.width + x]
            if x < image.width and y < image.height else transparent
            for y in range(tile_y * 8, tile_y * 8 + 8)
            for x in range(tile_x * 8, tile_x * 8 + 8)
        )
        for tile_y in range(height_tiles)
        for tile_x in range(width_tiles)
    ]


def _flip(tile: tuple[Any, ...], horizontal: bool, vertical: bool) -> tuple[Any, ...]:
    rows = [tile[offset:offset + 8] for offset in range(0, 64, 8)]
    if horizontal:
        rows = [row[::-1] for row in rows]
    if vertical:
        rows.reverse()
    return tuple(value for row in rows for value in row)


def _canonical_flip(tile: tuple[Any, ...]) -> tuple[Any, ...]:
    return min(
        tile,
        _flip(tile, True, False),
        _flip(tile, False, True),
        _flip(tile, True, True),
    )


def _nearest(color: tuple[int, int, int, int],
             palette: tuple[tuple[int, int, int, int], ...]) -> tuple[int, int, int, int]:
    return min(palette, key=lambda candidate: (
        sum((color[index] - candidate[index]) ** 2 for index in range(4)),
        candidate,
    ))


def _palette_analysis(image: Image) -> tuple[dict[str, Any], Image]:
    counts = Counter(image.pixels)
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    selected = tuple(color for color, _ in ordered[:4])
    mapping = {color: _nearest(color, selected) for color in counts}
    reduced = Image(image.width, image.height,
                    tuple(mapping[color] for color in image.pixels))
    recommendations: list[dict[str, Any]] = []
    if len(counts) > 4:
        recommendations.append({
            "severity": "required",
            "code": "reduce-to-2bpp-palette",
            "message": f"reduce {len(counts)} RGBA colors to four before 2BPP conversion",
            "suggestedPalette": [_rgba_hex(color) for color in selected],
        })
    elif len(counts) < 4:
        recommendations.append({
            "severity": "info",
            "code": "palette-headroom",
            "message": f"asset uses {len(counts)} of four available 2BPP colors",
        })
    return ({
        "uniqueRgbaColors": len(counts),
        "usage": [
            {"rgba": _rgba_hex(color), "pixels": count}
            for color, count in ordered
        ],
        "reductionMapping": [
            {
                "from": _rgba_hex(color),
                "to": _rgba_hex(mapping[color]),
                "pixels": counts[color],
            }
            for color in sorted(mapping)
            if mapping[color] != color
        ],
        "recommendations": recommendations,
    }, reduced)


def _mono_image(image: Image) -> tuple[Image, bytes, Counter[int]]:
    shades = (0, 85, 170, 255)
    pixels: list[tuple[int, int, int, int]] = []
    indices: list[int] = []
    for red, green, blue, alpha in image.pixels:
        luminance = (299 * red + 587 * green + 114 * blue + 500) // 1000
        index = min(range(4), key=lambda candidate: (abs(luminance - shades[candidate]), candidate))
        indices.append(index)
        shade = shades[index]
        pixels.append((shade, shade, shade, alpha))
    result = Image(image.width, image.height, tuple(pixels))
    return result, bytes(indices), Counter(indices)


def _png_chunk(kind: bytes, body: bytes) -> bytes:
    return (struct.pack(">I", len(body)) + kind + body +
            struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF))


def encode_rgba_png(image: Image) -> bytes:
    rows = bytearray()
    for y in range(image.height):
        rows.append(0)
        for color in image.pixels[y * image.width:(y + 1) * image.width]:
            rows.extend(color)
    header = struct.pack(">IIBBBBB", image.width, image.height, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", header) +
            _png_chunk(b"IDAT", zlib.compress(bytes(rows), 9)) +
            _png_chunk(b"IEND", b""))


def _analyze(asset_id: str, image: Image, source: str | None) -> dict[str, Any]:
    source_tiles = _tiles(image)
    exact = len(set(source_tiles))
    flipped = len({_canonical_flip(tile) for tile in source_tiles})
    palette, reduced = _palette_analysis(image)
    mono, indices, histogram = _mono_image(reduced)
    mono_png = encode_rgba_png(mono)
    return {
        "id": asset_id,
        "source": source,
        "sourceImageSha256": _image_digest(image),
        "width": image.width,
        "height": image.height,
        "tiles": {
            "sourceTiles": len(source_tiles),
            "exactUnique": exact,
            "flipUnique": flipped,
            "exactSavingsTiles": len(source_tiles) - exact,
            "flipSavingsBeyondExactTiles": exact - flipped,
            "flipSavingsBeyondExactBytes2Bpp": (exact - flipped) * 16,
        },
        "palette": palette,
        "monoVariant": {
            "width": mono.width,
            "height": mono.height,
            "shadePalette": ["#000000", "#555555", "#AAAAAA", "#FFFFFF"],
            "shadeUsage": [histogram.get(index, 0) for index in range(4)],
            "pixelIndicesBase64": base64.b64encode(indices).decode("ascii"),
            "pngSha256": hashlib.sha256(mono_png).hexdigest(),
            "pngBase64": base64.b64encode(mono_png).decode("ascii"),
        },
    }


def preview_asset_optimization(
    assets: Mapping[str, str | Path | Image] | str | Path | Image,
) -> AssetOptimizationReport:
    if isinstance(assets, Mapping):
        items = list(assets.items())
    else:
        if isinstance(assets, Image):
            items = [("asset", assets)]
        else:
            path = Path(assets)
            items = [(path.stem, path)]
    results: list[Mapping[str, Any]] = []
    for asset_id, source in sorted(items, key=lambda item: str(item[0])):
        if not isinstance(asset_id, str) or not asset_id:
            raise OptimizationError("asset ids must be nonempty strings")
        if isinstance(source, Image):
            image = source
            label = None
        else:
            path = Path(source)
            image = read_png(path)
            label = str(path)
        results.append(_analyze(asset_id, image, label))
    return AssetOptimizationReport(tuple(results))
