#ifndef TIDEWHEEL_TRAVERSE_MODEL_H
#define TIDEWHEEL_TRAVERSE_MODEL_H

#include <stdbool.h>
#include <stdint.h>

#define TIDEWHEEL_GOAL_X 30u
#define TIDEWHEEL_FIRST_CROSSING_X 8u
#define TIDEWHEEL_SECOND_CROSSING_X 20u

typedef enum {
    TIDEWHEEL_PLAYING = 0,
    TIDEWHEEL_ARRIVED,
    TIDEWHEEL_SWEPT
} tidewheel_result_t;

typedef struct {
    uint8_t position;
    uint8_t tide_phase;
    uint8_t move_count;
    tidewheel_result_t result;
    bool braced;
} tidewheel_model_t;

typedef struct {
    int8_t move;
    bool brace;
    bool replay;
    bool reset;
} tidewheel_input_t;

typedef struct {
    bool changed;
    bool reset_session;
} tidewheel_event_t;

bool tidewheel_is_crossing(uint8_t position);
void tidewheel_reset(tidewheel_model_t *model);
void tidewheel_step(tidewheel_model_t *model, const tidewheel_input_t *input,
                    tidewheel_event_t *event);

#endif
