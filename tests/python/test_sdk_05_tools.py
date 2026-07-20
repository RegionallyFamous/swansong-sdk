import json
from pathlib import Path
import tempfile
import unittest
import wave

from swansong_sdk.audio_workbench import (
    AudioWorkbenchError, render_music_preview, simulate_sfx_arbitration,
)
from swansong_sdk.asset_import import AssetImportError, import_asset
from swansong_sdk.budget_history import compare_resource_reports
from swansong_sdk.migration import apply_migration, plan_migration
from swansong_sdk.scenario_script import ScenarioScriptError, compile_scenario_script


MUSIC = b'''type = "music"
frames_per_row_q8 = 256
loop = true

[[instruments]]
wave = [0, 2, 4, 6, 8, 10, 12, 15, 15, 12, 10, 8, 6, 4, 2, 0]
attack = 0
release = 0

[[rows]]
channels = [[60, 0, 10], [64, 0, 8], [67, 0, 6], [72, 0, 4]]

[[rows]]
channels = [[254, 254, 254], [255, 254, 254], [254, 254, 254], [255, 254, 254]]
'''


class AudioWorkbenchTests(unittest.TestCase):
    def test_preview_is_deterministic_and_not_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.wav"
            second = Path(directory) / "second.wav"
            one = render_music_preview(MUSIC, output=first, sample_rate=8000)
            two = render_music_preview(MUSIC, output=second, sample_rate=8000)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(one["wavSHA256"], two["wavSHA256"])
            self.assertFalse(one["gameplayEvidence"])
            self.assertFalse(one["hardwareAccurate"])
            with wave.open(str(first), "rb") as source:
                self.assertEqual(source.getnchannels(), 2)
                self.assertGreater(source.getnframes(), 0)

    def test_preview_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "preview.wav"
            render_music_preview(MUSIC, output=output)
            with self.assertRaises(AudioWorkbenchError):
                render_music_preview(MUSIC, output=output)

    def test_arbitration_matches_runtime_priority_policy(self):
        report = simulate_sfx_arbitration([
            {"id": "a", "priority": 3}, {"id": "b", "priority": 4},
            {"id": "c", "priority": 5}, {"id": "d", "priority": 6},
            {"id": "weak", "priority": 2}, {"id": "strong", "priority": 9},
        ])
        self.assertFalse(report["decisions"][4]["accepted"])
        self.assertEqual(report["decisions"][5]["stolen"], "a")


class BudgetHistoryTests(unittest.TestCase):
    def test_reports_regressions_and_improvements(self):
        report = compare_resource_reports(
            {"project": "demo", "romBytes": 110, "audioBytes": 30},
            {"project": "demo", "romBytes": 100, "audioBytes": 40},
            allowed_increase={"romBytes": 5, "audioBytes": 0},
        )
        self.assertFalse(report["ok"])
        self.assertEqual(report["regressions"], ["romBytes"])


class MigrationTests(unittest.TestCase):
    def test_preview_and_atomic_apply_with_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "swan.toml"
            manifest.write_text(
                'schema_version = 1\n\n[sdk]\nversion = "0.4.0"\n'
                'revision = "sha256:' + '1' * 64 + '"\n\n[game]\nid = "demo"\n'
            )
            report = plan_migration(
                manifest, target_version="0.5.0",
                target_revision="sha256:" + "2" * 64,
            )
            self.assertTrue(report["changed"])
            self.assertIn('version = "0.4.0"', manifest.read_text())
            applied = apply_migration(report)
            self.assertTrue(applied["applied"])
            self.assertIn('version = "0.5.0"', manifest.read_text())
            self.assertTrue(Path(applied["backup"]).is_file())


class AssetImportTests(unittest.TestCase):
    def test_hash_bound_import_preserves_provenance_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            root.mkdir()
            source = Path(directory) / "shared.png"
            source.write_bytes(b"reviewed-asset")
            import hashlib
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            report = import_asset(
                root, source, "assets/shared.png", "assets/shared.provenance.json",
                expected_sha256=digest,
            )
            self.assertEqual((root / "assets/shared.png").read_bytes(), source.read_bytes())
            self.assertEqual(report["destination"]["sha256"], digest)
            self.assertFalse(report["gameplayEvidence"])
            with self.assertRaises(AssetImportError):
                import_asset(
                    root, source, "assets/shared.png", "assets/again.json",
                    expected_sha256=digest,
                )

    def test_rejects_unreviewed_or_outside_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "project"
            root.mkdir()
            source = Path(directory) / "shared.bin"
            source.write_bytes(b"bytes")
            with self.assertRaises(AssetImportError):
                import_asset(
                    root, source, "../escape.bin", "assets/report.json",
                    expected_sha256="0" * 64,
                )


class ScenarioScriptTests(unittest.TestCase):
    def test_compiles_taps_holds_chords_and_repeats(self):
        report = compile_scenario_script({
            "schema": "swansong-scenario-script-v1",
            "tailFrames": 10,
            "steps": [
                {"tap": {"inputs": ["a"]}},
                {"hold": {"inputs": ["x2"], "holdFrames": 5}},
                {"chord": {"inputs": ["start", "b"]}},
                {"repeat": {"count": 2, "steps": [
                    {"tap": {"inputs": ["x1"]}}, {"waitFrames": 3}
                ]}},
            ],
        }, ready_frames=120)
        plan = report["plan"]
        self.assertFalse(report["gameplayEvidence"])
        self.assertEqual(plan["events"][1], {"frameIndex": 120, "inputs": ["a"]})
        self.assertIn({"frameIndex": 130, "inputs": ["b", "start"]}, plan["events"])
        self.assertGreater(plan["totalFrames"], 140)

    def test_rejects_one_input_chord(self):
        with self.assertRaises(ScenarioScriptError):
            compile_scenario_script({
                "schema": "swansong-scenario-script-v1",
                "steps": [{"chord": {"inputs": ["a"]}}],
            }, ready_frames=1)


if __name__ == "__main__":
    unittest.main()
