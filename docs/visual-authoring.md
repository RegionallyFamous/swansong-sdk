# Visual authoring contracts

SwanSong SDK owns the source formats and validation rules used by SwanSong
Studio's visual editors. The documents are ordinary project-owned JSON files,
usually under `authoring/`. They are deterministic, diffable, and usable from
the CLI without Desktop. Studio must edit these contracts rather than maintain
a second private representation.

Authoring output is never gameplay evidence. It does not prove that a ROM
builds, runs, displays the intended image, produces audio, or satisfies a play
contract. Only `swan play` through SwanSong and inspected PNG/WAV evidence can
do that.

## Safe command surface

```sh
swan author create tilemap overworld
swan author validate authoring/overworld.tilemap.json
swan author report authoring/overworld.tilemap.json --json
swan author export authoring/overworld.tilemap.json \
  --output assets/metadata/overworld.json
```

All four operations load the nearest `swan.toml`. Explicit input and output
paths must resolve inside that project, including through symlinks. `create`,
`report --output`, and `export` use exclusive creation and refuse an existing
destination. There is no force flag, command hook, script field, shell
interpolation, or external program invocation.

Every JSON result uses `swansong-author-operation-report-v1`, includes the
canonical document digest, deterministic metrics and findings, and sets
`gameplayEvidence` to false. Human output repeats the evidence warning.

## Document kinds

### Tilemaps and layers

`swansong-author-tilemap-v1` describes an 8×8-tile map, one or two background
layers, layer scroll origins, and sparse placed cells. Cells carry tile and
palette indices plus horizontal/vertical flip flags. Coordinates are checked
against the declared dimensions; duplicate cells in one layer are rejected.
The document references a project-relative PNG tileset source.

`swan assets` compiles the sparse layers and scroll origins into a typed,
far-ROM C descriptor while the referenced project PNG remains the Wonderful
tile source. Export can still produce a hash-bound handoff for another tool.

### Sprite animations and hitboxes

`swansong-author-sprites-v1` binds named rectangles to a project-relative PNG
sheet. Named animations contain ordered frame steps, integer frame durations,
looping, and flips. Per-frame hitboxes use `solid`, `hurt`, `attack`, or
`trigger` kinds and signed origin-relative positions. Every frame reference is
validated.

`swan assets` compiles frame rectangles, animation steps, looping/flips, and
hitboxes into typed C. The PNG remains the Wonderful sprite-sheet source.

### Palettes and mono mappings

`swansong-author-palette-v1` holds 1–16 `#RRGGBB` colors, one 0–3 mono shade
per color, and an optional transparent index. Export writes a deterministic
8-pixel-high PNG swatch that the existing graphics pipeline can decode. The
mono mapping also compiles into typed ROM data; the swatch remains an art
source/preview, not a screenshot.

### Collision regions and paths

`swansong-author-collision-v1` defines pixel bounds, open or closed region
polylines, collision kinds, and named movement paths with per-point frame
waits. All points are integer and in bounds. Export is a hash-bound JSON
handoff for a portable C game model. `swan assets` also compiles regions and
paths into typed static tables; the SDK does not introduce runtime allocation,
physics, or a second rule engine.

### Scene flow

`swansong-author-scene-flow-v1` describes named static scenes, one initial
scene, and event-labelled deferred transitions with 16-bit arguments. Events
are identifiers, not executable expressions. References and duplicate
`from`/`event` routes are rejected. Reports warn about scenes unreachable from
the initial scene. Export is an explicit handoff for the SDK's generated
static scene-dispatch boundary. `swan assets` emits typed scene and transition
tables without far-function-pointer dispatch.

### Audio patterns and instruments

`swansong-author-audio-v1` describes 1–16 native 16-sample wavetable
instruments and an ordered four-channel row timeline. Notes use MIDI-like
0–127 values, `hold`, or `off`; instruments use a declared ID or `hold`;
volumes use 0–15 or `hold`. Tempo is the existing Q8 frames-per-row value.

Export writes the exact music TOML already accepted by `swan assets`, mapping
editor IDs to deterministic instrument indices and editor-friendly hold/off
values to the runtime's 254/255 commands. It does not audition or synthesize
audio and is not WAV evidence. Use `swan audio preview` for an approximate host
audition and accept only the decoded, listened-to SwanSong cartridge WAV.

## Schema and integration inventory

The distributable schema directory includes one schema per document plus
`author-operation-report.schema.json` and `author-handoff.schema.json`.
Semantic validation in `swansong_sdk.authoring` additionally checks
cross-field rules such as references, uniqueness, coordinate bounds, and mono
mapping length that JSON Schema alone cannot fully express.

Generation writes typed headers/sources, `authoring-report.json`, and
`sources.mk` under `build/generated`. The report binds document and dependency
hashes; stale generated authoring outputs are removed when their source
document is removed.

Desktop may render previews, timelines, canvases, graphs, and property panels
from these documents. It should call `swan author validate` after edits and
show `swan author report` findings. Export status must remain visible:
`sdk-consumable`, `sdk-consumable-preview`, or `handoff-required`.
