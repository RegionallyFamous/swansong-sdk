# SwanSong SDK contribution rules

## Invariants

- Target Wonderful `wswan/medium` and generate `.wsc` cartridges.
- Keep runtime code C11-compatible and statically allocated. Do not introduce a
  heap, floating point, recursion, an ECS, or far function-pointer tables.
- Sample hardware input once per VBlank through the generated platform entry
  point. Game code must consume `swan_frame_t` or semantic actions.
- In `swan_scene_update`, consume the immutable frame and invalidate graphics
  only when state actually changes or an animation needs another frame.
  Unconditional gameplay invalidation can continuously rebuild background
  state and hide mutations on hardware. Keep a SwanSong ROM regression for
  any change to this rule.
- For horizontal games, the X pad maps to up X3, right X2, down X1, and left
  X4. Keep raw X/Y buttons available and express semantic rotation in the
  generated manifest bindings.
- Keep reusable policies in `include/swan` and `src`; game rules belong in a
  game or recipe model.
- Keep production model code portable so the same C file runs in host tests and
  the shipping ROM.
- Never add another emulator, capture tool, or acceptance backend. SwanSong is
  the only ROM execution path.
- Do not check in `build/`, generated code, ROMs, ELF files, screenshots, or WAV
  captures unless a release process explicitly requires an evidence fixture.

## Tooling and manifests

- `swan.toml` is the source of truth. Add schema fields in
  `python/swansong_sdk/manifest.py`, `schema/swan.schema.json`, and the manifest
  reference together.
- Generation must be byte-deterministic, stable across repeated runs, and have
  no network dependency.
- The Python package must run on Python 3.11+ with no mandatory third-party
  dependencies.
- Templates must remain useful games, not API snippets. Each needs a portable
  model, host test, ROM integration, budgets, and neutral/interaction/failure/
  reset SwanSong scenarios.

## Required checks

Run before handing off a change:

```sh
PYTHONPATH=python python3 -m unittest discover -s tests/python -v
make test
```

For changes affecting a recipe, scaffold every recipe and run `swan test`
and `swan build` against the pinned Wonderful toolchain. For runtime behavior,
run the affected contracts with `swan play` and inspect the returned PNG, WAV,
and structured evidence before reporting a pass.
