# SwanSong Desktop integration

SwanSong Desktop is the intended unified interface for the SDK. The SDK remains
a separately testable, reusable headless package, while Desktop discovers and
invokes the exact same `swan` commands. Desktop must not fork manifest parsing,
asset conversion, Wonderful invocation, budgets, or play-contract logic.

## Product surface

Desktop should expose one project workspace with:

- New Project, backed by `swan new` and the three recipe identifiers.
- Manifest editing with `schema/swan.schema.json` validation and generated
  controls/resource previews.
- Assets, Build, Test, and Report actions backed by the corresponding `swan`
  commands and their stable JSON outputs.
- Play Contract selection backed by the checked-in scenario metadata and
  SwanSong's native deterministic executor.
- Evidence review showing the complete input plan, full native PNG, WAV audio
  metrics/playback, build identity, resource report, and replay comparison.
- A diagnostics console that preserves compiler and generator output without
  requiring the user to leave SwanSong.

## Integration boundary

The first Desktop integration may launch the bundled CLI in a subprocess. A
later in-process bridge may call the Python package, but it must preserve the
same command contracts and filesystem outputs so CI and non-Desktop workflows
remain identical. Desktop supplies an explicit SDK location; generated project
Makefiles receive that location through `SWANSONG_SDK_DIR`.

The SDK calls SwanSong only through its deterministic MCP playtest contract.
When hosted inside Desktop, the executor may be injected directly instead of
launching a second process, but the request and evidence schemas remain the
same. No alternate emulator or acceptance path is permitted.

For replay debugging, Desktop should invoke `swan replay --json` and render its
ordered `timeline` and `inputSegments`; it should not reinterpret raw plans or
evidence hashes. A recorded failing plan can be handed to `swan minimize` with
a checked `swansong-failure-predicate-v1`. Progress UI may display the final
`swansong-minimize-report-v1`, but cancellation must discard an unverified
candidate rather than writing it as the minimized result.

## Distribution

Desktop bundles a tagged SDK release, its schema, recipes, Python runtime, and
the pinned Wonderful package manifest. Projects record the SDK tag and may opt
into a newer installed release. The UI must show the resolved SDK, Wonderful,
SwanSong engine, and manifest-schema versions on every build and evidence run.

This keeps all tools in one place for players and developers while retaining a
single implementation that can also run in CI, a terminal, or an agent.
