#include <swan/swan.h>

#include "swan_assets.h"
#include "swan_controls.h"
#include "swan_project.h"
#include "diagnostic_art.h"
#include "model.h"

#define UTILITY_SAVE_SCHEMA 1u
#define UTILITY_RESET_CHORD (SWAN_KEY_B | SWAN_KEY_START)
#define UTILITY_COMMIT_CUE_FRAMES 64u

static utility_model_t model;
static swan_ws_eeprom_context_t eeprom_context;
static swan_storage_t cartridge_storage;
static swan_ws_rtc_context_t rtc_context;
static swan_rtc_backend_t rtc_backend;
static swan_datetime_t boot_datetime;
static swan_rtc_status_t rtc_status;
static bool storage_ready;
static uint8_t commit_frames;
static utility_outcome_t commit_outcome;
static bool commit_allow_empty;
static bool scene_background_ready;

#if SWAN_DETERMINISTIC_TRACE
static uint32_t utility_state_hash(void) {
    swan_state_hash_t hash;
    uint8_t index;
    swan_state_hash_begin(&hash);
    swan_state_hash_u8(&hash, model.grid_column);
    swan_state_hash_u8(&hash, model.grid_row);
    swan_state_hash_u8(&hash, model.text_cursor);
    for (index = 0; index < UTILITY_TEXT_CAPACITY; ++index)
        swan_state_hash_u8(&hash, model.symbols[index]);
    swan_state_hash_u8(&hash, model.confirm_frames);
    swan_state_hash_bool(&hash, model.confirm_used_alternate);
    swan_state_hash_bool(&hash, model.dirty);
    swan_state_hash_u8(&hash, (uint8_t)model.outcome);
    return swan_state_hash_finish(&hash);
}

static void utility_mark_outcome(void) {
    uint8_t index;
    uint16_t progress = 0;
    for (index = 0; index < UTILITY_TEXT_CAPACITY; ++index)
        progress = (uint16_t)(progress + (model.symbols[index] != 0));
    swan_debug_frame_mark_state(progress, utility_state_hash());
    swan_debug_frame_mark_ending((uint8_t)model.outcome);
}
#else
#define utility_mark_outcome() ((void)0)
#endif

static const swan_instrument_t SWAN_FAR utility_instruments[1] = {{
    {0, 1, 3, 6, 10, 14, 10, 6, 3, 1, 0, 0, 0, 0, 0, 0}, 0, 0
}};

static bool action_pressed(const swan_frame_t *frame, uint8_t action) {
    return (frame->input->actions_pressed & (uint16_t)(1u << action)) != 0;
}

static bool action_held(const swan_frame_t *frame, uint8_t action) {
    return (frame->input->actions_held & (uint16_t)(1u << action)) != 0;
}

static bool action_released(const swan_frame_t *frame, uint8_t action) {
    return (frame->input->actions_released & (uint16_t)(1u << action)) != 0;
}

static void persist_document(utility_outcome_t outcome, bool allow_empty) {
    utility_record_t record;
    swan_save_info_t info;
    swan_save_status_t status;
    if (!allow_empty && !utility_model_has_text(&model)) {
        utility_model_mark_save_error(&model);
        return;
    }
    if (!storage_ready) {
        utility_model_mark_save_error(&model);
        return;
    }
    utility_model_make_record(&model, &record);
    status = swan_save_store(&cartridge_storage, UTILITY_SAVE_SCHEMA,
                             &record, sizeof(record), &info);
    if (status != SWAN_SAVE_OK) {
        utility_model_mark_save_error(&model);
        return;
    }
    utility_model_mark_persisted(&model, outcome);
}

static void schedule_persist(utility_outcome_t outcome, bool allow_empty) {
    if ((!allow_empty && !utility_model_has_text(&model)) || !storage_ready) {
        utility_model_mark_save_error(&model);
        return;
    }
    swan_audio_init(utility_instruments, 1);
    (void)swan_audio_play_sfx(&swan_asset_commit_sfx);
    swan_debug_frame_mark_audio(1u);
    commit_frames = UTILITY_COMMIT_CUE_FRAMES;
    commit_outcome = outcome;
    commit_allow_empty = allow_empty;
}

void swan_game_boot(void) {
    utility_record_t record;
    swan_save_info_t info;
    swan_save_status_t status;
    utility_model_reset(&model);
    swan_diagnostic_art_load();
    swan_audio_init(utility_instruments, 1);
    swan_ws_rtc_backend(&rtc_context, &rtc_backend, true);
    rtc_status = swan_rtc_capture(&rtc_backend, &boot_datetime);
    storage_ready = swan_ws_eeprom_storage(
        &eeprom_context, &cartridge_storage, 128
    );
    if (!storage_ready) {
        utility_model_mark_save_error(&model);
        return;
    }
    status = swan_save_load(&cartridge_storage, UTILITY_SAVE_SCHEMA,
                            &record, sizeof(record), &info);
    if (status == SWAN_SAVE_OK) {
        if (!utility_model_restore(&model, &record))
            utility_model_mark_save_error(&model);
    } else if (status != SWAN_SAVE_EMPTY) {
        utility_model_mark_save_error(&model);
    }
}

void swan_scene_enter(swan_scene_id_t scene, uint16_t argument) {
    (void)argument;
    scene_background_ready = false;
    if (scene == SWAN_SCENE_EDITOR) swan_core_reset_session();
    swan_core_invalidate();
}

void swan_scene_update(swan_scene_id_t scene, const swan_frame_t *frame) {
    uint16_t repeated;
    int8_t dx;
    int8_t dy;
    bool changed = false;
    if (scene == SWAN_SCENE_TITLE) {
        if (action_pressed(frame, SWAN_ACTION_CONFIRM))
            swan_core_request_scene(SWAN_SCENE_EDITOR, 0);
        utility_mark_outcome();
        return;
    }

    /* Finish the cue before EEPROM access can temporarily occupy the hardware. */
    if (commit_frames != 0) {
        --commit_frames;
        if (commit_frames == 0) {
            persist_document(commit_outcome, commit_allow_empty);
            swan_core_invalidate();
        }
        utility_mark_outcome();
        return;
    }

    repeated = frame->input->repeated;
    dx = (int8_t)(((repeated & SWAN_PRIMARY_RIGHT) != 0) -
                  ((repeated & SWAN_PRIMARY_LEFT) != 0));
    dy = (int8_t)(((repeated & SWAN_PRIMARY_DOWN) != 0) -
                  ((repeated & SWAN_PRIMARY_UP) != 0));
    if (dx != 0 || dy != 0) {
        utility_model_move_grid(&model, dx, dy);
        changed = true;
    }
    dx = (int8_t)(((repeated & SWAN_SECONDARY_RIGHT) != 0) -
                  ((repeated & SWAN_SECONDARY_LEFT) != 0));
    dy = (int8_t)(((repeated & SWAN_SECONDARY_DOWN) != 0) -
                  ((repeated & SWAN_SECONDARY_UP) != 0));
    if (dx != 0 || dy != 0) {
        utility_model_move_text(&model, dx, dy);
        changed = true;
    }

    if ((frame->input->pressed & UTILITY_RESET_CHORD) == UTILITY_RESET_CHORD) {
        utility_model_reset_document(&model);
        swan_core_reset_session();
        schedule_persist(UTILITY_OUTCOME_RESET, true);
        swan_core_invalidate();
        utility_mark_outcome();
        return;
    }
    if (utility_model_update_confirm(
            &model,
            action_pressed(frame, SWAN_ACTION_CONFIRM),
            action_held(frame, SWAN_ACTION_CONFIRM),
            action_released(frame, SWAN_ACTION_CONFIRM))) changed = true;
    if (action_pressed(frame, SWAN_ACTION_ERASE) && utility_model_erase(&model))
        changed = true;
    if (action_pressed(frame, SWAN_ACTION_SAVE)) {
        schedule_persist(UTILITY_OUTCOME_SAVED, false);
        changed = true;
    }
    if (changed) swan_core_invalidate();
    utility_mark_outcome();
}

void swan_scene_render(swan_scene_id_t scene) {
    uint8_t index;
    if (!scene_background_ready) {
        swan_gfx_fill(0, 0, 0, 28, 18, SWAN_TILE_ATTR(1, 0));
        scene_background_ready = true;
    }
    if (scene == SWAN_SCENE_TITLE) {
        swan_gfx_put_tile(0, 12, 8, SWAN_TILE_ATTR(4, 0));
        swan_gfx_put_tile(0, 14, 8, SWAN_TILE_ATTR(3, 0));
        swan_gfx_put_tile(0, 16, 8, SWAN_TILE_ATTR(2, 0));
        swan_gfx_put_tile(
            0, 18, 8,
            SWAN_TILE_ATTR(rtc_status == SWAN_RTC_OK ? 2 : 5, 0)
        );
        if (rtc_status == SWAN_RTC_OK) {
            uint8_t day_marks = (uint8_t)(boot_datetime.day % 5u);
            for (index = 0; index < 5; ++index) {
                swan_gfx_put_tile(
                    0, (uint8_t)(12 + index), 10,
                    SWAN_TILE_ATTR(index < day_marks ? 4 : 1, 0)
                );
            }
        }
        return;
    }

    for (index = 0; index < UTILITY_TEXT_CAPACITY; ++index) {
        uint8_t symbol = model.symbols[index];
        uint8_t tile = symbol == 0 ? 0 :
            (symbol > UTILITY_SYMBOL_COUNT ? 3 : 2);
        uint8_t x = (uint8_t)(5 + (index % UTILITY_TEXT_COLUMNS) * 4);
        uint8_t y = (uint8_t)(2 + (index / UTILITY_TEXT_COLUMNS) * 3);
        swan_gfx_put_tile(0, x, y, SWAN_TILE_ATTR(tile, 0));
        swan_gfx_put_tile(
            0, x, (uint8_t)(y + 1),
            SWAN_TILE_ATTR(index == model.text_cursor ? 4 : 1, 0)
        );
    }
    for (index = 0; index < UTILITY_SYMBOL_COUNT; ++index) {
        uint8_t column = (uint8_t)(index % UTILITY_GRID_COLUMNS);
        uint8_t row = (uint8_t)(index / UTILITY_GRID_COLUMNS);
        uint8_t selected = column == model.grid_column && row == model.grid_row;
        swan_gfx_put_tile(0, (uint8_t)(9 + column * 3), (uint8_t)(9 + row * 2),
                          SWAN_TILE_ATTR(selected ? 5 : 4, 0));
    }
    swan_gfx_put_tile(0, 26, 1,
                      SWAN_TILE_ATTR(model.dirty ? 3 : 1, 0));
    if (model.outcome != UTILITY_OUTCOME_EDITING) {
        uint8_t tile = model.outcome == UTILITY_OUTCOME_SAVED ? 2 :
            (model.outcome == UTILITY_OUTCOME_RESET ? 4 : 5);
        swan_gfx_fill(0, 24, 3, 3, 1, SWAN_TILE_ATTR(tile, 0));
    } else {
        swan_gfx_fill(0, 24, 3, 3, 1, SWAN_TILE_ATTR(1, 0));
    }
}

void swan_scene_exit(swan_scene_id_t scene) { (void)scene; }
