"""Operational CLI workflows for diagnosis, development, and releases."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from typing import Callable, Iterable
import zipfile

from . import __version__
from .evidence import EvidenceError, validate_wav
from .identity import sdk_identity
from .layout import LayoutError, sdk_root
from .manifest import PROJECT_VERSION, Manifest, ManifestError, find_manifest, load_manifest
from .plans import PlanError, load_plan
from .png2bpp import PNGError, read_png
from .provenance import (
    ProvenanceError, supply_chain_artifacts, validate_provenance,
)
from .swansong import SwanSongError, probe_server, server_command


DOCTOR_SCHEMA = "swansong-doctor-report-v1"
DEV_EVENT_SCHEMA = "swansong-dev-event-v1"
RELEASE_SCHEMA = "swansong-release-report-v1"
OBSERVATION_SCHEMA = "swan-song-evidence-observation-v1"


class OperationsError(RuntimeError):
    """An operational workflow could not complete safely."""


@dataclass(frozen=True)
class ProcessResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


GateRunner = Callable[[tuple[str, ...], Manifest, float], ProcessResult]
EventSink = Callable[[dict[str, object]], None]
NoticeSink = Callable[[str, str], None]
ProvenanceResolver = Callable[[], dict[str, object]]


def canonical_json(value: object, *, compact: bool = False) -> str:
    separators = (",", ":") if compact else None
    return json.dumps(value, indent=None if compact else 2, separators=separators,
                      sort_keys=True) + "\n"


def run_process(argv: Iterable[str], *, cwd: Path, timeout: float,
                environment: dict[str, str] | None = None,
                input_text: str | None = None) -> ProcessResult:
    command = tuple(str(item) for item in argv)
    if not command or not command[0]:
        raise OperationsError("refusing to run an empty command")
    if timeout <= 0:
        raise OperationsError("command timeout must be greater than zero")
    try:
        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                env=environment,
                stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                text=True,
                start_new_session=True,
            )
            try:
                process.communicate(input=input_text, timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    process.wait(timeout=2)
                raise OperationsError(
                    f"command timed out after {timeout:g} seconds: {command[0]}"
                ) from exc

            def captured_text(handle: object) -> str:
                limit = 4 * 1024 * 1024
                handle.seek(0, os.SEEK_END)
                size = handle.tell()
                handle.seek(max(0, size - limit))
                payload = handle.read()
                prefix = "[output truncated to final 4 MiB]\n" if size > limit else ""
                return prefix + payload.decode("utf-8", errors="replace")

            stdout = captured_text(stdout_file)
            stderr = captured_text(stderr_file)
    except FileNotFoundError as exc:
        raise OperationsError(f"command is not installed: {command[0]}") from exc
    except OSError as exc:
        raise OperationsError(f"could not run {command[0]}: {exc}") from exc
    return ProcessResult(command, process.returncode, stdout, stderr)


def _package_version() -> str:
    return __version__


def _runtime_version(root: Path) -> str:
    header = root / "include" / "swan" / "version.h"
    try:
        lines = header.read_text().splitlines()
    except OSError as exc:
        raise OperationsError(f"could not read SDK version header {header}: {exc}") from exc
    for line in lines:
        if line.startswith("#define SWAN_VERSION_STRING "):
            return line.split(maxsplit=2)[2].strip('"')
    raise OperationsError(f"SDK version is missing from {header}")


def _check(check_id: str, status: str, message: str,
           details: dict[str, object] | None = None) -> dict[str, object]:
    result: dict[str, object] = {
        "id": check_id,
        "message": message,
        "status": status,
    }
    if details:
        result["details"] = details
    return result


def _wonderful_tool(name: str, root: Path) -> Path | None:
    candidate = root / "bin" / name
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return candidate.resolve()
    located = shutil.which(name)
    return Path(located).resolve() if located else None


def _toolchain_pin_status(root: Path, wonderful_root: Path) -> tuple[
        bool, str, dict[str, object]]:
    lock = root / "toolchain.lock"
    try:
        payload = lock.read_bytes()
        lines = payload.decode("utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return False, f"could not read toolchain lock: {exc}", {"path": str(lock)}
    native: dict[str, str] = {}
    ci: dict[str, str] = {}
    canonical_image: str | None = None
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("cbrzeszczot/"):
            canonical_image = line
            continue
        lane = native
        if line.startswith("ci:"):
            lane = ci
            line = line.removeprefix("ci:").strip()
        pieces = line.split(maxsplit=1)
        if len(pieces) != 2:
            return False, f"invalid toolchain lock entry: {raw}", {"path": str(lock)}
        lane[pieces[0]] = pieces[1]
    requested_lane = os.environ.get("SWANSONG_TOOLCHAIN_LANE")
    if requested_lane not in {None, "native", "ci"}:
        return False, "SWANSONG_TOOLCHAIN_LANE must be native or ci", {
            "path": str(lock), "requestedLane": requested_lane,
        }
    lane_name = requested_lane or ("ci" if os.environ.get("CI") else "native")
    expected = dict(native)
    if lane_name == "ci":
        expected.update(ci)
    database = wonderful_root / "pacman" / "db" / "local"
    missing = [
        f"{name} {version}"
        for name, version in sorted(expected.items())
        if not (database / f"{name}-{version}").is_dir()
    ]
    details: dict[str, object] = {
        "canonicalImage": canonical_image,
        "expectedPackages": [
            f"{name} {version}" for name, version in sorted(expected.items())
        ],
        "lane": lane_name,
        "lockPath": str(lock),
        "lockSha256": hashlib.sha256(payload).hexdigest(),
        "packageDatabase": str(database),
    }
    if missing:
        details["missingPinnedPackages"] = missing
        return False, "Wonderful packages do not match toolchain.lock", details
    return True, f"Wonderful {lane_name} packages match toolchain.lock", details


def _release_provenance() -> dict[str, object]:
    root = sdk_root().resolve()
    wonderful_root = Path(
        os.environ.get("WONDERFUL_TOOLCHAIN", "/opt/wonderful")
    ).resolve()
    ok, message, details = _toolchain_pin_status(root, wonderful_root)
    if not ok:
        raise OperationsError(message + ": " + ", ".join(
            str(item) for item in details.get("missingPinnedPackages", [])
        ))
    identity = sdk_identity()
    return {
        "schema": "swansong-build-provenance-v1",
        "sdkVersion": identity["version"],
        "sdkRevision": identity["revision"],
        "toolchain": {
            key: details.get(key)
            for key in (
                "canonicalImage", "expectedPackages", "lane", "lockSha256"
            )
        },
    }


def _probe_swansong(project_root: Path, timeout: float) -> tuple[bool, str, dict[str, object]]:
    try:
        command = server_command()
    except SwanSongError as exc:
        return False, str(exc), {}
    identity: dict[str, object] = {
        "executable": command[0],
        "argumentCount": max(0, len(command) - 1),
    }
    try:
        response = probe_server(
            command,
            cwd=project_root,
            timeout=timeout,
            client_name="swan-doctor",
            client_version=_package_version(),
        )
    except SwanSongError as exc:
        details = dict(identity)
        if exc.returncode is not None:
            details["returnCode"] = exc.returncode
            if exc.returncode:
                return False, (
                    f"SwanSong interface exited with code {exc.returncode}"
                ), details
            return False, "SwanSong did not return an initialize response", details
        return False, str(exc), details
    if "error" in response:
        return False, "SwanSong rejected the initialize request", {
            **identity, "error": response["error"],
        }
    result = response.get("result")
    if not isinstance(result, dict):
        return False, "SwanSong initialize response has no result object", identity
    server = result.get("serverInfo", {})
    name = server.get("name", "") if isinstance(server, dict) else ""
    if not isinstance(name, str) or "swansong" not in name.lower():
        return False, f"refusing non-SwanSong server {name!r}", {
            **identity, "serverName": name,
        }
    return True, f"SwanSong interface answered as {name}", {
        **identity, "serverName": name,
    }


def _project_source_status(manifest: Manifest) -> tuple[bool, str, dict[str, object]]:
    missing: list[str] = []
    escaped: list[str] = []
    root = manifest.root.resolve()
    expected = [root / "swan.toml", root / "Makefile", root / "src"]
    for path in expected:
        if not path.exists():
            missing.append(str(path))
    for asset in manifest.assets:
        path = (root / asset.source).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            escaped.append(asset.source)
            continue
        if not path.is_file():
            missing.append(str(path))
    for scenario in manifest.play_scenarios:
        try:
            load_plan(
                root, scenario.plan, ready_frames=manifest.play_ready_frames
            )
        except PlanError as exc:
            missing.append(str(exc))
    details: dict[str, object] = {
        "assetCount": len(manifest.assets),
        "projectRoot": str(root),
        "scenarioCount": len(manifest.play_scenarios),
    }
    if missing:
        details["missing"] = sorted(missing)
    if escaped:
        details["outsideProject"] = sorted(escaped)
    if missing or escaped:
        return False, "project source paths are incomplete or unsafe", details
    return True, "project source and declared asset paths are available", details


def _generated_config_status(manifest: Manifest) -> tuple[bool, str, dict[str, object]]:
    path = manifest.root / "wfconfig.toml"
    details: dict[str, object] = {"path": str(path)}
    try:
        with path.open("rb") as handle:
            config = tomllib.load(handle)
    except FileNotFoundError:
        return False, "generated wfconfig.toml is missing; run swan assets", details
    except tomllib.TOMLDecodeError as exc:
        details["error"] = str(exc)
        return False, "generated wfconfig.toml is invalid", details
    cartridge = config.get("cartridge")
    if not isinstance(cartridge, dict):
        return False, "generated wfconfig.toml has no cartridge table", details
    expected = {
        "publisher_id": manifest.publisher_id,
        "game_id": manifest.game_id,
        "game_version": manifest.cartridge_version,
        "color": True,
        "rtc": manifest.rtc,
        "vertical": manifest.orientation == "vertical",
        "save_type": {
            "none": "NONE", "eeprom-128b": "EEPROM_128B",
            "eeprom-1kb": "EEPROM_1KB", "eeprom-2kb": "EEPROM_2KB",
            "sram-8kb": "SRAM_8KB", "sram-32kb": "SRAM_32KB",
            "sram-128kb": "SRAM_128KB", "sram-256kb": "SRAM_256KB",
            "sram-512kb": "SRAM_512KB",
        }[manifest.save_type],
    }
    mismatches = {
        key: {"actual": cartridge.get(key), "expected": value}
        for key, value in expected.items() if cartridge.get(key) != value
    }
    if mismatches:
        details["mismatches"] = mismatches
        return False, "generated config does not match swan.toml", details
    return True, "generated config matches the manifest", details


def doctor_report(project: str | Path | None = None, *, timeout: float = 5.0) -> dict[str, object]:
    if timeout <= 0:
        raise OperationsError("doctor timeout must be greater than zero")
    checks: list[dict[str, object]] = []
    python_version = ".".join(str(item) for item in sys.version_info[:3])
    python_ok = sys.version_info >= (3, 11)
    checks.append(_check(
        "python", "pass" if python_ok else "fail",
        f"Python {python_version} {'is supported' if python_ok else 'is below the 3.11 minimum'}",
        {"executable": sys.executable, "minimum": "3.11", "version": python_version},
    ))

    root: Path | None = None
    identity: dict[str, str] | None = None
    try:
        root = sdk_root().resolve()
        required = (
            "include/swan/swan.h", "src/core.c", "mk/runtime-library.mk",
            "schema/swan.schema.json", "schema/frame-input-plan.schema.json",
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
            "templates/common/Makefile.tmpl",
            "CHANGELOG.md",
            "docs/input-gestures.md",
            "docs/release-notes-0.3.1.md",
            "docs/release-notes-0.4.0.md",
            "docs/supply-chain.md",
            "toolchain.lock",
        )
        missing = [item for item in required if not (root / item).is_file()]
        checks.append(_check(
            "sdk-payload", "fail" if missing else "pass",
            "SDK payload is incomplete" if missing else "SDK payload is complete",
            {"missing": missing, "root": str(root)},
        ))
        package_version = _package_version()
        runtime_version = _runtime_version(root)
        identity = sdk_identity()
        version_ok = package_version == runtime_version
        checks.append(_check(
            "sdk-version", "pass" if version_ok else "fail",
            (
                f"SwanSong SDK {package_version}"
                if version_ok else
                f"Python package {package_version} does not match runtime {runtime_version}"
            ),
            {
                "manifestSchema": 1, "packageVersion": package_version,
                "runtimeVersion": runtime_version,
            },
        ))
    except (LayoutError, OSError, OperationsError) as exc:
        checks.append(_check("sdk-payload", "fail", str(exc)))
        checks.append(_check("sdk-version", "fail", "SDK version could not be read"))

    manifest: Manifest | None = None
    manifest_path: Path | None = None
    try:
        manifest_path = find_manifest(project or ".")
        manifest = load_manifest(manifest_path)
        checks.append(_check(
            "manifest", "pass", f"manifest is valid for {manifest.id}",
            {"path": str(manifest_path), "project": manifest.id,
             "schemaVersion": 1, "version": manifest.version},
        ))
    except ManifestError as exc:
        checks.append(_check("manifest", "fail", str(exc)))

    if manifest is not None and identity is not None:
        pin_ok = (
            manifest.sdk_version == identity["version"]
            and manifest.sdk_revision == identity["revision"]
        )
        checks.append(_check(
            "sdk-project-pin", "pass" if pin_ok else "fail",
            (
                "project SDK pin matches the resolved payload"
                if pin_ok else
                "project SDK pin does not match the resolved payload"
            ),
            {
                "actualRevision": identity["revision"],
                "actualVersion": identity["version"],
                "expectedRevision": manifest.sdk_revision,
                "expectedVersion": manifest.sdk_version,
            },
        ))
    else:
        checks.append(_check(
            "sdk-project-pin", "fail",
            "project SDK pin cannot be checked without a valid manifest and SDK payload",
        ))

    project_root = manifest.root if manifest else Path(project or ".").resolve()
    if manifest:
        paths_ok, message, details = _project_source_status(manifest)
        checks.append(_check("project-paths", "pass" if paths_ok else "fail", message, details))
        config_ok, message, details = _generated_config_status(manifest)
        checks.append(_check("generated-config", "pass" if config_ok else "fail", message, details))
    else:
        checks.append(_check("project-paths", "fail", "project paths cannot be checked without a valid manifest"))
        checks.append(_check("generated-config", "fail", "generated config cannot be checked without a valid manifest"))

    wonderful_root = Path(os.environ.get("WONDERFUL_TOOLCHAIN", "/opt/wonderful")).resolve()
    tools = {
        name: _wonderful_tool(name, wonderful_root)
        for name in ("wf-config", "wf-process", "wf-superfamiconv", "wf-wswantool")
    }
    target_makefile = wonderful_root / "target" / "wswan" / "medium" / "makedefs.mk"
    missing_tools = sorted(name for name, path in tools.items() if path is None)
    wonderful_ok = not missing_tools and target_makefile.is_file()
    pin_ok = False
    pin_message = "Wonderful package pins could not be checked"
    pin_details: dict[str, object] = {}
    if wonderful_ok and root is not None:
        pin_ok, pin_message, pin_details = _toolchain_pin_status(
            root, wonderful_root
        )
    wonderful_ok = wonderful_ok and pin_ok
    checks.append(_check(
        "wonderful", "pass" if wonderful_ok else "fail",
        pin_message if wonderful_ok else (
            pin_message if not pin_ok else "Wonderful toolchain is incomplete"
        ),
        {
            "missingTools": missing_tools,
            "root": str(wonderful_root),
            "targetMakefile": str(target_makefile),
            "tools": {name: str(path) if path else None for name, path in tools.items()},
            "pin": pin_details,
        },
    ))

    swansong_ok, message, details = _probe_swansong(project_root, timeout)
    checks.append(_check("swansong", "pass" if swansong_ok else "fail", message, details))
    return {
        "checks": checks,
        "ok": all(item["status"] == "pass" for item in checks),
        "schema": DOCTOR_SCHEMA,
    }


def _watch_files(manifest: Manifest) -> set[Path]:
    root = manifest.root.resolve()
    files: set[Path] = set()

    def include(path: Path) -> None:
        resolved = path.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise OperationsError(
                f"development input resolves outside the project: {path}"
            ) from exc
        if resolved.is_file():
            files.add(resolved)

    include(root / "swan.toml")
    include(root / "Makefile")
    for directory in (root / "src", root / "assets", root / "tests"):
        if directory.is_dir():
            for path in directory.rglob("*"):
                if path.is_file():
                    include(path)
    for asset in manifest.assets:
        include(root / asset.source)
    return files


def watched_paths(manifest: Manifest) -> tuple[Path, ...]:
    return tuple(sorted(_watch_files(manifest), key=str))


def _snapshot(manifest: Manifest) -> dict[str, str | None]:
    state: dict[str, str | None] = {}
    for path in watched_paths(manifest):
        try:
            state[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        except FileNotFoundError:
            state[str(path)] = None
        except OSError as exc:
            raise OperationsError(f"could not hash development input {path}: {exc}") from exc
    return state


def _display_path(manifest: Manifest, value: str) -> str:
    path = Path(value)
    try:
        return path.relative_to(manifest.root).as_posix()
    except ValueError:
        return str(path)


def _changed_paths(manifest: Manifest, before: dict[str, object],
                   after: dict[str, object]) -> list[str]:
    return sorted(
        _display_path(manifest, path)
        for path in set(before) | set(after) if before.get(path) != after.get(path)
    )


def run_cli_gate(command: tuple[str, ...], manifest: Manifest, timeout: float) -> ProcessResult:
    if not command:
        raise OperationsError("gate command cannot be empty")
    name, *arguments = command
    argv = [sys.executable, "-P", "-m", "swansong_sdk.cli", name]
    if name == "play":
        argv.extend(arguments)
    elif arguments:
        raise OperationsError(f"unexpected arguments for {name}: {arguments}")
    argv.extend(("--project", str(manifest.root / "swan.toml")))
    if name == "report":
        argv.append("--json")
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    source_python = sdk_root() / "python"
    if source_python.is_dir():
        environment["PYTHONPATH"] = str(source_python)
    environment["PYTHONSAFEPATH"] = "1"
    environment["SWANSONG_SDK_DIR"] = str(sdk_root())
    return run_process(argv, cwd=manifest.root, timeout=timeout,
                       environment=environment)


def _gate(command: tuple[str, ...], manifest: Manifest, timeout: float,
          runner: GateRunner) -> ProcessResult:
    result = runner(command, manifest, timeout)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        if len(detail) > 4000:
            detail = detail[-4000:]
        suffix = f": {detail}" if detail else ""
        raise OperationsError(f"{' '.join(command)} gate failed with exit code {result.returncode}{suffix}")
    return result


def _select_scenario(manifest: Manifest, requested: str | None) -> str:
    ids = [item.id for item in manifest.play_scenarios]
    if requested:
        if requested not in ids:
            raise OperationsError(f"unknown scenario {requested!r}; available: {', '.join(ids) or 'none'}")
        return requested
    if "interaction" in ids:
        return "interaction"
    if ids:
        return ids[0]
    raise OperationsError("swan dev requires at least one declared play scenario")


def development_session(manifest: Manifest, *, scenario: str | None = None,
                        once: bool = False, poll_cycles: int | None = None,
                        poll_interval: float = 0.25, debounce: float = 0.2,
                        timeout: float = 300.0, test_mode: bool = False,
                        runner: GateRunner = run_cli_gate,
                        sink: EventSink | None = None) -> dict[str, object]:
    if poll_cycles is not None and poll_cycles < 0:
        raise OperationsError("poll cycles cannot be negative")
    if timeout <= 0:
        raise OperationsError("gate timeout must be greater than zero")
    if poll_interval < 0 or debounce < 0:
        raise OperationsError("poll interval and debounce cannot be negative")
    if test_mode:
        poll_interval = 0
        debounce = 0
        if poll_cycles is None:
            poll_cycles = 0
    selected = _select_scenario(manifest, scenario)
    sequence = 0

    def emit(event_type: str, **values: object) -> dict[str, object]:
        nonlocal sequence
        event: dict[str, object] = {
            "project": manifest.id,
            "scenario": selected,
            "schema": DEV_EVENT_SCHEMA,
            "sequence": sequence,
            "type": event_type,
        }
        event.update(values)
        sequence += 1
        if sink:
            sink(event)
        return event

    builds = 0

    def rebuild(changed: list[str]) -> None:
        nonlocal builds
        emit("change", changed=changed)
        for command in (("build",), ("play", selected)):
            label = command[0] if len(command) == 1 else ":".join(command)
            emit("gate", gate=label, status="started")
            try:
                _gate(command, manifest, timeout, runner)
            except OperationsError:
                emit("gate", gate=label, status="failed")
                raise
            emit("gate", gate=label, status="passed")
        builds += 1

    current = _snapshot(manifest)
    emit("start", status="watching")
    rebuild(["<initial>"])
    # Do not lose an edit that lands while the compiler or SwanSong is active.
    for _ in range(4):
        post_build = _snapshot(manifest)
        if post_build == current:
            current = post_build
            break
        changed_during_build = _changed_paths(manifest, current, post_build)
        current = post_build
        rebuild(changed_during_build)
    cycles = 0
    if once:
        return emit("stop", builds=builds, pollCycles=cycles, status="passed")
    while poll_cycles is None or cycles < poll_cycles:
        if poll_interval:
            time.sleep(poll_interval)
        cycles += 1
        updated = _snapshot(manifest)
        if updated == current:
            continue
        changed = _changed_paths(manifest, current, updated)
        if debounce:
            stable_since = time.monotonic()
            deadline = stable_since + max(2.0, debounce * 10.0)
            while time.monotonic() - stable_since < debounce and time.monotonic() < deadline:
                time.sleep(min(poll_interval or debounce, debounce))
                candidate = _snapshot(manifest)
                if candidate != updated:
                    changed = sorted(set(changed) | set(_changed_paths(manifest, updated, candidate)))
                    updated = candidate
                    stable_since = time.monotonic()
        rebuild(changed)
        current = _snapshot(manifest)
    return emit("stop", builds=builds, pollCycles=cycles, status="passed")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _release_notes(manifest: Manifest, supplied: Path | None) -> bytes:
    if supplied:
        try:
            text = supplied.read_text()
        except OSError as exc:
            raise OperationsError(f"could not read release notes {supplied}: {exc}") from exc
        return (text.replace("\r\n", "\n").rstrip() + "\n").encode()
    scenarios = "\n".join(f"- {item.id}: {item.title}" for item in manifest.play_scenarios)
    if not scenarios:
        scenarios = "- No play scenarios declared."
    return (
        f"# {manifest.title} {manifest.version}\n\n"
        "Built by SwanSong SDK after assets, build, host-test, resource-report, "
        "and declared SwanSong play gates.\n\n"
        f"## Play contracts\n\n{scenarios}\n"
    ).encode()


def _write_deterministic_zip(path: Path, prefix: str, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9) as archive:
        for relative in sorted(files):
            info = zipfile.ZipInfo(f"{prefix}/{relative}", (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, files[relative])


def _release_output(manifest: Manifest, output: str | Path | None) -> Path:
    if not PROJECT_VERSION.fullmatch(manifest.version):
        raise OperationsError("release version is not a path-safe semantic version")
    filename = f"{manifest.id}-{manifest.version}.zip"
    if output is None:
        return (manifest.root / "dist" / filename).resolve()
    path = Path(output).resolve()
    return path if path.suffix.lower() == ".zip" else path / filename


def _read_release_bytes(path: Path, label: str) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise OperationsError(f"could not read {label} {path}: {exc}") from exc


def _verified_evidence_files(manifest: Manifest, scenario: object,
                             rom_payload: bytes) -> dict[str, bytes]:
    scenario_id = str(getattr(scenario, "id"))
    source = manifest.root / "build" / "swansong" / scenario_id
    png_path = source / "frame.png"
    wav_path = source / "audio.wav"
    metadata_path = source / "evidence.json"
    png = _read_release_bytes(png_path, f"{scenario_id} PNG evidence")
    wav = _read_release_bytes(wav_path, f"{scenario_id} WAV evidence")
    metadata_payload = _read_release_bytes(
        metadata_path, f"{scenario_id} structured evidence"
    )
    try:
        read_png(png_path)
        wav_metrics = validate_wav(wav_path)
    except (OSError, PNGError, EvidenceError) as exc:
        raise OperationsError(
            f"play:{scenario_id} produced undecodable media evidence: {exc}"
        ) from exc
    if not wav_metrics.get("frameCount"):
        raise OperationsError(
            f"play:{scenario_id} produced empty WAV evidence"
        )
    audio_expectation = str(getattr(scenario, "audio_expectation", "any"))
    peak_amplitude = int(wav_metrics.get("peakAmplitude", 0))
    if audio_expectation == "audible" and peak_amplitude == 0:
        raise OperationsError(
            f"play:{scenario_id} requires audible WAV evidence but its WAV is silent"
        )
    if audio_expectation == "silent" and peak_amplitude != 0:
        raise OperationsError(
            f"play:{scenario_id} requires silent WAV evidence but its WAV is audible"
        )
    try:
        metadata = json.loads(metadata_payload)
    except json.JSONDecodeError as exc:
        raise OperationsError(
            f"play:{scenario_id} produced invalid structured evidence JSON"
        ) from exc
    if not isinstance(metadata, dict) or metadata.get("schema") != "swan-song-playtest-report-v1":
        raise OperationsError(f"play:{scenario_id} produced unsupported evidence metadata")
    _, expected_plan = load_plan(
        manifest.root, str(getattr(scenario, "plan")),
        ready_frames=manifest.play_ready_frames,
    )
    expected_rom_sha = _sha256(rom_payload)
    audio = metadata.get("audio")
    checks = {
        "ROM hash": metadata.get("romSHA256") == expected_rom_sha,
        "ROM byte count": metadata.get("romByteCount") == len(rom_payload),
        "input plan": metadata.get("plan") == expected_plan,
        "PNG hash": metadata.get("capturePNG_SHA256") == _sha256(png),
        "WAV hash": (
            isinstance(audio, dict)
            and audio.get("finalWindowWAVSHA256") == _sha256(wav)
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise OperationsError(
            f"play:{scenario_id} evidence is stale or unbound: {', '.join(failures)}"
        )
    observation_path = source / "observation.json"
    observation_payload = _read_release_bytes(
        observation_path, f"{scenario_id} inspected observation"
    )
    try:
        observation = json.loads(observation_payload)
    except json.JSONDecodeError as exc:
        raise OperationsError(
            f"play:{scenario_id} observation is invalid JSON"
        ) from exc
    required_checks = tuple(getattr(scenario, "required_checks"))
    observed_checks = observation.get("requiredChecks") if isinstance(observation, dict) else None
    inspection_checks = {
        "schema": (
            isinstance(observation, dict)
            and observation.get("schema") == OBSERVATION_SCHEMA
        ),
        "scenario": (
            isinstance(observation, dict)
            and observation.get("scenario") == scenario_id
        ),
        "pass verdict": (
            isinstance(observation, dict)
            and observation.get("verdict") == "pass"
        ),
        "PNG inspection": (
            isinstance(observation, dict)
            and observation.get("pngInspected") is True
        ),
        "WAV inspection": (
            isinstance(observation, dict)
            and observation.get("wavInspected") is True
        ),
        "observer": (
            isinstance(observation, dict)
            and isinstance(observation.get("observer"), str)
            and bool(observation["observer"].strip())
        ),
        "ROM hash": (
            isinstance(observation, dict)
            and observation.get("romSHA256") == expected_rom_sha
        ),
        "PNG hash": (
            isinstance(observation, dict)
            and observation.get("capturePNG_SHA256") == _sha256(png)
        ),
        "WAV hash": (
            isinstance(observation, dict)
            and observation.get("finalWindowWAVSHA256") == _sha256(wav)
        ),
        "required checks": (
            isinstance(observed_checks, dict)
            and set(observed_checks) == set(required_checks)
            and all(
                isinstance(observed_checks[item], str)
                and bool(observed_checks[item].strip())
                for item in required_checks
            )
        ),
    }
    inspection_failures = [
        name for name, passed in inspection_checks.items() if not passed
    ]
    if inspection_failures:
        raise OperationsError(
            f"play:{scenario_id} lacks a bound inspected pass: "
            + ", ".join(inspection_failures)
        )
    return {
        f"evidence/{scenario_id}/frame.png": png,
        f"evidence/{scenario_id}/audio.wav": wav,
        f"evidence/{scenario_id}/evidence.json": metadata_payload,
        f"evidence/{scenario_id}/observation.json": observation_payload,
    }


def release_project(manifest: Manifest, *, output: str | Path | None = None,
                    notes: str | Path | None = None, timeout: float = 300.0,
                    runner: GateRunner = run_cli_gate,
                    notify: NoticeSink | None = None,
                    provenance_resolver: ProvenanceResolver = _release_provenance,
                    ) -> dict[str, object]:
    if timeout <= 0:
        raise OperationsError("release gate timeout must be greater than zero")
    if not manifest.play_scenarios:
        raise OperationsError("release requires at least one declared SwanSong play scenario")
    if not PROJECT_VERSION.fullmatch(manifest.version):
        raise OperationsError("release version is not a path-safe semantic version")
    provenance = provenance_resolver()
    identity = sdk_identity()
    lock_payload = _read_release_bytes(sdk_root() / "toolchain.lock", "toolchain lock")
    try:
        validate_provenance(
            provenance,
            sdk_version=identity["version"],
            sdk_revision=identity["revision"],
            lock_sha256=_sha256(lock_payload),
            lock_payload=lock_payload,
        )
    except ProvenanceError as exc:
        raise OperationsError(str(exc)) from exc
    resolved_version = provenance.get("sdkVersion")
    resolved_revision = provenance.get("sdkRevision")
    if manifest.sdk_version is None or manifest.sdk_revision is None:
        raise OperationsError("release requires sdk.version and sdk.revision pins in swan.toml")
    if (
        manifest.sdk_version != resolved_version
        or manifest.sdk_revision != resolved_revision
    ):
        raise OperationsError(
            "project SDK pin does not match the resolved SDK payload: "
            f"expected {manifest.sdk_version} {manifest.sdk_revision}, "
            f"got {resolved_version} {resolved_revision}"
        )
    gates: list[dict[str, str]] = []
    report: dict[str, object] | None = None
    verified_evidence: dict[str, bytes] = {}
    commands: list[tuple[str, ...]] = [
        ("assets",), ("build",), ("test",), ("report",),
        *(("play", scenario.id) for scenario in manifest.play_scenarios),
    ]
    for command in commands:
        name = command[0] if len(command) == 1 else ":".join(command)
        if notify:
            notify(name, "started")
        try:
            result = _gate(command, manifest, timeout, runner)
            if command == ("report",):
                try:
                    parsed = json.loads(result.stdout)
                except json.JSONDecodeError as exc:
                    raise OperationsError(
                        "report gate did not return valid JSON"
                    ) from exc
                if (
                    not isinstance(parsed, dict)
                    or parsed.get("schema") != "swansong-resource-report-v1"
                ):
                    raise OperationsError("report gate returned an unsupported schema")
                report = parsed
            if command[0] == "play":
                rom_path = manifest.root / manifest.rom_name
                rom_for_evidence = _read_release_bytes(rom_path, "built ROM")
                scenario = next(
                    item for item in manifest.play_scenarios if item.id == command[1]
                )
                verified_evidence.update(
                    _verified_evidence_files(manifest, scenario, rom_for_evidence)
                )
        except (OperationsError, OSError):
            if notify:
                notify(name, "failed")
            raise
        gates.append({"name": name, "status": "passed"})
        if notify:
            notify(name, "passed")
    if report is None:
        raise OperationsError("release report gate did not run")

    rom = manifest.root / manifest.rom_name
    if not rom.is_file():
        raise OperationsError(f"build gate did not produce {manifest.rom_name}")
    rom_payload = _read_release_bytes(rom, "built ROM")

    files: dict[str, bytes] = {
        f"rom/{rom.name}": rom_payload,
        "provenance.json": canonical_json(provenance).encode(),
        "report.json": canonical_json(report).encode(),
        "release-notes.md": _release_notes(manifest, Path(notes).resolve() if notes else None),
    }
    mono = manifest.root / (manifest.id.replace("-", "_") + ".ws")
    if manifest.hardware == "mono-compatible" and not mono.is_file():
        raise OperationsError(f"build gate did not produce mono validation ROM {mono.name}")
    if manifest.hardware == "mono-compatible":
        files[f"rom/{mono.name}"] = _read_release_bytes(mono, "mono validation ROM")
    files.update(verified_evidence)
    supply_chain = supply_chain_artifacts(manifest, provenance, files)
    files.update({
        name: canonical_json(document).encode()
        for name, document in supply_chain.items()
    })
    checksum_lines = [f"{_sha256(files[name])}  {name}" for name in sorted(files)]
    files["checksums.sha256"] = ("\n".join(checksum_lines) + "\n").encode()

    destination = _release_output(manifest, output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    prefix = f"{manifest.id}-{manifest.version}"
    with tempfile.TemporaryDirectory(prefix=".swan-release-", dir=destination.parent) as temporary:
        candidate = Path(temporary) / destination.name
        _write_deterministic_zip(candidate, prefix, files)
        package_payload = candidate.read_bytes()
        os.replace(candidate, destination)
    artifacts = [
        {"bytes": len(payload), "path": name, "sha256": _sha256(payload)}
        for name, payload in sorted(files.items())
    ]
    return {
        "artifacts": artifacts,
        "gates": gates,
        "ok": True,
        "package": str(destination),
        "packageSha256": _sha256(package_payload),
        "project": manifest.id,
        "schema": RELEASE_SCHEMA,
        "sdkRevision": provenance.get("sdkRevision"),
        "sdkVersion": provenance.get("sdkVersion"),
        "toolchainLockSha256": (
            provenance.get("toolchain", {}).get("lockSha256")
            if isinstance(provenance.get("toolchain"), dict) else None
        ),
        "version": manifest.version,
    }
