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
