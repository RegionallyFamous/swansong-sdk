# SwanSong SDK 0.4.0 release notes

SwanSong SDK 0.4.0 turns the lessons from the first ten SwanSong Originals and
the WonderWitch-era homebrew catalog into reusable framework contracts.

The runtime now recognizes deterministic semantic taps, double taps, hold
starts, held-long state, release-after-hold events, and up to eight generated
same-frame action chords. Draining or resetting input clears every gesture
timer, so fresh sessions remain bit-exact.

New projects can use the fourth production recipe, `utility-app`, for compact
non-game software with dual-cluster navigation, fixed-capacity editors,
long-press alternatives, journaled EEPROM persistence, audible commit feedback,
and distinct success, failure, interaction, and reset proofs.

Every recipe now declares a measured `[play].ready_frames` boundary. Asset,
play, Doctor, and release paths reject scenarios that try to press a control
before that fresh-boot boundary. Generated play contracts publish the same
value for SwanSong Studio and automated players.

Audio evidence now measures left/right energy, cue onset, silent-frame ratios,
internal dropouts, clipped samples, and loop seams. Projects can opt into
per-scenario limits without changing the existing exact PNG/WAV evidence
contract.

Normal frame presentation no longer performs a full tilemap and sprite
profiling sweep. Resource diagnostics remain exact when requested through the
profiler, while games keep their VBlank cadence during ordinary play. The
WonderSwan backend also has a native rectangular tile-fill path, and the
`utility-app` recipe preserves static scenery between updates instead of
redrawing the whole screen after each button event. Generated Makefiles also
track the resolved SDK runtime as a normal link dependency so adjacent SDK
development cannot silently replay an older archive.
