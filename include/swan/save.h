#ifndef SWAN_SAVE_H
#define SWAN_SAVE_H

#include <stdbool.h>
#include <stdint.h>

typedef bool (*swan_storage_read_fn)(void *context, uint32_t offset,
                                     void *destination, uint16_t length);
typedef bool (*swan_storage_write_fn)(void *context, uint32_t offset,
                                      const void *source, uint16_t length);
typedef bool (*swan_storage_sync_fn)(void *context);

typedef struct {
    void *context;
    uint32_t byte_count;
    swan_storage_read_fn read;
    swan_storage_write_fn write;
    swan_storage_sync_fn sync;
} swan_storage_t;

typedef enum {
    SWAN_SAVE_OK = 0,
    SWAN_SAVE_EMPTY,
    SWAN_SAVE_CORRUPT,
    SWAN_SAVE_SCHEMA_MISMATCH,
    SWAN_SAVE_CAPACITY,
    SWAN_SAVE_IO_ERROR,
    SWAN_SAVE_BAD_ARGUMENT
} swan_save_status_t;

typedef struct {
    uint16_t schema;
    uint16_t length;
    uint32_t generation;
    uint8_t slot;
} swan_save_info_t;

uint32_t swan_crc32(const void *data, uint16_t length);
uint16_t swan_save_capacity(const swan_storage_t *storage);
swan_save_status_t swan_save_load(const swan_storage_t *storage,
                                  uint16_t expected_schema, void *destination,
                                  uint16_t capacity, swan_save_info_t *info);
swan_save_status_t swan_save_load_any(const swan_storage_t *storage,
                                      void *destination, uint16_t capacity,
                                      swan_save_info_t *info);
swan_save_status_t swan_save_store(const swan_storage_t *storage,
                                   uint16_t schema, const void *source,
                                   uint16_t length, swan_save_info_t *info);

#endif
