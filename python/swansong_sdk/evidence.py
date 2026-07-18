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
    audio_signal_floor: float = 0.0
    stereo_balance_delta: float | None = None
    cue_onset_delta_ms: float | None = None
    silent_frame_ratio_increase: float | None = None
    internal_silence_increase_ms: float | None = None
    clipped_sample_ratio_increase: float | None = None
    loop_seam_delta_increase: float | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.pixel_channel_tolerance <= 255:
            raise EvidenceError("pixel_channel_tolerance must be 0..255")
        if self.pcm_sample_tolerance < 0:
            raise EvidenceError("pcm_sample_tolerance must be nonnegative")
        for name in ("changed_pixel_ratio", "changed_sample_ratio",
                     "normalized_rms_delta", "audio_signal_floor"):
            value = getattr(self, name)
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise EvidenceError(f"{name} must be between 0 and 1")

        optional_ranges = {
            "stereo_balance_delta": 2.0,
            "silent_frame_ratio_increase": 1.0,
            "clipped_sample_ratio_increase": 1.0,
            "loop_seam_delta_increase": 2.0,
        }
        for name, maximum in optional_ranges.items():
            value = getattr(self, name)
            if value is not None and (
                    not math.isfinite(value) or not 0.0 <= value <= maximum):
                raise EvidenceError(f"{name} must be between 0 and {maximum:g}")
        for name in ("cue_onset_delta_ms", "internal_silence_increase_ms"):
            value = getattr(self, name)
            if value is not None and (not math.isfinite(value) or value < 0.0):
                raise EvidenceError(f"{name} must be nonnegative")

    def to_dict(self) -> dict[str, int | float | None]:
        return {
            "pixelChannelTolerance": self.pixel_channel_tolerance,
            "changedPixelRatio": self.changed_pixel_ratio,
            "pcmSampleTolerance": self.pcm_sample_tolerance,
            "changedSampleRatio": self.changed_sample_ratio,
            "normalizedRmsDelta": self.normalized_rms_delta,
            "audioSignalFloor": self.audio_signal_floor,
            "stereoBalanceDelta": self.stereo_balance_delta,
            "cueOnsetDeltaMs": self.cue_onset_delta_ms,
            "silentFrameRatioIncrease": self.silent_frame_ratio_increase,
            "internalSilenceIncreaseMs": self.internal_silence_increase_ms,
            "clippedSampleRatioIncrease": self.clipped_sample_ratio_increase,
            "loopSeamDeltaIncrease": self.loop_seam_delta_increase,
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

    def metadata(self, signal_floor: float = 0.0) -> dict[str, Any]:
        floor_amplitude = math.floor(signal_floor * self.full_scale)
        channel_energy = [0] * self.channels
        channel_peak = [0] * self.channels
        clipped_by_channel = [0] * self.channels
        first_sample = [0] * self.channels
        last_sample = [0] * self.channels
        clipped = 0
        audible_frames = 0
        first_audible: int | None = None
        last_audible: int | None = None
        current_silence = 0
        maximum_internal_silence = 0

        for frame in range(self.frame_count):
            audible = False
            base = frame * self.channels
            for channel in range(self.channels):
                sample = self.samples[base + channel]
                if frame == 0:
                    first_sample[channel] = sample
                last_sample[channel] = sample
                magnitude = abs(sample)
                channel_energy[channel] += sample * sample
                channel_peak[channel] = max(channel_peak[channel], magnitude)
                if sample <= -self.full_scale or sample >= self.full_scale - 1:
                    clipped += 1
                    clipped_by_channel[channel] += 1
                if magnitude > floor_amplitude:
                    audible = True
            if audible:
                audible_frames += 1
                if first_audible is None:
                    first_audible = frame
                else:
                    maximum_internal_silence = max(
                        maximum_internal_silence, current_silence
                    )
                last_audible = frame
                current_silence = 0
            else:
                current_silence += 1

        silent_frames = self.frame_count - audible_frames
        leading_silence = (
            first_audible if first_audible is not None else self.frame_count
        )
        trailing_silence = (
            self.frame_count - last_audible - 1
            if last_audible is not None else self.frame_count
        )
        loop_seams = [
            abs(last_sample[channel] - first_sample[channel]) / self.full_scale
            if self.frame_count else 0.0
            for channel in range(self.channels)
        ]
        channel_metrics = []
        for channel in range(self.channels):
            rms = (
                math.sqrt(channel_energy[channel] / self.frame_count)
                if self.frame_count else 0.0
            )
            channel_metrics.append({
                "channelIndex": channel,
                "peakAmplitude": channel_peak[channel],
                "normalizedPeak": round(channel_peak[channel] / self.full_scale, 9),
                "rmsAmplitude": round(rms, 9),
                "normalizedRms": round(rms / self.full_scale, 9),
                "clippedSamples": clipped_by_channel[channel],
                "clippedSampleRatio": round(
                    clipped_by_channel[channel] / self.frame_count, 9
                ) if self.frame_count else 0.0,
            })

        stereo = None
        if self.channels == 2:
            total_energy = channel_energy[0] + channel_energy[1]
            balance = (
                (channel_energy[1] - channel_energy[0]) / total_energy
                if total_energy else 0.0
            )
            stereo = {
                "leftEnergy": channel_energy[0],
                "rightEnergy": channel_energy[1],
                "balance": round(balance, 9),
                "dominantChannel": (
                    "right" if balance > 0.0 else "left" if balance < 0.0 else "center"
                ),
            }

        metadata = {
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
            "audioSignalFloor": signal_floor,
            "audioSignalFloorAmplitude": floor_amplitude,
            "audibleFrames": audible_frames,
            "silentFrames": silent_frames,
            "silentFrameRatio": round(
                silent_frames / self.frame_count, 9
            ) if self.frame_count else 0.0,
            "cueOnsetFrame": first_audible,
            "cueOnsetMs": (
                round(first_audible * 1000 / self.frame_rate, 6)
                if first_audible is not None else None
            ),
            "leadingSilenceMs": round(leading_silence * 1000 / self.frame_rate, 6),
            "trailingSilenceMs": round(trailing_silence * 1000 / self.frame_rate, 6),
            "maximumInternalSilenceFrames": maximum_internal_silence,
            "maximumInternalSilenceMs": round(
                maximum_internal_silence * 1000 / self.frame_rate, 6
            ),
            "clippedSamples": clipped,
            "clippedSampleRatio": round(
                clipped / len(self.samples), 9
            ) if self.samples else 0.0,
            "loopSeamByChannel": [round(value, 9) for value in loop_seams],
            "maximumLoopSeam": round(max(loop_seams, default=0.0), 9),
            "channelMetrics": channel_metrics,
            "stereo": stereo,
        }
        return metadata


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


def validate_wav(path: str | Path, *, signal_floor: float = 0.0) -> dict[str, Any]:
    """Fully decode PCM evidence and return deterministic format metrics."""
    if not math.isfinite(signal_floor) or not 0.0 <= signal_floor <= 1.0:
        raise EvidenceError("signal_floor must be between 0 and 1")
    return _read_wave(Path(path)).metadata(signal_floor)


def _regression_check(*, threshold: float | None, before: Any, after: Any,
                      delta: float | None, regression: bool,
                      applicable: bool = True) -> dict[str, Any]:
    return {
        "enabled": threshold is not None,
        "applicable": applicable,
        "before": before,
        "after": after,
        "delta": round(delta, 9) if delta is not None else None,
        "threshold": threshold,
        "regression": threshold is not None and applicable and regression,
    }


def _audio_regressions(before: Mapping[str, Any], after: Mapping[str, Any],
                       limits: EvidenceThresholds) -> dict[str, Any]:
    before_stereo = before.get("stereo")
    after_stereo = after.get("stereo")
    stereo_applicable = isinstance(before_stereo, Mapping) and isinstance(
        after_stereo, Mapping
    )
    stereo_delta = (
        abs(float(after_stereo["balance"]) - float(before_stereo["balance"]))
        if stereo_applicable else None
    )

    before_onset = before.get("cueOnsetMs")
    after_onset = after.get("cueOnsetMs")
    cue_applicable = before_onset is not None
    cue_delta = (
        abs(float(after_onset) - float(before_onset))
        if before_onset is not None and after_onset is not None else None
    )
    cue_regression = (
        after_onset is None or
        (cue_delta is not None and limits.cue_onset_delta_ms is not None and
         cue_delta > limits.cue_onset_delta_ms)
    )

    silence_delta = max(
        0.0,
        float(after["silentFrameRatio"]) - float(before["silentFrameRatio"]),
    )
    internal_silence_delta = max(
        0.0,
        float(after["maximumInternalSilenceMs"]) -
        float(before["maximumInternalSilenceMs"]),
    )
    clipping_delta = max(
        0.0,
        float(after["clippedSampleRatio"]) - float(before["clippedSampleRatio"]),
    )
    seam_delta = max(
        0.0,
        float(after["maximumLoopSeam"]) - float(before["maximumLoopSeam"]),
    )

    checks = {
        "stereoBalance": _regression_check(
            threshold=limits.stereo_balance_delta,
            before=before_stereo.get("balance") if stereo_applicable else None,
            after=after_stereo.get("balance") if stereo_applicable else None,
            delta=stereo_delta,
            regression=(
                stereo_delta is not None and limits.stereo_balance_delta is not None and
                stereo_delta > limits.stereo_balance_delta
            ),
            applicable=stereo_applicable,
        ),
        "cueOnset": _regression_check(
            threshold=limits.cue_onset_delta_ms,
            before=before_onset,
            after=after_onset,
            delta=cue_delta,
            regression=cue_regression,
            applicable=cue_applicable,
        ),
        "silentFrames": _regression_check(
            threshold=limits.silent_frame_ratio_increase,
            before=before["silentFrameRatio"],
            after=after["silentFrameRatio"],
            delta=silence_delta,
            regression=(
                limits.silent_frame_ratio_increase is not None and
                silence_delta > limits.silent_frame_ratio_increase
            ),
        ),
        "internalSilence": _regression_check(
            threshold=limits.internal_silence_increase_ms,
            before=before["maximumInternalSilenceMs"],
            after=after["maximumInternalSilenceMs"],
            delta=internal_silence_delta,
            regression=(
                limits.internal_silence_increase_ms is not None and
                internal_silence_delta > limits.internal_silence_increase_ms
            ),
        ),
        "clipping": _regression_check(
            threshold=limits.clipped_sample_ratio_increase,
            before=before["clippedSampleRatio"],
            after=after["clippedSampleRatio"],
            delta=clipping_delta,
            regression=(
                limits.clipped_sample_ratio_increase is not None and
                clipping_delta > limits.clipped_sample_ratio_increase
            ),
        ),
        "loopSeam": _regression_check(
            threshold=limits.loop_seam_delta_increase,
            before=before["maximumLoopSeam"],
            after=after["maximumLoopSeam"],
            delta=seam_delta,
            regression=(
                limits.loop_seam_delta_increase is not None and
                seam_delta > limits.loop_seam_delta_increase
            ),
        ),
    }
    return {
        "configured": any(item["enabled"] for item in checks.values()),
        "detected": any(item["regression"] for item in checks.values()),
        "checks": checks,
    }


def diff_wav(before: str | Path, after: str | Path,
             thresholds: EvidenceThresholds | None = None) -> dict[str, Any]:
    limits = thresholds or EvidenceThresholds()
    left = _read_wave(Path(before))
    right = _read_wave(Path(after))
    before_metadata = left.metadata(limits.audio_signal_floor)
    after_metadata = right.metadata(limits.audio_signal_floor)
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
    regressions = _audio_regressions(before_metadata, after_metadata, limits)
    return {
        "schema": "swansong-wav-diff-v1",
        "before": before_metadata,
        "after": after_metadata,
        "formatMatch": format_match,
        "frameCountMatch": left.frame_count == right.frame_count,
        "changedSamples": changed,
        "changedSampleRatio": round(ratio, 9),
        "maximumSampleDelta": maximum_delta,
        "meanAbsoluteSampleDelta": round(absolute_delta / total, 9) if total else 0.0,
        "normalizedRmsDelta": round(rms_delta, 9),
        "regressions": regressions,
        "meaningfulDifference": (
            not format_match or left.frame_count != right.frame_count or
            ratio > limits.changed_sample_ratio or
            rms_delta > limits.normalized_rms_delta or regressions["detected"]
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
