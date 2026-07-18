#include <swan/swan.h>
#include "swan_assets.h"
#include "swan_controls.h"
#include "swan_project.h"
#include "model.h"

static game_model_t model;

static void load_palette(const uint16_t SWAN_FAR *source) {
    uint16_t colors[4];
    uint8_t index;
    for (index = 0; index < 4; ++index) colors[index] = source[index];
    swan_gfx_set_palette(0, colors);
}

static void load_title_art(void) {
    swan_gfx_load_tiles(0, swan_asset_title_art_tiles,
                        SWAN_ASSET_TITLE_ART_TILE_COUNT);
    load_palette(swan_asset_title_art_palette);
}

static void load_play_art(void) {
    swan_gfx_load_tiles(0, swan_asset_play_art_tiles,
                        SWAN_ASSET_PLAY_ART_TILE_COUNT);
    load_palette(swan_asset_play_art_palette);
}

static swan_tile_attr_t play_tile(uint8_t index) {
    return swan_asset_play_art_map[index];
}

void swan_game_boot(void) { game_model_reset(&model); }

void swan_scene_enter(swan_scene_id_t scene, uint16_t argument) {
    (void)argument;
    if (scene == SWAN_SCENE_TITLE) {
        load_title_art();
        swan_gfx_set_layer_enabled(1, false);
    } else if (scene == SWAN_SCENE_BATTLE) {
        game_model_reset(&model);
        swan_core_reset_session();
        load_play_art();
        swan_gfx_set_layer_enabled(1, false);
    }
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
            game_model_reset(&model);
            swan_core_reset_session();
        }
    }
}

void swan_scene_render(swan_scene_id_t scene) {
    uint8_t x;
    uint8_t y;
    uint8_t index;
    uint16_t map_index;
    if (scene == SWAN_SCENE_TITLE) {
        for (y = 0; y < SWAN_ASSET_TITLE_ART_HEIGHT_TILES; ++y) {
            for (x = 0; x < SWAN_ASSET_TITLE_ART_WIDTH_TILES; ++x) {
                map_index = (uint16_t)(
                    y * SWAN_ASSET_TITLE_ART_WIDTH_TILES + x
                );
                swan_gfx_put_tile(0, x, y,
                                  swan_asset_title_art_map[map_index]);
            }
        }
    } else {
        swan_gfx_fill(0, 0, 0, 28, 18, play_tile(0));
        for (y = 0; y < GAME_BOARD_HEIGHT; ++y) {
            for (x = 0; x < GAME_BOARD_WIDTH; ++x) {
                swan_gfx_put_tile(0, (uint8_t)(11 + x), (uint8_t)(5 + y),
                                  play_tile((uint8_t)(1 + ((x + y) & 1u))));
            }
        }
        swan_gfx_put_tile(0, 13, 7, play_tile(6));
        swan_gfx_put_tile(0, 12, 5, play_tile(5));
        swan_gfx_put_tile(0, 15, 10, play_tile(5));
        for (index = 0; index < GAME_KEEPER_COUNT; ++index) {
            swan_gfx_put_tile(0, (uint8_t)(11 + model.keeper_x[index]),
                              (uint8_t)(5 + model.keeper_y[index]),
                              play_tile((uint8_t)(3 + index)));
        }
        swan_gfx_put_tile(0, (uint8_t)(11 + model.cursor_x),
                          (uint8_t)(5 + model.cursor_y), play_tile(7));
        for (index = 0; index < model.storm; ++index)
            swan_gfx_put_tile(0, (uint8_t)(2 + index), 2, play_tile(6));
        for (index = 0; index < model.turn && index < 6; ++index)
            swan_gfx_put_tile(0, (uint8_t)(21 + index), 2, play_tile(5));
        if (model.result == GAME_RESULT_WIN)
            swan_gfx_fill(0, 11, 13, 6, 1, play_tile(5));
        else if (model.result == GAME_RESULT_STORM)
            swan_gfx_fill(0, 11, 13, 6, 1, play_tile(6));
    }
}

void swan_scene_exit(swan_scene_id_t scene) { (void)scene; }
