"""Explicit, hash-bound imports for assets outside a SwanSong project."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


SCHEMA = "swansong-asset-import-report-v1"


class AssetImportError(ValueError):
    pass


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _project_path(root: Path, value: str | Path, label: str) -> Path:
    raw = Path(value)
    candidate = (raw if raw.is_absolute() else root / raw).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise AssetImportError(f"{label} must remain inside the project") from exc
    if candidate == root:
        raise AssetImportError(f"{label} must name a file inside the project")
    return candidate


def import_asset(
    project_root: str | Path,
    source: str | Path,
    destination: str | Path,
    provenance_report: str | Path,
    *,
    expected_sha256: str,
) -> dict[str, object]:
    """Copy one external file into a project without weakening manifest isolation."""
    root = Path(project_root).resolve()
    source_path = Path(source).expanduser().resolve()
    destination_path = _project_path(root, destination, "asset destination")
    report_path = _project_path(root, provenance_report, "provenance report")
    if not source_path.is_file():
        raise AssetImportError(f"asset import source does not exist: {source_path}")
    if destination_path == report_path:
        raise AssetImportError("asset destination and provenance report must differ")
    if destination_path.exists() or report_path.exists():
        raise AssetImportError("asset import never overwrites destination files")
    if len(expected_sha256) != 64:
        raise AssetImportError("expected_sha256 must be a SHA-256 hex digest")
    try:
        int(expected_sha256, 16)
    except ValueError as exc:
        raise AssetImportError("expected_sha256 must be a SHA-256 hex digest") from exc
    payload = source_path.read_bytes()
    digest = _sha256(payload)
    if digest != expected_sha256.lower():
        raise AssetImportError("asset import source does not match the reviewed SHA-256")
    report: dict[str, object] = {
        "schema": SCHEMA,
        "source": {
            "path": str(source_path),
            "sha256": digest,
            "bytes": len(payload),
        },
        "destination": {
            "path": destination_path.relative_to(root).as_posix(),
            "sha256": digest,
            "bytes": len(payload),
        },
        "provenanceReport": report_path.relative_to(root).as_posix(),
        "copied": True,
        "gameplayEvidence": False,
    }
    report_payload = (
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    ).encode("utf-8")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination_path.open("xb") as handle:
            handle.write(payload)
        with report_path.open("xb") as handle:
            handle.write(report_payload)
    except BaseException:
        if destination_path.is_file() and _sha256(destination_path.read_bytes()) == digest:
            destination_path.unlink()
        raise
    return report
