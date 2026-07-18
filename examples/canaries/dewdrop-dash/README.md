# Dewdrop Dash

This complete WonderSwan canary was created through SwanSong SDK's public
`arcade-action` recipe. Guide a living raindrop along a leaf, gather three
seeds, avoid drying out on scorch cells, and return to the rain cup.

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
four-color Imagegen source compiled through the same Wonderful asset lane as a
third-party game; the SDK contains no Dewdrop Dash-specific runtime changes.
