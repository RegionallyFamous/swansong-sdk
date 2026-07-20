#ifndef SWAN_TILE_GRID_H
#define SWAN_TILE_GRID_H

#include <stdbool.h>
#include <stdint.h>

#define SWAN_TILE_GRID_MAX_WIDTH 32u
#define SWAN_TILE_GRID_MAX_HEIGHT 32u
#define SWAN_TILE_GRID_MAX_CELLS \
    (SWAN_TILE_GRID_MAX_WIDTH * SWAN_TILE_GRID_MAX_HEIGHT)
#define SWAN_TILE_GRID_DIRTY_BYTES (SWAN_TILE_GRID_MAX_CELLS / 8u)

typedef struct {
    uint16_t cells[SWAN_TILE_GRID_MAX_CELLS];
    uint8_t dirty[SWAN_TILE_GRID_DIRTY_BYTES];
    uint16_t cell_count;
    uint16_t dirty_count;
    uint8_t width;
    uint8_t height;
} swan_tile_grid_t;

typedef struct {
    uint16_t value;
    uint8_t x;
    uint8_t y;
} swan_tile_change_t;

bool swan_tile_grid_init(swan_tile_grid_t *grid, uint8_t width,
                         uint8_t height, uint16_t initial_value);
uint16_t swan_tile_grid_get(const swan_tile_grid_t *grid, uint8_t x, uint8_t y);
bool swan_tile_grid_set(swan_tile_grid_t *grid, uint8_t x, uint8_t y,
                        uint16_t value);
uint16_t swan_tile_grid_sync(swan_tile_grid_t *grid, const uint16_t *values,
                             uint16_t value_count);
void swan_tile_grid_invalidate_all(swan_tile_grid_t *grid);
void swan_tile_grid_clear_dirty(swan_tile_grid_t *grid);
bool swan_tile_grid_is_dirty(const swan_tile_grid_t *grid, uint8_t x, uint8_t y);
bool swan_tile_grid_next_dirty(const swan_tile_grid_t *grid, uint16_t *cursor,
                               swan_tile_change_t *change);

#endif
