#include <assert.h>
#include "model.h"

int main(void) {
    game_model_t model;
    game_model_reset(&model);
    assert(model.x == GAME_HOME_X && model.y == GAME_HOME_Y);
    assert(model.charge == 3 && model.seeds == 0 && !model.complete);
    game_model_move(&model, -9, 0);
    assert(model.x == GAME_HOME_X && model.event == GAME_EVENT_BLOCKED);
    game_model_move(&model, 0, -1);
    assert(model.charge == 2 && model.event == GAME_EVENT_SCORCHED);
    game_model_reset(&model);
    game_model_move(&model, 1, 0);
    game_model_collect(&model);
    assert(model.seeds == 1 && model.event == GAME_EVENT_COLLECTED);
    game_model_move(&model, 1, 0);
    game_model_collect(&model);
    game_model_move(&model, 1, 0);
    game_model_collect(&model);
    assert(model.seeds == GAME_ALL_SEEDS && !model.complete);
    game_model_move(&model, -1, 0);
    game_model_move(&model, -1, 0);
    game_model_move(&model, -1, 0);
    assert(model.complete && model.event == GAME_EVENT_COMPLETE);
    game_model_reset(&model);
    assert(!model.complete && model.seeds == 0 && model.charge == 3);
    return 0;
}
