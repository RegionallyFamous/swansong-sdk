#include <swan/swan.h>

static const uint8_t SWAN_FAR smoke_tiles[32] = {
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
    0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF
};

static const uint8_t SWAN_FAR smoke_bank_tile[16] = {
    0xAA, 0xAA, 0x55, 0x55, 0xAA, 0xAA, 0x55, 0x55,
    0xAA, 0xAA, 0x55, 0x55, 0xAA, 0xAA, 0x55, 0x55
};

static uint16_t visible_tile;
#if defined(SWAN_SMOKE_SRAM)
static swan_ws_sram_context_t sram_context;
#else
static swan_ws_eeprom_context_t eeprom_context;
#endif
static swan_storage_t cartridge_storage;
static swan_ws_rtc_context_t rtc_context;
static swan_rtc_backend_t cartridge_rtc;

const swan_core_config_t swan_game_config = {
    .initial_scene = 0,
    .initial_argument = 0,
    .capabilities = SWAN_HARDWARE_COLOR | SWAN_HARDWARE_RTC,
    .vertical = false,
    .input = {
        .keys = { [4] = SWAN_KEY_A, [5] = SWAN_KEY_B },
        .repeat_delay = 20,
        .repeat_period = 5
    }
};

void swan_game_boot(void) {
    uint16_t palette[4] = {
        0x0FFF, 0x0000, 0x00AF, 0x0A4F
    };
    swan_gfx_config_t graphics = { 1024, 2, 4 };
    swan_datetime_t datetime;
    swan_save_info_t save_info;
    uint8_t payload = 0;
    const uint8_t marker = 0x5Au;
    swan_save_status_t save_status;
    bool storage_ok;
    bool rtc_ok;
    uint8_t storage_stage = 0;
    swan_gfx_init(&graphics);
#if defined(SWAN_SMOKE_SRAM)
    storage_ok = swan_ws_sram_storage(&sram_context, &cartridge_storage, 8192);
#else
    storage_ok = swan_ws_eeprom_storage(&eeprom_context, &cartridge_storage, 1024);
#endif
    if (storage_ok) {
        storage_stage = 1;
        save_status = swan_save_load(&cartridge_storage, 1, &payload,
                                     sizeof(payload), &save_info);
        if (save_status == SWAN_SAVE_EMPTY) {
            storage_stage = 2;
            save_status = swan_save_store(&cartridge_storage, 1, &marker,
                                          sizeof(marker), &save_info);
            if (save_status == SWAN_SAVE_OK) {
                storage_stage = 3;
                save_status = swan_save_load(&cartridge_storage, 1, &payload,
                                             sizeof(payload), &save_info);
            }
        }
        storage_ok = save_status == SWAN_SAVE_OK && payload == marker;
        if (storage_ok) storage_stage = 4;
    }
    swan_ws_rtc_backend(&rtc_context, &cartridge_rtc,
        (swan_core_capabilities() & SWAN_HARDWARE_RTC) != 0);
    rtc_ok = swan_rtc_capture(&cartridge_rtc, &datetime) == SWAN_RTC_OK;
    visible_tile = 1;
    if (!storage_ok && !rtc_ok) palette[3] = 0x0000;
    else if (!storage_ok) {
        static const uint16_t stage_colors[4] = {
            0x0000, 0x0F00, 0x0F80, 0x0FF0
        };
        palette[3] = stage_colors[storage_stage];
    }
    else if (!rtc_ok) palette[3] = 0x000F;
    else palette[3] = 0x00F0;
    swan_gfx_load_tiles(0, smoke_tiles, 2);
    swan_gfx_load_tiles(512, smoke_bank_tile, 1);
    swan_gfx_set_palette(0, palette);
    swan_audio_init(0, 0);
}

void swan_scene_enter(swan_scene_id_t scene, uint16_t argument) {
    (void)scene;
    (void)argument;
    swan_core_invalidate();
}

void swan_scene_update(swan_scene_id_t scene, const struct swan_frame *frame) {
    if (scene == 0 && (frame->input->actions_pressed & (1u << 5)) != 0) {
        swan_core_request_scene(1, 0);
    } else if ((frame->input->actions_pressed & (1u << 4)) != 0) {
        visible_tile = visible_tile == 1 ? 512 : 1;
        swan_core_invalidate();
    }
}

void swan_scene_render(swan_scene_id_t scene) {
    (void)scene;
    swan_gfx_fill(0, 0, 0, 28, 18, SWAN_TILE_ATTR(visible_tile, 0));
}

void swan_scene_exit(swan_scene_id_t scene) { (void)scene; }
