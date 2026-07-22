#include <swan/records.h>

#define SWAN_RECORDS_MAGIC_0 ((uint8_t)'S')
#define SWAN_RECORDS_MAGIC_1 ((uint8_t)'R')

static uint32_t read_u32(const uint8_t *input) {
    return (uint32_t)input[0] | ((uint32_t)input[1] << 8) |
        ((uint32_t)input[2] << 16) | ((uint32_t)input[3] << 24);
}

static uint16_t read_u16(const uint8_t *input) {
    return (uint16_t)(input[0] | ((uint16_t)input[1] << 8));
}

static void write_u32(uint8_t *output, uint32_t value) {
    output[0] = (uint8_t)value;
    output[1] = (uint8_t)(value >> 8);
    output[2] = (uint8_t)(value >> 16);
    output[3] = (uint8_t)(value >> 24);
}

static void write_u16(uint8_t *output, uint16_t value) {
    output[0] = (uint8_t)value;
    output[1] = (uint8_t)(value >> 8);
}

bool swan_records_valid(const swan_record_t *records, uint8_t count,
                        uint8_t capacity) {
    uint8_t index;
    if (count > capacity || (count != 0 && records == 0)) return false;
    for (index = 1; index < count; ++index) {
        if (records[index - 1u].score < records[index].score) return false;
    }
    return true;
}

uint8_t swan_records_insert(swan_record_t *records, uint8_t *count,
                            uint8_t capacity, uint32_t score, uint16_t tag) {
    uint8_t index;
    uint8_t position;
    uint8_t last;
    if (records == 0 || count == 0 || capacity == 0 || *count > capacity ||
        !swan_records_valid(records, *count, capacity))
        return SWAN_RECORD_NO_RANK;
    position = 0;
    while (position < *count && records[position].score >= score) ++position;
    if (position == capacity) return SWAN_RECORD_NO_RANK;
    last = *count < capacity ? *count : (uint8_t)(capacity - 1u);
    for (index = last; index > position; --index)
        records[index] = records[index - 1u];
    records[position].score = score;
    records[position].tag = tag;
    if (*count < capacity) ++*count;
    return position;
}

uint16_t swan_records_serialized_size(uint8_t count) {
    return (uint16_t)(SWAN_RECORDS_HEADER_SIZE +
                      (uint16_t)count * SWAN_RECORDS_RECORD_SIZE);
}

uint16_t swan_records_serialize(const swan_record_t *records, uint8_t count,
                                uint8_t *output, uint16_t output_capacity) {
    uint16_t required = swan_records_serialized_size(count);
    uint16_t offset = SWAN_RECORDS_HEADER_SIZE;
    uint8_t index;
    if (output == 0 || output_capacity < required ||
        !swan_records_valid(records, count, count)) return 0;
    output[0] = SWAN_RECORDS_MAGIC_0;
    output[1] = SWAN_RECORDS_MAGIC_1;
    output[2] = SWAN_RECORDS_BINARY_VERSION;
    output[3] = count;
    for (index = 0; index < count; ++index) {
        write_u32(output + offset, records[index].score);
        write_u16(output + offset + 4u, records[index].tag);
        offset = (uint16_t)(offset + SWAN_RECORDS_RECORD_SIZE);
    }
    return required;
}

bool swan_records_deserialize(const uint8_t *input, uint16_t input_length,
                              swan_record_t *records, uint8_t capacity,
                              uint8_t *count) {
    uint32_t previous = UINT32_MAX;
    uint16_t offset = SWAN_RECORDS_HEADER_SIZE;
    uint8_t encoded_count;
    uint8_t index;
    if (input == 0 || count == 0 || input_length < SWAN_RECORDS_HEADER_SIZE ||
        input[0] != SWAN_RECORDS_MAGIC_0 || input[1] != SWAN_RECORDS_MAGIC_1 ||
        input[2] != SWAN_RECORDS_BINARY_VERSION) return false;
    encoded_count = input[3];
    if (encoded_count > capacity || (encoded_count != 0 && records == 0) ||
        input_length != swan_records_serialized_size(encoded_count)) return false;
    for (index = 0; index < encoded_count; ++index) {
        uint32_t score = read_u32(input + offset);
        if (score > previous) return false;
        previous = score;
        offset = (uint16_t)(offset + SWAN_RECORDS_RECORD_SIZE);
    }
    offset = SWAN_RECORDS_HEADER_SIZE;
    for (index = 0; index < encoded_count; ++index) {
        records[index].score = read_u32(input + offset);
        records[index].tag = read_u16(input + offset + 4u);
        offset = (uint16_t)(offset + SWAN_RECORDS_RECORD_SIZE);
    }
    *count = encoded_count;
    return true;
}
