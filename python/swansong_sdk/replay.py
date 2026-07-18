"""Read-only replay timeline reports over checked SwanSong artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from .evidence import EvidenceError, validate_wav
from .minimize import canonical_digest
from .plans import validate_plan
from .png2bpp import PNGError, read_png


CHECKPOINT_SCHEMA = "swansong-replay-checkpoints-v1"
REPORT_SCHEMA = "swansong-replay-report-v1"
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9-]{0,63}$")


class ReplayError(ValueError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_checkpoints(value: object, *, total_frames: int,
                         path: Path = Path("<checkpoints>")) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema") != CHECKPOINT_SCHEMA:
        raise ReplayError(f"replay checkpoints must use {CHECKPOINT_SCHEMA}: {path}")
    if set(value) != {"schema", "checkpoints"} or not isinstance(value["checkpoints"], list):
        raise ReplayError("replay checkpoints require only schema and checkpoints")
    seen: set[str] = set()
    previous = -1
    for index, item in enumerate(value["checkpoints"]):
        if not isinstance(item, dict):
            raise ReplayError(f"checkpoint {index} must be an object")
        required = {"id", "frameIndex", "label"}
        allowed = required | {"requiredCheck", "evidence"}
        if not required <= set(item) or set(item) - allowed:
            raise ReplayError(f"checkpoint {index} has invalid fields")
        identifier = item["id"]
        frame = item["frameIndex"]
        label = item["label"]
        if not isinstance(identifier, str) or not _IDENTIFIER.fullmatch(identifier) or identifier in seen:
            raise ReplayError(f"checkpoint {index} id must be unique lowercase kebab-case")
        if not isinstance(frame, int) or isinstance(frame, bool) or not previous <= frame < total_frames:
            raise ReplayError(f"checkpoint {index} frameIndex must be ordered and within the plan")
        if not isinstance(label, str) or not label.strip():
            raise ReplayError(f"checkpoint {index} label must be nonempty")
        if "requiredCheck" in item and (not isinstance(item["requiredCheck"], str) or not item["requiredCheck"].strip()):
            raise ReplayError(f"checkpoint {index} requiredCheck must be nonempty")
        evidence = item.get("evidence", [])
        if (not isinstance(evidence, list) or
                not all(isinstance(name, str) and _IDENTIFIER.fullmatch(name) for name in evidence) or
                len(evidence) != len(set(evidence))):
            raise ReplayError(f"checkpoint {index} evidence must contain unique evidence ids")
        seen.add(identifier)
        previous = frame
    return value


def input_segments(plan: Mapping[str, Any]) -> list[dict[str, Any]]:
    events = plan["events"]
    total = int(plan["totalFrames"])
    return [{
        "startFrame": event["frameIndex"],
        "endFrameExclusive": (
            events[index + 1]["frameIndex"] if index + 1 < len(events) else total
        ),
        "inputs": list(event["inputs"]),
    } for index, event in enumerate(events)]


def _trace_summary(frame: Mapping[str, Any]) -> dict[str, Any]:
    scalars: dict[str, Any] = {}
    collection_counts: dict[str, int] = {}
    for key in sorted(frame):
        if key == "frameIndex":
            continue
        value = frame[key]
        if value is None or isinstance(value, (bool, int, float, str)):
            scalars[key] = value
        elif isinstance(value, (list, dict)):
            collection_counts[key] = len(value)
    result: dict[str, Any] = {"fields": scalars}
    if collection_counts:
        result["collectionCounts"] = collection_counts
    return result


def validate_trace(value: object, *, total_frames: int,
                   path: Path = Path("<trace>")) -> tuple[list[Mapping[str, Any]], dict[str, Any]]:
    if not isinstance(value, Mapping) or not isinstance(value.get("frames"), list):
        raise ReplayError(f"replay trace must be an object with a frames array: {path}")
    frames = value["frames"]
    previous = -1
    summaries: list[Mapping[str, Any]] = []
    for position, frame in enumerate(frames):
        if not isinstance(frame, Mapping):
            raise ReplayError(f"trace frame {position} must be an object")
        index = frame.get("frameIndex")
        if not isinstance(index, int) or isinstance(index, bool) or not previous < index < total_frames:
            raise ReplayError("trace frameIndex values must strictly increase within the plan")
        summaries.append({"frameIndex": index, **_trace_summary(frame)})
        previous = index
    metadata = {
        "schema": value.get("schema"),
        "sha256": canonical_digest(value),
        "frames": len(frames),
        "firstFrame": frames[0]["frameIndex"] if frames else None,
        "lastFrame": frames[-1]["frameIndex"] if frames else None,
    }
    return summaries, metadata


def evidence_binding(identifier: str, directory: Path) -> dict[str, Any]:
    if not _IDENTIFIER.fullmatch(identifier):
        raise ReplayError(f"evidence id must be lowercase kebab-case: {identifier!r}")
    resolved = directory.resolve()
    png = resolved / "frame.png"
    wav = resolved / "audio.wav"
    structured_path = resolved / "evidence.json"
    missing = [item.name for item in (png, wav, structured_path) if not item.is_file()]
    if missing:
        raise ReplayError(f"evidence {identifier} is missing: {', '.join(missing)}")
    try:
        image = read_png(png)
        audio = validate_wav(wav)
        structured = json.loads(structured_path.read_text())
    except (OSError, json.JSONDecodeError, PNGError, EvidenceError) as exc:
        raise ReplayError(f"invalid evidence {identifier}: {exc}") from exc
    if not isinstance(structured, dict):
        raise ReplayError(f"evidence {identifier} evidence.json must contain one object")
    scalar_summary = {
        key: value for key, value in sorted(structured.items())
        if value is None or isinstance(value, (bool, int, float, str))
    }
    return {
        "id": identifier,
        "directory": str(resolved),
        "png": {"sha256": _sha256(png), "width": image.width, "height": image.height},
        "wav": {
            "sha256": _sha256(wav),
            "channels": audio["channels"],
            "sampleRate": audio["sampleRate"],
            "sampleWidthBytes": audio["sampleWidthBytes"],
            "sampleFrames": audio["frameCount"],
        },
        "structured": {"sha256": _sha256(structured_path), "summary": scalar_summary},
    }


def build_replay_report(plan: Mapping[str, Any], *,
                        checkpoints: Mapping[str, Any] | None = None,
                        evidence: Sequence[Mapping[str, Any]] = (),
                        trace: Mapping[str, Any] | None = None,
                        scenario: Mapping[str, Any] | None = None,
                        ) -> dict[str, Any]:
    checked = validate_plan(dict(plan), Path("<replay-plan>"))
    total = int(checked["totalFrames"])
    checkpoint_contract = validate_checkpoints(
        checkpoints or {"schema": CHECKPOINT_SCHEMA, "checkpoints": []},
        total_frames=total,
    )
    evidence_by_id: dict[str, Mapping[str, Any]] = {}
    for binding in evidence:
        identifier = binding.get("id")
        if not isinstance(identifier, str) or identifier in evidence_by_id:
            raise ReplayError("evidence bindings must have unique string ids")
        evidence_by_id[identifier] = binding
    referenced: set[str] = set()
    points: dict[int, dict[str, Any]] = {}
    for event in checked["events"]:
        points[event["frameIndex"]] = {
            "frameIndex": event["frameIndex"],
            "inputs": list(event["inputs"]),
            "inputChanged": True,
            "checkpoints": [],
            "evidence": [],
        }
    for checkpoint in checkpoint_contract["checkpoints"]:
        point = points.setdefault(checkpoint["frameIndex"], {
            "frameIndex": checkpoint["frameIndex"],
            "inputs": None,
            "inputChanged": False,
            "checkpoints": [],
            "evidence": [],
        })
        point["checkpoints"].append(dict(checkpoint))
        for identifier in checkpoint.get("evidence", []):
            if identifier not in evidence_by_id:
                raise ReplayError(
                    f"checkpoint {checkpoint['id']} references unknown evidence {identifier}"
                )
            if identifier not in point["evidence"]:
                point["evidence"].append(identifier)
            referenced.add(identifier)
    trace_metadata = None
    if trace is not None:
        summaries, trace_metadata = validate_trace(trace, total_frames=total)
        for summary in summaries:
            point = points.setdefault(summary["frameIndex"], {
                "frameIndex": summary["frameIndex"],
                "inputs": None,
                "inputChanged": False,
                "checkpoints": [],
                "evidence": [],
            })
            point["traceSummary"] = {
                key: value for key, value in summary.items() if key != "frameIndex"
            }
    segments = input_segments(checked)
    segment_index = 0
    for frame_index in sorted(points):
        while (segment_index + 1 < len(segments) and
               segments[segment_index + 1]["startFrame"] <= frame_index):
            segment_index += 1
        if points[frame_index]["inputs"] is None:
            points[frame_index]["inputs"] = list(segments[segment_index]["inputs"])
    scenario_value = dict(scenario) if scenario is not None else None
    return {
        "schema": REPORT_SCHEMA,
        "ok": True,
        "plan": {
            "schema": checked["schema"],
            "sha256": canonical_digest(checked),
            "totalFrames": total,
            "eventCount": len(checked["events"]),
        },
        "scenario": scenario_value,
        "inputSegments": segments,
        "checkpoints": [dict(item) for item in checkpoint_contract["checkpoints"]],
        "evidenceBindings": [dict(evidence_by_id[key]) for key in sorted(evidence_by_id)],
        "unboundEvidence": sorted(set(evidence_by_id) - referenced),
        "trace": trace_metadata,
        "timeline": [points[key] for key in sorted(points)],
    }
