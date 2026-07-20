from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

from swansong_sdk.generator import (
    GenerationError, asset_report, compile_assets, generate, validate_budgets,
)
from swansong_sdk.manifest import load_manifest
from swansong_sdk.scaffold import create_project


SDK_ROOT = Path(__file__).resolve().parents[2]


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
                project / "build/generated/sources.mk",
                project / "build/generated/authoring-report.json",
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
            sources = (project / "build/generated/sources.mk").read_text()
            self.assertIn("build/generated/src/swan_assets.c", sources)
            self.assertIn("build/generated/src/swan_config.c", sources)
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

    def test_play_contract_carries_validated_semantic_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(
                "outcome-contract-output", "arcade-action", Path(temporary) / "project"
            )
            outcomes = project / "tests/outcomes"
            outcomes.mkdir()
            (outcomes / "neutral.json").write_text(json.dumps({
                "schema": "swan-scenario-outcome-contract-v1",
                "final": {"scene": 0, "progress": 0},
                "reset": {"expectation": "none"},
                "audio": {"expectation": "audible", "markerMask": 1},
            }))
            manifest_path = project / "swan.toml"
            manifest_path.write_text(manifest_path.read_text().replace(
                'plan = "tests/play/neutral.json"',
                'plan = "tests/play/neutral.json"\n'
                'outcome = "tests/outcomes/neutral.json"',
                1,
            ))
            generate(load_manifest(manifest_path))
            contract = json.loads(
                (project / "build/generated/play-contract.json").read_text()
            )
            neutral = contract["scenarios"][0]
            self.assertTrue(neutral["requiresRuntimeTrace"])
            self.assertEqual(neutral["outcomeContract"]["final"]["scene"], 0)
            self.assertEqual(contract["deterministicTrace"]["sceneIds"], {
                "play": 1, "title": 0,
            })
            graph = json.loads(
                (project / "build/generated/input-graph.json").read_text()
            )
            outcome_node = next(
                item for item in graph["nodes"]
                if item["path"] == "tests/outcomes/neutral.json"
            )
            self.assertEqual(outcome_node["kind"], "scenario-outcome")
            self.assertEqual(
                outcome_node["outputs"], ["build/generated/play-contract.json"]
            )
            self.assertRegex(neutral["planSHA256"], r"^[0-9a-f]{64}$")

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
            first_report = json.loads(
                (project / "build/generated/asset-report.json").read_text()
            )
            self.assertEqual(first_report["assets"][-1]["conversionCache"], "miss")
            self.assertIn(b"generated by SwanSong SDK through Wonderful wf-process", before)
            self.assertIn(b"swan_asset_checker_tiles", before)
            self.assertNotIn(b"autogenerated by wf-process on", before)
            generate(load_manifest(manifest_path))
            self.assertEqual(before, output.read_bytes())
            second_report = json.loads(
                (project / "build/generated/asset-report.json").read_text()
            )
            self.assertEqual(second_report["assets"][-1]["conversionCache"], "hit")
            payload = self._diagnostic_png()
            body = b"cache\0miss"
            ancillary = (
                struct.pack(">I", len(body)) + b"tEXt" + body +
                struct.pack(">I", zlib.crc32(b"tEXt" + body) & 0xFFFFFFFF)
            )
            source.write_bytes(payload[:-12] + ancillary + payload[-12:])
            generate(load_manifest(manifest_path))
            third_report = json.loads(
                (project / "build/generated/asset-report.json").read_text()
            )
            self.assertEqual(third_report["assets"][-1]["conversionCache"], "miss")

    def test_all_recipe_host_tests_compile_and_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for recipe in ("arcade-action", "menu-puzzle", "grid-tactics", "utility-app"):
                project = create_project(f"host-{recipe}", recipe, root / recipe)
                subprocess.run(["make", "clean"], cwd=project, check=True, capture_output=True, text=True)
                subprocess.run(["make", "test"], cwd=project, check=True, capture_output=True, text=True)

    def test_recipes_preserve_runtime_and_render_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(
                "responsive-utility", "utility-app", Path(temporary) / "project"
            )
            makefile = (project / "Makefile").read_text()
            game = (project / "src/game.c").read_text()
            self.assertIn(
                "$(SWANSONG_RUNTIME): $(SWANSONG_RUNTIME_SOURCES)", makefile
            )
            self.assertIn(
                "$(ELF_STAGE1): force $(OBJS) $(SWANSONG_RUNTIME)", makefile
            )
            self.assertEqual(
                game.count("swan_gfx_fill(0, 0, 0, 28, 18"), 1
            )
            self.assertIn("if (!scene_background_ready)", game)
            self.assertIn("model.dirty ? 3 : 1", game)

    def test_authored_c_sources_are_discovered_and_listed_for_first_build(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(
                "authored-output", "arcade-action", Path(temporary) / "project"
            )
            authoring = project / "authoring"
            authoring.mkdir()
            authoring_document = authoring / "night.palette.json"
            authoring_document.write_text(json.dumps({
                "schema": "swansong-author-palette-v1",
                "id": "night-palette",
                "colors": ["#000000", "#224466", "#88AACC", "#FFFFFF"],
                "monoMapping": [0, 1, 2, 3],
                "transparentIndex": None,
            }))
            generate(load_manifest(project / "swan.toml"))
            generated_source = (
                project / "build/generated/src/swan_author_night_palette.c"
            )
            generated_header = (
                project / "build/generated/include/swan_author_night_palette.h"
            )
            sources = (project / "build/generated/sources.mk").read_text()
            report = json.loads(
                (project / "build/generated/authoring-report.json").read_text()
            )
            self.assertTrue(generated_source.is_file())
            self.assertTrue(generated_header.is_file())
            self.assertIn(
                "build/generated/src/swan_author_night_palette.c", sources
            )
            self.assertEqual(report["documents"][0]["kind"], "palette")
            makefile = (project / "Makefile").read_text()
            self.assertIn("-include $(GENERATED_SOURCES_MK)", makefile)
            self.assertIn("assets: $(GENERATED_SOURCES_MK)", makefile)
            if Path("/opt/wonderful/target/wswan/medium/makedefs.mk").is_file():
                environment = os.environ.copy()
                environment["PYTHONPATH"] = str(SDK_ROOT / "python")
                environment["SWAN"] = f"{sys.executable} -m swansong_sdk.cli"
                environment["SWANSONG_SDK_DIR"] = str(SDK_ROOT)
                subprocess.run(
                    ["make", "clean"], cwd=project, env=environment,
                    check=True, capture_output=True, text=True,
                )
                build = subprocess.run(
                    ["make", "all"], cwd=project, env=environment,
                    check=False, capture_output=True, text=True,
                )
                self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
                self.assertTrue((
                    project / "build/obj/tiles1024-trace0-64/build/generated/src/"
                    "swan_author_night_palette.c.o"
                ).is_file())
                authored = json.loads(authoring_document.read_text())
                authored["colors"][1] = "#336699"
                authoring_document.write_text(json.dumps(authored))
                rebuild = subprocess.run(
                    ["make", "all"], cwd=project, env=environment,
                    check=False, capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(rebuild.returncode, 0, rebuild.stdout + rebuild.stderr)
                self.assertIn(
                    "0x0963u", generated_source.read_text()
                )
                trace_build = subprocess.run(
                    ["make", "SWAN_TRACE=1", "all"], cwd=project,
                    env=environment, check=False, capture_output=True, text=True,
                    timeout=30,
                )
                self.assertEqual(
                    trace_build.returncode, 0,
                    trace_build.stdout + trace_build.stderr,
                )
                release_rebuild = subprocess.run(
                    ["make", "all"], cwd=project, env=environment,
                    check=False, capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(
                    release_rebuild.returncode, 0,
                    release_rebuild.stdout + release_rebuild.stderr,
                )


if __name__ == "__main__":
    unittest.main()
