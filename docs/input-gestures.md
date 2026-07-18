# Deterministic input gestures

SwanSong samples hardware once per frame, maps raw keys to semantic actions,
and derives gestures before the immutable `swan_frame_t` reaches the current
scene. Gesture recognition uses fixed-size state, integer frame counts, and no
clock, allocation, or hidden input read, so a recorded input plan produces the
same events on host and cartridge builds.

Projects configure timing and chords in `swan.toml`:

```toml
[controls.actions]
move = ["X1"]
focus = ["Y2"]
fire = ["A"]

[controls.gestures]
tap_max_frames = 8
double_tap_window = 12
hold_threshold = 20

[controls.chords]
focus_fire = ["focus", "fire"]
```

`actions_tapped` fires on release when the action was held for no more than
`tap_max_frames` and never crossed the hold threshold. Every qualifying short
release is a tap. `actions_double_tapped` additionally fires on the second tap
when it completes inside `double_tap_window`; a third tap starts a new pair.

`actions_hold_started` fires once, on the sampled frame that reaches
`hold_threshold`. `actions_held_long` remains set until release, and
`actions_released_after_hold` fires for one frame on that release. A press
longer than the tap limit but shorter than the hold threshold produces neither
a tap nor a hold event.

`chords_pressed` fires only when all configured semantic actions begin in the
same sampled frame. It does not fire when one member was already held, which
prevents staggered directions or buttons from becoming an accidental command.
Use `swan_chord_pressed(SWAN_CHORD_FOCUS_FIRE)` or inspect the immutable mask.

The matching helpers are `swan_action_tapped`,
`swan_action_double_tapped`, `swan_action_hold_started`,
`swan_action_held_long`, and `swan_action_released_after_hold`. Existing
pressed, held, released, and repeated fields and helpers are unchanged.

`swan_input_drain()` clears held input, partial taps, pending double taps, hold
progress, and gesture events. Held physical keys remain drained until released,
so an intro exit or `swan_core_reset_session()` cannot leak a gesture into the
next scene or session.

Generated SwanSong play contracts include the timing values and named chord
members under `inputGestures`. Scenario recorders and game-playing agents can
therefore construct intentional taps, holds, and simultaneous dual-cluster
commands without inferring timing from screenshots.
