from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from swansong_sdk.cli import _parse_linked_usage, _run_make, main
from swansong_sdk.operations import OperationsError


class CliTests(unittest.TestCase):
    def test_make_reenters_the_active_installed_sdk(self) -> None:
        manifest = mock.Mock(root=Path("/tmp/game"), hardware="color-required")
        with mock.patch("swansong_sdk.cli.subprocess.run") as run:
            _run_make(manifest, ["test"])
        environment = run.call_args.kwargs["env"]
        self.assertIn(str(Path(sys.executable)), environment["SWAN"])
        self.assertTrue(environment["SWAN"].endswith(" -m swansong_sdk.cli"))

    def test_sdk_path_contains_complete_payload(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["sdk-path"]), 0)
        root = Path(output.getvalue().strip())
        for relative in (
            "include/swan/swan.h", "src/core.c", "mk/runtime-library.mk",
            "templates/common/Makefile.tmpl", "schema/swan.schema.json",
            "schema/frame-input-plan.schema.json",
            "schema/failure-predicate.schema.json",
            "schema/minimize-report.schema.json",
            "schema/replay-checkpoints.schema.json",
            "schema/replay-report.schema.json",
            "schema/author-tilemap.schema.json",
            "schema/author-sprites.schema.json",
            "schema/author-palette.schema.json",
            "schema/author-collision.schema.json",
            "schema/author-scene-flow.schema.json",
            "schema/author-audio.schema.json",
            "schema/author-operation-report.schema.json",
            "schema/author-handoff.schema.json",
            "CHANGELOG.md", "docs/input-gestures.md",
            "docs/release-notes-0.3.1.md",
            "docs/release-notes-0.4.0.md",
            "docs/supply-chain.md", "toolchain.lock",
        ):
            self.assertTrue((root / relative).is_file(), relative)

    def test_parses_wonderful_linked_iram_usage(self) -> None:
        output = """Section           Used    Free  Free%
-------------- ------- ------- ------
Internal RAM     35756   29780    46%
|
+- Mono area     13208    3176    20%
+- Color area    22548   26604    55%
Cartridge ROM    10553  120519    92%
"""
        self.assertEqual(_parse_linked_usage(output), {
            "linkedInternalRamBytes": 35756,
            "linkedMonoAreaBytes": 13208,
            "linkedColorAreaBytes": 22548,
        })
        self.assertEqual(_parse_linked_usage("no usage table"), {
            "linkedInternalRamBytes": None,
            "linkedMonoAreaBytes": None,
            "linkedColorAreaBytes": None,
        })

    def test_new_assets_and_json_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "cli-game"
            with redirect_stdout(StringIO()):
                self.assertEqual(main(["new", "cli-game", "--template", "menu-puzzle", "--directory", str(project)]), 0)
                self.assertEqual(main(["assets", "--project", str(project / "swan.toml")]), 0)
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(["report", "--project", str(project / "swan.toml"), "--json"]), 0)
            report = json.loads(output.getvalue())
            self.assertEqual(report["project"], "cli-game")
            self.assertIsNone(report["romBytes"])
            self.assertIsNone(report["linkedInternalRamBytes"])
            self.assertIsNone(report["linkedMonoAreaBytes"])
            self.assertIsNone(report["linkedColorAreaBytes"])
            capacity = StringIO()
            with redirect_stdout(capacity):
                self.assertEqual(main([
                    "hardware-tile-capacity", "--project", str(project / "swan.toml")
                ]), 0)
            self.assertEqual(capacity.getvalue().strip(), "512")

    def test_new_refuses_nonempty_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            (target / "keep").write_text("mine")
            with redirect_stderr(StringIO()):
                self.assertEqual(main(["new", "refuse-me", "--directory", str(target)]), 2)
            self.assertEqual((target / "keep").read_text(), "mine")

    def test_doctor_json_uses_versioned_contract_and_exit_status(self) -> None:
        report = {"schema": "swansong-doctor-report-v1", "ok": False, "checks": []}
        output = StringIO()
        with mock.patch("swansong_sdk.cli.doctor_report", return_value=report):
            with redirect_stdout(output):
                self.assertEqual(main(["doctor", "--json"]), 2)
        self.assertEqual(json.loads(output.getvalue()), report)

    def test_dev_json_streams_versioned_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "dev-game"
            with redirect_stdout(StringIO()):
                self.assertEqual(main([
                    "new", "dev-game", "--template", "menu-puzzle",
                    "--directory", str(project),
                ]), 0)

            def session(unused_manifest, **kwargs):
                event = {
                    "schema": "swansong-dev-event-v1", "sequence": 0,
                    "type": "stop", "project": "dev-game", "scenario": "interaction",
                    "status": "passed", "builds": 1, "pollCycles": 0,
                }
                kwargs["sink"](event)
                return event

            output = StringIO()
            with mock.patch("swansong_sdk.cli.development_session", side_effect=session):
                with redirect_stdout(output):
                    self.assertEqual(main([
                        "dev", "--project", str(project / "swan.toml"),
                        "--once", "--json",
                    ]), 0)
            events = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual(events[0]["schema"], "swansong-dev-event-v1")

    def test_dev_json_failure_keeps_sequence_monotonic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "dev-failure"
            with redirect_stdout(StringIO()):
                self.assertEqual(main([
                    "new", "dev-failure", "--template", "menu-puzzle",
                    "--directory", str(project),
                ]), 0)

            def session(unused_manifest, **kwargs):
                kwargs["sink"]({
                    "schema": "swansong-dev-event-v1", "sequence": 4,
                    "type": "gate", "project": "dev-failure",
                    "scenario": "interaction", "status": "failed",
                })
                raise OperationsError("build failed")

            output = StringIO()
            with mock.patch("swansong_sdk.cli.development_session", side_effect=session):
                with redirect_stdout(output):
                    self.assertEqual(main([
                        "dev", "--project", str(project / "swan.toml"),
                        "--once", "--json",
                    ]), 2)
            events = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual([item["sequence"] for item in events], [4, 5])
            self.assertEqual(events[-1]["type"], "error")

    def test_release_json_uses_versioned_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "release-game"
            with redirect_stdout(StringIO()):
                self.assertEqual(main([
                    "new", "release-game", "--template", "menu-puzzle",
                    "--directory", str(project),
                ]), 0)
            report = {
                "schema": "swansong-release-report-v1", "ok": True,
                "project": "release-game", "version": "0.1.0",
                "package": str(project / "release.zip"), "packageSha256": "abc",
                "gates": [], "artifacts": [],
            }
            output = StringIO()
            with mock.patch("swansong_sdk.cli.release_project", return_value=report):
                with redirect_stdout(output):
                    self.assertEqual(main([
                        "release", "--project", str(project / "swan.toml"), "--json",
                    ]), 0)
            self.assertEqual(json.loads(output.getvalue()), report)

    def test_release_json_failure_stays_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / "failed-release"
            with redirect_stdout(StringIO()):
                self.assertEqual(main([
                    "new", "failed-release", "--template", "menu-puzzle",
                    "--directory", str(project),
                ]), 0)
            output = StringIO()
            with mock.patch(
                "swansong_sdk.cli.release_project",
                side_effect=RuntimeError("unexpected implementation error"),
            ):
                with self.assertRaises(RuntimeError):
                    main(["release", "--project", str(project / "swan.toml"), "--json"])
            with mock.patch(
                "swansong_sdk.cli.release_project",
                side_effect=OperationsError("test gate failed"),
            ):
                with redirect_stdout(output):
                    self.assertEqual(main([
                        "release", "--project", str(project / "swan.toml"), "--json",
                    ]), 2)
            report = json.loads(output.getvalue())
            self.assertEqual(report["schema"], "swansong-release-report-v1")
            self.assertFalse(report["ok"])
            self.assertEqual(report["error"]["code"], "release-gate-failed")
            self.assertEqual(set(report), {
                "artifacts", "error", "gates", "ok", "package",
                "packageSha256", "project", "schema", "sdkRevision", "sdkVersion",
                "toolchainLockSha256", "version",
            })

    def test_release_manifest_failure_uses_complete_report_shape(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([
                "release", "--project", "/definitely/missing/swan.toml", "--json",
            ]), 2)
        report = json.loads(output.getvalue())
        self.assertEqual(set(report), {
            "artifacts", "error", "gates", "ok", "package",
            "packageSha256", "project", "schema", "sdkRevision", "sdkVersion",
            "toolchainLockSha256", "version",
        })
        self.assertIsNone(report["project"])


if __name__ == "__main__":
    unittest.main()
