"""Project-owned visual authoring documents and deterministic export handoffs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
from typing import Any, Callable, Mapping

from .optimize import encode_rgba_png
from .png2bpp import Image


REPORT_SCHEMA = "swansong-author-operation-report-v1"
HANDOFF_SCHEMA = "swansong-author-handoff-v1"
KINDS = ("tilemap", "sprites", "palette", "collision", "scene-flow", "audio")
SCHEMAS = {kind: f"swansong-author-{kind}-v1" for kind in KINDS}
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


class AuthoringError(ValueError):
    pass


def canonical_json(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def canonical_digest(value: object) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _identifier(value: object, context: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise AuthoringError(f"{context} must be lowercase kebab-case")
    return value


def _integer(value: object, context: str, minimum: int, maximum: int) -> int:
    if (not isinstance(value, int) or isinstance(value, bool) or
            not minimum <= value <= maximum):
        raise AuthoringError(f"{context} must be an integer from {minimum} to {maximum}")
    return value


def _boolean(value: object, context: str) -> bool:
    if not isinstance(value, bool):
        raise AuthoringError(f"{context} must be true or false")
    return value


def _array(value: object, context: str, minimum: int = 0,
           maximum: int | None = None) -> list[Any]:
    if not isinstance(value, list) or len(value) < minimum or (
        maximum is not None and len(value) > maximum
    ):
        bounds = f"{minimum}..{maximum}" if maximum is not None else f"at least {minimum}"
        raise AuthoringError(f"{context} must be an array with {bounds} item(s)")
    return value


def _object(value: object, context: str, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise AuthoringError(f"{context} must contain exactly: {', '.join(sorted(keys))}")
    return value


def _source_path(value: object, context: str, suffix: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise AuthoringError(f"{context} must be a project-relative {suffix} path")
    path = PurePosixPath(value)
    windows_path = PureWindowsPath(value)
    if (path.is_absolute() or windows_path.is_absolute() or windows_path.drive or
            ".." in path.parts or path.suffix.lower() != suffix):
        raise AuthoringError(f"{context} must be a project-relative {suffix} path")
    return value


def _unique(items: list[dict[str, Any]], context: str) -> set[str]:
    identifiers = [_identifier(item.get("id"), f"{context} id") for item in items]
    if len(identifiers) != len(set(identifiers)):
        raise AuthoringError(f"{context} ids must be unique")
    return set(identifiers)


def _top(value: object, kind: str, keys: set[str]) -> dict[str, Any]:
    document = _object(value, f"{kind} document", keys | {"schema", "id"})
    if document["schema"] != SCHEMAS[kind]:
        raise AuthoringError(f"{kind} document must use {SCHEMAS[kind]}")
    _identifier(document["id"], f"{kind} document id")
    return document


def _validate_tilemap(value: object) -> dict[str, Any]:
    document = _top(value, "tilemap", {
        "tileSize", "width", "height", "tilesetSource", "layers",
    })
    if document["tileSize"] != 8:
        raise AuthoringError("tilemap tileSize must be 8")
    width = _integer(document["width"], "tilemap width", 1, 256)
    height = _integer(document["height"], "tilemap height", 1, 256)
    _source_path(document["tilesetSource"], "tilemap tilesetSource", ".png")
    layers = _array(document["layers"], "tilemap layers", 1, 2)
    checked_layers = [
        _object(item, f"tilemap layer {index}", {
            "id", "visible", "scrollX", "scrollY", "cells",
        }) for index, item in enumerate(layers)
    ]
    _unique(checked_layers, "tilemap layer")
    for layer_index, layer in enumerate(checked_layers):
        _boolean(layer["visible"], f"tilemap layer {layer_index} visible")
        _integer(layer["scrollX"], f"tilemap layer {layer_index} scrollX", -32768, 32767)
        _integer(layer["scrollY"], f"tilemap layer {layer_index} scrollY", -32768, 32767)
        cells = _array(layer["cells"], f"tilemap layer {layer_index} cells")
        coordinates: set[tuple[int, int]] = set()
        for cell_index, raw_cell in enumerate(cells):
            cell = _object(raw_cell, f"tilemap cell {layer_index}:{cell_index}", {
                "x", "y", "tile", "palette", "flipX", "flipY",
            })
            x = _integer(cell["x"], "tilemap cell x", 0, width - 1)
            y = _integer(cell["y"], "tilemap cell y", 0, height - 1)
            if (x, y) in coordinates:
                raise AuthoringError(f"tilemap layer {layer_index} contains duplicate cell {x},{y}")
            coordinates.add((x, y))
            _integer(cell["tile"], "tilemap cell tile", 0, 1023)
            _integer(cell["palette"], "tilemap cell palette", 0, 15)
            _boolean(cell["flipX"], "tilemap cell flipX")
            _boolean(cell["flipY"], "tilemap cell flipY")
    return document


def _validate_sprites(value: object) -> dict[str, Any]:
    document = _top(value, "sprites", {"source", "frames", "animations", "hitboxes"})
    _source_path(document["source"], "sprites source", ".png")
    frames = [_object(item, f"sprite frame {index}", {
        "id", "x", "y", "width", "height", "originX", "originY",
    }) for index, item in enumerate(_array(document["frames"], "sprite frames", 1, 1024))]
    frame_ids = _unique(frames, "sprite frame")
    for index, frame in enumerate(frames):
        _integer(frame["x"], f"sprite frame {index} x", 0, 65535)
        _integer(frame["y"], f"sprite frame {index} y", 0, 65535)
        width = _integer(frame["width"], f"sprite frame {index} width", 1, 224)
        height = _integer(frame["height"], f"sprite frame {index} height", 1, 144)
        _integer(frame["originX"], f"sprite frame {index} originX", -width, width)
        _integer(frame["originY"], f"sprite frame {index} originY", -height, height)
    animations = [_object(item, f"sprite animation {index}", {
        "id", "loop", "steps",
    }) for index, item in enumerate(_array(document["animations"], "sprite animations", 1, 256))]
    _unique(animations, "sprite animation")
    for animation_index, animation in enumerate(animations):
        _boolean(animation["loop"], f"sprite animation {animation_index} loop")
        for step_index, raw_step in enumerate(_array(
            animation["steps"], f"sprite animation {animation_index} steps", 1, 4096,
        )):
            step = _object(raw_step, f"sprite step {animation_index}:{step_index}", {
                "frame", "durationFrames", "flipX", "flipY",
            })
            if not isinstance(step["frame"], str) or step["frame"] not in frame_ids:
                raise AuthoringError(f"sprite step references unknown frame {step['frame']!r}")
            _integer(step["durationFrames"], "sprite step durationFrames", 1, 65535)
            _boolean(step["flipX"], "sprite step flipX")
            _boolean(step["flipY"], "sprite step flipY")
    hitboxes = [_object(item, f"sprite hitbox {index}", {
        "id", "frame", "kind", "x", "y", "width", "height",
    }) for index, item in enumerate(_array(document["hitboxes"], "sprite hitboxes", 0, 4096))]
    _unique(hitboxes, "sprite hitbox")
    for index, hitbox in enumerate(hitboxes):
        if not isinstance(hitbox["frame"], str) or hitbox["frame"] not in frame_ids:
            raise AuthoringError(f"sprite hitbox references unknown frame {hitbox['frame']!r}")
        if (not isinstance(hitbox["kind"], str) or
                hitbox["kind"] not in {"solid", "hurt", "attack", "trigger"}):
            raise AuthoringError(f"sprite hitbox {index} kind is invalid")
        _integer(hitbox["x"], f"sprite hitbox {index} x", -32768, 32767)
        _integer(hitbox["y"], f"sprite hitbox {index} y", -32768, 32767)
        _integer(hitbox["width"], f"sprite hitbox {index} width", 1, 65535)
        _integer(hitbox["height"], f"sprite hitbox {index} height", 1, 65535)
    return document


def _validate_palette(value: object) -> dict[str, Any]:
    document = _top(value, "palette", {"colors", "monoMapping", "transparentIndex"})
    colors = _array(document["colors"], "palette colors", 1, 16)
    if not all(isinstance(color, str) and _COLOR.fullmatch(color) for color in colors):
        raise AuthoringError("palette colors must use #RRGGBB")
    mono = _array(document["monoMapping"], "palette monoMapping", len(colors), len(colors))
    for index, shade in enumerate(mono):
        _integer(shade, f"palette monoMapping {index}", 0, 3)
    transparent = document["transparentIndex"]
    if transparent is not None:
        _integer(transparent, "palette transparentIndex", 0, len(colors) - 1)
    return document


def _point(value: object, context: str, width: int, height: int,
           *, wait: bool = False) -> dict[str, Any]:
    keys = {"x", "y", "waitFrames"} if wait else {"x", "y"}
    point = _object(value, context, keys)
    _integer(point["x"], f"{context} x", 0, width - 1)
    _integer(point["y"], f"{context} y", 0, height - 1)
    if wait:
        _integer(point["waitFrames"], f"{context} waitFrames", 0, 65535)
    return point


def _validate_collision(value: object) -> dict[str, Any]:
    document = _top(value, "collision", {"width", "height", "regions", "paths"})
    width = _integer(document["width"], "collision width", 1, 65535)
    height = _integer(document["height"], "collision height", 1, 65535)
    regions = [_object(item, f"collision region {index}", {
        "id", "kind", "closed", "points",
    }) for index, item in enumerate(_array(document["regions"], "collision regions", 0, 4096))]
    _unique(regions, "collision region")
    for index, region in enumerate(regions):
        if (not isinstance(region["kind"], str) or
                region["kind"] not in {"solid", "hazard", "trigger", "one-way"}):
            raise AuthoringError(f"collision region {index} kind is invalid")
        closed = _boolean(region["closed"], f"collision region {index} closed")
        points = _array(region["points"], f"collision region {index} points", 3 if closed else 2, 256)
        for point_index, raw_point in enumerate(points):
            _point(raw_point, f"collision region {index} point {point_index}", width, height)
    paths = [_object(item, f"collision path {index}", {
        "id", "loop", "points",
    }) for index, item in enumerate(_array(document["paths"], "collision paths", 0, 1024))]
    _unique(paths, "collision path")
    for index, path in enumerate(paths):
        _boolean(path["loop"], f"collision path {index} loop")
        for point_index, raw_point in enumerate(_array(
            path["points"], f"collision path {index} points", 1, 4096,
        )):
            _point(raw_point, f"collision path {index} point {point_index}", width, height, wait=True)
    return document


def _validate_scene_flow(value: object) -> dict[str, Any]:
    document = _top(value, "scene-flow", {"initialScene", "scenes", "transitions"})
    scenes = [_object(item, f"scene-flow scene {index}", {"id", "title"})
              for index, item in enumerate(_array(document["scenes"], "scene-flow scenes", 1, 255))]
    scene_ids = _unique(scenes, "scene-flow scene")
    for index, scene in enumerate(scenes):
        if not isinstance(scene["title"], str) or not scene["title"].strip():
            raise AuthoringError(f"scene-flow scene {index} title must be nonempty")
    if (not isinstance(document["initialScene"], str) or
            document["initialScene"] not in scene_ids):
        raise AuthoringError("scene-flow initialScene must reference a declared scene")
    transitions = [_object(item, f"scene-flow transition {index}", {
        "id", "from", "to", "event", "argument",
    }) for index, item in enumerate(_array(document["transitions"], "scene-flow transitions", 0, 4096))]
    _unique(transitions, "scene-flow transition")
    routes: set[tuple[str, str]] = set()
    for index, transition in enumerate(transitions):
        if (not isinstance(transition["from"], str) or
                not isinstance(transition["to"], str) or
                transition["from"] not in scene_ids or transition["to"] not in scene_ids):
            raise AuthoringError(f"scene-flow transition {index} references an unknown scene")
        event = _identifier(transition["event"], f"scene-flow transition {index} event")
        route = (transition["from"], event)
        if route in routes:
            raise AuthoringError(
                f"scene-flow has multiple transitions from {route[0]!r} for event {event!r}"
            )
        routes.add(route)
        _integer(transition["argument"], f"scene-flow transition {index} argument", 0, 65535)
    return document


def _validate_audio(value: object) -> dict[str, Any]:
    document = _top(value, "audio", {
        "framesPerRowQ8", "loop", "instruments", "rows",
    })
    _integer(document["framesPerRowQ8"], "audio framesPerRowQ8", 1, 65535)
    _boolean(document["loop"], "audio loop")
    instruments = [_object(item, f"audio instrument {index}", {
        "id", "wave", "attack", "release",
    }) for index, item in enumerate(_array(document["instruments"], "audio instruments", 1, 16))]
    instrument_ids = _unique(instruments, "audio instrument")
    for index, instrument in enumerate(instruments):
        wave = _array(instrument["wave"], f"audio instrument {index} wave", 16, 16)
        for sample_index, sample in enumerate(wave):
            _integer(sample, f"audio instrument {index} wave {sample_index}", 0, 15)
        _integer(instrument["attack"], f"audio instrument {index} attack", 0, 255)
        _integer(instrument["release"], f"audio instrument {index} release", 0, 255)
    rows = [_object(item, f"audio row {index}", {"id", "channels"})
            for index, item in enumerate(_array(document["rows"], "audio rows", 1, 65535))]
    _unique(rows, "audio row")
    for row_index, row in enumerate(rows):
        channels = _array(row["channels"], f"audio row {row_index} channels", 4, 4)
        for channel_index, raw_command in enumerate(channels):
            command = _object(raw_command, f"audio row {row_index} channel {channel_index}", {
                "note", "instrument", "volume",
            })
            note = command["note"]
            if isinstance(note, str):
                if note not in {"hold", "off"}:
                    raise AuthoringError("audio command note must be 0..127, hold, or off")
            else:
                _integer(note, "audio command note", 0, 127)
            instrument = command["instrument"]
            if (not isinstance(instrument, str) or
                    (instrument != "hold" and instrument not in instrument_ids)):
                raise AuthoringError(f"audio command references unknown instrument {instrument!r}")
            volume = command["volume"]
            if isinstance(volume, str):
                if volume != "hold":
                    raise AuthoringError("audio command volume must be 0..15 or hold")
            else:
                _integer(volume, "audio command volume", 0, 15)
    return document


_VALIDATORS: dict[str, Callable[[object], dict[str, Any]]] = {
    "tilemap": _validate_tilemap,
    "sprites": _validate_sprites,
    "palette": _validate_palette,
    "collision": _validate_collision,
    "scene-flow": _validate_scene_flow,
    "audio": _validate_audio,
}


def document_kind(value: object) -> str:
    if not isinstance(value, Mapping):
        raise AuthoringError("authoring document must be an object")
    schema = value.get("schema")
    for kind, expected in SCHEMAS.items():
        if schema == expected:
            return kind
    raise AuthoringError(f"unknown authoring document schema {schema!r}")


def validate_document(value: object) -> dict[str, Any]:
    kind = document_kind(value)
    return _VALIDATORS[kind](value)


def default_document(kind: str, identifier: str) -> dict[str, Any]:
    if kind not in KINDS:
        raise AuthoringError(f"unknown authoring kind {kind!r}")
    _identifier(identifier, "authoring document id")
    hold = {"note": "hold", "instrument": "hold", "volume": "hold"}
    documents: dict[str, dict[str, Any]] = {
        "tilemap": {
            "schema": SCHEMAS["tilemap"], "id": identifier, "tileSize": 8,
            "width": 28, "height": 18, "tilesetSource": "assets/art/tiles.png",
            "layers": [{
                "id": "background", "visible": True, "scrollX": 0, "scrollY": 0,
                "cells": [],
            }],
        },
        "sprites": {
            "schema": SCHEMAS["sprites"], "id": identifier,
            "source": "assets/art/sprites.png",
            "frames": [{
                "id": "idle-0", "x": 0, "y": 0, "width": 8, "height": 8,
                "originX": 4, "originY": 7,
            }],
            "animations": [{
                "id": "idle", "loop": True,
                "steps": [{
                    "frame": "idle-0", "durationFrames": 8,
                    "flipX": False, "flipY": False,
                }],
            }],
            "hitboxes": [{
                "id": "body", "frame": "idle-0", "kind": "hurt",
                "x": -3, "y": -7, "width": 6, "height": 7,
            }],
        },
        "palette": {
            "schema": SCHEMAS["palette"], "id": identifier,
            "colors": ["#101820", "#3B6472", "#8FB9A8", "#F7E7B2"],
            "monoMapping": [0, 1, 2, 3], "transparentIndex": None,
        },
        "collision": {
            "schema": SCHEMAS["collision"], "id": identifier,
            "width": 224, "height": 144, "regions": [],
            "paths": [{
                "id": "main-path", "loop": False,
                "points": [{"x": 112, "y": 72, "waitFrames": 0}],
            }],
        },
        "scene-flow": {
            "schema": SCHEMAS["scene-flow"], "id": identifier,
            "initialScene": "title",
            "scenes": [{"id": "title", "title": "Title"}],
            "transitions": [],
        },
        "audio": {
            "schema": SCHEMAS["audio"], "id": identifier,
            "framesPerRowQ8": 1536, "loop": True,
            "instruments": [{
                "id": "lead", "wave": [0, 1, 3, 6, 10, 13, 15, 13, 10, 6, 3, 1, 0, 1, 0, 1],
                "attack": 1, "release": 4,
            }],
            "rows": [{
                "id": "row-000", "channels": [
                    {"note": 36, "instrument": "lead", "volume": 8},
                    dict(hold), dict(hold), dict(hold),
                ],
            }],
        },
    }
    return validate_document(documents[kind])


def _scene_findings(document: Mapping[str, Any]) -> list[dict[str, str]]:
    reachable = {document["initialScene"]}
    changed = True
    while changed:
        changed = False
        for transition in document["transitions"]:
            if transition["from"] in reachable and transition["to"] not in reachable:
                reachable.add(transition["to"])
                changed = True
    return [{
        "severity": "warning", "code": "unreachable-scene",
        "message": f"scene {scene['id']} is not reachable from {document['initialScene']}",
    } for scene in document["scenes"] if scene["id"] not in reachable]


def document_report(value: object) -> dict[str, Any]:
    document = validate_document(value)
    kind = document_kind(document)
    findings: list[dict[str, str]] = []
    if kind == "tilemap":
        cells = [cell for layer in document["layers"] for cell in layer["cells"]]
        metrics = {
            "widthTiles": document["width"], "heightTiles": document["height"],
            "layerCount": len(document["layers"]), "placedCells": len(cells),
            "highestTile": max((cell["tile"] for cell in cells), default=None),
            "palettesReferenced": len({cell["palette"] for cell in cells}),
        }
    elif kind == "sprites":
        metrics = {
            "frameCount": len(document["frames"]),
            "animationCount": len(document["animations"]),
            "animationSteps": sum(len(item["steps"]) for item in document["animations"]),
            "animationDurationFrames": sum(
                step["durationFrames"] for item in document["animations"] for step in item["steps"]
            ),
            "hitboxCount": len(document["hitboxes"]),
        }
    elif kind == "palette":
        metrics = {
            "colorCount": len(document["colors"]),
            "paletteBankCount": (len(document["colors"]) + 3) // 4,
            "monoShadesUsed": len(set(document["monoMapping"])),
            "transparentIndex": document["transparentIndex"],
        }
        if len(document["colors"]) % 4:
            findings.append({
                "severity": "warning", "code": "partial-palette-bank",
                "message": "the final 2BPP palette bank has fewer than four colors",
            })
    elif kind == "collision":
        metrics = {
            "widthPixels": document["width"], "heightPixels": document["height"],
            "regionCount": len(document["regions"]), "pathCount": len(document["paths"]),
            "regionPoints": sum(len(item["points"]) for item in document["regions"]),
            "pathPoints": sum(len(item["points"]) for item in document["paths"]),
        }
    elif kind == "scene-flow":
        metrics = {
            "sceneCount": len(document["scenes"]),
            "transitionCount": len(document["transitions"]),
            "initialScene": document["initialScene"],
        }
        findings = _scene_findings(document)
    else:
        metrics = {
            "instrumentCount": len(document["instruments"]),
            "rowCount": len(document["rows"]),
            "channelCommands": len(document["rows"]) * 4,
            "durationFramesQ8": len(document["rows"]) * document["framesPerRowQ8"],
        }
    return {"kind": kind, "metrics": metrics, "findings": findings}


def _audio_toml(document: Mapping[str, Any]) -> str:
    instrument_indices = {
        instrument["id"]: index for index, instrument in enumerate(document["instruments"])
    }
    lines = [
        'type = "music"',
        f"frames_per_row_q8 = {document['framesPerRowQ8']}",
        f"loop = {'true' if document['loop'] else 'false'}",
        "",
    ]
    for instrument in document["instruments"]:
        lines.extend((
            "[[instruments]]",
            "wave = [" + ", ".join(str(value) for value in instrument["wave"]) + "]",
            f"attack = {instrument['attack']}",
            f"release = {instrument['release']}",
            "",
        ))
    for row in document["rows"]:
        channels: list[str] = []
        for command in row["channels"]:
            note = {"hold": 254, "off": 255}.get(command["note"], command["note"])
            instrument = (
                254 if command["instrument"] == "hold"
                else instrument_indices[command["instrument"]]
            )
            volume = 254 if command["volume"] == "hold" else command["volume"]
            channels.append(f"[{note}, {instrument}, {volume}]")
        lines.extend(("[[rows]]", "channels = [" + ", ".join(channels) + "]", ""))
    return "\n".join(lines)


def _palette_png(document: Mapping[str, Any]) -> bytes:
    colors = [tuple(int(color[offset:offset + 2], 16) for offset in (1, 3, 5)) + (255,)
              for color in document["colors"]]
    pixels = tuple(color for _y in range(8) for color in colors for _x in range(8))
    return encode_rgba_png(Image(len(colors) * 8, 8, pixels))


def export_document(value: object) -> tuple[bytes, dict[str, Any]]:
    document = validate_document(value)
    kind = document_kind(document)
    if kind == "audio":
        payload = _audio_toml(document).encode("utf-8")
        media_type = "application/toml"
        suffix = ".toml"
        integration = {"status": "sdk-consumable", "manifestAssetType": "music"}
    elif kind == "palette":
        payload = _palette_png(document)
        media_type = "image/png"
        suffix = ".png"
        integration = {
            "status": "sdk-consumable-preview",
            "manifestAssetTypes": ["fullscreen", "tilemap", "spritesheet", "metatiles", "font"],
            "note": "The PNG is a swatch source; monoMapping remains in the authoring document.",
        }
    else:
        if kind == "tilemap":
            integration = {
                "status": "handoff-required", "manifestAssetType": "tilemap",
                "sourceImage": document["tilesetSource"],
            }
        elif kind == "sprites":
            integration = {
                "status": "handoff-required", "manifestAssetType": "spritesheet",
                "sourceImage": document["source"],
            }
        elif kind == "collision":
            integration = {"status": "handoff-required", "consumer": "portable-game-model"}
        else:
            integration = {"status": "handoff-required", "consumer": "static-scene-dispatch"}
        handoff = {
            "schema": HANDOFF_SCHEMA,
            "kind": kind,
            "sourceSchema": document["schema"],
            "sourceSHA256": canonical_digest(document),
            "gameplayEvidence": False,
            "integration": integration,
            "document": document,
        }
        payload = canonical_json(handoff).encode("utf-8")
        media_type = "application/json"
        suffix = ".json"
    return payload, {
        "mediaType": media_type,
        "requiredSuffix": suffix,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
        "integration": integration,
    }


def operation_report(operation: str, document: Mapping[str, Any], *,
                     project: str, document_path: Path,
                     output_path: Path | None = None,
                     export: Mapping[str, Any] | None = None) -> dict[str, Any]:
    analysis = document_report(document)
    report = {
        "schema": REPORT_SCHEMA,
        "ok": True,
        "operation": operation,
        "project": project,
        "kind": analysis["kind"],
        "document": str(document_path),
        "documentSchema": document["schema"],
        "documentSHA256": canonical_digest(document),
        "metrics": analysis["metrics"],
        "findings": analysis["findings"],
        "output": str(output_path) if output_path is not None else None,
        "export": dict(export) if export is not None else None,
        "gameplayEvidence": False,
        "notice": "Authoring documents, previews, and exports are not gameplay evidence.",
    }
    return report
