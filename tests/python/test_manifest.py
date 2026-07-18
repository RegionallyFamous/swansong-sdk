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
            for recipe in ("arcade-action", "menu-puzzle", "grid-tactics"):
                project = create_project(f"test-{recipe}", recipe, root / recipe)
                manifest = load_manifest(project / "swan.toml")
                self.assertEqual(manifest.template, recipe)
                self.assertEqual(manifest.sdk_version, "0.2.0")
                self.assertRegex(manifest.sdk_revision or "", r"^sha256:[0-9a-f]{64}$")
                self.assertGreaterEqual(len(manifest.play_scenarios), 4)
                self.assertEqual(manifest.rom_name, f"test_{recipe.replace('-', '_')}.wsc")

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


if __name__ == "__main__":
    unittest.main()
