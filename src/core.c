#include <string.h>

#include <swan/audio.h>
#include <swan/core.h>
#include <swan/debug.h>
#include <swan/gfx.h>

#include "runtime_internal.h"

typedef struct {
    swan_frame_t frame;
    swan_scene_runtime_t scenes;
    uint8_t capabilities;
    bool vertical;
    bool dirty;
    bool animated;
    bool booting;
    bool initialized;
} core_state_t;

static core_state_t core;

#if defined(__GNUC__)
__attribute__((weak))
#endif
void swan_platform_set_vertical(bool vertical) { (void)vertical; }

#if defined(__GNUC__)
__attribute__((weak))
#endif
void swan_platform_reset_audio_hardware(void) {}

void swan_core_init(const swan_core_config_t *config) {
    swan_core_config_t defaults;
    memset(&defaults, 0, sizeof(defaults));
    defaults.initial_scene = 0;
    defaults.capabilities = SWAN_HARDWARE_COLOR;
    defaults.input.repeat_delay = 20;
    defaults.input.repeat_period = 5;
    defaults.input.tap_max_frames = SWAN_INPUT_DEFAULT_TAP_MAX_FRAMES;
    defaults.input.double_tap_window = SWAN_INPUT_DEFAULT_DOUBLE_TAP_WINDOW;
    defaults.input.hold_threshold = SWAN_INPUT_DEFAULT_HOLD_THRESHOLD;
    if (config == 0) config = &defaults;
    memset(&core, 0, sizeof(core));
    swan_debug_reset();
    swan_input_init(&config->input);
    core.capabilities = config->capabilities;
    core.vertical = config->vertical;
    swan_gfx_internal_set_hardware_tile_capacity(
        (config->capabilities & SWAN_HARDWARE_COLOR) != 0 ?
            SWAN_GFX_HARDWARE_TILE_CAPACITY : SWAN_GFX_SPRITE_TILE_CAPACITY);
    swan_gfx_init(0);
    swan_audio_init(0, 0);
    swan_scene_runtime_init(&core.scenes);
    core.frame.input = swan_input_get();
    core.dirty = true;
    core.initialized = true;
    core.booting = true;
    swan_game_boot();
    core.booting = false;
    swan_scene_begin(&core.scenes, config->initial_scene, config->initial_argument);
    swan_scene_render(core.scenes.current);
    core.dirty = false;
    if (swan_gfx_dirty()) swan_gfx_present();
}

void swan_core_step(uint16_t raw_keys) {
#if SWAN_DETERMINISTIC_TRACE
    const swan_gfx_frame_usage_t *usage;
    const swan_audio_voice_t *voices;
    uint8_t trace_flags = 0;
    uint8_t transition_from = SWAN_SCENE_NONE;
    uint8_t transition_to = SWAN_SCENE_NONE;
    uint16_t transition_argument = 0;
    uint8_t audio_voice_mask = 0;
    uint8_t audio_sfx_mask = 0;
    uint8_t channel;
#endif
    if (!core.initialized) {
        SWAN_ASSERT(false, SWAN_PANIC_PLATFORM);
        return;
    }
    swan_input_update(raw_keys);
    ++core.frame.boot_tick;
    ++core.frame.session_tick;
    swan_audio_tick();
#if SWAN_DETERMINISTIC_TRACE
    swan_debug_frame_internal_begin(core.scenes.current, core.frame.boot_tick,
                                    core.frame.session_tick, core.frame.input);
#endif
    swan_scene_update(core.scenes.current, &core.frame);
#if SWAN_DETERMINISTIC_TRACE
    if (core.dirty) trace_flags |= SWAN_DEBUG_FRAME_DIRTY;
    if (core.scenes.pending != SWAN_SCENE_NONE) {
        transition_from = core.scenes.current;
        transition_to = core.scenes.pending;
        transition_argument = core.scenes.pending_argument;
    }
#endif
    if (swan_scene_apply(&core.scenes)) {
        core.dirty = true;
#if SWAN_DETERMINISTIC_TRACE
        trace_flags |= SWAN_DEBUG_FRAME_DIRTY;
#endif
    }
    if (core.dirty || core.animated) {
#if SWAN_DETERMINISTIC_TRACE
        trace_flags |= SWAN_DEBUG_FRAME_RENDERED;
        if (core.animated) trace_flags |= SWAN_DEBUG_FRAME_ANIMATED;
#endif
        swan_scene_render(core.scenes.current);
        core.dirty = false;
    }
    if (swan_gfx_dirty()) {
#if SWAN_DETERMINISTIC_TRACE
        trace_flags |= SWAN_DEBUG_FRAME_PRESENTED;
#endif
        swan_gfx_present();
    }
#if SWAN_DETERMINISTIC_TRACE
    usage = swan_gfx_internal_frame_usage();
    if (usage->scanline_overflow)
        trace_flags |= SWAN_DEBUG_FRAME_SPRITE_OVERFLOW;
    voices = swan_audio_voices();
    for (channel = 0; channel < SWAN_AUDIO_CHANNEL_COUNT; ++channel) {
        if (voices[channel].owner != SWAN_VOICE_SILENT &&
                voices[channel].note != SWAN_AUDIO_NOTE_OFF &&
                voices[channel].volume != 0)
            audio_voice_mask |= (uint8_t)(1u << channel);
        if (voices[channel].owner == SWAN_VOICE_SFX &&
                voices[channel].note != SWAN_AUDIO_NOTE_OFF &&
                voices[channel].volume != 0)
            audio_sfx_mask |= (uint8_t)(1u << channel);
    }
    swan_debug_frame_internal_end(
        core.frame.boot_tick, core.frame.session_tick, core.scenes.current,
        transition_from, transition_to, transition_argument, trace_flags,
        usage->sprites_visible, usage->maximum_sprites_on_scanline,
        audio_voice_mask, audio_sfx_mask,
        (uint8_t)swan_debug_state()->code);
#endif
}

void swan_core_reset_session(void) {
    core.frame.session_tick = 0;
    swan_input_drain();
    swan_audio_stop_all();
    swan_platform_reset_audio_hardware();
    swan_gfx_hide_sprites();
    core.dirty = true;
#if SWAN_DETERMINISTIC_TRACE
    swan_debug_frame_internal_session_reset();
#endif
}

bool swan_core_request_scene(swan_scene_id_t scene, uint16_t argument) {
    return swan_scene_request(&core.scenes, scene, argument);
}

void swan_core_invalidate(void) {
    core.dirty = true;
}

void swan_core_set_animated(bool animated) {
    core.animated = animated;
}

uint32_t swan_core_boot_tick(void) {
    return core.frame.boot_tick;
}

uint32_t swan_core_session_tick(void) {
    return core.frame.session_tick;
}

uint8_t swan_core_capabilities(void) {
    return core.capabilities;
}

bool swan_core_vertical(void) { return core.vertical; }

void swan_core_set_vertical(bool vertical) {
    core.vertical = vertical;
    swan_platform_set_vertical(vertical);
}

const swan_frame_t *swan_core_frame(void) {
    return &core.frame;
}

swan_scene_runtime_t *swan_core_scenes(void) {
    return &core.scenes;
}

bool swan_core_internal_booting(void) { return core.booting; }
