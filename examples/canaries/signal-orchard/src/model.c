#include "model.h"

bool game_model_goal_at(uint8_t x, uint8_t y) {
    return (x == 1 && y == 0) || (x == 4 && y == 5);
}

bool game_model_obstacle_at(uint8_t x, uint8_t y) {
    return x == 2 && y == 2;
}

static bool keeper_at(const game_model_t *model, uint8_t x, uint8_t y,
                      uint8_t *keeper) {
    uint8_t index;
    for (index = 0; index < GAME_KEEPER_COUNT; ++index) {
        if (model->keeper_x[index] == x && model->keeper_y[index] == y) {
            if (keeper != 0) *keeper = index;
            return true;
        }
    }
    return false;
}

static void update_win(game_model_t *model) {
    if (game_model_goal_at(model->keeper_x[0], model->keeper_y[0]) &&
            game_model_goal_at(model->keeper_x[1], model->keeper_y[1])) {
        model->result = GAME_RESULT_WIN;
        model->event = GAME_EVENT_WIN;
        model->selected = -1;
    }
}

void game_model_reset(game_model_t *model) {
    model->cursor_x = 0;
    model->cursor_y = 1;
    model->keeper_x[0] = 0;
    model->keeper_y[0] = 1;
    model->keeper_x[1] = 5;
    model->keeper_y[1] = 4;
    model->turn = 1;
    model->storm = GAME_STORM_TURNS;
    model->acted = 0;
    model->result = GAME_RESULT_PLAYING;
    model->event = GAME_EVENT_READY;
    model->selected = -1;
}

void game_model_cursor(game_model_t *model, int8_t dx, int8_t dy) {
    int8_t x;
    int8_t y;
    if (model->result != GAME_RESULT_PLAYING) return;
    x = (int8_t)model->cursor_x + dx;
    y = (int8_t)model->cursor_y + dy;
    if (x >= 0 && x < (int8_t)GAME_BOARD_WIDTH) model->cursor_x = (uint8_t)x;
    if (y >= 0 && y < (int8_t)GAME_BOARD_HEIGHT) model->cursor_y = (uint8_t)y;
    model->event = GAME_EVENT_CURSOR;
}

void game_model_confirm(game_model_t *model) {
    uint8_t keeper;
    uint8_t distance;
    if (model->result != GAME_RESULT_PLAYING) return;
    if (model->selected < 0) {
        if (keeper_at(model, model->cursor_x, model->cursor_y, &keeper) &&
                (model->acted & (1u << keeper)) == 0) {
            model->selected = (int8_t)keeper;
            model->event = GAME_EVENT_SELECTED;
        } else {
            model->event = GAME_EVENT_INVALID;
        }
        return;
    }
    keeper = (uint8_t)model->selected;
    distance = (uint8_t)(
        (model->cursor_x > model->keeper_x[keeper] ?
            model->cursor_x - model->keeper_x[keeper] :
            model->keeper_x[keeper] - model->cursor_x) +
        (model->cursor_y > model->keeper_y[keeper] ?
            model->cursor_y - model->keeper_y[keeper] :
            model->keeper_y[keeper] - model->cursor_y)
    );
    if (distance == 0 || distance > 2 ||
            game_model_obstacle_at(model->cursor_x, model->cursor_y) ||
            keeper_at(model, model->cursor_x, model->cursor_y, 0)) {
        model->event = GAME_EVENT_INVALID;
        return;
    }
    model->keeper_x[keeper] = model->cursor_x;
    model->keeper_y[keeper] = model->cursor_y;
    model->acted |= (uint8_t)(1u << keeper);
    model->selected = -1;
    model->event = GAME_EVENT_MOVED;
    update_win(model);
}

void game_model_cancel(game_model_t *model) {
    if (model->result != GAME_RESULT_PLAYING) return;
    model->selected = -1;
    model->event = GAME_EVENT_CANCELLED;
}

void game_model_end_turn(game_model_t *model) {
    if (model->result != GAME_RESULT_PLAYING) return;
    ++model->turn;
    model->selected = -1;
    model->acted = 0;
    if (model->storm != 0) --model->storm;
    if (model->storm == 0) {
        model->result = GAME_RESULT_STORM;
        model->event = GAME_EVENT_STORM;
    } else {
        model->event = GAME_EVENT_TURN;
    }
}
