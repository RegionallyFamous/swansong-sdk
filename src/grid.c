#include <string.h>

#include <swan/grid.h>

static bool valid_cell(const swan_grid_cursor_t *cursor, uint8_t x, uint8_t y) {
    return cursor != 0 && x < cursor->width && y < cursor->height;
}

static uint16_t cell_index(const swan_grid_cursor_t *cursor,
                           uint8_t x, uint8_t y) {
    return (uint16_t)y * cursor->width + x;
}

static uint8_t wrapped_axis(int16_t value, uint8_t limit) {
    int16_t wrapped = (int16_t)(value % limit);
    if (wrapped < 0) wrapped = (int16_t)(wrapped + limit);
    return (uint8_t)wrapped;
}

static uint8_t clamped_axis(int16_t value, uint8_t limit) {
    if (value < 0) return 0;
    if (value >= limit) return (uint8_t)(limit - 1u);
    return (uint8_t)value;
}

bool swan_grid_cursor_init(swan_grid_cursor_t *cursor, uint8_t width,
                           uint8_t height, bool wrap) {
    if (cursor == 0 || width == 0 || height == 0 ||
        width > SWAN_GRID_MAX_WIDTH || height > SWAN_GRID_MAX_HEIGHT)
        return false;
    memset(cursor, 0, sizeof(*cursor));
    cursor->width = width;
    cursor->height = height;
    cursor->wrap = wrap;
    return true;
}

bool swan_grid_cursor_set(swan_grid_cursor_t *cursor, uint8_t x, uint8_t y) {
    if (!valid_cell(cursor, x, y) || (cursor->x == x && cursor->y == y))
        return false;
    cursor->x = x;
    cursor->y = y;
    return true;
}

bool swan_grid_cursor_move(swan_grid_cursor_t *cursor, int8_t dx, int8_t dy) {
    uint8_t x;
    uint8_t y;
    if (cursor == 0 || cursor->width == 0 || cursor->height == 0)
        return false;
    if (cursor->wrap) {
        x = wrapped_axis((int16_t)cursor->x + dx, cursor->width);
        y = wrapped_axis((int16_t)cursor->y + dy, cursor->height);
    } else {
        x = clamped_axis((int16_t)cursor->x + dx, cursor->width);
        y = clamped_axis((int16_t)cursor->y + dy, cursor->height);
    }
    return swan_grid_cursor_set(cursor, x, y);
}

bool swan_grid_cursor_is_selected(const swan_grid_cursor_t *cursor,
                                  uint8_t x, uint8_t y) {
    uint16_t index;
    if (!valid_cell(cursor, x, y)) return false;
    index = cell_index(cursor, x, y);
    return (cursor->selected[index >> 3] &
            (uint8_t)(1u << (index & 7u))) != 0;
}

bool swan_grid_cursor_select(swan_grid_cursor_t *cursor, uint8_t x, uint8_t y,
                             bool selected) {
    uint16_t index;
    uint8_t *byte;
    uint8_t mask;
    bool current;
    if (!valid_cell(cursor, x, y)) return false;
    index = cell_index(cursor, x, y);
    byte = &cursor->selected[index >> 3];
    mask = (uint8_t)(1u << (index & 7u));
    current = (*byte & mask) != 0;
    if (current == selected) return false;
    if (selected) {
        *byte |= mask;
        ++cursor->selected_count;
    } else {
        *byte &= (uint8_t)~mask;
        --cursor->selected_count;
    }
    return true;
}

bool swan_grid_cursor_toggle(swan_grid_cursor_t *cursor) {
    if (cursor == 0) return false;
    return swan_grid_cursor_select(cursor, cursor->x, cursor->y,
        !swan_grid_cursor_is_selected(cursor, cursor->x, cursor->y));
}

void swan_grid_cursor_clear_selection(swan_grid_cursor_t *cursor) {
    if (cursor == 0) return;
    memset(cursor->selected, 0, sizeof(cursor->selected));
    cursor->selected_count = 0;
}
