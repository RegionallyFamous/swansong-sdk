#include <string.h>

#include <wonderful.h>
#include <ws.h>
#include <wse/memory.h>

#include <swan/swan.h>

#include "runtime_internal.h"

#ifndef SWAN_GFX_HARDWARE_TILE_CAPACITY
#define SWAN_GFX_HARDWARE_TILE_CAPACITY 1024
#endif

#if SWAN_GFX_HARDWARE_TILE_CAPACITY > 512
WSE_RESERVE_TILES(1024, 0);
#else
WSE_RESERVE_TILES(512, 0);
#endif

static bool color_active;
#if !SWAN_GFX_DIRECT_HARDWARE
static uint16_t tiles_generation;
static uint16_t map_generation[2];
#endif
static uint16_t palette_generation;
static uint16_t sprite_generation;
static uint16_t scroll_generation;
static uint16_t clip_generation;

#if SWAN_GFX_DIRECT_HARDWARE
void swan_platform_gfx_load_tiles(uint16_t first_tile,
                                  const uint8_t SWAN_FAR *data,
                                  uint16_t tile_count) {
    uint8_t ws_iram *destination = (uint8_t ws_iram *)WS_TILE_MEM(first_tile);
    uint16_t byte_count = (uint16_t)(tile_count * 16u);
    uint16_t index;
    for (index = 0; index < byte_count; ++index) destination[index] = data[index];
}

void swan_platform_gfx_put_tile(uint8_t layer, uint8_t x, uint8_t y,
                                swan_tile_attr_t attr) {
    ws_screen_t ws_iram *screen = layer == 0 ? &wse_screen1 : &wse_screen2;
    screen->row[y].cell[x] = attr;
}

swan_tile_attr_t swan_platform_gfx_get_tile(uint8_t layer, uint8_t x,
                                            uint8_t y) {
    ws_screen_t ws_iram *screen = layer == 0 ? &wse_screen1 : &wse_screen2;
    return screen->row[y].cell[x];
}

void swan_platform_gfx_set_palette(uint8_t palette,
                                   const uint16_t colors[4]) {
    if (color_active)
        memcpy(WS_SCREEN_COLOR_MEM(palette), colors, 4u * sizeof(uint16_t));
    else
        outportw((uint8_t)(WS_SCR_PAL_0_PORT + palette * 2u),
                 WS_DISPLAY_MONO_PALETTE(0, 7, 4, 2));
}

void swan_platform_gfx_set_sprite(uint8_t sprite,
                                  const swan_sprite_t *value) {
    wse_sprites1.entry[sprite].attr = (uint16_t)(
        value->tile |
        ((uint16_t)value->palette << SWAN_TILE_PALETTE_SHIFT) |
        ((value->flags & SWAN_SPRITE_FLAG_OUTSIDE_CLIP) ?
            WS_SPRITE_ATTR_OUTSIDE : 0) |
        ((value->flags & SWAN_SPRITE_FLAG_PRIORITY) ?
            WS_SPRITE_ATTR_PRIORITY : 0) |
        ((value->flags & SWAN_SPRITE_FLAG_HFLIP) ?
            WS_SPRITE_ATTR_FLIP_H : 0) |
        ((value->flags & SWAN_SPRITE_FLAG_VFLIP) ?
            WS_SPRITE_ATTR_FLIP_V : 0));
    wse_sprites1.entry[sprite].x = value->visible ? (uint8_t)value->x : 224u;
    wse_sprites1.entry[sprite].y = value->visible ? (uint8_t)value->y : 144u;
}

void swan_platform_gfx_get_sprite(uint8_t sprite, swan_sprite_t *value) {
    uint16_t attr = wse_sprites1.entry[sprite].attr;
    value->x = wse_sprites1.entry[sprite].x;
    value->y = wse_sprites1.entry[sprite].y;
    value->tile = attr & SWAN_TILE_INDEX_MASK;
    value->palette = (uint8_t)((attr >> SWAN_TILE_PALETTE_SHIFT) & 7u);
    value->flags = (uint8_t)(
        ((attr & WS_SPRITE_ATTR_OUTSIDE) ? SWAN_SPRITE_FLAG_OUTSIDE_CLIP : 0) |
        ((attr & WS_SPRITE_ATTR_PRIORITY) ? SWAN_SPRITE_FLAG_PRIORITY : 0) |
        ((attr & WS_SPRITE_ATTR_FLIP_H) ? SWAN_SPRITE_FLAG_HFLIP : 0) |
        ((attr & WS_SPRITE_ATTR_FLIP_V) ? SWAN_SPRITE_FLAG_VFLIP : 0));
    value->visible = false;
}

void swan_platform_gfx_hide_sprites(uint8_t sprite_capacity) {
    uint8_t sprite;
    for (sprite = 0; sprite < sprite_capacity; ++sprite) {
        wse_sprites1.entry[sprite].x = 224u;
        wse_sprites1.entry[sprite].y = 144u;
    }
}
#endif

static uint16_t note_frequency(uint8_t note) {
    static const uint8_t base_hz[12] = {
        65, 69, 73, 78, 82, 87, 92, 98, 104, 110, 117, 123
    };
    uint16_t hz;
    uint8_t octave;
    if (note == SWAN_AUDIO_NOTE_OFF || note == SWAN_AUDIO_NO_CHANGE) return 0;
    octave = (uint8_t)(note / 12u);
    if (octave > 5) octave = 5;
    hz = (uint16_t)base_hz[note % 12u] << octave;
    return WS_SOUND_WAVE_HZ_TO_FREQ(hz, 32);
}

void swan_platform_set_vertical(bool vertical) {
    ws_display_set_icons(vertical ? WS_LCD_ICON_ORIENT_V : WS_LCD_ICON_ORIENT_H);
}

void swan_platform_reset_audio_hardware(void) {
    ws_sound_reset();
    outportw(WS_SOUND_VOL_CH1_PORT, 0);
    outportw(WS_SOUND_VOL_CH3_PORT, 0);
    ws_sound_set_wavetable_address(&wse_wavetable1);
    outportb(WS_SOUND_OUT_CTRL_PORT,
             WS_SOUND_OUT_CTRL_SPEAKER_ENABLE |
             WS_SOUND_OUT_CTRL_HEADPHONE_ENABLE |
             WS_SOUND_OUT_CTRL_SPEAKER_VOLUME_100);
}

static void commit_graphics(void) {
    uint8_t layer;
    uint16_t generation;
#if !SWAN_GFX_DIRECT_HARDWARE
    generation = swan_gfx_internal_tiles_generation();
    if (generation != tiles_generation ||
        swan_gfx_internal_tile_upload_count() != 0) {
        const swan_gfx_tile_upload_t *uploads = swan_gfx_internal_tile_uploads();
        const uint8_t *staging = swan_gfx_internal_tile_staging();
        uint8_t count = swan_gfx_internal_tile_upload_count();
        uint8_t upload;
        for (upload = 0; upload < count; ++upload) {
            uint16_t bytes = (uint16_t)(uploads[upload].tile_count * 16u);
            const uint8_t *source = staging + uploads[upload].staging_tile * 16u;
            if (!color_active &&
                uploads[upload].first_tile + uploads[upload].tile_count >
                    SWAN_GFX_SPRITE_TILE_CAPACITY) {
                SWAN_ASSERT(false, SWAN_PANIC_RESOURCE_LIMIT);
                continue;
            }
            if (color_active)
                ws_gdma_copy(WS_TILE_MEM(uploads[upload].first_tile), source, bytes);
            else
                memcpy(WS_TILE_MEM(uploads[upload].first_tile), source, bytes);
        }
        tiles_generation = generation;
        swan_gfx_internal_tiles_committed(generation);
    }
    for (layer = 0; layer < 2; ++layer) {
        ws_screen_t ws_iram *destination = layer == 0 ? &wse_screen1 : &wse_screen2;
        generation = swan_gfx_internal_map_generation(layer);
        if (generation != map_generation[layer]) {
            if (color_active) ws_gdma_copy(destination, swan_gfx_internal_map(layer), sizeof(ws_screen_t));
            else memcpy(destination, swan_gfx_internal_map(layer), sizeof(ws_screen_t));
            map_generation[layer] = generation;
        }
    }
#else
    (void)layer;
#endif
    generation = swan_gfx_internal_palette_generation();
    if (generation != palette_generation) {
        uint8_t palette;
#if SWAN_GFX_DIRECT_HARDWARE
        if (!color_active) {
            for (palette = 0; palette < SWAN_GFX_PALETTE_CAPACITY; ++palette)
                outportw((uint8_t)(WS_SCR_PAL_0_PORT + palette * 2u),
                         WS_DISPLAY_MONO_PALETTE(0, 7, 4, 2));
        }
#else
        if (color_active) {
            for (palette = 0; palette < SWAN_GFX_PALETTE_CAPACITY; ++palette) {
                if (swan_gfx_internal_palette_set(palette))
                    memcpy(WS_SCREEN_COLOR_MEM(palette),
                           swan_gfx_internal_palette(palette), 4u * sizeof(uint16_t));
            }
        } else {
            for (palette = 0; palette < SWAN_GFX_PALETTE_CAPACITY; ++palette)
                outportw((uint8_t)(WS_SCR_PAL_0_PORT + palette * 2u),
                         WS_DISPLAY_MONO_PALETTE(0, 7, 4, 2));
        }
#endif
        palette_generation = generation;
    }
    generation = swan_gfx_internal_sprite_generation();
    if (generation != sprite_generation) {
        uint8_t count = swan_gfx_internal_sprite_capacity();
#if !SWAN_GFX_DIRECT_HARDWARE
        const swan_sprite_t *source = swan_gfx_internal_sprites();
        uint8_t sprite;
        for (sprite = 0; sprite < count; ++sprite) {
            wse_sprites1.entry[sprite].attr = (uint16_t)(
                source[sprite].tile |
                ((uint16_t)source[sprite].palette << SWAN_TILE_PALETTE_SHIFT) |
                ((source[sprite].flags & SWAN_SPRITE_FLAG_OUTSIDE_CLIP) ?
                    WS_SPRITE_ATTR_OUTSIDE : 0) |
                ((source[sprite].flags & SWAN_SPRITE_FLAG_PRIORITY) ?
                    WS_SPRITE_ATTR_PRIORITY : 0) |
                ((source[sprite].flags & SWAN_SPRITE_FLAG_HFLIP) ?
                    WS_SPRITE_ATTR_FLIP_H : 0) |
                ((source[sprite].flags & SWAN_SPRITE_FLAG_VFLIP) ?
                    WS_SPRITE_ATTR_FLIP_V : 0));
            wse_sprites1.entry[sprite].x = source[sprite].visible ? (uint8_t)source[sprite].x : 224u;
            wse_sprites1.entry[sprite].y = source[sprite].visible ? (uint8_t)source[sprite].y : 144u;
        }
#endif
        outportb(WS_SPR_FIRST_PORT, 0);
        outportb(WS_SPR_COUNT_PORT, count);
        sprite_generation = generation;
    }
    generation = swan_gfx_internal_scroll_generation();
    if (generation != scroll_generation) {
        ws_display_scroll_screen1_to((uint8_t)swan_gfx_internal_scroll_x(0),
                                     (uint8_t)swan_gfx_internal_scroll_y(0));
        ws_display_scroll_screen2_to((uint8_t)swan_gfx_internal_scroll_x(1),
                                     (uint8_t)swan_gfx_internal_scroll_y(1));
        scroll_generation = generation;
    }
    generation = swan_gfx_internal_clip_generation();
    if (generation != clip_generation) {
        const swan_gfx_clip_t *clip = swan_gfx_layer_clip(1);
        if (clip != 0)
            ws_display_set_screen2_window(clip->x, clip->y,
                                          clip->width, clip->height);
        clip = swan_gfx_sprite_clip();
        if (clip != 0)
            ws_display_set_sprite_window(clip->x, clip->y,
                                         clip->width, clip->height);
        clip_generation = generation;
    }
    ws_display_set_control(
        (swan_gfx_internal_layer_enabled(0) ? WS_DISPLAY_CTRL_SCR1_ENABLE : 0) |
        (swan_gfx_internal_layer_enabled(1) ? WS_DISPLAY_CTRL_SCR2_ENABLE : 0) |
        (swan_gfx_internal_sprites_enabled() ? WS_DISPLAY_CTRL_SPR_ENABLE : 0) |
        (swan_gfx_sprite_clip() != 0 ? WS_DISPLAY_CTRL_SPR_WIN_ENABLE : 0) |
        (swan_gfx_layer_clip_mode(1) == SWAN_GFX_CLIP_INSIDE ?
            WS_DISPLAY_CTRL_SCR2_WIN_INSIDE : 0) |
        (swan_gfx_layer_clip_mode(1) == SWAN_GFX_CLIP_OUTSIDE ?
            WS_DISPLAY_CTRL_SCR2_WIN_OUTSIDE : 0));
}

static void commit_audio(void) {
    static const uint8_t frequency_ports[4] = {
        WS_SOUND_FREQ_CH1_PORT, WS_SOUND_FREQ_CH2_PORT,
        WS_SOUND_FREQ_CH3_PORT, WS_SOUND_FREQ_CH4_PORT
    };
    static const uint8_t volume_ports[4] = {
        WS_SOUND_VOL_CH1_PORT, WS_SOUND_VOL_CH2_PORT,
        WS_SOUND_VOL_CH3_PORT, WS_SOUND_VOL_CH4_PORT
    };
    const swan_audio_voice_t *voices = swan_audio_voices();
    const swan_instrument_t SWAN_FAR *instruments = swan_audio_internal_instruments();
    uint8_t instrument_count = swan_audio_internal_instrument_count();
    uint8_t enabled = 0;
    uint8_t channel;
    for (channel = 0; channel < 4; ++channel) {
        if (voices[channel].owner != SWAN_VOICE_SILENT &&
            voices[channel].note != SWAN_AUDIO_NOTE_OFF) {
            uint8_t sample;
            outportw(frequency_ports[channel], note_frequency(voices[channel].note));
            outportb(volume_ports[channel],
                     (uint8_t)((voices[channel].volume << 4) | voices[channel].volume));
            if (instruments != 0 && voices[channel].instrument < instrument_count) {
                for (sample = 0; sample < 16; ++sample)
                    wse_wavetable1.wave[channel].data[sample] =
                        instruments[voices[channel].instrument].wave[sample];
            }
            enabled |= (uint8_t)(1u << channel);
        } else {
            outportb(volume_ports[channel], 0);
        }
    }
    outportb(WS_SOUND_CH_CTRL_PORT, enabled);
}

void main(void) {
    swan_core_config_t config = swan_game_config;
    ws_display_set_control(0);
    ws_display_set_screen_addresses(&wse_screen1, &wse_screen2);
    ws_display_set_sprite_address(&wse_sprites1);
    memset(&wse_screen1, 0, sizeof(wse_screen1));
    memset(&wse_screen2, 0, sizeof(wse_screen2));
    memset(&wse_sprites1, 0, sizeof(wse_sprites1));
    color_active = ws_system_set_mode(WS_MODE_COLOR);
    if (!color_active)
        ws_display_set_shade_lut(WS_DISPLAY_SHADE_LUT_DEFAULT);
    config.capabilities = (uint8_t)((config.capabilities & SWAN_HARDWARE_RTC) |
        (color_active ? SWAN_HARDWARE_COLOR : SWAN_HARDWARE_MONO));
    ws_display_set_icons(config.vertical ? WS_LCD_ICON_ORIENT_V : WS_LCD_ICON_ORIENT_H);
    ws_display_scroll_screen1_to(0, 0);
    ws_display_scroll_screen2_to(0, 0);
    swan_platform_reset_audio_hardware();
    /* Keep the display disabled until the first fully prepared frame. */
    swan_core_init(&config);
    commit_graphics();
    commit_audio();
    ws_int_set_default_handler_vblank();
    ws_int_enable(WS_INT_ENABLE_VBLANK);
    ia16_enable_irq();
    while (1) {
        ia16_halt();
        commit_graphics();
        commit_audio();
        swan_core_step(swan_ws_translate_keys(ws_keypad_scan()));
    }
}
