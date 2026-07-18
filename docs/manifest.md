# `swan.toml` reference

The checked-in manifest is the project source of truth. Unknown top-level data
is reserved for forward-compatible tools; all documented values are validated.
See `schema/swan.schema.json` for editor integration.

`[sdk]` records the semantic SDK version and a content-addressed `sha256:`
revision. `swan new` writes both from the resolved payload. `swan doctor`
reports a mismatch, and `swan release` refuses an absent or mismatched pin.
This distinguishes source checkouts, submodules, and installed wheels that
claim the same package version but contain different code or templates.

## Game and cartridge

`schema_version` is currently `1`. `[game]` requires a lowercase kebab-case
`id`, human `title`, semantic `version`, one of the three recipe names,
`color-required` or `mono-compatible` hardware, `horizontal` or `vertical`
orientation, and a declared `initial_scene` C identifier.

`[cartridge]` contains byte-sized Wonderful publisher/game/version IDs, a save
type, logical save payload bytes, and an RTC flag. Supported save names mirror
Wonderful: `none`; `eeprom-128b`, `eeprom-1kb`, or `eeprom-2kb`; and
`sram-8kb`, `sram-32kb`, `sram-128kb`, `sram-256kb`, or `sram-512kb`.

## Controls and scenes

`[controls.actions]` maps up to 16 semantic C identifiers to one or more raw
WonderSwan keys: `X1`–`X4`, `Y1`–`Y4`, `A`, `B`, or `START`. Both directional
clusters remain available so vertical games can map their primary direction
without losing the secondary cluster.

Every `[[scenes]]` entry has a unique C identifier and optional asset IDs. Scene
transitions are generated as integer IDs and switch dispatch; there are no
runtime function-pointer tables.

The generated controls header also exposes `SWAN_PRIMARY_UP/RIGHT/DOWN/LEFT`
and `SWAN_SECONDARY_*`. Horizontal projects use the X cluster as primary;
vertical projects use the Y cluster. Raw X and Y keys remain available.

## Assets

Each `[[assets]]` entry has an identifier, type, source path, optional static
group, and optional `flip_dedupe`. Source paths cannot escape the project.
Graphic types are `fullscreen`, `tilemap`, `spritesheet`, `metatiles`, and
`font`; all route through the pinned Wonderful SuperFamiconv backend while
retaining stable SwanSong IDs and reports. Audio types are `music` and `sfx`.
Music TOML declares up to 16
16-sample instruments, four-channel `[note, instrument, volume]` rows, Q8 frame
tempo, and looping. SFX TOML declares prioritized, timed command steps. Both
compile into typed runtime sequencer data and are deterministically hashed and
budgeted.

The runtime exposes `swan_audio_pause()` and `swan_audio_resume()` as an exact
static pause of music, active SFX, row, and fixed-point phase. While paused,
ticks do not advance and new SFX are rejected. `swan_audio_position()` returns
the deterministic row/phase plus playing and paused flags; it never consults a
wall clock and reset/stop clears the position bit-exactly.

`swan_core_reset_session()` stops the logical sequencer before invoking an
internal platform reset. On WonderSwan this resets oscillator phase, restores
the framework wavetable address and speaker/headphone routing, and leaves every
channel silent for the next commit. This keeps post-reset WAV output independent
of prior audio history without exposing raw sound-register access to gameplay.

## Resources and budgets

`[resources]` records fixed work RAM, runtime-owned VRAM tiles and palettes,
visible sprites, and worst-case scanline reservations that cannot be derived
from static artwork. `[budgets]` caps ROM bytes, work RAM, peak VRAM tiles,
peak palettes, sprites, scanline sprites, and audio source bytes. The ROM
budget may never exceed 8 MiB.

After linking, `swan report` also reads Wonderful's ELF usage analysis and
enforces the physical internal-RAM ceilings. Wonderful places common data in a
16 KiB mono area and Color-only data in a separate 48 KiB extension; SwanSong
checks both areas rather than incorrectly applying the mono ceiling to their
combined Color total. These totals include the runtime, game, generated data,
and linker reservations and are intentionally separate from the game-owned
`[resources].work_ram_bytes` reservation.

## Play scenarios

Each `[[play.scenarios]]` declares a kebab-case ID, title, goal, checked-in
`swan-song-frame-input-plan-v1` JSON path, required visual/behavioral checks,
and an optional `audio_expectation` of `audible`, `silent`, or `any`. Every mode
requires a decoded, non-empty, hash-bound WAV and explicit WAV inspection;
`audible` requires non-zero PCM amplitude while `silent` requires exactly zero.
The v0.2 `audio = true` spelling remains accepted as `audible`, and `false`
maps to `any`; conflicting old and new declarations are rejected. All generated
contracts require a fresh boot and media inspection.
