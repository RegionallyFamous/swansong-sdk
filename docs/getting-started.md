# Getting started

## Install the SDK tools

Use Python 3.11 or newer. An editable install is convenient while the SDK is in
`0.x` incubation:

```sh
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e /path/to/swansong-sdk
```

Install the Wonderful packages listed in `toolchain.lock` under
`/opt/wonderful`, or set `WONDERFUL_TOOLCHAIN` to an equivalent pinned install.
The Python wheel includes the C runtime, headers, schema, recipes, and build
fragments. `swan sdk-path` prints that complete payload location; builds place
the compiled static runtime under the game project's own `build` directory.

## Create a game

```sh
swan new parcel-run --template arcade-action
cd parcel-run
swan assets
swan test
swan build
swan doctor
```

`swan assets` validates `swan.toml` and writes only derived files:

```text
wfconfig.toml
build/generated/include/swan_project.h
build/generated/include/swan_controls.h
build/generated/include/swan_assets.h
build/generated/include/swan_resources.h
build/generated/src/swan_assets.c
build/generated/src/swan_config.c
build/generated/docs/controls.md
build/generated/play-contract.json
build/generated/asset-report.json
```

The generated entry point owns the VBlank loop and translates Wonderful's
hardware keypad masks into the SDK's stable key representation before sampling
input. A game implements only the fixed `swan_game_boot` and `swan_scene_*`
symbols.

## Add artwork

Declare non-interlaced PNGs under `[[assets]]`. SwanSong performs a
dependency-free PNG/color preflight, then wraps Wonderful `wf-process` and the
pinned SuperFamiconv package as the cartridge conversion authority. Indexed,
grayscale, RGB, grayscale-alpha, and RGBA sources are accepted; each graphic
must use no more than four RGBA colors. Wonderful deduplicates flip-equivalent
tiles and emits WSC 2BPP tiles, RGB444 palettes, and tilemaps into
`build/generated/src`.

Scene asset lists establish peak VRAM and palette usage. Assets in the `common`
group are counted in every scene. Generation fails when a peak exceeds the
declared budget.

The v1 graphics path is 2BPP. A `mono-compatible` project therefore uses the
same tile data for its primary Color cartridge and a generated mono validation
cartridge; the platform adapter supplies normalized mono palette registers.
Its runtime is linked with the shared 512-tile layout and writes Wonderful's
reserved tile, screen, sprite, and palette memory directly so all live state
fits in the mono-visible 16 KiB area. `color-required` projects use both 2BPP
tile banks (1024 background tiles); sprites always remain limited to tiles
0–511.

Color backgrounds address tiles 0 through 1023 with `SWAN_TILE_ATTR`; sprites
use the separate `swan_sprite_t.tile` field and are limited to 0 through 511.
In a `color-required` runtime, tile uploads are staged until the next VBlank.
Up to 512 tiles in 16 batches may be prepared for one presentation, so larger
scene banks should stream over multiple frames. This keeps the Color runtime's
tile staging buffer at 8 KiB instead of shadowing the full 16 KiB tile memory.
The mono-compatible runtime uses a lean hardware-backed path instead: render
calls write the reserved WSE tile, screen, sprite, and palette resources during
the frame preparation phase, avoiding Color-only shadow state.

`swan_gfx_set_camera` controls either background's 256×256 pixel scroll plane,
and `swan_gfx_camera_project` converts world positions for sprite placement.
WonderSwan hardware clips Screen 2 (SDK layer 1) inside or outside a rectangle;
Screen 1 has no hardware window. `swan_gfx_set_layer_clip` exposes that limit,
while `swan_gfx_set_sprite_clip` controls the sprite window. Sprite flags can
select outside-window rendering, priority, and flips.

The manifest selects the hardware reservation for the project's shared runtime.
`color-required` projects reserve both 512-tile banks and can address all 1024
background tiles. `mono-compatible` projects compile both their `.wsc` and
`.ws` cartridges against a 512-tile runtime, keeping screen and tile resources
inside mono-visible IRAM. Its graphics bookkeeping uses only 68 bytes of BSS;
the screen maps and sprite table have a single owner in WSE memory. The runtime
also rejects bank-1 uploads and tilemap entries whenever the detected hardware
mode is mono.

## Use cartridge persistence and RTC

The WonderSwan adapter binds the save media declared in generated
`wfconfig.toml` to the portable two-slot journal. Keep both the adapter context
and `swan_storage_t` in static storage:

```c
static swan_ws_eeprom_context_t eeprom;
static swan_storage_t storage;

void swan_game_boot(void) {
    if (swan_ws_eeprom_storage(&eeprom, &storage, 1024)) {
        /* swan_save_load(...) or swan_save_store(...) */
    }
}
```

Use `swan_ws_sram_storage` in the same way for 8, 32, 128, 256, or 512 KiB
SRAM cartridges. EEPROM sizes are 128 B, 1 KiB, and 2 KiB. The selected size
must match the manifest cartridge setting.

For schema migration, call `swan_save_load` with the current game schema. On
`SWAN_SAVE_SCHEMA_MISMATCH`, inspect `swan_save_info_t.schema`, load the valid
older record with `swan_save_load_any`, transform it in fixed game-owned
storage, and commit the new record with `swan_save_store`. The journal keeps
the older valid slot intact until that new commit is complete.

RTC reads are deliberately restricted to `swan_game_boot`. Bind a static
backend and call `swan_rtc_capture` there once, then copy the normalized
`swan_datetime_t` into game state. Repeated boot-time reads return the same
captured value; a later read returns `SWAN_RTC_WRONG_PHASE`, so deterministic
scene updates cannot consult live time.

## Play through SwanSong

Set either:

```sh
export SWANSONG_DESKTOP_DIR=/path/to/SwanSong-Desktop
```

or `SWANSONG_MCP_COMMAND` to the exact command that launches SwanSong's MCP
server. Then run a scenario declared in `swan.toml`:

```sh
swan play interaction
```

The CLI replays the complete frame plan twice from fresh boots. It rejects a
non-SwanSong MCP server or divergent replay and writes `frame.png`, `audio.wav`,
and `evidence.json` to `build/swansong/<scenario>/`. A human or game-playing
agent must inspect the media before declaring the behavior correct.

During development, swan dev rebuilds on source or declared-asset changes and
replays the interaction contract through SwanSong. Use swan dev --once for a
bounded build/play check.

SwanSong Studio calls the same CLI contracts for the rest of the loop:
`swan scenario-record` turns an exported input log into a checked-in frame
plan; `swan minimize` reduces a declared failure within a bounded SwanSong
evaluation budget; `swan replay` combines a plan with checkpoints, evidence,
and trace summaries for a frame timeline; `swan optimize` previews source-art
savings; `swan profile` combines declared budgets with an optional trace; `swan evidence-diff` compares decoded
captures; `swan fuzz` executes seeded plans through SwanSong; and `swan lab`
exercises the save/RTC contracts without consulting the host clock.

When the project is ready, inspect each scenario's current PNG/WAV evidence and
write its bound `swan-song-evidence-observation-v1` record beside the evidence.
Then `swan release` reruns assets, build, host tests, resource budgets, and every
declared play contract, verifies those inspected records, and writes a
deterministic release ZIP under `dist`. CI and SwanSong Studio should use the
versioned JSON forms of Doctor, Dev, and Release rather than parsing
human-formatted output. The CLI reference defines the observation schema.
