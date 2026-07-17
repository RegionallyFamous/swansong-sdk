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
```

Available recipes are `arcade-action`, `menu-puzzle`, and `grid-tactics`. Every
recipe includes a portable gameplay model, host tests, cartridge callbacks,
resource budgets, and fresh-boot SwanSong contracts.

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
[`swan.toml` reference](docs/manifest.md), [CLI reference](docs/cli.md), and
[SwanSong Desktop integration contract](docs/swansong-desktop-integration.md).
Framework contributors should also follow the [feedback loop](docs/framework-feedback-loop.md)
and [contribution guide](AGENTS.md).

## Status

The public API is in `0.x` incubation. Releases follow the pinned toolchain in
[`toolchain.lock`](toolchain.lock). The project is MIT licensed; Wonderful and
its libraries retain their respective licenses and notices listed in
[third-party notices](THIRD_PARTY_NOTICES.md).
