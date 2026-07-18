from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from swansong_sdk.identity import sdk_identity
from swansong_sdk.manifest import load_manifest
from swansong_sdk.plans import load_plan
from swansong_sdk.png2bpp import read_png


ROOT = Path(__file__).parents[2]
CANARIES = {
    "dewdrop-dash": "arcade-action",
    "signal-orchard": "grid-tactics",
}


class CanaryTests(unittest.TestCase):
    def test_canaries_are_complete_recipe_projects_with_owned_art(self) -> None:
        identity = sdk_identity()
        for project_id, recipe in CANARIES.items():
            with self.subTest(project=project_id):
                root = ROOT / "examples/canaries" / project_id
                manifest = load_manifest(root / "swan.toml")
                self.assertEqual(manifest.id, project_id)
                self.assertEqual(manifest.template, recipe)
                self.assertEqual(manifest.sdk_version, identity["version"])
                self.assertEqual(manifest.sdk_revision, identity["revision"])
                self.assertEqual(len(manifest.play_scenarios), 5)
                self.assertEqual(
                    {item.id for item in manifest.play_scenarios},
                    {"neutral", "interaction", "success", "failure", "reset"},
                )
                reset_scenario = next(
                    item for item in manifest.play_scenarios if item.id == "reset"
                )
                if any(asset.type == "music" for asset in manifest.assets):
                    self.assertEqual(reset_scenario.audio_expectation, "silent")
                for scenario in manifest.play_scenarios:
                    load_plan(root, scenario.plan)
                art_assets = [item for item in manifest.assets
                              if item.type in {"fullscreen", "spritesheet"}]
                self.assertEqual(len(art_assets), 2)
                for asset in art_assets:
                    image = read_png(root / asset.source)
                    self.assertLessEqual(len(set(image.pixels)), 4)
                    self.assertEqual(image.width % 8, 0)
                    self.assertEqual(image.height % 8, 0)
                self.assertTrue((root / "ART_PROVENANCE.md").is_file())
                self.assertFalse((root / "src/diagnostic_art.h").exists())
                game_source = (root / "src/game.c").read_text()
                self.assertGreaterEqual(
                    game_source.count("swan_core_reset_session();"), 2,
                    "scene entry and in-game reset must both reset SDK session state",
                )

    def test_portable_canary_models_compile_and_pass_without_sdk_linkage(self) -> None:
        compiler = os.environ.get("CC", "cc")
        with tempfile.TemporaryDirectory() as temporary:
            output_root = Path(temporary)
            for project_id in CANARIES:
                with self.subTest(project=project_id):
                    root = ROOT / "examples/canaries" / project_id
                    output = output_root / project_id
                    subprocess.run([
                        compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-I", str(root / "src"), "-o", str(output),
                        str(root / "tests/host/test_model.c"),
                        str(root / "src/model.c"),
                    ], check=True)
                    subprocess.run([str(output)], check=True)


if __name__ == "__main__":
    unittest.main()
