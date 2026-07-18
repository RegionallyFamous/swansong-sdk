from __future__ import annotations

from dataclasses import replace
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock
import wave
import zipfile

from swansong_sdk.generator import generate
from swansong_sdk.identity import sdk_identity
from swansong_sdk.layout import sdk_root
from swansong_sdk.manifest import load_manifest
from swansong_sdk.operations import (
    DEV_EVENT_SCHEMA, DOCTOR_SCHEMA, RELEASE_SCHEMA, OperationsError,
    ProcessResult, development_session, doctor_report, release_project,
    run_cli_gate, watched_paths,
)
from swansong_sdk.operations import _verified_evidence_files
from swansong_sdk.scaffold import create_project
from swansong_sdk.plans import load_plan


SWANSONG_SERVER = r'''
import json
import sys

for line in sys.stdin:
    request = json.loads(line)
    print(json.dumps({
        "jsonrpc": "2.0",
        "id": request["id"],
        "result": {"serverInfo": {"name": "swansong-doctor-fixture"}},
    }, sort_keys=True), flush=True)
'''

PNG_FIXTURE = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def wav_fixture(amplitude: int = 0, frames: int = 4) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as target:
        target.setnchannels(2)
        target.setsampwidth(2)
        target.setframerate(48_000)
        sample = amplitude.to_bytes(2, "little", signed=True)
        target.writeframes(sample * 2 * frames)
    return output.getvalue()


def executable(path: Path, text: str = "#!/bin/sh\nexit 0\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def install_locked_packages(wonderful: Path) -> None:
    database = wonderful / "pacman/db/local"
    database.mkdir(parents=True, exist_ok=True)
    lock = Path(__file__).parents[2] / "toolchain.lock"
    for raw in lock.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("cbrzeszczot/"):
            continue
        if line.startswith("ci:"):
            line = line.removeprefix("ci:").strip()
        name, version = line.split(maxsplit=1)
        (database / f"{name}-{version}").mkdir(exist_ok=True)


def provenance_fixture() -> dict[str, object]:
    identity = sdk_identity()
    lock_sha256 = hashlib.sha256((sdk_root() / "toolchain.lock").read_bytes()).hexdigest()
    return {
        "schema": "swansong-build-provenance-v1",
        "sdkVersion": identity["version"],
        "sdkRevision": identity["revision"],
        "toolchain": {
            "canonicalImage": (
                "cbrzeszczot/wonderful@sha256:"
                "1bd074214c0592a5fca3f26ce0c47d3a809f48e83f68705189fe30c78e75435e"
            ),
            "expectedPackages": ["test-package 1.0"],
            "lane": "test",
            "lockSha256": lock_sha256,
        },
    }


class OperationsTests(unittest.TestCase):
    def project(self, root: Path, recipe: str = "menu-puzzle"):
        project = create_project("operation-game", recipe, root / "operation-game")
        manifest = load_manifest(project / "swan.toml")
        generate(manifest)
        return manifest

    def test_doctor_report_checks_complete_environment_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = self.project(root)
            wonderful = root / "wonderful"
            for name in ("wf-config", "wf-process", "wf-superfamiconv", "wf-wswantool"):
                executable(wonderful / "bin" / name)
            target = wonderful / "target/wswan/medium/makedefs.mk"
            target.parent.mkdir(parents=True)
            target.write_text("# fixture\n")
            install_locked_packages(wonderful)
            server = root / "swansong_server.py"
            server.write_text(SWANSONG_SERVER)
            environment = {
                "WONDERFUL_TOOLCHAIN": str(wonderful),
                "SWANSONG_MCP_COMMAND": f"{sys.executable} {server} --token secret-value",
            }
            with mock.patch.dict(os.environ, environment, clear=False):
                first = doctor_report(manifest.root, timeout=2)
                second = doctor_report(manifest.root, timeout=2)
            self.assertEqual(first, second)
            self.assertNotIn("secret-value", json.dumps(first, sort_keys=True))
            self.assertEqual(first["schema"], DOCTOR_SCHEMA)
            self.assertTrue(first["ok"])
            self.assertEqual([item["id"] for item in first["checks"]], [
                "python", "sdk-payload", "sdk-version", "manifest",
                "sdk-project-pin", "project-paths", "generated-config",
                "wonderful", "swansong",
            ])

    def test_doctor_fails_when_generated_config_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self.project(Path(temporary))
            config = manifest.root / "wfconfig.toml"
            config.write_text(config.read_text().replace("game_id = 1", "game_id = 99"))
            with mock.patch("swansong_sdk.operations._probe_swansong", return_value=(True, "ok", {})):
                report = doctor_report(manifest.root)
            check = next(item for item in report["checks"] if item["id"] == "generated-config")
            self.assertEqual(check["status"], "fail")
            self.assertFalse(report["ok"])

    def test_doctor_redacts_failing_swansong_command_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = self.project(root)
            wonderful = root / "wonderful"
            for name in ("wf-config", "wf-process", "wf-superfamiconv", "wf-wswantool"):
                executable(wonderful / "bin" / name)
            target = wonderful / "target/wswan/medium/makedefs.mk"
            target.parent.mkdir(parents=True)
            target.write_text("# fixture\n")
            install_locked_packages(wonderful)
            server = root / "failing_swansong.py"
            server.write_text("raise SystemExit(7)\n")
            environment = {
                "WONDERFUL_TOOLCHAIN": str(wonderful),
                "SWANSONG_MCP_COMMAND": (
                    f"{sys.executable} {server} --token never-serialize-this"
                ),
            }
            with mock.patch.dict(os.environ, environment, clear=False):
                report = doctor_report(manifest.root, timeout=2)
            self.assertFalse(report["ok"])
            serialized = json.dumps(report, sort_keys=True)
            self.assertNotIn("never-serialize-this", serialized)
            check = next(item for item in report["checks"] if item["id"] == "swansong")
            self.assertEqual(check["details"]["argumentCount"], 3)
            self.assertEqual(check["details"]["returnCode"], 7)

    def test_doctor_redacts_timed_out_swansong_command_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = self.project(root)
            wonderful = root / "wonderful"
            for name in ("wf-config", "wf-process", "wf-superfamiconv", "wf-wswantool"):
                executable(wonderful / "bin" / name)
            target = wonderful / "target/wswan/medium/makedefs.mk"
            target.parent.mkdir(parents=True)
            target.write_text("# fixture\n")
            install_locked_packages(wonderful)
            server = root / "hanging_swansong.py"
            server.write_text("import time; time.sleep(10)\n")
            environment = {
                "WONDERFUL_TOOLCHAIN": str(wonderful),
                "SWANSONG_MCP_COMMAND": (
                    f"{sys.executable} {server} --token timeout-secret"
                ),
            }
            with mock.patch.dict(os.environ, environment, clear=False):
                report = doctor_report(manifest.root, timeout=0.05)
            self.assertNotIn("timeout-secret", json.dumps(report, sort_keys=True))
            self.assertFalse(report["ok"])

    def test_dev_once_uses_build_then_existing_play_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self.project(Path(temporary))
            commands: list[tuple[str, ...]] = []
            events: list[dict[str, object]] = []

            def runner(command, unused_manifest, unused_timeout):
                self.assertIs(unused_manifest, manifest)
                commands.append(command)
                return ProcessResult(command, 0, "", "")

            result = development_session(
                manifest, once=True, test_mode=True, runner=runner, sink=events.append,
            )
            self.assertEqual(commands, [("build",), ("play", "interaction")])
            self.assertEqual(result["type"], "stop")
            self.assertEqual([event["sequence"] for event in events], list(range(len(events))))
            self.assertTrue(all(event["schema"] == DEV_EVENT_SCHEMA for event in events))

    def test_child_gates_keep_source_checkout_importable_from_project_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self.project(Path(temporary))
            captured: dict[str, object] = {}

            def fake_run(argv, *, cwd, timeout, environment):
                captured.update(argv=argv, cwd=cwd, timeout=timeout, environment=environment)
                return ProcessResult(tuple(argv), 0, "", "")

            hostile_environment = {
                "PYTHONPATH": str(manifest.root),
                "SWANSONG_SDK_DIR": str(manifest.root / "fake-sdk"),
            }
            with mock.patch.dict(os.environ, hostile_environment, clear=False), \
                    mock.patch("swansong_sdk.operations.run_process", side_effect=fake_run):
                run_cli_gate(("assets",), manifest, 12)
            self.assertEqual(captured["cwd"], manifest.root)
            self.assertEqual(captured["argv"][1:4], ["-P", "-m", "swansong_sdk.cli"])
            environment = captured["environment"]
            resolved_sdk = sdk_root()
            source_python = resolved_sdk / "python"
            if source_python.is_dir():
                self.assertEqual(environment["PYTHONPATH"], str(source_python))
            else:
                self.assertNotIn("PYTHONPATH", environment)
            self.assertEqual(environment["SWANSONG_SDK_DIR"], str(resolved_sdk))

    def test_watch_set_includes_inputs_and_excludes_generated_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self.project(Path(temporary), "arcade-action")
            generated = manifest.root / "build/generated/not-an-input.c"
            generated.parent.mkdir(parents=True, exist_ok=True)
            generated.write_text("generated")
            paths = {path.relative_to(manifest.root).as_posix() for path in watched_paths(manifest)}
            self.assertIn("swan.toml", paths)
            self.assertIn("Makefile", paths)
            self.assertIn("src/model.c", paths)
            self.assertIn("assets/audio/theme.toml", paths)
            self.assertNotIn("build/generated/not-an-input.c", paths)

    def test_release_archive_is_deterministic_and_complete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = self.project(root)
            calls: list[tuple[str, ...]] = []
            stale_evidence = False
            omit_observation = False
            malformed_media = False

            def runner(command, unused_manifest, unused_timeout):
                self.assertIs(unused_manifest, manifest)
                calls.append(command)
                if command == ("build",):
                    (manifest.root / manifest.rom_name).write_bytes(b"ROM-fixture")
                    if manifest.hardware == "mono-compatible":
                        (manifest.root / "operation_game.ws").write_bytes(b"MONO-fixture")
                if command[0] == "play":
                    evidence = manifest.root / "build/swansong" / command[1]
                    evidence.mkdir(parents=True, exist_ok=True)
                    png = b"\x89PNG\r\n\x1a\ntruncated" if malformed_media else PNG_FIXTURE
                    wav = wav_fixture()
                    (evidence / "frame.png").write_bytes(png)
                    (evidence / "audio.wav").write_bytes(wav)
                    scenario = next(item for item in manifest.play_scenarios
                                    if item.id == command[1])
                    _, plan = load_plan(manifest.root, scenario.plan)
                    rom = (manifest.root / manifest.rom_name).read_bytes()
                    (evidence / "evidence.json").write_text(json.dumps({
                        "schema": "swan-song-playtest-report-v1",
                        "romSHA256": (
                            "0" * 64 if stale_evidence else hashlib.sha256(rom).hexdigest()
                        ),
                        "romByteCount": len(rom),
                        "plan": plan,
                        "capturePNG_SHA256": hashlib.sha256(png).hexdigest(),
                        "audio": {
                            "finalWindowWAVSHA256": hashlib.sha256(wav).hexdigest(),
                        },
                    }, sort_keys=True) + "\n")
                    observation_path = evidence / "observation.json"
                    if omit_observation:
                        observation_path.unlink(missing_ok=True)
                    else:
                        observation_path.write_text(json.dumps({
                            "schema": "swan-song-evidence-observation-v1",
                            "scenario": scenario.id,
                            "verdict": "pass",
                            "pngInspected": True,
                            "wavInspected": True,
                            "observer": "release-test",
                            "romSHA256": hashlib.sha256(rom).hexdigest(),
                            "capturePNG_SHA256": hashlib.sha256(png).hexdigest(),
                            "finalWindowWAVSHA256": hashlib.sha256(wav).hexdigest(),
                            "requiredChecks": {
                                item: f"observed {item}" for item in scenario.required_checks
                            },
                        }, sort_keys=True) + "\n")
                stdout = ""
                if command == ("report",):
                    stdout = json.dumps({
                        "schema": "swansong-resource-report-v1", "project": manifest.id,
                    })
                return ProcessResult(command, 0, stdout, "")

            output = root / "release.zip"
            first = release_project(
                manifest, output=output, runner=runner,
                provenance_resolver=provenance_fixture,
            )
            first_bytes = output.read_bytes()
            second = release_project(
                manifest, output=output, runner=runner,
                provenance_resolver=provenance_fixture,
            )
            self.assertEqual(first_bytes, output.read_bytes())
            self.assertEqual(first["packageSha256"], second["packageSha256"])
            self.assertEqual(first["schema"], RELEASE_SCHEMA)
            expected_calls = 4 + len(manifest.play_scenarios)
            self.assertEqual(len(calls), expected_calls * 2)
            with zipfile.ZipFile(output) as archive:
                names = archive.namelist()
                self.assertEqual(names, sorted(names))
                self.assertTrue(any(name.endswith(f"rom/{manifest.rom_name}") for name in names))
                self.assertTrue(any(name.endswith("checksums.sha256") for name in names))
                self.assertTrue(any(name.endswith("attestation.intoto.json") for name in names))
                self.assertTrue(any(name.endswith("sbom.cdx.json") for name in names))
                self.assertTrue(any(name.endswith("sbom.spdx.json") for name in names))
                self.assertTrue(any(name.endswith("release-notes.md") for name in names))
                for scenario in manifest.play_scenarios:
                    self.assertTrue(any(
                        name.endswith(f"evidence/{scenario.id}/evidence.json") for name in names
                    ))
                    self.assertTrue(any(
                        name.endswith(f"evidence/{scenario.id}/observation.json") for name in names
                    ))
                self.assertTrue(all(info.date_time == (1980, 1, 1, 0, 0, 0)
                                    for info in archive.infolist()))
            stale_evidence = True
            with self.assertRaisesRegex(OperationsError, "stale or unbound"):
                release_project(
                    manifest, output=root / "stale.zip", runner=runner,
                    provenance_resolver=provenance_fixture,
                )
            stale_evidence = False
            omit_observation = True
            with self.assertRaisesRegex(OperationsError, "inspected observation"):
                release_project(
                    manifest, output=root / "unobserved.zip", runner=runner,
                    provenance_resolver=provenance_fixture,
                )
            omit_observation = False
            malformed_media = True
            with self.assertRaisesRegex(OperationsError, "undecodable media"):
                release_project(
                    manifest, output=root / "malformed.zip", runner=runner,
                    provenance_resolver=provenance_fixture,
                )

    def test_release_fails_closed_before_packaging(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = self.project(root)
            output = root / "failed.zip"

            def runner(command, unused_manifest, unused_timeout):
                code = 1 if command == ("test",) else 0
                return ProcessResult(command, code, "", "host test failed")

            with self.assertRaisesRegex(OperationsError, "test gate failed"):
                release_project(
                    manifest, output=output, runner=runner,
                    provenance_resolver=provenance_fixture,
                )
            self.assertFalse(output.exists())

    def test_audio_expectations_decode_bind_and_inspect_every_wav(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self.project(Path(temporary))
            source_scenario = manifest.play_scenarios[0]
            rom_payload = b"audio-contract-rom"

            def verify(expectation: str, wav: bytes, *, inspected: bool = True) -> None:
                scenario = replace(source_scenario, audio_expectation=expectation)
                source = manifest.root / "build/swansong" / scenario.id
                source.mkdir(parents=True, exist_ok=True)
                png = PNG_FIXTURE
                _, plan = load_plan(manifest.root, scenario.plan)
                (source / "frame.png").write_bytes(png)
                (source / "audio.wav").write_bytes(wav)
                (source / "evidence.json").write_text(json.dumps({
                    "schema": "swan-song-playtest-report-v1",
                    "romSHA256": hashlib.sha256(rom_payload).hexdigest(),
                    "romByteCount": len(rom_payload),
                    "plan": plan,
                    "capturePNG_SHA256": hashlib.sha256(png).hexdigest(),
                    "audio": {
                        "finalWindowWAVSHA256": hashlib.sha256(wav).hexdigest(),
                    },
                }, sort_keys=True) + "\n")
                (source / "observation.json").write_text(json.dumps({
                    "schema": "swan-song-evidence-observation-v1",
                    "scenario": scenario.id,
                    "verdict": "pass",
                    "pngInspected": True,
                    "wavInspected": inspected,
                    "observer": "audio-contract-test",
                    "romSHA256": hashlib.sha256(rom_payload).hexdigest(),
                    "capturePNG_SHA256": hashlib.sha256(png).hexdigest(),
                    "finalWindowWAVSHA256": hashlib.sha256(wav).hexdigest(),
                    "requiredChecks": {
                        item: f"observed {item}" for item in scenario.required_checks
                    },
                }, sort_keys=True) + "\n")
                _verified_evidence_files(manifest, scenario, rom_payload)

            verify("silent", wav_fixture())
            verify("audible", wav_fixture(32))
            verify("any", wav_fixture())
            verify("any", wav_fixture(32))
            with self.assertRaisesRegex(OperationsError, "requires audible"):
                verify("audible", wav_fixture())
            with self.assertRaisesRegex(OperationsError, "requires silent"):
                verify("silent", wav_fixture(32))
            with self.assertRaisesRegex(OperationsError, "empty WAV"):
                verify("any", wav_fixture(frames=0))
            with self.assertRaisesRegex(OperationsError, "WAV inspection"):
                verify("silent", wav_fixture(), inspected=False)

    def test_release_refuses_no_play_contract_or_unsafe_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = self.project(Path(temporary))
            with self.assertRaisesRegex(OperationsError, "at least one"):
                release_project(replace(manifest, play_scenarios=()))
            with self.assertRaisesRegex(OperationsError, "path-safe"):
                release_project(replace(manifest, version="../../escape"))
            with self.assertRaisesRegex(OperationsError, "SDK pin"):
                release_project(
                    replace(manifest, sdk_revision="sha256:" + "0" * 64),
                    provenance_resolver=provenance_fixture,
                )
            incomplete = provenance_fixture()
            incomplete["toolchain"] = {
                "lane": "test", "lockSha256": "0" * 64,
            }
            with self.assertRaisesRegex(OperationsError, "toolchain.lock"):
                release_project(
                    manifest,
                    provenance_resolver=lambda: incomplete,
                )


if __name__ == "__main__":
    unittest.main()
