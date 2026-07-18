from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from swansong_sdk.plans import (
    PlanError, load_plan, validate_plan, validate_play_readiness,
)


class PlanTests(unittest.TestCase):
    def test_accepts_exact_frame_plan_with_two_neutral_frames(self) -> None:
        plan = {
            "schema": "swan-song-frame-input-plan-v1",
            "totalFrames": 20,
            "events": [
                {"frameIndex": 0, "inputs": []},
                {"frameIndex": 10, "inputs": ["a"]},
                {"frameIndex": 11, "inputs": []},
                {"frameIndex": 13, "inputs": ["x2"]},
            ],
        }
        self.assertIs(validate_plan(plan, Path("valid.json")), plan)

    def test_accepts_recorded_rapid_press_after_one_neutral_frame(self) -> None:
        plan = {
            "schema": "swan-song-frame-input-plan-v1",
            "totalFrames": 20,
            "events": [
                {"frameIndex": 0, "inputs": []},
                {"frameIndex": 10, "inputs": ["a"]},
                {"frameIndex": 11, "inputs": []},
                {"frameIndex": 12, "inputs": ["x2"]},
            ],
        }
        self.assertIs(validate_plan(plan, Path("rapid.json")), plan)

    def test_play_readiness_uses_first_non_neutral_input(self) -> None:
        plan = {
            "schema": "swan-song-frame-input-plan-v1",
            "totalFrames": 30,
            "events": [
                {"frameIndex": 0, "inputs": []},
                {"frameIndex": 8, "inputs": []},
                {"frameIndex": 12, "inputs": ["a"]},
                {"frameIndex": 13, "inputs": []},
            ],
        }
        path = Path("ready.json")
        self.assertIs(validate_play_readiness(plan, path, 12), plan)
        with self.assertRaisesRegex(
            PlanError,
            r"first non-neutral input at frame 12 is before play\.ready_frames 13",
        ):
            validate_play_readiness(plan, path, 13)

        neutral = {
            "schema": "swan-song-frame-input-plan-v1",
            "totalFrames": 10,
            "events": [{"frameIndex": 0, "inputs": []}],
        }
        self.assertIs(validate_play_readiness(neutral, path, 120), neutral)

    def test_rejects_unknown_inputs_and_non_neutral_boot(self) -> None:
        with self.assertRaisesRegex(PlanError, "neutral frame 0"):
            validate_plan({
                "schema": "swan-song-frame-input-plan-v1",
                "totalFrames": 2,
                "events": [{"frameIndex": 0, "inputs": ["a"]}],
            }, Path("boot.json"))
        with self.assertRaisesRegex(PlanError, "invalid or duplicate"):
            validate_plan({
                "schema": "swan-song-frame-input-plan-v1",
                "totalFrames": 2,
                "events": [{"frameIndex": 0, "inputs": []},
                           {"frameIndex": 1, "inputs": ["select"]}],
            }, Path("input.json"))

    def test_load_rejects_missing_invalid_and_escaped_plans(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            with self.assertRaisesRegex(PlanError, "does not exist"):
                load_plan(root, "missing.json")
            invalid = root / "invalid.json"
            invalid.write_text("not json")
            with self.assertRaisesRegex(PlanError, "invalid JSON"):
                load_plan(root, "invalid.json")
            outside = root.parent / "outside-plan.json"
            outside.write_text(json.dumps({}))
            try:
                with self.assertRaisesRegex(PlanError, "outside the project"):
                    load_plan(root, "../outside-plan.json")
            finally:
                outside.unlink(missing_ok=True)

    def test_load_applies_optional_readiness_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            path = root / "early.json"
            path.write_text(json.dumps({
                "schema": "swan-song-frame-input-plan-v1",
                "totalFrames": 20,
                "events": [
                    {"frameIndex": 0, "inputs": []},
                    {"frameIndex": 10, "inputs": ["a"]},
                ],
            }))
            load_plan(root, "early.json", ready_frames=10)
            with self.assertRaisesRegex(PlanError, "play.ready_frames 11"):
                load_plan(root, "early.json", ready_frames=11)


if __name__ == "__main__":
    unittest.main()
