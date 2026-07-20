# SwanSong SDK 0.5.0

This release turns recurring game-specific work into reusable SDK behavior.
The main additions are a fixed-capacity gameplay primitive layer, compiled
visual authoring data, deterministic runtime traces and semantic outcomes,
faster content-addressed iteration, and safer artist/release workflows.

## Game building

- Animation, camera, AABB/tile collision, dirty tile grids, selection grids,
  stable pools, iterative BFS, and canonical state hashing are public C APIs.
- Tilemap, sprite/hitbox, palette/mono, collision/path, and scene-flow
  authoring JSON compiles into typed generated C.
- Wonderful graphic conversion is cached by source, conversion settings,
  generated script, and pinned toolchain identity. `input-graph.json` explains
  which project inputs own each generated output.
- Scenario scripts expand taps, holds, chords, repeated movement, and waits
  into exact frame plans. `swan play --all` fresh-boots every declared plan.

## Evidence and diagnosis

- Trace builds record semantic state without adding hidden gameplay inputs or
  release storage. Outcome contracts distinguish real progress, endings,
  resets, audio cues, and panics from a merely changing screenshot hash.
- Trace-mode sprite diagnostics use a bounded per-frame scan so diagnostic
  ROMs preserve gameplay timing; the exact full VRAM profiler stays on demand.
- SwanSong validates the SDK's opt-in diagnostic mailbox internally and
  returns only a canonical trace after separate semantic-trace confirmation;
  raw emulated memory remains private.
- The audio workbench renders deterministic authoring previews and reports
  loop seams, instrument envelopes, per-channel activity, and SFX arbitration.
  SwanSong WAVs remain the only cartridge audio authority.
- Historical resource reports can block unexplained ROM, RAM, VRAM, tile, or
  audio growth during `swan report` and `swan release`.
- Development and release play gates now run a separately identified trace ROM;
  Release then rebuilds the non-trace cartridge and packages a binding between
  both ROM digests without distributing the diagnostic ROM.

## Safer iteration

- `swan asset-import` copies reviewed outside assets into a project only when
  their SHA-256 matches, and writes source provenance without weakening normal
  project path isolation.
- Optimizer application requires the exact reviewed source hash and
  `artist-approved`; it preserves the original, never overwrites output, and
  reverts only when both report and generated file remain unchanged.
- `swan migrate` previews SDK/schema pin changes and applies them atomically
  with a content-addressed backup.
- Cartridge EEPROM setup now uses Wonderful's documented byte-address widths
  for 128-byte, 1-KiB, and 2-KiB media, covered by backend contract tests.

Four integration canaries now include hardware-sprite, transactional save plus
RTC boot-capture, and mono-compatible dual-layer scrolling/camera coverage.
