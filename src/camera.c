#include <stdint.h>

#include <swan/camera.h>

static bool valid_bounds(const swan_camera_bounds_t *bounds) {
    return bounds != 0 && bounds->min_x <= bounds->max_x &&
        bounds->min_y <= bounds->max_y;
}

static int16_t clamp_axis(int32_t value, int16_t low, int16_t high) {
    if (value < low) return low;
    if (value > high) return high;
    return (int16_t)value;
}

bool swan_camera_clamp(swan_camera_t *camera,
                       const swan_camera_bounds_t *bounds) {
    if (camera == 0 || !valid_bounds(bounds)) return false;
    camera->x = clamp_axis(camera->x, bounds->min_x, bounds->max_x);
    camera->y = clamp_axis(camera->y, bounds->min_y, bounds->max_y);
    return true;
}

bool swan_camera_move_clamped(swan_camera_t *camera, int16_t dx, int16_t dy,
                              const swan_camera_bounds_t *bounds) {
    if (camera == 0 || !valid_bounds(bounds)) return false;
    camera->x = clamp_axis((int32_t)camera->x + dx,
                           bounds->min_x, bounds->max_x);
    camera->y = clamp_axis((int32_t)camera->y + dy,
                           bounds->min_y, bounds->max_y);
    return true;
}

bool swan_camera_center_clamped(swan_camera_t *camera, int16_t target_x,
                                int16_t target_y, uint16_t viewport_width,
                                uint16_t viewport_height,
                                const swan_camera_bounds_t *bounds) {
    if (camera == 0 || !valid_bounds(bounds) || viewport_width == 0 ||
        viewport_height == 0) return false;
    camera->x = clamp_axis((int32_t)target_x - viewport_width / 2u,
                           bounds->min_x, bounds->max_x);
    camera->y = clamp_axis((int32_t)target_y - viewport_height / 2u,
                           bounds->min_y, bounds->max_y);
    return true;
}
