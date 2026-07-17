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

from .generator import GenerationError, asset_report, generate, validate_budgets
from .layout import LayoutError, sdk_root
from .manifest import ManifestError, find_manifest, load_manifest
from .plans import PlanError, load_plan
from .scaffold import RECIPES, ScaffoldError, create_project
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


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="swan", description="Build deterministic WonderSwan games with SwanSong SDK")
    result.add_argument("--version", action="version", version="swan 0.1.0")
    commands = result.add_subparsers(dest="command", required=True)

    sdk_path_parser = commands.add_parser(
        "sdk-path", help="print the complete installed SDK payload path"
    )
    sdk_path_parser.set_defaults(handler=command_sdk_path)

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
    return result


def main(argv: list[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        args.handler(args)
        return 0
    except (CommandError, GenerationError, LayoutError, ManifestError, PlanError,
            ScaffoldError, SwanSongError) as exc:
        print(f"swan: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
