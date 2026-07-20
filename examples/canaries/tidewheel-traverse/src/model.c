#include <string.h>

#include "model.h"

bool tidewheel_is_crossing(uint8_t position) {
    return position == TIDEWHEEL_FIRST_CROSSING_X ||
        position == TIDEWHEEL_SECOND_CROSSING_X;
}

void tidewheel_reset(tidewheel_model_t *model) {
    memset(model, 0, sizeof(*model));
}

void tidewheel_step(tidewheel_model_t *model, const tidewheel_input_t *input,
                    tidewheel_event_t *event) {
    int16_t destination;
    memset(event, 0, sizeof(*event));
    if (input->reset || (model->result != TIDEWHEEL_PLAYING && input->replay)) {
        tidewheel_reset(model);
        event->changed = true;
        event->reset_session = true;
        return;
    }
    if (model->result != TIDEWHEEL_PLAYING) return;
    if (input->brace && !model->braced) {
        model->braced = true;
        event->changed = true;
    }
    if (input->move == 0) return;
    destination = (int16_t)model->position +
        (input->move > 0 ? 1 : -1);
    if (destination < 0) destination = 0;
    if (destination > (int16_t)TIDEWHEEL_GOAL_X)
        destination = TIDEWHEEL_GOAL_X;
    if ((uint8_t)destination == model->position) return;
    model->position = (uint8_t)destination;
    ++model->move_count;
    model->tide_phase = (uint8_t)((model->tide_phase + 1u) & 3u);
    if (tidewheel_is_crossing(model->position)) {
        if (!model->braced) model->result = TIDEWHEEL_SWEPT;
        model->braced = false;
    }
    if (model->position == TIDEWHEEL_GOAL_X &&
        model->result == TIDEWHEEL_PLAYING)
        model->result = TIDEWHEEL_ARRIVED;
    event->changed = true;
}
