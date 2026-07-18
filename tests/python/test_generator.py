from __future__ import annotations

import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib

from swansong_sdk.generator import (
    GenerationError, asset_report, compile_assets, generate, validate_budgets,
)
from swansong_sdk.manifest import load_manifest
from swansong_sdk.scaffold import create_project


class GeneratorTests(unittest.TestCase):
    @staticmethod
    def _diagnostic_png() -> bytes:
        def chunk(kind: bytes, payload: bytes) -> bytes:
            return (struct.pack(">I", len(payload)) + kind + payload +
                    struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))
        rows = b"".join(
            b"\x00" + b"".join(
                (b"\xff\xff\xff\xff" if (x + y) % 2 else b"\x00\x00\x00\xff")
                for x in range(8)
            )
            for y in range(8)
        )
        return (b"\x89PNG\r\n\x1a\n" +
                chunk(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 6, 0, 0, 0)) +
                chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))

    def test_generation_is_deterministic_and_complete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project("generated-game", "arcade-action", Path(temporary) / "project")
            manifest = load_manifest(project / "swan.toml")
            generate(manifest)
            expected = (
                project / "wfconfig.toml",
                project / "build/generated/include/swan_project.h",
                project / "build/generated/include/swan_controls.h",
                project / "build/generated/include/swan_assets.h",
                project / "build/generated/include/swan_resources.h",
                project / "build/generated/src/swan_config.c",
                project / "build/generated/play-contract.json",
                project / "build/generated/asset-report.json",
                project / "build/generated/docs/controls.md",
            )
            before = {path: path.read_bytes() for path in expected}
            generate(manifest)
            self.assertEqual(before, {path: path.read_bytes() for path in expected})
            contract = json.loads((project / "build/generated/play-contract.json").read_text())
            self.assertEqual(contract["schema"], "swan-song-game-contract-v1")
            self.assertEqual(contract["readyFrames"], 120)
            self.assertTrue(all(scenario["freshBoot"] for scenario in contract["scenarios"]))
            report = json.loads((project / "build/generated/asset-report.json").read_text())
            self.assertTrue(all(scene["vramTiles"] >= 6 for scene in report["sceneUsage"]))
            self.assertTrue(all(scene["palettes"] >= 1 for scene in report["sceneUsage"]))
            controls = (project / "build/generated/include/swan_controls.h").read_text()
            self.assertIn("#define SWAN_PRIMARY_UP (SWAN_KEY_X3)", controls)
            self.assertIn("#define SWAN_SECONDARY_LEFT (SWAN_KEY_Y1)", controls)
            manifest_path = project / "swan.toml"
            manifest_path.write_text(manifest_path.read_text().replace(
                'orientation = "horizontal"', 'orientation = "vertical"'))
            generate(load_manifest(manifest_path))
            vertical_controls = (project / "build/generated/include/swan_controls.h").read_text()
            self.assertIn("#define SWAN_PRIMARY_UP (SWAN_KEY_Y2)", vertical_controls)
            self.assertIn("#define SWAN_SECONDARY_LEFT (SWAN_KEY_X4)", vertical_controls)

    def test_generation_rejects_scenario_input_before_ready_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(
                "early-game", "arcade-action", Path(temporary) / "project"
            )
            plan = project / "tests/play/interaction.json"
            plan.write_text(plan.read_text().replace(
                '"frameIndex": 120, "inputs": ["a"]',
                '"frameIndex": 119, "inputs": ["a"]',
                1,
            ))
            with self.assertRaisesRegex(
                GenerationError,
                r"first non-neutral input at frame 119 is before "
                r"play\.ready_frames 120",
            ):
                generate(load_manifest(project / "swan.toml"))

    def test_budget_failure_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project("budget-game", "grid-tactics", Path(temporary) / "project")
            path = project / "swan.toml"
            path.write_text(path.read_text().replace("sprites = 64", "sprites = 1", 1))
            manifest = load_manifest(path)
            compiled = compile_assets(manifest)
            failures = validate_budgets(manifest, asset_report(manifest, compiled))
            self.assertTrue(any("sprites" in failure for failure in failures))

    def test_play_contract_carries_declared_audio_evidence_limits(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(
                "audio-contract-output", "arcade-action", Path(temporary) / "project"
            )
            manifest_path = project / "swan.toml"
            manifest_path.write_text(manifest_path.read_text().replace(
                'audio_expectation = "audible"',
                'audio_expectation = "audible"\n\n'
                '[play.scenarios.audio_evidence]\n'
                'signal_floor = 0.01\n'
                'max_stereo_balance_delta = 0.1',
                1,
            ))
            generate(load_manifest(manifest_path))
            contract = json.loads(
                (project / "build/generated/play-contract.json").read_text()
            )
            audio = contract["scenarios"][0]["audioEvidence"]
            self.assertEqual(audio["signalFloor"], 0.01)
            self.assertEqual(audio["maxStereoBalanceDelta"], 0.1)

    def test_input_gestures_and_chords_are_generated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project("gesture-output", "arcade-action", Path(temporary) / "project")
            manifest_path = project / "swan.toml"
            manifest_path.write_text(manifest_path.read_text() + """

[controls.gestures]
tap_max_frames = 4
double_tap_window = 7
hold_threshold = 15

[controls.chords]
move_fire = ["left", "confirm"]
""")
            generate(load_manifest(manifest_path))
            controls = (project / "build/generated/include/swan_controls.h").read_text()
            source = (project / "build/generated/src/swan_config.c").read_text()
            documentation = (project / "build/generated/docs/controls.md").read_text()
            contract = json.loads(
                (project / "build/generated/play-contract.json").read_text()
            )
            self.assertIn("SWAN_CHORD_MOVE_FIRE = 0", controls)
            self.assertIn("SWAN_CHORD_COUNT = 1", controls)
            self.assertIn("(1u << SWAN_ACTION_LEFT)", source)
            self.assertIn("(1u << SWAN_ACTION_CONFIRM)", source)
            self.assertIn(".tap_max_frames = 4", source)
            self.assertIn(".double_tap_window = 7", source)
            self.assertIn(".hold_threshold = 15", source)
            self.assertIn("| `move_fire` | left + confirm |", documentation)
            self.assertEqual(contract["inputGestures"], {
                "tapMaxFrames": 4,
                "doubleTapWindow": 7,
                "holdThreshold": 15,
                "chords": {"move_fire": ["left", "confirm"]},
                "sameFrameChords": True,
            })
            subprocess.run([
                "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-c",
                "-I", str(Path(__file__).resolve().parents[2] / "include"),
                "-I", str(project / "build/generated/include"),
                "-o", str(project / "build/gesture-config.o"),
                str(project / "build/generated/src/swan_config.c"),
            ], check=True, capture_output=True, text=True)

    @unittest.skipUnless(
        Path("/opt/wonderful/bin/wf-process").is_file() or shutil.which("wf-process"),
        "Wonderful wf-process is not installed",
    )
    def test_graphics_are_emitted_by_wonderful_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project("wonderful-art", "menu-puzzle", Path(temporary) / "project")
            source = project / "assets" / "checker.png"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(self._diagnostic_png())
            manifest_path = project / "swan.toml"
            manifest_path.write_text(manifest_path.read_text() + """

[[assets]]
id = "checker"
type = "tilemap"
source = "assets/checker.png"
group = "common"
""")
            generate(load_manifest(manifest_path))
            output = project / "build/generated/src/swan_asset_checker_wonderful.c"
            before = output.read_bytes()
            self.assertIn(b"generated by SwanSong SDK through Wonderful wf-process", before)
            self.assertIn(b"swan_asset_checker_tiles", before)
            self.assertNotIn(b"autogenerated by wf-process on", before)
            generate(load_manifest(manifest_path))
            self.assertEqual(before, output.read_bytes())

    def test_all_recipe_host_tests_compile_and_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for recipe in ("arcade-action", "menu-puzzle", "grid-tactics", "utility-app"):
                project = create_project(f"host-{recipe}", recipe, root / recipe)
                subprocess.run(["make", "clean"], cwd=project, check=True, capture_output=True, text=True)
                subprocess.run(["make", "test"], cwd=project, check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
