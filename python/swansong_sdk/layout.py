"""Locate the complete SDK payload in a source checkout or wheel install."""

from __future__ import annotations

from pathlib import Path
import sysconfig


class LayoutError(RuntimeError):
    pass


def sdk_root() -> Path:
    repository = Path(__file__).resolve().parents[2]
    if all((repository / name).is_dir() for name in ("include", "src", "mk", "templates")):
        return repository
    package = Path(__file__).resolve()
    candidates = [
        *(parent / "share" / "swansong-sdk" for parent in package.parents),
        Path(sysconfig.get_path("data")) / "share" / "swansong-sdk",
    ]
    seen: set[Path] = set()
    for shared in candidates:
        if shared in seen:
            continue
        seen.add(shared)
        if all((shared / name).is_dir() for name in ("include", "src", "mk", "templates")):
            return shared
    raise LayoutError("the installed SwanSong SDK is missing its C runtime payload")
