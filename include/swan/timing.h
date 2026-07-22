#ifndef SWAN_TIMING_H
#define SWAN_TIMING_H

#include <stdbool.h>
#include <stdint.h>

typedef struct {
    uint16_t duration;
    uint16_t remaining;
} swan_timer_t;

typedef enum {
    SWAN_TIMING_MISS = 0,
    SWAN_TIMING_GOOD,
    SWAN_TIMING_GREAT,
    SWAN_TIMING_PERFECT
} swan_timing_grade_t;

/* Nested absolute frame windows: perfect <= great <= good. */
typedef struct {
    uint16_t perfect;
    uint16_t great;
    uint16_t good;
} swan_timing_windows_t;

void swan_timer_start(swan_timer_t *timer, uint16_t duration);
/* Cancel the timer and clear its elapsed/progress state. */
void swan_timer_stop(swan_timer_t *timer);
bool swan_timer_advance(swan_timer_t *timer, uint16_t frames);
bool swan_timer_active(const swan_timer_t *timer);
uint16_t swan_timer_elapsed(const swan_timer_t *timer);
uint8_t swan_timer_progress_q8(const swan_timer_t *timer);

bool swan_timing_windows_valid(const swan_timing_windows_t *windows);
swan_timing_grade_t swan_timing_grade(uint32_t target_frame,
                                      uint32_t actual_frame,
                                      const swan_timing_windows_t *windows);
int8_t swan_timing_direction(uint32_t target_frame, uint32_t actual_frame);

#endif
