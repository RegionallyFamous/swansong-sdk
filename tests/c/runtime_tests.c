#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include <swan/swan.h>
#include <swan/legacy.h>

static unsigned tests_run;
static unsigned tests_failed;

#define CHECK(expression) do { \
    ++tests_run; \
    if (!(expression)) { \
        ++tests_failed; \
        printf("FAIL %s:%u: %s\n", __FILE__, (unsigned)__LINE__, #expression); \
    } \
} while (0)

static unsigned boot_count;
static unsigned enter_count;
static unsigned update_count;
static unsigned render_count;
static unsigned exit_count;
static uint16_t last_argument;
static unsigned platform_audio_reset_count;
static uint32_t platform_audio_reset_session_tick;
static bool platform_audio_reset_saw_silence;
static bool rtc_boot_test_enabled;
static swan_ws_rtc_context_t rtc_boot_context;
static swan_rtc_backend_t rtc_boot_backend;
static swan_rtc_status_t rtc_boot_first_status;
static swan_rtc_status_t rtc_boot_second_status;
static uint16_t last_frame_tapped;
static uint16_t last_frame_hold_started;
static uint16_t last_frame_chords;
static bool trace_reset_during_update;

extern uint8_t swan_debug_frame_trace_mailbox[
    SWAN_DEBUG_FRAME_TRACE_MAILBOX_HEADER_SIZE +
    SWAN_DEBUG_FRAME_TRACE_CAPACITY * SWAN_DEBUG_FRAME_TRACE_RECORD_SIZE];

void swan_platform_reset_audio_hardware(void) {
    uint8_t channel;
    ++platform_audio_reset_count;
    platform_audio_reset_session_tick = swan_core_session_tick();
    platform_audio_reset_saw_silence = true;
    for (channel = 0; channel < SWAN_AUDIO_CHANNEL_COUNT; ++channel) {
        if (swan_audio_voices()[channel].owner != SWAN_VOICE_SILENT ||
                swan_audio_voices()[channel].note != SWAN_AUDIO_NOTE_OFF ||
                swan_audio_voices()[channel].volume != 0 ||
                swan_audio_voices()[channel].priority != 0) {
            platform_audio_reset_saw_silence = false;
        }
    }
}

const swan_core_config_t swan_game_config = {
    .initial_scene = 0,
    .capabilities = SWAN_HARDWARE_COLOR
};

void swan_game_boot(void) {
    swan_datetime_t datetime;
    ++boot_count;
    swan_gfx_init(0);
    swan_audio_init(0, 0);
    if (rtc_boot_test_enabled) {
        swan_ws_rtc_backend(&rtc_boot_context, &rtc_boot_backend, true);
        rtc_boot_first_status = swan_rtc_capture(&rtc_boot_backend, &datetime);
        rtc_boot_second_status = swan_rtc_capture(&rtc_boot_backend, &datetime);
    }
}

void swan_scene_enter(swan_scene_id_t scene, uint16_t argument) {
    (void)scene;
    ++enter_count;
    last_argument = argument;
    swan_core_invalidate();
}

void swan_scene_update(swan_scene_id_t scene, const struct swan_frame *frame) {
    (void)scene;
    ++update_count;
    last_frame_tapped = frame->input->actions_tapped;
    last_frame_hold_started = frame->input->actions_hold_started;
    last_frame_chords = frame->input->chords_pressed;
    if (trace_reset_during_update &&
            (frame->input->actions_pressed & (1u << 1)) != 0) {
        swan_core_reset_session();
        swan_debug_frame_mark_ending(0);
    }
    swan_debug_frame_mark_state((uint16_t)frame->session_tick,
                                0x53570000u | frame->session_tick);
    if ((frame->input->actions_pressed & 1u) != 0) {
        swan_debug_frame_mark_ending(7);
        swan_debug_frame_mark_audio(0x0004u);
        swan_core_request_scene(1, 42);
    }
}

void swan_scene_render(swan_scene_id_t scene) {
    (void)scene;
    ++render_count;
}

void swan_scene_exit(swan_scene_id_t scene) {
    (void)scene;
    ++exit_count;
}

static void test_random(void) {
    swan_random_t a;
    swan_random_t b;
    uint8_t i;
    swan_random_seed(&a, 1234);
    swan_random_seed(&b, 1234);
    for (i = 0; i < 32; ++i) CHECK(swan_random_next(&a) == swan_random_next(&b));
    for (i = 0; i < 32; ++i) CHECK(swan_random_bounded(&a, 7) < 7);
    CHECK(swan_random_range_u8(&a, 9, 9) == 9);
}

static void test_debug(void) {
    uint8_t i;
    swan_debug_reset();
    for (i = 0; i < SWAN_DEBUG_TRACE_CAPACITY + 2u; ++i)
        swan_debug_trace(i, (uint16_t)(i * 3u));
    CHECK(swan_debug_trace_count() == SWAN_DEBUG_TRACE_CAPACITY);
    CHECK(swan_debug_trace_get(0)->code == 2);
    CHECK(swan_debug_trace_get((uint8_t)(SWAN_DEBUG_TRACE_CAPACITY - 1u))->code ==
          SWAN_DEBUG_TRACE_CAPACITY + 1u);
    CHECK(swan_debug_trace_get(SWAN_DEBUG_TRACE_CAPACITY) == 0);
    swan_debug_set_overlay(true);
    CHECK(swan_debug_overlay_enabled());
    CHECK(strcmp(swan_debug_build_identity()->sdk_version, SWAN_VERSION_STRING) == 0);
}

static uint16_t read_trace_u16(const uint8_t *value) {
    return (uint16_t)(value[0] | (uint16_t)(value[1] << 8));
}

static uint32_t read_trace_u32(const uint8_t *value) {
    return (uint32_t)value[0] | ((uint32_t)value[1] << 8) |
        ((uint32_t)value[2] << 16) | ((uint32_t)value[3] << 24);
}

static uint32_t trace_record_hash(const uint8_t *record) {
    uint32_t hash = 2166136261u;
    uint8_t index;
    for (index = 0; index < SWAN_DEBUG_FRAME_TRACE_RECORD_SIZE; ++index) {
        hash ^= record[index];
        hash *= 16777619u;
    }
    return hash;
}

static void test_deterministic_frame_trace(void) {
    static const swan_audio_row_t rows[1] = {
        { { { 12, 0, 15 },
            { SWAN_AUDIO_NO_CHANGE, SWAN_AUDIO_NO_CHANGE, SWAN_AUDIO_NO_CHANGE },
            { SWAN_AUDIO_NO_CHANGE, SWAN_AUDIO_NO_CHANGE, SWAN_AUDIO_NO_CHANGE },
            { SWAN_AUDIO_NO_CHANGE, SWAN_AUDIO_NO_CHANGE, SWAN_AUDIO_NO_CHANGE } } }
    };
    static const swan_song_t song = { rows, 1, 256, true };
    swan_core_config_t config;
    swan_sprite_t sprite = { 8, 8, 0, 0, 0, true };
    const swan_debug_frame_trace_t *frame;
    uint8_t serialized[SWAN_DEBUG_FRAME_TRACE_HEADER_SIZE +
        SWAN_DEBUG_FRAME_TRACE_CAPACITY * SWAN_DEBUG_FRAME_TRACE_RECORD_SIZE];
    uint16_t serialized_size;

    memset(&config, 0, sizeof(config));
    config.initial_scene = 0;
    config.capabilities = SWAN_HARDWARE_COLOR;
    config.input.keys[0] = SWAN_KEY_A;
    config.input.keys[1] = SWAN_KEY_B;
    trace_reset_during_update = false;
    swan_core_init(&config);
    CHECK(swan_debug_frame_trace_count() == 0);
    swan_debug_frame_mark_audio(0x0002u);
    CHECK(swan_gfx_set_sprite(0, &sprite));
    swan_audio_play_music(&song);
    swan_core_step(SWAN_KEY_A);
    CHECK(swan_debug_frame_trace_count() == 1);
    frame = swan_debug_frame_trace_get(0);
    CHECK(frame != 0 && frame->boot_tick == 1 && frame->session_tick == 1);
    CHECK(frame->scene == 1 && frame->transition_from == 0 &&
          frame->transition_to == 1 && frame->transition_argument == 42);
    CHECK((frame->flags & SWAN_DEBUG_FRAME_TRANSITION) != 0);
    CHECK((frame->flags & SWAN_DEBUG_FRAME_RENDERED) != 0);
    CHECK(frame->input_pressed == SWAN_KEY_A && frame->actions_pressed == 1u);
    CHECK(frame->progress == 1 && frame->state_hash == 0x53570001u);
    CHECK(frame->ending == 7 && frame->audio_marker == 0x0006u);
    CHECK(frame->sprites_visible == 1 && frame->maximum_sprites_on_scanline == 1);
    CHECK(frame->audio_voice_mask == 1);
    CHECK(frame->audio_sfx_mask == 0);

    trace_reset_during_update = true;
    swan_core_step(SWAN_KEY_B);
    trace_reset_during_update = false;
    CHECK(swan_debug_frame_trace_count() == 2);
    CHECK(swan_debug_frame_trace_reset_count() == 1);
    frame = swan_debug_frame_trace_get(1);
    CHECK(frame->session_tick == 0 && frame->reset_count == 1);
    CHECK((frame->flags & SWAN_DEBUG_FRAME_SESSION_RESET) != 0);
    CHECK(frame->progress == 0 && frame->state_hash == 0x53570000u);
    CHECK(frame->ending == 0 && frame->audio_marker == 0);
    CHECK(swan_debug_frame_trace_get(2) == 0);

    serialized_size = swan_debug_frame_trace_serialize(serialized,
                                                        sizeof(serialized));
    CHECK(serialized_size == SWAN_DEBUG_FRAME_TRACE_HEADER_SIZE +
          2u * SWAN_DEBUG_FRAME_TRACE_RECORD_SIZE);
    CHECK(memcmp(serialized, "SWTR", 4) == 0);
    CHECK(serialized[4] == SWAN_DEBUG_FRAME_TRACE_BINARY_VERSION);
    CHECK(serialized[5] == SWAN_DEBUG_FRAME_TRACE_RECORD_SIZE);
    CHECK(read_trace_u16(&serialized[6]) == 2);
    CHECK(read_trace_u32(&serialized[8]) == 0);
    CHECK(read_trace_u16(&serialized[12]) == 1);
    CHECK(read_trace_u32(&serialized[16]) == 2);
    CHECK(read_trace_u32(&serialized[20]) == swan_debug_frame_trace_stream_hash());
    CHECK(read_trace_u16(&serialized[24]) == 6);
    CHECK(read_trace_u16(&serialized[26]) == 1);
    CHECK(read_trace_u32(&serialized[28]) == 0);
    CHECK(read_trace_u32(&serialized[SWAN_DEBUG_FRAME_TRACE_HEADER_SIZE]) == 1);
    CHECK(read_trace_u16(&serialized[SWAN_DEBUG_FRAME_TRACE_HEADER_SIZE + 24]) == 1);
    CHECK(swan_debug_frame_trace_serialize(serialized,
        (uint16_t)(serialized_size - 1u)) == 0);
    CHECK(memcmp(swan_debug_frame_trace_mailbox, "SWMB", 4) == 0);
    CHECK(swan_debug_frame_trace_mailbox[4] ==
          SWAN_DEBUG_FRAME_TRACE_MAILBOX_VERSION);
    CHECK(swan_debug_frame_trace_mailbox[5] == SWAN_DEBUG_FRAME_TRACE_RECORD_SIZE);
    CHECK(swan_debug_frame_trace_mailbox[6] == SWAN_DEBUG_FRAME_TRACE_CAPACITY);
    CHECK(swan_debug_frame_trace_mailbox[7] == 2);
    CHECK(read_trace_u32(&swan_debug_frame_trace_mailbox[20]) == 2);
    CHECK(read_trace_u16(&swan_debug_frame_trace_mailbox[28]) == 6);
    CHECK(read_trace_u32(&swan_debug_frame_trace_mailbox[32]) ==
          (trace_record_hash(&swan_debug_frame_trace_mailbox[
              SWAN_DEBUG_FRAME_TRACE_MAILBOX_HEADER_SIZE]) ^
           trace_record_hash(&swan_debug_frame_trace_mailbox[
              SWAN_DEBUG_FRAME_TRACE_MAILBOX_HEADER_SIZE +
              SWAN_DEBUG_FRAME_TRACE_RECORD_SIZE])));

    {
        uint8_t index;
        for (index = 0; index < SWAN_DEBUG_FRAME_TRACE_CAPACITY + 2u; ++index)
            swan_core_step(0);
    }
    CHECK(swan_debug_frame_trace_count() == SWAN_DEBUG_FRAME_TRACE_CAPACITY);
    CHECK(swan_debug_frame_trace_dropped() == 4);
    CHECK(swan_debug_frame_trace_total_count() ==
          SWAN_DEBUG_FRAME_TRACE_CAPACITY + 4u);
    CHECK(swan_debug_frame_trace_audio_markers() == 6);
    CHECK(swan_debug_frame_trace_transition_count() == 1);
    CHECK(swan_debug_frame_trace_get(0)->boot_tick == 5);
    {
        uint8_t index;
        uint32_t retained_hash = 0;
        for (index = 0; index < SWAN_DEBUG_FRAME_TRACE_CAPACITY; ++index) {
            retained_hash ^= trace_record_hash(
                &swan_debug_frame_trace_mailbox[
                    SWAN_DEBUG_FRAME_TRACE_MAILBOX_HEADER_SIZE +
                    (uint16_t)index * SWAN_DEBUG_FRAME_TRACE_RECORD_SIZE]
            );
        }
        CHECK(read_trace_u32(&swan_debug_frame_trace_mailbox[32]) ==
              retained_hash);
    }
}

static void test_input(void) {
    swan_input_config_t config;
    memset(&config, 0, sizeof(config));
    config.keys[0] = SWAN_KEY_A | SWAN_KEY_B;
    config.keys[1] = SWAN_KEY_X1;
    config.repeat_delay = 2;
    config.repeat_period = 2;
    swan_input_init(&config);
    swan_input_update(SWAN_KEY_A | SWAN_KEY_X1);
    CHECK(swan_input_get()->pressed == (SWAN_KEY_A | SWAN_KEY_X1));
    CHECK(swan_input_get()->repeated == (SWAN_KEY_A | SWAN_KEY_X1));
    CHECK(swan_action_pressed(0));
    CHECK(swan_action_held(1));
    swan_input_update(SWAN_KEY_A | SWAN_KEY_X1);
    CHECK(swan_input_get()->repeated == 0);
    swan_input_update(SWAN_KEY_A | SWAN_KEY_X1);
    CHECK(swan_input_get()->repeated == (SWAN_KEY_A | SWAN_KEY_X1));
    swan_input_update(0);
    CHECK(swan_input_get()->released == (SWAN_KEY_A | SWAN_KEY_X1));
    CHECK(swan_action_released(0) && swan_action_released(1));
    CHECK(swan_input_dx(SWAN_KEY_X4 | SWAN_KEY_Y3) == 0);
    CHECK(swan_input_dy(SWAN_KEY_X3) == -1);
    CHECK(swan_input_dy(SWAN_KEY_X1) == 1);
    swan_input_update(SWAN_KEY_A);
    swan_input_drain();
    CHECK(swan_input_get()->released == 0);
    swan_input_update(SWAN_KEY_A);
    CHECK(swan_input_get()->held == 0 && swan_input_get()->pressed == 0);
    swan_input_update(0);
    swan_input_update(SWAN_KEY_A);
    CHECK(swan_input_get()->pressed == SWAN_KEY_A);
}

static void test_input_gestures(void) {
    swan_input_config_t config;
    memset(&config, 0, sizeof(config));
    config.keys[0] = SWAN_KEY_A;
    config.keys[1] = SWAN_KEY_B;
    config.keys[2] = SWAN_KEY_X1;
    config.keys[3] = SWAN_KEY_X2;
    config.chord_actions[0] = (1u << 0) | (1u << 1);
    config.chord_actions[1] = (1u << 2); /* Invalid one-action chord is inert. */
    config.tap_max_frames = 1;
    config.double_tap_window = 4;
    config.hold_threshold = 3;
    swan_input_init(&config);

    swan_input_update(SWAN_KEY_A);
    CHECK(!swan_action_tapped(0) && !swan_action_double_tapped(0));
    swan_input_update(0);
    CHECK(swan_action_tapped(0) && !swan_action_double_tapped(0));
    CHECK(swan_input_get()->actions_tapped == (1u << 0));
    swan_input_update(SWAN_KEY_A);
    CHECK(!swan_action_tapped(0));
    swan_input_update(0);
    CHECK(swan_action_tapped(0) && swan_action_double_tapped(0));
    CHECK(swan_input_get()->actions_double_tapped == (1u << 0));
    swan_input_update(0);
    CHECK(swan_input_get()->actions_tapped == 0 &&
          swan_input_get()->actions_double_tapped == 0);

    swan_input_update(SWAN_KEY_B);
    CHECK(!swan_action_hold_started(1) && !swan_action_held_long(1));
    swan_input_update(SWAN_KEY_B);
    CHECK(!swan_action_hold_started(1));
    swan_input_update(SWAN_KEY_B);
    CHECK(swan_action_hold_started(1) && swan_action_held_long(1));
    swan_input_update(SWAN_KEY_B);
    CHECK(!swan_action_hold_started(1) && swan_action_held_long(1));
    swan_input_update(0);
    CHECK(swan_action_released_after_hold(1));
    CHECK(!swan_action_tapped(1) && !swan_action_held_long(1));
    swan_input_update(0);
    CHECK(!swan_action_released_after_hold(1));

    swan_input_update(SWAN_KEY_X1);
    swan_input_update(SWAN_KEY_X1);
    swan_input_update(0);
    CHECK(!swan_action_tapped(2));
    CHECK(!swan_action_released_after_hold(2));

    swan_input_update(SWAN_KEY_A | SWAN_KEY_B);
    CHECK(swan_chord_pressed(0));
    CHECK(swan_input_get()->chords_pressed == (1u << 0));
    CHECK(!swan_chord_pressed(1));
    swan_input_update(SWAN_KEY_A | SWAN_KEY_B);
    CHECK(!swan_chord_pressed(0));
    swan_input_update(0);
    swan_input_update(SWAN_KEY_A);
    swan_input_update(SWAN_KEY_A | SWAN_KEY_B);
    CHECK(!swan_chord_pressed(0));
    swan_input_update(0);

    swan_input_update(SWAN_KEY_A);
    swan_input_update(0);
    swan_input_update(0);
    swan_input_update(0);
    swan_input_update(0);
    swan_input_update(0);
    swan_input_update(SWAN_KEY_A);
    swan_input_update(0);
    CHECK(swan_action_tapped(0) && !swan_action_double_tapped(0));

    swan_input_drain();
    swan_input_update(SWAN_KEY_A);
    swan_input_update(0);
    CHECK(swan_action_tapped(0) && !swan_action_double_tapped(0));

    swan_input_update(SWAN_KEY_A);
    swan_input_update(SWAN_KEY_A);
    swan_input_update(SWAN_KEY_A);
    CHECK(swan_action_hold_started(0));
    swan_input_update(0);
    CHECK(swan_action_released_after_hold(0));
    swan_input_update(SWAN_KEY_A);
    swan_input_update(0);
    CHECK(swan_action_tapped(0) && !swan_action_double_tapped(0));

    swan_input_update(SWAN_KEY_B);
    swan_input_update(SWAN_KEY_B);
    swan_input_update(SWAN_KEY_B);
    CHECK(swan_action_held_long(1));
    swan_input_drain();
    CHECK(!swan_action_held_long(1));
    swan_input_update(0);
    CHECK(!swan_action_released_after_hold(1));
    CHECK(!swan_action_tapped(SWAN_ACTION_CAPACITY));
    CHECK(!swan_action_held_long(SWAN_ACTION_CAPACITY));
    CHECK(!swan_chord_pressed(SWAN_INPUT_CHORD_CAPACITY));

    memset(&config, 0, sizeof(config));
    config.keys[0] = SWAN_KEY_A | SWAN_KEY_X1;
    config.tap_max_frames = 1;
    config.hold_threshold = 4;
    swan_input_init(&config);
    swan_input_update(SWAN_KEY_A);
    swan_input_update(SWAN_KEY_A | SWAN_KEY_X1);
    swan_input_update(SWAN_KEY_X1);
    CHECK(swan_action_held(0));
    CHECK(!swan_action_tapped(0) && !swan_action_released_after_hold(0));
    swan_input_update(0);
    CHECK(!swan_action_tapped(0) && !swan_action_released_after_hold(0));

    memset(&config, 0, sizeof(config));
    config.keys[0] = SWAN_KEY_A;
    swan_input_init(&config);
    swan_input_update(SWAN_KEY_A);
    swan_input_update(0);
    CHECK(swan_action_tapped(0));
}

static void test_wswan_keys(void) {
    CHECK(swan_ws_translate_keys(0x0002u) == SWAN_KEY_START);
    CHECK(swan_ws_translate_keys(0x000Cu) == (SWAN_KEY_A | SWAN_KEY_B));
    CHECK(swan_ws_translate_keys(0x00F0u) ==
          (SWAN_KEY_X1 | SWAN_KEY_X2 | SWAN_KEY_X3 | SWAN_KEY_X4));
    CHECK(swan_ws_translate_keys(0x0F00u) ==
          (SWAN_KEY_Y1 | SWAN_KEY_Y2 | SWAN_KEY_Y3 | SWAN_KEY_Y4));
    CHECK(swan_ws_translate_keys(0xF001u) == 0);
}

#define NC { SWAN_AUDIO_NO_CHANGE, SWAN_AUDIO_NO_CHANGE, SWAN_AUDIO_NO_CHANGE }
static void test_core_and_scenes(void) {
    static const swan_audio_row_t reset_rows[1] = {
        { { { 12, 0, 15 }, NC, NC, NC } }
    };
    static const swan_song_t reset_song = { reset_rows, 1, 256, true };
    swan_core_config_t config;
    unsigned reset_count;
    memset(&config, 0, sizeof(config));
    config.initial_scene = 0;
    config.initial_argument = 7;
    config.capabilities = SWAN_HARDWARE_COLOR;
    config.vertical = true;
    config.input.keys[0] = SWAN_KEY_A;
    config.input.keys[1] = SWAN_KEY_B;
    config.input.repeat_delay = 20;
    config.input.repeat_period = 5;
    config.input.chord_actions[0] = (1u << 0) | (1u << 1);
    config.input.tap_max_frames = 2;
    config.input.double_tap_window = 4;
    config.input.hold_threshold = 3;
    boot_count = enter_count = update_count = render_count = exit_count = 0;
    last_frame_tapped = last_frame_hold_started = last_frame_chords = 0;
    swan_core_init(&config);
    CHECK(boot_count == 1 && enter_count == 1 && last_argument == 7);
    CHECK(swan_core_vertical());
    swan_core_set_vertical(false);
    CHECK(!swan_core_vertical());
    swan_core_step(SWAN_KEY_A);
    CHECK(swan_core_boot_tick() == 1 && swan_core_session_tick() == 1);
    CHECK(update_count == 1 && exit_count == 1 && enter_count == 2);
    CHECK(swan_core_scenes()->current == 1 && last_argument == 42);
    CHECK(render_count == 2);
    swan_core_step(SWAN_KEY_A);
    CHECK(render_count == 2);
    CHECK(last_frame_hold_started == 0);
    swan_core_step(0);
    CHECK(last_frame_tapped == (1u << 0));
    swan_core_step(SWAN_KEY_A | SWAN_KEY_B);
    CHECK(last_frame_chords == (1u << 0));
    swan_audio_play_music(&reset_song);
    CHECK(swan_audio_voices()[0].owner == SWAN_VOICE_MUSIC);
    reset_count = platform_audio_reset_count;
    swan_core_reset_session();
    CHECK(swan_core_session_tick() == 0);
    CHECK(swan_audio_voices()[0].owner == SWAN_VOICE_SILENT);
    CHECK(platform_audio_reset_count == reset_count + 1);
    CHECK(platform_audio_reset_session_tick == 0);
    CHECK(platform_audio_reset_saw_silence);
    CHECK(!swan_audio_position().playing && !swan_audio_position().paused);
    CHECK(swan_audio_position().row == 0 && swan_audio_position().phase_q8 == 0);
    swan_debug_reset();
    CHECK(swan_scene_request(swan_core_scenes(), 2, 1));
    CHECK(!swan_scene_request(swan_core_scenes(), 3, 2));
    CHECK(swan_debug_state()->code == SWAN_PANIC_SCENE_CONFLICT);
    swan_scene_apply(swan_core_scenes());
    CHECK(swan_core_scenes()->current == 2);
}

static void test_legacy_helpers(void) {
    swan_core_config_t config;
    swan_random_t expected;
    uint16_t first;
    memset(&config, 0, sizeof(config));
    config.capabilities = SWAN_HARDWARE_COLOR;
    swan_core_init(&config);
    rf_init(true);
    CHECK(swan_core_vertical());
    CHECK(rf_primary_axis(SWAN_KEY_X4) == -1);
    CHECK(rf_primary_axis(SWAN_KEY_X2) == 1);
    CHECK(rf_primary_axis(SWAN_KEY_X3) == -1);
    rf_session_begin(1234);
    first = rf_random();
    swan_core_step(0);
    CHECK(swan_core_session_tick() == 1);
    rf_session_begin(1234);
    CHECK(swan_core_session_tick() == 0);
    CHECK(rf_random() == first);
    swan_random_seed(&expected, RF_DEFAULT_RANDOM_SEED);
    rf_session_begin(0);
    CHECK(rf_random() == swan_random_next(&expected));
}

static void test_assets_and_gfx(void) {
    static const uint8_t data[32] = {0};
    static const uint8_t full_upload[SWAN_GFX_TILE_UPLOAD_CAPACITY * 16u] = {0};
    swan_asset_t assets[3] = {
        { 1, SWAN_ASSET_TILES, data, 32, 2, 0 },
        { 2, SWAN_ASSET_PALETTE, data, 8, 1, 0 },
        { 3, SWAN_ASSET_SFX, data, 10, 1, 0 }
    };
    swan_asset_catalog_t catalog = { assets, 3, 2, 1, 0, 10 };
    swan_asset_usage_t usage;
    swan_gfx_config_t config = { 1024, 8, 64 };
    uint16_t palette[4] = { 0, 1, 2, 3 };
    swan_sprite_t sprite = { 10, 20, 2, 0, 0, true };
    swan_gfx_clip_t clip = { 16, 8, 192, 128 };
    swan_gfx_clip_t invalid_clip = { 223, 143, 2, 2 };
    int16_t projected_x;
    int16_t projected_y;
    uint8_t i;
    CHECK(swan_assets_validate(&catalog, &usage) == SWAN_ASSETS_OK);
    CHECK(usage.tiles == 2 && usage.palettes == 1 && usage.audio_bytes == 10);
    CHECK(swan_assets_find(&catalog, 2) == &assets[1]);
    assets[2].id = 2;
    CHECK(swan_assets_validate(&catalog, 0) == SWAN_ASSETS_DUPLICATE_ID);
    assets[2].id = 3;
    catalog.tile_budget = 1;
    CHECK(swan_assets_validate(&catalog, 0) == SWAN_ASSETS_TILE_LIMIT);

    swan_debug_reset();
    swan_gfx_init(&config);
    CHECK(swan_gfx_layer_enabled(0));
    CHECK(!swan_gfx_layer_enabled(1));
    CHECK(swan_gfx_sprites_enabled());
    swan_gfx_set_layer_enabled(1, true);
    CHECK(swan_gfx_layer_enabled(1));
    swan_gfx_set_layer_enabled(1, false);
    CHECK(swan_gfx_load_tiles(1, data, 2));
    CHECK(swan_gfx_load_tiles(1023, data, 1));
    CHECK(swan_gfx_tile_index(SWAN_TILE_ATTR(1023, 7)) == 1023);
    CHECK(swan_gfx_fill(0, 0, 0, 4, 3, SWAN_TILE_ATTR(1, 0)));
    CHECK(swan_gfx_get_tile(0, 0, 0) == SWAN_TILE_ATTR(1, 0));
    CHECK(swan_gfx_get_tile(0, 3, 2) == SWAN_TILE_ATTR(1, 0));
    CHECK(swan_gfx_get_tile(0, 4, 2) == 0);
    CHECK(swan_gfx_get_tile(0, 3, 3) == 0);
    CHECK(swan_gfx_put_tile(1, 31, 31, SWAN_TILE_ATTR(1023, 7)));
    CHECK(swan_gfx_get_tile(1, 31, 31) == SWAN_TILE_ATTR(1023, 7));
    CHECK(!swan_gfx_put_tile(0, 32, 0, 0));
    CHECK(swan_gfx_set_camera(0, 120, -30));
    CHECK(swan_gfx_camera(0)->x == 120 && swan_gfx_camera(0)->y == -30);
    CHECK(swan_gfx_camera_project(0, 130, -10, &projected_x, &projected_y));
    CHECK(projected_x == 10 && projected_y == 20);
    CHECK(!swan_gfx_set_camera(2, 0, 0));
    CHECK(swan_gfx_set_layer_clip(1, SWAN_GFX_CLIP_INSIDE, &clip));
    CHECK(swan_gfx_layer_clip_mode(1) == SWAN_GFX_CLIP_INSIDE);
    CHECK(swan_gfx_layer_clip(1)->width == 192);
    CHECK(swan_gfx_set_layer_clip(1, SWAN_GFX_CLIP_OUTSIDE, &clip));
    CHECK(!swan_gfx_set_layer_clip(0, SWAN_GFX_CLIP_INSIDE, &clip));
    CHECK(swan_gfx_set_layer_clip(1, SWAN_GFX_CLIP_DISABLED, 0));
    CHECK(swan_gfx_layer_clip(1) == 0);
    CHECK(swan_gfx_set_sprite_clip(&clip));
    CHECK(swan_gfx_sprite_clip()->height == 128);
    CHECK(!swan_gfx_set_sprite_clip(&invalid_clip));
    CHECK(swan_gfx_set_sprite_clip(0));
    CHECK(swan_gfx_sprite_clip() == 0);
    sprite.tile = 511;
    CHECK(swan_gfx_set_sprite(0, &sprite));
    sprite.tile = 512;
    CHECK(!swan_gfx_set_sprite(0, &sprite));
    sprite.tile = 2;
    sprite.flags = 0x80;
    CHECK(!swan_gfx_set_sprite(0, &sprite));
    sprite.flags = SWAN_SPRITE_FLAG_PRIORITY | SWAN_SPRITE_FLAG_HFLIP;
    CHECK(swan_gfx_set_sprite(0, &sprite));
    swan_debug_reset();
    CHECK(swan_gfx_set_palette(7, palette));
    for (i = 0; i < 33; ++i) {
        sprite.x = (int16_t)i;
        CHECK(swan_gfx_set_sprite(i, &sprite));
    }
    swan_gfx_present();
    CHECK(swan_gfx_usage()->sprites_visible == 33);
    CHECK(swan_gfx_usage()->scanline_overflow);
    CHECK(!swan_gfx_dirty());

    swan_gfx_hide_sprites();
    sprite.visible = true;
    sprite.y = -8;
    CHECK(swan_gfx_set_sprite(0, &sprite));
    CHECK(swan_gfx_usage()->maximum_sprites_on_scanline == 0);
    sprite.y = -7;
    CHECK(swan_gfx_set_sprite(0, &sprite));
    CHECK(swan_gfx_usage()->maximum_sprites_on_scanline == 1);
    sprite.y = 252;
    CHECK(swan_gfx_set_sprite(0, &sprite));
    CHECK(swan_gfx_usage()->maximum_sprites_on_scanline == 1);
    sprite.y = 32767;
    CHECK(swan_gfx_set_sprite(0, &sprite));
    CHECK(swan_gfx_usage()->maximum_sprites_on_scanline == 1);
    swan_gfx_set_sprites_enabled(false);
    CHECK(swan_gfx_usage()->maximum_sprites_on_scanline == 0);
    swan_gfx_set_sprites_enabled(true);
    CHECK(swan_gfx_usage()->maximum_sprites_on_scanline == 1);

    swan_gfx_init(&config);
    CHECK(swan_gfx_load_tiles(512, full_upload,
                              SWAN_GFX_TILE_UPLOAD_CAPACITY));
    CHECK(!swan_gfx_load_tiles(0, data, 1));

    {
        swan_core_config_t mono;
        memset(&mono, 0, sizeof(mono));
        mono.capabilities = SWAN_HARDWARE_MONO;
        swan_core_init(&mono);
        CHECK(!swan_gfx_load_tiles(512, data, 1));
        CHECK(!swan_gfx_put_tile(0, 0, 0, SWAN_TILE_ATTR(512, 0)));
        sprite.tile = 511;
        CHECK(swan_gfx_set_sprite(0, &sprite));
    }
}

static void test_audio(void) {
    static const swan_audio_row_t rows[2] = {
        { { { 12, 0, 15 }, NC, NC, NC } },
        { { { 13, 0, 10 }, NC, NC, NC } }
    };
    static const swan_song_t song = { rows, 2, 512, true };
    static const swan_sfx_step_t step = { { 30, 0, 12 }, 2 };
    swan_sfx_t effects[6];
    swan_audio_position_t position;
    uint8_t i;
    swan_audio_init(0, 0);
    swan_audio_play_music(&song);
    CHECK(swan_audio_voices()[0].note == 12);
    swan_audio_tick();
    position = swan_audio_position();
    CHECK(position.playing && !position.paused && position.row == 0);
    CHECK(position.phase_q8 == 256);
    CHECK(swan_audio_pause());
    position = swan_audio_position();
    CHECK(position.playing && position.paused && position.phase_q8 == 256);
    CHECK(swan_audio_voices()[0].owner == SWAN_VOICE_SILENT);
    swan_audio_tick();
    CHECK(swan_audio_position().phase_q8 == 256);
    CHECK(!swan_audio_pause());
    CHECK(swan_audio_resume());
    CHECK(!swan_audio_resume());
    CHECK(swan_audio_voices()[0].note == 12);
    CHECK(swan_audio_music_row() == 0);
    swan_audio_tick();
    CHECK(swan_audio_music_row() == 1 && swan_audio_voices()[0].note == 13);
    for (i = 0; i < 6; ++i) {
        effects[i].steps = &step;
        effects[i].step_count = 1;
        effects[i].priority = i < 4 ? 5 : (i == 4 ? 1 : 6);
    }
    for (i = 0; i < 4; ++i) CHECK(swan_audio_play_sfx(&effects[i]) >= 0);
    CHECK(swan_audio_play_sfx(&effects[4]) == -1);
    CHECK(swan_audio_play_sfx(&effects[5]) >= 0);
    swan_audio_set_master_volume(5);
    CHECK(swan_audio_voices()[0].volume <= 5);
    swan_audio_tick();
    swan_audio_tick();
    CHECK(swan_audio_voices()[0].owner != SWAN_VOICE_SFX);
    CHECK(swan_audio_pause());
    swan_audio_play_music(&song);
    position = swan_audio_position();
    CHECK(position.playing && !position.paused && position.row == 0);
    CHECK(swan_audio_voices()[0].note == 12);
    swan_audio_stop_all();
    position = swan_audio_position();
    CHECK(!position.playing && !position.paused && position.row == 0);
    CHECK(position.phase_q8 == 0);

    swan_audio_play_music(&song);
    swan_audio_tick();
    CHECK(swan_audio_pause());
    swan_audio_stop_music();
    position = swan_audio_position();
    CHECK(!position.playing && !position.paused && position.phase_q8 == 0);
    CHECK(!swan_audio_resume());

    swan_audio_play_music(&song);
    CHECK(swan_audio_play_sfx(&effects[0]) >= 0);
    CHECK(swan_audio_pause());
    swan_audio_stop_music();
    position = swan_audio_position();
    CHECK(!position.playing && position.paused && position.phase_q8 == 0);
    CHECK(swan_audio_resume());
    CHECK(swan_audio_voices()[0].owner == SWAN_VOICE_SFX);
    swan_audio_stop_all();
}

typedef struct {
    uint8_t bytes[256];
    unsigned writes;
    unsigned fail_write;
} memory_storage_t;

static bool memory_read(void *context, uint32_t offset, void *destination, uint16_t length) {
    memory_storage_t *memory = context;
    if (offset + length > sizeof(memory->bytes)) return false;
    memcpy(destination, memory->bytes + offset, length);
    return true;
}

static bool memory_write(void *context, uint32_t offset, const void *source, uint16_t length) {
    memory_storage_t *memory = context;
    ++memory->writes;
    if (memory->fail_write != 0 && memory->writes == memory->fail_write) return false;
    if (offset + length > sizeof(memory->bytes)) return false;
    memcpy(memory->bytes + offset, source, length);
    return true;
}

static bool memory_sync(void *context) { (void)context; return true; }

static void test_save(void) {
    memory_storage_t memory;
    swan_storage_t storage = { &memory, sizeof(memory.bytes), memory_read,
                               memory_write, memory_sync };
    uint8_t output[16];
    uint8_t migrated[3];
    swan_save_info_t info;
    static const uint8_t first[] = { 1, 2, 3 };
    static const uint8_t second[] = { 4, 5, 6, 7 };
    static const uint8_t third[] = { 8, 9 };
    memset(&memory, 0xFF, sizeof(memory));
    memory.writes = 0;
    memory.fail_write = 0;
    CHECK(swan_save_capacity(&storage) == 104);
    CHECK(swan_save_load(&storage, 1, output, sizeof(output), &info) == SWAN_SAVE_EMPTY);
    CHECK(swan_save_store(&storage, 1, first, sizeof(first), &info) == SWAN_SAVE_OK);
    CHECK(info.generation == 1 && info.slot == 0);
    CHECK(swan_save_store(&storage, 1, second, sizeof(second), &info) == SWAN_SAVE_OK);
    CHECK(info.generation == 2 && info.slot == 1);
    CHECK(swan_save_load(&storage, 1, output, sizeof(output), &info) == SWAN_SAVE_OK);
    CHECK(info.length == sizeof(second) && memcmp(output, second, sizeof(second)) == 0);
    memory.bytes[128 + 24] ^= 0x80u;
    CHECK(swan_save_load(&storage, 1, output, sizeof(output), &info) == SWAN_SAVE_OK);
    CHECK(info.generation == 1 && memcmp(output, first, sizeof(first)) == 0);
    CHECK(swan_save_store(&storage, 2, third, sizeof(third), &info) == SWAN_SAVE_OK);
    CHECK(swan_save_load(&storage, 1, output, sizeof(output), &info) == SWAN_SAVE_SCHEMA_MISMATCH);
    CHECK(info.schema == 2);
    CHECK(swan_save_load_any(&storage, output, sizeof(output), &info) == SWAN_SAVE_OK);
    CHECK(memcmp(output, third, sizeof(third)) == 0);
    memory.writes = 0;
    memory.fail_write = 2;
    CHECK(swan_save_store(&storage, 2, first, sizeof(first), &info) == SWAN_SAVE_IO_ERROR);
    memory.fail_write = 0;
    CHECK(swan_save_load_any(&storage, output, sizeof(output), &info) == SWAN_SAVE_OK);
    CHECK(memcmp(output, third, sizeof(third)) == 0);
    CHECK(info.schema == 2 && info.length == sizeof(third));
    migrated[0] = output[0];
    migrated[1] = output[1];
    migrated[2] = 42;
    CHECK(swan_save_store(&storage, 3, migrated, sizeof(migrated), &info) ==
          SWAN_SAVE_OK);
    memset(output, 0, sizeof(output));
    CHECK(swan_save_load(&storage, 3, output, sizeof(output), &info) ==
          SWAN_SAVE_OK);
    CHECK(info.schema == 3 && info.length == sizeof(migrated));
    CHECK(memcmp(output, migrated, sizeof(migrated)) == 0);
}

typedef struct {
    uint8_t raw[7];
    swan_rtc_status_t status;
} fake_rtc_t;

static swan_rtc_status_t fake_rtc_read(void *context, uint8_t registers[7]) {
    fake_rtc_t *rtc = context;
    memcpy(registers, rtc->raw, 7);
    return rtc->status;
}

static void test_rtc(void) {
    fake_rtc_t rtc = { { 0x24, 0x02, 0x29, 0x04, 0x23, 0x59, 0x58 }, SWAN_RTC_OK };
    swan_rtc_backend_t backend = { &rtc, fake_rtc_read };
    swan_datetime_t datetime;
    uint8_t decoded;
    CHECK(swan_rtc_capture(&backend, &datetime) == SWAN_RTC_OK);
    CHECK(datetime.year == 2024 && datetime.month == 2 && datetime.day == 29);
    CHECK(swan_rtc_decode_bcd(0x59, 59, &decoded) && decoded == 59);
    CHECK(!swan_rtc_decode_bcd(0x6A, 59, &decoded));
    rtc.raw[0] = 0x23;
    CHECK(swan_rtc_capture(&backend, &datetime) == SWAN_RTC_INVALID);
    rtc.status = SWAN_RTC_POWER_LOSS;
    CHECK(swan_rtc_capture(&backend, &datetime) == SWAN_RTC_POWER_LOSS);
    CHECK(swan_rtc_capture(0, &datetime) == SWAN_RTC_UNAVAILABLE);
}

static void test_wswan_adapters(void) {
    swan_ws_eeprom_context_t eeprom;
    swan_ws_sram_context_t sram;
    swan_ws_rtc_context_t rtc;
    swan_storage_t storage;
    swan_rtc_backend_t backend;
    uint8_t byte = 0;
    uint8_t raw[7];
    CHECK(swan_ws_eeprom_storage(&eeprom, &storage, 128));
    CHECK(eeprom.address_bits == 7 && storage.byte_count == 128);
    CHECK(swan_save_capacity(&storage) == 40);
    CHECK(!swan_ws_eeprom_storage(&eeprom, &storage, 129));
    CHECK(swan_ws_eeprom_storage(&eeprom, &storage, 1024));
    CHECK(eeprom.address_bits == 10);
    CHECK(swan_ws_eeprom_storage(&eeprom, &storage, 2048));
    CHECK(eeprom.address_bits == 11);
    CHECK(swan_ws_sram_storage(&sram, &storage, 8192));
    CHECK(storage.byte_count == 8192);
    CHECK(swan_ws_sram_storage(&sram, &storage, 524288));
    CHECK(!swan_ws_sram_storage(&sram, &storage, 16384));
#if !defined(__WONDERFUL_WSWAN__)
    CHECK(!storage.read(storage.context, 0, &byte, 1));
    CHECK(!storage.write(storage.context, 0, &byte, 1));
    CHECK(!storage.sync(storage.context));
#else
    (void)byte;
#endif
    swan_ws_rtc_backend(&rtc, &backend, false);
    CHECK(backend.read(backend.context, raw) == SWAN_RTC_UNAVAILABLE);
#if !defined(__WONDERFUL_WSWAN__)
    swan_ws_rtc_backend(&rtc, &backend, true);
    CHECK(backend.read(backend.context, raw) == SWAN_RTC_WRONG_PHASE);
    rtc_boot_test_enabled = true;
    swan_core_init(&swan_game_config);
    rtc_boot_test_enabled = false;
    CHECK(rtc_boot_context.captured);
    CHECK(rtc_boot_first_status == SWAN_RTC_IO_ERROR);
    CHECK(rtc_boot_second_status == SWAN_RTC_IO_ERROR);
    CHECK(swan_rtc_capture(&rtc_boot_backend, &(swan_datetime_t){0}) ==
          SWAN_RTC_WRONG_PHASE);
#endif
}

static void test_canonical_state_hash(void) {
    swan_state_hash_t first;
    swan_state_hash_t second;
    const uint8_t canonical[] = {0x12, 0xFE, 0x56, 0x34, 0xDE, 0xBC, 0x9A, 0x78, 1};
    swan_state_hash_begin(&first);
    swan_state_hash_u8(&first, 0x12);
    swan_state_hash_i8(&first, -2);
    swan_state_hash_u16(&first, 0x3456);
    swan_state_hash_u32(&first, 0x789ABCDEu);
    swan_state_hash_bool(&first, true);
    swan_state_hash_begin(&second);
    swan_state_hash_bytes(&second, canonical, sizeof(canonical));
    CHECK(first.bytes == sizeof(canonical));
    CHECK(swan_state_hash_finish(&first) == 0x58E5BF2Eu);
    CHECK(swan_state_hash_finish(&first) == swan_state_hash_finish(&second));
}

int main(void) {
    test_debug();
    test_deterministic_frame_trace();
    test_random();
    test_input();
    test_input_gestures();
    test_wswan_keys();
    test_core_and_scenes();
    test_legacy_helpers();
    test_assets_and_gfx();
    test_audio();
    test_save();
    test_rtc();
    test_wswan_adapters();
    test_canonical_state_hash();
    printf("runtime: %u checks, %u failures\n", tests_run, tests_failed);
    return tests_failed == 0 ? 0 : 1;
}
