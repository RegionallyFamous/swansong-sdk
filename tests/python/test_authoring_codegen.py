from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from swansong_sdk.authoring import AuthoringError, default_document
from swansong_sdk.authoring_codegen import (
    COMPILABLE_KINDS, compile_authoring_document, compile_project_authoring,
)
from swansong_sdk.optimize import (
    ARTIST_APPROVAL, OptimizationError, apply_approved_asset_optimization,
    encode_rgba_png, preview_asset_optimization,
    revert_approved_asset_optimization,
)
from swansong_sdk.png2bpp import Image, read_png


SDK_ROOT = Path(__file__).resolve().parents[2]


def _source_image() -> Image:
    colors = (
        (0, 0, 0, 255), (255, 255, 255, 255), (255, 0, 0, 255),
        (0, 255, 0, 255), (0, 0, 255, 255),
    )
    return Image(8, 8, tuple(colors[(x + y) % len(colors)] for y in range(8) for x in range(8)))


def _documents() -> list[dict[str, object]]:
    tilemap = default_document("tilemap", "world-map")
    tilemap["layers"][0]["cells"] = [{
        "x": 2, "y": 3, "tile": 9, "palette": 2,
        "flipX": True, "flipY": False,
    }]
    sprites = default_document("sprites", "pilot-sheet")
    sprites["frames"].append({
        "id": "run-0", "x": 8, "y": 0, "width": 8, "height": 8,
        "originX": 4, "originY": 7,
    })
    sprites["animations"].append({
        "id": "run", "loop": True,
        "steps": [{
            "frame": "run-0", "durationFrames": 4,
            "flipX": True, "flipY": False,
        }],
    })
    palette = default_document("palette", "night-palette")
    collision = default_document("collision", "world-collision")
    collision["regions"] = [{
        "id": "wall", "kind": "solid", "closed": True,
        "points": [{"x": 0, "y": 0}, {"x": 8, "y": 0}, {"x": 8, "y": 8}],
    }]
    flow = default_document("scene-flow", "main-flow")
    flow["scenes"].append({"id": "play", "title": "Play"})
    flow["transitions"] = [{
        "id": "begin", "from": "title", "to": "play",
        "event": "confirm", "argument": 7,
    }]
    return [tilemap, sprites, palette, collision, flow]


class AuthoringCodegenTests(unittest.TestCase):
    def test_all_portable_documents_compile_to_deterministic_c(self) -> None:
        self.assertEqual(set(COMPILABLE_KINDS), {
            "tilemap", "sprites", "palette", "collision", "scene-flow",
        })
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            for document in _documents():
                with self.subTest(kind=document["schema"]):
                    first = compile_authoring_document(document)
                    second = compile_authoring_document(deepcopy(document))
                    self.assertEqual(first, second)
                    self.assertEqual(first.to_dict(), second.to_dict())
                    self.assertIn(first.document_sha256, first.header)
                    include = output / "include" / first.header_name
                    source = output / "src" / first.source_name
                    include.parent.mkdir(exist_ok=True)
                    source.parent.mkdir(exist_ok=True)
                    include.write_text(first.header)
                    source.write_text(first.source)
                    subprocess.run([
                        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-c",
                        "-I", str(SDK_ROOT / "include"), "-I", str(include.parent),
                        "-o", str(output / (first.source_name + ".o")), str(source),
                    ], check=True, capture_output=True, text=True)
                    wonderful_cc = Path(
                        "/opt/wonderful/toolchain/gcc-ia16-elf/bin/ia16-elf-gcc"
                    )
                    if wonderful_cc.is_file():
                        subprocess.run([
                            str(wonderful_cc), "-std=gnu11", "-Wall", "-Wextra",
                            "-Werror", "-march=v30mz", "-mtune=v30mz",
                            "-mregparmcall", "-ffreestanding", "-mcmodel=medium",
                            "-msegelf", "-mcs-jump-tables", "-c",
                            "-I", str(SDK_ROOT / "include"),
                            "-I", str(include.parent),
                            "-o", str(output / (first.source_name + ".ia16.o")),
                            str(source),
                        ], check=True, capture_output=True, text=True)

    def test_generated_data_contains_runtime_ready_authored_values(self) -> None:
        tilemap, sprites, palette, collision, flow = [
            compile_authoring_document(document) for document in _documents()
        ]
        self.assertIn("{2u, 3u, 9u, 2u, 1u}", tilemap.source)
        self.assertIn("SWAN_AUTHOR_WORLD_MAP_CELL_COUNT 1u", tilemap.header)
        self.assertIn("SWAN_AUTHOR_PILOT_SHEET_HITBOX_COUNT 1u", sprites.header)
        self.assertIn("{1u, 4u, 1u}", sprites.source)
        self.assertIn("swan_author_night_palette_mono_mapping", palette.source)
        self.assertIn("0x0211u", palette.source)
        self.assertIn("{0u, 3u, 0u, 1u}", collision.source)
        self.assertIn("SWAN_AUTHOR_MAIN_FLOW_SCENE_PLAY = 1", flow.header)
        self.assertIn("{0u, 1u, 0u, 7u}", flow.source)

    def test_project_discovery_binds_dependencies_and_rejects_escapes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            authoring = root / "authoring"
            art = root / "assets/art"
            authoring.mkdir(parents=True)
            art.mkdir(parents=True)
            image = encode_rgba_png(_source_image())
            (art / "tiles.png").write_bytes(image)
            document = default_document("tilemap", "world-map")
            (authoring / "world.tilemap.json").write_text(json.dumps(document))
            compiled = compile_project_authoring(root)
            self.assertEqual(len(compiled), 1)
            self.assertEqual(compiled[0].dependencies, ((
                "assets/art/tiles.png", hashlib.sha256(image).hexdigest(),
            ),))

            outside = Path(temporary) / "outside.tilemap.json"
            outside.write_text(json.dumps(document))
            linked = authoring / "escape.tilemap.json"
            try:
                linked.symlink_to(outside)
            except OSError:
                self.skipTest("symlinks are unavailable")
            with self.assertRaisesRegex(AuthoringError, "outside the project"):
                compile_project_authoring(root)


class ApprovedOptimizationTests(unittest.TestCase):
    def test_apply_is_hash_bound_source_preserving_and_reversible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "assets/source.png"
            source.parent.mkdir()
            source.write_bytes(encode_rgba_png(_source_image()))
            source_before = source.read_bytes()
            digest = hashlib.sha256(source_before).hexdigest()
            preview = preview_asset_optimization({"ship": source}).to_dict()
            self.assertEqual(preview["assets"][0]["sourceFileSHA256"], digest)

            with self.assertRaisesRegex(OptimizationError, "artist approval"):
                apply_approved_asset_optimization(
                    root, "assets/source.png", "assets/source-optimized.png",
                    "authoring/source-optimization.json", asset_id="ship",
                    operations=("palette-reduction",),
                    expected_source_sha256=digest, approval="yes",
                )
            applied = apply_approved_asset_optimization(
                root, "assets/source.png", "assets/source-optimized.png",
                "authoring/source-optimization.json", asset_id="ship",
                operations=("palette-reduction", "mono-conversion"),
                expected_source_sha256=digest, approval=ARTIST_APPROVAL,
            )
            output = root / applied["output"]["path"]
            report = root / "authoring/source-optimization.json"
            self.assertEqual(source.read_bytes(), source_before)
            self.assertTrue(output.is_file() and report.is_file())
            self.assertEqual(len(set(read_png(output).pixels)), 4)
            self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(),
                             applied["output"]["sha256"])
            reverted = revert_approved_asset_optimization(
                root, report, expected_report_sha256=applied["reportSHA256"],
                approval=ARTIST_APPROVAL,
            )
            self.assertFalse(output.exists())
            self.assertTrue(report.is_file())
            self.assertEqual(reverted["removedOutputSHA256"], applied["output"]["sha256"])
            self.assertEqual(source.read_bytes(), source_before)

    def test_apply_rejects_stale_hash_escape_overwrite_and_tampered_revert(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "project"
            root.mkdir()
            source = root / "source.png"
            source.write_bytes(encode_rgba_png(_source_image()))
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            arguments = dict(
                asset_id="ship", operations=("palette-reduction",),
                expected_source_sha256=digest, approval=ARTIST_APPROVAL,
            )
            with self.assertRaisesRegex(OptimizationError, "changed after"):
                apply_approved_asset_optimization(
                    root, source, "optimized.png", "report.json",
                    **{**arguments, "expected_source_sha256": "0" * 64},
                )
            with self.assertRaisesRegex(OptimizationError, "inside the project"):
                apply_approved_asset_optimization(
                    root, source, "../outside.png", "report.json", **arguments,
                )
            applied = apply_approved_asset_optimization(
                root, source, "optimized.png", "report.json", **arguments,
            )
            report_path = root / "report.json"
            report_bytes = report_path.read_bytes()
            report_path.write_bytes(report_bytes + b"\n")
            with self.assertRaisesRegex(OptimizationError, "report changed"):
                revert_approved_asset_optimization(
                    root, report_path,
                    expected_report_sha256=applied["reportSHA256"],
                    approval=ARTIST_APPROVAL,
                )
            report_path.write_bytes(report_bytes)
            (root / "optimized.png").write_bytes(b"changed")
            with self.assertRaisesRegex(OptimizationError, "output changed"):
                revert_approved_asset_optimization(
                    root, "report.json", expected_report_sha256=applied["reportSHA256"],
                    approval=ARTIST_APPROVAL,
                )
            self.assertTrue((root / "optimized.png").is_file())
            self.assertEqual(applied["source"]["sha256"], digest)


if __name__ == "__main__":
    unittest.main()
