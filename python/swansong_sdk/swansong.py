"""Minimal JSON-RPC client for SwanSong's deterministic MCP playtest tool."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import select
import shlex
import shutil
import signal
import subprocess
import tempfile
import time
from typing import Any

from .evidence import EvidenceError, validate_wav
from .png2bpp import PNGError, read_png


class SwanSongError(RuntimeError):
    def __init__(self, message: str, *, returncode: int | None = None) -> None:
        super().__init__(message)
        self.returncode = returncode


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


def _available_stderr(process: subprocess.Popen[bytes], limit: int = 8192) -> str:
    if process.stderr is None:
        return ""
    chunks = bytearray()
    descriptor = process.stderr.fileno()
    while len(chunks) < limit:
        readable, _, _ = select.select([descriptor], [], [], 0)
        if not readable:
            break
        chunk = os.read(descriptor, min(4096, limit - len(chunks)))
        if not chunk:
            break
        chunks.extend(chunk)
    return chunks.decode("utf-8", errors="replace")


def _exchange(process: subprocess.Popen[bytes], request: dict[str, Any],
              deadline: float, buffer: bytearray, *,
              raise_rpc_error: bool = True) -> dict[str, Any]:
    if process.stdin is None or process.stdout is None:
        raise SwanSongError("SwanSong MCP did not open standard I/O")
    process.stdin.write(
        (json.dumps(request, separators=(",", ":")) + "\n").encode("utf-8")
    )
    process.stdin.flush()
    while True:
        while b"\n" in buffer:
            line, _, remainder = buffer.partition(b"\n")
            buffer[:] = remainder
            if len(line) > 4 * 1024 * 1024:
                raise SwanSongError("SwanSong MCP response exceeded the 4 MiB line limit")
            try:
                response = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not isinstance(response, dict):
                continue
            if response.get("id") == request.get("id"):
                if "error" in response and raise_rpc_error:
                    raise SwanSongError(f"SwanSong MCP error: {response['error']}")
                return response
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SwanSongError("SwanSong MCP timed out while waiting for evidence")
        descriptor = process.stdout.fileno()
        readable, _, _ = select.select([descriptor], [], [], remaining)
        if not readable:
            raise SwanSongError("SwanSong MCP timed out while waiting for evidence")
        chunk = os.read(descriptor, 65536)
        if not chunk:
            error = _available_stderr(process)
            returncode = process.poll()
            raise SwanSongError(
                f"SwanSong MCP closed before responding: {error.strip()}",
                returncode=returncode,
            )
        buffer.extend(chunk)
        if len(buffer) > 4 * 1024 * 1024:
            raise SwanSongError("SwanSong MCP response exceeded the 4 MiB line limit")


def _close_process(process: subprocess.Popen[bytes], *, grace: float) -> None:
    if process.stdin:
        try:
            process.stdin.close()
        except BrokenPipeError:
            pass
    if process.poll() is None and grace > 0:
        try:
            process.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            pass
    if process.poll() is None:
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
    if process.stdout:
        process.stdout.close()
    if process.stderr:
        process.stderr.close()


def probe_server(command: list[str], *, cwd: Path, timeout: float,
                 client_name: str, client_version: str) -> dict[str, Any]:
    """Perform one bounded initialize exchange with a line-oriented MCP server."""
    if timeout <= 0:
        raise SwanSongError("SwanSong timeout must be greater than zero")
    if not command or not command[0]:
        raise SwanSongError("refusing to run an empty SwanSong MCP command")
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        raise SwanSongError(
            f"SwanSong MCP command is not installed: {command[0]}"
        ) from exc
    except OSError as exc:
        raise SwanSongError(f"could not run SwanSong MCP command {command[0]}: {exc}") from exc
    try:
        return _exchange(process, {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": client_name, "version": client_version},
            },
        }, time.monotonic() + timeout, bytearray(), raise_rpc_error=False)
    finally:
        # MCP servers are expected to remain alive. Once the matching response
        # arrives, terminate this private probe process instead of waiting for EOF.
        _close_process(process, grace=0)


def _call(process: subprocess.Popen[bytes], request_id: int, rom: Path,
          plan: dict[str, Any], deadline: float,
          buffer: bytearray) -> dict[str, Any]:
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
    }, deadline, buffer)
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


def play(rom: Path, plan: dict[str, Any], *, output: Path,
         verify_replay: bool = True, timeout: float = 300.0) -> dict[str, Any]:
    if timeout <= 0:
        raise SwanSongError("SwanSong timeout must be greater than zero")
    command = server_command()
    deadline = time.monotonic() + timeout
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    buffer = bytearray()
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
        }, deadline, buffer)
        server_name = initialized.get("result", {}).get("serverInfo", {}).get("name", "")
        if "swansong" not in server_name.lower():
            raise SwanSongError(f"refusing non-SwanSong MCP server {server_name!r}")
        structured, png, wav = _media(_call(process, 2, rom, plan, deadline, buffer))
        if verify_replay:
            replay, replay_png, replay_wav = _media(
                _call(process, 3, rom, plan, deadline, buffer)
            )
            if replay != structured or replay_png != png or replay_wav != wav:
                raise SwanSongError("deterministic replay produced different evidence")
        try:
            with tempfile.TemporaryDirectory(prefix="swan-media-") as temporary:
                media = Path(temporary)
                png_path = media / "frame.png"
                wav_path = media / "audio.wav"
                png_path.write_bytes(png)
                wav_path.write_bytes(wav)
                read_png(png_path)
                validate_wav(wav_path)
        except (OSError, PNGError, EvidenceError) as exc:
            raise SwanSongError(f"SwanSong returned undecodable media evidence: {exc}") from exc
        output.mkdir(parents=True, exist_ok=True)
        (output / "frame.png").write_bytes(png)
        (output / "audio.wav").write_bytes(wav)
        (output / "evidence.json").write_text(json.dumps(structured, indent=2, sort_keys=True) + "\n")
        return structured
    finally:
        _close_process(process, grace=2)
