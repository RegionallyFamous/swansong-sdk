"""Previewable, reversible SwanSong project metadata migrations."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import tempfile


REPORT_SCHEMA = "swansong-migration-report-v1"
SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
REVISION = re.compile(r"^sha256:[0-9a-f]{64}$")


class MigrationError(RuntimeError):
    pass


def _replace_single(text: str, pattern: str, replacement: str, label: str) -> tuple[str, str | None]:
    matches = list(re.finditer(pattern, text, flags=re.MULTILINE))
    if len(matches) > 1:
        raise MigrationError(f"manifest contains duplicate {label} declarations")
    if not matches:
        return text, None
    match = matches[0]
    previous = match.group(0)
    return text[:match.start()] + replacement + text[match.end():], previous


def plan_migration(manifest_path: Path, *, target_version: str,
                   target_revision: str, target_schema: int = 1) -> dict[str, object]:
    if not SEMVER.fullmatch(target_version):
        raise MigrationError("target SDK version must be semantic, such as 0.5.0")
    if not REVISION.fullmatch(target_revision):
        raise MigrationError("target SDK revision must be sha256 followed by 64 lowercase hexadecimal digits")
    if not isinstance(target_schema, int) or isinstance(target_schema, bool) or target_schema < 1:
        raise MigrationError("target schema must be a positive integer")
    try:
        original = manifest_path.read_text()
    except OSError as exc:
        raise MigrationError(f"could not read manifest {manifest_path}: {exc}") from exc
    normalized = original.replace("\r\n", "\n")
    updated, old_schema = _replace_single(
        normalized, r"^schema_version\s*=\s*\d+\s*$",
        f"schema_version = {target_schema}", "schema_version",
    )
    if old_schema is None:
        raise MigrationError("manifest is missing schema_version")
    sdk_match = re.search(r"^\[sdk\]\s*$", updated, flags=re.MULTILINE)
    if sdk_match is None:
        insertion = f'\n[sdk]\nversion = "{target_version}"\nrevision = "{target_revision}"\n'
        line_end = updated.find("\n", re.search(r"^schema_version\s*=.*$", updated, flags=re.MULTILINE).end())
        if line_end < 0:
            updated += insertion
        else:
            updated = updated[:line_end + 1] + insertion.lstrip("\n") + updated[line_end + 1:]
        old_version = old_revision = None
    else:
        next_section = re.search(r"^\[[^]]+\]\s*$", updated[sdk_match.end():], flags=re.MULTILINE)
        section_end = sdk_match.end() + (next_section.start() if next_section else len(updated[sdk_match.end():]))
        section = updated[sdk_match.end():section_end]
        section, old_version = _replace_single(
            section, r'^version\s*=\s*"[^"]*"\s*$',
            f'version = "{target_version}"', "sdk.version",
        )
        section, old_revision = _replace_single(
            section, r'^revision\s*=\s*"[^"]*"\s*$',
            f'revision = "{target_revision}"', "sdk.revision",
        )
        if old_version is None or old_revision is None:
            raise MigrationError("existing [sdk] table must declare both version and revision")
        updated = updated[:sdk_match.end()] + section + updated[section_end:]
    if not updated.endswith("\n"):
        updated += "\n"
    changes: list[dict[str, object]] = []
    if old_schema != f"schema_version = {target_schema}":
        changes.append({"field": "schema_version", "before": old_schema, "after": target_schema})
    if old_version != f'version = "{target_version}"':
        changes.append({"field": "sdk.version", "before": old_version, "after": target_version})
    if old_revision != f'revision = "{target_revision}"':
        changes.append({"field": "sdk.revision", "before": old_revision, "after": target_revision})
    return {
        "schema": REPORT_SCHEMA,
        "manifest": str(manifest_path.resolve()),
        "fromSHA256": hashlib.sha256(normalized.encode()).hexdigest(),
        "toSHA256": hashlib.sha256(updated.encode()).hexdigest(),
        "targetSchema": target_schema,
        "targetSDKVersion": target_version,
        "targetSDKRevision": target_revision,
        "changes": changes,
        "changed": updated != normalized,
        "applied": False,
        "backup": None,
        "updatedText": updated,
    }


def apply_migration(report: dict[str, object]) -> dict[str, object]:
    if report.get("schema") != REPORT_SCHEMA or not isinstance(report.get("manifest"), str):
        raise MigrationError("invalid migration report")
    manifest = Path(str(report["manifest"]))
    updated = report.get("updatedText")
    if not isinstance(updated, str):
        raise MigrationError("migration report is missing updated text")
    try:
        current = manifest.read_bytes()
    except OSError as exc:
        raise MigrationError(f"could not reread manifest {manifest}: {exc}") from exc
    if hashlib.sha256(current.replace(b"\r\n", b"\n")).hexdigest() != report.get("fromSHA256"):
        raise MigrationError("manifest changed after migration preview; create a new plan")
    backup = manifest.with_name(f"{manifest.name}.swan-backup-{str(report['fromSHA256'])[:12]}")
    try:
        with backup.open("xb") as destination:
            destination.write(current)
    except FileExistsError:
        if backup.read_bytes() != current:
            raise MigrationError(f"existing migration backup does not match source: {backup}")
    except OSError as exc:
        raise MigrationError(f"could not write migration backup {backup}: {exc}") from exc
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=manifest.parent,
            prefix=f".{manifest.name}.", suffix=".swan-migrate", delete=False,
        ) as destination:
            destination.write(updated)
            destination.flush()
            os.fsync(destination.fileno())
            temporary = Path(destination.name)
        temporary.replace(manifest)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise MigrationError(f"could not apply migration to {manifest}: {exc}") from exc
    result = dict(report)
    result.pop("updatedText", None)
    result["applied"] = True
    result["backup"] = str(backup)
    return result
