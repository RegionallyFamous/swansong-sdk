from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import wave

from swansong_sdk.cli import main
from swansong_sdk.optimize import encode_rgba_png
from swansong_sdk.png2bpp import Image
from swansong_sdk.swansong import SwanSongError


def _new_project(root: Path) -> Path:
    project = root / "tool-game"
    with redirect_stdout(StringIO()):
        status = main([
            "new", "tool-game", "--template", "menu-puzzle",
            "--directory", str(project),
        ])
    if status != 0:
        raise AssertionError("could not create CLI fixture project")
    return project


def _json_command(arguments: list[str]) -> tuple[int, dict[str, object]]:
    output = StringIO()
    with redirect_stdout(output):
        status = main([*arguments, "--json"])
    return status, json.loads(output.getvalue())


def _write_evidence(directory: Path, *, color: int, sample: int) -> None:
    directory.mkdir(parents=True)
    directory.joinpath("frame.png").write_bytes(encode_rgba_png(Image(
        1, 1, ((color, 0, 0, 255),),
    )))
    with wave.open(str(directory / "audio.wav"), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8_000)
        output.writeframes(sample.to_bytes(2, "little", signed=True))
    directory.joinpath("evidence.json").write_text(
        json.dumps({"frame": 1, "marker": color}, sort_keys=True) + "\n"
    )


class ToolCliTests(unittest.TestCase):
    def test_scenario_record_writes_editable_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = _new_project(Path(temporary))
            log = project / "input-log.json"
            log.write_text(json.dumps({
                "schema": "swan-song-input-frame-log-v2",
                "droppedFrameCount": 0,
                "totalFrameCount": 4,
                "frames": [
                    {"sequenceIndex": 0, "effectiveInputs": []},
                    {"sequenceIndex": 1, "effectiveInputs": ["A"]},
                    {"sequenceIndex": 2, "effectiveInputs": []},
                    {"sequenceIndex": 3, "effectiveInputs": []},
                ],
            }))
            status, report = _json_command([
                "scenario-record", "--project", str(project / "swan.toml"),
                "--input-log", str(log), "--output", "plans/recorded.json",
            ])
            self.assertEqual(status, 0)
            self.assertEqual(report["schema"], "swansong-scenario-record-report-v1")
            plan = json.loads((project / "plans/recorded.json").read_text())
            self.assertEqual(plan["events"][1], {"frameIndex": 1, "inputs": ["a"]})

    def test_evidence_diff_decodes_media_and_can_fail_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            before, after = root / "before", root / "after"
            _write_evidence(before, color=0, sample=0)
            _write_evidence(after, color=255, sample=100)
            status, report = _json_command([
                "evidence-diff", "--before", str(before), "--after", str(after),
                "--fail-on-difference",
            ])
            self.assertEqual(status, 1)
            self.assertEqual(report["schema"], "swansong-evidence-diff-v1")
            self.assertEqual(report["png"]["changedPixels"], 1)
            self.assertEqual(report["wav"]["changedSamples"], 1)

    def test_corrupt_evidence_png_returns_stable_json_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            before, after = root / "before", root / "after"
            _write_evidence(before, color=0, sample=0)
            _write_evidence(after, color=0, sample=0)
            after.joinpath("frame.png").write_bytes(b"not a png")
            status, report = _json_command([
                "evidence-diff", "--before", str(before), "--after", str(after),
            ])
            self.assertEqual(status, 2)
            self.assertEqual(report["schema"], "swansong-evidence-diff-v1")
            self.assertFalse(report["ok"])

    def test_fuzz_generate_only_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = _new_project(Path(temporary))
            arguments = [
                "fuzz", "--project", str(project / "swan.toml"),
                "--seed", "41", "--cases", "2", "--frames", "100",
                "--generate-only",
            ]
            first_status, first = _json_command(arguments)
            second_status, second = _json_command(arguments)
            self.assertEqual((first_status, second_status), (0, 0))
            self.assertEqual(first, second)
            self.assertEqual(first["schema"], "swansong-fuzz-report-v1")
            self.assertEqual(len(first["cases"]), 2)

    def test_fuzz_executes_baseline_and_cases_through_swansong(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = _new_project(Path(temporary))
            (project / "tool_game.wsc").write_bytes(b"ROM")
            calls: list[dict[str, object]] = []

            def fake_play(unused_rom, plan, *, output, verify_replay):
                self.assertTrue(verify_replay)
                calls.append(plan)
                return {"finalGameRasterSHA256": str(len(calls))}

            with mock.patch("swansong_sdk.cli.play", side_effect=fake_play):
                status, report = _json_command([
                    "fuzz", "--project", str(project / "swan.toml"),
                    "--seed", "9", "--cases", "2", "--frames", "100",
                ])
            self.assertEqual(status, 0)
            self.assertEqual(len(calls), 3)
            self.assertEqual(report["mode"], "swansong-execution")
            self.assertEqual(report["verdict"], "review")
            self.assertEqual(report["cases"][0]["status"], "needs-observation")

    def test_fuzz_baseline_failure_stays_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = _new_project(Path(temporary))
            (project / "tool_game.wsc").write_bytes(b"ROM")
            with mock.patch(
                "swansong_sdk.cli.play",
                side_effect=SwanSongError("fresh-boot replay diverged"),
            ):
                status, report = _json_command([
                    "fuzz", "--project", str(project / "swan.toml"),
                    "--cases", "1", "--frames", "100",
                ])
            self.assertEqual(status, 2)
            self.assertEqual(report["schema"], "swansong-fuzz-report-v1")
            self.assertEqual(report["verdict"], "fail")
            self.assertEqual(
                report["findings"][0]["code"],
                "baseline-execution-or-reset-divergence",
            )

    def test_profile_optimize_and_laboratory_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = _new_project(Path(temporary))
            manifest = str(project / "swan.toml")
            profile_status, profile = _json_command([
                "profile", "--project", manifest,
            ])
            optimize_status, optimize = _json_command([
                "optimize", "--project", manifest,
            ])
            lab_status, lab = _json_command([
                "lab", "--project", manifest, "--case", "rtc",
                "--rtc-seed", "1710000000",
            ])
            self.assertEqual((profile_status, optimize_status, lab_status), (0, 0, 0))
            self.assertEqual(profile["schema"], "swansong-profile-report-v1")
            self.assertEqual(optimize["schema"], "swansong-asset-optimization-report-v1")
            self.assertEqual(lab["schema"], "swansong-laboratory-report-v1")
            self.assertEqual(lab["saveCases"], [])
            self.assertEqual(lab["rtcSeedUnix"], 1710000000)


if __name__ == "__main__":
    unittest.main()
