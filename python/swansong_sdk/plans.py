"""Validation for SwanSong's checked-in exact-frame input plans."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


INPUTS = {"x1", "x2", "x3", "x4", "y1", "y2", "y3", "y4", "a", "b", "start"}


class PlanError(ValueError):
    pass


def validate_plan(plan: object, path: Path) -> dict[str, Any]:
    if not isinstance(plan, dict) or plan.get("schema") != "swan-song-frame-input-plan-v1":
        raise PlanError(f"play plan must use swan-song-frame-input-plan-v1: {path}")
    total = plan.get("totalFrames")
    events = plan.get("events")
    if not isinstance(total, int) or isinstance(total, bool) or total <= 0:
        raise PlanError(f"play plan totalFrames must be a positive integer: {path}")
    if not isinstance(events, list) or not events:
        raise PlanError(f"play plan events must be a nonempty array: {path}")
    previous = -1
    for index, event in enumerate(events):
        if not isinstance(event, dict) or set(event) != {"frameIndex", "inputs"}:
            raise PlanError(f"play plan event {index} must contain only frameIndex and inputs: {path}")
        frame = event.get("frameIndex")
        inputs = event.get("inputs")
        if not isinstance(frame, int) or isinstance(frame, bool) or not previous < frame < total:
            raise PlanError(f"play plan event {index} frameIndex must increase and be within totalFrames: {path}")
        if (not isinstance(inputs, list) or
                not all(isinstance(value, str) and value in INPUTS for value in inputs) or
                len(inputs) != len(set(inputs))):
            raise PlanError(f"play plan event {index} has invalid or duplicate inputs: {path}")
        previous = frame
    first = events[0]
    if first["frameIndex"] != 0 or first["inputs"]:
        raise PlanError(f"play plan must begin with a neutral frame 0 event: {path}")
    return plan


def validate_play_readiness(plan: dict[str, Any], path: Path,
                            ready_frames: int) -> dict[str, Any]:
    """Reject gameplay input sent before a project's boot/intro safe point."""

    for event in plan["events"]:
        if event["inputs"]:
            frame = event["frameIndex"]
            if frame < ready_frames:
                raise PlanError(
                    f"play plan first non-neutral input at frame {frame} is before "
                    f"play.ready_frames {ready_frames}: {path}"
                )
            break
    return plan


def load_plan(root: Path, relative: str, *,
              ready_frames: int | None = None) -> tuple[Path, dict[str, Any]]:
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise PlanError(f"play plan points outside the project: {relative}") from exc
    try:
        raw = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise PlanError(f"play plan does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PlanError(f"invalid JSON play plan {path}: {exc}") from exc
    plan = validate_plan(raw, path)
    if ready_frames is not None:
        validate_play_readiness(plan, path, ready_frames)
    return path, plan


def load_plan_file(path: Path) -> tuple[Path, dict[str, Any]]:
    """Load an explicitly selected plan without applying project-relative policy."""

    resolved = path.resolve()
    try:
        raw = json.loads(resolved.read_text())
    except FileNotFoundError as exc:
        raise PlanError(f"play plan does not exist: {resolved}") from exc
    except json.JSONDecodeError as exc:
        raise PlanError(f"invalid JSON play plan {resolved}: {exc}") from exc
    return resolved, validate_plan(raw, resolved)
