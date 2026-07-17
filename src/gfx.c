#include <string.h>

#include <swan/debug.h>
#include <swan/gfx.h>

#include "runtime_internal.h"

typedef struct {
#if !SWAN_GFX_DIRECT_HARDWARE
    uint8_t tile_staging[SWAN_GFX_TILE_UPLOAD_CAPACITY][16];
    swan_gfx_tile_upload_t tile_uploads[SWAN_GFX_TILE_UPLOAD_BATCH_CAPACITY];
    swan_tile_attr_t maps[SWAN_GFX_LAYER_COUNT][SWAN_GFX_MAP_HEIGHT][SWAN_GFX_MAP_WIDTH];
    uint16_t palettes[SWAN_GFX_PALETTE_CAPACITY][4];
    swan_sprite_t sprites[SWAN_GFX_SPRITE_CAPACITY];
#else
    uint8_t sprite_visible[SWAN_GFX_SPRITE_CAPACITY / 8u];
#endif
    swan_camera_t cameras[SWAN_GFX_LAYER_COUNT];
    swan_gfx_clip_t layer_clip;
    swan_gfx_clip_t sprite_clip;
    swan_gfx_config_t limits;
    swan_gfx_usage_t usage;
    uint16_t palette_set;
    uint16_t staged_tile_count;
    uint16_t tiles_generation;
    uint16_t map_generation[SWAN_GFX_LAYER_COUNT];
    uint16_t palette_generation;
    uint16_t sprite_generation;
    uint16_t scroll_generation;
    uint16_t clip_generation;
    uint8_t tile_upload_count;
    swan_gfx_clip_mode_t layer_clip_mode;
    bool layer_enabled[SWAN_GFX_LAYER_COUNT];
    bool sprites_enabled;
    bool sprite_clip_enabled;
    bool dirty;
} swan_gfx_state_t;

static swan_gfx_state_t gfx;
static uint16_t hardware_tile_capacity = SWAN_GFX_TILE_CAPACITY;

uint16_t swan_gfx_tile_index(swan_tile_attr_t attr) {
    return (uint16_t)((attr & SWAN_TILE_INDEX_MASK) |
        ((attr & SWAN_TILE_BANK_MASK) >> 4));
}

static bool valid_background_attr(swan_tile_attr_t attr) {
    uint16_t tile = swan_gfx_tile_index(attr);
    uint8_t palette = (uint8_t)((attr >> SWAN_TILE_PALETTE_SHIFT) & 15u);
    return tile < gfx.limits.tile_capacity && palette < gfx.limits.palette_capacity;
}

static bool valid_clip(const swan_gfx_clip_t *clip) {
    return clip != 0 && clip->width != 0 && clip->height != 0 &&
        clip->x < SWAN_GFX_DISPLAY_WIDTH && clip->y < SWAN_GFX_DISPLAY_HEIGHT &&
        clip->width <= SWAN_GFX_DISPLAY_WIDTH - clip->x &&
        clip->height <= SWAN_GFX_DISPLAY_HEIGHT - clip->y;
}

void swan_gfx_init(const swan_gfx_config_t *config) {
    memset(&gfx, 0, sizeof(gfx));
    gfx.limits.tile_capacity = hardware_tile_capacity;
    gfx.limits.palette_capacity = SWAN_GFX_PALETTE_CAPACITY;
    gfx.limits.sprite_capacity = SWAN_GFX_SPRITE_CAPACITY;
    if (config != 0) {
        if (config->tile_capacity != 0 &&
            config->tile_capacity <= hardware_tile_capacity)
            gfx.limits.tile_capacity = config->tile_capacity;
        if (config->palette_capacity != 0 && config->palette_capacity <= SWAN_GFX_PALETTE_CAPACITY)
            gfx.limits.palette_capacity = config->palette_capacity;
        if (config->sprite_capacity != 0 && config->sprite_capacity <= SWAN_GFX_SPRITE_CAPACITY)
            gfx.limits.sprite_capacity = config->sprite_capacity;
    }
    gfx.dirty = true;
    gfx.tiles_generation = 1;
    gfx.map_generation[0] = 1;
    gfx.map_generation[1] = 1;
    gfx.palette_generation = 1;
    gfx.sprite_generation = 1;
    gfx.scroll_generation = 1;
    gfx.clip_generation = 1;
    gfx.layer_enabled[0] = true;
    gfx.layer_enabled[1] = false;
    gfx.sprites_enabled = true;
}

bool swan_gfx_load_tiles(uint16_t first_tile, const uint8_t SWAN_FAR *data,
                         uint16_t tile_count) {
#if !SWAN_GFX_DIRECT_HARDWARE
    uint16_t byte_count;
    uint16_t index;
    swan_gfx_tile_upload_t *upload;
#endif
    if (data == 0 || tile_count == 0 || first_tile >= gfx.limits.tile_capacity ||
        tile_count > gfx.limits.tile_capacity - first_tile
#if !SWAN_GFX_DIRECT_HARDWARE
        ||
        tile_count > SWAN_GFX_TILE_UPLOAD_CAPACITY - gfx.staged_tile_count ||
        gfx.tile_upload_count >= SWAN_GFX_TILE_UPLOAD_BATCH_CAPACITY
#endif
        ) {
        SWAN_ASSERT(false, SWAN_PANIC_RESOURCE_LIMIT);
        return false;
    }
#if SWAN_GFX_DIRECT_HARDWARE
    swan_platform_gfx_load_tiles(first_tile, data, tile_count);
#else
    upload = &gfx.tile_uploads[gfx.tile_upload_count++];
    upload->first_tile = first_tile;
    upload->tile_count = tile_count;
    upload->staging_tile = gfx.staged_tile_count;
    byte_count = (uint16_t)(tile_count * 16u);
    for (index = 0; index < byte_count; ++index)
        ((uint8_t *)gfx.tile_staging)[(uint16_t)(gfx.staged_tile_count * 16u) + index] =
            data[index];
    gfx.staged_tile_count = (uint16_t)(gfx.staged_tile_count + tile_count);
#endif
    ++gfx.tiles_generation;
    gfx.dirty = true;
    return true;
}

bool swan_gfx_put_tile(uint8_t layer, uint8_t x, uint8_t y, swan_tile_attr_t attr) {
    if (layer >= SWAN_GFX_LAYER_COUNT || x >= SWAN_GFX_MAP_WIDTH ||
        y >= SWAN_GFX_MAP_HEIGHT || !valid_background_attr(attr)) {
        SWAN_ASSERT(false, SWAN_PANIC_RESOURCE_LIMIT);
        return false;
    }
#if SWAN_GFX_DIRECT_HARDWARE
    swan_platform_gfx_put_tile(layer, x, y, attr);
#else
    gfx.maps[layer][y][x] = attr;
#endif
    ++gfx.map_generation[layer];
    gfx.dirty = true;
    return true;
}

bool swan_gfx_fill(uint8_t layer, uint8_t x, uint8_t y, uint8_t width,
                   uint8_t height, swan_tile_attr_t attr) {
    uint8_t px;
    uint8_t py;
    if (layer >= SWAN_GFX_LAYER_COUNT || width == 0 || height == 0 ||
        x >= SWAN_GFX_MAP_WIDTH || y >= SWAN_GFX_MAP_HEIGHT ||
        width > SWAN_GFX_MAP_WIDTH - x || height > SWAN_GFX_MAP_HEIGHT - y ||
        !valid_background_attr(attr)) {
        SWAN_ASSERT(false, SWAN_PANIC_RESOURCE_LIMIT);
        return false;
    }
    for (py = y; py < (uint8_t)(y + height); ++py) {
        for (px = x; px < (uint8_t)(x + width); ++px) {
#if SWAN_GFX_DIRECT_HARDWARE
            swan_platform_gfx_put_tile(layer, px, py, attr);
#else
            gfx.maps[layer][py][px] = attr;
#endif
        }
    }
    ++gfx.map_generation[layer];
    gfx.dirty = true;
    return true;
}

swan_tile_attr_t swan_gfx_get_tile(uint8_t layer, uint8_t x, uint8_t y) {
    if (layer >= SWAN_GFX_LAYER_COUNT || x >= SWAN_GFX_MAP_WIDTH ||
        y >= SWAN_GFX_MAP_HEIGHT) return 0;
#if SWAN_GFX_DIRECT_HARDWARE
    return swan_platform_gfx_get_tile(layer, x, y);
#else
    return gfx.maps[layer][y][x];
#endif
}

bool swan_gfx_set_camera(uint8_t layer, int16_t x, int16_t y) {
    if (layer >= SWAN_GFX_LAYER_COUNT) {
        SWAN_ASSERT(false, SWAN_PANIC_BAD_ARGUMENT);
        return false;
    }
    gfx.cameras[layer].x = x;
    gfx.cameras[layer].y = y;
    ++gfx.scroll_generation;
    gfx.dirty = true;
    return true;
}

const swan_camera_t *swan_gfx_camera(uint8_t layer) {
    return layer < SWAN_GFX_LAYER_COUNT ? &gfx.cameras[layer] : 0;
}

bool swan_gfx_camera_project(uint8_t layer, int16_t world_x, int16_t world_y,
                             int16_t *screen_x, int16_t *screen_y) {
    int32_t x;
    int32_t y;
    if (layer >= SWAN_GFX_LAYER_COUNT || screen_x == 0 || screen_y == 0) {
        SWAN_ASSERT(false, SWAN_PANIC_BAD_ARGUMENT);
        return false;
    }
    x = (int32_t)world_x - gfx.cameras[layer].x;
    y = (int32_t)world_y - gfx.cameras[layer].y;
    if (x < INT16_MIN || x > INT16_MAX || y < INT16_MIN || y > INT16_MAX)
        return false;
    *screen_x = (int16_t)x;
    *screen_y = (int16_t)y;
    return true;
}

void swan_gfx_set_scroll(uint8_t layer, int16_t x, int16_t y) {
    (void)swan_gfx_set_camera(layer, x, y);
}

bool swan_gfx_set_layer_clip(uint8_t layer, swan_gfx_clip_mode_t mode,
                             const swan_gfx_clip_t *clip) {
    if (layer != 1 || mode > SWAN_GFX_CLIP_OUTSIDE ||
        (mode != SWAN_GFX_CLIP_DISABLED && !valid_clip(clip))) {
        SWAN_ASSERT(false, SWAN_PANIC_BAD_ARGUMENT);
        return false;
    }
    gfx.layer_clip_mode = mode;
    if (mode != SWAN_GFX_CLIP_DISABLED) gfx.layer_clip = *clip;
    ++gfx.clip_generation;
    gfx.dirty = true;
    return true;
}

swan_gfx_clip_mode_t swan_gfx_layer_clip_mode(uint8_t layer) {
    return layer == 1 ? gfx.layer_clip_mode : SWAN_GFX_CLIP_DISABLED;
}

const swan_gfx_clip_t *swan_gfx_layer_clip(uint8_t layer) {
    return layer == 1 && gfx.layer_clip_mode != SWAN_GFX_CLIP_DISABLED ?
        &gfx.layer_clip : 0;
}

bool swan_gfx_set_sprite_clip(const swan_gfx_clip_t *clip) {
    if (clip != 0 && !valid_clip(clip)) {
        SWAN_ASSERT(false, SWAN_PANIC_BAD_ARGUMENT);
        return false;
    }
    gfx.sprite_clip_enabled = clip != 0;
    if (clip != 0) gfx.sprite_clip = *clip;
    ++gfx.clip_generation;
    gfx.dirty = true;
    return true;
}

const swan_gfx_clip_t *swan_gfx_sprite_clip(void) {
    return gfx.sprite_clip_enabled ? &gfx.sprite_clip : 0;
}

void swan_gfx_set_layer_enabled(uint8_t layer, bool enabled) {
    if (layer >= SWAN_GFX_LAYER_COUNT) {
        SWAN_ASSERT(false, SWAN_PANIC_BAD_ARGUMENT);
        return;
    }
    gfx.layer_enabled[layer] = enabled;
    gfx.dirty = true;
}

bool swan_gfx_layer_enabled(uint8_t layer) {
    return layer < SWAN_GFX_LAYER_COUNT && gfx.layer_enabled[layer];
}

bool swan_gfx_set_palette(uint8_t palette, const uint16_t colors[4]) {
    if (palette >= gfx.limits.palette_capacity || colors == 0) {
        SWAN_ASSERT(false, SWAN_PANIC_RESOURCE_LIMIT);
        return false;
    }
#if SWAN_GFX_DIRECT_HARDWARE
    swan_platform_gfx_set_palette(palette, colors);
#else
    memcpy(gfx.palettes[palette], colors, sizeof(gfx.palettes[palette]));
#endif
    gfx.palette_set |= (uint16_t)(1u << palette);
    ++gfx.palette_generation;
    gfx.dirty = true;
    return true;
}

bool swan_gfx_set_sprite(uint8_t sprite, const swan_sprite_t *value) {
    if (sprite >= gfx.limits.sprite_capacity || value == 0 ||
        value->tile >= SWAN_GFX_SPRITE_TILE_CAPACITY ||
        value->tile >= gfx.limits.tile_capacity || value->palette >= 8u ||
        (value->flags & (uint8_t)~SWAN_SPRITE_FLAG_MASK) != 0) {
        SWAN_ASSERT(false, SWAN_PANIC_RESOURCE_LIMIT);
        return false;
    }
#if SWAN_GFX_DIRECT_HARDWARE
    swan_platform_gfx_set_sprite(sprite, value);
    if (value->visible)
        gfx.sprite_visible[sprite >> 3] |= (uint8_t)(1u << (sprite & 7u));
    else
        gfx.sprite_visible[sprite >> 3] &= (uint8_t)~(1u << (sprite & 7u));
#else
    gfx.sprites[sprite] = *value;
#endif
    ++gfx.sprite_generation;
    gfx.dirty = true;
    return true;
}

void swan_gfx_hide_sprites(void) {
#if SWAN_GFX_DIRECT_HARDWARE
    memset(gfx.sprite_visible, 0, sizeof(gfx.sprite_visible));
    swan_platform_gfx_hide_sprites(gfx.limits.sprite_capacity);
#else
    uint8_t sprite;
    for (sprite = 0; sprite < gfx.limits.sprite_capacity; ++sprite) {
        gfx.sprites[sprite].visible = false;
    }
#endif
    ++gfx.sprite_generation;
    gfx.dirty = true;
}

void swan_gfx_set_sprites_enabled(bool enabled) {
    gfx.sprites_enabled = enabled;
    gfx.dirty = true;
}

bool swan_gfx_sprites_enabled(void) { return gfx.sprites_enabled; }

static void measure_usage(void) {
    uint8_t layer;
    uint8_t y;
    uint8_t x;
    uint8_t sprite;
    uint8_t scanline;
    uint16_t highest = 0;
    uint8_t palettes = 0;
    uint8_t visible = 0;
    uint8_t maximum = 0;

    for (layer = 0; layer < SWAN_GFX_LAYER_COUNT; ++layer) {
        for (y = 0; y < SWAN_GFX_MAP_HEIGHT; ++y) {
            for (x = 0; x < SWAN_GFX_MAP_WIDTH; ++x) {
                uint16_t tile = swan_gfx_tile_index(swan_gfx_get_tile(layer, x, y));
                if (tile > highest) highest = tile;
            }
        }
    }
    for (sprite = 0; sprite < gfx.limits.sprite_capacity; ++sprite) {
        swan_sprite_t value;
#if SWAN_GFX_DIRECT_HARDWARE
        swan_platform_gfx_get_sprite(sprite, &value);
        value.visible = (gfx.sprite_visible[sprite >> 3] &
            (uint8_t)(1u << (sprite & 7u))) != 0;
#else
        value = gfx.sprites[sprite];
#endif
        if (value.visible) {
            uint16_t tile = value.tile;
            ++visible;
            if (tile > highest) highest = tile;
        }
    }
    for (x = 0; x < gfx.limits.palette_capacity; ++x) {
        if ((gfx.palette_set & (uint16_t)(1u << x)) != 0) palettes = (uint8_t)(x + 1u);
    }
    for (scanline = 0; scanline < 144u; ++scanline) {
        uint8_t count = 0;
        for (sprite = 0; sprite < gfx.limits.sprite_capacity; ++sprite) {
            swan_sprite_t value;
#if SWAN_GFX_DIRECT_HARDWARE
            swan_platform_gfx_get_sprite(sprite, &value);
            value.visible = (gfx.sprite_visible[sprite >> 3] &
                (uint8_t)(1u << (sprite & 7u))) != 0;
#else
            value = gfx.sprites[sprite];
#endif
            if (value.visible && scanline >= value.y && scanline < value.y + 8)
                ++count;
        }
        if (count > maximum) maximum = count;
    }
    gfx.usage.highest_tile = highest;
    gfx.usage.palettes_used = palettes;
    gfx.usage.sprites_visible = visible;
    gfx.usage.maximum_sprites_on_scanline = maximum;
    gfx.usage.scanline_overflow = maximum > SWAN_GFX_SPRITES_PER_SCANLINE;
}

void swan_gfx_present(void) {
    measure_usage();
    gfx.dirty = false;
}

bool swan_gfx_dirty(void) {
    return gfx.dirty;
}

const swan_gfx_usage_t *swan_gfx_usage(void) {
    measure_usage();
    return &gfx.usage;
}

const swan_tile_attr_t *swan_gfx_internal_map(uint8_t layer) {
#if SWAN_GFX_DIRECT_HARDWARE
    (void)layer;
    return 0;
#else
    return layer < SWAN_GFX_LAYER_COUNT ? &gfx.maps[layer][0][0] : 0;
#endif
}

const uint8_t *swan_gfx_internal_tile_staging(void) {
#if SWAN_GFX_DIRECT_HARDWARE
    return 0;
#else
    return &gfx.tile_staging[0][0];
#endif
}
const swan_gfx_tile_upload_t *swan_gfx_internal_tile_uploads(void) {
#if SWAN_GFX_DIRECT_HARDWARE
    return 0;
#else
    return gfx.tile_uploads;
#endif
}
uint8_t swan_gfx_internal_tile_upload_count(void) {
#if SWAN_GFX_DIRECT_HARDWARE
    return 0;
#else
    return gfx.tile_upload_count;
#endif
}
void swan_gfx_internal_tiles_committed(uint16_t generation) {
#if SWAN_GFX_DIRECT_HARDWARE
    (void)generation;
#else
    if (generation == gfx.tiles_generation) {
        gfx.tile_upload_count = 0;
        gfx.staged_tile_count = 0;
    }
#endif
}
const uint16_t *swan_gfx_internal_palette(uint8_t palette) {
#if SWAN_GFX_DIRECT_HARDWARE
    (void)palette;
    return 0;
#else
    return palette < gfx.limits.palette_capacity ? gfx.palettes[palette] : 0;
#endif
}
bool swan_gfx_internal_palette_set(uint8_t palette) {
    return palette < gfx.limits.palette_capacity &&
        (gfx.palette_set & (uint16_t)(1u << palette)) != 0;
}
const swan_sprite_t *swan_gfx_internal_sprites(void) {
#if SWAN_GFX_DIRECT_HARDWARE
    return 0;
#else
    return gfx.sprites;
#endif
}
uint8_t swan_gfx_internal_sprite_capacity(void) { return gfx.limits.sprite_capacity; }
int16_t swan_gfx_internal_scroll_x(uint8_t layer) {
    return layer < SWAN_GFX_LAYER_COUNT ? gfx.cameras[layer].x : 0;
}
int16_t swan_gfx_internal_scroll_y(uint8_t layer) {
    return layer < SWAN_GFX_LAYER_COUNT ? gfx.cameras[layer].y : 0;
}
uint16_t swan_gfx_internal_tiles_generation(void) { return gfx.tiles_generation; }
uint16_t swan_gfx_internal_map_generation(uint8_t layer) {
    return layer < SWAN_GFX_LAYER_COUNT ? gfx.map_generation[layer] : 0;
}
uint16_t swan_gfx_internal_palette_generation(void) { return gfx.palette_generation; }
uint16_t swan_gfx_internal_sprite_generation(void) { return gfx.sprite_generation; }
uint16_t swan_gfx_internal_scroll_generation(void) { return gfx.scroll_generation; }
uint16_t swan_gfx_internal_clip_generation(void) { return gfx.clip_generation; }
bool swan_gfx_internal_layer_enabled(uint8_t layer) {
    return layer < SWAN_GFX_LAYER_COUNT && gfx.layer_enabled[layer];
}
bool swan_gfx_internal_sprites_enabled(void) { return gfx.sprites_enabled; }
void swan_gfx_internal_set_hardware_tile_capacity(uint16_t tile_capacity) {
    hardware_tile_capacity = tile_capacity <= SWAN_GFX_SPRITE_TILE_CAPACITY ?
        SWAN_GFX_SPRITE_TILE_CAPACITY : SWAN_GFX_TILE_CAPACITY;
}
