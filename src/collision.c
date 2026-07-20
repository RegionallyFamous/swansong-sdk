#include <stdint.h>

#include <swan/collision.h>

static int32_t floor_div(int32_t value, uint8_t divisor) {
    if (value >= 0) return value / divisor;
    return -(((-value) + divisor - 1) / divisor);
}

bool swan_aabb_overlaps(const swan_aabb_t *a, const swan_aabb_t *b) {
    int32_t a_right;
    int32_t a_bottom;
    int32_t b_right;
    int32_t b_bottom;
    if (a == 0 || b == 0 || a->width == 0 || a->height == 0 ||
        b->width == 0 || b->height == 0) return false;
    a_right = (int32_t)a->x + a->width;
    a_bottom = (int32_t)a->y + a->height;
    b_right = (int32_t)b->x + b->width;
    b_bottom = (int32_t)b->y + b->height;
    return a->x < b_right && a_right > b->x &&
        a->y < b_bottom && a_bottom > b->y;
}

bool swan_aabb_contains(const swan_aabb_t *box, int16_t x, int16_t y) {
    if (box == 0 || box->width == 0 || box->height == 0) return false;
    return x >= box->x && y >= box->y &&
        (int32_t)x < (int32_t)box->x + box->width &&
        (int32_t)y < (int32_t)box->y + box->height;
}

bool swan_tile_collision_aabb(const swan_tile_collision_map_t *map,
                              const swan_aabb_t *box) {
    int32_t left;
    int32_t right;
    int32_t top;
    int32_t bottom;
    int32_t x;
    int32_t y;
    if (map == 0 || box == 0 || map->flags == 0 || map->width == 0 ||
        map->height == 0 || map->tile_width == 0 || map->tile_height == 0 ||
        box->width == 0 || box->height == 0) return false;
    left = floor_div(box->x, map->tile_width);
    right = floor_div((int32_t)box->x + box->width - 1, map->tile_width);
    top = floor_div(box->y, map->tile_height);
    bottom = floor_div((int32_t)box->y + box->height - 1, map->tile_height);
    if (map->outside_solid && (left < 0 || top < 0 || right >= map->width ||
                              bottom >= map->height)) return true;
    if (left < 0) left = 0;
    if (top < 0) top = 0;
    if (right >= map->width) right = (int32_t)map->width - 1;
    if (bottom >= map->height) bottom = (int32_t)map->height - 1;
    if (left > right || top > bottom) return false;
    for (y = top; y <= bottom; ++y) {
        for (x = left; x <= right; ++x) {
            uint16_t index = (uint16_t)y * map->width + (uint16_t)x;
            if ((map->flags[index] & map->solid_mask) != 0) return true;
        }
    }
    return false;
}
