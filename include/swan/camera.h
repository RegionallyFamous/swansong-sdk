#ifndef SWAN_CAMERA_H
#define SWAN_CAMERA_H

#include <stdbool.h>
#include <stdint.h>

#include <swan/gfx.h>

typedef struct {
    int16_t min_x;
    int16_t min_y;
    int16_t max_x;
    int16_t max_y;
} swan_camera_bounds_t;

bool swan_camera_clamp(swan_camera_t *camera,
                       const swan_camera_bounds_t *bounds);
bool swan_camera_move_clamped(swan_camera_t *camera, int16_t dx, int16_t dy,
                              const swan_camera_bounds_t *bounds);
bool swan_camera_center_clamped(swan_camera_t *camera, int16_t target_x,
                                int16_t target_y, uint16_t viewport_width,
                                uint16_t viewport_height,
                                const swan_camera_bounds_t *bounds);

#endif
