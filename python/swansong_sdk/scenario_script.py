"""Compile readable deterministic scenario macros into exact frame plans."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping, Sequence

from .plans import INPUTS, validate_plan, validate_play_readiness


SCRIPT_SCHEMA = "swansong-scenario-script-v1"
REPORT_SCHEMA = "swansong-scenario-compile-report-v1"
MAX_NESTING = 4
MAX_TOTAL_FRAMES = 1_000_000
MAX_EXPANDED_ACTIONS = 4096


class ScenarioScriptError(ValueError):
    pass


def _positive(value: object, context: str, *, allow_zero: bool = False) -> int:
    minimum = 0 if allow_zero else 1
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        qualifier = "non-negative" if allow_zero else "positive"
        raise ScenarioScriptError(f"{context} must be a {qualifier} integer")
    return value


def _inputs(value: object, context: str, *, chord: bool = False) -> list[str]:
    if (not isinstance(value, list) or
            not all(isinstance(item, str) and item.lower() in INPUTS for item in value)):
        raise ScenarioScriptError(f"{context} inputs must use known WonderSwan names")
    normalized = [item.lower() for item in value]
    if not normalized or len(normalized) != len(set(normalized)):
        raise ScenarioScriptError(f"{context} inputs must be nonempty and unique")
    if chord and len(normalized) < 2:
        raise ScenarioScriptError(f"{context} requires at least two same-frame inputs")
    return sorted(normalized)


def compile_scenario_script(value: object, *, ready_frames: int = 0,
                            source: Path | None = None) -> dict[str, object]:
    if not isinstance(value, dict) or value.get("schema") != SCRIPT_SCHEMA:
        raise ScenarioScriptError(f"scenario script must use {SCRIPT_SCHEMA}")
    if set(value) - {"schema", "steps", "tailFrames"}:
        raise ScenarioScriptError("scenario script contains unsupported fields")
    steps = value.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ScenarioScriptError("scenario script steps must be a nonempty array")
    tail_frames = _positive(value.get("tailFrames", 60), "tailFrames")
    ready = _positive(ready_frames, "ready_frames", allow_zero=True)
    current = max(1, ready)
    events: list[dict[str, object]] = [{"frameIndex": 0, "inputs": []}]
    expanded = 0

    def append(frame: int, inputs: list[str]) -> None:
        nonlocal expanded
        if frame >= MAX_TOTAL_FRAMES:
            raise ScenarioScriptError("scenario script exceeds the maximum frame count")
        if events[-1]["frameIndex"] == frame:
            events[-1] = {"frameIndex": frame, "inputs": inputs}
        elif events[-1]["inputs"] != inputs:
            events.append({"frameIndex": frame, "inputs": inputs})
        expanded += 1
        if expanded > MAX_EXPANDED_ACTIONS:
            raise ScenarioScriptError("scenario script expands beyond the action limit")

    def execute(items: Sequence[object], depth: int) -> None:
        nonlocal current
        if depth > MAX_NESTING:
            raise ScenarioScriptError("scenario repeat nesting exceeds the supported depth")
        for index, raw in enumerate(items):
            if not isinstance(raw, dict) or len(raw) != 1:
                raise ScenarioScriptError(f"scenario step {index} must contain exactly one macro")
            macro, argument = next(iter(raw.items()))
            if macro == "waitFrames":
                current += _positive(argument, f"scenario step {index} waitFrames")
                continue
            if macro == "repeat":
                if not isinstance(argument, dict) or set(argument) != {"count", "steps"}:
                    raise ScenarioScriptError("repeat requires only count and steps")
                count = _positive(argument["count"], "repeat count")
                nested = argument["steps"]
                if not isinstance(nested, list) or not nested:
                    raise ScenarioScriptError("repeat steps must be a nonempty array")
                for _ in range(count):
                    execute(nested, depth + 1)
                continue
            if macro not in {"tap", "hold", "chord"} or not isinstance(argument, dict):
                raise ScenarioScriptError(f"unsupported scenario macro {macro!r}")
            allowed = {"inputs", "holdFrames", "releaseFrames"}
            if set(argument) - allowed:
                raise ScenarioScriptError(f"{macro} contains unsupported fields")
            pressed = _inputs(argument.get("inputs"), macro, chord=macro == "chord")
            default_hold = 1
            hold = _positive(argument.get("holdFrames", default_hold), f"{macro} holdFrames")
            release = _positive(argument.get("releaseFrames", 2), f"{macro} releaseFrames")
            append(current, pressed)
            current += hold
            append(current, [])
            current += release

    execute(steps, 0)
    total_frames = current + tail_frames
    if total_frames > MAX_TOTAL_FRAMES:
        raise ScenarioScriptError("scenario script exceeds the maximum frame count")
    plan = {
        "schema": "swan-song-frame-input-plan-v1",
        "totalFrames": total_frames,
        "events": events,
    }
    path = source or Path("<scenario-script>")
    validate_plan(plan, path)
    validate_play_readiness(plan, path, ready)
    canonical = json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
    return {
        "schema": REPORT_SCHEMA,
        "source": str(source) if source is not None else None,
        "readyFrames": ready,
        "expandedActions": expanded,
        "gameplayEvidence": False,
        "planSHA256": hashlib.sha256(canonical).hexdigest(),
        "plan": plan,
    }
