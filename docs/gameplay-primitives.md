# Gameplay primitives

SwanSong 0.5 ships a small, static layer between raw graphics/input and a
game's portable rules. These modules do not impose a genre architecture and do
not allocate memory.

| Header | Purpose | Fixed limit |
|---|---|---|
| `swan/animation.h` | deterministic sprite frame playback | caller-owned animation |
| `swan/camera.h` | clamp, move, and center a 2D camera | signed 16-bit world |
| `swan/collision.h` | AABB and flagged tile collision | caller-owned map |
| `swan/tile_grid.h` | dirty-cell cache for tile layers | 32 × 32 cells |
| `swan/grid.h` | cursor movement and selected cells | 16 × 16 cells |
| `swan/pool.h` | stable reusable object slots | 128 slots |
| `swan/path.h` | iterative four-way BFS | 256 cells |
| `swan/timing.h` | pause-safe frame timers and nested timing grades | caller-owned timer |
| `swan/score.h` | saturating scores, timed chains, and multiplier ladders | caller-owned score |
| `swan/records.h` | stable descending records and canonical save bytes | 255 caller-owned entries |
| `swan/motion.h` | 8-fractional-bit velocity, acceleration, braking, and bounce | signed 32-bit state |
| `swan/state.h` | canonical little-endian FNV-1a state hashes | 65,535 counted bytes |

Use these helpers in cartridge presentation code while keeping game rules in a
portable model compiled by both the ROM and host tests. A model's trace hash
must append each logical field explicitly with `swan_state_hash_*`; hashing a C
struct directly is not canonical because padding is compiler-dependent.

Resource exhaustion is a normal result, never an allocation attempt. Pools
return `SWAN_POOL_NONE`, pathfinding returns a capacity status, and tile grids
reject dimensions beyond their fixed backing storage. Recipes demonstrate the
same reset boundary used by the runtime: reset the model, session clock, audio,
graphics ownership, and input drain together.

## Timing and score attacks

`swan_timer_t` advances only when the game advances it, so pause, menus, and
hit-stop do not consume a countdown accidentally. `swan_timing_grade()` grades
an absolute captured input frame against caller-owned perfect/great/good
windows. `swan_timer_stop()` cancels a timer and clears its duration, elapsed
time, and progress. The runtime does not read a clock or input behind the
game's back.

`swan_score_t` combines saturating 32-bit points with a timed chain and a
caller-selected multiplier ladder. A zero chain timeout keeps a chain alive
until the game explicitly breaks it. `swan_records_insert()` maintains a
descending fixed-capacity table and inserts equal scores after existing equal
scores, so replaying the same input produces a stable ranking. Its 16-bit tag
is deliberately policy-free: games can store a packed name, stage, mode, or
replay seed. Persist records with `swan_records_serialize()` and recover them
with `swan_records_deserialize()` before passing the byte payload through
`swan_save_store()`; never persist the native C struct layout.

## Fixed-point motion

`swan_motion_t` stores position and velocity in signed 32-bit fields with eight
fractional bits. Acceleration, integration, velocity clamps, braking, and
bounded bounce use no floating point or hidden clock. Bounce restitution is
scaled from 0 (stop) through 256 (full reflection). Keep game-specific
collision shape, steering, jump, and damage rules in the portable model; this
module only supplies predictable motion arithmetic.

These additions follow the cross-year design findings in
[WWGP game-design lessons](wwgp-design-lessons.md).
