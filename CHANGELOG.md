# SwanSong SDK changelog

## 0.4.0 — 2026-07-18

- Added deterministic semantic taps, double taps, holds, hold releases, and
  same-frame action chords to the C11 input runtime and generated controls.
- Added a production `utility-app` recipe with dual-cluster navigation,
  fixed-capacity editing, transactional EEPROM persistence, distinct outcomes,
  host tests, and complete SwanSong scenarios.
- Added an enforceable play-readiness boundary so scenarios cannot send their
  first input before a game's fresh-boot safe point.
- Expanded WAV evidence with stereo balance, cue onset, dropout, clipping, and
  loop-seam measurements plus optional per-scenario regression limits.
- Removed full tilemap and sprite diagnostics from the normal frame-present
  path, retaining exact on-demand profiler results without stalling gameplay.
- Added native rectangular tile fills and taught the utility recipe to redraw
  only its changing editor regions after a scene background is prepared.
- Made generated projects relink whenever their pinned SDK runtime archive or
  runtime sources change, including direct Makefile-based development.

## 0.3.1 — 2026-07-18

- Fixed `swan doctor` timing out after a valid initialize response from a
  normal long-lived SwanSong MCP server.
- Unified Doctor's probe with the bounded line-oriented MCP response reader,
  while retaining response identity checks, timeouts, redacted command details,
  and process-group cleanup.

## 0.3.0 — 2026-07-18

- Added deterministic failure-plan minimization and read-only replay timelines.
- Added project-owned visual authoring contracts for tilemaps, sprites,
  palettes, collision, scene flow, and four-channel audio.
- Added `audible`, `silent`, and `any` play-contract audio expectations with
  decoded, non-empty, hash-bound WAV inspection in every mode.
- Added exact static audio pause/resume and deterministic sequencer row/phase
  reporting without a wall clock.
- Made session reset stop the logical sequencer, disable every WonderSwan
  wavetable channel, and clear its volumes, producing an exact silent boundary.
- Added deterministic SPDX 2.3, CycloneDX 1.6, and unsigned
  in-toto/SLSA-style release records, with fail-closed SDK and Wonderful
  dependency pins.
- Added Dewdrop Dash and Signal Orchard as recipe-only production canaries,
  plus isolated-wheel CI that scaffolds, builds, tests, and reports both.

## 0.2.0 — 2026-07-17

- Added Doctor, Dev, Scenario Recorder, Evidence Diff, deterministic Fuzz,
  Profiler, Asset Optimizer, Save/RTC Lab, and deterministic Release tooling.
- Added the Wonderful-backed graphic and audio asset pipeline and all three
  production recipes.

## 0.1.0 — 2026-07-16

- Introduced the deterministic C11 runtime, scenes, semantic input, graphics,
  RNG, save/RTC foundations, CLI, and first recipe canaries.
