"""Load and validate the declarative SwanSong project manifest."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path
import re
import tomllib
from typing import Any


SCHEMA_VERSION = 1
HARDWARE = {"color-required", "mono-compatible"}
ORIENTATIONS = {"horizontal", "vertical"}
ASSET_TYPES = {
    "fullscreen", "tilemap", "spritesheet", "metatiles", "font",
    "music", "sfx",
}
AUDIO_EXPECTATIONS = {"audible", "silent", "any"}
INPUTS = {"X1", "X2", "X3", "X4", "Y1", "Y2", "Y3", "Y4", "A", "B", "START"}
SAVE_CAPACITIES = {
    "none": 0,
    "eeprom-128b": 128,
    "eeprom-1kb": 1024,
    "eeprom-2kb": 2048,
    "sram-8kb": 8192,
    "sram-32kb": 32768,
    "sram-128kb": 131072,
    "sram-256kb": 262144,
    "sram-512kb": 524288,
}
SAVE_TYPES = set(SAVE_CAPACITIES)
C_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PROJECT_ID = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
PROJECT_VERSION = re.compile(
    r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?"
    r"(?:\+[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?$"
)
SDK_REVISION = re.compile(r"^sha256:[0-9a-f]{64}$")


class ManifestError(ValueError):
    """A manifest is missing a required value or contains an invalid value."""


@dataclass(frozen=True)
class Asset:
    id: str
    type: str
    source: str
    group: str = "common"
    flip_dedupe: bool = True


@dataclass(frozen=True)
class Scene:
    id: str
    assets: tuple[str, ...] = ()


@dataclass(frozen=True)
class AudioEvidenceThresholds:
    signal_floor: float = 0.0
    max_stereo_balance_delta: float | None = None
    max_cue_onset_delta_ms: float | None = None
    max_silent_frame_ratio_increase: float | None = None
    max_internal_silence_increase_ms: float | None = None
    max_clipped_sample_ratio_increase: float | None = None
    max_loop_seam_delta_increase: float | None = None

    @property
    def configured(self) -> bool:
        return self.signal_floor != 0.0 or any(
            value is not None for name, value in self.__dict__.items()
            if name != "signal_floor"
        )

    def to_contract(self) -> dict[str, float | None]:
        return {
            "signalFloor": self.signal_floor,
            "maxStereoBalanceDelta": self.max_stereo_balance_delta,
            "maxCueOnsetDeltaMs": self.max_cue_onset_delta_ms,
            "maxSilentFrameRatioIncrease": self.max_silent_frame_ratio_increase,
            "maxInternalSilenceIncreaseMs": self.max_internal_silence_increase_ms,
            "maxClippedSampleRatioIncrease": self.max_clipped_sample_ratio_increase,
            "maxLoopSeamDeltaIncrease": self.max_loop_seam_delta_increase,
        }


@dataclass(frozen=True)
class PlayScenario:
    id: str
    title: str
    goal: str
    plan: str
    required_checks: tuple[str, ...]
    audio_expectation: str = "any"
    audio_evidence: AudioEvidenceThresholds = field(
        default_factory=AudioEvidenceThresholds
    )
    outcome_contract: str | None = None

    @property
    def audio(self) -> bool:
        """Compatibility view for v0.2 consumers that treated audio as boolean."""
        return self.audio_expectation == "audible"


@dataclass(frozen=True)
class Budgets:
    rom_bytes: int = 8 * 1024 * 1024
    work_ram_bytes: int = 16 * 1024
    vram_tiles: int = 512
    palettes: int = 16
    sprites: int = 128
    sprites_per_scanline: int = 32
    audio_bytes: int = 64 * 1024


@dataclass(frozen=True)
class Resources:
    work_ram_bytes: int = 0
    vram_tiles: int = 0
    palettes: int = 0
    sprites: int = 0
    sprites_per_scanline: int = 0


@dataclass(frozen=True)
class InputGestures:
    tap_max_frames: int = 8
    double_tap_window: int = 12
    hold_threshold: int = 20


@dataclass(frozen=True)
class Manifest:
    root: Path
    id: str
    title: str
    version: str
    template: str
    hardware: str
    orientation: str
    initial_scene: str
    sdk_version: str | None
    sdk_revision: str | None
    game_id: int
    publisher_id: int
    cartridge_version: int
    save_type: str
    save_bytes: int
    rtc: bool
    controls: dict[str, tuple[str, ...]]
    input_gestures: InputGestures
    input_chords: dict[str, tuple[str, ...]]
    scenes: tuple[Scene, ...]
    assets: tuple[Asset, ...]
    play_ready_frames: int
    play_scenarios: tuple[PlayScenario, ...]
    budgets: Budgets = field(default_factory=Budgets)
    resources: Resources = field(default_factory=Resources)

    @property
    def rom_name(self) -> str:
        return self.id.replace("-", "_") + ".wsc"


def _table(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ManifestError(f"{key} must be a table")
    return value


def _string(table: dict[str, Any], key: str, *, context: str, default: str | None = None) -> str:
    value = table.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{context}.{key} must be a non-empty string")
    return value


def _integer(table: dict[str, Any], key: str, *, context: str, default: int) -> int:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ManifestError(f"{context}.{key} must be an integer")
    return value


def _optional_number(table: dict[str, Any], key: str, *, context: str,
                     default: float | None = None, maximum: float | None = None
                     ) -> float | None:
    value = table.get(key, default)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ManifestError(f"{context}.{key} must be a number")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ManifestError(f"{context}.{key} must be a finite nonnegative number")
    if maximum is not None and result > maximum:
        raise ManifestError(f"{context}.{key} must be at most {maximum:g}")
    return result


def _identifier(value: str, context: str) -> None:
    if not C_IDENTIFIER.fullmatch(value):
        raise ManifestError(f"{context} must be a C identifier, got {value!r}")


def _list_of_strings(value: Any, context: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
        raise ManifestError(f"{context} must be a non-empty string array")
    return tuple(value)


def load_manifest(path: str | Path = "swan.toml") -> Manifest:
    manifest_path = Path(path).resolve()
    try:
        with manifest_path.open("rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise ManifestError(f"manifest not found: {manifest_path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ManifestError(f"invalid TOML in {manifest_path}: {exc}") from exc

    schema = data.get("schema_version")
    if schema != SCHEMA_VERSION:
        raise ManifestError(f"schema_version must be {SCHEMA_VERSION}, got {schema!r}")

    game = _table(data, "game")
    project_id = _string(game, "id", context="game")
    if not PROJECT_ID.fullmatch(project_id):
        raise ManifestError("game.id must be lowercase kebab-case")
    title = _string(game, "title", context="game")
    version = _string(game, "version", context="game", default="0.1.0")
    if not PROJECT_VERSION.fullmatch(version):
        raise ManifestError("game.version must be a path-safe semantic version such as 1.2.3")
    template = _string(game, "template", context="game")
    hardware = _string(game, "hardware", context="game", default="color-required")
    if hardware not in HARDWARE:
        raise ManifestError(f"game.hardware must be one of {sorted(HARDWARE)}")
    orientation = _string(game, "orientation", context="game", default="horizontal")
    if orientation not in ORIENTATIONS:
        raise ManifestError(f"game.orientation must be one of {sorted(ORIENTATIONS)}")
    initial_scene = _string(game, "initial_scene", context="game")
    _identifier(initial_scene, "game.initial_scene")

    sdk = _table(data, "sdk")
    sdk_version_raw = sdk.get("version")
    sdk_revision_raw = sdk.get("revision")
    if (sdk_version_raw is None) != (sdk_revision_raw is None):
        raise ManifestError("sdk.version and sdk.revision must be declared together")
    sdk_version: str | None = None
    sdk_revision: str | None = None
    if sdk_version_raw is not None:
        sdk_version = _string(sdk, "version", context="sdk")
        if not PROJECT_VERSION.fullmatch(sdk_version):
            raise ManifestError("sdk.version must be a semantic version such as 0.3.0")
        sdk_revision = _string(sdk, "revision", context="sdk")
        if not SDK_REVISION.fullmatch(sdk_revision):
            raise ManifestError("sdk.revision must be sha256 followed by 64 lowercase hex digits")

    cartridge = _table(data, "cartridge")
    game_id = _integer(cartridge, "game_id", context="cartridge", default=1)
    publisher_id = _integer(cartridge, "publisher_id", context="cartridge", default=0)
    cartridge_version = _integer(cartridge, "version", context="cartridge", default=1)
    for name, value in (("game_id", game_id), ("publisher_id", publisher_id), ("version", cartridge_version)):
        if not 0 <= value <= 255:
            raise ManifestError(f"cartridge.{name} must be between 0 and 255")
    save_type = _string(cartridge, "save_type", context="cartridge", default="none").lower()
    if save_type not in SAVE_TYPES:
        raise ManifestError(f"cartridge.save_type must be one of {sorted(SAVE_TYPES)}")
    save_bytes = _integer(cartridge, "save_bytes", context="cartridge", default=0)
    if save_bytes < 0:
        raise ManifestError("cartridge.save_bytes cannot be negative")
    if save_bytes > SAVE_CAPACITIES[save_type]:
        raise ManifestError(
            f"cartridge.save_bytes exceeds {save_type} capacity of {SAVE_CAPACITIES[save_type]} bytes"
        )
    rtc = cartridge.get("rtc", False)
    if not isinstance(rtc, bool):
        raise ManifestError("cartridge.rtc must be true or false")

    controls_table = _table(data, "controls")
    actions = _table(controls_table, "actions")
    controls: dict[str, tuple[str, ...]] = {}
    for action, raw_inputs in actions.items():
        _identifier(action, f"controls.actions.{action}")
        inputs = _list_of_strings(raw_inputs, f"controls.actions.{action}")
        unknown = set(inputs) - INPUTS
        if unknown:
            raise ManifestError(f"controls.actions.{action} has unknown inputs: {sorted(unknown)}")
        controls[action] = inputs
    if not controls:
        raise ManifestError("controls.actions must contain at least one action")
    if len(controls) > 16:
        raise ManifestError("controls.actions cannot exceed the runtime capacity of 16")

    gesture_table = _table(controls_table, "gestures")
    gesture_defaults = InputGestures()
    unknown_gestures = set(gesture_table) - set(InputGestures.__dataclass_fields__)
    if unknown_gestures:
        raise ManifestError(
            f"controls.gestures has unknown keys: {sorted(unknown_gestures)}"
        )
    input_gestures = InputGestures(**{
        name: _integer(
            gesture_table, name, context="controls.gestures",
            default=getattr(gesture_defaults, name),
        )
        for name in InputGestures.__dataclass_fields__
    })
    for name, value in input_gestures.__dict__.items():
        if not 1 <= value <= 255:
            raise ManifestError(f"controls.gestures.{name} must be between 1 and 255 frames")

    chords = _table(controls_table, "chords")
    input_chords: dict[str, tuple[str, ...]] = {}
    for chord, raw_actions in chords.items():
        _identifier(chord, f"controls.chords.{chord}")
        chord_actions = _list_of_strings(raw_actions, f"controls.chords.{chord}")
        unknown = set(chord_actions) - set(controls)
        if unknown:
            raise ManifestError(
                f"controls.chords.{chord} has unknown actions: {sorted(unknown)}"
            )
        if len(set(chord_actions)) != len(chord_actions):
            raise ManifestError(f"controls.chords.{chord} cannot repeat an action")
        if len(chord_actions) < 2:
            raise ManifestError(
                f"controls.chords.{chord} must contain at least two distinct actions"
            )
        input_chords[chord] = chord_actions
    if len(input_chords) > 8:
        raise ManifestError("controls.chords cannot exceed the runtime capacity of 8")

    raw_scenes = data.get("scenes", [])
    if not isinstance(raw_scenes, list) or not raw_scenes:
        raise ManifestError("at least one [[scenes]] entry is required")
    scenes: list[Scene] = []
    seen_scenes: set[str] = set()
    for index, item in enumerate(raw_scenes):
        if not isinstance(item, dict):
            raise ManifestError(f"scenes[{index}] must be a table")
        scene_id = _string(item, "id", context=f"scenes[{index}]")
        _identifier(scene_id, f"scenes[{index}].id")
        if scene_id in seen_scenes:
            raise ManifestError(f"duplicate scene id: {scene_id}")
        seen_scenes.add(scene_id)
        raw_scene_assets = item.get("assets", [])
        scene_assets = _list_of_strings(raw_scene_assets, f"scenes[{index}].assets") if raw_scene_assets else ()
        scenes.append(Scene(scene_id, scene_assets))
    if initial_scene not in seen_scenes:
        raise ManifestError(f"game.initial_scene {initial_scene!r} is not declared in [[scenes]]")

    raw_assets = data.get("assets", [])
    if not isinstance(raw_assets, list):
        raise ManifestError("assets must be an array of tables")
    assets: list[Asset] = []
    seen_assets: set[str] = set()
    for index, item in enumerate(raw_assets):
        if not isinstance(item, dict):
            raise ManifestError(f"assets[{index}] must be a table")
        asset_id = _string(item, "id", context=f"assets[{index}]")
        _identifier(asset_id, f"assets[{index}].id")
        if asset_id in seen_assets:
            raise ManifestError(f"duplicate asset id: {asset_id}")
        seen_assets.add(asset_id)
        asset_type = _string(item, "type", context=f"assets[{index}]")
        if asset_type not in ASSET_TYPES:
            raise ManifestError(f"assets[{index}].type must be one of {sorted(ASSET_TYPES)}")
        source = _string(item, "source", context=f"assets[{index}]")
        group = _string(item, "group", context=f"assets[{index}]", default="common")
        _identifier(group, f"assets[{index}].group")
        flip_dedupe = item.get("flip_dedupe", True)
        if not isinstance(flip_dedupe, bool):
            raise ManifestError(f"assets[{index}].flip_dedupe must be true or false")
        assets.append(Asset(asset_id, asset_type, source, group, flip_dedupe))
    for scene in scenes:
        unknown = set(scene.assets) - seen_assets
        if unknown:
            raise ManifestError(f"scene {scene.id} references unknown assets: {sorted(unknown)}")

    play_table = _table(data, "play")
    play_ready_frames = _integer(
        play_table, "ready_frames", context="play", default=60
    )
    if play_ready_frames <= 0:
        raise ManifestError("play.ready_frames must be greater than zero")
    raw_scenarios = play_table.get("scenarios", [])
    if not isinstance(raw_scenarios, list):
        raise ManifestError("play.scenarios must be an array of tables")
    scenarios: list[PlayScenario] = []
    seen_scenarios: set[str] = set()
    for index, item in enumerate(raw_scenarios):
        if not isinstance(item, dict):
            raise ManifestError(f"play.scenarios[{index}] must be a table")
        context = f"play.scenarios[{index}]"
        scenario_id = _string(item, "id", context=context)
        if not PROJECT_ID.fullmatch(scenario_id):
            raise ManifestError(f"{context}.id must be lowercase kebab-case")
        if scenario_id in seen_scenarios:
            raise ManifestError(f"duplicate scenario id: {scenario_id}")
        seen_scenarios.add(scenario_id)
        required_checks = _list_of_strings(item.get("required_checks", []), f"{context}.required_checks")
        if not required_checks:
            raise ManifestError(f"{context}.required_checks cannot be empty")
        legacy_audio = item.get("audio")
        if legacy_audio is not None and not isinstance(legacy_audio, bool):
            raise ManifestError(f"{context}.audio must be true or false")
        audio_expectation = item.get("audio_expectation")
        if audio_expectation is None:
            audio_expectation = "audible" if legacy_audio is True else "any"
        elif (not isinstance(audio_expectation, str) or
              audio_expectation not in AUDIO_EXPECTATIONS):
            raise ManifestError(
                f"{context}.audio_expectation must be audible, silent, or any"
            )
        if legacy_audio is not None:
            legacy_expectation = "audible" if legacy_audio else "any"
            if audio_expectation != legacy_expectation:
                raise ManifestError(
                    f"{context}.audio and audio_expectation conflict"
                )
        raw_audio_evidence = item.get("audio_evidence", {})
        if not isinstance(raw_audio_evidence, dict):
            raise ManifestError(f"{context}.audio_evidence must be a table")
        allowed_audio_evidence = {
            "signal_floor", "max_stereo_balance_delta", "max_cue_onset_delta_ms",
            "max_silent_frame_ratio_increase", "max_internal_silence_increase_ms",
            "max_clipped_sample_ratio_increase", "max_loop_seam_delta_increase",
        }
        unknown_audio_evidence = set(raw_audio_evidence) - allowed_audio_evidence
        if unknown_audio_evidence:
            raise ManifestError(
                f"{context}.audio_evidence has unknown keys: "
                f"{sorted(unknown_audio_evidence)}"
            )
        audio_evidence = AudioEvidenceThresholds(
            signal_floor=_optional_number(
                raw_audio_evidence, "signal_floor", context=f"{context}.audio_evidence",
                default=0.0, maximum=1.0,
            ) or 0.0,
            max_stereo_balance_delta=_optional_number(
                raw_audio_evidence, "max_stereo_balance_delta",
                context=f"{context}.audio_evidence", maximum=2.0,
            ),
            max_cue_onset_delta_ms=_optional_number(
                raw_audio_evidence, "max_cue_onset_delta_ms",
                context=f"{context}.audio_evidence",
            ),
            max_silent_frame_ratio_increase=_optional_number(
                raw_audio_evidence, "max_silent_frame_ratio_increase",
                context=f"{context}.audio_evidence", maximum=1.0,
            ),
            max_internal_silence_increase_ms=_optional_number(
                raw_audio_evidence, "max_internal_silence_increase_ms",
                context=f"{context}.audio_evidence",
            ),
            max_clipped_sample_ratio_increase=_optional_number(
                raw_audio_evidence, "max_clipped_sample_ratio_increase",
                context=f"{context}.audio_evidence", maximum=1.0,
            ),
            max_loop_seam_delta_increase=_optional_number(
                raw_audio_evidence, "max_loop_seam_delta_increase",
                context=f"{context}.audio_evidence", maximum=2.0,
            ),
        )
        scenarios.append(PlayScenario(
            id=scenario_id,
            title=_string(item, "title", context=context),
            goal=_string(item, "goal", context=context),
            plan=_string(item, "plan", context=context),
            required_checks=required_checks,
            audio_expectation=audio_expectation,
            audio_evidence=audio_evidence,
            outcome_contract=(
                _string(item, "outcome", context=context)
                if item.get("outcome") is not None else None
            ),
        ))

    budget_table = _table(data, "budgets")
    defaults = Budgets()
    budgets = Budgets(**{
        name: _integer(budget_table, name, context="budgets", default=getattr(defaults, name))
        for name in Budgets.__dataclass_fields__
    })
    for name, value in budgets.__dict__.items():
        if value <= 0:
            raise ManifestError(f"budgets.{name} must be greater than zero")
    if budgets.rom_bytes > 8 * 1024 * 1024:
        raise ManifestError("budgets.rom_bytes cannot exceed the 8 MiB release ceiling")

    resource_table = _table(data, "resources")
    resources = Resources(**{
        name: _integer(resource_table, name, context="resources", default=0)
        for name in Resources.__dataclass_fields__
    })
    for name, value in resources.__dict__.items():
        if value < 0:
            raise ManifestError(f"resources.{name} cannot be negative")

    return Manifest(
        manifest_path.parent, project_id, title, version, template, hardware,
        orientation, initial_scene, sdk_version, sdk_revision,
        game_id, publisher_id, cartridge_version,
        save_type, save_bytes, rtc, controls, input_gestures, input_chords,
        tuple(scenes), tuple(assets),
        play_ready_frames, tuple(scenarios), budgets, resources,
    )


def find_manifest(start: str | Path = ".") -> Path:
    current = Path(start).resolve()
    if current.is_file():
        return current
    while True:
        candidate = current / "swan.toml"
        if candidate.is_file():
            return candidate
        if current.parent == current:
            raise ManifestError("no swan.toml found in this directory or its parents")
        current = current.parent
