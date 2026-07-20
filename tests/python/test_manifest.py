from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from swansong_sdk.manifest import ManifestError, find_manifest, load_manifest
from swansong_sdk.scaffold import create_project


class ManifestTests(unittest.TestCase):
    def test_every_recipe_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for recipe in ("arcade-action", "menu-puzzle", "grid-tactics", "utility-app"):
                project = create_project(f"test-{recipe}", recipe, root / recipe)
                manifest = load_manifest(project / "swan.toml")
                self.assertEqual(manifest.template, recipe)
                self.assertEqual(
                    manifest.play_ready_frames,
                    180 if recipe == "utility-app" else 120,
                )
                self.assertEqual(manifest.sdk_version, "0.5.0")
                self.assertRegex(manifest.sdk_revision or "", r"^sha256:[0-9a-f]{64}$")
                self.assertGreaterEqual(len(manifest.play_scenarios), 4)
                self.assertTrue(all(
                    item.audio_expectation in {"audible", "silent", "any"}
                    for item in manifest.play_scenarios
                ))
                self.assertEqual(manifest.rom_name, f"test_{recipe.replace('-', '_')}.wsc")

    def test_play_readiness_defaults_for_existing_projects_and_is_validated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(
                "ready-game", "arcade-action", Path(temporary) / "project"
            )
            path = project / "swan.toml"
            explicit = path.read_text()
            path.write_text(explicit.replace("[play]\nready_frames = 120\n\n", ""))
            self.assertEqual(load_manifest(path).play_ready_frames, 60)

            path.write_text(explicit.replace("ready_frames = 120", "ready_frames = 0"))
            with self.assertRaisesRegex(ManifestError, "greater than zero"):
                load_manifest(path)

            path.write_text(explicit.replace("ready_frames = 120", "ready_frames = true"))
            with self.assertRaisesRegex(ManifestError, "must be an integer"):
                load_manifest(path)

    def test_finds_manifest_in_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project("find-me", "arcade-action", Path(temporary) / "project")
            child = project / "one" / "two"
            child.mkdir(parents=True)
            self.assertEqual(find_manifest(child), project / "swan.toml")

    def test_rejects_unknown_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project("bad-input", "arcade-action", Path(temporary) / "project")
            path = project / "swan.toml"
            path.write_text(path.read_text().replace('left = ["X4"]', 'left = ["JOYSTICK"]'))
            with self.assertRaisesRegex(ManifestError, "unknown inputs"):
                load_manifest(path)

    def test_input_gestures_and_chords_are_validated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project("gesture-game", "arcade-action", Path(temporary) / "project")
            path = project / "swan.toml"
            path.write_text(path.read_text() + """

[controls.gestures]
tap_max_frames = 5
double_tap_window = 9
hold_threshold = 17

[controls.chords]
move_fire = ["left", "confirm"]
""")
            manifest = load_manifest(path)
            self.assertEqual(manifest.input_gestures.tap_max_frames, 5)
            self.assertEqual(manifest.input_gestures.double_tap_window, 9)
            self.assertEqual(manifest.input_gestures.hold_threshold, 17)
            self.assertEqual(manifest.input_chords["move_fire"], ("left", "confirm"))

            path.write_text(path.read_text().replace(
                '["left", "confirm"]', '["left", "missing"]'
            ))
            with self.assertRaisesRegex(ManifestError, "unknown actions"):
                load_manifest(path)

    def test_rejects_invalid_gesture_capacity_and_one_action_chord(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project("bad-gesture", "arcade-action", Path(temporary) / "project")
            path = project / "swan.toml"
            original = path.read_text()
            path.write_text(original + """

[controls.gestures]
hold_threshold = 256
""")
            with self.assertRaisesRegex(ManifestError, "between 1 and 255"):
                load_manifest(path)
            path.write_text(original + """

[controls.gestures]
tap_frames = 4
""")
            with self.assertRaisesRegex(ManifestError, "unknown keys"):
                load_manifest(path)
            path.write_text(original + """

[controls.chords]
not_a_chord = ["confirm"]
""")
            with self.assertRaisesRegex(ManifestError, "at least two distinct actions"):
                load_manifest(path)
            path.write_text(original + """

[controls.chords]
duplicate = ["left", "confirm", "confirm"]
""")
            with self.assertRaisesRegex(ManifestError, "cannot repeat"):
                load_manifest(path)

            chord_lines = "\n".join(
                f'chord_{index} = ["left", "confirm"]' for index in range(9)
            )
            path.write_text(original + "\n[controls.chords]\n" + chord_lines + "\n")
            with self.assertRaisesRegex(ManifestError, "capacity of 8"):
                load_manifest(path)

    def test_rejects_release_version_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(
                "unsafe-version", "menu-puzzle", Path(temporary) / "project"
            )
            path = project / "swan.toml"
            path.write_text(path.read_text().replace(
                'version = "0.1.0"', 'version = "../../escape"', 1
            ))
            with self.assertRaisesRegex(ManifestError, "semantic version"):
                load_manifest(path)

    def test_rejects_invalid_sdk_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project("bad-sdk-pin", "menu-puzzle", Path(temporary) / "project")
            path = project / "swan.toml"
            path.write_text(path.read_text().replace("revision = \"sha256:", "revision = \"git:"))
            with self.assertRaisesRegex(ManifestError, "sdk.revision"):
                load_manifest(path)

    def test_rejects_more_than_eight_mib(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project("too-large", "arcade-action", Path(temporary) / "project")
            path = project / "swan.toml"
            path.write_text(path.read_text().replace("rom_bytes = 8388608", "rom_bytes = 8388609"))
            with self.assertRaisesRegex(ManifestError, "8 MiB"):
                load_manifest(path)

    def test_rejects_missing_initial_scene(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project("bad-scene", "arcade-action", Path(temporary) / "project")
            path = project / "swan.toml"
            path.write_text(path.read_text().replace('initial_scene = "title"', 'initial_scene = "missing"'))
            with self.assertRaisesRegex(ManifestError, "not declared"):
                load_manifest(path)

    def test_audio_expectations_and_legacy_boolean_are_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(
                "audio-contract", "arcade-action", Path(temporary) / "project"
            )
            path = project / "swan.toml"
            manifest = load_manifest(path)
            self.assertEqual(manifest.play_scenarios[0].audio_expectation, "audible")
            text = path.read_text().replace(
                'audio_expectation = "audible"', "audio = true", 1
            )
            path.write_text(text)
            self.assertEqual(
                load_manifest(path).play_scenarios[0].audio_expectation, "audible"
            )
            path.write_text(text.replace(
                "audio = true", 'audio = true\naudio_expectation = "silent"', 1
            ))
            with self.assertRaisesRegex(ManifestError, "conflict"):
                load_manifest(path)

    def test_audio_evidence_thresholds_are_typed_and_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = create_project(
                "audio-thresholds", "arcade-action", Path(temporary) / "project"
            )
            path = project / "swan.toml"
            text = path.read_text().replace(
                'audio_expectation = "audible"',
                'audio_expectation = "audible"\n\n'
                '[play.scenarios.audio_evidence]\n'
                'signal_floor = 0.01\n'
                'max_stereo_balance_delta = 0.15\n'
                'max_cue_onset_delta_ms = 20\n'
                'max_silent_frame_ratio_increase = 0.05\n'
                'max_internal_silence_increase_ms = 12\n'
                'max_clipped_sample_ratio_increase = 0.0\n'
                'max_loop_seam_delta_increase = 0.02',
                1,
            )
            path.write_text(text)
            contract = load_manifest(path).play_scenarios[0].audio_evidence
            self.assertTrue(contract.configured)
            self.assertEqual(contract.signal_floor, 0.01)
            self.assertEqual(contract.max_cue_onset_delta_ms, 20.0)
            self.assertEqual(contract.to_contract()["maxLoopSeamDeltaIncrease"], 0.02)

            path.write_text(text.replace("signal_floor = 0.01", "signal_floor = 1.01"))
            with self.assertRaisesRegex(ManifestError, "at most 1"):
                load_manifest(path)


if __name__ == "__main__":
    unittest.main()
