#ifndef SWAN_PATH_H
#define SWAN_PATH_H

#include <stdint.h>

#include <swan/grid.h>

#define SWAN_PATH_MAX_CELLS SWAN_GRID_MAX_CELLS

typedef enum {
    SWAN_PATH_FOUND = 0,
    SWAN_PATH_UNREACHABLE,
    SWAN_PATH_CAPACITY,
    SWAN_PATH_INVALID
} swan_path_status_t;

typedef struct {
    uint16_t queue[SWAN_PATH_MAX_CELLS];
    uint16_t parent[SWAN_PATH_MAX_CELLS];
    uint8_t visited[SWAN_PATH_MAX_CELLS / 8u];
} swan_pathfinder_t;

swan_path_status_t swan_path_find(swan_pathfinder_t *pathfinder,
                                  const uint8_t *cell_flags, uint8_t width,
                                  uint8_t height, uint8_t blocked_mask,
                                  swan_grid_point_t start,
                                  swan_grid_point_t goal,
                                  swan_grid_point_t *path,
                                  uint16_t path_capacity,
                                  uint16_t *path_length);

#endif
