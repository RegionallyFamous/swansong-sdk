#include <swan/swan.h>

#include "swan_assets.h"
#include "swan_controls.h"
#include "swan_project.h"
#include "model.h"

#define BOARD_WIDTH 32u
#define BOARD_HEIGHT 18u
#define CAUSEWAY_Y 11u
#define NO_POSITION UINT8_MAX

static tidewheel_model_t model;
static swan_tile_grid_t board;
static swan_sprite_animation_t wheel_animation;
static swan_camera_t foreground_camera;
static swan_camera_t background_camera;
static uint8_t last_position = NO_POSITION;

static bool action_pressed(const swan_frame_t *frame, uint8_t action) {
    return (frame->input->actions_pressed & (uint16_t)(1u << action)) != 0;
}

static void load_palette(const uint16_t SWAN_FAR *source) {
    uint16_t colors[4];
    uint8_t index;
    for (index = 0; index < 4; ++index) colors[index] = source[index];
    (void)swan_gfx_set_palette(0, colors);
}

static void load_title_art(void) {
    (void)swan_gfx_load_tiles(0, swan_asset_title_art_tiles,
                              SWAN_ASSET_TITLE_ART_TILE_COUNT);
    load_palette(swan_asset_title_art_palette);
}

static void load_play_art(void) {
    (void)swan_gfx_load_tiles(0, swan_asset_play_art_tiles,
                              SWAN_ASSET_PLAY_ART_TILE_COUNT);
    load_palette(swan_asset_play_art_palette);
}

static swan_tile_attr_t play_tile(uint8_t index) {
    return swan_asset_play_art_map[index];
}

static swan_tile_attr_t base_tile(uint8_t position) {
    if (tidewheel_is_crossing(position)) return play_tile(3);
    if (position == TIDEWHEEL_GOAL_X) return play_tile(7);
    return play_tile(2);
}

static void prepare_playfield(void) {
    uint8_t x;
    uint8_t y;
    (void)swan_tile_grid_init(&board, BOARD_WIDTH, BOARD_HEIGHT, play_tile(0));
    for (x = 0; x <= TIDEWHEEL_GOAL_X; ++x)
        (void)swan_tile_grid_set(&board, x, CAUSEWAY_Y, base_tile(x));
    (void)swan_sprite_animation_init(&wheel_animation, 4, 2, 6, true);
    foreground_camera.x = 0;
    foreground_camera.y = 0;
    background_camera.x = 0;
    background_camera.y = 0;
    last_position = NO_POSITION;
    (void)swan_gfx_fill(0, 0, 0, 32, 32, play_tile(1));
    for (y = 1; y < 32; y = (uint8_t)(y + 4u)) {
        for (x = 0; x < 32; x = (uint8_t)(x + 2u))
            (void)swan_gfx_put_tile(0, x, y,
                (swan_tile_attr_t)(play_tile(1) | SWAN_TILE_HFLIP));
    }
    swan_gfx_set_layer_enabled(0, true);
    swan_gfx_set_layer_enabled(1, true);
    swan_gfx_set_sprites_enabled(false);
    (void)swan_gfx_set_camera(0, 0, 0);
    (void)swan_gfx_set_camera(1, 0, 0);
}

static void update_foreground_camera(void) {
    static const swan_camera_bounds_t bounds = {0, 0, 32, 0};
    (void)swan_camera_center_clamped(&foreground_camera,
        (int16_t)(model.position * 8u + 4u), CAUSEWAY_Y * 8u,
        SWAN_GFX_DISPLAY_WIDTH, SWAN_GFX_DISPLAY_HEIGHT, &bounds);
    (void)swan_gfx_set_camera(1, foreground_camera.x, foreground_camera.y);
}

static bool update_background_camera(void) {
    static const swan_camera_bounds_t bounds = {0, 0, 16, 0};
    int16_t target = (int16_t)(foreground_camera.x / 2);
    int16_t dx = (int16_t)((target > background_camera.x) -
                           (target < background_camera.x));
    if (dx == 0) return false;
    (void)swan_camera_move_clamped(&background_camera, dx, 0, &bounds);
    (void)swan_gfx_set_camera(0, background_camera.x, background_camera.y);
    return true;
}

static void render_title(void) {
    uint8_t x;
    uint8_t y;
    for (y = 0; y < SWAN_ASSET_TITLE_ART_HEIGHT_TILES; ++y) {
        for (x = 0; x < SWAN_ASSET_TITLE_ART_WIDTH_TILES; ++x) {
            uint16_t index = (uint16_t)y * SWAN_ASSET_TITLE_ART_WIDTH_TILES + x;
            (void)swan_gfx_put_tile(0, x, y, swan_asset_title_art_map[index]);
        }
    }
}

static void render_play(void) {
    swan_tile_change_t change;
    uint16_t cursor = 0;
    uint8_t frame_tile = (uint8_t)(4u + wheel_animation.frame);
    if (last_position != NO_POSITION)
        (void)swan_tile_grid_set(&board, last_position, CAUSEWAY_Y,
                                 base_tile(last_position));
    (void)swan_tile_grid_set(&board, model.position, CAUSEWAY_Y,
        model.braced ? play_tile(6) : play_tile(frame_tile));
    while (swan_tile_grid_next_dirty(&board, &cursor, &change))
        (void)swan_gfx_put_tile(1, change.x, change.y, change.value);
    swan_tile_grid_clear_dirty(&board);
    last_position = model.position;
}

void swan_game_boot(void) {
    tidewheel_reset(&model);
}

void swan_scene_enter(swan_scene_id_t scene, uint16_t argument) {
    (void)argument;
    if (scene == SWAN_SCENE_TITLE) {
        load_title_art();
        swan_gfx_set_layer_enabled(0, true);
        swan_gfx_set_layer_enabled(1, false);
        swan_gfx_set_sprites_enabled(false);
        (void)swan_gfx_set_camera(0, 0, 0);
    } else if (scene == SWAN_SCENE_PLAY) {
        swan_core_reset_session();
        load_play_art();
        prepare_playfield();
        update_foreground_camera();
    } else {
        swan_gfx_set_layer_enabled(1, false);
        (void)swan_gfx_set_camera(0, 0, 0);
    }
    swan_core_invalidate();
}

void swan_scene_update(swan_scene_id_t scene, const swan_frame_t *frame) {
    tidewheel_input_t input = {0};
    tidewheel_event_t event;
    if (scene == SWAN_SCENE_TITLE) {
        if (action_pressed(frame, SWAN_ACTION_CONFIRM))
            (void)swan_core_request_scene(SWAN_SCENE_PLAY, 0);
        return;
    }
    input.move = (int8_t)(action_pressed(frame, SWAN_ACTION_RIGHT) -
                          action_pressed(frame, SWAN_ACTION_LEFT));
    input.brace = scene == SWAN_SCENE_PLAY &&
        action_pressed(frame, SWAN_ACTION_CONFIRM);
    input.replay = scene == SWAN_SCENE_RESULT &&
        action_pressed(frame, SWAN_ACTION_CONFIRM);
    input.reset = action_pressed(frame, SWAN_ACTION_RESET);
    tidewheel_step(&model, &input, &event);
    if (event.reset_session) {
        swan_core_reset_session();
        (void)swan_core_request_scene(SWAN_SCENE_PLAY, 0);
        return;
    }
    if (scene == SWAN_SCENE_PLAY) {
        if (event.changed) {
            update_foreground_camera();
            swan_core_invalidate();
        }
        if ((frame->session_tick & 3u) == 0 && update_background_camera())
            swan_core_invalidate();
        if (!model.braced && swan_sprite_animation_advance(&wheel_animation, 1))
            swan_core_invalidate();
        if (model.result != TIDEWHEEL_PLAYING)
            (void)swan_core_request_scene(SWAN_SCENE_RESULT, 0);
    }
}

void swan_scene_render(swan_scene_id_t scene) {
    if (scene == SWAN_SCENE_TITLE) {
        render_title();
    } else if (scene == SWAN_SCENE_PLAY) {
        render_play();
    } else {
        swan_tile_attr_t tile = model.result == TIDEWHEEL_ARRIVED ?
            play_tile(8) : play_tile(9);
        (void)swan_gfx_fill(0, 0, 0, 28, 18, play_tile(1));
        (void)swan_gfx_fill(0, 11, 6, 6, 6, tile);
    }
}

void swan_scene_exit(swan_scene_id_t scene) { (void)scene; }
