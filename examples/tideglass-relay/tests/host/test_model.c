#include <assert.h>
#include "model.h"

int main(void) {
    game_model_t model;
    game_model_reset(&model);
    assert(model.x == 2 && model.y == 2 && model.health == 3);
    game_model_move(&model, -99, -99);
    assert(model.x == 2 && model.y == 2);
    game_model_collect(&model);
    game_model_collect(&model);
    game_model_collect(&model);
    assert(model.complete);
    game_model_damage(&model);
    assert(model.health == 2);
    return 0;
}
