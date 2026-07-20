#ifndef SWAN_GRID_H
#define SWAN_GRID_H

#include <stdbool.h>
#include <stdint.h>

#define SWAN_GRID_MAX_WIDTH 16u
#define SWAN_GRID_MAX_HEIGHT 16u
#define SWAN_GRID_MAX_CELLS (SWAN_GRID_MAX_WIDTH * SWAN_GRID_MAX_HEIGHT)
#define SWAN_GRID_SELECTION_BYTES (SWAN_GRID_MAX_CELLS / 8u)

typedef struct {
    uint8_t x;
    uint8_t y;
} swan_grid_point_t;

typedef struct {
    uint8_t selected[SWAN_GRID_SELECTION_BYTES];
    uint16_t selected_count;
    uint8_t width;
    uint8_t height;
    uint8_t x;
    uint8_t y;
    bool wrap;
} swan_grid_cursor_t;

bool swan_grid_cursor_init(swan_grid_cursor_t *cursor, uint8_t width,
                           uint8_t height, bool wrap);
bool swan_grid_cursor_set(swan_grid_cursor_t *cursor, uint8_t x, uint8_t y);
bool swan_grid_cursor_move(swan_grid_cursor_t *cursor, int8_t dx, int8_t dy);
bool swan_grid_cursor_is_selected(const swan_grid_cursor_t *cursor,
                                  uint8_t x, uint8_t y);
bool swan_grid_cursor_select(swan_grid_cursor_t *cursor, uint8_t x, uint8_t y,
                             bool selected);
bool swan_grid_cursor_toggle(swan_grid_cursor_t *cursor);
void swan_grid_cursor_clear_selection(swan_grid_cursor_t *cursor);

#endif
