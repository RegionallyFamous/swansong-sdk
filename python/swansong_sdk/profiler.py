"""Resource profiling from manifests, generated reports, and declared traces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


SCHEMA = "swansong-profile-report-v1"
DISPLAY_WIDTH = 224
DISPLAY_HEIGHT = 144
DEFAULT_FRAME_BUDGET_US = 1_000_000 * 100 / 7547


class ProfileError(ValueError):
    pass


@dataclass(frozen=True)
class ProfileReport:
    limits: Mapping[str, int | float | None]
    peaks: Mapping[str, int | float]
    findings: tuple[Mapping[str, Any], ...]
    frames_analyzed: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "framesAnalyzed": self.frames_analyzed,
            "limits": dict(self.limits),
            "peaks": dict(self.peaks),
            "findings": [dict(item) for item in self.findings],
        }


def _mapping(value: Any) -> Mapping[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return value
    if hasattr(value, "__dict__"):
        return vars(value)
    raise ProfileError("profile inputs must be mappings or manifest objects")


def _number(source: Mapping[str, Any], *keys: str) -> int | float | None:
    for key in keys:
        value = source.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
    return None


def _limit_sources(manifest: Any, report: Mapping[str, Any]) -> dict[str, int | float | None]:
    root = _mapping(manifest)
    manifest_budgets = _mapping(root.get("budgets"))
    report_budgets = _mapping(report.get("budgets"))
    budgets = {**manifest_budgets, **report_budgets}
    return {
        "vramTiles": _number(budgets, "vram_tiles", "vramTiles"),
        "palettes": _number(budgets, "palettes"),
        "sprites": _number(budgets, "sprites"),
        "spritesPerScanline": _number(
            budgets, "sprites_per_scanline", "spritesPerScanline"),
        "frameBudgetUs": DEFAULT_FRAME_BUDGET_US,
        "dirtyDisplayRatio": 0.5,
    }


def _sprite_metrics(frame: Mapping[str, Any]) -> tuple[int, int, set[int], set[int]]:
    raw = frame.get("sprites")
    if raw is None:
        visible = int(_number(frame, "spritesVisible", "visibleSprites") or 0)
        scanline: Any = frame.get(
            "spritesPerScanline", frame.get("maximumSpritesPerScanline", 0)
        )
        if isinstance(scanline, Sequence) and not isinstance(scanline, (str, bytes)):
            if not all(isinstance(value, int) and not isinstance(value, bool)
                       for value in scanline):
                raise ProfileError("spritesPerScanline values must be integers")
            scanline = max((int(value) for value in scanline), default=0)
        elif not isinstance(scanline, (int, float)) or isinstance(scanline, bool):
            raise ProfileError("spritesPerScanline must be a number or integer array")
        return visible, int(scanline), set(), set()
    if not isinstance(raw, list):
        raise ProfileError("frame sprites must be an array")
    counts = [0] * DISPLAY_HEIGHT
    visible = 0
    tiles: set[int] = set()
    palettes: set[int] = set()
    for sprite in raw:
        if not isinstance(sprite, Mapping):
            raise ProfileError("sprites must be objects")
        if sprite.get("visible", True) is False:
            continue
        visible += 1
        y = int(sprite.get("y", 0))
        height = max(1, int(sprite.get("height", 8)))
        for scanline in range(max(0, y), min(DISPLAY_HEIGHT, y + height)):
            counts[scanline] += 1
        if isinstance(sprite.get("tile"), int):
            tiles.add(int(sprite["tile"]))
        if isinstance(sprite.get("palette"), int):
            palettes.add(int(sprite["palette"]))
    return visible, max(counts, default=0), tiles, palettes


def _declared_set(frame: Mapping[str, Any], key: str) -> set[int]:
    raw = frame.get(key)
    if raw is None:
        return set()
    if not isinstance(raw, list) or not all(isinstance(value, int) for value in raw):
        raise ProfileError(f"frame {key} must be an integer array")
    return {int(value) for value in raw}


def _dirty_pixels(frame: Mapping[str, Any]) -> int:
    declared = _number(frame, "dirtyPixels")
    if declared is not None:
        return max(0, min(DISPLAY_WIDTH * DISPLAY_HEIGHT, int(declared)))
    regions = frame.get("dirtyRegions", [])
    if not isinstance(regions, list):
        raise ProfileError("dirtyRegions must be an array")
    pixels: set[tuple[int, int]] = set()
    for region in regions:
        if not isinstance(region, Mapping):
            raise ProfileError("dirty regions must be objects")
        x = int(region.get("x", 0))
        y = int(region.get("y", 0))
        width = max(0, int(region.get("width", 0)))
        height = max(0, int(region.get("height", 0)))
        for py in range(max(0, y), min(DISPLAY_HEIGHT, y + height)):
            for px in range(max(0, x), min(DISPLAY_WIDTH, x + width)):
                pixels.add((px, py))
    return len(pixels)


def _finding(code: str, message: str, *, severity: str, actual: int | float,
             limit: int | float, frame: int | str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "severity": severity,
        "code": code,
        "message": message,
        "actual": actual,
        "limit": limit,
    }
    if frame is not None:
        result["frameIndex"] = frame
    return result


def profile_resources(*, manifest: Any = None, report: Mapping[str, Any] | None = None,
                      trace: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
                      dirty_ratio_warning: float = 0.5,
                      frame_budget_us: float = DEFAULT_FRAME_BUDGET_US,
                      ) -> ProfileReport:
    if not 0.0 <= dirty_ratio_warning <= 1.0:
        raise ProfileError("dirty_ratio_warning must be between 0 and 1")
    if frame_budget_us <= 0:
        raise ProfileError("frame_budget_us must be positive")
    resource_report = report or {}
    limits = _limit_sources(manifest, resource_report)
    limits["dirtyDisplayRatio"] = dirty_ratio_warning
    limits["frameBudgetUs"] = frame_budget_us
    if trace is None:
        frames: list[Mapping[str, Any]] = []
    elif isinstance(trace, Mapping):
        raw_frames = trace.get("frames", [])
        if not isinstance(raw_frames, list):
            raise ProfileError("trace frames must be an array")
        frames = raw_frames
    else:
        frames = list(trace)
    findings: list[dict[str, Any]] = []
    peaks: dict[str, int | float] = {
        "vramTiles": 0,
        "palettes": 0,
        "sprites": 0,
        "spritesPerScanline": 0,
        "dirtyPixels": 0,
        "dirtyDisplayRatio": 0.0,
        "frameTimeUs": 0.0,
    }

    for position, frame in enumerate(frames):
        if not isinstance(frame, Mapping):
            raise ProfileError("trace frames must be objects")
        frame_index = frame.get("frameIndex", position)
        sprites, scanline, sprite_tiles, sprite_palettes = _sprite_metrics(frame)
        tiles = _declared_set(frame, "tiles") | sprite_tiles
        palettes = _declared_set(frame, "palettes") | sprite_palettes
        tile_count = int(_number(frame, "tilesUsed", "vramTiles") or len(tiles))
        palette_count = int(_number(frame, "palettesUsed") or len(palettes))
        dirty = _dirty_pixels(frame)
        dirty_ratio = dirty / (DISPLAY_WIDTH * DISPLAY_HEIGHT)
        frame_time = float(_number(frame, "frameTimeUs") or 0.0)
        values: dict[str, int | float] = {
            "vramTiles": tile_count,
            "palettes": palette_count,
            "sprites": sprites,
            "spritesPerScanline": scanline,
            "dirtyPixels": dirty,
            "dirtyDisplayRatio": dirty_ratio,
            "frameTimeUs": frame_time,
        }
        for key, value in values.items():
            peaks[key] = max(peaks[key], value)
        for key, code, label in (
            ("vramTiles", "vram-tile-budget", "VRAM tiles"),
            ("palettes", "palette-budget", "palettes"),
            ("sprites", "sprite-budget", "visible sprites"),
            ("spritesPerScanline", "sprite-scanline-budget", "sprites on one scanline"),
        ):
            limit = limits[key]
            if limit is not None and values[key] > limit:
                findings.append(_finding(
                    code, f"{label} exceed the declared budget", severity="error",
                    actual=values[key], limit=limit, frame=frame_index,
                ))
        if dirty_ratio > dirty_ratio_warning:
            findings.append(_finding(
                "dirty-region-pressure", "dirty presentation covers too much of the display",
                severity="warning", actual=round(dirty_ratio, 9),
                limit=dirty_ratio_warning, frame=frame_index,
            ))
        if frame_time > frame_budget_us:
            findings.append(_finding(
                "frame-time-budget", "frame preparation exceeds the native refresh budget",
                severity="error", actual=frame_time, limit=frame_budget_us,
                frame=frame_index,
            ))

    scene_usage = resource_report.get("sceneUsage", [])
    if not isinstance(scene_usage, list):
        raise ProfileError("resource report sceneUsage must be an array")
    for scene in scene_usage:
        if not isinstance(scene, Mapping):
            raise ProfileError("sceneUsage entries must be objects")
        for key, report_key, code in (
            ("vramTiles", "vramTiles", "vram-tile-budget"),
            ("palettes", "palettes", "palette-budget"),
        ):
            actual = _number(scene, report_key)
            limit = limits[key]
            if actual is not None:
                peaks[key] = max(peaks[key], actual)
                if limit is not None and actual > limit:
                    findings.append(_finding(
                        code, f"scene {scene.get('scene', '?')} exceeds its declared budget",
                        severity="error", actual=actual, limit=limit,
                        frame=f"scene:{scene.get('scene', '?')}",
                    ))
    peaks["dirtyDisplayRatio"] = round(float(peaks["dirtyDisplayRatio"]), 9)
    peaks["frameTimeUs"] = round(float(peaks["frameTimeUs"]), 6)
    return ProfileReport(limits, peaks, tuple(findings), len(frames))
