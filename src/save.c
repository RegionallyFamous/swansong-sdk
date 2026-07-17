#include <string.h>

#include <swan/save.h>
#include <swan/version.h>

#define SAVE_HEADER_SIZE 24u
#define SAVE_MAGIC 0x4E415753ul /* "SWAN" in little endian */
#define SAVE_COMMITTED 0xA55Au

typedef struct {
    uint16_t schema;
    uint16_t length;
    uint32_t generation;
    uint32_t payload_crc;
} decoded_header_t;

static uint16_t read16(const uint8_t *bytes) {
    return (uint16_t)(bytes[0] | ((uint16_t)bytes[1] << 8));
}

static uint32_t read32(const uint8_t *bytes) {
    return (uint32_t)bytes[0] | ((uint32_t)bytes[1] << 8) |
        ((uint32_t)bytes[2] << 16) | ((uint32_t)bytes[3] << 24);
}

static void write16(uint8_t *bytes, uint16_t value) {
    bytes[0] = (uint8_t)value;
    bytes[1] = (uint8_t)(value >> 8);
}

static void write32(uint8_t *bytes, uint32_t value) {
    bytes[0] = (uint8_t)value;
    bytes[1] = (uint8_t)(value >> 8);
    bytes[2] = (uint8_t)(value >> 16);
    bytes[3] = (uint8_t)(value >> 24);
}

static uint32_t crc_update(uint32_t crc, const uint8_t *bytes, uint16_t length) {
    uint16_t i;
    for (i = 0; i < length; ++i) {
        uint8_t bit;
        crc ^= bytes[i];
        for (bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ ((crc & 1u) ? 0xEDB88320ul : 0);
    }
    return crc;
}

uint32_t swan_crc32(const void *data, uint16_t length) {
    if (data == 0 && length != 0) return 0;
    return crc_update(0xFFFFFFFFul, (const uint8_t *)data, length) ^ 0xFFFFFFFFul;
}

uint16_t swan_save_capacity(const swan_storage_t *storage) {
    uint32_t slot_size;
    uint32_t capacity;
    if (storage == 0 || storage->byte_count < SAVE_HEADER_SIZE * 2u) return 0;
    slot_size = storage->byte_count / 2u;
    capacity = slot_size - SAVE_HEADER_SIZE;
    return capacity > UINT16_MAX ? UINT16_MAX : (uint16_t)capacity;
}

static bool storage_valid(const swan_storage_t *storage) {
    return storage != 0 && storage->read != 0 && storage->write != 0 &&
        storage->byte_count >= SAVE_HEADER_SIZE * 2u;
}

static bool header_empty(const uint8_t bytes[SAVE_HEADER_SIZE]) {
    uint8_t i;
    bool all_zero = true;
    bool all_ff = true;
    for (i = 0; i < SAVE_HEADER_SIZE; ++i) {
        if (bytes[i] != 0) all_zero = false;
        if (bytes[i] != 0xFFu) all_ff = false;
    }
    return all_zero || all_ff;
}

static bool decode_header(const uint8_t bytes[SAVE_HEADER_SIZE], uint16_t capacity,
                          decoded_header_t *header) {
    if (read32(bytes) != SAVE_MAGIC ||
        read16(bytes + 4) != SWAN_SAVE_FORMAT_VERSION ||
        read16(bytes + 10) != SAVE_COMMITTED ||
        read16(bytes + 8) > capacity ||
        swan_crc32(bytes, 20) != read32(bytes + 20)) return false;
    header->schema = read16(bytes + 6);
    header->length = read16(bytes + 8);
    header->generation = read32(bytes + 12);
    header->payload_crc = read32(bytes + 16);
    return true;
}

static bool payload_valid(const swan_storage_t *storage, uint8_t slot,
                          const decoded_header_t *header) {
    uint8_t chunk[32];
    uint16_t remaining = header->length;
    uint16_t position = 0;
    uint32_t crc = 0xFFFFFFFFul;
    uint32_t slot_size = storage->byte_count / 2u;
    while (remaining != 0) {
        uint16_t length = remaining > sizeof(chunk) ? sizeof(chunk) : remaining;
        if (!storage->read(storage->context,
                           (uint32_t)slot * slot_size + SAVE_HEADER_SIZE + position,
                           chunk, length)) return false;
        crc = crc_update(crc, chunk, length);
        position = (uint16_t)(position + length);
        remaining = (uint16_t)(remaining - length);
    }
    return (crc ^ 0xFFFFFFFFul) == header->payload_crc;
}

static swan_save_status_t inspect_slots(const swan_storage_t *storage,
                                        decoded_header_t headers[2],
                                        bool valid[2], bool *all_empty) {
    uint8_t bytes[SAVE_HEADER_SIZE];
    uint16_t capacity = swan_save_capacity(storage);
    uint8_t slot;
    *all_empty = true;
    for (slot = 0; slot < 2; ++slot) {
        uint32_t offset = (uint32_t)slot * (storage->byte_count / 2u);
        if (!storage->read(storage->context, offset, bytes, sizeof(bytes)))
            return SWAN_SAVE_IO_ERROR;
        if (!header_empty(bytes)) *all_empty = false;
        valid[slot] = decode_header(bytes, capacity, &headers[slot]) &&
            payload_valid(storage, slot, &headers[slot]);
    }
    return SWAN_SAVE_OK;
}

static int8_t newest_slot(const decoded_header_t headers[2], const bool valid[2]) {
    if (!valid[0]) return valid[1] ? 1 : -1;
    if (!valid[1]) return 0;
    return (int32_t)(headers[1].generation - headers[0].generation) > 0 ? 1 : 0;
}

static swan_save_status_t load_internal(const swan_storage_t *storage,
                                        bool check_schema, uint16_t expected_schema,
                                        void *destination, uint16_t capacity,
                                        swan_save_info_t *info) {
    decoded_header_t headers[2];
    bool valid[2];
    bool all_empty;
    int8_t slot;
    swan_save_status_t status;
    uint32_t offset;
    if (!storage_valid(storage) || (destination == 0 && capacity != 0))
        return SWAN_SAVE_BAD_ARGUMENT;
    status = inspect_slots(storage, headers, valid, &all_empty);
    if (status != SWAN_SAVE_OK) return status;
    slot = newest_slot(headers, valid);
    if (slot < 0) return all_empty ? SWAN_SAVE_EMPTY : SWAN_SAVE_CORRUPT;
    if (info != 0) {
        info->schema = headers[(uint8_t)slot].schema;
        info->length = headers[(uint8_t)slot].length;
        info->generation = headers[(uint8_t)slot].generation;
        info->slot = (uint8_t)slot;
    }
    if (check_schema && headers[(uint8_t)slot].schema != expected_schema)
        return SWAN_SAVE_SCHEMA_MISMATCH;
    if (headers[(uint8_t)slot].length > capacity) return SWAN_SAVE_CAPACITY;
    offset = (uint32_t)(uint8_t)slot * (storage->byte_count / 2u) + SAVE_HEADER_SIZE;
    if (headers[(uint8_t)slot].length != 0 &&
        !storage->read(storage->context, offset, destination,
                       headers[(uint8_t)slot].length)) return SWAN_SAVE_IO_ERROR;
    return SWAN_SAVE_OK;
}

swan_save_status_t swan_save_load(const swan_storage_t *storage,
                                  uint16_t expected_schema, void *destination,
                                  uint16_t capacity, swan_save_info_t *info) {
    return load_internal(storage, true, expected_schema, destination, capacity, info);
}

swan_save_status_t swan_save_load_any(const swan_storage_t *storage,
                                      void *destination, uint16_t capacity,
                                      swan_save_info_t *info) {
    return load_internal(storage, false, 0, destination, capacity, info);
}

swan_save_status_t swan_save_store(const swan_storage_t *storage,
                                   uint16_t schema, const void *source,
                                   uint16_t length, swan_save_info_t *info) {
    decoded_header_t headers[2];
    bool valid[2];
    bool all_empty;
    int8_t current;
    uint8_t target;
    uint8_t bytes[SAVE_HEADER_SIZE];
    uint32_t generation;
    uint32_t slot_size;
    uint32_t offset;
    swan_save_status_t status;
    if (!storage_valid(storage) || (source == 0 && length != 0))
        return SWAN_SAVE_BAD_ARGUMENT;
    if (length > swan_save_capacity(storage)) return SWAN_SAVE_CAPACITY;
    status = inspect_slots(storage, headers, valid, &all_empty);
    (void)all_empty;
    if (status != SWAN_SAVE_OK) return status;
    current = newest_slot(headers, valid);
    target = current < 0 ? 0 : (uint8_t)(1 - current);
    generation = current < 0 ? 1u : headers[(uint8_t)current].generation + 1u;
    slot_size = storage->byte_count / 2u;
    offset = (uint32_t)target * slot_size;

    memset(bytes, 0, sizeof(bytes));
    if (!storage->write(storage->context, offset, bytes, sizeof(bytes)))
        return SWAN_SAVE_IO_ERROR;
    if (storage->sync != 0 && !storage->sync(storage->context))
        return SWAN_SAVE_IO_ERROR;
    if (length != 0 && !storage->write(storage->context, offset + SAVE_HEADER_SIZE,
                                       source, length)) return SWAN_SAVE_IO_ERROR;
    if (storage->sync != 0 && !storage->sync(storage->context))
        return SWAN_SAVE_IO_ERROR;

    write32(bytes, SAVE_MAGIC);
    write16(bytes + 4, SWAN_SAVE_FORMAT_VERSION);
    write16(bytes + 6, schema);
    write16(bytes + 8, length);
    write16(bytes + 10, SAVE_COMMITTED);
    write32(bytes + 12, generation);
    write32(bytes + 16, swan_crc32(source, length));
    write32(bytes + 20, swan_crc32(bytes, 20));
    if (!storage->write(storage->context, offset, bytes, sizeof(bytes)))
        return SWAN_SAVE_IO_ERROR;
    if (storage->sync != 0 && !storage->sync(storage->context))
        return SWAN_SAVE_IO_ERROR;
    if (info != 0) {
        info->schema = schema;
        info->length = length;
        info->generation = generation;
        info->slot = target;
    }
    return SWAN_SAVE_OK;
}
