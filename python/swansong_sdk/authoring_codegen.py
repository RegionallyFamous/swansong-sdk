"""Deterministic C compilation for project-owned authoring documents.

The authoring JSON remains the editable source of truth.  This module turns the
portable parts of those documents into ordinary generated headers and C data;
it never executes project content or invokes an external converter.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .authoring import AuthoringError, canonical_digest, document_kind, validate_document


COMPILATION_SCHEMA = "swansong-authoring-compilation-v1"
COMPILABLE_KINDS = ("tilemap", "sprites", "palette", "collision", "scene-flow")


def _c_lower(value: str) -> str:
    return value.replace("-", "_")


def _c_upper(value: str) -> str:
    return _c_lower(value).upper()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _far_pointer(type_name: str, field: str) -> str:
    return f"    const {type_name} SWAN_FAR *{field};"


def _array(name: str, type_name: str, rows: Iterable[str]) -> list[str]:
    values = list(rows)
    if not values:
        return []
    return [
        f"const {type_name} SWAN_FAR {name}[{len(values)}] = {{",
        *(f"    {value}," for value in values),
        "};",
        "",
    ]


@dataclass(frozen=True)
class CompiledAuthoringDocument:
    kind: str
    identifier: str
    document_sha256: str
    header_name: str
    source_name: str
    header: str
    source: str
    document_path: str | None = None
    dependencies: tuple[tuple[str, str], ...] = ()

    def files(self) -> Mapping[str, bytes]:
        return {
            f"include/{self.header_name}": self.header.encode("utf-8"),
            f"src/{self.source_name}": self.source.encode("utf-8"),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": COMPILATION_SCHEMA,
            "kind": self.kind,
            "id": self.identifier,
            "document": self.document_path,
            "documentSHA256": self.document_sha256,
            "dependencies": [
                {"path": path, "sha256": digest}
                for path, digest in self.dependencies
            ],
            "header": self.header_name,
            "headerSHA256": _sha256(self.header.encode("utf-8")),
            "source": self.source_name,
            "sourceSHA256": _sha256(self.source.encode("utf-8")),
            "gameplayEvidence": False,
        }


def _preamble(document: Mapping[str, Any]) -> tuple[str, str, str, list[str]]:
    identifier = document["id"]
    lower = _c_lower(identifier)
    upper = _c_upper(identifier)
    digest = canonical_digest(document)
    lines = [
        f"/* Generated from an artist-owned {document_kind(document)} document. */",
        f"/* Source document SHA-256: {digest} */",
    ]
    return lower, upper, digest, lines


def _compile_tilemap(document: Mapping[str, Any]) -> tuple[str, str]:
    lower, upper, digest, comment = _preamble(document)
    prefix = f"swan_author_{lower}"
    cell_type = f"{prefix}_tile_cell_t"
    layer_type = f"{prefix}_tile_layer_t"
    map_type = f"{prefix}_tilemap_t"
    cells: list[Mapping[str, Any]] = []
    layer_rows: list[str] = []
    for layer in document["layers"]:
        first = len(cells)
        cells.extend(layer["cells"])
        layer_rows.append(
            "{%du, %du, %d, %d, %du}" % (
                first, len(layer["cells"]), layer["scrollX"], layer["scrollY"],
                1 if layer["visible"] else 0,
            )
        )
    cell_rows = [
        "{%du, %du, %du, %du, %du}" % (
            cell["x"], cell["y"], cell["tile"], cell["palette"],
            (1 if cell["flipX"] else 0) | (2 if cell["flipY"] else 0),
        )
        for cell in cells
    ]
    guard = f"SWAN_GENERATED_AUTHOR_{upper}_H"
    header = "\n".join([
        *comment, f"#ifndef {guard}", f"#define {guard}", "",
        "#include <stdint.h>", "#include <swan/types.h>", "",
        f"#define SWAN_AUTHOR_{upper}_SOURCE_SHA256 {json.dumps(digest)}",
        f"#define SWAN_AUTHOR_{upper}_CELL_COUNT {len(cells)}u",
        f"#define SWAN_AUTHOR_{upper}_LAYER_COUNT {len(layer_rows)}u", "",
        f"typedef struct {{ uint16_t x, y, tile; uint8_t palette, flags; }} {cell_type};",
        f"typedef struct {{ uint32_t first_cell, cell_count; int16_t scroll_x, scroll_y; uint8_t visible; }} {layer_type};",
        f"typedef struct {{",
        "    uint16_t width_tiles, height_tiles;", "    uint8_t layer_count;",
        _far_pointer(cell_type, "cells"), _far_pointer(layer_type, "layers"),
        f"}} {map_type};", "",
        *([f"extern const {cell_type} SWAN_FAR {prefix}_cells[{len(cells)}];"] if cells else []),
        f"extern const {layer_type} SWAN_FAR {prefix}_layers[{len(layer_rows)}];",
        f"extern const {map_type} SWAN_FAR {prefix};", "", "#endif", "",
    ])
    source = "\n".join([
        *comment, f'#include "{prefix}.h"', "",
        *_array(f"{prefix}_cells", cell_type, cell_rows),
        *_array(f"{prefix}_layers", layer_type, layer_rows),
        f"const {map_type} SWAN_FAR {prefix} = {{",
        f"    {document['width']}u, {document['height']}u, {len(layer_rows)}u,",
        f"    {'%s_cells' % prefix if cells else '0'}, {prefix}_layers",
        "};", "",
    ])
    return header, source


def _compile_sprites(document: Mapping[str, Any]) -> tuple[str, str]:
    lower, upper, digest, comment = _preamble(document)
    prefix = f"swan_author_{lower}"
    frame_type = f"{prefix}_frame_t"
    step_type = f"{prefix}_animation_step_t"
    animation_type = f"{prefix}_animation_t"
    hitbox_type = f"{prefix}_hitbox_t"
    sheet_type = f"{prefix}_sprite_sheet_t"
    frame_ids = {frame["id"]: index for index, frame in enumerate(document["frames"])}
    steps: list[Mapping[str, Any]] = []
    animation_rows: list[str] = []
    for animation in document["animations"]:
        first = len(steps)
        steps.extend(animation["steps"])
        animation_rows.append(
            "{%du, %du, %du}" % (first, len(animation["steps"]), 1 if animation["loop"] else 0)
        )
    frame_rows = [
        "{%du, %du, %du, %du, %d, %d}" % (
            frame["x"], frame["y"], frame["width"], frame["height"],
            frame["originX"], frame["originY"],
        )
        for frame in document["frames"]
    ]
    step_rows = [
        "{%du, %du, %du}" % (
            frame_ids[step["frame"]], step["durationFrames"],
            (1 if step["flipX"] else 0) | (2 if step["flipY"] else 0),
        )
        for step in steps
    ]
    kinds = {"solid": 0, "hurt": 1, "attack": 2, "trigger": 3}
    hitbox_rows = [
        "{%du, %du, %d, %d, %du, %du}" % (
            frame_ids[item["frame"]], kinds[item["kind"]], item["x"], item["y"],
            item["width"], item["height"],
        )
        for item in document["hitboxes"]
    ]
    guard = f"SWAN_GENERATED_AUTHOR_{upper}_H"
    header = "\n".join([
        *comment, f"#ifndef {guard}", f"#define {guard}", "",
        "#include <stdint.h>", "#include <swan/types.h>", "",
        f"#define SWAN_AUTHOR_{upper}_SOURCE_SHA256 {json.dumps(digest)}",
        f"#define SWAN_AUTHOR_{upper}_FRAME_COUNT {len(frame_rows)}u",
        f"#define SWAN_AUTHOR_{upper}_ANIMATION_COUNT {len(animation_rows)}u",
        f"#define SWAN_AUTHOR_{upper}_HITBOX_COUNT {len(hitbox_rows)}u", "",
        f"typedef struct {{ uint16_t x, y, width, height; int16_t origin_x, origin_y; }} {frame_type};",
        f"typedef struct {{ uint16_t frame, duration_frames; uint8_t flags; }} {step_type};",
        f"typedef struct {{ uint32_t first_step, step_count; uint8_t loop; }} {animation_type};",
        f"typedef struct {{ uint16_t frame; uint8_t kind; int16_t x, y; uint16_t width, height; }} {hitbox_type};",
        f"typedef struct {{", "    uint16_t frame_count, animation_count, hitbox_count;",
        _far_pointer(frame_type, "frames"), _far_pointer(step_type, "steps"),
        _far_pointer(animation_type, "animations"), _far_pointer(hitbox_type, "hitboxes"),
        f"}} {sheet_type};", "",
        f"extern const {frame_type} SWAN_FAR {prefix}_frames[{len(frame_rows)}];",
        f"extern const {step_type} SWAN_FAR {prefix}_steps[{len(step_rows)}];",
        f"extern const {animation_type} SWAN_FAR {prefix}_animations[{len(animation_rows)}];",
        *([f"extern const {hitbox_type} SWAN_FAR {prefix}_hitboxes[{len(hitbox_rows)}];"] if hitbox_rows else []),
        f"extern const {sheet_type} SWAN_FAR {prefix};", "", "#endif", "",
    ])
    source = "\n".join([
        *comment, f'#include "{prefix}.h"', "",
        *_array(f"{prefix}_frames", frame_type, frame_rows),
        *_array(f"{prefix}_steps", step_type, step_rows),
        *_array(f"{prefix}_animations", animation_type, animation_rows),
        *_array(f"{prefix}_hitboxes", hitbox_type, hitbox_rows),
        f"const {sheet_type} SWAN_FAR {prefix} = {{",
        f"    {len(frame_rows)}u, {len(animation_rows)}u, {len(hitbox_rows)}u,",
        f"    {prefix}_frames, {prefix}_steps, {prefix}_animations,",
        f"    {'%s_hitboxes' % prefix if hitbox_rows else '0'}", "};", "",
    ])
    return header, source


def _rgb444(color: str) -> int:
    red, green, blue = (int(color[index:index + 2], 16) for index in (1, 3, 5))
    return (blue >> 4) << 8 | (green >> 4) << 4 | (red >> 4)


def _compile_palette(document: Mapping[str, Any]) -> tuple[str, str]:
    lower, upper, digest, comment = _preamble(document)
    prefix = f"swan_author_{lower}"
    palette_type = f"{prefix}_palette_t"
    colors = [_rgb444(color) for color in document["colors"]]
    transparent = -1 if document["transparentIndex"] is None else document["transparentIndex"]
    guard = f"SWAN_GENERATED_AUTHOR_{upper}_H"
    header = "\n".join([
        *comment, f"#ifndef {guard}", f"#define {guard}", "",
        "#include <stdint.h>", "#include <swan/types.h>", "",
        f"#define SWAN_AUTHOR_{upper}_SOURCE_SHA256 {json.dumps(digest)}",
        f"#define SWAN_AUTHOR_{upper}_COLOR_COUNT {len(colors)}u", "",
        f"typedef struct {{ uint8_t color_count; int8_t transparent_index;",
        "    const uint16_t SWAN_FAR *colors_rgb444;",
        "    const uint8_t SWAN_FAR *mono_mapping;",
        f"}} {palette_type};", "",
        f"extern const uint16_t SWAN_FAR {prefix}_colors_rgb444[{len(colors)}];",
        f"extern const uint8_t SWAN_FAR {prefix}_mono_mapping[{len(colors)}];",
        f"extern const {palette_type} SWAN_FAR {prefix};", "", "#endif", "",
    ])
    source = "\n".join([
        *comment, f'#include "{prefix}.h"', "",
        *_array(f"{prefix}_colors_rgb444", "uint16_t", (f"0x{value:04X}u" for value in colors)),
        *_array(f"{prefix}_mono_mapping", "uint8_t", (f"{value}u" for value in document["monoMapping"])),
        f"const {palette_type} SWAN_FAR {prefix} = {{",
        f"    {len(colors)}u, {transparent}, {prefix}_colors_rgb444, {prefix}_mono_mapping",
        "};", "",
    ])
    return header, source


def _compile_collision(document: Mapping[str, Any]) -> tuple[str, str]:
    lower, upper, digest, comment = _preamble(document)
    prefix = f"swan_author_{lower}"
    point_type = f"{prefix}_point_t"
    region_type = f"{prefix}_region_t"
    path_point_type = f"{prefix}_path_point_t"
    path_type = f"{prefix}_path_t"
    collision_type = f"{prefix}_collision_t"
    region_points: list[Mapping[str, Any]] = []
    region_rows: list[str] = []
    region_kinds = {"solid": 0, "hazard": 1, "trigger": 2, "one-way": 3}
    for region in document["regions"]:
        first = len(region_points)
        region_points.extend(region["points"])
        region_rows.append("{%du, %du, %du, %du}" % (
            first, len(region["points"]), region_kinds[region["kind"]],
            1 if region["closed"] else 0,
        ))
    path_points: list[Mapping[str, Any]] = []
    path_rows: list[str] = []
    for path in document["paths"]:
        first = len(path_points)
        path_points.extend(path["points"])
        path_rows.append("{%du, %du, %du}" % (
            first, len(path["points"]), 1 if path["loop"] else 0,
        ))
    guard = f"SWAN_GENERATED_AUTHOR_{upper}_H"
    header = "\n".join([
        *comment, f"#ifndef {guard}", f"#define {guard}", "",
        "#include <stdint.h>", "#include <swan/types.h>", "",
        f"#define SWAN_AUTHOR_{upper}_SOURCE_SHA256 {json.dumps(digest)}",
        f"typedef struct {{ uint16_t x, y; }} {point_type};",
        f"typedef struct {{ uint32_t first_point, point_count; uint8_t kind, closed; }} {region_type};",
        f"typedef struct {{ uint16_t x, y, wait_frames; }} {path_point_type};",
        f"typedef struct {{ uint32_t first_point, point_count; uint8_t loop; }} {path_type};",
        f"typedef struct {{", "    uint16_t width_pixels, height_pixels, region_count, path_count;",
        _far_pointer(point_type, "region_points"), _far_pointer(region_type, "regions"),
        _far_pointer(path_point_type, "path_points"), _far_pointer(path_type, "paths"),
        f"}} {collision_type};", "",
        *([f"extern const {point_type} SWAN_FAR {prefix}_region_points[{len(region_points)}];"] if region_points else []),
        *([f"extern const {region_type} SWAN_FAR {prefix}_regions[{len(region_rows)}];"] if region_rows else []),
        *([f"extern const {path_point_type} SWAN_FAR {prefix}_path_points[{len(path_points)}];"] if path_points else []),
        *([f"extern const {path_type} SWAN_FAR {prefix}_paths[{len(path_rows)}];"] if path_rows else []),
        f"extern const {collision_type} SWAN_FAR {prefix};", "", "#endif", "",
    ])
    source = "\n".join([
        *comment, f'#include "{prefix}.h"', "",
        *_array(f"{prefix}_region_points", point_type,
                ("{%du, %du}" % (p["x"], p["y"]) for p in region_points)),
        *_array(f"{prefix}_regions", region_type, region_rows),
        *_array(f"{prefix}_path_points", path_point_type,
                ("{%du, %du, %du}" % (p["x"], p["y"], p["waitFrames"]) for p in path_points)),
        *_array(f"{prefix}_paths", path_type, path_rows),
        f"const {collision_type} SWAN_FAR {prefix} = {{",
        f"    {document['width']}u, {document['height']}u, {len(region_rows)}u, {len(path_rows)}u,",
        f"    {'%s_region_points' % prefix if region_points else '0'}, {'%s_regions' % prefix if region_rows else '0'},",
        f"    {'%s_path_points' % prefix if path_points else '0'}, {'%s_paths' % prefix if path_rows else '0'}",
        "};", "",
    ])
    return header, source


def _compile_scene_flow(document: Mapping[str, Any]) -> tuple[str, str]:
    lower, upper, digest, comment = _preamble(document)
    prefix = f"swan_author_{lower}"
    transition_type = f"{prefix}_transition_t"
    flow_type = f"{prefix}_scene_flow_t"
    scene_ids = {scene["id"]: index for index, scene in enumerate(document["scenes"])}
    event_names = list(dict.fromkeys(item["event"] for item in document["transitions"]))
    event_ids = {name: index for index, name in enumerate(event_names)}
    rows = [
        "{%du, %du, %du, %du}" % (
            scene_ids[item["from"]], scene_ids[item["to"]], event_ids[item["event"]],
            item["argument"],
        )
        for item in document["transitions"]
    ]
    guard = f"SWAN_GENERATED_AUTHOR_{upper}_H"
    scene_enum = [
        f"    SWAN_AUTHOR_{upper}_SCENE_{_c_upper(scene['id'])} = {index},"
        for index, scene in enumerate(document["scenes"])
    ]
    event_enum = ([
        f"    SWAN_AUTHOR_{upper}_EVENT_{_c_upper(name)} = {index},"
        for index, name in enumerate(event_names)
    ] or [f"    SWAN_AUTHOR_{upper}_EVENT_NONE = 0,"])
    header = "\n".join([
        *comment, f"#ifndef {guard}", f"#define {guard}", "",
        "#include <stdint.h>", "#include <swan/types.h>", "",
        f"#define SWAN_AUTHOR_{upper}_SOURCE_SHA256 {json.dumps(digest)}", "",
        f"enum swan_author_{lower}_scene_id {{", *scene_enum,
        f"    SWAN_AUTHOR_{upper}_SCENE_COUNT = {len(scene_ids)}", "};", "",
        f"enum swan_author_{lower}_event_id {{", *event_enum,
        f"    SWAN_AUTHOR_{upper}_EVENT_COUNT = {len(event_names)}", "};", "",
        f"typedef struct {{ uint8_t from_scene, to_scene, event; uint16_t argument; }} {transition_type};",
        f"typedef struct {{ uint8_t initial_scene, scene_count; uint16_t transition_count;",
        _far_pointer(transition_type, "transitions"), f"}} {flow_type};", "",
        *([f"extern const {transition_type} SWAN_FAR {prefix}_transitions[{len(rows)}];"] if rows else []),
        f"extern const {flow_type} SWAN_FAR {prefix};", "", "#endif", "",
    ])
    source = "\n".join([
        *comment, f'#include "{prefix}.h"', "",
        *_array(f"{prefix}_transitions", transition_type, rows),
        f"const {flow_type} SWAN_FAR {prefix} = {{",
        f"    {scene_ids[document['initialScene']]}u, {len(scene_ids)}u, {len(rows)}u,",
        f"    {'%s_transitions' % prefix if rows else '0'}", "};", "",
    ])
    return header, source


_COMPILERS = {
    "tilemap": _compile_tilemap,
    "sprites": _compile_sprites,
    "palette": _compile_palette,
    "collision": _compile_collision,
    "scene-flow": _compile_scene_flow,
}


def compile_authoring_document(
    value: object, *, document_path: str | None = None,
    dependencies: Mapping[str, str] | None = None,
) -> CompiledAuthoringDocument:
    """Compile one validated authoring document into deterministic C data."""
    document = validate_document(value)
    kind = document_kind(document)
    if kind not in COMPILABLE_KINDS:
        raise AuthoringError(f"{kind} is exported through its native asset compiler")
    identifier = document["id"]
    lower = _c_lower(identifier)
    header, source = _COMPILERS[kind](document)
    return CompiledAuthoringDocument(
        kind=kind,
        identifier=identifier,
        document_sha256=canonical_digest(document),
        header_name=f"swan_author_{lower}.h",
        source_name=f"swan_author_{lower}.c",
        header=header,
        source=source,
        document_path=document_path,
        dependencies=tuple(sorted((dependencies or {}).items())),
    )


def _safe_project_file(root: Path, value: str, context: str) -> Path:
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise AuthoringError(f"{context} points outside the project") from exc
    if not candidate.is_file():
        raise AuthoringError(f"{context} does not exist: {value}")
    return candidate


def compile_project_authoring(project_root: str | Path) -> tuple[CompiledAuthoringDocument, ...]:
    """Discover and compile project ``authoring/*.<kind>.json`` documents."""
    root = Path(project_root).resolve()
    directory = root / "authoring"
    if not directory.is_dir():
        return ()
    suffixes = {f".{kind}.json": kind for kind in COMPILABLE_KINDS}
    candidates = [
        path for path in directory.rglob("*.json")
        if any(path.name.endswith(suffix) for suffix in suffixes)
    ]
    compiled: list[CompiledAuthoringDocument] = []
    output_names: set[str] = set()
    for path in sorted(candidates, key=lambda item: item.relative_to(root).as_posix()):
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(root).as_posix()
        except ValueError as exc:
            raise AuthoringError(f"authoring document points outside the project: {path}") from exc
        try:
            value = json.loads(resolved.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise AuthoringError(f"could not read authoring document {relative}: {exc}") from exc
        kind = document_kind(value)
        expected_suffix = f".{kind}.json"
        if not path.name.endswith(expected_suffix):
            raise AuthoringError(
                f"authoring document {relative} must end with {expected_suffix}"
            )
        dependencies: dict[str, str] = {}
        if kind == "tilemap":
            source_value = value.get("tilesetSource")
            if isinstance(source_value, str):
                source = _safe_project_file(root, source_value, "tilemap tilesetSource")
                dependencies[source_value] = _sha256(source.read_bytes())
        elif kind == "sprites":
            source_value = value.get("source")
            if isinstance(source_value, str):
                source = _safe_project_file(root, source_value, "sprites source")
                dependencies[source_value] = _sha256(source.read_bytes())
        item = compile_authoring_document(
            value, document_path=relative, dependencies=dependencies,
        )
        if item.source_name in output_names:
            raise AuthoringError(
                f"authoring id {item.identifier!r} produces a duplicate generated source"
            )
        output_names.add(item.source_name)
        compiled.append(item)
    return tuple(compiled)
