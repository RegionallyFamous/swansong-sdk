"""Editable conversion of observed input transitions into SwanSong plans.

This module records inputs only.  It does not execute ROMs or infer gameplay
state; shipping-ROM execution remains the responsibility of SwanSong.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .plans import INPUTS, PlanError, validate_plan


SCHEMA = "swansong-scenario-record-report-v1"
FRAME_LOG_SCHEMA = "swan-song-input-frame-log-v2"
PLAN_SCHEMA = "swan-song-frame-input-plan-v1"
DEFAULT_REFRESH_NUMERATOR = 7547
DEFAULT_REFRESH_DENOMINATOR = 100


class ScenarioError(ValueError):
    pass


def normalize_inputs(values: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise ScenarioError("inputs must be strings")
        name = value.strip().lower()
        if name not in INPUTS:
            raise ScenarioError(f"unknown WonderSwan input {value!r}")
        if name not in normalized:
            normalized.append(name)
    return tuple(sorted(normalized))


def timestamp_to_frame(timestamp_ms: int, *, refresh_numerator: int,
                       refresh_denominator: int) -> int:
    if timestamp_ms < 0:
        raise ScenarioError("timestamp_ms must be nonnegative")
    if refresh_numerator <= 0 or refresh_denominator <= 0:
        raise ScenarioError("refresh rate must be positive")
    frames = Fraction(timestamp_ms * refresh_numerator,
                      1000 * refresh_denominator)
    return frames.numerator // frames.denominator


@dataclass(frozen=True)
class ScenarioEvent:
    frame_index: int
    inputs: tuple[str, ...]
    timestamp_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "frameIndex": self.frame_index,
            "inputs": list(self.inputs),
        }
        if self.timestamp_ms is not None:
            result["timestampMs"] = self.timestamp_ms
        return result


class ScenarioRecording:
    """Mutable transition list with deterministic editing and plan export."""

    def __init__(self, *, refresh_numerator: int = DEFAULT_REFRESH_NUMERATOR,
                 refresh_denominator: int = DEFAULT_REFRESH_DENOMINATOR) -> None:
        if refresh_numerator <= 0 or refresh_denominator <= 0:
            raise ScenarioError("refresh rate must be positive")
        self.refresh_numerator = refresh_numerator
        self.refresh_denominator = refresh_denominator
        self._events: dict[int, ScenarioEvent] = {
            0: ScenarioEvent(0, (), 0),
        }

    @property
    def events(self) -> tuple[ScenarioEvent, ...]:
        return tuple(self._events[index] for index in sorted(self._events))

    def record(self, inputs: Iterable[str], *, frame_index: int | None = None,
               timestamp_ms: int | None = None) -> ScenarioEvent:
        if (frame_index is None) == (timestamp_ms is None):
            raise ScenarioError("provide exactly one of frame_index or timestamp_ms")
        if timestamp_ms is not None:
            frame_index = timestamp_to_frame(
                timestamp_ms,
                refresh_numerator=self.refresh_numerator,
                refresh_denominator=self.refresh_denominator,
            )
        assert frame_index is not None
        if frame_index < 0:
            raise ScenarioError("frame_index must be nonnegative")
        event = ScenarioEvent(frame_index, normalize_inputs(inputs), timestamp_ms)
        if frame_index == 0 and event.inputs:
            raise ScenarioError("frame 0 is reserved for the neutral fresh boot")
        self._events[frame_index] = event
        return event

    def edit(self, frame_index: int, *, inputs: Iterable[str] | None = None,
             new_frame_index: int | None = None) -> ScenarioEvent:
        if frame_index not in self._events:
            raise ScenarioError(f"no transition exists at frame {frame_index}")
        original = self._events[frame_index]
        target = frame_index if new_frame_index is None else new_frame_index
        values = original.inputs if inputs is None else normalize_inputs(inputs)
        if target < 0 or (target == 0 and values):
            raise ScenarioError("edited frame must be nonnegative and frame 0 neutral")
        if target != frame_index and target in self._events:
            raise ScenarioError(f"a transition already exists at frame {target}")
        del self._events[frame_index]
        event = ScenarioEvent(target, tuple(values), original.timestamp_ms)
        self._events[target] = event
        if 0 not in self._events:
            self._events[0] = ScenarioEvent(0, (), 0)
        return event

    def delete(self, frame_index: int) -> None:
        if frame_index == 0:
            raise ScenarioError("the neutral frame 0 transition cannot be deleted")
        if frame_index not in self._events:
            raise ScenarioError(f"no transition exists at frame {frame_index}")
        del self._events[frame_index]

    def _compressed_events(self) -> list[ScenarioEvent]:
        result: list[ScenarioEvent] = []
        previous: tuple[str, ...] | None = None
        for event in self.events:
            if event.inputs != previous:
                result.append(event)
                previous = event.inputs
        return result

    def to_plan(self, *, total_frames: int | None = None) -> dict[str, Any]:
        events = self._compressed_events()
        last_frame = events[-1].frame_index
        if total_frames is None:
            total_frames = last_frame + 1
        if total_frames <= last_frame:
            raise ScenarioError("total_frames must be after the final transition")
        plan = {
            "schema": PLAN_SCHEMA,
            "totalFrames": total_frames,
            "events": [
                {"frameIndex": event.frame_index, "inputs": list(event.inputs)}
                for event in events
            ],
        }
        try:
            return validate_plan(plan, Path("<recording>"))
        except PlanError as exc:
            raise ScenarioError(str(exc)) from exc

    def to_dict(self, *, total_frames: int | None = None,
                source_schema: str = "transition-list") -> dict[str, Any]:
        plan = self.to_plan(total_frames=total_frames)
        return {
            "schema": SCHEMA,
            "sourceSchema": source_schema,
            "refreshRate": {
                "numerator": self.refresh_numerator,
                "denominator": self.refresh_denominator,
            },
            "editableEvents": [event.to_dict() for event in self.events],
            "plan": plan,
        }

    @classmethod
    def from_plan(cls, plan: Mapping[str, Any]) -> "ScenarioRecording":
        checked = validate_plan(dict(plan), Path("<plan>"))
        result = cls()
        result._events.clear()
        for raw in checked["events"]:
            event = ScenarioEvent(raw["frameIndex"], normalize_inputs(raw["inputs"]))
            result._events[event.frame_index] = event
        return result


def record_transitions(transitions: Sequence[Mapping[str, Any]], *,
                       total_frames: int | None = None,
                       refresh_numerator: int = DEFAULT_REFRESH_NUMERATOR,
                       refresh_denominator: int = DEFAULT_REFRESH_DENOMINATOR,
                       ) -> dict[str, Any]:
    recording = ScenarioRecording(
        refresh_numerator=refresh_numerator,
        refresh_denominator=refresh_denominator,
    )
    for transition in transitions:
        unknown = set(transition) - {"frameIndex", "timestampMs", "inputs"}
        if unknown or "inputs" not in transition:
            raise ScenarioError(f"invalid transition keys: {sorted(unknown)}")
        recording.record(
            transition["inputs"],
            frame_index=transition.get("frameIndex"),
            timestamp_ms=transition.get("timestampMs"),
        )
    return recording.to_dict(total_frames=total_frames)


def recording_from_frame_log(log: Mapping[str, Any]) -> ScenarioRecording:
    if log.get("schema") != FRAME_LOG_SCHEMA:
        raise ScenarioError(f"frame log must use {FRAME_LOG_SCHEMA}")
    dropped = log.get("droppedFrameCount")
    total = log.get("totalFrameCount")
    frames = log.get("frames")
    if not isinstance(dropped, int) or isinstance(dropped, bool) or dropped != 0:
        raise ScenarioError("frame log contains dropped frames and is not replay-safe")
    if not isinstance(total, int) or isinstance(total, bool) or total <= 0:
        raise ScenarioError("frame log totalFrameCount must be positive")
    if not isinstance(frames, list) or len(frames) != total:
        raise ScenarioError("frame log frames must match totalFrameCount")
    normalized_frames: list[tuple[str, ...]] = []
    for expected, frame in enumerate(frames):
        if not isinstance(frame, Mapping) or frame.get("sequenceIndex") != expected:
            raise ScenarioError("frame log sequenceIndex values must be contiguous from 0")
        values = frame.get("effectiveInputs")
        if not isinstance(values, list):
            raise ScenarioError(f"frame {expected} effectiveInputs must be an array")
        normalized_frames.append(normalize_inputs(values))

    shift = 1 if normalized_frames[0] else 0
    recording = ScenarioRecording()
    previous: tuple[str, ...] = ()
    for index, inputs in enumerate(normalized_frames):
        target = index + shift
        if inputs != previous:
            recording.record(inputs, frame_index=target)
            previous = inputs
    return recording


def record_frame_log(log: Mapping[str, Any]) -> dict[str, Any]:
    recording = recording_from_frame_log(log)
    total = int(log["totalFrameCount"])
    shift = 1 if normalize_inputs(log["frames"][0]["effectiveInputs"]) else 0
    last = recording.events[-1].frame_index
    total_frames = max(total + shift, last + 1)
    return recording.to_dict(total_frames=total_frames, source_schema=FRAME_LOG_SCHEMA)
