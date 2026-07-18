# SwanSong SDK 0.3.0 release notes

SwanSong SDK 0.3 turns the 0.2 tool suite into a stronger game-production and
release boundary. It is still a pre-1.0 release: the public API is usable and
tested, but the 1.0 freeze remains gated on the full Originals migration and
hardware/evidence completion.

## Make and debug games

`swan author` now owns safe, versioned, project-local documents for tilemaps,
sprite animation and hitboxes, palettes and mono mapping, collision paths,
scene flow, and audio timelines. Authoring exports are deterministic and always
state that they are not gameplay evidence. `swan minimize` reduces a failing
exact-frame plan through SwanSong; `swan replay` produces an inspectable frame
timeline bound to checkpoints, traces, PNGs, WAVs, and structured evidence.

The audio sequencer can pause and resume without resetting its row or fixed-
point phase. Play contracts can require audible, intentionally silent, or
unconstrained audio. All three modes still require a non-empty decoded WAV,
inspection, and exact evidence hashes.

Session reset now also resets the WonderSwan sound hardware after stopping the
logical sequencer. The framework restores its wavetable and output routing but
leaves every channel silent, giving reset evidence an exact history-independent
audio boundary. WonderSwan does not expose its wavetable sample offset to
software, so games that need bit-exact reset evidence must keep that boundary
silent; explicitly restarting a wavetable song is deterministic at the
sequencer level but cannot promise identical raw PCM phase across histories.

## Release with dependency evidence

`swan release` now emits deterministic SPDX 2.3 and CycloneDX 1.6 bills of
materials and an in-toto Statement with a SLSA provenance predicate. Packaging
fails before any ZIP is written when the project SDK revision, toolchain-lock
digest, pinned Wonderful packages, or canonical image digest is absent or
mismatched. These records supplement the existing evidence observations and
sorted checksums; they do not claim signing or hardware provenance.

## Production canaries

Dewdrop Dash and Signal Orchard were created from the public arcade-action and
grid-tactics recipes. They use portable rule models, five fresh-boot contracts,
project-owned four-color art, and real 128 KiB WSC builds. CI installs the SDK
wheel, scrubs source-checkout imports, scaffolds each recipe, applies only the
game-owned files, then runs assets, host tests, build, and resource report.

Friction from these canaries became cross-platform authoring path validation,
recipe audio expectations, exact sequencer pause/resume, canary regression
tests, supply-chain records, and the isolated-wheel production gate.
