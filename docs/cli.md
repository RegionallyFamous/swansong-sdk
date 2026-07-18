# `swan` command reference

## `swan sdk-path`

Prints the source-checkout or installed wheel path containing the C runtime,
headers, build fragment, schema, recipes, and documentation. Generated
Makefiles use this command so pip-installed SDKs build into the game's own
capacity-keyed `build/swansong-sdk-*` directory instead of writing into the
Python prefix.

## `swan hardware-tile-capacity [--project PATH]`

Prints `512` for a `mono-compatible` manifest and `1024` for a
`color-required` manifest. Generated Makefiles use the value when compiling
the static runtime, keeping linker-owned screens in mono-visible memory for a
compatible build while allowing both Color tile banks where safe.

## `swan new NAME --template RECIPE`

Creates a new, nonempty game scaffold. Names use lowercase kebab-case. Recipes
are `arcade-action`, `menu-puzzle`, and `grid-tactics`. `--directory` selects a
different destination; existing nonempty directories are never overwritten.

## `swan assets [--project PATH]`

Loads and validates the nearest `swan.toml`, hashes every source asset, wraps
Wonderful `wf-process`/SuperFamiconv for 2BPP graphics, generates project
interfaces and metadata, and enforces all non-ROM budgets. SwanSong removes
Wonderful's wall-clock banner so output is byte-stable on an unchanged input
tree.

## `swan build [--project PATH] [--target TARGET]`

Runs asset generation, invokes Make and Wonderful, then reports resource usage.
The command fails on generation, compiler, linker, ROM-budget, or 8 MiB ceiling
errors. Every project builds a Color `.wsc` as the primary artifact. Projects
declaring `mono-compatible` also build a WonderSwan `.ws` validation cartridge
from the same stage-1 ELF and generated mono footer.

## `swan test [--project PATH]`

Regenerates derived files and runs the project's `make test` target. Recipes
compile the exact portable model C used by the cartridge into a native host
test executable.

## `swan report [--project PATH] [--json]`

Reports ROM bytes, declared game work RAM, Wonderful-linked total internal RAM,
its separately linked 16 KiB mono and 48 KiB Color-extension areas, peak scene
tiles and palettes, declared sprites and scanline pressure, and source audio
bytes. Each linked area is checked against its physical hardware ceiling; the
declared game reservation is checked against its project budget. JSON output uses the
`swansong-resource-report-v1` contract.

## `swan play SCENARIO [--project PATH]`

Loads a declared fresh-boot frame plan and sends it exclusively to SwanSong's
`swansong_playtest_plan` MCP tool. It requires screenshot, WAV, and structured
evidence, verifies an identical second replay by default, and stores the media
under `build/swansong`. `--no-verify-replay` is intended only for interactive
diagnosis and must not be used for an acceptance result.

## swan doctor

Usage: swan doctor [--project PATH] [--timeout SECONDS] [--json]

Runs a read-only environment audit. Doctor validates Python 3.11+, the complete
SDK payload and matching Python/runtime versions, safe project/source/asset and
play-plan paths, the manifest and its content-addressed SDK pin, the generated wfconfig.toml, the pinned
Wonderful wswan/medium tools, and SwanSong's JSON-RPC initialize interface. It
exits nonzero if any check fails.

The SwanSong probe sends one newline-terminated initialize request and accepts
the matching response without requiring the long-lived MCP server to exit. The
response deadline is bounded by `--timeout`, and cleanup escalates from
termination to a forced stop; malformed, errored, silent, and non-SwanSong
responders still fail the check.

The JSON form emits one deterministic swansong-doctor-report-v1 object with
an ok boolean and ordered checks. Each check has a stable id, status, message,
and optional details object. Reports contain no clock time or measured
duration, so Desktop and CI can consume the contract without parsing prose.

## swan dev

Usage: swan dev [--project PATH] [--scenario ID] [--once]

Builds the project, executes a declared scenario through the existing
swan play contract, then polls swan.toml, Makefile, src, assets, tests, and
every declared asset source. Changes are debounced; generated build and release
outputs are excluded to prevent rebuild loops. The default scenario is
interaction, or the first declared scenario. Every rebuild and replay has a
bounded --timeout.

--once performs one build/replay and exits. --poll-cycles N bounds the watcher
by filesystem polls. --test-mode removes sleeps and defaults to zero poll
cycles, ensuring an automated invocation cannot hang. Polling behavior is
otherwise controlled with --poll-interval and --debounce.

The JSON form streams deterministic JSON Lines. Every line uses
swansong-dev-event-v1 and includes sequence, type, project, and scenario plus
event-specific changed, gate, status, builds, or pollCycles fields. Sequence
numbers start at zero for each invocation. Events deliberately omit timestamps
and durations.

## swan scenario-record

Usage: swan scenario-record --project PATH --input-log LOG --output PLAN [--json]

Converts SwanSong Desktop's actual `swan-song-input-frame-log-v2` capture into
an editable exact-frame plan. The command refuses dropped or noncontiguous
frames, normalizes controls, compresses unchanged inputs, preserves a neutral
fresh boot, and writes `swan-song-frame-input-plan-v1`. JSON output uses
`swansong-scenario-record-report-v1`.

## swan author

Usage: swan author create KIND ID [--project PATH] [--output DOCUMENT] [--json]

Usage: swan author validate DOCUMENT [--project PATH] [--json]

Usage: swan author report DOCUMENT [--project PATH] [--output REPORT] [--json]

Usage: swan author export DOCUMENT --output SOURCE [--project PATH] [--json]

Provides the headless contracts behind Studio's tilemap/layer, sprite
animation/hitbox, palette/mono, collision/path, scene-flow, and audio
pattern/instrument editors. Kinds are `tilemap`, `sprites`, `palette`,
`collision`, `scene-flow`, and `audio`. Create defaults to
`authoring/ID.KIND.json`.

All paths are resolved against the project containing `swan.toml` and must
remain within it through symlinks. Every write exclusively creates a new file;
existing documents, sources, reports, and exports are never overwritten. The
formats contain identifiers and data only—no command or script field is
accepted, and Author never launches another tool.

Audio exports directly to the existing SDK music TOML format. Palette exports
a deterministic PNG swatch. The other four kinds export a hash-bound
`swansong-author-handoff-v1` document that states the existing Wonderful asset
lane or portable-model integration point. They do not introduce a competing
compiler. Reports use `swansong-author-operation-report-v1`, always set
`gameplayEvidence` false, and never claim a visual or audio preview is ROM
evidence. See [Visual authoring contracts](visual-authoring.md).

## swan minimize

Usage: swan minimize --project PATH --plan PLAN --predicate PREDICATE --output PLAN [--json]

Delta-reduces a failing exact-frame input plan while preserving a declared,
machine-checkable result. The predicate must use
`swansong-failure-predicate-v1` and select one of two closed forms:

- `structured-evidence` compares the value at an RFC 6901 JSON pointer with an
  exact JSON value. Each candidate is run with SwanSong's normal bit-exact
  replay verification.
- `execution-error` compares the complete SwanSong error message with
  `messageEquals`. Each candidate is executed twice and both errors must be
  byte-identical. A timeout, transport failure, or different message therefore
  cannot accidentally preserve an unrelated failure.

Frame zero is immutable and remains neutral. The reducer expands the plan into
effective frame input, applies deterministic delta debugging to remove frame
chunks, removes individual chord inputs, and repeats until it is one-minimal or
`--max-evaluations` is reached. Removing frames shifts later input earlier, so
the result minimizes unnecessary waits as well as actions. The default limit is
256 distinct candidates; the cache, accepted reductions, limit status, source
and minimized digests, and exact observed results are recorded in
`swansong-minimize-report-v1`.

The source plan must already satisfy the predicate. The final candidate is
fresh-boot verified once more before the output plan is written. Structured
evidence is stored under `build/swansong/minimize` by default; use
`--evidence-output` to select another directory and `--report` to persist the
report. SwanSong is the only execution backend.

Example structured-evidence predicate:

```json
{
  "schema": "swansong-failure-predicate-v1",
  "kind": "structured-evidence",
  "path": "/failure/code",
  "equals": "invalid-transition"
}
```

## swan replay

Usage: swan replay --project PATH (--plan PLAN | --scenario ID) [--checkpoints FILE] [--evidence ID=DIR] [--trace FILE] [--json]

Builds a read-only frame timeline for SwanSong Studio, CI, or a game-playing
agent. This command does not emulate or execute the cartridge—`swan play`
remains the execution command. The report combines:

- compact effective-input segments and indexed input-change points from a
  validated `swan-song-frame-input-plan-v1`;
- declared scenario goal, required checks, and audible/silent/any audio
  expectation when
  `--scenario` is used;
- ordered `swansong-replay-checkpoints-v1` annotations;
- one or more fully decoded PNG/WAV/structured evidence directories bound with
  repeatable `--evidence ID=DIRECTORY`; and
- optional per-frame trace summaries, with scalar fields retained and large
  collections represented by counts.

Checkpoint evidence IDs must resolve to supplied evidence. The report calls out
unbound evidence, hashes the plan, trace, PNG, WAV, and structured evidence,
and provides a sorted `timeline` suitable for a scrubber without expanding
every unchanged frame. JSON uses `swansong-replay-report-v1`; `--output`
writes the same deterministic report to a file.

Checkpoint annotations use this contract:

```json
{
  "schema": "swansong-replay-checkpoints-v1",
  "checkpoints": [
    {
      "id": "movement-stops",
      "frameIndex": 143,
      "label": "Player stops responding",
      "requiredCheck": "directional controls remain operational",
      "evidence": ["failure"]
    }
  ]
}
```

## swan evidence-diff

Usage: swan evidence-diff --before DIR --after DIR [--json]

Compares both directories' `frame.png`, `audio.wav`, and `evidence.json`.
Pixels and uncompressed PCM samples are decoded and measured; hashes are only
identity metadata. Tolerance flags cover channel delta, changed-pixel ratio,
sample delta, changed-sample ratio, and RMS delta. `--fail-on-difference`
turns a meaningful change into a regression gate. JSON uses
`swansong-evidence-diff-v1`.

## swan fuzz

Usage: swan fuzz --project PATH --seed N --cases N --frames N [--json]

Generates deterministic valid input plans, runs a neutral baseline and every
case through SwanSong, and requires an identical fresh-boot replay for each.
Crashes, execution failures, and reset divergence fail the run. A case ending
on the neutral raster is marked for PNG/WAV review, not automatically called a
dead end. A transport-clean run returns `review`, never `pass`, until a person
or game-playing agent inspects its PNG/WAV evidence. `--generate-only` is an
offline plan-preview mode and never claims a ROM verdict. JSON uses
`swansong-fuzz-report-v1`.

## swan profile

Usage: swan profile --project PATH [--trace TRACE.json] [--json]

Combines the manifest and generated resource report with an optional exported
frame trace. It reports tile and palette ownership, visible sprites,
per-scanline pressure, dirty regions, and frame-time budgets using
`swansong-profile-report-v1`. Static values remain useful when the engine has
not exported a trace; the report states how many frames it actually analyzed.

## swan optimize

Usage: swan optimize --project PATH [--asset ID] [--output REPORT] [--json]

Previews exact and flip-aware tile deduplication, deterministic four-color
palette reduction, and a mono PNG variant without modifying source art. Empty
projects return a valid zero-asset report. The artist-reviewed preview uses
`swansong-asset-optimization-report-v1`.

## swan lab

Usage: swan lab --project PATH [--case all|save|rtc] [--rtc-seed UNIX] [--json]

Runs the deterministic two-slot save journal and boot-time RTC laboratory.
Cases cover empty media, corrupt newest data, interrupted commit, schema and
capacity errors, invalid BCD, unavailable RTC, power loss, and time travel at
a new boot boundary. This is a runtime-contract model, not an emulator; JSON
uses `swansong-laboratory-report-v1`.

## swan release

Usage: swan release [--project PATH] [--output PATH] [--notes PATH] [--json]

Runs, in order, the assets, build, host-test, JSON resource-report, and every
declared SwanSong play gate. Each child command is invoked without a shell and
with a timeout. A failed, timed-out, malformed, or missing gate stops the
release before packaging.

Each play gate must also have `build/swansong/<scenario>/observation.json` using
`swan-song-evidence-observation-v1`. The record binds the ROM, PNG, and WAV
hashes, names an observer, asserts PNG and WAV inspection, records a `pass`
verdict, and has one non-empty observation for every manifest
`required_checks` entry. Release fully decodes a non-empty hash-bound WAV in
all modes, requires non-zero PCM for `audible`, and requires zero PCM for
`silent`. Only a person or
game-playing agent that inspected the current media should create this record;
execution success and changing hashes cannot create it automatically.

On success, Release creates a ZIP containing the Color ROM, the mono validation
ROM when present, the resource report, release notes, PNG/WAV/JSON evidence for
each declared scenario, its inspected observation record, pinned SDK/toolchain
provenance, SPDX and CycloneDX SBOMs, an unsigned in-toto/SLSA provenance
statement, and sorted SHA-256 checksums. SDK provenance includes both the
semantic version and
deterministic payload revision, and Release refuses a resolved SDK that differs
from `[sdk]` in `swan.toml`. Toolchain provenance must contain an immutable
image digest and the exact package set declared by `toolchain.lock`; incomplete
or mutable provenance fails before packaging. See
[Supply chain](supply-chain.md) for the artifact contract. PNG and WAV files
are fully decoded before acceptance. ZIP members are sorted
and use a fixed timestamp and mode, making unchanged inputs byte-identical.
--output accepts a ZIP filename or destination directory. --notes supplies
Markdown; otherwise the SDK generates deterministic notes from the manifest.

The JSON form emits one swansong-release-report-v1 object with ok, project and
version, ordered gates, sorted artifact hashes, package path, and package
SHA-256. A failed JSON invocation emits the same schema with ok false, a stable
error code, and no package.

An observation record has this shape; hashes and check names must match the
fresh SwanSong evidence and manifest exactly:

```json
{
  "schema": "swan-song-evidence-observation-v1",
  "scenario": "interaction",
  "verdict": "pass",
  "pngInspected": true,
  "wavInspected": true,
  "observer": "release playtester",
  "romSHA256": "...",
  "capturePNG_SHA256": "...",
  "finalWindowWAVSHA256": "...",
  "requiredChecks": {
    "cursor visibly moved": "Cursor moved one cell right after X2."
  }
}
```
