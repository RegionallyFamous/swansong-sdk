#include <assert.h>
#include <string.h>

#include "model.h"

static void move(tidewheel_model_t *model, int8_t direction,
                 tidewheel_event_t *event) {
    const tidewheel_input_t input = {direction, false, false, false};
    tidewheel_step(model, &input, event);
}

static void brace(tidewheel_model_t *model, tidewheel_event_t *event) {
    const tidewheel_input_t input = {0, true, false, false};
    tidewheel_step(model, &input, event);
}

int main(void) {
    tidewheel_model_t model;
    tidewheel_model_t initial;
    tidewheel_event_t event;
    tidewheel_input_t input = {0, false, false, false};
    uint8_t position;

    tidewheel_reset(&model);
    initial = model;
    move(&model, -1, &event);
    assert(!event.changed && !memcmp(&model, &initial, sizeof(model)));

    for (position = 1; position <= TIDEWHEEL_FIRST_CROSSING_X; ++position)
        move(&model, 1, &event);
    assert(model.position == TIDEWHEEL_FIRST_CROSSING_X);
    assert(model.result == TIDEWHEEL_SWEPT);

    input.replay = true;
    tidewheel_step(&model, &input, &event);
    assert(event.changed && event.reset_session);
    assert(!memcmp(&model, &initial, sizeof(model)));

    for (position = 1; position <= TIDEWHEEL_GOAL_X; ++position) {
        if (position == TIDEWHEEL_FIRST_CROSSING_X ||
            position == TIDEWHEEL_SECOND_CROSSING_X) {
            brace(&model, &event);
            assert(model.braced && event.changed);
        }
        move(&model, 1, &event);
        assert(model.result != TIDEWHEEL_SWEPT);
        assert(model.tide_phase == (model.move_count & 3u));
    }
    assert(model.position == TIDEWHEEL_GOAL_X);
    assert(model.result == TIDEWHEEL_ARRIVED && !model.braced);

    memset(&input, 0, sizeof(input));
    input.reset = true;
    tidewheel_step(&model, &input, &event);
    assert(event.changed && event.reset_session);
    assert(!memcmp(&model, &initial, sizeof(model)));
    return 0;
}
