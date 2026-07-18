#include <assert.h>
#include "model.h"
int main(void) {
    game_model_t model;
    game_model_reset(&model);
    assert(model.cursor_x == 0 && model.cursor_y == 1);
    assert(model.storm == GAME_STORM_TURNS && model.selected == -1);
    game_model_confirm(&model);
    assert(model.selected == 0 && model.event == GAME_EVENT_SELECTED);
    game_model_cursor(&model, 1, 0);
    game_model_cursor(&model, 0, -1);
    game_model_confirm(&model);
    assert(model.keeper_x[0] == 1 && model.keeper_y[0] == 0);
    assert(model.selected == -1 && model.acted == 1);
    game_model_cursor(&model, 4, 4);
    assert(model.cursor_x == 5 && model.cursor_y == 4);
    game_model_confirm(&model);
    game_model_cursor(&model, -1, 0);
    game_model_cursor(&model, 0, 1);
    game_model_confirm(&model);
    assert(model.result == GAME_RESULT_WIN && model.event == GAME_EVENT_WIN);
    game_model_reset(&model);
    game_model_confirm(&model);
    game_model_cursor(&model, 2, 1);
    game_model_confirm(&model);
    assert(model.event == GAME_EVENT_INVALID && model.selected == 0);
    game_model_cancel(&model);
    assert(model.selected == -1 && model.event == GAME_EVENT_CANCELLED);
    game_model_end_turn(&model);
    game_model_end_turn(&model);
    game_model_end_turn(&model);
    game_model_end_turn(&model);
    assert(model.result == GAME_RESULT_STORM && model.storm == 0);
    game_model_reset(&model);
    assert(model.result == GAME_RESULT_PLAYING && model.turn == 1);
    return 0;
}
