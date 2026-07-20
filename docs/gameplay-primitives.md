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
