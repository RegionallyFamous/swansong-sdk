#ifndef SWAN_RECORDS_H
#define SWAN_RECORDS_H

#include <stdbool.h>
#include <stdint.h>

#define SWAN_RECORD_NO_RANK UINT8_MAX
#define SWAN_RECORDS_BINARY_VERSION 1u
#define SWAN_RECORDS_HEADER_SIZE 4u
#define SWAN_RECORDS_RECORD_SIZE 6u

typedef struct {
    uint32_t score;
    uint16_t tag;
} swan_record_t;

bool swan_records_valid(const swan_record_t *records, uint8_t count,
                        uint8_t capacity);
uint8_t swan_records_insert(swan_record_t *records, uint8_t *count,
                            uint8_t capacity, uint32_t score, uint16_t tag);

/*
 * Canonical bytes are "SR", version, count, then count records containing a
 * little-endian uint32 score and uint16 tag. Deserialization is all-or-nothing.
 */
uint16_t swan_records_serialized_size(uint8_t count);
uint16_t swan_records_serialize(const swan_record_t *records, uint8_t count,
                                uint8_t *output, uint16_t output_capacity);
bool swan_records_deserialize(const uint8_t *input, uint16_t input_length,
                              swan_record_t *records, uint8_t capacity,
                              uint8_t *count);

#endif
