#ifndef SIGNAL_ORCHARD_MODEL_H
#define SIGNAL_ORCHARD_MODEL_H

#include <stdbool.h>
#include <stdint.h>

#define GAME_BOARD_WIDTH 6u
#define GAME_BOARD_HEIGHT 6u
#define GAME_KEEPER_COUNT 2u
#define GAME_STORM_TURNS 4u

enum {
    GAME_RESULT_PLAYING = 0,
    GAME_RESULT_WIN,
    GAME_RESULT_STORM
};

enum {
    GAME_EVENT_READY = 0,
    GAME_EVENT_CURSOR,
    GAME_EVENT_SELECTED,
    GAME_EVENT_MOVED,
    GAME_EVENT_INVALID,
    GAME_EVENT_CANCELLED,
    GAME_EVENT_TURN,
    GAME_EVENT_WIN,
    GAME_EVENT_STORM
};

typedef struct {
    uint8_t cursor_x;
    uint8_t cursor_y;
    uint8_t keeper_x[GAME_KEEPER_COUNT];
    uint8_t keeper_y[GAME_KEEPER_COUNT];
    uint8_t turn;
    uint8_t storm;
    uint8_t acted;
    uint8_t result;
    uint8_t event;
    int8_t selected;
} game_model_t;

void game_model_reset(game_model_t *model);
void game_model_cursor(game_model_t *model, int8_t dx, int8_t dy);
void game_model_confirm(game_model_t *model);
void game_model_cancel(game_model_t *model);
void game_model_end_turn(game_model_t *model);
bool game_model_goal_at(uint8_t x, uint8_t y);
bool game_model_obstacle_at(uint8_t x, uint8_t y);

#endif
