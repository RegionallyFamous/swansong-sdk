"""Minimal JSON-RPC client for SwanSong's deterministic MCP playtest tool."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
from typing import Any


class SwanSongError(RuntimeError):
    pass


def server_command() -> list[str]:
    configured = os.environ.get("SWANSONG_MCP_COMMAND")
    if configured:
        command = shlex.split(configured)
        if not command:
            raise SwanSongError("SWANSONG_MCP_COMMAND is empty")
        return command
    desktop = os.environ.get("SWANSONG_DESKTOP_DIR")
    if desktop:
        runner = Path(desktop) / "Scripts" / "run-swansong-playtest-mcp.sh"
        if runner.is_file():
            return [str(runner)]
        raise SwanSongError(f"SwanSong MCP runner not found under SWANSONG_DESKTOP_DIR: {runner}")
    runner = shutil.which("swansong-playtest-mcp")
    if runner:
        return [runner]
    raise SwanSongError(
        "SwanSong MCP was not found. Set SWANSONG_MCP_COMMAND or SWANSONG_DESKTOP_DIR."
    )


def _exchange(process: subprocess.Popen[str], request: dict[str, Any]) -> dict[str, Any]:
    if process.stdin is None or process.stdout is None:
        raise SwanSongError("SwanSong MCP did not open standard I/O")
    process.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
    process.stdin.flush()
    while True:
        line = process.stdout.readline()
        if not line:
            error = process.stderr.read() if process.stderr else ""
            raise SwanSongError(f"SwanSong MCP closed before responding: {error.strip()}")
        try:
            response = json.loads(line)
        except json.JSONDecodeError:
            continue
        if response.get("id") == request.get("id"):
            if "error" in response:
                raise SwanSongError(f"SwanSong MCP error: {response['error']}")
            return response


def _call(process: subprocess.Popen[str], request_id: int, rom: Path, plan: dict[str, Any]) -> dict[str, Any]:
    response = _exchange(process, {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": "tools/call",
        "params": {
            "name": "swansong_playtest_plan",
            "arguments": {
                "romPath": str(rom.resolve()),
                "plan": plan,
                "confirmShareCapture": True,
            },
        },
    })
    result = response.get("result", {})
    if result.get("isError"):
        content = result.get("content", [])
        detail = content[0].get("text", "unknown error") if content else "unknown error"
        raise SwanSongError(f"SwanSong rejected the playtest: {detail}")
    return result


def _media(result: dict[str, Any]) -> tuple[dict[str, Any], bytes, bytes]:
    content = result.get("content", [])
    by_type = {part.get("type"): part for part in content}
    if "image" not in by_type or "audio" not in by_type:
        raise SwanSongError("SwanSong response did not contain both screenshot and audio evidence")
    try:
        png = base64.b64decode(by_type["image"]["data"], validate=True)
        wav = base64.b64decode(by_type["audio"]["data"], validate=True)
    except (KeyError, ValueError) as exc:
        raise SwanSongError("SwanSong returned invalid media evidence") from exc
    if not png.startswith(b"\x89PNG\r\n\x1a\n") or not (wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"):
        raise SwanSongError("SwanSong returned malformed PNG or WAV evidence")
    structured = result.get("structuredContent")
    if not isinstance(structured, dict):
        raise SwanSongError("SwanSong response did not contain structured evidence")
    return structured, png, wav


def play(rom: Path, plan: dict[str, Any], *, output: Path, verify_replay: bool = True) -> dict[str, Any]:
    command = server_command()
    process = subprocess.Popen(
        command,
        text=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        initialized = _exchange(process, {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "swan-cli", "version": "1"},
            },
        })
        server_name = initialized.get("result", {}).get("serverInfo", {}).get("name", "")
        if "swansong" not in server_name.lower():
            raise SwanSongError(f"refusing non-SwanSong MCP server {server_name!r}")
        structured, png, wav = _media(_call(process, 2, rom, plan))
        if verify_replay:
            replay, replay_png, replay_wav = _media(_call(process, 3, rom, plan))
            if replay != structured or replay_png != png or replay_wav != wav:
                raise SwanSongError("deterministic replay produced different evidence")
        output.mkdir(parents=True, exist_ok=True)
        (output / "frame.png").write_bytes(png)
        (output / "audio.wav").write_bytes(wav)
        (output / "evidence.json").write_text(json.dumps(structured, indent=2, sort_keys=True) + "\n")
        return structured
    finally:
        if process.stdin:
            process.stdin.close()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)
        if process.stdout:
            process.stdout.close()
        if process.stderr:
            process.stderr.close()
