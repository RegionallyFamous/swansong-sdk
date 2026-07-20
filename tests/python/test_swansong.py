from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from swansong_sdk.swansong import SwanSongError, play


SERVER = r'''
import base64
import io
import json
import os
import sys
import wave

png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")
wav_buffer = io.BytesIO()
with wave.open(wav_buffer, "wb") as output:
    output.setnchannels(2)
    output.setsampwidth(2)
    output.setframerate(48000)
    output.writeframes(b"\0" * 16)
wav = wav_buffer.getvalue()
for line in sys.stdin:
    request = json.loads(line)
    if request["method"] == "initialize":
        result = {"serverInfo": {"name": os.environ.get("TEST_SERVER_NAME", "swansong-playtester")}}
    else:
        arguments = request["params"]["arguments"]
        if not (
            arguments.get("confirmShareCapture")
            and arguments.get("captureSDKTrace")
            and arguments.get("confirmShareSDKTrace")
        ):
            result = {"isError": True, "content": [{"type": "text", "text": "confirmation required"}]}
        else:
            result = {
                "structuredContent": {"plan": arguments["plan"], "finalGameRasterSHA256": "abc123"},
                "content": [
                    {"type": "text", "text": "ok"},
                    {"type": "image", "data": base64.b64encode(png).decode()},
                    {"type": "audio", "data": base64.b64encode(wav).decode()},
                ],
            }
    print(json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}), flush=True)
'''

HANGING_SERVER = r'''
import sys
import time
for line in sys.stdin:
    time.sleep(10)
'''

PARTIAL_LINE_SERVER = r'''
import sys
import time
for line in sys.stdin:
    sys.stdout.write('{"jsonrpc":')
    sys.stdout.flush()
    time.sleep(10)
'''


class SwanSongTests(unittest.TestCase):
    def test_records_png_wav_and_identical_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            server = root / "server.py"
            server.write_text(SERVER)
            rom = root / "game.wsc"
            rom.write_bytes(b"ROM")
            plan = {"schema": "swan-song-frame-input-plan-v1", "totalFrames": 1, "events": []}
            environment = {"SWANSONG_MCP_COMMAND": f"{sys.executable} {server}"}
            with mock.patch.dict(os.environ, environment, clear=False):
                evidence = play(rom, plan, output=root / "evidence")
            self.assertEqual(evidence["finalGameRasterSHA256"], "abc123")
            self.assertTrue((root / "evidence/frame.png").read_bytes().startswith(b"\x89PNG"))
            self.assertEqual(json.loads((root / "evidence/evidence.json").read_text()), evidence)

    def test_refuses_non_swansong_server(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            server = root / "server.py"
            server.write_text(SERVER)
            rom = root / "game.wsc"
            rom.write_bytes(b"ROM")
            environment = {
                "SWANSONG_MCP_COMMAND": f"{sys.executable} {server}",
                "TEST_SERVER_NAME": "untrusted-emulator",
            }
            with mock.patch.dict(os.environ, environment, clear=False):
                with self.assertRaisesRegex(SwanSongError, "refusing non-SwanSong"):
                    play(rom, {}, output=root / "evidence")

    def test_times_out_and_terminates_hung_swansong_server(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            server = root / "hanging.py"
            server.write_text(HANGING_SERVER)
            rom = root / "game.wsc"
            rom.write_bytes(b"ROM")
            with mock.patch.dict(
                os.environ,
                {"SWANSONG_MCP_COMMAND": f"{sys.executable} {server}"},
                clear=False,
            ):
                with self.assertRaisesRegex(SwanSongError, "timed out"):
                    play(rom, {}, output=root / "evidence", timeout=0.05)

    def test_partial_json_line_cannot_bypass_deadline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            server = root / "partial.py"
            server.write_text(PARTIAL_LINE_SERVER)
            rom = root / "game.wsc"
            rom.write_bytes(b"ROM")
            with mock.patch.dict(
                os.environ,
                {"SWANSONG_MCP_COMMAND": f"{sys.executable} {server}"},
                clear=False,
            ):
                with self.assertRaisesRegex(SwanSongError, "timed out"):
                    play(rom, {}, output=root / "evidence", timeout=0.05)


if __name__ == "__main__":
    unittest.main()
