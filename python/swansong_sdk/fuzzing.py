"""Deterministic input-plan fuzzing and declared-trace verdict helpers.

The generator creates plans for SwanSong.  Trace evaluation consumes evidence
reported by SwanSong or a game model; it never pretends to execute a ROM.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .plans import INPUTS, validate_plan
from .scenario import normalize_inputs


SCHEMA = "swansong-fuzz-report-v1"


class FuzzError(ValueError):
    pass


class _XorShift32:
    def __init__(self, seed: int) -> None:
        self.state = seed & 0xFFFFFFFF or 0x6D2B79F5

    def next(self) -> int:
        value = self.state
        value ^= (value << 13) & 0xFFFFFFFF
        value ^= value >> 17
        value ^= (value << 5) & 0xFFFFFFFF
        self.state = value & 0xFFFFFFFF
        return self.state

    def bounded(self, limit: int) -> int:
        if limit <= 0:
            raise FuzzError("random bound must be positive")
        return self.next() % limit


@dataclass(frozen=True)
class FuzzReport:
    mode: str
    verdict: str
    findings: tuple[Mapping[str, Any], ...]
    seed: int | None = None
    plan: Mapping[str, Any] | None = None
    trace_digest: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "mode": self.mode,
            "verdict": self.verdict,
            "seed": self.seed,
            "plan": dict(self.plan) if self.plan is not None else None,
            "traceDigest": self.trace_digest,
            "findings": [dict(item) for item in self.findings],
        }


def generate_fuzz_plan(*, seed: int, total_frames: int,
                       inputs: Iterable[str] = tuple(sorted(INPUTS)),
                       neutral_boot_frames: int = 60,
                       maximum_actions: int = 64,
                       allow_chords: bool = True) -> FuzzReport:
    if total_frames <= 0:
        raise FuzzError("total_frames must be positive")
    if neutral_boot_frames < 1:
        raise FuzzError("neutral_boot_frames must reserve frame 0")
    if maximum_actions < 0:
        raise FuzzError("maximum_actions must be nonnegative")
    choices = normalize_inputs(inputs)
    if not choices:
        raise FuzzError("at least one input is required")
    random = _XorShift32(seed)
    events: list[dict[str, Any]] = [{"frameIndex": 0, "inputs": []}]
    cursor = neutral_boot_frames
    actions = 0
    while cursor + 1 < total_frames and actions < maximum_actions:
        first = choices[random.bounded(len(choices))]
        chord = [first]
        if allow_chords and len(choices) > 1 and random.bounded(5) == 0:
            second = choices[random.bounded(len(choices))]
            if second != first:
                chord.append(second)
        chord.sort()
        hold = 1 + random.bounded(min(8, total_frames - cursor - 1))
        release = cursor + hold
        events.append({"frameIndex": cursor, "inputs": chord})
        if release < total_frames:
            events.append({"frameIndex": release, "inputs": []})
        actions += 1
        # The release frame and its successor are neutral before another press.
        cursor = release + 2 + random.bounded(6)
    plan = {
        "schema": "swan-song-frame-input-plan-v1",
        "totalFrames": total_frames,
        "events": events,
    }
    checked = validate_plan(plan, Path("<fuzz-plan>"))
    return FuzzReport("generation", "ready", (), seed=seed, plan=checked)


def crash_finding(trace: Mapping[str, Any]) -> dict[str, Any] | None:
    status = str(trace.get("status", "")).lower()
    crash = trace.get("crash")
    if not crash and status not in {"crash", "crashed", "hang", "hung", "timeout"}:
        return None
    return {
        "severity": "error",
        "code": "execution-failure",
        "message": "declared trace reports a crash, hang, or timeout",
        "detail": crash if crash else status,
    }


def invalid_transition_findings(frames: Sequence[Mapping[str, Any]],
                                allowed: Mapping[str, Iterable[str]],
                                ) -> list[dict[str, Any]]:
    normalized = {str(state): {str(target) for target in targets}
                  for state, targets in allowed.items()}
    findings: list[dict[str, Any]] = []
    previous: Mapping[str, Any] | None = None
    for frame in frames:
        if previous is not None:
            before = previous.get("state")
            after = frame.get("state")
            if before is not None and after is not None and before != after:
                if str(after) not in normalized.get(str(before), set()):
                    findings.append({
                        "severity": "error",
                        "code": "invalid-transition",
                        "frameIndex": frame.get("frameIndex"),
                        "from": before,
                        "to": after,
                        "message": f"transition {before!r} -> {after!r} is not allowed",
                    })
        previous = frame
    return findings


def dead_end_finding(frames: Sequence[Mapping[str, Any]], *,
                     threshold_frames: int = 120) -> dict[str, Any] | None:
    if threshold_frames <= 0:
        raise FuzzError("threshold_frames must be positive")
    for start, frame in enumerate(frames):
        meaningful = bool(frame.get("meaningfulInput")) or bool(frame.get("inputs"))
        marker = frame.get("progressMarker", frame.get("stateHash"))
        if not meaningful or marker is None:
            continue
        start_index = frame.get("frameIndex")
        if not isinstance(start_index, int):
            continue
        last_index = start_index
        changed = False
        for following in frames[start + 1:]:
            following_index = following.get("frameIndex")
            if isinstance(following_index, int):
                last_index = following_index
            candidate = following.get("progressMarker", following.get("stateHash"))
            if candidate is not None and candidate != marker:
                changed = True
                break
        if not changed and last_index - start_index >= threshold_frames:
            return {
                "severity": "error",
                "code": "dead-end",
                "frameIndex": start_index,
                "durationFrames": last_index - start_index,
                "markerBasis": "progressMarker" if "progressMarker" in frame else "stateHash",
                "message": "meaningful input was followed by no declared progress",
            }
    return None


def reset_divergence_findings(reset_checks: Sequence[Mapping[str, Any]],
                              ) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for index, check in enumerate(reset_checks):
        if "baseline" not in check or "actual" not in check:
            raise FuzzError("reset checks require baseline and actual values")
        baseline = json.dumps(check["baseline"], sort_keys=True, separators=(",", ":"))
        actual = json.dumps(check["actual"], sort_keys=True, separators=(",", ":"))
        if baseline != actual:
            findings.append({
                "severity": "error",
                "code": "reset-divergence",
                "checkIndex": index,
                "baselineSha256": hashlib.sha256(baseline.encode()).hexdigest(),
                "actualSha256": hashlib.sha256(actual.encode()).hexdigest(),
                "message": "reset/replay state differs from the declared baseline",
            })
    return findings


def _validate_frames(raw: Any) -> list[Mapping[str, Any]]:
    if not isinstance(raw, list):
        raise FuzzError("trace frames must be an array")
    frames: list[Mapping[str, Any]] = []
    previous = -1
    for frame in raw:
        if not isinstance(frame, Mapping):
            raise FuzzError("trace frames must be objects")
        index = frame.get("frameIndex")
        if not isinstance(index, int) or isinstance(index, bool) or index <= previous:
            raise FuzzError("trace frameIndex values must strictly increase")
        previous = index
        frames.append(frame)
    return frames


def evaluate_trace(trace: Mapping[str, Any], *,
                   allowed_transitions: Mapping[str, Iterable[str]] | None = None,
                   dead_end_frames: int = 120) -> FuzzReport:
    frames = _validate_frames(trace.get("frames"))
    findings: list[dict[str, Any]] = []
    crash = crash_finding(trace)
    if crash is not None:
        findings.append(crash)
    if allowed_transitions is not None:
        findings.extend(invalid_transition_findings(frames, allowed_transitions))
    dead_end = dead_end_finding(frames, threshold_frames=dead_end_frames)
    if dead_end is not None:
        findings.append(dead_end)
    reset_checks = trace.get("resetChecks", [])
    if not isinstance(reset_checks, list):
        raise FuzzError("resetChecks must be an array")
    findings.extend(reset_divergence_findings(reset_checks))
    canonical = json.dumps(trace, sort_keys=True, separators=(",", ":"), default=str)
    evaluable = bool(frames)
    verdict = "fail" if findings else "pass" if evaluable else "inconclusive"
    return FuzzReport(
        "trace-verdict", verdict, tuple(findings),
        trace_digest=hashlib.sha256(canonical.encode()).hexdigest(),
    )
