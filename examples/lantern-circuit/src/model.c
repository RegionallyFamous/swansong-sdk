#include "model.h"
void game_model_reset(game_model_t *model) {
    model->cursor_x = 1; model->cursor_y = 1; model->unit_x = 1; model->unit_y = 1; model->turn = 1; model->selected = false;
}
void game_model_cursor(game_model_t *model, int8_t dx, int8_t dy) {
    int8_t x = (int8_t)model->cursor_x + dx, y = (int8_t)model->cursor_y + dy;
    if (x >= 0 && x < 8) model->cursor_x = (uint8_t)x;
    if (y >= 0 && y < 8) model->cursor_y = (uint8_t)y;
}
void game_model_confirm(game_model_t *model) {
    if (!model->selected) model->selected = model->cursor_x == model->unit_x && model->cursor_y == model->unit_y;
    else { model->unit_x = model->cursor_x; model->unit_y = model->cursor_y; model->selected = false; }
}
void game_model_cancel(game_model_t *model) { model->selected = false; }
void game_model_end_turn(game_model_t *model) { ++model->turn; model->selected = false; }
