from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
import wave

from swansong_sdk.evidence import validate_wav
from swansong_sdk.minimize import (
    FailureObservation, MinimizeError, json_pointer, minimize_plan,
    observe_evidence, validate_failure_predicate,
)
from swansong_sdk.optimize import encode_rgba_png
from swansong_sdk.png2bpp import Image
from swansong_sdk.replay import (
    ReplayError, build_replay_report, evidence_binding, validate_checkpoints,
)


def _plan() -> dict[str, object]:
    return {
        "schema": "swan-song-frame-input-plan-v1",
        "totalFrames": 10,
        "events": [
            {"frameIndex": 0, "inputs": []},
            {"frameIndex": 2, "inputs": ["a"]},
            {"frameIndex": 4, "inputs": []},
            {"frameIndex": 6, "inputs": ["b", "x2"]},
            {"frameIndex": 8, "inputs": []},
        ],
    }


def _effective_inputs(plan: dict[str, object]) -> list[tuple[str, ...]]:
    events = plan["events"]
    result: list[tuple[str, ...]] = []
    cursor = 0
    state: tuple[str, ...] = ()
    for frame in range(plan["totalFrames"]):
        if cursor < len(events) and events[cursor]["frameIndex"] == frame:
            state = tuple(events[cursor]["inputs"])
            cursor += 1
        result.append(state)
    return result


def _write_evidence(directory: Path) -> None:
    directory.mkdir()
    directory.joinpath("frame.png").write_bytes(encode_rgba_png(Image(
        2, 1, ((0, 0, 0, 255), (255, 255, 255, 255)),
    )))
    with wave.open(str(directory / "audio.wav"), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8_000)
        output.writeframes(b"\x00\x00\x01\x00")
    directory.joinpath("evidence.json").write_text(json.dumps({
        "finalGameRasterSHA256": "abc", "framesExecuted": 10,
        "nested": {"not": "copied into scalar summary"},
    }) + "\n")


class MinimizeTests(unittest.TestCase):
    def test_validates_predicates_and_rfc6901_paths(self) -> None:
        predicate = validate_failure_predicate({
            "schema": "swansong-failure-predicate-v1",
            "kind": "structured-evidence",
            "path": "/failure/code",
            "equals": "stuck",
        })
        observation = observe_evidence(predicate, {
            "failure": {"code": "stuck"}, "a/b": {"~key": 7},
        })
        self.assertTrue(observation.matched)
        self.assertEqual(json_pointer({"a/b": {"~key": 7}}, "/a~1b/~0key"), (True, 7))
        with self.assertRaisesRegex(MinimizeError, "messageEquals"):
            validate_failure_predicate({
                "schema": "swansong-failure-predicate-v1",
                "kind": "execution-error", "messageContains": "crash",
            })
        with self.assertRaisesRegex(MinimizeError, "invalid RFC 6901 escape"):
            validate_failure_predicate({
                "schema": "swansong-failure-predicate-v1",
                "kind": "structured-evidence", "path": "/bad~2path", "equals": 1,
            })

    def test_delta_reduction_is_deterministic_and_removes_chord_atoms(self) -> None:
        calls: list[dict[str, object]] = []

        def evaluator(candidate: dict[str, object]) -> FailureObservation:
            calls.append(candidate)
            matched = any("b" in inputs for inputs in _effective_inputs(candidate))
            return FailureObservation(matched, {"failure": "b-held" if matched else None})

        first, first_report = minimize_plan(_plan(), evaluator)
        second, second_report = minimize_plan(_plan(), evaluator)
        self.assertEqual(first, second)
        self.assertEqual(first["totalFrames"], 2)
        self.assertEqual(first["events"], [
            {"frameIndex": 0, "inputs": []},
            {"frameIndex": 1, "inputs": ["b"]},
        ])
        for key in ("source", "minimized", "evaluations", "cacheHits", "reductions"):
            self.assertEqual(first_report[key], second_report[key])
        self.assertLess(first_report["minimized"]["inputFrameAtoms"],
                        first_report["source"]["inputFrameAtoms"])

    def test_rejects_nonmatching_source_and_honors_evaluation_budget(self) -> None:
        def no_failure(unused: dict[str, object]) -> FailureObservation:
            return FailureObservation(False, {"failure": None})

        with self.assertRaisesRegex(MinimizeError, "does not match"):
            minimize_plan(_plan(), no_failure)

        def always(candidate: dict[str, object]) -> FailureObservation:
            return FailureObservation(True, {"frames": candidate["totalFrames"]})

        minimized, report = minimize_plan(_plan(), always, maximum_evaluations=1)
        self.assertEqual(minimized, _plan())
        self.assertEqual(report["evaluations"], 1)
        self.assertTrue(report["limitReached"])

    def test_source_plan_is_not_silently_normalized_past_its_predicate(self) -> None:
        source = {
            "schema": "swan-song-frame-input-plan-v1", "totalFrames": 5,
            "events": [
                {"frameIndex": 0, "inputs": []},
                {"frameIndex": 1, "inputs": ["a"]},
                {"frameIndex": 2, "inputs": ["a"]},
                {"frameIndex": 4, "inputs": []},
            ],
        }

        def exact_event_count(candidate: dict[str, object]) -> FailureObservation:
            count = len(candidate["events"])
            return FailureObservation(count == 4, {"eventCount": count})

        minimized, report = minimize_plan(source, exact_event_count)
        self.assertEqual(minimized, source)
        self.assertEqual(report["source"]["eventCount"], 4)
        self.assertEqual(report["source"]["sha256"], report["minimized"]["sha256"])


class ReplayTests(unittest.TestCase):
    def test_builds_timeline_with_checkpoints_evidence_and_trace_summaries(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "evidence"
            _write_evidence(directory)
            binding = evidence_binding("failure", directory)
            checkpoints = {
                "schema": "swansong-replay-checkpoints-v1",
                "checkpoints": [{
                    "id": "stuck-state", "frameIndex": 7,
                    "label": "Movement stops", "requiredCheck": "player can move",
                    "evidence": ["failure"],
                }],
            }
            trace = {"schema": "example-trace-v1", "frames": [{
                "frameIndex": 7, "state": "stuck", "sprites": [{}, {}],
                "dirtyPixels": 0,
            }]}
            report = build_replay_report(
                _plan(), checkpoints=checkpoints, evidence=[binding], trace=trace,
                scenario={"id": "failure", "requiredChecks": ["player can move"]},
            )
            self.assertEqual(report["schema"], "swansong-replay-report-v1")
            point = next(item for item in report["timeline"] if item["frameIndex"] == 7)
            self.assertEqual(point["inputs"], ["b", "x2"])
            self.assertEqual(point["evidence"], ["failure"])
            self.assertEqual(point["traceSummary"]["fields"]["state"], "stuck")
            self.assertEqual(point["traceSummary"]["collectionCounts"]["sprites"], 2)
            self.assertEqual(report["unboundEvidence"], [])
            self.assertEqual(binding["png"]["width"], 2)
            self.assertEqual(binding["wav"]["sampleFrames"], 2)
            validate_wav(directory / "audio.wav")

    def test_rejects_out_of_range_checkpoints_and_unknown_evidence(self) -> None:
        with self.assertRaisesRegex(ReplayError, "within the plan"):
            validate_checkpoints({
                "schema": "swansong-replay-checkpoints-v1",
                "checkpoints": [{"id": "late", "frameIndex": 10, "label": "Late"}],
            }, total_frames=10)
        with self.assertRaisesRegex(ReplayError, "unknown evidence"):
            build_replay_report(_plan(), checkpoints={
                "schema": "swansong-replay-checkpoints-v1",
                "checkpoints": [{
                    "id": "failure", "frameIndex": 7, "label": "Failure",
                    "evidence": ["missing"],
                }],
            })


if __name__ == "__main__":
    unittest.main()
