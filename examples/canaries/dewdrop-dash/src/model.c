#include "model.h"

bool game_model_seed_at(uint8_t x, uint8_t y, uint8_t *mask) {
    static const uint8_t positions[3][2] = {{2, 5}, {3, 5}, {4, 5}};
    uint8_t index;
    for (index = 0; index < 3; ++index) {
        if (positions[index][0] == x && positions[index][1] == y) {
            if (mask != 0) *mask = (uint8_t)(1u << index);
            return true;
        }
    }
    if (mask != 0) *mask = 0;
    return false;
}

bool game_model_scorch_at(uint8_t x, uint8_t y) {
    return (x == 1 && y == 4) || (x == 6 && y == 2);
}

void game_model_reset(game_model_t *model) {
    model->x = GAME_HOME_X;
    model->y = GAME_HOME_Y;
    model->seeds = 0;
    model->charge = 3;
    model->event = GAME_EVENT_READY;
    model->complete = false;
}

void game_model_move(game_model_t *model, int8_t dx, int8_t dy) {
    int8_t next_x;
    int8_t next_y;
    if (model->complete || model->charge == 0) return;
    next_x = (int8_t)model->x + dx;
    next_y = (int8_t)model->y + dy;
    if (next_x < 0 || next_x >= (int8_t)GAME_GRID_WIDTH ||
            next_y < 0 || next_y >= (int8_t)GAME_GRID_HEIGHT) {
        model->event = GAME_EVENT_BLOCKED;
        return;
    }
    model->x = (uint8_t)next_x;
    model->y = (uint8_t)next_y;
    if (game_model_scorch_at(model->x, model->y)) {
        --model->charge;
        model->event = GAME_EVENT_SCORCHED;
    } else {
        model->event = GAME_EVENT_MOVED;
    }
    if (model->seeds == GAME_ALL_SEEDS && model->x == GAME_HOME_X &&
            model->y == GAME_HOME_Y) {
        model->complete = true;
        model->event = GAME_EVENT_COMPLETE;
    }
}

void game_model_collect(game_model_t *model) {
    uint8_t mask;
    if (model->complete || model->charge == 0) return;
    if (game_model_seed_at(model->x, model->y, &mask) &&
            (model->seeds & mask) == 0) {
        model->seeds |= mask;
        model->event = GAME_EVENT_COLLECTED;
    } else {
        model->event = GAME_EVENT_MISSED;
    }
}
