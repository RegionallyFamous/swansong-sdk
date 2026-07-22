# SwanSong SDK

SwanSong SDK is a deterministic C11 framework and developer toolkit for native
WonderSwan games. It adds fixed-step scenes, semantic input, tile and sprite
ownership, sequenced audio, transactional saves, asset generation, reusable
game recipes, and black-box playtests to the Wonderful Toolchain.

SwanSong is the sole emulator and automated gameplay authority. Host tests are
used for portable game rules; ROM behavior is accepted only after SwanSong
returns an inspected screenshot, WAV capture, structured evidence, and an
identical fresh-boot replay.

## Quick start

Requirements are Python 3.11+, a C compiler for host tests, the pinned
[Wonderful Toolchain](https://wonderful.asie.pl/), and SwanSong Desktop for ROM
playtests.

```sh
python3 -m pip install -e .
swan new tiny-orbit --template arcade-action
cd tiny-orbit
swan assets
swan test
swan build
swan play neutral
swan doctor
swan author create palette launch-palette
swan audio preview --source assets/audio/theme.toml
swan profile --json
swan optimize --json
swan lab --json
swan release
```

Available recipes are `arcade-action`, `menu-puzzle`, `grid-tactics`, and
`utility-app`. The utility recipe adds orientation-aware dual-cluster text-grid
entry, tap/hold alternatives, transactional EEPROM records, and explicit
save/reset outcomes. Every recipe includes a portable model, host tests,
cartridge callbacks, resource budgets, and fresh-boot SwanSong contracts.

`swan doctor` audits the complete SDK, toolchain, project, generated config,
and SwanSong interface. `swan dev` watches project inputs and reruns a declared
SwanSong contract against a diagnostic trace ROM. Scenario Recorder,
deterministic failure-plan Minimizer,
Replay Inspector, Evidence Diff, deterministic Fuzz, Profiler, Asset Optimizer,
project-owned visual Authoring, and Save/RTC Lab share stable versioned JSON
contracts with SwanSong Studio and CI. `swan release` fails closed across
build, test, budgets, pinned toolchain provenance, and every declared SwanSong
play gate, then rebuilds a clean non-trace release ROM. It requires hash-bound
PNG/WAV inspection notes for every required check and packages an explicit
validation-ROM/release-ROM digest binding before producing a byte-deterministic
release archive.

Release archives also carry deterministic SPDX and CycloneDX software bills
of materials plus an unsigned in-toto/SLSA provenance statement. The four
complete recipe canaries under `examples/canaries` prove that a clean installed
SDK can create, asset-build, host-test, compile, and report a bounded native WSC
ROM without project-specific framework changes. Together they cover hardware
sprites, save/RTC boot behavior, and mono-compatible dual-layer scrolling.

Version 0.5 also adds fixed-capacity animation, camera, collision, dirty-grid,
selection, pool, and pathfinding primitives; compiled visual authoring data;
content-addressed graphic rebuilds; an audio authoring workbench; safe shared
asset import; reversible optimizer and SDK migrations; historical budget
gates; and opt-in semantic runtime traces. See [gameplay primitives](docs/gameplay-primitives.md)
and [trace/outcome contracts](docs/trace-and-outcomes.md).

The current unreleased runtime adds pause-safe frame timers, explicit timing
grades, saturating chain/multiplier scoring, stable caller-owned record tables,
canonical record serialization, and deterministic 8-fractional-bit motion.
These fill recurring gaps found in the complete WWGP 2001–2003 catalogs
without adding a genre engine. See the
[WWGP design review](docs/wwgp-design-lessons.md).

## Design constraints

- C11 with static capacities; no heap, floating point, recursion, ECS, or far
  function-pointer dispatch tables.
- Input is sampled exactly once per VBlank and exposed as an immutable frame
  snapshot.
- All nondeterminism is explicit. Gameplay receives seeded RNG and captured RTC
  values rather than reading hidden global state.
- WonderSwan Color is the primary target. Projects explicitly declare
  `color-required` or `mono-compatible`.
- Source assets and `swan.toml` are versioned. Generated outputs live under
  `build/generated`.
- Project budgets and the 8 MiB cartridge ceiling are build failures, not
  advisory warnings.

See [Getting started](docs/getting-started.md), the
[`swan.toml` reference](docs/manifest.md), [input gesture guide](docs/input-gestures.md),
[CLI reference](docs/cli.md), and
[SwanSong Desktop integration contract](docs/swansong-desktop-integration.md).
Framework contributors should also follow the [feedback loop](docs/framework-feedback-loop.md)
and [contribution guide](AGENTS.md). Release engineers should read the
[supply-chain contract](docs/supply-chain.md) and [0.5.0 release notes](docs/release-notes-0.5.0.md).

## Status

The public API is in `0.x` incubation. Releases follow the pinned toolchain in
[`toolchain.lock`](toolchain.lock). The project is MIT licensed; Wonderful and
its libraries retain their respective licenses and notices listed in
[third-party notices](THIRD_PARTY_NOTICES.md).
