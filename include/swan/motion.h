#ifndef SWAN_MOTION_H
#define SWAN_MOTION_H

#include <stdbool.h>
#include <stdint.h>

#define SWAN_FIXED_SHIFT 8u
#define SWAN_FIXED_ONE ((int32_t)1 << SWAN_FIXED_SHIFT)

typedef int32_t swan_fixed_t;

/* Signed 32-bit position and velocity with SWAN_FIXED_SHIFT fractional bits. */
typedef struct {
    swan_fixed_t x;
    swan_fixed_t y;
    swan_fixed_t velocity_x;
    swan_fixed_t velocity_y;
} swan_motion_t;

typedef struct {
    swan_fixed_t min_x;
    swan_fixed_t min_y;
    swan_fixed_t max_x;
    swan_fixed_t max_y;
} swan_motion_bounds_t;

typedef enum {
    SWAN_MOTION_HIT_LEFT = 1u << 0,
    SWAN_MOTION_HIT_RIGHT = 1u << 1,
    SWAN_MOTION_HIT_TOP = 1u << 2,
    SWAN_MOTION_HIT_BOTTOM = 1u << 3
} swan_motion_hit_t;

swan_fixed_t swan_fixed_from_int(int16_t value);
int16_t swan_fixed_to_int_floor(swan_fixed_t value);
swan_fixed_t swan_fixed_approach(swan_fixed_t value, swan_fixed_t target,
                                 swan_fixed_t amount);

void swan_motion_integrate(swan_motion_t *motion, swan_fixed_t acceleration_x,
                           swan_fixed_t acceleration_y);
bool swan_motion_clamp_velocity(swan_motion_t *motion,
                                swan_fixed_t maximum_x,
                                swan_fixed_t maximum_y);
bool swan_motion_brake(swan_motion_t *motion, swan_fixed_t amount_x,
                       swan_fixed_t amount_y);
uint8_t swan_motion_bounce(swan_motion_t *motion,
                           const swan_motion_bounds_t *bounds,
                           uint16_t restitution_q8);

#endif
