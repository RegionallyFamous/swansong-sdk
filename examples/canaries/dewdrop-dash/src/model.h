#ifndef DEWDROP_DASH_MODEL_H
#define DEWDROP_DASH_MODEL_H

#include <stdbool.h>
#include <stdint.h>

typedef struct {
    uint8_t x;
    uint8_t y;
    uint8_t seeds;
    uint8_t charge;
    uint8_t event;
    bool complete;
} game_model_t;

enum {
    GAME_EVENT_READY = 0,
    GAME_EVENT_MOVED,
    GAME_EVENT_BLOCKED,
    GAME_EVENT_SCORCHED,
    GAME_EVENT_COLLECTED,
    GAME_EVENT_MISSED,
    GAME_EVENT_COMPLETE
};

#define GAME_GRID_WIDTH 10u
#define GAME_GRID_HEIGHT 7u
#define GAME_HOME_X 1u
#define GAME_HOME_Y 5u
#define GAME_ALL_SEEDS 0x07u

void game_model_reset(game_model_t *model);
void game_model_move(game_model_t *model, int8_t dx, int8_t dy);
void game_model_collect(game_model_t *model);
bool game_model_seed_at(uint8_t x, uint8_t y, uint8_t *mask);
bool game_model_scorch_at(uint8_t x, uint8_t y);

#endif
