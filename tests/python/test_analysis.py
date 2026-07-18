from __future__ import annotations

import base64
import json
from pathlib import Path
import tempfile
import unittest
import wave

from swansong_sdk.evidence import EvidenceThresholds, diff_evidence, diff_png, diff_wav
from swansong_sdk.fuzzing import evaluate_trace, generate_fuzz_plan
from swansong_sdk.laboratory import JournalModel, run_laboratory
from swansong_sdk.optimize import encode_rgba_png, preview_asset_optimization
from swansong_sdk.plans import validate_plan
from swansong_sdk.png2bpp import Image, read_png
from swansong_sdk.profiler import profile_resources
from swansong_sdk.scenario import (
    ScenarioError,
    ScenarioRecording,
    record_frame_log,
    record_transitions,
)


def _write_wave(path: Path, samples: list[int]) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b"".join(value.to_bytes(2, "little", signed=True)
                                    for value in samples))


class ScenarioTests(unittest.TestCase):
    def test_imports_desktop_frame_log_and_compresses_transitions(self) -> None:
        states = [[], ["A"], ["a"], [], ["X2"], []]
        log = {
            "schema": "swan-song-input-frame-log-v2",
            "droppedFrameCount": 0,
            "totalFrameCount": len(states),
            "frames": [
                {"sequenceIndex": index, "effectiveInputs": inputs}
                for index, inputs in enumerate(states)
            ],
        }
        report = record_frame_log(log)
        self.assertEqual(report["schema"], "swansong-scenario-record-report-v1")
        self.assertEqual(report["plan"]["events"], [
            {"frameIndex": 0, "inputs": []},
            {"frameIndex": 1, "inputs": ["a"]},
            {"frameIndex": 3, "inputs": []},
            {"frameIndex": 4, "inputs": ["x2"]},
            {"frameIndex": 5, "inputs": []},
        ])
        validate_plan(report["plan"], Path("frame-log.json"))

    def test_frame_log_rejects_drops_and_noncontiguous_frames(self) -> None:
        log = {
            "schema": "swan-song-input-frame-log-v2",
            "droppedFrameCount": 1,
            "totalFrameCount": 1,
            "frames": [{"sequenceIndex": 0, "effectiveInputs": []}],
        }
        with self.assertRaisesRegex(ScenarioError, "dropped"):
            record_frame_log(log)
        log["droppedFrameCount"] = 0
        log["frames"][0]["sequenceIndex"] = 1
        with self.assertRaisesRegex(ScenarioError, "contiguous"):
            record_frame_log(log)

    def test_pressed_first_frame_is_shifted_behind_neutral_boot(self) -> None:
        log = {
            "schema": "swan-song-input-frame-log-v2",
            "droppedFrameCount": 0,
            "totalFrameCount": 3,
            "frames": [
                {"sequenceIndex": 0, "effectiveInputs": ["B"]},
                {"sequenceIndex": 1, "effectiveInputs": []},
                {"sequenceIndex": 2, "effectiveInputs": []},
            ],
        }
        plan = record_frame_log(log)["plan"]
        self.assertEqual(plan["totalFrames"], 4)
        self.assertEqual(plan["events"][:3], [
            {"frameIndex": 0, "inputs": []},
            {"frameIndex": 1, "inputs": ["b"]},
            {"frameIndex": 2, "inputs": []},
        ])

    def test_actual_rapid_press_release_press_is_preserved(self) -> None:
        states = [[], ["a"], [], ["b"], []]
        report = record_frame_log({
            "schema": "swan-song-input-frame-log-v2",
            "droppedFrameCount": 0,
            "totalFrameCount": len(states),
            "frames": [
                {"sequenceIndex": index, "effectiveInputs": inputs}
                for index, inputs in enumerate(states)
            ],
        })
        self.assertEqual(report["plan"]["events"], [
            {"frameIndex": 0, "inputs": []},
            {"frameIndex": 1, "inputs": ["a"]},
            {"frameIndex": 2, "inputs": []},
            {"frameIndex": 3, "inputs": ["b"]},
            {"frameIndex": 4, "inputs": []},
        ])

    def test_timestamp_recording_is_editable(self) -> None:
        recording = ScenarioRecording(refresh_numerator=75, refresh_denominator=1)
        event = recording.record(["START"], timestamp_ms=100)
        self.assertEqual(event.frame_index, 7)
        recording.edit(7, inputs=["a"], new_frame_index=8)
        recording.record([], frame_index=9)
        report = recording.to_dict(total_frames=12)
        self.assertEqual(report["plan"]["events"][1],
                         {"frameIndex": 8, "inputs": ["a"]})
        self.assertEqual(record_transitions([
            {"frameIndex": 3, "inputs": ["X1"]},
            {"frameIndex": 4, "inputs": []},
        ], total_frames=5)["plan"]["events"][1]["inputs"], ["x1"])


class EvidenceTests(unittest.TestCase):
    def test_png_pixel_metrics_and_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            left = Image(2, 1, ((0, 0, 0, 255), (0, 0, 0, 255)))
            right = Image(2, 1, ((0, 0, 0, 255), (255, 0, 0, 255)))
            before = root / "before.png"
            after = root / "after.png"
            before.write_bytes(encode_rgba_png(left))
            after.write_bytes(encode_rgba_png(right))
            strict = diff_png(before, after)
            tolerant = diff_png(
                before, after,
                EvidenceThresholds(changed_pixel_ratio=0.5),
            )
            self.assertEqual(strict["changedPixels"], 1)
            self.assertEqual(strict["changedBounds"],
                             {"x": 1, "y": 0, "width": 1, "height": 1})
            self.assertTrue(strict["meaningfulDifference"])
            self.assertFalse(tolerant["meaningfulDifference"])

    def test_wav_pcm_amplitude_and_structured_diff(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            before = root / "before.wav"
            after = root / "after.wav"
            _write_wave(before, [0, 100, -100, 0])
            _write_wave(after, [0, 100, -50, 0])
            audio = diff_wav(before, after)
            self.assertEqual(audio["changedSamples"], 1)
            self.assertEqual(audio["maximumSampleDelta"], 50)
            result = diff_evidence(
                before_wav=before,
                after_wav=after,
                before_metadata={"raster": "one", "frame": 10},
                after_metadata={"raster": "two", "frame": 10},
            ).to_dict()
            self.assertEqual(result["schema"], "swansong-evidence-diff-v1")
            self.assertTrue(result["meaningfulDifference"])
            self.assertEqual(result["metadata"]["changes"][0]["path"], "$.raster")
            json.dumps(result, sort_keys=True)

    def test_structured_diff_detects_added_empty_container(self) -> None:
        from swansong_sdk.evidence import diff_metadata

        result = diff_metadata({}, {"extra": {}})
        self.assertTrue(result["meaningfulDifference"])
        self.assertIn("$.extra", {change["path"] for change in result["changes"]})


class FuzzTests(unittest.TestCase):
    def test_generation_is_deterministic_and_plan_valid(self) -> None:
        first = generate_fuzz_plan(seed=99, total_frames=180).to_dict()
        second = generate_fuzz_plan(seed=99, total_frames=180).to_dict()
        self.assertEqual(first, second)
        self.assertEqual(first["schema"], "swansong-fuzz-report-v1")
        validate_plan(first["plan"], Path("fuzz.json"))

    def test_trace_verdict_reports_declared_failures(self) -> None:
        trace = {
            "status": "crash",
            "crash": {"panic": 7},
            "frames": [
                {"frameIndex": 0, "state": "title", "progressMarker": "zero"},
                {"frameIndex": 1, "state": "play", "progressMarker": "stuck",
                 "inputs": ["a"]},
                {"frameIndex": 121, "state": "broken", "progressMarker": "stuck"},
            ],
            "resetChecks": [{"baseline": {"score": 0}, "actual": {"score": 1}}],
        }
        report = evaluate_trace(
            trace,
            allowed_transitions={"title": ["play"], "play": ["result"]},
            dead_end_frames=100,
        ).to_dict()
        self.assertEqual(report["verdict"], "fail")
        self.assertEqual(
            {finding["code"] for finding in report["findings"]},
            {"execution-failure", "invalid-transition", "dead-end", "reset-divergence"},
        )


class ProfilerTests(unittest.TestCase):
    def test_accepts_per_scanline_aggregate_array(self) -> None:
        report = profile_resources(
            report={"budgets": {"sprites_per_scanline": 4}},
            trace={"frames": [{
                "frameIndex": 2,
                "spritesVisible": 3,
                "spritesPerScanline": [1, 7, 3],
            }]},
        ).to_dict()
        self.assertEqual(report["peaks"]["spritesPerScanline"], 7)
        self.assertIn(
            "sprite-scanline-budget",
            {finding["code"] for finding in report["findings"]},
        )

    def test_profiles_trace_and_static_scene_budgets(self) -> None:
        report = profile_resources(
            report={
                "budgets": {
                    "vram_tiles": 4, "palettes": 2, "sprites": 2,
                    "sprites_per_scanline": 1,
                },
                "sceneUsage": [{"scene": "large", "vramTiles": 5, "palettes": 3}],
            },
            trace={"frames": [{
                "frameIndex": 9,
                "tiles": [0, 1, 2, 3, 4],
                "palettes": [0, 1, 2],
                "sprites": [
                    {"x": 0, "y": 10, "tile": 1, "palette": 0},
                    {"x": 8, "y": 10, "tile": 2, "palette": 1},
                ],
                "dirtyRegions": [{"x": 0, "y": 0, "width": 224, "height": 144}],
                "frameTimeUs": 14000,
            }]},
        ).to_dict()
        self.assertEqual(report["schema"], "swansong-profile-report-v1")
        self.assertEqual(report["peaks"]["spritesPerScanline"], 2)
        codes = {finding["code"] for finding in report["findings"]}
        self.assertTrue({
            "vram-tile-budget", "palette-budget", "sprite-scanline-budget",
            "dirty-region-pressure", "frame-time-budget",
        }.issubset(codes))


class OptimizationTests(unittest.TestCase):
    def test_flip_dedupe_palette_reduction_and_mono_preview(self) -> None:
        colors = [
            (0, 0, 0, 255), (255, 0, 0, 255), (0, 255, 0, 255),
            (0, 0, 255, 255), (255, 255, 255, 255),
        ]
        left = tuple(colors[(x + y) % len(colors)] for y in range(8) for x in range(8))
        rows = [left[offset:offset + 8] for offset in range(0, 64, 8)]
        right = tuple(color for row in rows for color in reversed(row))
        pixels = tuple(
            color
            for y in range(8)
            for color in (left[y * 8:(y + 1) * 8] + right[y * 8:(y + 1) * 8])
        )
        report = preview_asset_optimization(Image(16, 8, pixels)).to_dict()
        asset = report["assets"][0]
        self.assertEqual(report["schema"], "swansong-asset-optimization-report-v1")
        self.assertEqual(asset["tiles"]["sourceTiles"], 2)
        self.assertEqual(asset["tiles"]["exactUnique"], 2)
        self.assertEqual(asset["tiles"]["flipUnique"], 1)
        self.assertEqual(asset["palette"]["uniqueRgbaColors"], 5)
        self.assertEqual(asset["palette"]["recommendations"][0]["severity"], "required")
        with tempfile.TemporaryDirectory() as temporary:
            preview = Path(temporary) / "mono.png"
            preview.write_bytes(base64.b64decode(asset["monoVariant"]["pngBase64"]))
            self.assertEqual((read_png(preview).width, read_png(preview).height), (16, 8))


class LaboratoryTests(unittest.TestCase):
    def test_default_save_and_rtc_matrix_passes(self) -> None:
        report = run_laboratory().to_dict()
        self.assertEqual(report["schema"], "swansong-laboratory-report-v1")
        self.assertTrue(report["passed"])
        self.assertEqual(
            {case["id"] for case in report["saveCases"]},
            {"empty-media", "corrupt-newest-slot", "interrupted-commit",
             "schema-mismatch", "capacity-failure"},
        )
        self.assertIn("time-travel", {case["id"] for case in report["rtcCases"]})
        json.dumps(report, sort_keys=True)

    def test_seeded_rtc_uses_sunday_zero_weekday(self) -> None:
        report = run_laboratory(rtc_seed_unix=1709164800).to_dict()
        fixed = next(case for case in report["rtcCases"] if case["id"] == "fixed-time")
        # 2024-02-29 is Thursday: Sunday=0 encodes it as 4.
        self.assertEqual(fixed["observed"]["datetime"]["weekday"], 4)

    def test_journal_model_recovers_previous_valid_slot(self) -> None:
        journal = JournalModel(256)
        first = journal.store(7, b"one")
        second = journal.store(7, b"two")
        self.assertEqual((first.slot, second.slot), (0, 1))
        assert second.slot is not None
        journal.corrupt_payload(second.slot)
        loaded = journal.load(expected_schema=7)
        self.assertEqual((loaded.status, loaded.payload, loaded.generation),
                         ("ok", b"one", 1))


if __name__ == "__main__":
    unittest.main()
