#ifndef SWAN_GFX_H
#define SWAN_GFX_H

#include <stdbool.h>
#include <stdint.h>
#include <swan/types.h>

#define SWAN_GFX_LAYER_COUNT 2u
#define SWAN_GFX_MAP_WIDTH 32u
#define SWAN_GFX_MAP_HEIGHT 32u
#define SWAN_GFX_DISPLAY_WIDTH 224u
#define SWAN_GFX_DISPLAY_HEIGHT 144u
#define SWAN_GFX_TILE_CAPACITY 1024u
#define SWAN_GFX_SPRITE_TILE_CAPACITY 512u
#define SWAN_GFX_TILE_UPLOAD_CAPACITY 512u
#define SWAN_GFX_TILE_UPLOAD_BATCH_CAPACITY 16u
#ifndef SWAN_GFX_HARDWARE_TILE_CAPACITY
#define SWAN_GFX_HARDWARE_TILE_CAPACITY SWAN_GFX_TILE_CAPACITY
#endif
#define SWAN_GFX_PALETTE_CAPACITY 16u
#define SWAN_GFX_SPRITE_CAPACITY 128u
#define SWAN_GFX_SPRITES_PER_SCANLINE 32u

typedef uint16_t swan_tile_attr_t;

#define SWAN_TILE_INDEX_MASK 0x01FFu
#define SWAN_TILE_BANK_MASK 0x2000u
#define SWAN_TILE_PALETTE_SHIFT 9u
#define SWAN_TILE_HFLIP 0x4000u
#define SWAN_TILE_VFLIP 0x8000u
#define SWAN_TILE_ATTR(tile, palette) \
    ((swan_tile_attr_t)(((tile) & SWAN_TILE_INDEX_MASK) | \
        (((tile) & 0x0200u) << 4) | \
        (((palette) & 15u) << SWAN_TILE_PALETTE_SHIFT)))

#define SWAN_SPRITE_FLAG_OUTSIDE_CLIP (1u << 0)
#define SWAN_SPRITE_FLAG_PRIORITY (1u << 1)
#define SWAN_SPRITE_FLAG_HFLIP (1u << 2)
#define SWAN_SPRITE_FLAG_VFLIP (1u << 3)
#define SWAN_SPRITE_FLAG_MASK 0x0Fu

typedef struct {
    int16_t x;
    int16_t y;
} swan_camera_t;

typedef struct {
    uint8_t x;
    uint8_t y;
    uint8_t width;
    uint8_t height;
} swan_gfx_clip_t;

typedef enum {
    SWAN_GFX_CLIP_DISABLED = 0,
    SWAN_GFX_CLIP_INSIDE,
    SWAN_GFX_CLIP_OUTSIDE
} swan_gfx_clip_mode_t;

typedef struct {
    int16_t x;
    int16_t y;
    uint16_t tile;
    uint8_t palette;
    uint8_t flags;
    bool visible;
} swan_sprite_t;

typedef struct {
    uint16_t tile_capacity;
    uint8_t palette_capacity;
    uint8_t sprite_capacity;
} swan_gfx_config_t;

typedef struct {
    uint16_t highest_tile;
    uint8_t palettes_used;
    uint8_t sprites_visible;
    uint8_t maximum_sprites_on_scanline;
    bool scanline_overflow;
} swan_gfx_usage_t;

void swan_gfx_init(const swan_gfx_config_t *config);
uint16_t swan_gfx_tile_index(swan_tile_attr_t attr);
bool swan_gfx_load_tiles(uint16_t first_tile, const uint8_t SWAN_FAR *data,
                         uint16_t tile_count);
bool swan_gfx_put_tile(uint8_t layer, uint8_t x, uint8_t y, swan_tile_attr_t attr);
bool swan_gfx_fill(uint8_t layer, uint8_t x, uint8_t y, uint8_t width,
                   uint8_t height, swan_tile_attr_t attr);
swan_tile_attr_t swan_gfx_get_tile(uint8_t layer, uint8_t x, uint8_t y);
bool swan_gfx_set_camera(uint8_t layer, int16_t x, int16_t y);
const swan_camera_t *swan_gfx_camera(uint8_t layer);
bool swan_gfx_camera_project(uint8_t layer, int16_t world_x, int16_t world_y,
                             int16_t *screen_x, int16_t *screen_y);
void swan_gfx_set_scroll(uint8_t layer, int16_t x, int16_t y);
bool swan_gfx_set_layer_clip(uint8_t layer, swan_gfx_clip_mode_t mode,
                             const swan_gfx_clip_t *clip);
swan_gfx_clip_mode_t swan_gfx_layer_clip_mode(uint8_t layer);
const swan_gfx_clip_t *swan_gfx_layer_clip(uint8_t layer);
bool swan_gfx_set_sprite_clip(const swan_gfx_clip_t *clip);
const swan_gfx_clip_t *swan_gfx_sprite_clip(void);
void swan_gfx_set_layer_enabled(uint8_t layer, bool enabled);
bool swan_gfx_layer_enabled(uint8_t layer);
bool swan_gfx_set_palette(uint8_t palette, const uint16_t colors[4]);
bool swan_gfx_set_sprite(uint8_t sprite, const swan_sprite_t *value);
void swan_gfx_hide_sprites(void);
void swan_gfx_set_sprites_enabled(bool enabled);
bool swan_gfx_sprites_enabled(void);
void swan_gfx_present(void);
bool swan_gfx_dirty(void);
/* Computes exact resource and scanline diagnostics on demand. */
const swan_gfx_usage_t *swan_gfx_usage(void);

#endif
