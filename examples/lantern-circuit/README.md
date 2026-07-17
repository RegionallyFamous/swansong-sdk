# Lantern Circuit

This WonderSwan game was created from SwanSong SDK's `grid-tactics` recipe.

```sh
python3 -m pip install -e "$SWANSONG_SDK_DIR"
swan assets
swan test
swan build
swan play neutral
```

Set `SWANSONG_SDK_DIR` when the SDK is not checked out beside this project.
`swan play` accepts only SwanSong's deterministic MCP server and writes the
inspected PNG, WAV, and evidence JSON under `build/swansong/`.
