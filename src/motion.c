#include <limits.h>

#include <swan/motion.h>

static swan_fixed_t add_saturated(swan_fixed_t value, swan_fixed_t delta) {
    if (delta > 0 && value > INT32_MAX - delta) return INT32_MAX;
    if (delta < 0 && value < INT32_MIN - delta) return INT32_MIN;
    return value + delta;
}

static swan_fixed_t clamp_signed(swan_fixed_t value, swan_fixed_t maximum) {
    if (value > maximum) return maximum;
    if (value < -maximum) return -maximum;
    return value;
}

static swan_fixed_t scale_reversed(swan_fixed_t velocity,
                                   uint16_t restitution_q8) {
    uint32_t magnitude;
    uint32_t scaled;
    bool negative = velocity < 0;
    if (negative)
        magnitude = (uint32_t)(-(velocity + 1)) + 1u;
    else
        magnitude = (uint32_t)velocity;
    scaled = (magnitude >> SWAN_FIXED_SHIFT) * restitution_q8;
    scaled += ((magnitude & (SWAN_FIXED_ONE - 1u)) * restitution_q8) >>
        SWAN_FIXED_SHIFT;
    if (scaled > (uint32_t)INT32_MAX) scaled = (uint32_t)INT32_MAX;
    return negative ? (swan_fixed_t)scaled : -(swan_fixed_t)scaled;
}

swan_fixed_t swan_fixed_from_int(int16_t value) {
    return (swan_fixed_t)value * SWAN_FIXED_ONE;
}

int16_t swan_fixed_to_int_floor(swan_fixed_t value) {
    swan_fixed_t whole = value / SWAN_FIXED_ONE;
    if (value < 0 && value % SWAN_FIXED_ONE != 0) --whole;
    if (whole < INT16_MIN) return INT16_MIN;
    if (whole > INT16_MAX) return INT16_MAX;
    return (int16_t)whole;
}

swan_fixed_t swan_fixed_approach(swan_fixed_t value, swan_fixed_t target,
                                 swan_fixed_t amount) {
    swan_fixed_t next;
    if (amount < 0) return value;
    if (value < target) {
        next = add_saturated(value, amount);
        return next >= target ? target : next;
    }
    if (value > target) {
        next = add_saturated(value, -amount);
        return next <= target ? target : next;
    }
    return value;
}

void swan_motion_integrate(swan_motion_t *motion, swan_fixed_t acceleration_x,
                           swan_fixed_t acceleration_y) {
    if (motion == 0) return;
    motion->velocity_x = add_saturated(motion->velocity_x, acceleration_x);
    motion->velocity_y = add_saturated(motion->velocity_y, acceleration_y);
    motion->x = add_saturated(motion->x, motion->velocity_x);
    motion->y = add_saturated(motion->y, motion->velocity_y);
}

bool swan_motion_clamp_velocity(swan_motion_t *motion,
                                swan_fixed_t maximum_x,
                                swan_fixed_t maximum_y) {
    swan_fixed_t old_x;
    swan_fixed_t old_y;
    if (motion == 0 || maximum_x < 0 || maximum_y < 0) return false;
    old_x = motion->velocity_x;
    old_y = motion->velocity_y;
    motion->velocity_x = clamp_signed(old_x, maximum_x);
    motion->velocity_y = clamp_signed(old_y, maximum_y);
    return old_x != motion->velocity_x || old_y != motion->velocity_y;
}

bool swan_motion_brake(swan_motion_t *motion, swan_fixed_t amount_x,
                       swan_fixed_t amount_y) {
    swan_fixed_t old_x;
    swan_fixed_t old_y;
    if (motion == 0 || amount_x < 0 || amount_y < 0) return false;
    old_x = motion->velocity_x;
    old_y = motion->velocity_y;
    motion->velocity_x = swan_fixed_approach(old_x, 0, amount_x);
    motion->velocity_y = swan_fixed_approach(old_y, 0, amount_y);
    return old_x != motion->velocity_x || old_y != motion->velocity_y;
}

uint8_t swan_motion_bounce(swan_motion_t *motion,
                           const swan_motion_bounds_t *bounds,
                           uint16_t restitution_q8) {
    uint8_t hits = 0;
    if (motion == 0 || bounds == 0 || bounds->min_x > bounds->max_x ||
        bounds->min_y > bounds->max_y || restitution_q8 > 256u) return 0;
    if (motion->x < bounds->min_x) {
        motion->x = bounds->min_x;
        if (motion->velocity_x < 0)
            motion->velocity_x = scale_reversed(motion->velocity_x,
                                                restitution_q8);
        hits |= SWAN_MOTION_HIT_LEFT;
    } else if (motion->x > bounds->max_x) {
        motion->x = bounds->max_x;
        if (motion->velocity_x > 0)
            motion->velocity_x = scale_reversed(motion->velocity_x,
                                                restitution_q8);
        hits |= SWAN_MOTION_HIT_RIGHT;
    }
    if (motion->y < bounds->min_y) {
        motion->y = bounds->min_y;
        if (motion->velocity_y < 0)
            motion->velocity_y = scale_reversed(motion->velocity_y,
                                                restitution_q8);
        hits |= SWAN_MOTION_HIT_TOP;
    } else if (motion->y > bounds->max_y) {
        motion->y = bounds->max_y;
        if (motion->velocity_y > 0)
            motion->velocity_y = scale_reversed(motion->velocity_y,
                                                restitution_q8);
        hits |= SWAN_MOTION_HIT_BOTTOM;
    }
    return hits;
}
