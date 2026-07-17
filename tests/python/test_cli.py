from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from swansong_sdk.cli import _parse_linked_usage, main


class CliTests(unittest.TestCase):
    def test_sdk_path_contains_complete_payload(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["sdk-path"]), 0)
        root = Path(output.getvalue().strip())
        for relative in ("include/swan/swan.h", "src/core.c", "mk/runtime-library.mk",
                         "templates/common/Makefile.tmpl", "schema/swan.schema.json"):
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


if __name__ == "__main__":
    unittest.main()
