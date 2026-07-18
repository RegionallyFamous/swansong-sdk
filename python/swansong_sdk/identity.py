"""Compute a deterministic identity for the complete SwanSong SDK payload."""

from __future__ import annotations

import hashlib
from pathlib import Path

from . import __version__
from .layout import sdk_root


_PAYLOAD_DIRECTORIES = ("docs", "include", "mk", "schema", "src", "templates")
_PAYLOAD_FILES = ("CHANGELOG.md", "toolchain.lock")


def _payload_files() -> list[tuple[str, Path]]:
    root = sdk_root().resolve()
    package = Path(__file__).resolve().parent
    files: list[tuple[str, Path]] = []
    for path in sorted(package.rglob("*.py")):
        if path.is_file():
            files.append((f"python/swansong_sdk/{path.relative_to(package).as_posix()}", path))
    for directory in _PAYLOAD_DIRECTORIES:
        base = root / directory
        for path in sorted(base.rglob("*")):
            if path.is_file():
                files.append((path.relative_to(root).as_posix(), path))
    for name in _PAYLOAD_FILES:
        files.append((name, root / name))
    return sorted(files)


def sdk_payload_sha256() -> str:
    """Hash normalized paths and bytes for every distributable SDK input."""
    digest = hashlib.sha256()
    for name, path in _payload_files():
        payload = path.read_bytes()
        encoded = name.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def sdk_identity() -> dict[str, str]:
    """Return the version and content-addressed revision used by projects."""
    return {
        "version": __version__,
        "revision": f"sha256:{sdk_payload_sha256()}",
    }
