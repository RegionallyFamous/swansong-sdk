"""Project scaffolding without a template-engine dependency."""

from __future__ import annotations

from pathlib import Path

from .identity import sdk_identity
from .layout import LayoutError, sdk_root
from .manifest import PROJECT_ID


RECIPES = ("arcade-action", "menu-puzzle", "grid-tactics")


class ScaffoldError(RuntimeError):
    pass


def _templates_root() -> Path:
    try:
        return sdk_root() / "templates"
    except LayoutError as exc:
        raise ScaffoldError(str(exc)) from exc


def _title(project_id: str) -> str:
    return " ".join(word.capitalize() for word in project_id.split("-"))


def create_project(project_id: str, recipe: str, destination: str | Path | None = None) -> Path:
    if not PROJECT_ID.fullmatch(project_id):
        raise ScaffoldError("game name must be lowercase kebab-case")
    if recipe not in RECIPES:
        raise ScaffoldError(f"unknown recipe {recipe!r}; choose one of {', '.join(RECIPES)}")
    target = Path(destination or project_id).resolve()
    if target.exists() and any(target.iterdir() if target.is_dir() else [target]):
        raise ScaffoldError(f"destination is not empty: {target}")
    source_roots = [_templates_root() / "common", _templates_root() / recipe]
    identity = sdk_identity()
    replacements = {
        "@@PROJECT_ID@@": project_id,
        "@@PROJECT_C_ID@@": project_id.replace("-", "_"),
        "@@PROJECT_TITLE@@": _title(project_id),
        "@@RECIPE@@": recipe,
        "@@SDK_VERSION@@": identity["version"],
        "@@SDK_REVISION@@": identity["revision"],
    }
    target.mkdir(parents=True, exist_ok=True)
    for source_root in source_roots:
        if not source_root.is_dir():
            raise ScaffoldError(f"template is incomplete: {source_root}")
        for source in sorted(source_root.rglob("*")):
            if not source.is_file():
                continue
            relative = source.relative_to(source_root)
            name = relative.name[:-5] if relative.name.endswith(".tmpl") else relative.name
            destination_path = target / relative.with_name(name)
            text = source.read_text()
            for needle, replacement in replacements.items():
                text = text.replace(needle, replacement)
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            destination_path.write_text(text)
    return target
