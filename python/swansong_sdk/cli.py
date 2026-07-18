"""Command-line entry point for SwanSong SDK projects."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from .generator import GenerationError, asset_report, generate, validate_budgets
from .evidence import EvidenceError, EvidenceThresholds, diff_evidence
from .fuzzing import FuzzError, generate_fuzz_plan
from .laboratory import LaboratoryError, LaboratoryReport, run_laboratory
from .layout import LayoutError, sdk_root
from .manifest import ManifestError, find_manifest, load_manifest
from .optimize import OptimizationError, preview_asset_optimization
from .operations import (
    RELEASE_SCHEMA, OperationsError, canonical_json, development_session, doctor_report,
    release_project,
)
from .minimize import (
    FailureObservation, MinimizeError, minimize_plan,
    observe_evidence, observe_execution_error, validate_failure_predicate,
)
from .plans import PlanError, load_plan, load_plan_file
from .png2bpp import PNGError
from .profiler import ProfileError, profile_resources
from .replay import ReplayError, build_replay_report, evidence_binding, validate_checkpoints
from .scaffold import RECIPES, ScaffoldError, create_project
from .scenario import ScenarioError, record_frame_log
from .swansong import SwanSongError, play


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


def _run_make(manifest, targets: list[str]) -> None:
    environment = os.environ.copy()
    environment.setdefault("SWANSONG_SDK_DIR", str(sdk_root()))
    environment.setdefault(
        "SWAN_GFX_HARDWARE_TILE_CAPACITY",
        "512" if manifest.hardware == "mono-compatible" else "1024",
    )
    try:
        subprocess.run(["make", *targets], cwd=manifest.root, env=environment, check=True)
    except FileNotFoundError as exc:
        raise CommandError("make is not installed") from exc
    except subprocess.CalledProcessError as exc:
        raise CommandError(f"make {' '.join(targets) or 'all'} failed with exit code {exc.returncode}") from exc


def command_build(args: argparse.Namespace) -> None:
    manifest = _manifest(args.project)
    generate(manifest)
    _run_make(manifest, [args.target] if args.target else [])
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


def command_play(args: argparse.Namespace) -> None:
    manifest = _manifest(args.project)
    generate(manifest)
    scenario = next((item for item in manifest.play_scenarios if item.id == args.scenario), None)
    if scenario is None:
        choices = ", ".join(item.id for item in manifest.play_scenarios) or "none declared"
        raise CommandError(f"unknown scenario {args.scenario!r}; available: {choices}")
    _, plan = load_plan(manifest.root, scenario.plan)
    rom = _rom_path(manifest)
    if not rom.is_file():
        raise CommandError(f"ROM is not built: {rom}; run swan build first")
    output = manifest.root / "build" / "swansong" / scenario.id
    evidence = play(rom, plan, output=output, verify_replay=not args.no_verify_replay)
    print(f"SwanSong evidence: {output}")
    if evidence.get("finalGameRasterSHA256"):
        print(f"Raster SHA-256: {evidence['finalGameRasterSHA256']}")


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

    def notify(name: str, status: str) -> None:
        if not args.json:
            print(f"[{status.upper():7}] {name}")

    try:
        report = release_project(
            manifest, output=args.output, notes=args.notes,
            timeout=args.timeout, notify=notify,
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
        scenario_metadata = {
            "id": scenario.id,
            "title": scenario.title,
            "goal": scenario.goal,
            "requiredChecks": list(scenario.required_checks),
            "requiresAudioEvidence": scenario.audio,
        }
    if plan_argument is None:
        raise CommandError("swan replay requires --plan or --scenario")
    plan_path, plan = load_plan_file(Path(plan_argument))
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
    thresholds = EvidenceThresholds(
        pixel_channel_tolerance=args.pixel_tolerance,
        changed_pixel_ratio=args.pixel_ratio,
        pcm_sample_tolerance=args.sample_tolerance,
        changed_sample_ratio=args.sample_ratio,
        normalized_rms_delta=args.rms_delta,
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
    generated = [
        generate_fuzz_plan(
            seed=(args.seed + index) & 0xFFFFFFFF,
            total_frames=args.frames,
            neutral_boot_frames=min(args.neutral_boot_frames, args.frames),
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


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="swan", description="Build deterministic WonderSwan games with SwanSong SDK")
    result.add_argument("--version", action="version", version="swan 0.2.0")
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
        subcommand.set_defaults(handler=handler)

    build = commands.add_parser("build", help="generate assets and build the ROM with Wonderful")
    build.add_argument("--project", help="path to swan.toml")
    build.add_argument("--target", help="optional Make target")
    build.set_defaults(handler=command_build)

    play_parser = commands.add_parser("play", help="execute one fresh-boot scenario using SwanSong only")
    play_parser.add_argument("scenario")
    play_parser.add_argument("--project", help="path to swan.toml")
    play_parser.add_argument("--no-verify-replay", action="store_true", help="skip the second bit-exact replay")
    play_parser.set_defaults(handler=command_play)

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
    evidence.add_argument("--pixel-tolerance", type=int, default=0)
    evidence.add_argument("--pixel-ratio", type=float, default=0.0)
    evidence.add_argument("--sample-tolerance", type=int, default=0)
    evidence.add_argument("--sample-ratio", type=float, default=0.0)
    evidence.add_argument("--rms-delta", type=float, default=0.0)
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
    fuzz.add_argument("--neutral-boot-frames", type=int, default=60)
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
    optimize.add_argument("--output", help="optional JSON report destination")
    optimize.add_argument("--json", action="store_true",
                          help="emit swansong-asset-optimization-report-v1 JSON")
    optimize.set_defaults(handler=command_optimize)

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

    release = commands.add_parser(
        "release", help="run release gates and create a deterministic archive"
    )
    release.add_argument("--project", help="path to swan.toml")
    release.add_argument("--output",
                         help="output .zip path or directory; defaults to project dist")
    release.add_argument("--notes", help="optional Markdown release notes")
    release.add_argument("--timeout", type=float, default=300.0,
                         help="timeout for each release gate")
    release.add_argument("--json", action="store_true",
                         help="emit swansong-release-report-v1 JSON")
    release.set_defaults(handler=command_release)
    return result


_STRUCTURED_ERROR_SCHEMAS = {
    "doctor": "swansong-doctor-report-v1",
    "scenario-record": "swansong-scenario-record-report-v1",
    "minimize": "swansong-minimize-report-v1",
    "replay": "swansong-replay-report-v1",
    "evidence-diff": "swansong-evidence-diff-v1",
    "fuzz": "swansong-fuzz-report-v1",
    "profile": "swansong-profile-report-v1",
    "optimize": "swansong-asset-optimization-report-v1",
    "lab": "swansong-laboratory-report-v1",
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
    if args.command == "fuzz":
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
    except (CommandError, EvidenceError, FuzzError, GenerationError,
            LaboratoryError, LayoutError, ManifestError, OptimizationError,
            MinimizeError, OperationsError, OSError, PlanError, PNGError,
            ProfileError, ReplayError, ScaffoldError, ScenarioError,
            SwanSongError) as exc:
        if args is not None and _emit_structured_error(args, exc):
            return 2
        print(f"swan: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
