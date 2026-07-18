from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest import mock

from swansong_sdk.authoring import (
    HANDOFF_SCHEMA, KINDS, AuthoringError, canonical_digest, default_document,
    document_report, export_document, validate_document,
)
from swansong_sdk.cli import main
from swansong_sdk.generator import _compile_audio
from swansong_sdk.manifest import Asset
from swansong_sdk.png2bpp import read_png


def _project(root: Path) -> Path:
    project = root / "author-game"
    with redirect_stdout(StringIO()):
        status = main([
            "new", "author-game", "--template", "arcade-action",
            "--directory", str(project),
        ])
    if status != 0:
        raise AssertionError("could not scaffold authoring fixture")
    return project


def _json_command(arguments: list[str]) -> tuple[int, dict[str, object]]:
    output = StringIO()
    with redirect_stdout(output), redirect_stderr(StringIO()):
        status = main([*arguments, "--json"])
    return status, json.loads(output.getvalue())


class AuthoringDocumentTests(unittest.TestCase):
    def test_every_default_is_valid_deterministic_and_non_evidentiary(self) -> None:
        for kind in KINDS:
            with self.subTest(kind=kind):
                first = default_document(kind, f"sample-{kind}")
                second = default_document(kind, f"sample-{kind}")
                self.assertEqual(first, second)
                self.assertIs(validate_document(first), first)
                report = document_report(first)
                self.assertEqual(report["kind"], kind)
                self.assertIsInstance(report["metrics"], dict)
                payload, export = export_document(first)
                replay_payload, replay_export = export_document(second)
                self.assertEqual((payload, export), (replay_payload, replay_export))
                self.assertTrue(payload)
                self.assertEqual(len(payload), export["bytes"])
                self.assertEqual(len(export["sha256"]), 64)

    def test_tilemap_bounds_layers_duplicates_and_source_path(self) -> None:
        document = default_document("tilemap", "world-map")
        document["layers"][0]["cells"] = [{
            "x": 0, "y": 0, "tile": 7, "palette": 1,
            "flipX": False, "flipY": True,
        }]
        report = document_report(document)
        self.assertEqual(report["metrics"]["placedCells"], 1)
        self.assertEqual(report["metrics"]["highestTile"], 7)
        duplicate = deepcopy(document)
        duplicate["layers"][0]["cells"].append(dict(duplicate["layers"][0]["cells"][0]))
        with self.assertRaisesRegex(AuthoringError, "duplicate cell"):
            validate_document(duplicate)
        escaped = deepcopy(document)
        escaped["tilesetSource"] = "../outside.png"
        with self.assertRaisesRegex(AuthoringError, "project-relative"):
            validate_document(escaped)
        windows_absolute = deepcopy(document)
        windows_absolute["tilesetSource"] = "C:/outside.png"
        with self.assertRaisesRegex(AuthoringError, "project-relative"):
            validate_document(windows_absolute)
        too_many = deepcopy(document)
        too_many["layers"] *= 3
        with self.assertRaisesRegex(AuthoringError, "1..2"):
            validate_document(too_many)

    def test_sprite_references_animation_steps_and_hitboxes(self) -> None:
        document = default_document("sprites", "pilot-sprites")
        report = document_report(document)
        self.assertEqual(report["metrics"]["animationDurationFrames"], 8)
        broken = deepcopy(document)
        broken["animations"][0]["steps"][0]["frame"] = "missing"
        with self.assertRaisesRegex(AuthoringError, "unknown frame"):
            validate_document(broken)
        broken = deepcopy(document)
        broken["hitboxes"][0]["width"] = 0
        with self.assertRaisesRegex(AuthoringError, "1 to 65535"):
            validate_document(broken)

    def test_palette_mapping_and_png_export(self) -> None:
        document = default_document("palette", "night-palette")
        payload, metadata = export_document(document)
        self.assertEqual(metadata["requiredSuffix"], ".png")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "palette.png"
            path.write_bytes(payload)
            image = read_png(path)
        self.assertEqual((image.width, image.height), (32, 8))
        mismatch = deepcopy(document)
        mismatch["monoMapping"].pop()
        with self.assertRaisesRegex(AuthoringError, "4..4"):
            validate_document(mismatch)

    def test_collision_scene_flow_and_non_executable_fields(self) -> None:
        collision = default_document("collision", "world-collision")
        collision["regions"] = [{
            "id": "wall", "kind": "solid", "closed": True,
            "points": [{"x": 0, "y": 0}, {"x": 10, "y": 0}, {"x": 10, "y": 10}],
        }]
        self.assertEqual(document_report(collision)["metrics"]["regionPoints"], 3)
        outside = deepcopy(collision)
        outside["regions"][0]["points"][2]["x"] = 224
        with self.assertRaisesRegex(AuthoringError, "0 to 223"):
            validate_document(outside)

        flow = default_document("scene-flow", "main-flow")
        flow["scenes"].append({"id": "play", "title": "Play"})
        findings = document_report(flow)["findings"]
        self.assertEqual(findings[0]["code"], "unreachable-scene")
        flow["transitions"] = [{
            "id": "begin", "from": "title", "to": "play",
            "event": "confirm", "argument": 0,
        }]
        self.assertEqual(document_report(flow)["findings"], [])
        executable = deepcopy(flow)
        executable["transitions"][0]["command"] = "run anything"
        with self.assertRaisesRegex(AuthoringError, "contain exactly"):
            validate_document(executable)

    def test_audio_export_is_accepted_by_existing_sdk_compiler(self) -> None:
        document = default_document("audio", "flight-theme")
        payload, metadata = export_document(document)
        self.assertEqual(metadata["integration"], {
            "status": "sdk-consumable", "manifestAssetType": "music",
        })
        parsed = tomllib.loads(payload.decode())
        self.assertEqual(parsed["rows"][0]["channels"][1], [254, 254, 254])
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "theme.toml"
            path.write_bytes(payload)
            compiled = _compile_audio(Asset("theme", "music", "theme.toml"), path)
        self.assertEqual(compiled["type"], "music")
        self.assertEqual(len(compiled["instruments"]), 1)
        invalid = deepcopy(document)
        invalid["rows"][0]["channels"][0]["instrument"] = "missing"
        with self.assertRaisesRegex(AuthoringError, "unknown instrument"):
            validate_document(invalid)

    def test_handoffs_are_hash_bound_and_never_evidence(self) -> None:
        for kind in ("tilemap", "sprites", "collision", "scene-flow"):
            with self.subTest(kind=kind):
                document = default_document(kind, f"handoff-{kind}")
                payload, metadata = export_document(document)
                handoff = json.loads(payload)
                self.assertEqual(handoff["schema"], HANDOFF_SCHEMA)
                self.assertEqual(handoff["sourceSHA256"], canonical_digest(document))
                self.assertFalse(handoff["gameplayEvidence"])
                self.assertEqual(metadata["integration"]["status"], "handoff-required")


class AuthoringCliTests(unittest.TestCase):
    def test_create_validate_report_and_export_all_kinds(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = _project(Path(temporary))
            manifest = str(project / "swan.toml")
            for kind in KINDS:
                identifier = f"editor-{kind}"
                create_status, created = _json_command([
                    "author", "create", kind, identifier, "--project", manifest,
                ])
                self.assertEqual(create_status, 0, kind)
                self.assertFalse(created["gameplayEvidence"])
                document = project / "authoring" / f"{identifier}.{kind}.json"
                validate_status, validated = _json_command([
                    "author", "validate", str(document), "--project", manifest,
                ])
                self.assertEqual(validate_status, 0, kind)
                self.assertEqual(validated["documentSHA256"], created["documentSHA256"])
                suffix = {"audio": ".toml", "palette": ".png"}.get(kind, ".json")
                output = project / "exports" / f"{identifier}{suffix}"
                export_status, exported = _json_command([
                    "author", "export", str(document), "--project", manifest,
                    "--output", str(output),
                ])
                self.assertEqual(export_status, 0, kind)
                self.assertTrue(output.is_file())
                self.assertFalse(exported["gameplayEvidence"])

    def test_never_overwrites_documents_reports_or_exports(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = _project(Path(temporary))
            manifest = str(project / "swan.toml")
            document = project / "authoring" / "map.tilemap.json"
            document.parent.mkdir()
            document.write_text("keep me")
            status, report = _json_command([
                "author", "create", "tilemap", "map", "--project", manifest,
                "--output", str(document),
            ])
            self.assertEqual(status, 2)
            self.assertFalse(report["gameplayEvidence"])
            self.assertEqual(document.read_text(), "keep me")

            source = project / "authoring" / "theme.audio.json"
            source.write_text(json.dumps(default_document("audio", "theme")))
            output = project / "assets" / "audio" / "theme.toml"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("existing source")
            status, _ = _json_command([
                "author", "export", str(source), "--project", manifest,
                "--output", str(output),
            ])
            self.assertEqual(status, 2)
            self.assertEqual(output.read_text(), "existing source")

            report_path = project / "authoring" / "report.json"
            report_path.write_text("existing report")
            status, _ = _json_command([
                "author", "report", str(source), "--project", manifest,
                "--output", str(report_path),
            ])
            self.assertEqual(status, 2)
            self.assertEqual(report_path.read_text(), "existing report")

    def test_rejects_project_escape_absolute_paths_symlinks_and_bad_suffixes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = _project(root)
            manifest = str(project / "swan.toml")
            outside = root / "outside"
            outside.mkdir()
            status, report = _json_command([
                "author", "create", "palette", "escape", "--project", manifest,
                "--output", "../escape.json",
            ])
            self.assertEqual(status, 2)
            self.assertIn("project root", report["error"]["message"])
            status, _ = _json_command([
                "author", "create", "palette", "absolute", "--project", manifest,
                "--output", str(outside / "absolute.json"),
            ])
            self.assertEqual(status, 2)
            outside_document = outside / "outside.json"
            outside_document.write_text(json.dumps(default_document("palette", "outside")))
            status, _ = _json_command([
                "author", "validate", str(outside_document), "--project", manifest,
            ])
            self.assertEqual(status, 2)
            link = project / "linked-outside"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except OSError:
                pass
            else:
                status, _ = _json_command([
                    "author", "create", "palette", "linked", "--project", manifest,
                    "--output", "linked-outside/linked.json",
                ])
                self.assertEqual(status, 2)
                self.assertFalse((outside / "linked.json").exists())

            document = project / "authoring" / "palette.palette.json"
            document.parent.mkdir(exist_ok=True)
            document.write_text(json.dumps(default_document("palette", "palette")))
            status, _ = _json_command([
                "author", "export", str(document), "--project", manifest,
                "--output", "exports/palette.json",
            ])
            self.assertEqual(status, 2)
            self.assertFalse((project / "exports/palette.json").exists())

    def test_report_file_matches_machine_report_and_errors_are_stable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = _project(Path(temporary))
            manifest = str(project / "swan.toml")
            document = project / "authoring" / "flow.scene-flow.json"
            document.parent.mkdir()
            document.write_text(json.dumps(default_document("scene-flow", "flow")))
            output = project / "authoring" / "flow-report.json"
            status, report = _json_command([
                "author", "report", str(document), "--project", manifest,
                "--output", str(output),
            ])
            self.assertEqual(status, 0)
            self.assertEqual(json.loads(output.read_text()), report)
            status, error = _json_command([
                "author", "validate", "missing.json", "--project", manifest,
            ])
            self.assertEqual(status, 2)
            self.assertEqual(error["schema"], "swansong-author-operation-report-v1")
            self.assertEqual(error["operation"], "validate")
            self.assertFalse(error["gameplayEvidence"])

    def test_author_operations_do_not_invoke_external_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = _project(Path(temporary))
            manifest = str(project / "swan.toml")
            with mock.patch("subprocess.run", side_effect=AssertionError("must not run")):
                status, created = _json_command([
                    "author", "create", "audio", "quiet-theme", "--project", manifest,
                ])
                self.assertEqual(status, 0)
                document = Path(created["document"])
                status, _ = _json_command([
                    "author", "export", str(document), "--project", manifest,
                    "--output", "assets/audio/quiet-theme.toml",
                ])
                self.assertEqual(status, 0)


if __name__ == "__main__":
    unittest.main()
