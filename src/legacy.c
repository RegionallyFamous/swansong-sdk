#include <stdio.h>

#include <swan/audio.h>
#include <swan/core.h>
#include <swan/gfx.h>
#include <swan/legacy.h>
#include <swan/random.h>

static uint16_t legacy_frames;
static swan_random_t legacy_random;
static swan_sfx_step_t legacy_step;
static swan_sfx_t legacy_effect;

#if defined(__GNUC__)
__attribute__((weak))
#endif
uint16_t swan_legacy_poll_input(void) { return 0; }

void rf_init(bool vertical) {
    swan_gfx_config_t gfx = { SWAN_GFX_TILE_CAPACITY, SWAN_GFX_PALETTE_CAPACITY,
                              SWAN_GFX_SPRITE_CAPACITY };
    swan_core_set_vertical(vertical);
    legacy_frames = 0;
    swan_random_seed(&legacy_random, 0x71D3u);
    swan_input_init(0);
    swan_gfx_init(&gfx);
    swan_audio_init(0, 0);
    legacy_effect.steps = &legacy_step;
    legacy_effect.step_count = 1;
    legacy_effect.priority = 1;
}

void rf_session_begin(uint16_t random_seed) {
    legacy_frames = 0;
    swan_random_seed(&legacy_random,
                     random_seed == 0 ? RF_DEFAULT_RANDOM_SEED : random_seed);
    swan_core_reset_session();
}

void rf_frame(void) { rf_frame_with_input(swan_legacy_poll_input()); }
void rf_frame_with_input(uint16_t raw_keys) {
    swan_input_update(raw_keys);
    swan_audio_tick();
    ++legacy_frames;
}
void rf_set_orientation(bool vertical) { swan_core_set_vertical(vertical); }
void rf_clear(void) { swan_gfx_fill(0, 0, 0, 32, 32, SWAN_TILE_ATTR(0, 0)); }
void rf_header(const char SWAN_FAR *title, const char SWAN_FAR *subtitle) {
    (void)title; (void)subtitle;
}
void rf_footer(const char SWAN_FAR *help) { (void)help; }
void rf_art_load(const uint8_t SWAN_FAR *tiles, uint16_t tile_bytes,
                 const uint16_t SWAN_FAR *tilemap, uint8_t width, uint8_t height,
                 uint8_t screen_x, uint8_t screen_y,
                 const uint16_t SWAN_FAR *palette) {
    uint8_t x;
    uint8_t y;
    uint16_t local_palette[4];
    if (tiles != 0 && tile_bytes >= 16)
        swan_gfx_load_tiles(1, tiles, (uint16_t)(tile_bytes / 16u));
    if (palette != 0) {
        for (x = 0; x < 4; ++x) local_palette[x] = palette[x];
        swan_gfx_set_palette(0, local_palette);
    }
    for (y = 0; y < height; ++y)
        for (x = 0; x < width; ++x)
            swan_gfx_put_tile(0, (uint8_t)(screen_x + x), (uint8_t)(screen_y + y),
                              tilemap[(uint16_t)y * width + x]);
}
void rf_gfx_show_intro(const uint8_t SWAN_FAR *tiles, uint16_t tile_bytes,
                       const uint16_t SWAN_FAR *tilemap,
                       const uint16_t SWAN_FAR *palette) {
    rf_gfx_load(tiles, tile_bytes, palette, 0);
    rf_gfx_put_image(0, 0, tilemap, 28, 18);
}
void rf_gfx_load(const uint8_t SWAN_FAR *tiles, uint16_t tile_bytes,
                 const uint16_t SWAN_FAR *palette, uint16_t background_tile) {
    uint16_t local_palette[4];
    uint8_t index;
    if (tiles != 0 && tile_bytes >= 16)
        swan_gfx_load_tiles(0, tiles, (uint16_t)(tile_bytes / 16u));
    if (palette != 0) {
        for (index = 0; index < 4; ++index) local_palette[index] = palette[index];
        swan_gfx_set_palette(0, local_palette);
    }
    swan_gfx_fill(0, 0, 0, 32, 32, SWAN_TILE_ATTR(background_tile, 0));
}
void rf_gfx_fill(uint16_t tile, uint8_t x, uint8_t y, uint8_t width, uint8_t height) {
    swan_gfx_fill(0, x, y, width, height, SWAN_TILE_ATTR(tile, 0));
}
void rf_gfx_put_tile(uint8_t x, uint8_t y, uint16_t tile) {
    swan_gfx_put_tile(0, x, y, SWAN_TILE_ATTR(tile, 0));
}
void rf_gfx_put_image(uint8_t x, uint8_t y, const uint16_t SWAN_FAR *tiles,
                      uint8_t width, uint8_t height) {
    uint8_t px;
    uint8_t py;
    for (py = 0; py < height; ++py)
        for (px = 0; px < width; ++px)
            rf_gfx_put_tile((uint8_t)(x + px), (uint8_t)(y + py),
                            tiles[(uint16_t)py * width + px]);
}
void rf_playfield_begin(void) { }
void rf_playfield_end(void) { }
const rf_input_t *rf_input(void) { return swan_input_get(); }
int8_t rf_dx(uint16_t keys) { return swan_input_dx(keys); }
int8_t rf_dy(uint16_t keys) { return swan_input_dy(keys); }
int8_t rf_primary_axis(uint16_t keys) {
    int8_t value = rf_dx(keys);
    return value != 0 ? value : rf_dy(keys);
}
bool rf_pressed_any_direction(void) {
    return rf_dx(rf_input()->pressed) != 0 || rf_dy(rf_input()->pressed) != 0;
}
uint16_t rf_frame_count(void) {
    uint32_t session = swan_core_session_tick();
    uint32_t value = session > legacy_frames ? session : legacy_frames;
    return value > UINT16_MAX ? UINT16_MAX : (uint16_t)value;
}
uint16_t rf_random(void) { return swan_random_next(&legacy_random); }
uint8_t rf_clamp_u8(int16_t value, uint8_t low, uint8_t high) {
    if (value < low) return low;
    if (value > high) return high;
    return (uint8_t)value;
}
void rf_print_bar(uint8_t value, uint8_t maximum, uint8_t width) {
    uint8_t filled = maximum ? (uint8_t)(((uint16_t)value * width) / maximum) : 0;
    uint8_t i;
    putchar('[');
    for (i = 0; i < width; ++i) putchar(i < filled ? '#' : '.');
    putchar(']');
}
void rf_tone(uint16_t hz, uint8_t volume) {
    uint16_t note = hz / 16u;
    legacy_step.command.note = note > 127u ? 127u : (uint8_t)note;
    legacy_step.command.instrument = 0;
    legacy_step.command.volume = volume > 15 ? 15 : volume;
    legacy_step.duration_frames = UINT8_MAX;
    swan_audio_play_sfx(&legacy_effect);
}
void rf_sound_off(void) { swan_audio_stop_all(); }
void rf_beep(uint16_t hz, uint8_t duration_frames) {
    uint16_t note = hz / 16u;
    legacy_step.command.note = note > 127u ? 127u : (uint8_t)note;
    legacy_step.command.instrument = 0;
    legacy_step.command.volume = 6;
    legacy_step.duration_frames = duration_frames == 0 ? 1 : duration_frames;
    swan_audio_play_sfx(&legacy_effect);
}
