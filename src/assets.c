#include <string.h>

#include <swan/assets.h>

static bool add_u32(uint32_t *value, uint32_t amount) {
    uint32_t old = *value;
    *value += amount;
    return *value >= old;
}

swan_assets_status_t swan_assets_validate(const swan_asset_catalog_t *catalog,
                                           swan_asset_usage_t *usage) {
    swan_asset_usage_t measured;
    uint16_t i;
    if (catalog == 0 || (catalog->count != 0 && catalog->assets == 0)) {
        return SWAN_ASSETS_BAD_CATALOG;
    }
    memset(&measured, 0, sizeof(measured));
    for (i = 0; i < catalog->count; ++i) {
        const swan_asset_t SWAN_FAR *asset = &catalog->assets[i];
        uint16_t j;
        if (asset->byte_count != 0 && asset->data == 0) {
            return SWAN_ASSETS_BAD_CATALOG;
        }
        for (j = 0; j < i; ++j) {
            if (catalog->assets[j].id == asset->id) {
                return SWAN_ASSETS_DUPLICATE_ID;
            }
        }
        if (!add_u32(&measured.total_bytes, asset->byte_count)) {
            return SWAN_ASSETS_BAD_CATALOG;
        }
        switch (asset->kind) {
            case SWAN_ASSET_TILES:
            case SWAN_ASSET_FONT:
                if ((uint32_t)measured.tiles + asset->item_count > UINT16_MAX)
                    return SWAN_ASSETS_TILE_LIMIT;
                measured.tiles = (uint16_t)(measured.tiles + asset->item_count);
                break;
            case SWAN_ASSET_PALETTE:
                if ((uint16_t)measured.palettes + asset->item_count > UINT8_MAX)
                    return SWAN_ASSETS_PALETTE_LIMIT;
                measured.palettes = (uint8_t)(measured.palettes + asset->item_count);
                break;
            case SWAN_ASSET_SPRITES:
                if ((uint16_t)measured.sprites + asset->item_count > UINT8_MAX)
                    return SWAN_ASSETS_SPRITE_LIMIT;
                measured.sprites = (uint8_t)(measured.sprites + asset->item_count);
                break;
            case SWAN_ASSET_MUSIC:
            case SWAN_ASSET_SFX:
                if (!add_u32(&measured.audio_bytes, asset->byte_count))
                    return SWAN_ASSETS_AUDIO_LIMIT;
                break;
            case SWAN_ASSET_TILEMAP:
                break;
            default:
                return SWAN_ASSETS_BAD_CATALOG;
        }
    }
    if (usage != 0) *usage = measured;
    if (measured.tiles > catalog->tile_budget) return SWAN_ASSETS_TILE_LIMIT;
    if (measured.palettes > catalog->palette_budget) return SWAN_ASSETS_PALETTE_LIMIT;
    if (measured.sprites > catalog->sprite_budget) return SWAN_ASSETS_SPRITE_LIMIT;
    if (measured.audio_bytes > catalog->audio_byte_budget) return SWAN_ASSETS_AUDIO_LIMIT;
    return SWAN_ASSETS_OK;
}

const swan_asset_t SWAN_FAR *swan_assets_find(const swan_asset_catalog_t *catalog,
                                              swan_asset_id_t id) {
    uint16_t i;
    if (catalog == 0 || catalog->assets == 0) return 0;
    for (i = 0; i < catalog->count; ++i) {
        if (catalog->assets[i].id == id) return &catalog->assets[i];
    }
    return 0;
}
