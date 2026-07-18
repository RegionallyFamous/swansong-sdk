# Analysis and laboratory APIs

SwanSong SDK's analysis modules are Python 3.11 standard-library tools. They
prepare plans and inspect declared artifacts; they never emulate a ROM. Run
shipping cartridges and collect PNG, WAV, input-log, and structured evidence
through SwanSong, then pass those artifacts to these APIs.

Every top-level result has a stable schema and deterministic `to_dict()` form
for CLI, Desktop, CI, and Codex integrations.

## Record editable scenarios

`swansong_sdk.scenario.record_frame_log(log)` accepts SwanSong Desktop's
`swan-song-input-frame-log-v2` export. It requires:

- `droppedFrameCount` equal to zero;
- `frames` to match `totalFrameCount` exactly;
- contiguous `sequenceIndex` values beginning at zero; and
- each frame's `effectiveInputs` to contain known WonderSwan input names.

The importer lowercases input names, removes duplicate names, compresses
unchanged frames into transitions, and guarantees a neutral frame 0. If the
captured frame 0 is held, the recording is shifted one frame to preserve both
the neutral boot and the observed press. Rapid press/release/press sequences
remain legal exact-frame observations; generated fuzz plans still insert
longer neutral gaps deliberately. The result uses
`swansong-scenario-record-report-v1`; its `plan` uses the executable
`swan-song-frame-input-plan-v1` contract.

For hand-authored or timestamped recordings, use `ScenarioRecording.record`,
`edit`, `delete`, and `to_plan`. Timestamps are converted with an explicit
rational refresh rate, avoiding platform-dependent floating-point rounding.

## Compare SwanSong evidence

`swansong_sdk.evidence.diff_evidence(...)` returns
`swansong-evidence-diff-v1`. PNG comparison reports dimensions, SHA-256,
unique colors, transparency, changed pixels, ratio, bounding box, and channel
deltas. WAV comparison accepts uncompressed 8/16/24/32-bit PCM and reports
format metadata, peak/RMS amplitude, changed samples, and PCM deltas.

`EvidenceThresholds` controls channel/sample tolerances, changed pixel/sample
ratios, and normalized RMS delta. Defaults are exact. The report always keeps
exact measurements even when a configured threshold classifies the difference
as non-meaningful. Structured evidence mappings are flattened and compared by
stable JSON paths.

## Generate and judge fuzz traces

`swansong_sdk.fuzzing.generate_fuzz_plan(...)` uses a checked xorshift32 seed
and returns `swansong-fuzz-report-v1` containing a valid exact-frame SwanSong
plan. Generated ordinary presses include the plan contract's required neutral
release frames. The generator does not run the plan.

`evaluate_trace(...)` consumes a declared frame trace and optional allowed
state transitions. It reports declared crashes/hangs/timeouts, invalid state
transitions, dead ends after meaningful input, and canonical reset divergence.
Dead-end checks require an explicit `progressMarker` or `stateHash`; unchanged
screenshots alone are not treated as proof of a dead end.

## Profile frame and resource pressure

`swansong_sdk.profiler.profile_resources(...)` combines a manifest object or
mapping, `swansong-resource-report-v1`, and optional declared frame trace. Its
`swansong-profile-report-v1` output contains peak tiles, palettes, visible
sprites, sprites per scanline, dirty pixels, dirty display ratio, and frame
time. Findings identify static scene and observed-frame budget overruns.

Sprite scanline pressure can be calculated from each frame's sprite positions,
or consumed from declared aggregate values. Frame timing defaults to the native
refresh budget and dirty-region warnings default to half the 224×144 display;
both thresholds are explicit arguments.

## Preview asset optimization

`swansong_sdk.optimize.preview_asset_optimization(...)` accepts a PNG path,
an in-memory `Image`, or an asset-id mapping. The
`swansong-asset-optimization-report-v1` result reports:

- source, exact-deduplicated, and flip-deduplicated tile counts;
- 2BPP byte savings from flip reuse;
- per-color usage and deterministic four-color reduction mappings; and
- a four-shade mono preview as indexed pixels and a base64 PNG.

This is a preview only. It does not modify source art. The palette suggestion
uses frequency followed by nearest-RGBA mapping, so an artist should review it
before accepting a reduction.

## Exercise saves and RTC behavior

`swansong_sdk.laboratory.run_laboratory()` returns
`swansong-laboratory-report-v1`. `JournalModel` mirrors the SDK's two-slot,
24-byte-header, generation, commit marker, and CRC ordering over deterministic
byte storage. The default matrix covers empty media, corrupt newest data,
interrupted payload commit, schema mismatch, and capacity failure.

The RTC matrix covers fixed boot capture, invalid BCD, unavailable hardware,
power loss, and explicit time travel at a new boot-capture boundary. The model
does not consult the host clock. It reinforces the runtime rule that games may
inject a captured RTC value into deterministic state but must not read live RTC
during updates.
