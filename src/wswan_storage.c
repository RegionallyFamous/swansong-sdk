#include <string.h>

#include <swan/wswan.h>

static bool eeprom_size(uint16_t byte_count, uint8_t *address_bits) {
    if (address_bits == 0) return false;
    switch (byte_count) {
        case 128: *address_bits = 7; return true;
        case 1024: *address_bits = 10; return true;
        case 2048: *address_bits = 11; return true;
        default: return false;
    }
}

static bool sram_size(uint32_t byte_count) {
    return byte_count == 8192ul || byte_count == 32768ul ||
        byte_count == 131072ul || byte_count == 262144ul ||
        byte_count == 524288ul;
}

#if defined(__WONDERFUL_WSWAN__)

#include <wonderful.h>
#include <ws.h>

static bool range_valid(uint32_t byte_count, uint32_t offset, uint16_t length) {
    return offset <= byte_count && (uint32_t)length <= byte_count - offset;
}

static bool eeprom_read(void *opaque, uint32_t offset, void *destination,
                        uint16_t length) {
    swan_ws_eeprom_context_t *context = opaque;
    ws_eeprom_handle_t handle;
    if (context == 0 || destination == 0 ||
        !range_valid(context->byte_count, offset, length)) return false;
    handle = ws_eeprom_handle_cartridge(context->address_bits);
    ws_eeprom_read_data(handle, (uint16_t)offset, destination, length);
    return true;
}

static bool eeprom_write(void *opaque, uint32_t offset, const void *source,
                         uint16_t length) {
    swan_ws_eeprom_context_t *context = opaque;
    ws_eeprom_handle_t handle;
    const uint8_t *bytes = source;
    uint32_t end;
    uint16_t word_address;
    bool result = true;
    if (context == 0 || (source == 0 && length != 0) ||
        !range_valid(context->byte_count, offset, length)) return false;
    if (length == 0) return true;
    handle = ws_eeprom_handle_cartridge(context->address_bits);
    if (!ws_eeprom_write_unlock(handle)) return false;
    end = offset + length;
    word_address = (uint16_t)(offset & ~1ul);
    while ((uint32_t)word_address < end) {
        uint16_t value = ws_eeprom_read_word(handle, word_address);
        uint32_t first = word_address;
        uint32_t second = first + 1u;
        if (first >= offset && first < end)
            value = (uint16_t)((value & 0xFF00u) | bytes[first - offset]);
        if (second >= offset && second < end)
            value = (uint16_t)((value & 0x00FFu) |
                               ((uint16_t)bytes[second - offset] << 8));
        if (!ws_eeprom_write_word(handle, word_address, value)) {
            result = false;
            break;
        }
        word_address = (uint16_t)(word_address + 2u);
    }
    if (!ws_eeprom_write_lock(handle)) result = false;
    return result;
}

static bool eeprom_sync(void *opaque) { (void)opaque; return true; }

static bool sram_read(void *opaque, uint32_t offset, void *destination,
                      uint16_t length) {
    swan_ws_sram_context_t *context = opaque;
    uint8_t *output = destination;
    uint16_t remaining = length;
    if (context == 0 || destination == 0 ||
        !range_valid(context->byte_count, offset, length))
        return false;
    while (remaining != 0) {
        uint16_t within = (uint16_t)offset;
        uint32_t available = 65536ul - within;
        uint16_t chunk = available < remaining ? (uint16_t)available : remaining;
        ws_bank_t previous = ws_bank_ram_save((ws_bank_t)(offset >> 16));
        uint16_t index;
        for (index = 0; index < chunk; ++index)
            output[index] = WS_SRAM_MEM[(uint16_t)(within + index)];
        ws_bank_ram_restore(previous);
        output += chunk;
        offset += chunk;
        remaining = (uint16_t)(remaining - chunk);
    }
    return true;
}

static bool sram_write(void *opaque, uint32_t offset, const void *source,
                       uint16_t length) {
    swan_ws_sram_context_t *context = opaque;
    const uint8_t *input = source;
    uint16_t remaining = length;
    if (context == 0 || (source == 0 && length != 0) ||
        !range_valid(context->byte_count, offset, length)) return false;
    while (remaining != 0) {
        uint16_t within = (uint16_t)offset;
        uint32_t available = 65536ul - within;
        uint16_t chunk = available < remaining ? (uint16_t)available : remaining;
        ws_bank_t previous = ws_bank_ram_save((ws_bank_t)(offset >> 16));
        uint16_t index;
        for (index = 0; index < chunk; ++index)
            WS_SRAM_MEM[(uint16_t)(within + index)] = input[index];
        ws_bank_ram_restore(previous);
        input += chunk;
        offset += chunk;
        remaining = (uint16_t)(remaining - chunk);
    }
    return true;
}

static bool sram_sync(void *opaque) {
    (void)opaque;
    __asm volatile("" ::: "memory");
    return true;
}

#else

static bool unavailable_read(void *context, uint32_t offset, void *destination,
                             uint16_t length) {
    (void)context; (void)offset; (void)destination; (void)length;
    return false;
}
static bool unavailable_write(void *context, uint32_t offset, const void *source,
                              uint16_t length) {
    (void)context; (void)offset; (void)source; (void)length;
    return false;
}
static bool unavailable_sync(void *context) { (void)context; return false; }

#define eeprom_read unavailable_read
#define eeprom_write unavailable_write
#define eeprom_sync unavailable_sync
#define sram_read unavailable_read
#define sram_write unavailable_write
#define sram_sync unavailable_sync

#endif

bool swan_ws_eeprom_storage(swan_ws_eeprom_context_t *context,
                            swan_storage_t *storage, uint16_t byte_count) {
    uint8_t address_bits;
    if (context == 0 || storage == 0 || !eeprom_size(byte_count, &address_bits))
        return false;
    context->byte_count = byte_count;
    context->address_bits = address_bits;
    storage->context = context;
    storage->byte_count = byte_count;
    storage->read = eeprom_read;
    storage->write = eeprom_write;
    storage->sync = eeprom_sync;
    return true;
}

bool swan_ws_sram_storage(swan_ws_sram_context_t *context,
                          swan_storage_t *storage, uint32_t byte_count) {
    if (context == 0 || storage == 0 || !sram_size(byte_count)) return false;
    context->byte_count = byte_count;
    storage->context = context;
    storage->byte_count = byte_count;
    storage->read = sram_read;
    storage->write = sram_write;
    storage->sync = sram_sync;
    return true;
}
