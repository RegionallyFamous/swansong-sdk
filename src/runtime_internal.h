#ifndef SWAN_RUNTIME_INTERNAL_H
#define SWAN_RUNTIME_INTERNAL_H

#include <stdbool.h>
#include <stdint.h>

#include <swan/audio.h>
#include <swan/gfx.h>

#if defined(__WONDERFUL__) && SWAN_GFX_HARDWARE_TILE_CAPACITY <= 512
#define SWAN_GFX_DIRECT_HARDWARE 1
#else
#define SWAN_GFX_DIRECT_HARDWARE 0
#endif

typedef struct {
    uint16_t first_tile;
    uint16_t tile_count;
    uint16_t staging_tile;
} swan_gfx_tile_upload_t;

const swan_tile_attr_t *swan_gfx_internal_map(uint8_t layer);
const uint8_t *swan_gfx_internal_tile_staging(void);
const swan_gfx_tile_upload_t *swan_gfx_internal_tile_uploads(void);
uint8_t swan_gfx_internal_tile_upload_count(void);
void swan_gfx_internal_tiles_committed(uint16_t generation);
const uint16_t *swan_gfx_internal_palette(uint8_t palette);
bool swan_gfx_internal_palette_set(uint8_t palette);
const swan_sprite_t *swan_gfx_internal_sprites(void);
uint8_t swan_gfx_internal_sprite_capacity(void);
int16_t swan_gfx_internal_scroll_x(uint8_t layer);
int16_t swan_gfx_internal_scroll_y(uint8_t layer);
uint16_t swan_gfx_internal_tiles_generation(void);
uint16_t swan_gfx_internal_map_generation(uint8_t layer);
uint16_t swan_gfx_internal_palette_generation(void);
uint16_t swan_gfx_internal_sprite_generation(void);
uint16_t swan_gfx_internal_scroll_generation(void);
uint16_t swan_gfx_internal_clip_generation(void);
bool swan_gfx_internal_layer_enabled(uint8_t layer);
bool swan_gfx_internal_sprites_enabled(void);
void swan_gfx_internal_set_hardware_tile_capacity(uint16_t tile_capacity);
#if SWAN_GFX_DIRECT_HARDWARE
void swan_platform_gfx_load_tiles(uint16_t first_tile,
                                  const uint8_t SWAN_FAR *data,
                                  uint16_t tile_count);
void swan_platform_gfx_put_tile(uint8_t layer, uint8_t x, uint8_t y,
                                swan_tile_attr_t attr);
swan_tile_attr_t swan_platform_gfx_get_tile(uint8_t layer, uint8_t x,
                                            uint8_t y);
void swan_platform_gfx_set_palette(uint8_t palette,
                                   const uint16_t colors[4]);
void swan_platform_gfx_set_sprite(uint8_t sprite,
                                  const swan_sprite_t *value);
void swan_platform_gfx_get_sprite(uint8_t sprite, swan_sprite_t *value);
void swan_platform_gfx_hide_sprites(uint8_t sprite_capacity);
#endif
const swan_instrument_t SWAN_FAR *swan_audio_internal_instruments(void);
uint8_t swan_audio_internal_instrument_count(void);
bool swan_core_internal_booting(void);
void swan_platform_set_vertical(bool vertical);

#endif
