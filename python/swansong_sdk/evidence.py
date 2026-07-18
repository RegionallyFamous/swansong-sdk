"""Deterministic visual, audio, and structured SwanSong evidence comparison."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import wave
from typing import Any, Mapping

from .png2bpp import Image, read_png


SCHEMA = "swansong-evidence-diff-v1"


class EvidenceError(ValueError):
    pass


@dataclass(frozen=True)
class EvidenceThresholds:
    pixel_channel_tolerance: int = 0
    changed_pixel_ratio: float = 0.0
    pcm_sample_tolerance: int = 0
    changed_sample_ratio: float = 0.0
    normalized_rms_delta: float = 0.0

    def __post_init__(self) -> None:
        if not 0 <= self.pixel_channel_tolerance <= 255:
            raise EvidenceError("pixel_channel_tolerance must be 0..255")
        if self.pcm_sample_tolerance < 0:
            raise EvidenceError("pcm_sample_tolerance must be nonnegative")
        for name in ("changed_pixel_ratio", "changed_sample_ratio",
                     "normalized_rms_delta"):
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise EvidenceError(f"{name} must be between 0 and 1")

    def to_dict(self) -> dict[str, int | float]:
        return {
            "pixelChannelTolerance": self.pixel_channel_tolerance,
            "changedPixelRatio": self.changed_pixel_ratio,
            "pcmSampleTolerance": self.pcm_sample_tolerance,
            "changedSampleRatio": self.changed_sample_ratio,
            "normalizedRmsDelta": self.normalized_rms_delta,
        }


@dataclass(frozen=True)
class EvidenceDiff:
    png: Mapping[str, Any] | None
    wav: Mapping[str, Any] | None
    metadata: Mapping[str, Any] | None
    thresholds: EvidenceThresholds

    @property
    def meaningful_difference(self) -> bool:
        return any(
            part is not None and bool(part.get("meaningfulDifference"))
            for part in (self.png, self.wav, self.metadata)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "meaningfulDifference": self.meaningful_difference,
            "thresholds": self.thresholds.to_dict(),
            "png": dict(self.png) if self.png is not None else None,
            "wav": dict(self.wav) if self.wav is not None else None,
            "metadata": dict(self.metadata) if self.metadata is not None else None,
        }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _image_metadata(path: Path, image: Image) -> dict[str, Any]:
    colors = set(image.pixels)
    return {
        "sha256": _sha256(path),
        "width": image.width,
        "height": image.height,
        "pixelCount": image.width * image.height,
        "uniqueRgbaColors": len(colors),
        "hasTransparency": any(color[3] != 255 for color in colors),
    }


def diff_png(before: str | Path, after: str | Path,
             thresholds: EvidenceThresholds | None = None) -> dict[str, Any]:
    limits = thresholds or EvidenceThresholds()
    before_path = Path(before)
    after_path = Path(after)
    left = read_png(before_path)
    right = read_png(after_path)
    width = max(left.width, right.width)
    height = max(left.height, right.height)
    changed = 0
    channel_delta = 0
    maximum_delta = 0
    bounds: list[int] | None = None
    for y in range(height):
        for x in range(width):
            if x < left.width and y < left.height:
                a = left.pixels[y * left.width + x]
            else:
                a = (0, 0, 0, 0)
            if x < right.width and y < right.height:
                b = right.pixels[y * right.width + x]
            else:
                b = (0, 0, 0, 0)
            deltas = tuple(abs(a[index] - b[index]) for index in range(4))
            local_maximum = max(deltas)
            channel_delta += sum(deltas)
            maximum_delta = max(maximum_delta, local_maximum)
            if local_maximum > limits.pixel_channel_tolerance:
                changed += 1
                if bounds is None:
                    bounds = [x, y, x, y]
                else:
                    bounds[0] = min(bounds[0], x)
                    bounds[1] = min(bounds[1], y)
                    bounds[2] = max(bounds[2], x)
                    bounds[3] = max(bounds[3], y)
    total = width * height
    ratio = changed / total if total else 0.0
    bbox = None if bounds is None else {
        "x": bounds[0], "y": bounds[1],
        "width": bounds[2] - bounds[0] + 1,
        "height": bounds[3] - bounds[1] + 1,
    }
    return {
        "schema": "swansong-png-diff-v1",
        "before": _image_metadata(before_path, left),
        "after": _image_metadata(after_path, right),
        "dimensionsMatch": (left.width, left.height) == (right.width, right.height),
        "changedPixels": changed,
        "changedPixelRatio": round(ratio, 9),
        "changedBounds": bbox,
        "maximumChannelDelta": maximum_delta,
        "meanAbsoluteChannelDelta": round(channel_delta / (total * 4), 9) if total else 0.0,
        "meaningfulDifference": (
            (left.width, left.height) != (right.width, right.height) or
            ratio > limits.changed_pixel_ratio
        ),
    }


@dataclass(frozen=True)
class _WaveData:
    channels: int
    sample_width: int
    frame_rate: int
    frame_count: int
    samples: tuple[int, ...]
    sha256: str

    @property
    def maximum_amplitude(self) -> int:
        return max((abs(value) for value in self.samples), default=0)

    @property
    def rms(self) -> float:
        if not self.samples:
            return 0.0
        return math.sqrt(sum(value * value for value in self.samples) / len(self.samples))

    @property
    def full_scale(self) -> int:
        return 128 if self.sample_width == 1 else 1 << (self.sample_width * 8 - 1)

    def metadata(self) -> dict[str, Any]:
        return {
            "sha256": self.sha256,
            "channels": self.channels,
            "sampleWidthBytes": self.sample_width,
            "sampleRate": self.frame_rate,
            "frameCount": self.frame_count,
            "durationMs": round(self.frame_count * 1000 / self.frame_rate, 6),
            "peakAmplitude": self.maximum_amplitude,
            "normalizedPeak": round(self.maximum_amplitude / self.full_scale, 9),
            "rmsAmplitude": round(self.rms, 9),
            "normalizedRms": round(self.rms / self.full_scale, 9),
        }


def _decode_samples(payload: bytes, width: int) -> tuple[int, ...]:
    if width not in {1, 2, 3, 4}:
        raise EvidenceError(f"unsupported PCM sample width {width}")
    if len(payload) % width:
        raise EvidenceError("PCM payload is not sample aligned")
    samples: list[int] = []
    for offset in range(0, len(payload), width):
        raw = payload[offset:offset + width]
        if width == 1:
            samples.append(raw[0] - 128)
        else:
            samples.append(int.from_bytes(raw, "little", signed=True))
    return tuple(samples)


def _read_wave(path: Path) -> _WaveData:
    try:
        with wave.open(str(path), "rb") as source:
            if source.getcomptype() != "NONE":
                raise EvidenceError("only uncompressed PCM WAV evidence is supported")
            channels = source.getnchannels()
            width = source.getsampwidth()
            rate = source.getframerate()
            frames = source.getnframes()
            payload = source.readframes(frames)
    except (wave.Error, EOFError) as exc:
        raise EvidenceError(f"invalid WAV evidence {path}: {exc}") from exc
    expected_bytes = frames * channels * width
    if channels <= 0 or rate <= 0 or len(payload) != expected_bytes:
        raise EvidenceError(f"invalid or truncated WAV evidence {path}")
    return _WaveData(channels, width, rate, frames, _decode_samples(payload, width),
                     _sha256(path))


def validate_wav(path: str | Path) -> dict[str, Any]:
    """Fully decode PCM evidence and return deterministic format metrics."""
    return _read_wave(Path(path)).metadata()


def diff_wav(before: str | Path, after: str | Path,
             thresholds: EvidenceThresholds | None = None) -> dict[str, Any]:
    limits = thresholds or EvidenceThresholds()
    left = _read_wave(Path(before))
    right = _read_wave(Path(after))
    format_match = (left.channels, left.sample_width, left.frame_rate) == (
        right.channels, right.sample_width, right.frame_rate)
    total = max(len(left.samples), len(right.samples))
    changed = 0
    absolute_delta = 0
    maximum_delta = 0
    for index in range(total):
        a = left.samples[index] if index < len(left.samples) else 0
        b = right.samples[index] if index < len(right.samples) else 0
        delta = abs(a - b)
        absolute_delta += delta
        maximum_delta = max(maximum_delta, delta)
        if delta > limits.pcm_sample_tolerance:
            changed += 1
    ratio = changed / total if total else 0.0
    rms_delta = abs(
        left.rms / left.full_scale - right.rms / right.full_scale
    )
    return {
        "schema": "swansong-wav-diff-v1",
        "before": left.metadata(),
        "after": right.metadata(),
        "formatMatch": format_match,
        "frameCountMatch": left.frame_count == right.frame_count,
        "changedSamples": changed,
        "changedSampleRatio": round(ratio, 9),
        "maximumSampleDelta": maximum_delta,
        "meanAbsoluteSampleDelta": round(absolute_delta / total, 9) if total else 0.0,
        "normalizedRmsDelta": round(rms_delta, 9),
        "meaningfulDifference": (
            not format_match or left.frame_count != right.frame_count or
            ratio > limits.changed_sample_ratio or
            rms_delta > limits.normalized_rms_delta
        ),
    }


def _flatten(value: Any, prefix: str = "$") -> dict[str, Any]:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {
            prefix: {"container": "object", "length": len(value)},
        }
        for key in sorted(value, key=str):
            result.update(_flatten(value[key], f"{prefix}.{key}"))
        return result
    if isinstance(value, list):
        result = {
            prefix: {"container": "array", "length": len(value)},
        }
        for index, item in enumerate(value):
            result.update(_flatten(item, f"{prefix}[{index}]"))
        return result
    return {prefix: value}


def diff_metadata(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    left = _flatten(before)
    right = _flatten(after)
    changes = [
        {"path": path, "before": left.get(path), "after": right.get(path)}
        for path in sorted(set(left) | set(right))
        if left.get(path) != right.get(path) or (path in left) != (path in right)
    ]
    return {
        "schema": "swansong-structured-evidence-diff-v1",
        "beforeSha256": hashlib.sha256(
            json.dumps(before, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "afterSha256": hashlib.sha256(
            json.dumps(after, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "changes": changes,
        "meaningfulDifference": bool(changes),
    }


def diff_evidence(*, before_png: str | Path | None = None,
                  after_png: str | Path | None = None,
                  before_wav: str | Path | None = None,
                  after_wav: str | Path | None = None,
                  before_metadata: Mapping[str, Any] | None = None,
                  after_metadata: Mapping[str, Any] | None = None,
                  thresholds: EvidenceThresholds | None = None) -> EvidenceDiff:
    limits = thresholds or EvidenceThresholds()
    if (before_png is None) != (after_png is None):
        raise EvidenceError("PNG evidence must be provided as a before/after pair")
    if (before_wav is None) != (after_wav is None):
        raise EvidenceError("WAV evidence must be provided as a before/after pair")
    if (before_metadata is None) != (after_metadata is None):
        raise EvidenceError("structured evidence must be provided as a pair")
    if before_png is None and before_wav is None and before_metadata is None:
        raise EvidenceError("at least one evidence pair is required")
    png = diff_png(before_png, after_png, limits) if before_png is not None else None
    wav = diff_wav(before_wav, after_wav, limits) if before_wav is not None else None
    metadata = (
        diff_metadata(before_metadata, after_metadata)
        if before_metadata is not None and after_metadata is not None else None
    )
    return EvidenceDiff(png, wav, metadata, limits)
