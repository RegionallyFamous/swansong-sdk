#!/usr/bin/env python3
"""Exercise one tracked canary solely through an installed ``swan`` command."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def run(argv: list[str], *, cwd: Path, environment: dict[str, str]) -> str:
    result = subprocess.run(
        argv, cwd=cwd, env=environment, capture_output=True, text=True,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout)[-8000:]
        raise RuntimeError(
            f"{argv[0]} {argv[1] if len(argv) > 1 else ''} failed "
            f"with exit code {result.returncode}: {detail}"
        )
    return result.stdout


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--source", required=True, type=Path)
    result.add_argument("--work-root", required=True, type=Path)
    result.add_argument("--template", required=True,
                        choices=("arcade-action", "menu-puzzle", "grid-tactics",
                                 "utility-app"))
    result.add_argument("--swan", default="swan")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    source = args.source.resolve()
    work_root = args.work_root.resolve()
    if not (source / "swan.toml").is_file():
        raise RuntimeError(f"canary source has no swan.toml: {source}")
    project_id = source.name
    target = work_root / project_id
    if target.exists():
        raise RuntimeError(f"canary gate target already exists: {target}")
    work_root.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONSAFEPATH"] = "1"
    sdk_path = run([args.swan, "sdk-path"], cwd=work_root,
                   environment=environment).strip()
    if not sdk_path:
        raise RuntimeError("installed swan returned an empty SDK path")
    environment["SWANSONG_SDK_DIR"] = sdk_path
    run([
        args.swan, "new", project_id, "--template", args.template,
        "--directory", str(target),
    ], cwd=work_root, environment=environment)
    shutil.copytree(
        source,
        target,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(
            "build", "dist", "*.wsc", "*.ws", "wfconfig.toml",
            "compile_commands.json", "__pycache__", "*.pyc",
        ),
    )
    commands = []
    for command in ("assets", "test", "build"):
        run([args.swan, command, "--project", str(target / "swan.toml")],
            cwd=target, environment=environment)
        commands.append(command)
    report_text = run([
        args.swan, "report", "--project", str(target / "swan.toml"), "--json",
    ], cwd=target, environment=environment)
    commands.append("report")
    report = json.loads(report_text)
    if report.get("schema") != "swansong-resource-report-v1":
        raise RuntimeError("canary report used an unsupported schema")
    if report.get("budgetFailures"):
        raise RuntimeError(f"canary exceeded budgets: {report['budgetFailures']}")
    rom = target / (project_id.replace("-", "_") + ".wsc")
    if not rom.is_file() or not 0 < rom.stat().st_size <= 8 * 1024 * 1024:
        raise RuntimeError("canary did not produce a bounded WSC ROM")
    mono = target / (project_id.replace("-", "_") + ".ws")
    mono_compatible = 'hardware = "mono-compatible"' in (target / "swan.toml").read_text()
    if mono_compatible and (
        not mono.is_file() or not 0 < mono.stat().st_size <= 8 * 1024 * 1024
    ):
        raise RuntimeError("mono-compatible canary did not produce a bounded WS ROM")
    result = {
        "commands": ["new", *commands],
        "project": project_id,
        "report": report,
        "romBytes": rom.stat().st_size,
        "romSHA256": hashlib.sha256(rom.read_bytes()).hexdigest(),
        "monoROMBytes": mono.stat().st_size if mono_compatible else None,
        "monoROMSHA256": (
            hashlib.sha256(mono.read_bytes()).hexdigest()
            if mono_compatible else None
        ),
        "schema": "swansong-canary-gate-v1",
        "sdkPath": sdk_path,
        "template": args.template,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.SubprocessError,
            json.JSONDecodeError) as exc:
        print(f"canary gate: {exc}", file=sys.stderr)
        raise SystemExit(2)
