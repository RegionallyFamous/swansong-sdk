#include <swan/timing.h>

void swan_timer_start(swan_timer_t *timer, uint16_t duration) {
    if (timer == 0) return;
    timer->duration = duration;
    timer->remaining = duration;
}

void swan_timer_stop(swan_timer_t *timer) {
    if (timer == 0) return;
    timer->duration = 0;
    timer->remaining = 0;
}

bool swan_timer_advance(swan_timer_t *timer, uint16_t frames) {
    if (timer == 0 || timer->remaining == 0 || frames == 0) return false;
    if (frames < timer->remaining) {
        timer->remaining = (uint16_t)(timer->remaining - frames);
        return false;
    }
    timer->remaining = 0;
    return true;
}

bool swan_timer_active(const swan_timer_t *timer) {
    return timer != 0 && timer->remaining != 0;
}

uint16_t swan_timer_elapsed(const swan_timer_t *timer) {
    if (timer == 0 || timer->remaining > timer->duration) return 0;
    return (uint16_t)(timer->duration - timer->remaining);
}

uint8_t swan_timer_progress_q8(const swan_timer_t *timer) {
    uint32_t elapsed;
    if (timer == 0 || timer->duration == 0) return 0;
    elapsed = swan_timer_elapsed(timer);
    return (uint8_t)((elapsed * 255u) / timer->duration);
}

bool swan_timing_windows_valid(const swan_timing_windows_t *windows) {
    return windows != 0 && windows->perfect <= windows->great &&
        windows->great <= windows->good;
}

swan_timing_grade_t swan_timing_grade(uint32_t target_frame,
                                      uint32_t actual_frame,
                                      const swan_timing_windows_t *windows) {
    uint32_t distance;
    if (!swan_timing_windows_valid(windows)) return SWAN_TIMING_MISS;
    distance = actual_frame >= target_frame ? actual_frame - target_frame :
        target_frame - actual_frame;
    if (distance <= windows->perfect) return SWAN_TIMING_PERFECT;
    if (distance <= windows->great) return SWAN_TIMING_GREAT;
    if (distance <= windows->good) return SWAN_TIMING_GOOD;
    return SWAN_TIMING_MISS;
}

int8_t swan_timing_direction(uint32_t target_frame, uint32_t actual_frame) {
    if (actual_frame < target_frame) return -1;
    if (actual_frame > target_frame) return 1;
    return 0;
}
