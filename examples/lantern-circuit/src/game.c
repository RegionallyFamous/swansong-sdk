#include <swan/swan.h>
#include "swan_controls.h"
#include "swan_project.h"
#include "diagnostic_art.h"
#include "model.h"
static game_model_t model;
void swan_game_boot(void) { game_model_reset(&model); swan_diagnostic_art_load(); }
void swan_scene_enter(swan_scene_id_t scene, uint16_t argument) {
    (void)argument;
    if (scene == SWAN_SCENE_BATTLE) { game_model_reset(&model); swan_core_reset_session(); }
    swan_core_invalidate();
}
void swan_scene_update(swan_scene_id_t scene, const swan_frame_t *frame) {
    if (scene == SWAN_SCENE_TITLE && (frame->input->actions_pressed & (1u << SWAN_ACTION_CONFIRM)) != 0)
        swan_core_request_scene(SWAN_SCENE_BATTLE, 0);
    else if (scene == SWAN_SCENE_BATTLE) {
        if ((frame->input->actions_repeated & (1u << SWAN_ACTION_LEFT)) != 0) {
            game_model_cursor(&model, -1, 0); swan_core_invalidate();
        }
        if ((frame->input->actions_repeated & (1u << SWAN_ACTION_RIGHT)) != 0) {
            game_model_cursor(&model, 1, 0); swan_core_invalidate();
        }
        if ((frame->input->actions_repeated & (1u << SWAN_ACTION_UP)) != 0) {
            game_model_cursor(&model, 0, -1); swan_core_invalidate();
        }
        if ((frame->input->actions_repeated & (1u << SWAN_ACTION_DOWN)) != 0) {
            game_model_cursor(&model, 0, 1); swan_core_invalidate();
        }
        if ((frame->input->actions_pressed & (1u << SWAN_ACTION_CONFIRM)) != 0) {
            game_model_confirm(&model); swan_core_invalidate();
        }
        if ((frame->input->actions_pressed & (1u << SWAN_ACTION_CANCEL)) != 0) {
            game_model_cancel(&model); swan_core_invalidate();
        }
        if ((frame->input->actions_pressed & (1u << SWAN_ACTION_END_TURN)) != 0) {
            game_model_end_turn(&model); swan_core_invalidate();
        }
        if ((frame->input->actions_pressed & (1u << SWAN_ACTION_RESET)) != 0) {
            game_model_reset(&model); swan_core_invalidate();
        }
    }
}
void swan_scene_render(swan_scene_id_t scene) {
    uint8_t i;
    swan_gfx_fill(0, 0, 0, 28, 18, SWAN_TILE_ATTR(scene == SWAN_SCENE_TITLE ? 1 : 0, 0));
    if (scene == SWAN_SCENE_TITLE) {
        swan_gfx_put_tile(0, 12, 8, SWAN_TILE_ATTR(3, 0));
        swan_gfx_put_tile(0, 14, 8, SWAN_TILE_ATTR(4, 0));
    } else {
        swan_gfx_put_tile(0, (uint8_t)(4 + model.unit_x), (uint8_t)(4 + model.unit_y), SWAN_TILE_ATTR(2, 0));
        swan_gfx_put_tile(0, (uint8_t)(4 + model.cursor_x), (uint8_t)(4 + model.cursor_y), SWAN_TILE_ATTR(model.selected ? 4 : 3, 0));
        for (i = 0; i < model.turn && i < 8; ++i)
            swan_gfx_put_tile(0, (uint8_t)(1 + i), 1, SWAN_TILE_ATTR(5, 0));
    }
}
void swan_scene_exit(swan_scene_id_t scene) { (void)scene; }
