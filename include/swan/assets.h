#ifndef SWAN_ASSETS_H
#define SWAN_ASSETS_H

#include <stdbool.h>
#include <stdint.h>
#include <swan/types.h>

typedef uint16_t swan_asset_id_t;

typedef enum {
    SWAN_ASSET_TILES,
    SWAN_ASSET_TILEMAP,
    SWAN_ASSET_SPRITES,
    SWAN_ASSET_PALETTE,
    SWAN_ASSET_FONT,
    SWAN_ASSET_MUSIC,
    SWAN_ASSET_SFX
} swan_asset_kind_t;

typedef struct {
    swan_asset_id_t id;
    swan_asset_kind_t kind;
    const void SWAN_FAR *data;
    uint32_t byte_count;
    uint16_t item_count;
    uint8_t group;
} swan_asset_t;

typedef struct {
    const swan_asset_t SWAN_FAR *assets;
    uint16_t count;
    uint16_t tile_budget;
    uint8_t palette_budget;
    uint8_t sprite_budget;
    uint32_t audio_byte_budget;
} swan_asset_catalog_t;

typedef struct {
    uint16_t tiles;
    uint8_t palettes;
    uint8_t sprites;
    uint32_t audio_bytes;
    uint32_t total_bytes;
} swan_asset_usage_t;

typedef enum {
    SWAN_ASSETS_OK = 0,
    SWAN_ASSETS_BAD_CATALOG,
    SWAN_ASSETS_DUPLICATE_ID,
    SWAN_ASSETS_TILE_LIMIT,
    SWAN_ASSETS_PALETTE_LIMIT,
    SWAN_ASSETS_SPRITE_LIMIT,
    SWAN_ASSETS_AUDIO_LIMIT
} swan_assets_status_t;

swan_assets_status_t swan_assets_validate(const swan_asset_catalog_t *catalog,
                                           swan_asset_usage_t *usage);
const swan_asset_t SWAN_FAR *swan_assets_find(const swan_asset_catalog_t *catalog,
                                              swan_asset_id_t id);

#endif
