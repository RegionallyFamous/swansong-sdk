#include "model.h"

void game_model_reset(game_model_t *model) {
    model->x = 2;
    model->y = 2;
    model->pickups = 0;
    model->health = 3;
    model->complete = false;
}

void game_model_move(game_model_t *model, int8_t dx, int8_t dy) {
    int8_t next_x = model->x + dx;
    int8_t next_y = model->y + dy;
    if (next_x >= 0 && next_x < 26) model->x = next_x;
    if (next_y >= 0 && next_y < 16) model->y = next_y;
}

void game_model_collect(game_model_t *model) {
    if (model->pickups < 3) ++model->pickups;
    model->complete = model->pickups == 3;
}

void game_model_damage(game_model_t *model) {
    if (model->health) --model->health;
}
