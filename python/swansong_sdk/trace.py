"""Deterministic SDK frame traces and scenario outcome contracts.

The binary reader matches ``swan_debug_frame_trace_serialize`` exactly.  It
does not execute cartridges; trace bytes and audio observations must come from
the SwanSong-only play path.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import struct
from typing import Any, Mapping


TRACE_SCHEMA = "swan-deterministic-trace-v1"
OUTCOME_CONTRACT_SCHEMA = "swan-scenario-outcome-contract-v1"
OUTCOME_REPORT_SCHEMA = "swan-scenario-outcome-report-v1"
BINARY_MAGIC = b"SWTR"
BINARY_VERSION = 1
BINARY_HEADER_SIZE = 32
BINARY_RECORD_SIZE = 42
_RECORD = struct.Struct("<III10H10B")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FRAME_FLAG_MASK = 0x7F
_TRANSITION_FLAG = 1 << 3
_RESET_FLAG = 1 << 4
_FNV1A_OFFSET = 2166136261
_FNV1A_PRIME = 16777619


class TraceError(ValueError):
    pass


def _integer(value: object, name: str, low: int, high: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not low <= value <= high:
        raise TraceError(f"{name} must be an integer from {low} through {high}")
    return value


@dataclass(frozen=True)
class TraceFrame:
    boot_tick: int
    session_tick: int
    state_hash: int
    input_held: int
    input_pressed: int
    input_released: int
    actions_held: int
    actions_pressed: int
    actions_released: int
    progress: int
    audio_marker: int
    transition_argument: int
    reset_count: int
    scene: int
    transition_from: int
    transition_to: int
    ending: int
    flags: int
    sprites_visible: int
    audio_voice_mask: int
    audio_sfx_mask: int
    maximum_sprites_on_scanline: int
    panic_code: int

    @classmethod
    def from_bytes(cls, payload: bytes) -> "TraceFrame":
        if len(payload) != BINARY_RECORD_SIZE:
            raise TraceError(f"trace record must contain exactly {BINARY_RECORD_SIZE} bytes")
        return cls(*_RECORD.unpack(payload))

    @classmethod
    def from_dict(cls, value: Mapping[str, Any], *, index: int) -> "TraceFrame":
        names = {
            "bootTick": ("boot_tick", 0xFFFFFFFF),
            "sessionTick": ("session_tick", 0xFFFFFFFF),
            "stateHash": ("state_hash", 0xFFFFFFFF),
            "inputHeld": ("input_held", 0xFFFF),
            "inputPressed": ("input_pressed", 0xFFFF),
            "inputReleased": ("input_released", 0xFFFF),
            "actionsHeld": ("actions_held", 0xFFFF),
            "actionsPressed": ("actions_pressed", 0xFFFF),
            "actionsReleased": ("actions_released", 0xFFFF),
            "progress": ("progress", 0xFFFF),
            "audioMarker": ("audio_marker", 0xFFFF),
            "transitionArgument": ("transition_argument", 0xFFFF),
            "resetCount": ("reset_count", 0xFFFF),
            "scene": ("scene", 0xFF),
            "transitionFrom": ("transition_from", 0xFF),
            "transitionTo": ("transition_to", 0xFF),
            "ending": ("ending", 0xFF),
            "flags": ("flags", 0xFF),
            "spritesVisible": ("sprites_visible", 0xFF),
            "audioVoiceMask": ("audio_voice_mask", 0xFF),
            "audioSfxMask": ("audio_sfx_mask", 0xFF),
            "maximumSpritesOnScanline": ("maximum_sprites_on_scanline", 0xFF),
            "panicCode": ("panic_code", 0xFF),
        }
        if set(value) != set(names):
            missing = sorted(set(names) - set(value))
            extra = sorted(set(value) - set(names))
            raise TraceError(f"trace frame {index} fields differ; missing={missing}, extra={extra}")
        checked = {
            attribute: _integer(value[key], f"frames[{index}].{key}", 0, maximum)
            for key, (attribute, maximum) in names.items()
        }
        return cls(**checked)

    def to_bytes(self) -> bytes:
        return _RECORD.pack(
            self.boot_tick, self.session_tick, self.state_hash,
            self.input_held, self.input_pressed, self.input_released,
            self.actions_held, self.actions_pressed, self.actions_released,
            self.progress, self.audio_marker, self.transition_argument,
            self.reset_count, self.scene, self.transition_from,
            self.transition_to, self.ending, self.flags,
            self.sprites_visible, self.audio_voice_mask, self.audio_sfx_mask,
            self.maximum_sprites_on_scanline, self.panic_code,
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "bootTick": self.boot_tick,
            "sessionTick": self.session_tick,
            "stateHash": self.state_hash,
            "inputHeld": self.input_held,
            "inputPressed": self.input_pressed,
            "inputReleased": self.input_released,
            "actionsHeld": self.actions_held,
            "actionsPressed": self.actions_pressed,
            "actionsReleased": self.actions_released,
            "progress": self.progress,
            "audioMarker": self.audio_marker,
            "transitionArgument": self.transition_argument,
            "resetCount": self.reset_count,
            "scene": self.scene,
            "transitionFrom": self.transition_from,
            "transitionTo": self.transition_to,
            "ending": self.ending,
            "flags": self.flags,
            "spritesVisible": self.sprites_visible,
            "audioVoiceMask": self.audio_voice_mask,
            "audioSfxMask": self.audio_sfx_mask,
            "maximumSpritesOnScanline": self.maximum_sprites_on_scanline,
            "panicCode": self.panic_code,
        }


@dataclass(frozen=True)
class TraceCapture:
    frames: tuple[TraceFrame, ...]
    dropped_frame_count: int = 0
    reset_count: int = 0
    total_frame_count: int = 0
    stream_hash: int = _FNV1A_OFFSET
    audio_marker_union: int = 0
    transition_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": TRACE_SCHEMA,
            "binaryVersion": BINARY_VERSION,
            "recordSize": BINARY_RECORD_SIZE,
            "droppedFrameCount": self.dropped_frame_count,
            "resetCount": self.reset_count,
            "totalFrameCount": self.total_frame_count,
            "streamHashFNV1a32": self.stream_hash,
            "audioMarkerUnion": self.audio_marker_union,
            "transitionCount": self.transition_count,
            "frames": [frame.to_dict() for frame in self.frames],
        }


def _stream_hash(frames: tuple[TraceFrame, ...]) -> int:
    result = _FNV1A_OFFSET
    for frame in frames:
        for byte in frame.to_bytes():
            result = ((result ^ byte) * _FNV1A_PRIME) & 0xFFFFFFFF
    return result


def _marker_union(frames: tuple[TraceFrame, ...]) -> int:
    result = 0
    for frame in frames:
        result |= frame.audio_marker
    return result


def capture_from_frames(frames: tuple[TraceFrame, ...], *, reset_count: int = 0) -> TraceCapture:
    """Build an internally consistent complete capture from ordered frames."""
    return TraceCapture(
        frames=frames,
        reset_count=reset_count,
        total_frame_count=len(frames),
        stream_hash=_stream_hash(frames),
        audio_marker_union=_marker_union(frames),
        transition_count=sum(bool(frame.flags & _TRANSITION_FLAG) for frame in frames),
    )


def _validate_capture(capture: TraceCapture) -> TraceCapture:
    _integer(capture.dropped_frame_count, "droppedFrameCount", 0, 0xFFFFFFFF)
    _integer(capture.reset_count, "resetCount", 0, 0xFFFF)
    _integer(capture.total_frame_count, "totalFrameCount", 0, 0xFFFFFFFF)
    _integer(capture.stream_hash, "streamHashFNV1a32", 0, 0xFFFFFFFF)
    _integer(capture.audio_marker_union, "audioMarkerUnion", 0, 0xFFFF)
    _integer(capture.transition_count, "transitionCount", 0, 0xFFFF)
    if len(capture.frames) > 0xFF:
        raise TraceError("trace contains more than 255 bounded runtime records")
    if capture.total_frame_count != len(capture.frames) + capture.dropped_frame_count:
        raise TraceError("totalFrameCount must equal retained plus dropped records")
    previous_boot = -1
    previous_reset = 0
    for index, frame in enumerate(capture.frames):
        TraceFrame.from_dict(frame.to_dict(), index=index)
        if frame.boot_tick <= previous_boot:
            raise TraceError("trace bootTick values must strictly increase")
        if frame.reset_count < previous_reset or frame.reset_count > capture.reset_count:
            raise TraceError("trace resetCount values must be monotonic and within the header count")
        if frame.flags & ~_FRAME_FLAG_MASK:
            raise TraceError(f"trace frame {index} contains unknown flag bits")
        transitioned = bool(frame.flags & _TRANSITION_FLAG)
        if transitioned:
            if frame.transition_from == 0xFF or frame.transition_to == 0xFF:
                raise TraceError(f"trace frame {index} transition is missing a scene")
        elif (frame.transition_from, frame.transition_to, frame.transition_argument) != (0xFF, 0xFF, 0):
            raise TraceError(f"trace frame {index} has transition data without its flag")
        if frame.audio_voice_mask & ~0x0F or frame.audio_sfx_mask & ~0x0F:
            raise TraceError(f"trace frame {index} audio masks exceed four hardware channels")
        previous_boot = frame.boot_tick
        previous_reset = frame.reset_count
    retained_markers = _marker_union(capture.frames)
    if (capture.audio_marker_union & retained_markers) != retained_markers:
        raise TraceError("audioMarkerUnion omits a retained frame marker")
    retained_transitions = sum(bool(frame.flags & _TRANSITION_FLAG) for frame in capture.frames)
    if capture.transition_count < retained_transitions:
        raise TraceError("transitionCount is smaller than retained transitions")
    if capture.dropped_frame_count == 0:
        if capture.stream_hash != _stream_hash(capture.frames):
            raise TraceError("streamHashFNV1a32 does not match complete trace records")
        if capture.audio_marker_union != _marker_union(capture.frames):
            raise TraceError("audioMarkerUnion does not match complete trace records")
        if capture.transition_count != retained_transitions:
            raise TraceError("transitionCount does not match complete trace records")
    return capture


def decode_trace(payload: bytes) -> TraceCapture:
    if len(payload) < BINARY_HEADER_SIZE or payload[:4] != BINARY_MAGIC:
        raise TraceError("trace payload is missing the SWTR header")
    if payload[4] != BINARY_VERSION:
        raise TraceError(f"unsupported deterministic trace binary version {payload[4]}")
    if payload[5] != BINARY_RECORD_SIZE:
        raise TraceError(f"unsupported deterministic trace record size {payload[5]}")
    count = int.from_bytes(payload[6:8], "little")
    dropped = int.from_bytes(payload[8:12], "little")
    resets = int.from_bytes(payload[12:14], "little")
    if payload[14:16] != b"\0\0":
        raise TraceError("trace header reserved bytes must be zero")
    total = int.from_bytes(payload[16:20], "little")
    stream_hash = int.from_bytes(payload[20:24], "little")
    audio_markers = int.from_bytes(payload[24:26], "little")
    transitions = int.from_bytes(payload[26:28], "little")
    if payload[28:32] != b"\0\0\0\0":
        raise TraceError("trace header extended reserved bytes must be zero")
    expected = BINARY_HEADER_SIZE + count * BINARY_RECORD_SIZE
    if len(payload) != expected:
        raise TraceError(f"trace length is {len(payload)} bytes; expected exactly {expected}")
    frames = tuple(
        TraceFrame.from_bytes(payload[offset:offset + BINARY_RECORD_SIZE])
        for offset in range(BINARY_HEADER_SIZE, expected, BINARY_RECORD_SIZE)
    )
    return _validate_capture(TraceCapture(
        frames, dropped, resets, total, stream_hash, audio_markers, transitions,
    ))


def encode_trace(capture: TraceCapture) -> bytes:
    checked = _validate_capture(capture)
    header = bytearray(BINARY_HEADER_SIZE)
    header[:4] = BINARY_MAGIC
    header[4] = BINARY_VERSION
    header[5] = BINARY_RECORD_SIZE
    header[6:8] = len(checked.frames).to_bytes(2, "little")
    header[8:12] = checked.dropped_frame_count.to_bytes(4, "little")
    header[12:14] = checked.reset_count.to_bytes(2, "little")
    header[16:20] = checked.total_frame_count.to_bytes(4, "little")
    header[20:24] = checked.stream_hash.to_bytes(4, "little")
    header[24:26] = checked.audio_marker_union.to_bytes(2, "little")
    header[26:28] = checked.transition_count.to_bytes(2, "little")
    return bytes(header) + b"".join(frame.to_bytes() for frame in checked.frames)


def validate_trace(value: object) -> TraceCapture:
    if not isinstance(value, Mapping) or value.get("schema") != TRACE_SCHEMA:
        raise TraceError(f"deterministic traces must use {TRACE_SCHEMA}")
    required = {
        "schema", "binaryVersion", "recordSize", "droppedFrameCount", "resetCount",
        "totalFrameCount", "streamHashFNV1a32", "audioMarkerUnion",
        "transitionCount", "frames",
    }
    if set(value) != required:
        raise TraceError("deterministic trace fields do not match the v1 contract")
    if value["binaryVersion"] != BINARY_VERSION or value["recordSize"] != BINARY_RECORD_SIZE:
        raise TraceError("deterministic trace binary metadata does not match v1")
    if not isinstance(value["frames"], list):
        raise TraceError("deterministic trace frames must be an array")
    frames: list[TraceFrame] = []
    for index, frame in enumerate(value["frames"]):
        if not isinstance(frame, Mapping):
            raise TraceError(f"trace frame {index} must be an object")
        frames.append(TraceFrame.from_dict(frame, index=index))
    capture = TraceCapture(
        tuple(frames),
        _integer(value["droppedFrameCount"], "droppedFrameCount", 0, 0xFFFFFFFF),
        _integer(value["resetCount"], "resetCount", 0, 0xFFFF),
        _integer(value["totalFrameCount"], "totalFrameCount", 0, 0xFFFFFFFF),
        _integer(value["streamHashFNV1a32"], "streamHashFNV1a32", 0, 0xFFFFFFFF),
        _integer(value["audioMarkerUnion"], "audioMarkerUnion", 0, 0xFFFF),
        _integer(value["transitionCount"], "transitionCount", 0, 0xFFFF),
    )
    return _validate_capture(capture)


def load_trace(source: Path | bytes | bytearray | Mapping[str, Any]) -> TraceCapture:
    if isinstance(source, Mapping):
        return validate_trace(source)
    payload = source.read_bytes() if isinstance(source, Path) else bytes(source)
    if payload.lstrip().startswith(b"{"):
        try:
            value = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise TraceError(f"invalid deterministic trace JSON: {exc}") from exc
        return validate_trace(value)
    return decode_trace(payload)


def trace_sha256(capture: TraceCapture) -> str:
    return hashlib.sha256(encode_trace(capture)).hexdigest()


def trace_json_bytes(capture: TraceCapture) -> bytes:
    return (json.dumps(_validate_capture(capture).to_dict(), sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")


def validate_outcome_contract(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping) or value.get("schema") != OUTCOME_CONTRACT_SCHEMA:
        raise TraceError(f"scenario outcome contracts must use {OUTCOME_CONTRACT_SCHEMA}")
    allowed = {"schema", "final", "reset", "audio", "requireCompleteTrace", "traceSHA256"}
    if set(value) - allowed:
        raise TraceError(f"unknown scenario outcome fields: {sorted(set(value) - allowed)}")
    result: dict[str, Any] = {
        "schema": OUTCOME_CONTRACT_SCHEMA,
        "requireCompleteTrace": value.get("requireCompleteTrace", False),
    }
    if not isinstance(result["requireCompleteTrace"], bool):
        raise TraceError("requireCompleteTrace must be boolean")
    digest = value.get("traceSHA256")
    if digest is not None and (not isinstance(digest, str) or not _SHA256.fullmatch(digest)):
        raise TraceError("traceSHA256 must be a lowercase SHA-256 digest")
    if digest is not None:
        result["traceSHA256"] = digest

    final = value.get("final", {})
    if not isinstance(final, Mapping):
        raise TraceError("final outcome expectations must be an object")
    final_allowed = {"scene", "ending", "progress", "progressAtLeast", "progressAtMost", "stateHash"}
    if set(final) - final_allowed:
        raise TraceError(f"unknown final outcome fields: {sorted(set(final) - final_allowed)}")
    checked_final: dict[str, int] = {}
    for name, maximum in (("scene", 0xFE), ("ending", 0xFF), ("progress", 0xFFFF),
                          ("progressAtLeast", 0xFFFF), ("progressAtMost", 0xFFFF),
                          ("stateHash", 0xFFFFFFFF)):
        if name in final:
            checked_final[name] = _integer(final[name], f"final.{name}", 0, maximum)
    if "progress" in checked_final and ({"progressAtLeast", "progressAtMost"} & set(checked_final)):
        raise TraceError("final.progress cannot be combined with progress bounds")
    if checked_final.get("progressAtLeast", 0) > checked_final.get("progressAtMost", 0xFFFF):
        raise TraceError("final progress bounds are reversed")
    result["final"] = checked_final

    reset = value.get("reset", {})
    if not isinstance(reset, Mapping):
        raise TraceError("reset outcome expectations must be an object")
    reset_allowed = {"expectation", "scene", "ending", "progress", "stateHash", "sessionTick"}
    if set(reset) - reset_allowed:
        raise TraceError(f"unknown reset outcome fields: {sorted(set(reset) - reset_allowed)}")
    expectation = reset.get("expectation", "any")
    if expectation not in {"any", "none", "required", "exactly-one"}:
        raise TraceError("reset.expectation must be any, none, required, or exactly-one")
    checked_reset: dict[str, Any] = {"expectation": expectation}
    for name, maximum in (("scene", 0xFE), ("ending", 0xFF), ("progress", 0xFFFF),
                          ("stateHash", 0xFFFFFFFF), ("sessionTick", 0xFFFFFFFF)):
        if name in reset:
            checked_reset[name] = _integer(reset[name], f"reset.{name}", 0, maximum)
    result["reset"] = checked_reset

    audio = value.get("audio", {})
    if not isinstance(audio, Mapping):
        raise TraceError("audio outcome expectations must be an object")
    audio_allowed = {"expectation", "markerMask", "peakThreshold"}
    if set(audio) - audio_allowed:
        raise TraceError(f"unknown audio outcome fields: {sorted(set(audio) - audio_allowed)}")
    audio_expectation = audio.get("expectation", "any")
    if audio_expectation not in {"any", "audible", "silent"}:
        raise TraceError("audio.expectation must be any, audible, or silent")
    threshold = audio.get("peakThreshold", 0.0001)
    if (not isinstance(threshold, (int, float)) or isinstance(threshold, bool) or
            threshold < 0):
        raise TraceError("audio.peakThreshold must be nonnegative")
    checked_audio: dict[str, Any] = {
        "expectation": audio_expectation,
        "peakThreshold": float(threshold),
    }
    if "markerMask" in audio:
        checked_audio["markerMask"] = _integer(audio["markerMask"], "audio.markerMask", 1, 0xFFFF)
    result["audio"] = checked_audio
    return result


def validate_scenario_outcome(contract: Mapping[str, Any], trace: TraceCapture | Mapping[str, Any],
                              *, audio: Mapping[str, Any] | None = None) -> dict[str, Any]:
    checked = validate_outcome_contract(contract)
    capture = trace if isinstance(trace, TraceCapture) else validate_trace(trace)
    digest = trace_sha256(capture)
    final = capture.frames[-1] if capture.frames else None
    checks: list[dict[str, Any]] = []

    def check(identifier: str, passed: bool, expected: object, observed: object,
              message: str) -> None:
        checks.append({"id": identifier, "passed": passed, "expected": expected,
                       "observed": observed, "message": message})

    if checked["requireCompleteTrace"]:
        check("trace-complete", capture.dropped_frame_count == 0, 0,
              capture.dropped_frame_count, "bounded trace must not contain dropped frames")
    if "traceSHA256" in checked:
        check("trace-sha256", digest == checked["traceSHA256"], checked["traceSHA256"],
              digest, "binary trace identity must match")
    check("final-frame", final is not None, "present", "present" if final else "missing",
          "a final runtime frame is required")
    panic_codes = sorted({frame.panic_code for frame in capture.frames if frame.panic_code})
    check("runtime-panic", not panic_codes, [], panic_codes,
          "deterministic scenario execution must not panic")

    if final is not None:
        expected_final = checked["final"]
        for key, attribute in (("scene", "scene"), ("ending", "ending"),
                               ("progress", "progress"), ("stateHash", "state_hash")):
            if key in expected_final:
                observed = getattr(final, attribute)
                check(f"final-{key}", observed == expected_final[key], expected_final[key],
                      observed, f"final {key} must match")
        if "progressAtLeast" in expected_final:
            check("final-progress-minimum", final.progress >= expected_final["progressAtLeast"],
                  expected_final["progressAtLeast"], final.progress,
                  "final progress must reach the declared minimum")
        if "progressAtMost" in expected_final:
            check("final-progress-maximum", final.progress <= expected_final["progressAtMost"],
                  expected_final["progressAtMost"], final.progress,
                  "final progress must not exceed the declared maximum")

    reset = checked["reset"]
    reset_expectation = reset["expectation"]
    reset_passed = {
        "any": True,
        "none": capture.reset_count == 0,
        "required": capture.reset_count > 0,
        "exactly-one": capture.reset_count == 1,
    }[reset_expectation]
    check("reset-count", reset_passed, reset_expectation, capture.reset_count,
          "reset count must satisfy the declared expectation")
    reset_fields = set(reset) - {"expectation"}
    if reset_fields:
        check("reset-observed", capture.reset_count > 0, "at least one reset",
              capture.reset_count, "reset-state expectations require an observed reset")
        if final is not None and capture.reset_count > 0:
            for key, attribute in (("scene", "scene"), ("ending", "ending"),
                                   ("progress", "progress"), ("stateHash", "state_hash"),
                                   ("sessionTick", "session_tick")):
                if key in reset:
                    observed = getattr(final, attribute)
                    check(f"reset-{key}", observed == reset[key], reset[key], observed,
                          f"post-reset {key} must match")

    audio_contract = checked["audio"]
    marker_mask = audio_contract.get("markerMask")
    if marker_mask is not None:
        observed_marker = capture.audio_marker_union
        check("audio-marker", observed_marker & marker_mask == marker_mask,
              marker_mask, observed_marker, "runtime audio markers must include the declared mask")
    if audio_contract["expectation"] != "any":
        inspected = isinstance(audio, Mapping) and audio.get("inspected") is True
        peak = (
            audio.get("normalizedPeak", audio.get("peakAbsoluteSample"))
            if isinstance(audio, Mapping) else None
        )
        valid_peak = isinstance(peak, (int, float)) and not isinstance(peak, bool) and peak >= 0
        check("audio-inspected", inspected and valid_peak, "inspected SwanSong WAV peak",
              peak, "audible and silent verdicts require inspected SwanSong WAV evidence")
        if inspected and valid_peak:
            threshold = audio_contract["peakThreshold"]
            passed = peak > threshold if audio_contract["expectation"] == "audible" else peak <= threshold
            check("audio-expectation", passed, audio_contract["expectation"], peak,
                  "SwanSong WAV peak must satisfy the audio expectation")

    marked_resets = sum(bool(frame.flags & _RESET_FLAG) for frame in capture.frames)
    observed_final = None if final is None else {
        "scene": final.scene,
        "ending": final.ending,
        "progress": final.progress,
        "stateHash": final.state_hash,
        "sessionTick": final.session_tick,
        "panicCode": final.panic_code,
    }
    report = {
        "schema": OUTCOME_REPORT_SCHEMA,
        "passed": all(item["passed"] for item in checks),
        "trace": {
            "sha256": digest,
            "frameCount": len(capture.frames),
            "totalFrameCount": capture.total_frame_count,
            "droppedFrameCount": capture.dropped_frame_count,
            "complete": capture.dropped_frame_count == 0,
            "streamHashFNV1a32": capture.stream_hash,
        },
        "observed": {
            "final": observed_final,
            "reset": {"count": capture.reset_count, "markedFrames": marked_resets},
            "audio": dict(audio) if isinstance(audio, Mapping) else None,
        },
        "checks": checks,
    }
    return report


def outcome_report_bytes(report: Mapping[str, Any]) -> bytes:
    if report.get("schema") != OUTCOME_REPORT_SCHEMA:
        raise TraceError(f"outcome reports must use {OUTCOME_REPORT_SCHEMA}")
    return (json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
