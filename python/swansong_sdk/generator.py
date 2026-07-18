"""Deterministic project and asset generation."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tomllib
from typing import Iterable

from .manifest import Asset, Manifest
from .plans import PlanError, load_plan
from .png2bpp import PNGError, Tileset, convert_2bpp, read_png


GRAPHIC_TYPES = {"fullscreen", "tilemap", "spritesheet", "metatiles", "font"}
SAVE_TYPES = {
    "none": "NONE",
    "eeprom-128b": "EEPROM_128B",
    "eeprom-1kb": "EEPROM_1KB",
    "eeprom-2kb": "EEPROM_2KB",
    "sram-8kb": "SRAM_8KB",
    "sram-32kb": "SRAM_32KB",
    "sram-128kb": "SRAM_128KB",
    "sram-256kb": "SRAM_256KB",
    "sram-512kb": "SRAM_512KB",
}
INPUT_BITS = {
    "X1": "SWAN_KEY_X1", "X2": "SWAN_KEY_X2", "X3": "SWAN_KEY_X3", "X4": "SWAN_KEY_X4",
    "Y1": "SWAN_KEY_Y1", "Y2": "SWAN_KEY_Y2", "Y3": "SWAN_KEY_Y3", "Y4": "SWAN_KEY_Y4",
    "A": "SWAN_KEY_A", "B": "SWAN_KEY_B", "START": "SWAN_KEY_START",
}


class GenerationError(RuntimeError):
    pass


@dataclass(frozen=True)
class CompiledAsset:
    asset: Asset
    sha256: str
    source_bytes: int
    tileset: Tileset | None
    audio: dict[str, object] | None = None
    wonderful_tile_bytes: int | None = None
    wonderful_palette_bytes: int | None = None
    wonderful_map_bytes: int | None = None

    @property
    def tile_bytes(self) -> int:
        if self.wonderful_tile_bytes is not None:
            return self.wonderful_tile_bytes
        return sum(len(tile) for tile in self.tileset.tiles) if self.tileset else 0

    @property
    def tile_count(self) -> int:
        return self.tile_bytes // 16 if self.tileset else 0

    @property
    def palette_count(self) -> int:
        if not self.tileset:
            return 0
        if self.wonderful_palette_bytes is not None:
            return max(1, self.wonderful_palette_bytes // 8)
        return 1


def c_name(value: str) -> str:
    return value.upper().replace("-", "_")


def c_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def _write(path: Path, text: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = text.encode("utf-8") if isinstance(text, str) else text
    if path.is_file() and path.read_bytes() == payload:
        return
    path.write_bytes(payload)


def _format_bytes(values: Iterable[int], *, columns: int = 12) -> str:
    items = [f"0x{value:02X}" for value in values]
    return "\n".join("    " + ", ".join(items[index:index + columns]) + "," for index in range(0, len(items), columns))


def _format_words(values: Iterable[int], *, columns: int = 8) -> str:
    items = [f"0x{value:04X}" for value in values]
    return "\n".join("    " + ", ".join(items[index:index + columns]) + "," for index in range(0, len(items), columns))


def _audio_command(value: object, context: str) -> tuple[int, int, int]:
    if not isinstance(value, list) or len(value) != 3 or not all(isinstance(item, int) and not isinstance(item, bool) for item in value):
        raise GenerationError(f"{context} must be [note, instrument, volume]")
    note, instrument, volume = value
    if note not in range(128) and note not in (254, 255):
        raise GenerationError(f"{context} note must be 0..127, 254 (unchanged), or 255 (off)")
    if instrument not in range(16) and instrument != 254:
        raise GenerationError(f"{context} instrument must be 0..15 or 254 (unchanged)")
    if volume not in range(16) and volume != 254:
        raise GenerationError(f"{context} volume must be 0..15 or 254 (unchanged)")
    return note, instrument, volume


def _compile_audio(asset: Asset, source: Path) -> dict[str, object]:
    try:
        with source.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise GenerationError(f"invalid audio TOML for {asset.id}: {exc}") from exc
    declared = data.get("type", asset.type)
    if declared != asset.type:
        raise GenerationError(f"audio {asset.id} declares type {declared!r}, expected {asset.type!r}")
    if asset.type == "music":
        instruments = data.get("instruments", [])
        rows = data.get("rows", [])
        if not isinstance(instruments, list) or not 1 <= len(instruments) <= 16:
            raise GenerationError(f"music {asset.id} requires 1..16 [[instruments]]")
        parsed_instruments = []
        for index, instrument in enumerate(instruments):
            if not isinstance(instrument, dict):
                raise GenerationError(f"music {asset.id} instrument {index} must be a table")
            wave = instrument.get("wave")
            if not isinstance(wave, list) or len(wave) != 16 or not all(isinstance(item, int) and 0 <= item <= 15 for item in wave):
                raise GenerationError(f"music {asset.id} instrument {index} wave must contain 16 samples in 0..15")
            attack, release = instrument.get("attack", 0), instrument.get("release", 0)
            if not all(isinstance(item, int) and 0 <= item <= 255 for item in (attack, release)):
                raise GenerationError(f"music {asset.id} instrument {index} attack/release must be bytes")
            parsed_instruments.append((tuple(wave), attack, release))
        if not isinstance(rows, list) or not rows:
            raise GenerationError(f"music {asset.id} requires at least one [[rows]]")
        parsed_rows = []
        for row_index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise GenerationError(f"music {asset.id} row {row_index} must be a table")
            channels = row.get("channels")
            if not isinstance(channels, list) or len(channels) != 4:
                raise GenerationError(f"music {asset.id} row {row_index} requires four channels")
            parsed_rows.append(tuple(_audio_command(command, f"music {asset.id} row {row_index} channel {channel}") for channel, command in enumerate(channels)))
        frames = data.get("frames_per_row_q8", 1536)
        loop = data.get("loop", True)
        if not isinstance(frames, int) or isinstance(frames, bool) or not 1 <= frames <= 65535:
            raise GenerationError(f"music {asset.id} frames_per_row_q8 must be 1..65535")
        if not isinstance(loop, bool):
            raise GenerationError(f"music {asset.id} loop must be true or false")
        return {"type": "music", "instruments": tuple(parsed_instruments), "rows": tuple(parsed_rows), "frames": frames, "loop": loop}
    steps = data.get("steps", [])
    priority = data.get("priority", 0)
    if not isinstance(priority, int) or isinstance(priority, bool) or not 0 <= priority <= 255:
        raise GenerationError(f"sfx {asset.id} priority must be a byte")
    if not isinstance(steps, list) or not 1 <= len(steps) <= 255:
        raise GenerationError(f"sfx {asset.id} requires 1..255 [[steps]]")
    parsed_steps = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise GenerationError(f"sfx {asset.id} step {index} must be a table")
        duration = step.get("duration_frames")
        if not isinstance(duration, int) or isinstance(duration, bool) or not 1 <= duration <= 255:
            raise GenerationError(f"sfx {asset.id} step {index} duration_frames must be 1..255")
        parsed_steps.append((_audio_command(step.get("command"), f"sfx {asset.id} step {index}"), duration))
    return {"type": "sfx", "priority": priority, "steps": tuple(parsed_steps)}


def compile_assets(manifest: Manifest) -> tuple[CompiledAsset, ...]:
    compiled: list[CompiledAsset] = []
    for asset in manifest.assets:
        source = (manifest.root / asset.source).resolve()
        try:
            source.relative_to(manifest.root)
        except ValueError as exc:
            raise GenerationError(f"asset {asset.id} points outside the project: {asset.source}") from exc
        if not source.is_file():
            raise GenerationError(f"asset {asset.id} source does not exist: {asset.source}")
        payload = source.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        tileset: Tileset | None = None
        if asset.type in GRAPHIC_TYPES:
            if source.suffix.lower() != ".png":
                raise GenerationError(f"graphic asset {asset.id} must be a PNG")
            try:
                tileset = convert_2bpp(read_png(source), flip_dedupe=asset.flip_dedupe)
            except PNGError as exc:
                raise GenerationError(f"could not compile {asset.id}: {exc}") from exc
        audio = None
        if asset.type in {"music", "sfx"}:
            if source.suffix.lower() != ".toml":
                raise GenerationError(f"audio asset {asset.id} must be a TOML pattern file")
            audio = _compile_audio(asset, source)
        compiled.append(CompiledAsset(asset, digest, len(payload), tileset, audio))
    return tuple(compiled)


def _wfconfig(manifest: Manifest, *, color: bool = True) -> str:
    return "\n".join((
        "# Generated by swan assets. Do not edit.",
        "[cartridge]",
        f"publisher_id = 0x{manifest.publisher_id:02X}",
        f"game_id = {manifest.game_id}",
        f"game_version = {manifest.cartridge_version}",
        f'save_type = "{SAVE_TYPES[manifest.save_type]}"',
        f"color = {'true' if color else 'false'}",
        f"rtc = {'true' if manifest.rtc else 'false'}",
        f"vertical = {'true' if manifest.orientation == 'vertical' else 'false'}",
        "",
    ))


def _project_header(manifest: Manifest) -> str:
    lines = [
        "#ifndef SWAN_GENERATED_PROJECT_H", "#define SWAN_GENERATED_PROJECT_H", "",
        "#include <stdint.h>", "",
        f"#define SWAN_PROJECT_ID {c_string(manifest.id)}",
        f"#define SWAN_PROJECT_TITLE {c_string(manifest.title)}",
        f"#define SWAN_PROJECT_VERSION {c_string(manifest.version)}",
        f"#define SWAN_PROJECT_COLOR_REQUIRED {1 if manifest.hardware == 'color-required' else 0}",
        f"#define SWAN_PROJECT_VERTICAL {1 if manifest.orientation == 'vertical' else 0}",
        f"#define SWAN_PROJECT_HAS_RTC {1 if manifest.rtc else 0}", "",
        "enum swan_generated_scene_id {",
    ]
    lines.extend(f"    SWAN_SCENE_{c_name(scene.id)} = {index}," for index, scene in enumerate(manifest.scenes))
    lines.extend(("};", f"#define SWAN_INITIAL_SCENE SWAN_SCENE_{c_name(manifest.initial_scene)}", "", "#endif", ""))
    return "\n".join(lines)


def _controls_header(manifest: Manifest) -> str:
    horizontal = {
        "UP": "SWAN_KEY_X3", "RIGHT": "SWAN_KEY_X2",
        "DOWN": "SWAN_KEY_X1", "LEFT": "SWAN_KEY_X4",
    }
    vertical = {
        "UP": "SWAN_KEY_Y2", "RIGHT": "SWAN_KEY_Y3",
        "DOWN": "SWAN_KEY_Y4", "LEFT": "SWAN_KEY_Y1",
    }
    primary = vertical if manifest.orientation == "vertical" else horizontal
    secondary = horizontal if manifest.orientation == "vertical" else vertical
    lines = [
        "#ifndef SWAN_GENERATED_CONTROLS_H", "#define SWAN_GENERATED_CONTROLS_H", "",
        "#include <swan/input.h>", "", "enum swan_generated_action_id {",
    ]
    lines.extend(f"    SWAN_ACTION_{c_name(action)} = {index}," for index, action in enumerate(manifest.controls))
    lines.extend((f"    SWAN_ACTION_COUNT = {len(manifest.controls)}", "};", ""))
    lines.append("enum swan_generated_chord_id {")
    lines.extend(
        f"    SWAN_CHORD_{c_name(chord)} = {index},"
        for index, chord in enumerate(manifest.input_chords)
    )
    lines.extend((f"    SWAN_CHORD_COUNT = {len(manifest.input_chords)}", "};", ""))
    for action, inputs in manifest.controls.items():
        expression = " | ".join(INPUT_BITS[item] for item in inputs)
        lines.append(f"#define SWAN_ACTION_BINDING_{c_name(action)} ({expression})")
    lines.append("")
    for direction in ("UP", "RIGHT", "DOWN", "LEFT"):
        lines.append(f"#define SWAN_PRIMARY_{direction} ({primary[direction]})")
        lines.append(f"#define SWAN_SECONDARY_{direction} ({secondary[direction]})")
    lines.extend(("", "#endif", ""))
    return "\n".join(lines)


def _assets_header(compiled: tuple[CompiledAsset, ...]) -> str:
    lines = [
        "#ifndef SWAN_GENERATED_ASSETS_H", "#define SWAN_GENERATED_ASSETS_H", "",
        "#include <stdint.h>", "#include <swan/audio.h>", "#include <swan/types.h>", "", "enum swan_generated_asset_id {",
    ]
    if compiled:
        lines.extend(f"    SWAN_ASSET_{c_name(item.asset.id)} = {index}," for index, item in enumerate(compiled))
    lines.extend((f"    SWAN_ASSET_COUNT = {len(compiled)}", "};", ""))
    for item in compiled:
        if item.tileset:
            name = item.asset.id
            lines.extend((
                f"extern const uint8_t SWAN_FAR swan_asset_{name}_tiles[{item.tile_bytes}];",
                f"extern const uint16_t SWAN_FAR swan_asset_{name}_map[{len(item.tileset.tilemap)}];",
                f"extern const uint16_t SWAN_FAR swan_asset_{name}_palette[4];",
                f"#define SWAN_ASSET_{c_name(name)}_WIDTH_TILES {item.tileset.width_tiles}",
                f"#define SWAN_ASSET_{c_name(name)}_HEIGHT_TILES {item.tileset.height_tiles}",
                f"#define SWAN_ASSET_{c_name(name)}_TILE_COUNT {item.tile_count}", "",
            ))
        elif item.audio and item.audio["type"] == "music":
            name = item.asset.id
            instruments = item.audio["instruments"]
            rows = item.audio["rows"]
            lines.extend((
                f"extern const swan_instrument_t SWAN_FAR swan_asset_{name}_instruments[{len(instruments)}];",
                f"extern const swan_audio_row_t SWAN_FAR swan_asset_{name}_rows[{len(rows)}];",
                f"extern const swan_song_t SWAN_FAR swan_asset_{name}_song;",
                f"#define SWAN_ASSET_{c_name(name)}_INSTRUMENT_COUNT {len(instruments)}", "",
            ))
        elif item.audio:
            name = item.asset.id
            steps = item.audio["steps"]
            lines.extend((
                f"extern const swan_sfx_step_t SWAN_FAR swan_asset_{name}_steps[{len(steps)}];",
                f"extern const swan_sfx_t SWAN_FAR swan_asset_{name}_sfx;", "",
            ))
    lines.extend(("#endif", ""))
    return "\n".join(lines)


def _assets_source(compiled: tuple[CompiledAsset, ...]) -> str:
    lines = ["#include \"swan_assets.h\"", ""]
    for item in compiled:
        if not item.audio:
            continue
        name = item.asset.id
        if item.audio["type"] == "music":
            instruments = item.audio["instruments"]
            rows = item.audio["rows"]
            lines.append(f"const swan_instrument_t SWAN_FAR swan_asset_{name}_instruments[{len(instruments)}] = {{")
            for wave, attack, release in instruments:
                lines.append("    {{" + ", ".join(str(sample) for sample in wave) + f"}}, {attack}, {release}}},")
            lines.extend(("};", "", f"const swan_audio_row_t SWAN_FAR swan_asset_{name}_rows[{len(rows)}] = {{"))
            for row in rows:
                commands = ", ".join("{%d, %d, %d}" % command for command in row)
                lines.append(f"    {{{{{commands}}}}},")
            lines.extend((
                "};", "", f"const swan_song_t SWAN_FAR swan_asset_{name}_song = {{",
                f"    swan_asset_{name}_rows, {len(rows)}, {item.audio['frames']}, {'true' if item.audio['loop'] else 'false'}",
                "};", "",
            ))
        else:
            steps = item.audio["steps"]
            lines.append(f"const swan_sfx_step_t SWAN_FAR swan_asset_{name}_steps[{len(steps)}] = {{")
            for command, duration in steps:
                lines.append("    {{%d, %d, %d}, %d}," % (*command, duration))
            lines.extend((
                "};", "", f"const swan_sfx_t SWAN_FAR swan_asset_{name}_sfx = {{",
                f"    swan_asset_{name}_steps, {len(steps)}, {item.audio['priority']}",
                "};", "",
            ))
    return "\n".join(lines)


def _wonderful_process() -> Path:
    root = Path(os.environ.get("WONDERFUL_TOOLCHAIN", "/opt/wonderful"))
    candidate = root / "bin" / "wf-process"
    if candidate.is_file():
        return candidate
    located = shutil.which("wf-process")
    if located:
        return Path(located)
    raise GenerationError(
        "Wonderful wf-process is required for graphic assets; install the pinned "
        "wf-tools and wf-superfamiconv packages"
    )


def _compile_graphics_with_wonderful(
    manifest: Manifest, compiled: tuple[CompiledAsset, ...], generated: Path
) -> tuple[CompiledAsset, ...]:
    graphics = [item for item in compiled if item.tileset]
    source_dir = generated / "src"
    source_dir.mkdir(parents=True, exist_ok=True)
    for stale in source_dir.glob("swan_asset_*_wonderful.c"):
        stale.unlink()
    if not graphics:
        return compiled
    process = _wonderful_process()
    result: list[CompiledAsset] = []
    for item in compiled:
        if not item.tileset:
            result.append(item)
            continue
        asset = item.asset
        script = generated / "wonderful" / f"{asset.id}.lua"
        process_input = generated / "wonderful" / f"{asset.id}.png"
        output = source_dir / f"swan_asset_{asset.id}_wonderful.c"
        no_flip = ":no_flip()" if not asset.flip_dedupe else ""
        _write(script, "\n".join((
            'local process = require("wf.api.v1.process")',
            'local superfamiconv = require("wf.api.v1.process.tools.superfamiconv")',
            'local files = process.inputs(".png")',
            'local file = nil',
            'for _, candidate in pairs(files) do',
            '    if file ~= nil then error("SwanSong expects exactly one PNG input") end',
            '    file = candidate',
            'end',
            'if file == nil then error("SwanSong expects exactly one PNG input") end',
            'local config = superfamiconv.config():mode("wsc"):bpp(2):tile_base(0):palette_base(0)' + no_flip,
            f'process.emit_symbol("swan_asset_{asset.id}", superfamiconv.convert_tilemap(file, config))',
            "",
        )))
        source = (manifest.root / asset.source).resolve()
        _write(process_input, source.read_bytes())
        try:
            subprocess.run(
                [str(process), "-o", str(output), "-t", "wswan/medium", str(script)],
                check=True, capture_output=True, text=True,
            )
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout).strip()
            raise GenerationError(f"Wonderful could not convert {asset.id}: {detail}") from exc
        text = output.read_text()
        text = re.sub(
            r"^// autogenerated by wf-process on .*?$",
            "// generated by SwanSong SDK through Wonderful wf-process",
            text,
            count=1,
            flags=re.MULTILINE,
        )
        block_pattern = re.compile(
            r"^const uint8_t __wf_rom swan_asset_[A-Za-z0-9_]+_"
            r"(?:map|palette|tiles)\[\d+\] __attribute__\(\(aligned\(2\)\)\) = \{\n"
            r".*?^\};\n",
            flags=re.MULTILINE | re.DOTALL,
        )
        blocks = list(block_pattern.finditer(text))
        if len(blocks) == 3:
            prefix = text[:blocks[0].start()]
            suffix = text[blocks[-1].end():]
            text = prefix + "".join(sorted((match.group(0) for match in blocks))) + suffix
        _write(output, text)
        sizes = {}
        for suffix in ("tiles", "palette", "map"):
            match = re.search(
                rf"swan_asset_{re.escape(asset.id)}_{suffix}\[(\d+)\]", text
            )
            if not match:
                raise GenerationError(
                    f"Wonderful output for {asset.id} is missing the {suffix} symbol"
                )
            sizes[suffix] = int(match.group(1))
        if sizes["tiles"] % 16 != 0 or sizes["palette"] % 8 != 0 or sizes["map"] % 2 != 0:
            raise GenerationError(f"Wonderful returned invalid 2BPP data sizes for {asset.id}")
        result.append(replace(
            item,
            wonderful_tile_bytes=sizes["tiles"],
            wonderful_palette_bytes=sizes["palette"],
            wonderful_map_bytes=sizes["map"],
        ))
    return tuple(result)


def _config_source(manifest: Manifest) -> str:
    capabilities = "SWAN_HARDWARE_COLOR"
    if manifest.hardware == "mono-compatible":
        capabilities = "SWAN_HARDWARE_MONO | SWAN_HARDWARE_COLOR"
    if manifest.rtc:
        capabilities += " | SWAN_HARDWARE_RTC"
    action_lines = []
    for index, inputs in enumerate(manifest.controls.values()):
        action_lines.append(f"            [{index}] = " + " | ".join(INPUT_BITS[item] for item in inputs) + ",")
    chord_lines = []
    for index, actions in enumerate(manifest.input_chords.values()):
        expression = " | ".join(
            f"(1u << SWAN_ACTION_{c_name(action)})" for action in actions
        )
        chord_lines.append(f"            [{index}] = {expression},")
    return "\n".join((
        "/* Generated project configuration. The SDK owns the platform entry point. */",
        "#include <swan/swan.h>", "#include \"swan_project.h\"",
        "#include \"swan_controls.h\"", "",
        "const swan_build_identity_t swan_game_build_identity = {",
        "    SWAN_VERSION_STRING, SWAN_MANIFEST_SCHEMA_VERSION,",
        "    SWAN_PROJECT_ID, SWAN_PROJECT_VERSION",
        "};", "",
        "const swan_core_config_t swan_game_config = {",
        "    .initial_scene = SWAN_INITIAL_SCENE,",
        "    .initial_argument = 0,",
        f"    .capabilities = {capabilities},",
        f"    .vertical = {1 if manifest.orientation == 'vertical' else 0},",
        "    .input = {",
        "        .keys = {",
        *action_lines,
        "        },",
        "        .repeat_delay = 20,",
        "        .repeat_period = 5,",
        "        .chord_actions = {",
        *chord_lines,
        "        },",
        f"        .tap_max_frames = {manifest.input_gestures.tap_max_frames},",
        f"        .double_tap_window = {manifest.input_gestures.double_tap_window},",
        f"        .hold_threshold = {manifest.input_gestures.hold_threshold},",
        "    },",
        "};", "",
    ))


def _resource_header(manifest: Manifest, compiled: tuple[CompiledAsset, ...]) -> str:
    graphic_assets = {item.asset.id: item for item in compiled if item.tileset}
    common_tiles = manifest.resources.vram_tiles + sum(item.tile_count for item in compiled if item.tileset and item.asset.group == "common")
    scene_tiles = {
        scene.id: common_tiles + sum(graphic_assets[name].tile_count for name in scene.assets if name in graphic_assets and graphic_assets[name].asset.group != "common")
        for scene in manifest.scenes
    }
    peak_tiles = max(scene_tiles.values(), default=common_tiles)
    return "\n".join((
        "#ifndef SWAN_GENERATED_RESOURCES_H", "#define SWAN_GENERATED_RESOURCES_H", "",
        f"#define SWAN_RESERVED_WORK_RAM_BYTES {manifest.resources.work_ram_bytes}",
        f"#define SWAN_RESERVED_VRAM_TILES {peak_tiles}",
        f"#define SWAN_RESERVED_PALETTES {manifest.resources.palettes}",
        f"#define SWAN_RESERVED_SPRITES {manifest.resources.sprites}",
        f"#define SWAN_RESERVED_SPRITES_PER_SCANLINE {manifest.resources.sprites_per_scanline}",
        f"#define SWAN_BUDGET_WORK_RAM_BYTES {manifest.budgets.work_ram_bytes}",
        f"#define SWAN_BUDGET_VRAM_TILES {manifest.budgets.vram_tiles}",
        f"#define SWAN_BUDGET_PALETTES {manifest.budgets.palettes}",
        f"#define SWAN_BUDGET_SPRITES {manifest.budgets.sprites}",
        "", "#endif", "",
    ))


def _controls_markdown(manifest: Manifest) -> str:
    lines = [f"# {manifest.title} controls", "", "This file is generated from `swan.toml`.", "", "| Action | Physical inputs |", "|---|---|"]
    lines.extend(f"| `{action}` | {' + '.join(inputs)} |" for action, inputs in manifest.controls.items())
    lines.extend((
        "", "## Gesture timing", "",
        f"- Tap: release within {manifest.input_gestures.tap_max_frames} sampled frames.",
        f"- Double tap: complete the second tap within {manifest.input_gestures.double_tap_window} sampled frames.",
        f"- Hold: begins on sampled frame {manifest.input_gestures.hold_threshold}.",
    ))
    if manifest.input_chords:
        lines.extend(("", "## Same-frame chords", "", "| Chord | Actions |", "|---|---|"))
        lines.extend(
            f"| `{chord}` | {' + '.join(actions)} |"
            for chord, actions in manifest.input_chords.items()
        )
    lines.append("")
    return "\n".join(lines)


def _play_contract(manifest: Manifest) -> dict[str, object]:
    return {
        "schema": "swan-song-game-contract-v1",
        "game": {"id": manifest.id, "title": manifest.title, "rom": manifest.rom_name},
        "readyFrames": manifest.play_ready_frames,
        "controls": {key: list(value) for key, value in manifest.controls.items()},
        "inputGestures": {
            "tapMaxFrames": manifest.input_gestures.tap_max_frames,
            "doubleTapWindow": manifest.input_gestures.double_tap_window,
            "holdThreshold": manifest.input_gestures.hold_threshold,
            "chords": {
                key: list(value) for key, value in manifest.input_chords.items()
            },
            "sameFrameChords": True,
        },
        "scenarios": [
            {
                "id": scenario.id,
                "title": scenario.title,
                "goal": scenario.goal,
                "plan": scenario.plan,
                "requiredChecks": list(scenario.required_checks),
                "requiresAudioEvidence": scenario.audio,
                "audioExpectation": scenario.audio_expectation,
                **(
                    {"audioEvidence": scenario.audio_evidence.to_contract()}
                    if scenario.audio_evidence.configured else {}
                ),
                "freshBoot": True,
                "requiresMediaInspection": True,
            }
            for scenario in manifest.play_scenarios
        ],
    }


def asset_report(manifest: Manifest, compiled: tuple[CompiledAsset, ...]) -> dict[str, object]:
    graphics = [item for item in compiled if item.tileset]
    audio = [item for item in compiled if item.asset.type in {"music", "sfx"}]
    common = [item for item in graphics if item.asset.group == "common"]
    common_tiles = manifest.resources.vram_tiles + sum(item.tile_count for item in common)
    common_palettes = manifest.resources.palettes + sum(item.palette_count for item in common)
    scene_usage: list[dict[str, int | str]] = []
    for scene in manifest.scenes:
        referenced = [item for item in graphics if item.asset.id in scene.assets and item.asset.group != "common"]
        scene_usage.append({
            "scene": scene.id,
            "vramTiles": common_tiles + sum(item.tile_count for item in referenced),
            "palettes": common_palettes + sum(item.palette_count for item in referenced),
        })
    return {
        "schema": "swansong-resource-report-v1",
        "project": manifest.id,
        "sourceAssetBytes": sum(item.source_bytes for item in compiled),
        "generatedTileBytes": sum(item.tile_bytes for item in graphics),
        "audioBytes": sum(item.source_bytes for item in audio),
        "uniqueTiles": sum(item.tile_count for item in graphics),
        "sceneUsage": scene_usage,
        "reserved": manifest.resources.__dict__,
        "budgets": manifest.budgets.__dict__,
        "assets": [
            {
                "id": item.asset.id, "type": item.asset.type, "source": item.asset.source,
                "sha256": item.sha256, "sourceBytes": item.source_bytes,
                "tileBytes": item.tile_bytes, "uniqueTiles": item.tile_count,
                "converter": (
                    "wonderful-superfamiconv" if item.tileset else
                    "swansong-toml-audio" if item.audio else "swansong-static"
                ),
            }
            for item in compiled
        ],
    }


def validate_budgets(manifest: Manifest, report: dict[str, object], *, rom_path: Path | None = None) -> list[str]:
    failures: list[str] = []
    scene_usage = report["sceneUsage"]
    assert isinstance(scene_usage, list)
    peak_tiles = max((int(item["vramTiles"]) for item in scene_usage), default=0)
    peak_palettes = max((int(item["palettes"]) for item in scene_usage), default=0)
    checks = (
        ("work RAM", manifest.resources.work_ram_bytes, manifest.budgets.work_ram_bytes),
        ("VRAM tiles", peak_tiles, manifest.budgets.vram_tiles),
        ("palettes", peak_palettes, manifest.budgets.palettes),
        ("sprites", manifest.resources.sprites, manifest.budgets.sprites),
        ("sprites per scanline", manifest.resources.sprites_per_scanline, manifest.budgets.sprites_per_scanline),
        ("audio bytes", int(report["audioBytes"]), manifest.budgets.audio_bytes),
    )
    for label, actual, budget in checks:
        if actual > budget:
            failures.append(f"{label}: {actual} exceeds budget {budget}")
    if rom_path and rom_path.is_file():
        rom_bytes = rom_path.stat().st_size
        if rom_bytes > manifest.budgets.rom_bytes:
            failures.append(f"ROM: {rom_bytes} bytes exceeds project budget {manifest.budgets.rom_bytes}")
        if rom_bytes > 8 * 1024 * 1024:
            failures.append(f"ROM: {rom_bytes} bytes exceeds the 8 MiB release ceiling")
    return failures


def generate(manifest: Manifest) -> tuple[CompiledAsset, ...]:
    try:
        for scenario in manifest.play_scenarios:
            load_plan(
                manifest.root, scenario.plan,
                ready_frames=manifest.play_ready_frames,
            )
    except PlanError as exc:
        raise GenerationError(str(exc)) from exc
    compiled = compile_assets(manifest)
    generated = manifest.root / "build" / "generated"
    compiled = _compile_graphics_with_wonderful(manifest, compiled, generated)
    report = asset_report(manifest, compiled)
    failures = validate_budgets(manifest, report)
    if failures:
        raise GenerationError("resource budget failure:\n  " + "\n  ".join(failures))
    _write(manifest.root / "wfconfig.toml", _wfconfig(manifest, color=True))
    mono_config = generated / "wfconfig.mono.toml"
    if manifest.hardware == "mono-compatible":
        _write(mono_config, _wfconfig(manifest, color=False))
    elif mono_config.is_file():
        mono_config.unlink()
    _write(generated / "include" / "swan_project.h", _project_header(manifest))
    _write(generated / "include" / "swan_controls.h", _controls_header(manifest))
    _write(generated / "include" / "swan_assets.h", _assets_header(compiled))
    _write(generated / "include" / "swan_resources.h", _resource_header(manifest, compiled))
    _write(generated / "src" / "swan_assets.c", _assets_source(compiled))
    _write(generated / "src" / "swan_config.c", _config_source(manifest))
    _write(generated / "docs" / "controls.md", _controls_markdown(manifest))
    _write(generated / "play-contract.json", json.dumps(_play_contract(manifest), indent=2, sort_keys=True) + "\n")
    _write(generated / "asset-report.json", json.dumps(report, indent=2, sort_keys=True) + "\n")
    return compiled
