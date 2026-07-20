#include <swan/debug.h>
#include <swan/state.h>

#define SWAN_FNV1A_OFFSET 2166136261u
#define SWAN_FNV1A_PRIME 16777619u

void swan_state_hash_begin(swan_state_hash_t *hash) {
    SWAN_ASSERT(hash != 0, SWAN_PANIC_BAD_ARGUMENT);
    if (hash == 0) return;
    hash->value = SWAN_FNV1A_OFFSET;
    hash->bytes = 0;
}

void swan_state_hash_bytes(swan_state_hash_t *hash, const uint8_t *bytes,
                           uint16_t length) {
    uint16_t index;
    SWAN_ASSERT(hash != 0, SWAN_PANIC_BAD_ARGUMENT);
    SWAN_ASSERT(bytes != 0 || length == 0, SWAN_PANIC_BAD_ARGUMENT);
    if (hash == 0 || (bytes == 0 && length != 0)) return;
    for (index = 0; index < length; ++index) {
        hash->value ^= bytes[index];
        hash->value *= SWAN_FNV1A_PRIME;
    }
    if ((uint16_t)(UINT16_MAX - hash->bytes) < length)
        hash->bytes = UINT16_MAX;
    else
        hash->bytes = (uint16_t)(hash->bytes + length);
}

void swan_state_hash_u8(swan_state_hash_t *hash, uint8_t value) {
    swan_state_hash_bytes(hash, &value, 1);
}

void swan_state_hash_i8(swan_state_hash_t *hash, int8_t value) {
    swan_state_hash_u8(hash, (uint8_t)value);
}

void swan_state_hash_u16(swan_state_hash_t *hash, uint16_t value) {
    uint8_t encoded[2] = {(uint8_t)value, (uint8_t)(value >> 8)};
    swan_state_hash_bytes(hash, encoded, 2);
}

void swan_state_hash_u32(swan_state_hash_t *hash, uint32_t value) {
    uint8_t encoded[4] = {
        (uint8_t)value, (uint8_t)(value >> 8),
        (uint8_t)(value >> 16), (uint8_t)(value >> 24)
    };
    swan_state_hash_bytes(hash, encoded, 4);
}

void swan_state_hash_bool(swan_state_hash_t *hash, bool value) {
    swan_state_hash_u8(hash, value ? 1u : 0u);
}

uint32_t swan_state_hash_finish(const swan_state_hash_t *hash) {
    SWAN_ASSERT(hash != 0, SWAN_PANIC_BAD_ARGUMENT);
    return hash != 0 ? hash->value : 0;
}
