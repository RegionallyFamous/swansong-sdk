#ifndef SWAN_COLLISION_H
#define SWAN_COLLISION_H

#include <stdbool.h>
#include <stdint.h>

typedef struct {
    int16_t x;
    int16_t y;
    uint16_t width;
    uint16_t height;
} swan_aabb_t;

typedef struct {
    const uint8_t *flags;
    uint8_t width;
    uint8_t height;
    uint8_t tile_width;
    uint8_t tile_height;
    uint8_t solid_mask;
    bool outside_solid;
} swan_tile_collision_map_t;

bool swan_aabb_overlaps(const swan_aabb_t *a, const swan_aabb_t *b);
bool swan_aabb_contains(const swan_aabb_t *box, int16_t x, int16_t y);
bool swan_tile_collision_aabb(const swan_tile_collision_map_t *map,
                              const swan_aabb_t *box);

#endif
