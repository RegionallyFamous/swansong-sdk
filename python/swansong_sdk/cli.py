"""Command-line entry point for SwanSong SDK projects."""

from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

from . import __version__
from .authoring import (
    KINDS as AUTHORING_KINDS, REPORT_SCHEMA as AUTHORING_REPORT_SCHEMA,
    AuthoringError, default_document, export_document, operation_report,
    validate_document,
)
from .audio_workbench import (
    AudioWorkbenchError, render_music_preview, simulate_sfx_arbitration,
)
from .asset_import import AssetImportError, import_asset
from .budget_history import BudgetHistoryError, compare_resource_reports
from .generator import GenerationError, asset_report, generate, validate_budgets
from .evidence import EvidenceError, EvidenceThresholds, diff_evidence, validate_wav
from .fuzzing import FuzzError, generate_fuzz_plan
from .laboratory import LaboratoryError, LaboratoryReport, run_laboratory
from .layout import LayoutError, sdk_root
from .identity import sdk_identity
from .manifest import ManifestError, find_manifest, load_manifest
from .migration import MigrationError, apply_migration, plan_migration
from .optimize import (
    ARTIST_APPROVAL, OptimizationError,
    apply_approved_asset_optimization, preview_asset_optimization,
    revert_approved_asset_optimization,
)
from .operations import (
    RELEASE_SCHEMA, OperationsError, canonical_json, development_session, doctor_report,
    release_project,
)
from .minimize import (
    FailureObservation, MinimizeError, minimize_plan,
    observe_evidence, observe_execution_error, validate_failure_predicate,
)
from .plans import (
    PlanError, load_plan, load_plan_file, validate_play_readiness,
)
from .png2bpp import PNGError
from .profiler import ProfileError, profile_resources
from .replay import ReplayError, build_replay_report, evidence_binding, validate_checkpoints
from .scaffold import RECIPES, ScaffoldError, create_project
from .scenario import ScenarioError, record_frame_log
from .scenario_script import ScenarioScriptError, compile_scenario_script
from .swansong import SwanSongError, play
from .trace import (
    TraceError, encode_trace, load_trace, outcome_report_bytes, trace_json_bytes,
    validate_outcome_contract, validate_scenario_outcome,
)


class CommandError(RuntimeError):
    pass


def _manifest(argument: str | None):
    return load_manifest(argument or find_manifest())


def _rom_path(manifest) -> Path:
    candidates = (
        manifest.root / manifest.rom_name,
        manifest.root / "build" / manifest.rom_name,
        manifest.root / "dist" / manifest.rom_name,
    )
    return next((path for path in candidates if path.is_file()), candidates[0])


def _linked_elf_path(manifest) -> Path:
    name = manifest.id.replace("-", "_") + ".elf"
    candidates = (manifest.root / "build" / name, manifest.root / name)
    return next((path for path in candidates if path.is_file()), candidates[0])


def _parse_linked_usage(output: str) -> dict[str, int | None]:
    def used(label: str) -> int | None:
        match = re.search(
            rf"^(?:\+?-?\s*)?{re.escape(label)}\s+(\d+)\s+",
            output, re.MULTILINE,
        )
        return int(match.group(1)) if match else None

    return {
        "linkedInternalRamBytes": used("Internal RAM"),
        "linkedMonoAreaBytes": used("Mono area"),
        "linkedColorAreaBytes": used("Color area"),
    }


def _linked_usage(manifest) -> dict[str, int | None]:
    empty = {
        "linkedInternalRamBytes": None,
        "linkedMonoAreaBytes": None,
        "linkedColorAreaBytes": None,
    }
    elf = _linked_elf_path(manifest)
    if not elf.is_file():
        return empty
    root = Path(os.environ.get("WONDERFUL_TOOLCHAIN", "/opt/wonderful"))
    tool = root / "bin" / "wf-wswantool"
    located = shutil.which("wf-wswantool")
    if not tool.is_file() and located:
        tool = Path(located)
    if not tool.is_file():
        return empty
    try:
        result = subprocess.run(
            [str(tool), "usage", "-C", "--hide-linear-banks", str(elf)],
            cwd=manifest.root, check=True, capture_output=True, text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return empty
    return _parse_linked_usage(result.stdout + result.stderr)


def command_new(args: argparse.Namespace) -> None:
    target = create_project(args.name, args.template, args.directory)
    print(f"Created {target}")
    print(f"Next: cd {target} && swan assets && swan build")


def command_sdk_path(args: argparse.Namespace) -> None:
    del args
    print(sdk_root())


def command_doctor(args: argparse.Namespace) -> int:
    report = doctor_report(args.project, timeout=args.timeout)
    if args.json:
        print(canonical_json(report), end="")
    else:
        print(f"SwanSong doctor: {'PASS' if report['ok'] else 'FAIL'}")
        for check in report["checks"]:
            print(f"[{str(check['status']).upper():4}] {check['id']}: {check['message']}")
    return 0 if report["ok"] else 2


def command_hardware_tile_capacity(args: argparse.Namespace) -> None:
    manifest = _manifest(args.project)
    print(512 if manifest.hardware == "mono-compatible" else 1024)


def command_assets(args: argparse.Namespace) -> None:
    manifest = _manifest(args.project)
    compiled = generate(manifest)
    print(f"Generated {len(compiled)} assets in {manifest.root / 'build' / 'generated'}")


def _run_make(manifest, targets: list[str], *, variables: list[str] | None = None) -> None:
    environment = os.environ.copy()
    environment.setdefault("SWANSONG_SDK_DIR", str(sdk_root()))
    environment.setdefault(
        "SWAN", f"{shlex.quote(sys.executable)} -m swansong_sdk.cli",
    )
    environment.setdefault(
        "SWAN_GFX_HARDWARE_TILE_CAPACITY",
        "512" if manifest.hardware == "mono-compatible" else "1024",
    )
    try:
        subprocess.run(
            ["make", *(variables or []), *targets],
            cwd=manifest.root, env=environment, check=True,
        )
    except FileNotFoundError as exc:
        raise CommandError("make is not installed") from exc
    except subprocess.CalledProcessError as exc:
        raise CommandError(f"make {' '.join(targets) or 'all'} failed with exit code {exc.returncode}") from exc


def command_build(args: argparse.Namespace) -> None:
    manifest = _manifest(args.project)
    generate(manifest)
    variables = []
    if args.trace:
        if not 1 <= args.trace_capacity <= 255:
            raise CommandError("trace capacity must be between 1 and 255 frames")
        variables = ["SWAN_TRACE=1", f"SWAN_TRACE_CAPACITY={args.trace_capacity}"]
    _run_make(manifest, [args.target] if args.target else [], variables=variables)
    if args.target is None and manifest.hardware == "mono-compatible":
        root = Path(os.environ.get("WONDERFUL_TOOLCHAIN", "/opt/wonderful"))
        tool = root / "bin" / "wf-wswantool"
        located = shutil.which("wf-wswantool")
        if not tool.is_file() and located:
            tool = Path(located)
        stage = manifest.root / "build" / f"{manifest.id.replace('-', '_')}_stage1.elf"
        mono = manifest.root / (manifest.id.replace("-", "_") + ".ws")
        config = manifest.root / "build" / "generated" / "wfconfig.mono.toml"
        if not tool.is_file() or not stage.is_file():
            raise CommandError("mono-compatible validation requires wf-wswantool and the primary stage-1 ELF")
        try:
            subprocess.run(
                [str(tool), "build", "rom", "--config", str(config), "-o", str(mono), str(stage)],
                cwd=manifest.root, check=True,
            )
        except subprocess.CalledProcessError as exc:
            raise CommandError(f"mono-compatible ROM validation failed with exit code {exc.returncode}") from exc
    command_report(argparse.Namespace(project=str(manifest.root / "swan.toml"), json=False))


def command_test(args: argparse.Namespace) -> None:
    manifest = _manifest(args.project)
    generate(manifest)
    _run_make(manifest, ["test"])


def _scenario_outcome_contract(manifest, scenario) -> dict[str, object] | None:
    if scenario.outcome_contract is None:
        return None
    path = (manifest.root / scenario.outcome_contract).resolve()
    try:
        path.relative_to(manifest.root)
    except ValueError as exc:
        raise CommandError("scenario outcome contract must remain inside the project") from exc
    return validate_outcome_contract(
        _read_json_object(path, "scenario outcome contract")
    )


def _trace_from_evidence(evidence: dict[str, object]):
    structured = evidence.get("deterministicTrace")
    if isinstance(structured, dict):
        return load_trace(structured)
    encoded = evidence.get("deterministicTraceBase64")
    if isinstance(encoded, str):
        try:
            return load_trace(base64.b64decode(encoded, validate=True))
        except ValueError as exc:
            raise TraceError("SwanSong returned invalid deterministicTraceBase64") from exc
    return None


def _play_scenario(manifest, scenario, *, verify_replay: bool) -> None:
    _, plan = load_plan(
        manifest.root, scenario.plan, ready_frames=manifest.play_ready_frames
    )
    rom = _rom_path(manifest)
    if not rom.is_file():
        raise CommandError(f"ROM is not built: {rom}; run swan build first")
    output = manifest.root / "build" / "swansong" / scenario.id
    evidence = play(rom, plan, output=output, verify_replay=verify_replay)
    contract = _scenario_outcome_contract(manifest, scenario)
    if contract is not None:
        trace = _trace_from_evidence(evidence)
        if trace is None:
            raise CommandError(
                f"scenario {scenario.id!r} requires a deterministic runtime trace, "
                "but this SwanSong build did not return one"
            )
        audio = validate_wav(
            output / "audio.wav", signal_floor=scenario.audio_evidence.signal_floor,
        )
        audio["inspected"] = True
        outcome = validate_scenario_outcome(contract, trace, audio=audio)
        (output / "trace.swtr").write_bytes(encode_trace(trace))
        (output / "trace.json").write_bytes(trace_json_bytes(trace))
        (output / "outcome-report.json").write_bytes(outcome_report_bytes(outcome))
        if not outcome["passed"]:
            failed = ", ".join(
                item["id"] for item in outcome["checks"] if not item["passed"]
            )
            raise CommandError(f"scenario outcome failed: {failed}")
    print(f"SwanSong evidence: {output}")
    if evidence.get("finalGameRasterSHA256"):
        print(f"Raster SHA-256: {evidence['finalGameRasterSHA256']}")


def command_play(args: argparse.Namespace) -> None:
    manifest = _manifest(args.project)
    generate(manifest)
    if args.all:
        if args.scenario:
            raise CommandError("swan play accepts either a scenario or --all, not both")
        if not manifest.play_scenarios:
            raise CommandError("project declares no SwanSong scenarios")
        for scenario in manifest.play_scenarios:
            _play_scenario(
                manifest, scenario, verify_replay=not args.no_verify_replay,
            )
        return
    if not args.scenario:
        raise CommandError("swan play requires a scenario or --all")
    scenario = next(
        (item for item in manifest.play_scenarios if item.id == args.scenario), None
    )
    if scenario is None:
        choices = ", ".join(item.id for item in manifest.play_scenarios) or "none declared"
        raise CommandError(f"unknown scenario {args.scenario!r}; available: {choices}")
    _play_scenario(manifest, scenario, verify_replay=not args.no_verify_replay)


def command_outcome(args: argparse.Namespace) -> int:
    manifest = _manifest(args.project)
    scenario = next(
        (item for item in manifest.play_scenarios if item.id == args.scenario), None
    )
    if scenario is None:
        raise CommandError(f"unknown scenario {args.scenario!r}")
    contract = _scenario_outcome_contract(manifest, scenario)
    if contract is None:
        raise CommandError(f"scenario {scenario.id!r} does not declare an outcome contract")
    trace_path = Path(args.trace).resolve()
    wav_path = Path(args.wav).resolve()
    audio = validate_wav(wav_path, signal_floor=scenario.audio_evidence.signal_floor)
    audio["inspected"] = args.inspected
    audio["path"] = str(wav_path)
    report = validate_scenario_outcome(contract, load_trace(trace_path), audio=audio)
    report.update({
        "project": manifest.id,
        "scenario": scenario.id,
        "traceFile": str(trace_path),
        "wavFile": str(wav_path),
    })
    if args.output:
        destination = _output_path(manifest, args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(outcome_report_bytes(report))
    if args.json:
        print(canonical_json(report), end="")
    else:
        print(f"Scenario outcome: {'PASS' if report['passed'] else 'FAIL'}")
        for check in report["checks"]:
            print(f"[{'PASS' if check['passed'] else 'FAIL'}] {check['id']}")
    return 0 if report["passed"] else 2


def _human_dev_event(event: dict[str, object]) -> None:
    event_type = event["type"]
    if event_type == "start":
        print(f"Watching {event['project']} with scenario {event['scenario']}")
    elif event_type == "change":
        print("Change: " + ", ".join(str(item) for item in event["changed"]))
    elif event_type == "gate":
        print(f"[{str(event['status']).upper():7}] {event['gate']}")
    elif event_type == "stop":
        print(f"Stopped after {event['builds']} build(s) and {event['pollCycles']} poll cycle(s)")


def command_dev(args: argparse.Namespace) -> None:
    manifest = _manifest(args.project)
    if args.json:
        def sink(event: dict[str, object]) -> None:
            args._dev_next_sequence = int(event["sequence"]) + 1
            print(canonical_json(event, compact=True), end="")
    else:
        sink = _human_dev_event
    development_session(
        manifest, scenario=args.scenario, once=args.once,
        poll_cycles=args.poll_cycles, poll_interval=args.poll_interval,
        debounce=args.debounce, timeout=args.timeout,
        test_mode=args.test_mode, sink=sink,
    )


def command_release(args: argparse.Namespace) -> None:
    manifest = _manifest(args.project)
    baseline = (
        _read_json_object(Path(args.baseline_report).resolve(), "baseline resource report")
        if args.baseline_report else None
    )
    allowed = _budget_allowances(args.allow_increase)

    def notify(name: str, status: str) -> None:
        if not args.json:
            print(f"[{status.upper():7}] {name}")

    try:
        report = release_project(
            manifest, output=args.output, notes=args.notes,
            timeout=args.timeout, notify=notify, baseline_report=baseline,
            allowed_budget_increase=allowed,
        )
    except OperationsError as exc:
        if not args.json:
            raise
        report = _release_error_report(
            str(exc), project=manifest.id, version=manifest.version,
            code="release-gate-failed",
        )
        print(canonical_json(report), end="")
        return 2
    if args.json:
        print(canonical_json(report), end="")
    else:
        print(f"Release: {report['package']}")
        print(f"SHA-256: {report['packageSha256']}")


def command_report(args: argparse.Namespace) -> None:
    manifest = _manifest(args.project)
    compiled = generate(manifest)
    report = asset_report(manifest, compiled)
    rom = _rom_path(manifest)
    report["romBytes"] = rom.stat().st_size if rom.is_file() else None
    report.update(_linked_usage(manifest))
    report["internalRamHardwareBytes"] = 64 * 1024
    report["monoAreaHardwareBytes"] = 16 * 1024
    report["colorAreaHardwareBytes"] = 48 * 1024
    failures = validate_budgets(manifest, report, rom_path=rom)
    linked_iram = report["linkedInternalRamBytes"]
    mono_area = report["linkedMonoAreaBytes"]
    color_area = report["linkedColorAreaBytes"]
    if linked_iram is not None and linked_iram > 64 * 1024:
        failures.append(
            f"linked internal RAM: {linked_iram} exceeds "
            "65536 byte Color hardware limit"
        )
    if mono_area is not None and mono_area > 16 * 1024:
        failures.append(
            f"linked mono area: {mono_area} exceeds 16384 byte hardware limit"
        )
    if color_area is not None and color_area > 48 * 1024:
        failures.append(
            f"linked Color extension area: {color_area} exceeds 49152 byte hardware limit"
        )
    report["budgetFailures"] = failures
    baseline_path = getattr(args, "baseline_report", None)
    if baseline_path:
        history = compare_resource_reports(
            report,
            _read_json_object(Path(baseline_path).resolve(), "baseline resource report"),
            allowed_increase=_budget_allowances(getattr(args, "allow_increase", [])),
        )
        report["budgetHistory"] = history
        failures.extend(
            "historical budget regression: " + item for item in history["regressions"]
        )
        report["budgetFailures"] = failures
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        scene_usage = report["sceneUsage"]
        peak_tiles = max((item["vramTiles"] for item in scene_usage), default=0)
        peak_palettes = max((item["palettes"] for item in scene_usage), default=0)
        values = (
            ("ROM", report["romBytes"], manifest.budgets.rom_bytes, "bytes"),
            ("Work RAM", manifest.resources.work_ram_bytes, manifest.budgets.work_ram_bytes, "bytes"),
            ("Linked IRAM", report["linkedInternalRamBytes"], report["internalRamHardwareBytes"], "bytes"),
            ("Mono area", report["linkedMonoAreaBytes"], report["monoAreaHardwareBytes"], "bytes"),
            ("Color area", report["linkedColorAreaBytes"], report["colorAreaHardwareBytes"], "bytes"),
            ("VRAM", peak_tiles, manifest.budgets.vram_tiles, "tiles"),
            ("Palettes", peak_palettes, manifest.budgets.palettes, "palettes"),
            ("Sprites", manifest.resources.sprites, manifest.budgets.sprites, "sprites"),
            ("Sprite scanline", manifest.resources.sprites_per_scanline, manifest.budgets.sprites_per_scanline, "sprites"),
            ("Audio", report["audioBytes"], manifest.budgets.audio_bytes, "bytes"),
        )
        for label, actual, budget, unit in values:
            display = "not built" if actual is None else str(actual)
            print(f"{label:16} {display:>10} / {budget:<10} {unit}")
    if failures:
        raise CommandError("resource budget failure:\n  " + "\n  ".join(failures))


def _budget_allowances(values: list[str] | None) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values or []:
        name, separator, raw = value.partition("=")
        if not separator or not name or not raw.isdigit():
            raise CommandError("budget allowance must be METRIC=NON_NEGATIVE_INTEGER")
        if name in result:
            raise CommandError(f"duplicate budget allowance for {name}")
        result[name] = int(raw)
    return result


def _read_json_object(path: Path, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise CommandError(f"{label} does not exist: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise CommandError(f"could not read {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CommandError(f"{label} must contain one JSON object: {path}")
    return value


def _output_path(manifest, value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (manifest.root / path).resolve()


def command_scenario_record(args: argparse.Namespace) -> None:
    manifest = _manifest(args.project)
    source = Path(args.input_log).resolve()
    report = record_frame_log(_read_json_object(source, "input frame log"))
    destination = _output_path(manifest, args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(canonical_json(report["plan"]))
    report["inputLog"] = str(source)
    report["outputPlan"] = str(destination)
    if args.json:
        print(canonical_json(report), end="")
    else:
        print(f"Recorded {len(report['plan']['events'])} input transitions")
        print(f"Plan: {destination}")


def command_scenario_compile(args: argparse.Namespace) -> None:
    manifest = _manifest(args.project)
    source = _project_owned_path(manifest, args.script, label="scenario script")
    document = _read_json_object(source, "scenario script")
    report = compile_scenario_script(
        document, ready_frames=manifest.play_ready_frames, source=source,
    )
    destination = _project_owned_path(manifest, args.output, label="scenario plan output")
    if destination.suffix.lower() != ".json":
        raise ScenarioScriptError("scenario plan output must use a .json suffix")
    _write_new_file(
        destination, canonical_json(report["plan"]).encode("utf-8"),
        label="scenario plan",
    )
    report["project"] = manifest.id
    report["output"] = str(destination)
    if args.json:
        print(canonical_json(report), end="")
    else:
        print(
            f"Compiled {report['expandedActions']} deterministic actions into "
            f"{report['plan']['totalFrames']} frames"
        )
        print(f"Plan: {destination}")


def _project_owned_path(manifest, value: str, *, label: str) -> Path:
    raw = Path(value)
    candidate = raw if raw.is_absolute() else manifest.root / raw
    resolved = candidate.resolve()
    try:
        resolved.relative_to(manifest.root.resolve())
    except ValueError as exc:
        raise AuthoringError(f"{label} must remain inside the project root") from exc
    if resolved == manifest.root.resolve():
        raise AuthoringError(f"{label} must name a file inside the project root")
    return resolved


def _write_new_file(path: Path, payload: bytes, *, label: str) -> None:
    if path.exists():
        raise AuthoringError(f"refusing to overwrite existing {label}: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as destination:
            destination.write(payload)
    except FileExistsError as exc:
        raise AuthoringError(f"refusing to overwrite existing {label}: {path}") from exc


def _load_author_document(manifest, argument: str) -> tuple[Path, dict[str, object]]:
    path = _project_owned_path(manifest, argument, label="authoring document")
    return path, validate_document(_read_json_object(path, "authoring document"))


def _print_author_report(report: dict[str, object]) -> None:
    print(
        f"Author {str(report['operation']).upper()}: {report['kind']} "
        f"({len(report['findings'])} finding(s))"
    )
    print(f"Document: {report['document']}")
    if report["output"]:
        print(f"Output: {report['output']}")
    print("Authoring output is not gameplay evidence.")


def command_author_create(args: argparse.Namespace) -> None:
    manifest = _manifest(args.project)
    document = default_document(args.kind, args.id)
    destination = _project_owned_path(
        manifest,
        args.output or f"authoring/{args.id}.{args.kind}.json",
        label="authoring document output",
    )
    if destination.suffix.lower() != ".json":
        raise AuthoringError("authoring document output must use a .json suffix")
    _write_new_file(
        destination, canonical_json(document).encode("utf-8"),
        label="authoring document",
    )
    report = operation_report(
        "create", document, project=manifest.id, document_path=destination,
    )
    if args.json:
        print(canonical_json(report), end="")
    else:
        _print_author_report(report)


def command_author_validate(args: argparse.Namespace) -> None:
    manifest = _manifest(args.project)
    path, document = _load_author_document(manifest, args.document)
    report = operation_report(
        "validate", document, project=manifest.id, document_path=path,
    )
    if args.json:
        print(canonical_json(report), end="")
    else:
        _print_author_report(report)


def command_author_report(args: argparse.Namespace) -> None:
    manifest = _manifest(args.project)
    path, document = _load_author_document(manifest, args.document)
    report = operation_report(
        "report", document, project=manifest.id, document_path=path,
    )
    if args.output:
        destination = _project_owned_path(
            manifest, args.output, label="author report output",
        )
        if destination.suffix.lower() != ".json":
            raise AuthoringError("author report output must use a .json suffix")
        report["output"] = str(destination)
        _write_new_file(
            destination, canonical_json(report).encode("utf-8"),
            label="author report",
        )
    if args.json:
        print(canonical_json(report), end="")
    else:
        _print_author_report(report)


def command_author_export(args: argparse.Namespace) -> None:
    manifest = _manifest(args.project)
    path, document = _load_author_document(manifest, args.document)
    destination = _project_owned_path(
        manifest, args.output, label="author export output",
    )
    payload, export = export_document(document)
    if destination.suffix.lower() != export["requiredSuffix"]:
        raise AuthoringError(
            f"{document['schema']} export must use {export['requiredSuffix']}"
        )
    _write_new_file(destination, payload, label="author export")
    report = operation_report(
        "export", document, project=manifest.id, document_path=path,
        output_path=destination, export=export,
    )
    if args.json:
        print(canonical_json(report), end="")
    else:
        _print_author_report(report)


def _candidate_failure(rom: Path, plan: dict[str, object],
                       predicate: dict[str, object], *, output: Path,
                       timeout: float) -> FailureObservation:
    if predicate["kind"] == "structured-evidence":
        try:
            evidence = play(
                rom, plan, output=output, verify_replay=True, timeout=timeout,
            )
        except SwanSongError as exc:
            return FailureObservation(False, {
                "kind": "unexpected-execution-error", "message": str(exc),
            })
        return observe_evidence(predicate, evidence)

    messages: list[str] = []
    for replay_index in range(2):
        try:
            play(
                rom, plan, output=output / f"replay-{replay_index}",
                verify_replay=False, timeout=timeout,
            )
        except SwanSongError as exc:
            messages.append(str(exc))
        else:
            return FailureObservation(False, {"kind": "unexpected-success"})
    if messages[0] != messages[1]:
        return FailureObservation(False, {
            "kind": "nondeterministic-execution-error", "messages": messages,
        })
    return observe_execution_error(predicate, messages[0])


def command_minimize(args: argparse.Namespace) -> None:
    manifest = _manifest(args.project)
    plan_path, source_plan = load_plan_file(Path(args.plan))
    predicate_path = Path(args.predicate).resolve()
    predicate = validate_failure_predicate(
        _read_json_object(predicate_path, "failure predicate"), predicate_path,
    )
    rom = _rom_path(manifest)
    if not rom.is_file():
        raise CommandError(f"ROM is not built: {rom}; run swan build first")

    def evaluator(candidate: dict[str, object]) -> FailureObservation:
        with tempfile.TemporaryDirectory(prefix="swan-minimize-") as temporary:
            return _candidate_failure(
                rom, candidate, predicate, output=Path(temporary),
                timeout=args.timeout,
            )

    minimized, report = minimize_plan(
        source_plan, evaluator, maximum_evaluations=args.max_evaluations,
        predicate=predicate,
    )
    destination = _output_path(manifest, args.output)
    evidence_output = (
        _output_path(manifest, args.evidence_output) if args.evidence_output else
        manifest.root / "build" / "swansong" / "minimize"
    )
    final_observation = _candidate_failure(
        rom, minimized, predicate, output=evidence_output, timeout=args.timeout,
    )
    if not final_observation.matched:
        raise MinimizeError("final fresh-boot verification did not preserve the predicate")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(canonical_json(minimized))
    report.update({
        "project": manifest.id,
        "rom": str(rom.resolve()),
        "sourcePlan": str(plan_path),
        "predicateFile": str(predicate_path),
        "outputPlan": str(destination),
        "evidenceDirectory": (
            str(evidence_output.resolve())
            if predicate["kind"] == "structured-evidence" else None
        ),
        "finalVerificationResult": dict(final_observation.result),
    })
    if args.report:
        report_path = _output_path(manifest, args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report["reportFile"] = str(report_path)
        report_path.write_text(canonical_json(report))
    if args.json:
        print(canonical_json(report), end="")
    else:
        print(
            f"Minimized {report['source']['totalFrames']} to "
            f"{report['minimized']['totalFrames']} frames in "
            f"{report['evaluations']} predicate evaluation(s)"
        )
        print(f"Plan: {destination}")


def _parse_evidence_argument(value: str) -> tuple[str, Path]:
    identifier, separator, directory = value.partition("=")
    if not separator or not identifier or not directory:
        raise ReplayError("evidence must use ID=DIRECTORY")
    return identifier, Path(directory)


def command_replay(args: argparse.Namespace) -> None:
    manifest = _manifest(args.project)
    scenario_metadata: dict[str, object] | None = None
    scenario_ready_frames: int | None = None
    plan_argument = args.plan
    if args.scenario:
        scenario = next(
            (item for item in manifest.play_scenarios if item.id == args.scenario), None
        )
        if scenario is None:
            choices = ", ".join(item.id for item in manifest.play_scenarios)
            raise CommandError(
                f"unknown scenario {args.scenario!r}; available: {choices or 'none declared'}"
            )
        if plan_argument is None:
            plan_argument = str(manifest.root / scenario.plan)
        scenario_ready_frames = manifest.play_ready_frames
        scenario_metadata = {
            "id": scenario.id,
            "title": scenario.title,
            "goal": scenario.goal,
            "requiredChecks": list(scenario.required_checks),
            "requiresAudioEvidence": scenario.audio,
            "audioExpectation": scenario.audio_expectation,
            **(
                {"audioEvidence": scenario.audio_evidence.to_contract()}
                if scenario.audio_evidence.configured else {}
            ),
        }
    if plan_argument is None:
        raise CommandError("swan replay requires --plan or --scenario")
    plan_path, plan = load_plan_file(Path(plan_argument))
    if scenario_ready_frames is not None:
        validate_play_readiness(plan, plan_path, scenario_ready_frames)
    checkpoints = None
    checkpoint_path = None
    if args.checkpoints:
        checkpoint_path = Path(args.checkpoints).resolve()
        checkpoints = validate_checkpoints(
            _read_json_object(checkpoint_path, "replay checkpoints"),
            total_frames=plan["totalFrames"], path=checkpoint_path,
        )
    trace = None
    trace_path = None
    if args.trace:
        trace_path = Path(args.trace).resolve()
        trace = _read_json_object(trace_path, "replay trace")
    bindings = []
    for raw in args.evidence:
        identifier, directory = _parse_evidence_argument(raw)
        bindings.append(evidence_binding(identifier, directory))
    report = build_replay_report(
        plan, checkpoints=checkpoints, evidence=bindings, trace=trace,
        scenario=scenario_metadata,
    )
    report.update({
        "project": manifest.id,
        "planFile": str(plan_path),
        "checkpointFile": str(checkpoint_path) if checkpoint_path else None,
        "traceFile": str(trace_path) if trace_path else None,
    })
    if args.output:
        destination = _output_path(manifest, args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        report["outputFile"] = str(destination)
        destination.write_text(canonical_json(report))
    if args.json:
        print(canonical_json(report), end="")
    else:
        print(
            f"Replay timeline: {report['plan']['totalFrames']} frames, "
            f"{len(report['timeline'])} indexed point(s)"
        )
        print(
            f"Checkpoints: {len(report['checkpoints'])}; "
            f"evidence: {len(report['evidenceBindings'])}"
        )


def _evidence_files(directory: Path) -> tuple[Path, Path, dict[str, object]]:
    png = directory / "frame.png"
    wav = directory / "audio.wav"
    metadata_path = directory / "evidence.json"
    missing = [path.name for path in (png, wav, metadata_path) if not path.is_file()]
    if missing:
        raise CommandError(
            f"evidence directory {directory} is missing: {', '.join(missing)}"
        )
    return png, wav, _read_json_object(metadata_path, "structured evidence")


def command_evidence_diff(args: argparse.Namespace) -> int:
    before_dir = Path(args.before).resolve()
    after_dir = Path(args.after).resolve()
    before_png, before_wav, before_metadata = _evidence_files(before_dir)
    after_png, after_wav, after_metadata = _evidence_files(after_dir)
    scenario_audio = None
    if args.scenario:
        manifest = _manifest(args.project)
        scenario = next(
            (item for item in manifest.play_scenarios if item.id == args.scenario), None
        )
        if scenario is None:
            choices = ", ".join(item.id for item in manifest.play_scenarios)
            raise CommandError(
                f"unknown scenario {args.scenario!r}; available: {choices or 'none declared'}"
            )
        scenario_audio = scenario.audio_evidence
    elif args.project:
        raise CommandError("evidence-diff --project requires --scenario")

    def audio_limit(argument: str, contract: str, default: float | None = None
                    ) -> float | None:
        value = getattr(args, argument)
        if value is not None:
            return value
        if scenario_audio is not None:
            return getattr(scenario_audio, contract)
        return default

    thresholds = EvidenceThresholds(
        pixel_channel_tolerance=args.pixel_tolerance,
        changed_pixel_ratio=args.pixel_ratio,
        pcm_sample_tolerance=args.sample_tolerance,
        changed_sample_ratio=args.sample_ratio,
        normalized_rms_delta=args.rms_delta,
        audio_signal_floor=audio_limit("audio_floor", "signal_floor", 0.0) or 0.0,
        stereo_balance_delta=audio_limit(
            "stereo_balance_delta", "max_stereo_balance_delta"
        ),
        cue_onset_delta_ms=audio_limit(
            "cue_onset_delta_ms", "max_cue_onset_delta_ms"
        ),
        silent_frame_ratio_increase=audio_limit(
            "silent_frame_ratio_increase", "max_silent_frame_ratio_increase"
        ),
        internal_silence_increase_ms=audio_limit(
            "internal_silence_increase_ms", "max_internal_silence_increase_ms"
        ),
        clipped_sample_ratio_increase=audio_limit(
            "clipped_sample_ratio_increase", "max_clipped_sample_ratio_increase"
        ),
        loop_seam_delta_increase=audio_limit(
            "loop_seam_delta_increase", "max_loop_seam_delta_increase"
        ),
    )
    report = diff_evidence(
        before_png=before_png,
        after_png=after_png,
        before_wav=before_wav,
        after_wav=after_wav,
        before_metadata=before_metadata,
        after_metadata=after_metadata,
        thresholds=thresholds,
    ).to_dict()
    report["beforeDirectory"] = str(before_dir)
    report["afterDirectory"] = str(after_dir)
    report["regressionCandidate"] = report["meaningfulDifference"]
    if args.json:
        print(canonical_json(report), end="")
    else:
        verdict = "REVIEW" if report["meaningfulDifference"] else "MATCH"
        print(f"Evidence diff: {verdict}")
        print(f"Pixels changed: {report['png']['changedPixels']}")
        print(f"PCM samples changed: {report['wav']['changedSamples']}")
    return 1 if args.fail_on_difference and report["meaningfulDifference"] else 0


def _neutral_plan(total_frames: int) -> dict[str, object]:
    return {
        "schema": "swan-song-frame-input-plan-v1",
        "totalFrames": total_frames,
        "events": [{"frameIndex": 0, "inputs": []}],
    }


def command_fuzz(args: argparse.Namespace) -> int:
    manifest = _manifest(args.project)
    if args.cases <= 0:
        raise CommandError("fuzz cases must be positive")
    if not 1 <= args.frames <= 12_000:
        raise CommandError("fuzz frames must be between 1 and 12000")
    neutral_boot_frames = (
        manifest.play_ready_frames
        if args.neutral_boot_frames is None else args.neutral_boot_frames
    )
    if neutral_boot_frames < manifest.play_ready_frames:
        raise CommandError(
            f"fuzz neutral boot frames {neutral_boot_frames} cannot precede "
            f"play.ready_frames {manifest.play_ready_frames}"
        )
    generated = [
        generate_fuzz_plan(
            seed=(args.seed + index) & 0xFFFFFFFF,
            total_frames=args.frames,
            neutral_boot_frames=min(neutral_boot_frames, args.frames),
            maximum_actions=args.maximum_actions,
        ).to_dict()
        for index in range(args.cases)
    ]
    report: dict[str, object] = {
        "schema": "swansong-fuzz-report-v1",
        "project": manifest.id,
        "seed": args.seed,
        "casesRequested": args.cases,
        "framesPerCase": args.frames,
        "readyFrames": manifest.play_ready_frames,
        "mode": "generation" if args.generate_only else "swansong-execution",
        "verdict": "ready" if args.generate_only else "review",
        "checks": {
            "crashes": "SwanSong execution result",
            "deadEnds": "final raster candidate plus required PNG/WAV review",
            "invalidTransitions": "validated exact-frame input plan",
            "resetDivergence": "identical fresh-boot replay",
        },
        "findings": [],
        "cases": [],
    }
    if args.generate_only:
        report["cases"] = generated
    else:
        rom = _rom_path(manifest)
        if not rom.is_file():
            raise CommandError(f"ROM is not built: {rom}; run swan build first")
        baseline_output = manifest.root / "build" / "swansong" / "fuzz" / "baseline"
        try:
            baseline = play(
                rom, _neutral_plan(args.frames), output=baseline_output,
                verify_replay=True,
            )
        except SwanSongError as exc:
            report["verdict"] = "fail"
            report["findings"] = [{
                "severity": "error",
                "code": "baseline-execution-or-reset-divergence",
                "message": str(exc),
            }]
            report["cases"] = [
                {**item, "status": "not-run"} for item in generated
            ]
            if args.json:
                print(canonical_json(report), end="")
            else:
                print("Fuzz verdict: FAIL")
                print("The neutral SwanSong baseline failed; cases were not run.")
            return 2
        baseline_raster = baseline.get("finalGameRasterSHA256")
        cases: list[dict[str, object]] = []
        findings: list[dict[str, object]] = []
        for index, generated_case in enumerate(generated):
            seed = int(generated_case["seed"])
            output = manifest.root / "build" / "swansong" / "fuzz" / f"case-{index:04d}"
            case: dict[str, object] = {
                "index": index,
                "seed": seed,
                "plan": generated_case["plan"],
                "evidenceDirectory": str(output),
            }
            try:
                evidence = play(
                    rom, generated_case["plan"], output=output,
                    verify_replay=True,
                )
            except SwanSongError as exc:
                finding = {
                    "severity": "error",
                    "code": "execution-or-reset-divergence",
                    "caseIndex": index,
                    "seed": seed,
                    "message": str(exc),
                }
                case["status"] = "failed"
                case["finding"] = finding
                findings.append(finding)
            else:
                raster = evidence.get("finalGameRasterSHA256")
                case["status"] = "needs-observation"
                case["finalGameRasterSHA256"] = raster
                case["observableResponse"] = raster != baseline_raster
                if raster == baseline_raster:
                    findings.append({
                        "severity": "notice",
                        "code": "no-final-raster-response",
                        "caseIndex": index,
                        "seed": seed,
                        "message": (
                            "input returned to the neutral final raster; inspect the PNG/WAV "
                            "before classifying a dead end"
                        ),
                    })
            cases.append(case)
        report["baselineEvidenceDirectory"] = str(baseline_output)
        report["baselineFinalGameRasterSHA256"] = baseline_raster
        report["cases"] = cases
        report["findings"] = findings
        if any(item["severity"] == "error" for item in findings):
            report["verdict"] = "fail"
    if args.json:
        print(canonical_json(report), end="")
    else:
        print(f"Fuzz verdict: {str(report['verdict']).upper()}")
        print(f"Cases: {args.cases} × {args.frames} frames")
        if report["findings"]:
            print(f"Findings: {len(report['findings'])}")
    return 2 if report["verdict"] == "fail" else 0


def _project_resource_report(manifest) -> dict[str, object]:
    compiled = generate(manifest)
    report = asset_report(manifest, compiled)
    rom = _rom_path(manifest)
    report["romBytes"] = rom.stat().st_size if rom.is_file() else None
    report.update(_linked_usage(manifest))
    return report


def command_profile(args: argparse.Namespace) -> int:
    manifest = _manifest(args.project)
    trace = _read_json_object(Path(args.trace).resolve(), "profile trace") if args.trace else None
    report = profile_resources(
        manifest=manifest,
        report=_project_resource_report(manifest),
        trace=trace,
    ).to_dict()
    report["project"] = manifest.id
    report["trace"] = str(Path(args.trace).resolve()) if args.trace else None
    if args.json:
        print(canonical_json(report), end="")
    else:
        print(f"Profile: {report['framesAnalyzed']} traced frame(s)")
        for label, value in report["peaks"].items():
            print(f"{label:24} {value}")
        print(f"Findings: {len(report['findings'])}")
    return 2 if any(item.get("severity") == "error" for item in report["findings"]) else 0


def command_optimize(args: argparse.Namespace) -> None:
    manifest = _manifest(args.project)
    if args.revert:
        if not args.report or not args.expected_report_sha256 or not args.approval:
            raise OptimizationError(
                "optimization revert requires --report, --expected-report-sha256, "
                "and --approval artist-approved"
            )
        report = revert_approved_asset_optimization(
            manifest.root, args.report,
            expected_report_sha256=args.expected_report_sha256,
            approval=args.approval,
        )
        report["project"] = manifest.id
        if args.json:
            print(canonical_json(report), end="")
        else:
            print(f"Reverted generated optimization: {report['removedOutput']}")
            print("The original artist source remains unchanged.")
        return
    if args.apply:
        if args.asset is None:
            raise OptimizationError("optimization apply requires --asset")
        if (not args.output or not args.report or not args.operation or
                not args.expected_source_sha256 or not args.approval):
            raise OptimizationError(
                "optimization apply requires --output, --report, --operation, "
                "--expected-source-sha256, and --approval artist-approved"
            )
        asset = next((item for item in manifest.assets if item.id == args.asset), None)
        if asset is None or asset.type not in {
                "fullscreen", "tilemap", "spritesheet", "metatiles", "font"}:
            raise OptimizationError(f"unknown graphic asset {args.asset!r}")
        report = apply_approved_asset_optimization(
            manifest.root, asset.source, args.output, args.report,
            asset_id=asset.id, operations=tuple(args.operation),
            expected_source_sha256=args.expected_source_sha256,
            approval=args.approval,
        )
        report["project"] = manifest.id
        if args.json:
            print(canonical_json(report), end="")
        else:
            print(f"Applied approved optimization: {report['output']['path']}")
            print(f"Apply report SHA-256: {report['reportSHA256']}")
            print("The original artist source remains unchanged.")
        return
    graphic_types = {"fullscreen", "tilemap", "spritesheet", "metatiles", "font"}
    assets: dict[str, Path] = {}
    for asset in manifest.assets:
        if asset.type not in graphic_types or (args.asset is not None and asset.id != args.asset):
            continue
        source = (manifest.root / asset.source).resolve()
        try:
            source.relative_to(manifest.root)
        except ValueError as exc:
            raise CommandError(
                f"asset {asset.id} points outside the project: {asset.source}"
            ) from exc
        assets[asset.id] = source
    if args.asset is not None and not assets:
        raise CommandError(f"unknown graphic asset {args.asset!r}")
    report = preview_asset_optimization(assets).to_dict()
    report["project"] = manifest.id
    if not assets:
        report["notice"] = "project declares no source PNG assets to optimize"
    if args.output:
        destination = _output_path(manifest, args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(canonical_json(report))
        report["output"] = str(destination)
    if args.json:
        print(canonical_json(report), end="")
    else:
        print(f"Optimization preview: {len(report['assets'])} asset(s)")
        totals = report["totals"]
        print(f"Flip reuse savings: {totals['flipDedupeSavingsTiles']} tiles")


def command_asset_import(args: argparse.Namespace) -> None:
    manifest = _manifest(args.project)
    report = import_asset(
        manifest.root, args.source, args.destination, args.provenance_report,
        expected_sha256=args.expected_sha256,
    )
    report["project"] = manifest.id
    if args.json:
        print(canonical_json(report), end="")
    else:
        print(f"Imported asset: {report['destination']['path']}")
        print(f"SHA-256: {report['destination']['sha256']}")
        print(f"Provenance: {report['provenanceReport']}")


def command_lab(args: argparse.Namespace) -> int:
    manifest = _manifest(args.project)
    complete = run_laboratory(
        storage_bytes=args.storage_bytes,
        rtc_seed_unix=args.rtc_seed,
    )
    report = LaboratoryReport(
        complete.save_cases if args.case in {"all", "save"} else (),
        complete.rtc_cases if args.case in {"all", "rtc"} else (),
    ).to_dict()
    report["project"] = manifest.id
    report["case"] = args.case
    report["rtcSeedUnix"] = args.rtc_seed
    if args.json:
        print(canonical_json(report), end="")
    else:
        print(f"Save/RTC laboratory: {'PASS' if report['passed'] else 'FAIL'}")
        print(f"Save cases: {len(report['saveCases'])}; RTC cases: {len(report['rtcCases'])}")
    return 0 if report["passed"] else 2


def command_audio_preview(args: argparse.Namespace) -> None:
    manifest = _manifest(args.project)
    source = _project_owned_path(manifest, args.source, label="audio source")
    if not source.is_file():
        raise AudioWorkbenchError(f"audio source does not exist: {source}")
    destination = _project_owned_path(
        manifest,
        args.output or f"build/audio/{source.stem}.preview.wav",
        label="audio preview output",
    )
    if destination.suffix.lower() != ".wav":
        raise AudioWorkbenchError("audio preview output must use a .wav suffix")
    report = render_music_preview(
        source, output=destination, sample_rate=args.sample_rate,
        loops=args.loops, replace=args.replace,
    )
    report["project"] = manifest.id
    report["source"] = str(source)
    if args.json:
        print(canonical_json(report), end="")
    else:
        metrics = report["metrics"]
        print(f"Audio preview: {destination}")
        print(
            f"{metrics['rowCount']} rows, {metrics['maxPolyphony']} peak voices, "
            f"{metrics['durationMilliseconds']} ms"
        )
        print("Authoring preview only; verify the cartridge WAV in SwanSong.")


def command_audio_arbitrate(args: argparse.Namespace) -> None:
    manifest = _manifest(args.project)
    source = _project_owned_path(manifest, args.events, label="SFX event plan")
    document = _read_json_object(source, "SFX event plan")
    events = document.get("events")
    if not isinstance(events, list):
        raise AudioWorkbenchError("SFX event plan requires an events array")
    report = simulate_sfx_arbitration(events, channels=args.channels)
    report["project"] = manifest.id
    report["source"] = str(source)
    if args.json:
        print(canonical_json(report), end="")
    else:
        accepted = sum(1 for item in report["decisions"] if item["accepted"])
        stolen = sum(1 for item in report["decisions"] if item["stolen"] is not None)
        print(f"SFX arbitration: {accepted}/{len(events)} accepted, {stolen} channel steal(s)")


def command_migrate(args: argparse.Namespace) -> None:
    manifest_path = Path(args.project).resolve() if args.project else Path(find_manifest()).resolve()
    if manifest_path.is_dir():
        manifest_path /= "swan.toml"
    identity = sdk_identity()
    target_version = args.target_version or str(identity["version"])
    target_revision = args.target_revision or str(identity["revision"])
    report = plan_migration(
        manifest_path, target_version=target_version,
        target_revision=target_revision, target_schema=args.target_schema,
    )
    if args.apply:
        report = apply_migration(report)
    else:
        report = dict(report)
        report.pop("updatedText", None)
    if args.json:
        print(canonical_json(report), end="")
    else:
        action = "Applied" if report["applied"] else "Planned"
        print(f"{action} {len(report['changes'])} migration change(s)")
        for change in report["changes"]:
            print(f"- {change['field']}: {change['before']} -> {change['after']}")
        if not args.apply:
            print("No files changed; rerun with --apply after reviewing this plan.")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="swan", description="Build deterministic WonderSwan games with SwanSong SDK")
    result.add_argument("--version", action="version", version=f"swan {__version__}")
    commands = result.add_subparsers(dest="command", required=True)

    sdk_path_parser = commands.add_parser(
        "sdk-path", help="print the complete installed SDK payload path"
    )
    sdk_path_parser.set_defaults(handler=command_sdk_path)

    doctor = commands.add_parser(
        "doctor", help="validate the SDK, project, Wonderful, and SwanSong environment"
    )
    doctor.add_argument("--project", help="path to swan.toml or its project directory")
    doctor.add_argument("--timeout", type=float, default=5.0,
                        help="SwanSong interface probe timeout in seconds")
    doctor.add_argument("--json", action="store_true",
                        help="emit swansong-doctor-report-v1 JSON")
    doctor.set_defaults(handler=command_doctor)

    tile_capacity_parser = commands.add_parser(
        "hardware-tile-capacity",
        help="print the manifest-safe background tile capacity",
    )
    tile_capacity_parser.add_argument("--project", help="path to swan.toml")
    tile_capacity_parser.set_defaults(handler=command_hardware_tile_capacity)

    new = commands.add_parser("new", help="create a game from a production recipe")
    new.add_argument("name")
    new.add_argument("--template", choices=RECIPES, default="arcade-action")
    new.add_argument("--directory")
    new.set_defaults(handler=command_new)

    for name, help_text, handler in (
        ("assets", "validate and compile project assets", command_assets),
        ("test", "run generated assets and host tests", command_test),
        ("report", "report and enforce cartridge resource budgets", command_report),
    ):
        subcommand = commands.add_parser(name, help=help_text)
        subcommand.add_argument("--project", help="path to swan.toml")
        if name == "report":
            subcommand.add_argument("--json", action="store_true")
            subcommand.add_argument(
                "--baseline-report",
                help="previous swansong-resource-report-v1 JSON to compare",
            )
            subcommand.add_argument(
                "--allow-increase", action="append", default=[], metavar="METRIC=AMOUNT",
                help="allowed growth for one historical budget metric; may be repeated",
            )
        subcommand.set_defaults(handler=handler)

    build = commands.add_parser("build", help="generate assets and build the ROM with Wonderful")
    build.add_argument("--project", help="path to swan.toml")
    build.add_argument("--target", help="optional Make target")
    build.add_argument("--trace", action="store_true",
                       help="build an opt-in deterministic runtime trace ROM")
    build.add_argument("--trace-capacity", type=int, default=64,
                       help="retained runtime frames for --trace (1..255)")
    build.set_defaults(handler=command_build)

    play_parser = commands.add_parser("play", help="execute one fresh-boot scenario using SwanSong only")
    play_parser.add_argument("scenario", nargs="?")
    play_parser.add_argument("--all", action="store_true",
                             help="execute every declared scenario from a fresh boot")
    play_parser.add_argument("--project", help="path to swan.toml")
    play_parser.add_argument("--no-verify-replay", action="store_true", help="skip the second bit-exact replay")
    play_parser.set_defaults(handler=command_play)

    outcome = commands.add_parser(
        "outcome", help="validate a SwanSong runtime trace and inspected WAV"
    )
    outcome.add_argument("scenario")
    outcome.add_argument("--project", help="path to swan.toml")
    outcome.add_argument("--trace", required=True,
                         help="SwanSong-exported .swtr or trace JSON")
    outcome.add_argument("--wav", required=True,
                         help="WAV returned by the same SwanSong execution")
    outcome.add_argument("--inspected", action="store_true",
                         help="confirm the SwanSong WAV was actually inspected")
    outcome.add_argument("--output", help="optional outcome report JSON")
    outcome.add_argument("--json", action="store_true",
                         help="emit swan-scenario-outcome-report-v1 JSON")
    outcome.set_defaults(handler=command_outcome)

    dev = commands.add_parser(
        "dev", help="watch project inputs, rebuild, and replay a SwanSong scenario"
    )
    dev.add_argument("--project", help="path to swan.toml")
    dev.add_argument("--scenario", help="scenario to replay; defaults to interaction")
    dev.add_argument("--once", action="store_true",
                     help="build and replay once without entering the watch loop")
    dev.add_argument("--poll-cycles", type=int,
                     help="stop after this many filesystem polling cycles")
    dev.add_argument("--poll-interval", type=float, default=0.25,
                     help="filesystem polling interval in seconds")
    dev.add_argument("--debounce", type=float, default=0.2,
                     help="required stable interval before rebuilding")
    dev.add_argument("--timeout", type=float, default=300.0,
                     help="timeout for each build or play gate")
    dev.add_argument("--test-mode", action="store_true",
                     help="disable waits and default to zero poll cycles")
    dev.add_argument("--json", action="store_true",
                     help="stream swansong-dev-event-v1 JSONL")
    dev.set_defaults(handler=command_dev)

    recorder = commands.add_parser(
        "scenario-record", help="turn a SwanSong input frame log into an editable plan"
    )
    recorder.add_argument("--project", help="path to swan.toml")
    recorder.add_argument("--input-log", required=True,
                          help="swan-song-input-frame-log-v2 JSON export")
    recorder.add_argument("--output", required=True,
                          help="destination frame-plan JSON path")
    recorder.add_argument("--json", action="store_true",
                          help="emit swansong-scenario-record-report-v1 JSON")
    recorder.set_defaults(handler=command_scenario_record)

    scenario_compile = commands.add_parser(
        "scenario-compile",
        help="compile tap, hold, chord, repeat, and wait macros into an exact-frame plan",
    )
    scenario_compile.add_argument("--project", help="path to swan.toml")
    scenario_compile.add_argument("--script", required=True,
                                  help="project-owned swansong-scenario-script-v1 JSON")
    scenario_compile.add_argument("--output", required=True,
                                  help="new project-owned exact-frame plan JSON")
    scenario_compile.add_argument("--json", action="store_true",
                                  help="emit swansong-scenario-compile-report-v1 JSON")
    scenario_compile.set_defaults(handler=command_scenario_compile)

    author = commands.add_parser(
        "author", help="create, validate, report, and export visual authoring documents"
    )
    author_actions = author.add_subparsers(dest="author_operation", required=True)

    author_create = author_actions.add_parser(
        "create", help="create a new project-owned authoring document"
    )
    author_create.add_argument("kind", choices=AUTHORING_KINDS)
    author_create.add_argument("id", help="lowercase kebab-case document id")
    author_create.add_argument("--project", help="path to swan.toml")
    author_create.add_argument("--output", help="project-relative .json destination")
    author_create.add_argument("--json", action="store_true",
                               help="emit swansong-author-operation-report-v1 JSON")
    author_create.set_defaults(handler=command_author_create)

    for operation, help_text, handler in (
        ("validate", "validate one project-owned authoring document", command_author_validate),
        ("report", "report deterministic authoring metrics and findings", command_author_report),
        ("export", "export an SDK source or explicit handoff document", command_author_export),
    ):
        subcommand = author_actions.add_parser(operation, help=help_text)
        subcommand.add_argument("document", help="project-owned authoring JSON document")
        subcommand.add_argument("--project", help="path to swan.toml")
        if operation in {"report", "export"}:
            subcommand.add_argument(
                "--output", required=operation == "export",
                help=(
                    "new project-owned export destination" if operation == "export"
                    else "optional new project-owned .json report destination"
                ),
            )
        subcommand.add_argument("--json", action="store_true",
                                help="emit swansong-author-operation-report-v1 JSON")
        subcommand.set_defaults(handler=handler)

    minimize = commands.add_parser(
        "minimize", help="delta-reduce a failing exact-frame plan through SwanSong"
    )
    minimize.add_argument("--project", help="path to swan.toml")
    minimize.add_argument("--plan", required=True,
                          help="failing swan-song-frame-input-plan-v1 JSON")
    minimize.add_argument("--predicate", required=True,
                          help="swansong-failure-predicate-v1 JSON")
    minimize.add_argument("--output", required=True,
                          help="destination minimized plan JSON")
    minimize.add_argument("--report", help="optional minimization report destination")
    minimize.add_argument("--evidence-output",
                          help="final structured-evidence verification directory")
    minimize.add_argument("--max-evaluations", type=int, default=256,
                          help="maximum distinct candidate plans executed")
    minimize.add_argument("--timeout", type=float, default=300.0,
                          help="timeout for each SwanSong execution")
    minimize.add_argument("--json", action="store_true",
                          help="emit swansong-minimize-report-v1 JSON")
    minimize.set_defaults(handler=command_minimize)

    replay = commands.add_parser(
        "replay", help="build a read-only frame timeline from replay artifacts"
    )
    replay.add_argument("--project", help="path to swan.toml")
    replay.add_argument("--plan", help="exact-frame plan; optional with --scenario")
    replay.add_argument("--scenario", help="declared scenario metadata and default plan")
    replay.add_argument("--checkpoints",
                        help="swansong-replay-checkpoints-v1 JSON")
    replay.add_argument("--evidence", action="append", default=[], metavar="ID=DIRECTORY",
                        help="bind decoded SwanSong evidence; may be repeated")
    replay.add_argument("--trace", help="optional frame trace JSON")
    replay.add_argument("--output", help="optional replay report destination")
    replay.add_argument("--json", action="store_true",
                        help="emit swansong-replay-report-v1 JSON")
    replay.set_defaults(handler=command_replay)

    evidence = commands.add_parser(
        "evidence-diff", help="compare decoded SwanSong PNG, WAV, and JSON evidence"
    )
    evidence.add_argument("--before", required=True, help="baseline evidence directory")
    evidence.add_argument("--after", required=True, help="candidate evidence directory")
    evidence.add_argument("--project", help="path to swan.toml for scenario audio limits")
    evidence.add_argument("--scenario", help="play scenario declaring audio evidence limits")
    evidence.add_argument("--pixel-tolerance", type=int, default=0)
    evidence.add_argument("--pixel-ratio", type=float, default=0.0)
    evidence.add_argument("--sample-tolerance", type=int, default=0)
    evidence.add_argument("--sample-ratio", type=float, default=0.0)
    evidence.add_argument("--rms-delta", type=float, default=0.0)
    evidence.add_argument("--audio-floor", type=float,
                          help="normalized amplitude treated as silence for audio metrics")
    evidence.add_argument("--stereo-balance-delta", type=float,
                          help="maximum signed left/right energy-balance change")
    evidence.add_argument("--cue-onset-delta-ms", type=float,
                          help="maximum audible cue onset shift in milliseconds")
    evidence.add_argument("--silent-frame-ratio-increase", type=float,
                          help="maximum increase in all-channel silent-frame ratio")
    evidence.add_argument("--internal-silence-increase-ms", type=float,
                          help="maximum increase in the longest internal dropout")
    evidence.add_argument("--clipped-sample-ratio-increase", type=float,
                          help="maximum increase in exact full-scale PCM samples")
    evidence.add_argument("--loop-seam-delta-increase", type=float,
                          help="maximum increase in normalized end-to-start discontinuity")
    evidence.add_argument("--fail-on-difference", action="store_true",
                          help="exit nonzero when a meaningful difference is found")
    evidence.add_argument("--json", action="store_true",
                          help="emit swansong-evidence-diff-v1 JSON")
    evidence.set_defaults(handler=command_evidence_diff)

    fuzz = commands.add_parser(
        "fuzz", help="search deterministic input plans through SwanSong"
    )
    fuzz.add_argument("--project", help="path to swan.toml")
    fuzz.add_argument("--seed", type=int, default=1)
    fuzz.add_argument("--cases", type=int, default=8)
    fuzz.add_argument("--frames", type=int, default=600)
    fuzz.add_argument(
        "--neutral-boot-frames", type=int,
        help="neutral frames before fuzz input; defaults to play.ready_frames",
    )
    fuzz.add_argument("--maximum-actions", type=int, default=64)
    fuzz.add_argument("--generate-only", action="store_true",
                      help="emit plans without executing a ROM")
    fuzz.add_argument("--json", action="store_true",
                      help="emit swansong-fuzz-report-v1 JSON")
    fuzz.set_defaults(handler=command_fuzz)

    profile = commands.add_parser(
        "profile", help="profile tiles, sprites, palettes, dirty regions, and frame budgets"
    )
    profile.add_argument("--project", help="path to swan.toml")
    profile.add_argument("--trace", help="optional exported frame-profile trace JSON")
    profile.add_argument("--json", action="store_true",
                         help="emit swansong-profile-report-v1 JSON")
    profile.set_defaults(handler=command_profile)

    optimize = commands.add_parser(
        "optimize", help="preview tile dedupe, palette reduction, flip reuse, and mono art"
    )
    optimize.add_argument("--project", help="path to swan.toml")
    optimize.add_argument("--asset", help="limit the preview to one graphic asset id")
    mode = optimize.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true",
                      help="apply a hash-bound, artist-approved optimization")
    mode.add_argument("--revert", action="store_true",
                      help="remove an unchanged generated optimization output")
    optimize.add_argument("--output",
                          help="preview report path, or generated PNG with --apply")
    optimize.add_argument("--report",
                          help="apply report path, or existing report with --revert")
    optimize.add_argument("--operation", action="append", default=[],
                          choices=("palette-reduction", "mono-conversion"),
                          help="approved operation; repeat to preserve order")
    optimize.add_argument("--expected-source-sha256",
                          help="reviewed source digest required by --apply")
    optimize.add_argument("--expected-report-sha256",
                          help="reviewed apply-report digest required by --revert")
    optimize.add_argument("--approval", choices=(ARTIST_APPROVAL,),
                          help="explicit artist approval token")
    optimize.add_argument("--json", action="store_true",
                          help="emit swansong-asset-optimization-report-v1 JSON")
    optimize.set_defaults(handler=command_optimize)

    asset_import = commands.add_parser(
        "asset-import",
        help="copy a reviewed external asset into a project with provenance",
    )
    asset_import.add_argument("--project", help="path to swan.toml")
    asset_import.add_argument("--source", required=True,
                              help="external source file")
    asset_import.add_argument("--destination", required=True,
                              help="new project-owned destination")
    asset_import.add_argument("--provenance-report", required=True,
                              help="new project-owned provenance JSON")
    asset_import.add_argument("--expected-sha256", required=True,
                              help="reviewed SHA-256 of the source bytes")
    asset_import.add_argument("--json", action="store_true",
                              help="emit swansong-asset-import-report-v1 JSON")
    asset_import.set_defaults(handler=command_asset_import)

    laboratory = commands.add_parser(
        "lab", help="simulate save corruption, interrupted writes, RTC loss, and time travel"
    )
    laboratory.add_argument("--project", help="path to swan.toml")
    laboratory.add_argument("--case", choices=("all", "save", "rtc"), default="all")
    laboratory.add_argument("--rtc-seed", type=int,
                            help="UTC Unix time injected at the deterministic boot boundary")
    laboratory.add_argument("--storage-bytes", type=int, default=256)
    laboratory.add_argument("--json", action="store_true",
                            help="emit swansong-laboratory-report-v1 JSON")
    laboratory.set_defaults(handler=command_lab)

    audio = commands.add_parser(
        "audio", help="preview music and inspect deterministic SFX arbitration"
    )
    audio_actions = audio.add_subparsers(dest="audio_operation", required=True)
    audio_preview = audio_actions.add_parser(
        "preview", help="render a deterministic host-side authoring WAV"
    )
    audio_preview.add_argument("--project", help="path to swan.toml")
    audio_preview.add_argument("--source", required=True,
                               help="project-owned SwanSong music TOML")
    audio_preview.add_argument("--output", help="project-owned .wav destination")
    audio_preview.add_argument("--sample-rate", type=int, default=22050)
    audio_preview.add_argument("--loops", type=int, default=1)
    audio_preview.add_argument("--replace", action="store_true",
                               help="replace an earlier authoring preview")
    audio_preview.add_argument("--json", action="store_true",
                               help="emit swansong-audio-workbench-report-v1 JSON")
    audio_preview.set_defaults(handler=command_audio_preview)

    audio_arbitrate = audio_actions.add_parser(
        "arbitrate", help="explain fixed-priority SFX channel choices"
    )
    audio_arbitrate.add_argument("--project", help="path to swan.toml")
    audio_arbitrate.add_argument("--events", required=True,
                                 help="project-owned JSON document with an events array")
    audio_arbitrate.add_argument("--channels", type=int, default=4)
    audio_arbitrate.add_argument("--json", action="store_true",
                                 help="emit swansong-sfx-arbitration-report-v1 JSON")
    audio_arbitrate.set_defaults(handler=command_audio_arbitrate)

    migrate = commands.add_parser(
        "migrate", help="preview or apply a reversible manifest/SDK pin upgrade"
    )
    migrate.add_argument("--project", help="path to swan.toml or project directory")
    migrate.add_argument("--target-version",
                         help="target SDK semantic version; defaults to this SDK")
    migrate.add_argument("--target-revision",
                         help="target content revision; defaults to this SDK")
    migrate.add_argument("--target-schema", type=int, default=1)
    migrate.add_argument("--apply", action="store_true",
                         help="atomically write the reviewed plan and a hash-named backup")
    migrate.add_argument("--json", action="store_true",
                         help="emit swansong-migration-report-v1 JSON")
    migrate.set_defaults(handler=command_migrate)

    release = commands.add_parser(
        "release", help="run release gates and create a deterministic archive"
    )
    release.add_argument("--project", help="path to swan.toml")
    release.add_argument("--output",
                         help="output .zip path or directory; defaults to project dist")
    release.add_argument("--notes", help="optional Markdown release notes")
    release.add_argument(
        "--baseline-report",
        help="previous swansong-resource-report-v1 JSON included as a release growth gate",
    )
    release.add_argument(
        "--allow-increase", action="append", default=[], metavar="METRIC=AMOUNT",
        help="allowed growth for one historical budget metric; may be repeated",
    )
    release.add_argument("--timeout", type=float, default=300.0,
                         help="timeout for each release gate")
    release.add_argument("--json", action="store_true",
                         help="emit swansong-release-report-v1 JSON")
    release.set_defaults(handler=command_release)
    return result


_STRUCTURED_ERROR_SCHEMAS = {
    "doctor": "swansong-doctor-report-v1",
    "scenario-record": "swansong-scenario-record-report-v1",
    "scenario-compile": "swansong-scenario-compile-report-v1",
    "outcome": "swan-scenario-outcome-report-v1",
    "author": AUTHORING_REPORT_SCHEMA,
    "minimize": "swansong-minimize-report-v1",
    "replay": "swansong-replay-report-v1",
    "evidence-diff": "swansong-evidence-diff-v1",
    "fuzz": "swansong-fuzz-report-v1",
    "profile": "swansong-profile-report-v1",
    "optimize": "swansong-asset-optimization-report-v1",
    "asset-import": "swansong-asset-import-report-v1",
    "lab": "swansong-laboratory-report-v1",
    "audio": "swansong-audio-workbench-report-v1",
    "migrate": "swansong-migration-report-v1",
    "release": "swansong-release-report-v1",
}


def _release_error_report(message: str, *, project: str | None = None,
                          version: str | None = None,
                          code: str = "command-failed") -> dict[str, object]:
    return {
        "artifacts": [],
        "error": {"code": code, "message": message},
        "gates": [],
        "ok": False,
        "package": None,
        "packageSha256": None,
        "project": project,
        "schema": RELEASE_SCHEMA,
        "sdkRevision": None,
        "sdkVersion": None,
        "toolchainLockSha256": None,
        "version": version,
    }


def _emit_structured_error(args: argparse.Namespace, exc: Exception) -> bool:
    if not getattr(args, "json", False):
        return False
    if args.command == "dev":
        print(canonical_json({
            "schema": "swansong-dev-event-v1",
            "sequence": getattr(args, "_dev_next_sequence", 0),
            "type": "error",
            "status": "failed",
            "project": getattr(args, "project", None),
            "scenario": getattr(args, "scenario", None),
            "error": {"code": "command-failed", "message": str(exc)},
        }, compact=True), end="")
        return True
    schema = _STRUCTURED_ERROR_SCHEMAS.get(args.command)
    if schema is None:
        return False
    if args.command == "release":
        print(canonical_json(_release_error_report(str(exc))), end="")
        return True
    payload: dict[str, object] = {
        "schema": schema,
        "ok": False,
        "error": {"code": "command-failed", "message": str(exc)},
    }
    if args.command == "author":
        payload.update(
            operation=getattr(args, "author_operation", None),
            gameplayEvidence=False,
            notice="Authoring documents, previews, and exports are not gameplay evidence.",
        )
    elif args.command == "fuzz":
        payload.update(verdict="fail", findings=[{
            "severity": "error", "code": "command-failed", "message": str(exc),
        }], cases=[])
    elif args.command == "lab":
        payload["passed"] = False
    print(canonical_json(payload), end="")
    return True


def main(argv: list[str] | None = None) -> int:
    args: argparse.Namespace | None = None
    try:
        args = parser().parse_args(argv)
        status = args.handler(args)
        return status if isinstance(status, int) else 0
    except (AssetImportError, AudioWorkbenchError, AuthoringError, BudgetHistoryError, CommandError,
            EvidenceError, FuzzError, GenerationError,
            LaboratoryError, LayoutError, ManifestError, OptimizationError,
            MigrationError, MinimizeError, OperationsError, OSError, PlanError, PNGError,
            ProfileError, ReplayError, ScaffoldError, ScenarioError, TraceError,
            ScenarioScriptError, SwanSongError) as exc:
        if args is not None and _emit_structured_error(args, exc):
            return 2
        print(f"swan: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
