# Signal Orchard

This complete WonderSwan canary was created through SwanSong SDK's public
`grid-tactics` recipe. Route two wind-up orchard keepers onto radio-flower
beacons before four storm turns expire; the center stone blocks movement.

```sh
python3 -m pip install -e "$SWANSONG_SDK_DIR"
swan assets
swan test
swan build
swan report --json
swan play neutral
```

Set `SWANSONG_SDK_DIR` when the SDK is not checked out beside this project.
`swan play` accepts only SwanSong's deterministic MCP server and writes the
inspected PNG, WAV, and evidence JSON under `build/swansong/`.

The portable model is shared by the ROM and host test. Its art is project-owned
four-color Imagegen source compiled through the Wonderful asset lane; the SDK
contains no Signal Orchard-specific runtime changes.
