#ifndef SWAN_WSWAN_H
#define SWAN_WSWAN_H

#include <stdint.h>
#include <stdbool.h>

#include <swan/rtc.h>
#include <swan/save.h>

typedef struct {
    uint16_t byte_count;
    uint8_t address_bits;
} swan_ws_eeprom_context_t;

typedef struct {
    uint32_t byte_count;
} swan_ws_sram_context_t;

typedef struct {
    bool cartridge_has_rtc;
    bool captured;
    swan_rtc_status_t capture_status;
    uint8_t captured_registers[7];
} swan_ws_rtc_context_t;

/* Convert Wonderful's hardware keypad bit layout to swan_key_t. */
uint16_t swan_ws_translate_keys(uint16_t wonderful_keys);

/*
 * Bind cartridge storage declared by wfconfig.toml to the portable journal
 * codec. Context objects and the returned backend must remain alive together.
 */
bool swan_ws_eeprom_storage(swan_ws_eeprom_context_t *context,
                            swan_storage_t *storage, uint16_t byte_count);
bool swan_ws_sram_storage(swan_ws_sram_context_t *context,
                          swan_storage_t *storage, uint32_t byte_count);

/*
 * Bind the cartridge RTC for swan_rtc_capture from swan_game_boot. Hardware
 * access outside that boot callback is rejected with SWAN_RTC_WRONG_PHASE.
 */
void swan_ws_rtc_backend(swan_ws_rtc_context_t *context,
                         swan_rtc_backend_t *backend, bool cartridge_has_rtc);

#endif
