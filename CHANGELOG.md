# SwanSong SDK changelog

## Unreleased

- Added deterministic, opt-in SFX routing policy for preferred and reserved
  channels, music-steal eligibility and priority, and fixed-point ducking.
- Kept music resolving behind active effects so a stolen voice restores the
  correct held note, instrument, and volume when the effect ends.
- Added focused routing, priority, pause, ducking, and held-state restoration
  regression coverage without changing the default audio API behavior.

## 0.5.0 — 2026-07-20

- Added fixed-capacity animation, camera, collision, tile-grid, cursor-grid,
  pool, iterative pathfinding, and canonical state-hash primitives.
- Added opt-in deterministic runtime traces and machine-checkable scenario
  outcomes for state, progress, endings, resets, audio markers, and panics.
- Added the guarded `SWMB` mailbox contract used by SwanSong to validate and
  export canonical traces without exposing raw emulated memory.
- Compiled visual authoring documents directly into typed C data and generated
  a content-addressed project input graph plus incremental Wonderful art cache.
- Added deterministic tap/hold/chord/repeat scenario scripts, a host audio
  workbench, priority/SFX arbitration reports, and `swan play --all`.
- Added hash-bound external asset import, explicit artist-approved and
  reversible optimizer application, and source provenance reports.
- Added previewable manifest migration, historical resource-budget gates, and
  release packaging of budget comparisons.
- Added Dewdrop Dash sprite coverage, the Daybreak Ledger save/RTC canary, and
  the mono-compatible dual-layer Tidewheel Traverse scrolling canary.
- Corrected 128-byte and 2-KiB cartridge EEPROM byte-address widths to match
  Wonderful's storage contract, with focused backend tests.
- Kept deterministic frame tracing at full gameplay speed by collecting its
  sprite scanline summary without invoking the full on-demand VRAM profiler.
- Added retained-ring integrity to the private SwanSong trace mailbox and made
  wrapped sprite coordinates match WonderSwan scanline behavior.
- Isolated normal and trace game objects, made Development trace-aware, and
  made Release validate a trace ROM before rebuilding and binding the clean
  cartridge. Installed-wheel CI now covers all four production canaries.

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
