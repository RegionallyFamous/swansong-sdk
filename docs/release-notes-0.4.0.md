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
