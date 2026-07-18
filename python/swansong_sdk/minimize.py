"""Deterministic delta reduction for exact-frame SwanSong input plans."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .plans import INPUTS, validate_plan


PREDICATE_SCHEMA = "swansong-failure-predicate-v1"
REPORT_SCHEMA = "swansong-minimize-report-v1"
MAX_PLAN_FRAMES = 1_000_000


class MinimizeError(ValueError):
    pass


@dataclass(frozen=True)
class FailureObservation:
    matched: bool
    result: Mapping[str, Any]


def canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_failure_predicate(value: object,
                               path: Path = Path("<predicate>")) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema") != PREDICATE_SCHEMA:
        raise MinimizeError(f"failure predicate must use {PREDICATE_SCHEMA}: {path}")
    kind = value.get("kind")
    if kind == "structured-evidence":
        if set(value) != {"schema", "kind", "path", "equals"}:
            raise MinimizeError(
                "structured-evidence predicate requires only schema, kind, path, and equals"
            )
        pointer = value.get("path")
        if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
            raise MinimizeError("structured-evidence predicate path must be an RFC 6901 JSON pointer")
        for offset, character in enumerate(pointer):
            if character == "~" and (
                offset + 1 >= len(pointer) or pointer[offset + 1] not in "01"
            ):
                raise MinimizeError(
                    "structured-evidence predicate path contains an invalid RFC 6901 escape"
                )
    elif kind == "execution-error":
        if set(value) != {"schema", "kind", "messageEquals"}:
            raise MinimizeError(
                "execution-error predicate requires only schema, kind, and messageEquals"
            )
        message = value.get("messageEquals")
        if not isinstance(message, str) or not message:
            raise MinimizeError("execution-error messageEquals must be nonempty")
    else:
        raise MinimizeError(
            "failure predicate kind must be structured-evidence or execution-error"
        )
    return value


def json_pointer(document: object, pointer: str) -> tuple[bool, object]:
    if pointer == "":
        return True, document
    current = document
    for encoded in pointer[1:].split("/"):
        token = encoded.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping):
            if token not in current:
                return False, None
            current = current[token]
        elif isinstance(current, list):
            if (token == "-" or not token.isdigit() or
                    (len(token) > 1 and token.startswith("0"))):
                return False, None
            index = int(token)
            if index >= len(current):
                return False, None
            current = current[index]
        else:
            return False, None
    return True, current


def observe_evidence(predicate: Mapping[str, Any],
                     evidence: Mapping[str, Any]) -> FailureObservation:
    if predicate.get("kind") != "structured-evidence":
        raise MinimizeError("cannot apply a non-evidence predicate to structured evidence")
    found, actual = json_pointer(evidence, str(predicate["path"]))
    expected = predicate["equals"]
    return FailureObservation(found and actual == expected, {
        "kind": "structured-evidence",
        "path": predicate["path"],
        "found": found,
        "actual": actual,
        "expected": expected,
    })


def observe_execution_error(predicate: Mapping[str, Any],
                            message: str) -> FailureObservation:
    if predicate.get("kind") != "execution-error":
        raise MinimizeError("cannot apply an evidence predicate to an execution error")
    expected = str(predicate["messageEquals"])
    return FailureObservation(expected == message, {
        "kind": "execution-error",
        "message": message,
        "expected": expected,
    })


def expand_plan(plan: Mapping[str, Any]) -> list[tuple[str, ...]]:
    checked = validate_plan(dict(plan), Path("<minimize-plan>"))
    total = int(checked["totalFrames"])
    if total > MAX_PLAN_FRAMES:
        raise MinimizeError(
            f"minimization supports at most {MAX_PLAN_FRAMES} frames; got {total}"
        )
    events = checked["events"]
    states: list[tuple[str, ...]] = []
    event_index = 0
    current: tuple[str, ...] = ()
    for frame_index in range(total):
        if event_index < len(events) and events[event_index]["frameIndex"] == frame_index:
            current = tuple(sorted(events[event_index]["inputs"]))
            event_index += 1
        states.append(current)
    return states


def compress_frames(frames: Sequence[Sequence[str]]) -> dict[str, Any]:
    if not frames or frames[0]:
        raise MinimizeError("a minimized plan must retain a neutral fresh-boot frame")
    events: list[dict[str, Any]] = []
    previous: tuple[str, ...] | None = None
    for frame_index, raw_inputs in enumerate(frames):
        inputs = tuple(sorted(raw_inputs))
        if any(value not in INPUTS for value in inputs) or len(inputs) != len(set(inputs)):
            raise MinimizeError("minimized frame contains invalid or duplicate inputs")
        if inputs != previous:
            events.append({"frameIndex": frame_index, "inputs": list(inputs)})
            previous = inputs
    plan = {
        "schema": "swan-song-frame-input-plan-v1",
        "totalFrames": len(frames),
        "events": events,
    }
    return validate_plan(plan, Path("<minimized-plan>"))


def plan_metrics(plan: Mapping[str, Any]) -> dict[str, int | str]:
    frames = expand_plan(plan)
    return {
        "sha256": canonical_digest(plan),
        "totalFrames": len(frames),
        "eventCount": len(plan["events"]),
        "activeInputFrames": sum(bool(inputs) for inputs in frames),
        "inputFrameAtoms": sum(len(inputs) for inputs in frames),
    }


class _Reducer:
    def __init__(self, evaluator: Callable[[dict[str, Any]], FailureObservation],
                 maximum_evaluations: int) -> None:
        if maximum_evaluations <= 0:
            raise MinimizeError("maximum evaluations must be positive")
        self.evaluator = evaluator
        self.maximum_evaluations = maximum_evaluations
        self.evaluations = 0
        self.cache_hits = 0
        self.cache: dict[str, FailureObservation] = {}
        self.steps: list[dict[str, Any]] = []

    @property
    def exhausted(self) -> bool:
        return self.evaluations >= self.maximum_evaluations

    def evaluate(self, plan: dict[str, Any]) -> FailureObservation | None:
        digest = canonical_digest(plan)
        if digest in self.cache:
            self.cache_hits += 1
            return self.cache[digest]
        if self.exhausted:
            return None
        observation = self.evaluator(plan)
        if not isinstance(observation, FailureObservation):
            raise MinimizeError("minimizer evaluator must return FailureObservation")
        self.evaluations += 1
        self.cache[digest] = observation
        return observation

    def preserves(self, frames: Sequence[Sequence[str]]) -> bool:
        observation = self.evaluate(compress_frames(frames))
        return observation is not None and observation.matched

    def record(self, phase: str, before: Sequence[Sequence[str]],
               after: Sequence[Sequence[str]]) -> None:
        self.steps.append({
            "phase": phase,
            "beforeFrames": len(before),
            "afterFrames": len(after),
            "beforeInputFrameAtoms": sum(len(item) for item in before),
            "afterInputFrameAtoms": sum(len(item) for item in after),
        })

    def delete_chunks(self, frames: list[tuple[str, ...]]) -> list[tuple[str, ...]]:
        tail = frames[1:]
        granularity = 2
        while tail and not self.exhausted:
            chunk_size = (len(tail) + granularity - 1) // granularity
            reduced = False
            for start in range(0, len(tail), chunk_size):
                if self.exhausted:
                    break
                candidate_tail = tail[:start] + tail[start + chunk_size:]
                candidate = [(), *candidate_tail]
                if self.preserves(candidate):
                    before = [(), *tail]
                    self.record("delete-frame-chunk", before, candidate)
                    tail = candidate_tail
                    granularity = max(2, granularity - 1)
                    reduced = True
                    break
            if not reduced:
                if granularity >= len(tail):
                    break
                granularity = min(len(tail), granularity * 2)
        return [(), *tail]

    def remove_inputs(self, frames: list[tuple[str, ...]]) -> tuple[list[tuple[str, ...]], bool]:
        changed = False
        for index in range(1, len(frames)):
            for input_name in tuple(frames[index]):
                if self.exhausted:
                    return frames, changed
                candidate = list(frames)
                candidate[index] = tuple(
                    value for value in frames[index] if value != input_name
                )
                if self.preserves(candidate):
                    self.record("delete-input-atom", frames, candidate)
                    frames = candidate
                    changed = True
        return frames, changed


def minimize_plan(plan: Mapping[str, Any],
                  evaluator: Callable[[dict[str, Any]], FailureObservation], *,
                  maximum_evaluations: int = 256,
                  predicate: Mapping[str, Any] | None = None,
                  ) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a deterministic 1-minimal candidate within the evaluation budget.

    Frame zero is immutable. Remaining effective-input frames are delta-reduced,
    which removes both unnecessary waiting and interactions while preserving the
    evaluator's declared failure result. Chord inputs are then reduced one atom
    at a time and frame reduction is repeated after successful atom removal.
    """

    original = validate_plan(dict(plan), Path("<minimize-plan>"))
    reducer = _Reducer(evaluator, maximum_evaluations)
    initial = reducer.evaluate(original)
    if initial is None or not initial.matched:
        raise MinimizeError("the declared failure predicate does not match the source plan")
    original_frames = expand_plan(original)
    normalized = compress_frames(original_frames)
    minimized = original
    frames = original_frames
    can_reduce = True
    if canonical_digest(normalized) != canonical_digest(original):
        normalization = reducer.evaluate(normalized)
        if normalization is not None and normalization.matched:
            reducer.record("normalize-transitions", frames, frames)
            minimized = normalized
        else:
            can_reduce = False
    if can_reduce:
        while not reducer.exhausted:
            before = frames
            frames = reducer.delete_chunks(frames)
            frames, atoms_changed = reducer.remove_inputs(frames)
            if frames == before and not atoms_changed:
                break
        minimized = compress_frames(frames)
    final = reducer.evaluate(minimized)
    if final is None or not final.matched:
        raise MinimizeError("internal error: minimized plan no longer preserves the predicate")
    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "ok": True,
        "predicate": dict(predicate) if predicate is not None else None,
        "preserved": True,
        "source": plan_metrics(original),
        "minimized": plan_metrics(minimized),
        "evaluations": reducer.evaluations,
        "cacheHits": reducer.cache_hits,
        "maximumEvaluations": maximum_evaluations,
        "limitReached": reducer.exhausted,
        "sourceResult": dict(initial.result),
        "minimizedResult": dict(final.result),
        "reductions": reducer.steps,
    }
    return minimized, report
