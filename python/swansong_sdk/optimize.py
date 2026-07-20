"""Non-destructive asset optimization and mono-preview analysis."""

from __future__ import annotations

import base64
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct
from typing import Any, Mapping
import zlib

from .png2bpp import Image, read_png


SCHEMA = "swansong-asset-optimization-report-v1"
APPLY_SCHEMA = "swansong-asset-optimization-apply-v1"
REVERT_SCHEMA = "swansong-asset-optimization-revert-v1"
ARTIST_APPROVAL = "artist-approved"


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


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode(
        "utf-8"
    )


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _project_path(root: Path, value: str | Path, context: str) -> Path:
    raw = Path(value)
    candidate = (raw if raw.is_absolute() else root / raw).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise OptimizationError(f"{context} must remain inside the project") from exc
    return candidate


def _project_label(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _optimized_image(image: Image, operations: tuple[str, ...]) -> Image:
    allowed = {"palette-reduction", "mono-conversion"}
    if not operations or len(operations) != len(set(operations)):
        raise OptimizationError("optimization operations must be a nonempty unique sequence")
    unknown = [operation for operation in operations if operation not in allowed]
    if unknown:
        raise OptimizationError(f"unknown optimization operation {unknown[0]!r}")
    result = image
    for operation in operations:
        if operation == "palette-reduction":
            _, result = _palette_analysis(result)
        else:
            result, _, _ = _mono_image(result)
    return result


def apply_approved_asset_optimization(
    project_root: str | Path,
    source: str | Path,
    output: str | Path,
    report: str | Path,
    *,
    asset_id: str,
    operations: tuple[str, ...],
    expected_source_sha256: str,
    approval: str,
) -> dict[str, Any]:
    """Apply an artist-approved preview without overwriting its source image.

    The expected hash binds approval to the exact bytes that were previewed.
    Reversal is lossless because the source is preserved and the generated
    output is removed only when its recorded hash still matches.
    """
    if approval != ARTIST_APPROVAL:
        raise OptimizationError("optimization apply requires explicit artist approval")
    if not isinstance(asset_id, str) or not asset_id:
        raise OptimizationError("asset_id must be a nonempty string")
    root = Path(project_root).resolve()
    source_path = _project_path(root, source, "optimization source")
    output_path = _project_path(root, output, "optimization output")
    report_path = _project_path(root, report, "optimization report")
    if not source_path.is_file():
        raise OptimizationError(f"optimization source does not exist: {source}")
    if source_path == output_path:
        raise OptimizationError("optimization output must not overwrite its source")
    if output_path.suffix.lower() != ".png":
        raise OptimizationError("optimization output must be a PNG")
    if report_path.suffix.lower() != ".json":
        raise OptimizationError("optimization report must be JSON")
    if output_path.exists() or report_path.exists():
        raise OptimizationError("optimization apply never overwrites output or reports")
    if not isinstance(expected_source_sha256, str) or len(expected_source_sha256) != 64:
        raise OptimizationError("expected_source_sha256 must be a SHA-256 hex digest")
    try:
        int(expected_source_sha256, 16)
    except ValueError as exc:
        raise OptimizationError("expected_source_sha256 must be a SHA-256 hex digest") from exc
    source_digest = _file_sha256(source_path)
    if source_digest != expected_source_sha256.lower():
        raise OptimizationError("optimization source changed after artist approval")

    image = read_png(source_path)
    optimized = _optimized_image(image, operations)
    payload = encode_rgba_png(optimized)
    output_digest = hashlib.sha256(payload).hexdigest()
    source_label = _project_label(root, source_path)
    output_label = _project_label(root, output_path)
    preview = _analyze(asset_id, image, source_label)
    preview["sourceFileSHA256"] = source_digest
    preview_report = AssetOptimizationReport((preview,)).to_dict()
    preview_digest = hashlib.sha256(_canonical_json(preview_report)).hexdigest()
    operation_report = {
        "schema": APPLY_SCHEMA,
        "asset": asset_id,
        "approval": ARTIST_APPROVAL,
        "operations": list(operations),
        "source": {
            "path": source_label,
            "sha256": source_digest,
            "preserved": True,
        },
        "preview": {"schema": SCHEMA, "sha256": preview_digest},
        "output": {
            "path": output_label,
            "sha256": output_digest,
            "bytes": len(payload),
            "width": optimized.width,
            "height": optimized.height,
        },
        "revert": {
            "action": "delete-generated-output",
            "path": output_label,
            "expectedSHA256": output_digest,
        },
        "reportPath": _project_label(root, report_path),
        "gameplayEvidence": False,
    }
    report_payload = _canonical_json(operation_report)
    report_digest = hashlib.sha256(report_payload).hexdigest()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output_path.open("xb") as handle:
            handle.write(payload)
        with report_path.open("xb") as handle:
            handle.write(report_payload)
    except BaseException:
        if output_path.is_file() and _file_sha256(output_path) == output_digest:
            output_path.unlink()
        raise
    return {**operation_report, "reportSHA256": report_digest}


def revert_approved_asset_optimization(
    project_root: str | Path,
    report: str | Path,
    *,
    expected_report_sha256: str,
    approval: str,
) -> dict[str, Any]:
    """Remove an unchanged generated optimization output using its apply report."""
    if approval != ARTIST_APPROVAL:
        raise OptimizationError("optimization revert requires explicit artist approval")
    root = Path(project_root).resolve()
    report_path = _project_path(root, report, "optimization report")
    if not report_path.is_file():
        raise OptimizationError("optimization apply report does not exist")
    report_payload = report_path.read_bytes()
    report_digest = hashlib.sha256(report_payload).hexdigest()
    if report_digest != expected_report_sha256.lower():
        raise OptimizationError("optimization apply report changed after approval")
    try:
        applied = json.loads(report_payload)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise OptimizationError(f"invalid optimization apply report: {exc}") from exc
    if not isinstance(applied, dict) or applied.get("schema") != APPLY_SCHEMA:
        raise OptimizationError("optimization report has an unsupported schema")
    source_record = applied.get("source")
    output_record = applied.get("output")
    if not isinstance(source_record, dict) or not isinstance(output_record, dict):
        raise OptimizationError("optimization report is missing source or output bindings")
    source_value = source_record.get("path")
    output_value = output_record.get("path")
    if (applied.get("approval") != ARTIST_APPROVAL or source_record.get("preserved") is not True or
            not isinstance(source_value, str) or not isinstance(output_value, str)):
        raise OptimizationError("optimization report has invalid approval or path bindings")
    source_path = _project_path(root, source_value, "optimization source")
    output_path = _project_path(root, output_value, "optimization output")
    if source_path == output_path:
        raise OptimizationError("optimization report cannot remove its source")
    if not source_path.is_file() or _file_sha256(source_path) != source_record.get("sha256"):
        raise OptimizationError("optimization source no longer matches the approved report")
    if not output_path.is_file() or _file_sha256(output_path) != output_record.get("sha256"):
        raise OptimizationError("optimization output changed; refusing destructive revert")
    output_path.unlink()
    return {
        "schema": REVERT_SCHEMA,
        "asset": applied.get("asset"),
        "applyReport": _project_label(root, report_path),
        "applyReportSHA256": report_digest,
        "removedOutput": _project_label(root, output_path),
        "removedOutputSHA256": output_record["sha256"],
        "source": source_record,
        "gameplayEvidence": False,
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
        result = _analyze(asset_id, image, label)
        if not isinstance(source, Image):
            result["sourceFileSHA256"] = _file_sha256(Path(source))
        results.append(result)
    return AssetOptimizationReport(tuple(results))
