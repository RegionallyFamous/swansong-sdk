#include <string.h>

#include <swan/tile_grid.h>

static bool valid_cell(const swan_tile_grid_t *grid, uint8_t x, uint8_t y) {
    return grid != 0 && x < grid->width && y < grid->height;
}

static uint16_t cell_index(const swan_tile_grid_t *grid, uint8_t x, uint8_t y) {
    return (uint16_t)y * grid->width + x;
}

static bool dirty_at(const swan_tile_grid_t *grid, uint16_t index) {
    return (grid->dirty[index >> 3] & (uint8_t)(1u << (index & 7u))) != 0;
}

static void mark_dirty(swan_tile_grid_t *grid, uint16_t index) {
    uint8_t *byte = &grid->dirty[index >> 3];
    uint8_t mask = (uint8_t)(1u << (index & 7u));
    if ((*byte & mask) == 0) {
        *byte |= mask;
        ++grid->dirty_count;
    }
}

bool swan_tile_grid_init(swan_tile_grid_t *grid, uint8_t width,
                         uint8_t height, uint16_t initial_value) {
    uint16_t index;
    if (grid == 0 || width == 0 || height == 0 ||
        width > SWAN_TILE_GRID_MAX_WIDTH ||
        height > SWAN_TILE_GRID_MAX_HEIGHT) return false;
    memset(grid, 0, sizeof(*grid));
    grid->width = width;
    grid->height = height;
    grid->cell_count = (uint16_t)width * height;
    for (index = 0; index < grid->cell_count; ++index)
        grid->cells[index] = initial_value;
    swan_tile_grid_invalidate_all(grid);
    return true;
}

uint16_t swan_tile_grid_get(const swan_tile_grid_t *grid, uint8_t x, uint8_t y) {
    return valid_cell(grid, x, y) ? grid->cells[cell_index(grid, x, y)] : 0;
}

bool swan_tile_grid_set(swan_tile_grid_t *grid, uint8_t x, uint8_t y,
                        uint16_t value) {
    uint16_t index;
    if (!valid_cell(grid, x, y)) return false;
    index = cell_index(grid, x, y);
    if (grid->cells[index] == value) return false;
    grid->cells[index] = value;
    mark_dirty(grid, index);
    return true;
}

uint16_t swan_tile_grid_sync(swan_tile_grid_t *grid, const uint16_t *values,
                             uint16_t value_count) {
    uint16_t changed = 0;
    uint16_t index;
    if (grid == 0 || values == 0 || value_count != grid->cell_count)
        return 0;
    for (index = 0; index < value_count; ++index) {
        if (grid->cells[index] != values[index]) {
            grid->cells[index] = values[index];
            mark_dirty(grid, index);
            ++changed;
        }
    }
    return changed;
}

void swan_tile_grid_invalidate_all(swan_tile_grid_t *grid) {
    uint16_t index;
    if (grid == 0) return;
    memset(grid->dirty, 0, sizeof(grid->dirty));
    grid->dirty_count = 0;
    for (index = 0; index < grid->cell_count; ++index)
        mark_dirty(grid, index);
}

void swan_tile_grid_clear_dirty(swan_tile_grid_t *grid) {
    if (grid == 0) return;
    memset(grid->dirty, 0, sizeof(grid->dirty));
    grid->dirty_count = 0;
}

bool swan_tile_grid_is_dirty(const swan_tile_grid_t *grid, uint8_t x, uint8_t y) {
    return valid_cell(grid, x, y) && dirty_at(grid, cell_index(grid, x, y));
}

bool swan_tile_grid_next_dirty(const swan_tile_grid_t *grid, uint16_t *cursor,
                               swan_tile_change_t *change) {
    uint16_t index;
    if (grid == 0 || cursor == 0 || change == 0) return false;
    for (index = *cursor; index < grid->cell_count; ++index) {
        if (dirty_at(grid, index)) {
            change->x = (uint8_t)(index % grid->width);
            change->y = (uint8_t)(index / grid->width);
            change->value = grid->cells[index];
            *cursor = (uint16_t)(index + 1u);
            return true;
        }
    }
    *cursor = grid->cell_count;
    return false;
}
