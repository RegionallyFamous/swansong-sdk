#ifndef tideglass_relay_MODEL_H
#define tideglass_relay_MODEL_H

#include <stdbool.h>
#include <stdint.h>

typedef struct {
    int8_t x;
    int8_t y;
    uint8_t pickups;
    uint8_t health;
    bool complete;
} game_model_t;

void game_model_reset(game_model_t *model);
void game_model_move(game_model_t *model, int8_t dx, int8_t dy);
void game_model_collect(game_model_t *model);
void game_model_damage(game_model_t *model);

#endif
