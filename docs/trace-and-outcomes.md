# Deterministic traces and scenario outcomes

Trace ROMs are diagnostic builds. `swan build --trace` compiles a bounded
static recorder; normal and release builds compile the recorder and its marker
arguments out. `--trace-capacity 1..255` controls retained tail frames.

Each frame records boot/session ticks, raw and semantic input, scene and one
deferred transition, canonical game-state hash and progress, ending, reset,
dirty/render/present state, sprite pressure, audio ownership and game markers,
and panic status. The exact `SWTR` v1 wire format has a 32-byte little-endian
header and 42-byte records. Aggregate counts and a stream hash cover frames
that have fallen out of the retained ring.

Games mark semantics during `swan_scene_update`:

```c
swan_debug_frame_mark_state(progress, canonical_hash);
swan_debug_frame_mark_ending(ending_id);
swan_debug_frame_mark_audio(1u << cue_id);
```

Marker arguments are not evaluated in release builds. Build a canonical hash
by appending individual fields with `swan_state_hash_*`; never hash a padded C
struct or renderer-owned tables.

A play scenario may point to a project-owned outcome JSON:

```toml
[[play.scenarios]]
id = "success"
title = "Reach the beacon"
goal = "Finish one route"
plan = "tests/play/success.json"
required_checks = ["the success state is visible"]
outcome = "tests/outcomes/success.json"
audio_expectation = "audible"
```

The `swan-scenario-outcome-contract-v1` file can require final scene, ending,
exact or bounded progress, canonical state hash, reset count/post-reset state,
audio-marker bits, and audible or silent inspected SwanSong WAV evidence. Any
runtime panic fails unconditionally. `swan outcome SCENARIO --trace trace.swtr
--wav audio.wav --inspected` validates separately exported artifacts. When a
SwanSong play bridge returns `deterministicTrace` or
`deterministicTraceBase64`, `swan play` writes `trace.swtr`, `trace.json`, and
`outcome-report.json` and gates the scenario automatically.

The official SwanSong bridge obtains this payload from an opt-in `SWMB` v2
diagnostic mailbox in internal RAM. It validates structure, aggregate counts,
ring order, and the retained-record checksum inside SwanSong, then returns only
canonical `SWTR` bytes. Raw memory never crosses the bridge. The request must
set both `captureSDKTrace=true` and `confirmShareSDKTrace=true`; `swan play`
does this automatically. Build the cartridge with `swan build --trace` first.
A normal or release ROM has no mailbox, so play evidence still works but no
semantic trace is returned.

`requireCompleteTrace` defaults false because a long plan may exceed the ring.
Set it true only when the plan fits the configured capacity or a streaming
bridge guarantees that no record was dropped. Outcome reports supplement, but
never replace, inspection of the returned PNG and WAV.
