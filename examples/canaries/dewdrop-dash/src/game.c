#include <swan/swan.h>
#include "swan_assets.h"
#include "swan_controls.h"
#include "swan_project.h"
#include "model.h"

static game_model_t model;

static void set_sprite(uint8_t id, uint8_t tile, int16_t x, int16_t y,
                       bool visible) {
    swan_sprite_t sprite = {
        .x = x, .y = y, .tile = tile, .palette = 0,
        .flags = 0, .visible = visible,
    };
    (void)swan_gfx_set_sprite(id, &sprite);
}

static void load_palette(const uint16_t SWAN_FAR *source) {
    uint16_t colors[4];
    uint16_t index;
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

void swan_game_boot(void) {
    game_model_reset(&model);
    swan_audio_init(swan_asset_theme_instruments, SWAN_ASSET_THEME_INSTRUMENT_COUNT);
    swan_audio_play_music(&swan_asset_theme_song);
}

void swan_scene_enter(swan_scene_id_t scene, uint16_t argument) {
    (void)argument;
    if (scene == SWAN_SCENE_TITLE) {
        load_title_art();
        swan_gfx_set_layer_enabled(1, false);
        swan_gfx_hide_sprites();
        swan_gfx_set_sprites_enabled(false);
        swan_audio_play_music(&swan_asset_theme_song);
    } else if (scene == SWAN_SCENE_PLAY) {
        game_model_reset(&model);
        swan_core_reset_session();
        load_play_art();
        swan_gfx_set_sprites_enabled(true);
        swan_audio_play_music(&swan_asset_theme_song);
    }
    swan_core_invalidate();
}

void swan_scene_update(swan_scene_id_t scene, const swan_frame_t *frame) {
    if (scene == SWAN_SCENE_TITLE && (frame->input->actions_pressed & (1u << SWAN_ACTION_CONFIRM)) != 0) {
        swan_core_request_scene(SWAN_SCENE_PLAY, 0);
    } else if (scene == SWAN_SCENE_PLAY) {
        if ((frame->input->actions_repeated & (1u << SWAN_ACTION_LEFT)) != 0) {
            game_model_move(&model, -1, 0); swan_core_invalidate();
        }
        if ((frame->input->actions_repeated & (1u << SWAN_ACTION_RIGHT)) != 0) {
            game_model_move(&model, 1, 0); swan_core_invalidate();
        }
        if ((frame->input->actions_repeated & (1u << SWAN_ACTION_UP)) != 0) {
            game_model_move(&model, 0, -1); swan_core_invalidate();
        }
        if ((frame->input->actions_repeated & (1u << SWAN_ACTION_DOWN)) != 0) {
            game_model_move(&model, 0, 1); swan_core_invalidate();
        }
        if ((frame->input->actions_pressed & (1u << SWAN_ACTION_CONFIRM)) != 0) {
            game_model_collect(&model); swan_core_invalidate();
        }
        if ((frame->input->actions_pressed & (1u << SWAN_ACTION_CANCEL)) != 0) {
            swan_core_request_scene(SWAN_SCENE_TITLE, 0);
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
    uint16_t index;
    if (scene == SWAN_SCENE_TITLE) {
        for (y = 0; y < SWAN_ASSET_TITLE_ART_HEIGHT_TILES; ++y) {
            for (x = 0; x < SWAN_ASSET_TITLE_ART_WIDTH_TILES; ++x) {
                index = (uint16_t)(y * SWAN_ASSET_TITLE_ART_WIDTH_TILES + x);
                swan_gfx_put_tile(0, x, y, swan_asset_title_art_map[index]);
            }
        }
    } else {
        swan_gfx_fill(0, 0, 0, 28, 18, play_tile(0));
        for (y = 0; y < GAME_GRID_HEIGHT; ++y) {
            for (x = 0; x < GAME_GRID_WIDTH; ++x) {
                swan_gfx_put_tile(0, (uint8_t)(9 + x), (uint8_t)(5 + y),
                                  play_tile((uint8_t)(1 + ((x + y) & 1u))));
            }
        }
        swan_gfx_put_tile(0, 10, 9, play_tile(5));
        swan_gfx_put_tile(0, 15, 7, play_tile(5));
        set_sprite(0, swan_gfx_tile_index(play_tile(3)),
                   (int16_t)((9 + model.x) * 8),
                   (int16_t)((5 + model.y) * 8), true);
        set_sprite(1, swan_gfx_tile_index(play_tile(4)), 11 * 8, 10 * 8,
                   (model.seeds & 1u) == 0);
        set_sprite(2, swan_gfx_tile_index(play_tile(4)), 12 * 8, 10 * 8,
                   (model.seeds & 2u) == 0);
        set_sprite(3, swan_gfx_tile_index(play_tile(4)), 13 * 8, 10 * 8,
                   (model.seeds & 4u) == 0);
        set_sprite(4, swan_gfx_tile_index(play_tile(6)),
                   (int16_t)((9 + GAME_HOME_X) * 8),
                   (int16_t)((5 + GAME_HOME_Y) * 8), true);
        for (index = 0; index < 3; ++index)
            set_sprite((uint8_t)(5 + index),
                       swan_gfx_tile_index(play_tile(3)),
                       (int16_t)((2 + index) * 8), 2 * 8,
                       index < model.charge);
        for (index = 0; index < 3; ++index) {
            if ((model.seeds & (1u << index)) != 0)
                swan_gfx_put_tile(0, (uint8_t)(23 + index), 2, play_tile(4));
        }
        if (model.complete)
            swan_gfx_fill(0, 9, 14, 10, 1, play_tile(7));
        else if (model.charge == 0)
            swan_gfx_fill(0, 9, 14, 10, 1, play_tile(5));
    }
}

void swan_scene_exit(swan_scene_id_t scene) { (void)scene; }
