# Framework feedback loop

Every migrated or recipe-built game is an SDK experiment. Before work starts
on the next game, record the friction found by host tests, Wonderful builds,
and inspected SwanSong play evidence. Resolve each recurring item as exactly
one or more of:

- a stable runtime or CLI API;
- a manifest or asset validation rule;
- a recipe improvement;
- a concise documentation rule;
- a host, build, or SwanSong regression test.

Do not copy a workaround into the next game. Preserve production game rules in
portable C and validate that exact file on the host and in the ROM. Treat a
successful build, a changing hash, or an uninspected capture as an observation,
not a gameplay verdict.

The first canaries produced two permanent rules:

1. Recipe Makefiles resolve the adjacent or bundled SDK through
   `SWANSONG_SDK_DIR`; they do not depend on a global Python installation or
   compile SDK sources into the game's object namespace.
2. A scene invalidates graphics only after state changes or while declared
   animation is active. SwanSong inspection caught that unconditional recipe
   invalidation hid later interaction states even though host tests passed.
3. Frame presentation never performs a whole-map or whole-sprite diagnostic
   scan. Profiling is requested explicitly, static scenery is preserved, and
   hardware-backed rectangle operations are preferred for bulk changes.
   Scenario review compares scheduled SwanSong frames with the game's session
   tick so a delivered button transition cannot be mistaken for a sampled
   gameplay action when a slow renderer misses VBlanks.

For each game, append measured ROM, RAM reservation, peak tiles, palettes,
sprites, scanline sprites, and audio bytes to its review. If a limit cannot be
measured yet, record it as a tooling gap rather than presenting the declared
reservation as measured usage.
