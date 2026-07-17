#ifndef SWAN_LEGACY_H
#define SWAN_LEGACY_H

#include <stdbool.h>
#include <stdint.h>

#include <swan/input.h>
#include <swan/types.h>

typedef swan_input_t rf_input_t;

#define RF_DEFAULT_RANDOM_SEED 0x71D3u

void rf_init(bool vertical);
void rf_session_begin(uint16_t random_seed);
void rf_frame(void);
void rf_frame_with_input(uint16_t raw_keys);
void rf_set_orientation(bool vertical);
void rf_clear(void);
void rf_header(const char SWAN_FAR *title, const char SWAN_FAR *subtitle);
void rf_footer(const char SWAN_FAR *help);
void rf_art_load(const uint8_t SWAN_FAR *tiles, uint16_t tile_bytes,
                 const uint16_t SWAN_FAR *tilemap, uint8_t width, uint8_t height,
                 uint8_t screen_x, uint8_t screen_y,
                 const uint16_t SWAN_FAR *palette);
void rf_gfx_show_intro(const uint8_t SWAN_FAR *tiles, uint16_t tile_bytes,
                       const uint16_t SWAN_FAR *tilemap,
                       const uint16_t SWAN_FAR *palette);
void rf_gfx_load(const uint8_t SWAN_FAR *tiles, uint16_t tile_bytes,
                 const uint16_t SWAN_FAR *palette, uint16_t background_tile);
void rf_gfx_fill(uint16_t tile, uint8_t x, uint8_t y, uint8_t width, uint8_t height);
void rf_gfx_put_tile(uint8_t x, uint8_t y, uint16_t tile);
void rf_gfx_put_image(uint8_t x, uint8_t y, const uint16_t SWAN_FAR *tiles,
                      uint8_t width, uint8_t height);
void rf_playfield_begin(void);
void rf_playfield_end(void);
const rf_input_t *rf_input(void);
int8_t rf_dx(uint16_t keys);
int8_t rf_dy(uint16_t keys);
int8_t rf_primary_axis(uint16_t keys);
bool rf_pressed_any_direction(void);
uint16_t rf_frame_count(void);
uint16_t rf_random(void);
uint8_t rf_clamp_u8(int16_t value, uint8_t low, uint8_t high);
void rf_print_bar(uint8_t value, uint8_t maximum, uint8_t width);
void rf_tone(uint16_t hz, uint8_t volume);
void rf_sound_off(void);
void rf_beep(uint16_t hz, uint8_t duration_frames);

#endif
