#ifndef SWAN_STATE_H
#define SWAN_STATE_H

#include <stdbool.h>
#include <stdint.h>

/* Canonical little-endian state hashing for deterministic outcome contracts. */
typedef struct {
    uint32_t value;
    uint16_t bytes;
} swan_state_hash_t;

void swan_state_hash_begin(swan_state_hash_t *hash);
void swan_state_hash_bytes(swan_state_hash_t *hash, const uint8_t *bytes,
                           uint16_t length);
void swan_state_hash_u8(swan_state_hash_t *hash, uint8_t value);
void swan_state_hash_i8(swan_state_hash_t *hash, int8_t value);
void swan_state_hash_u16(swan_state_hash_t *hash, uint16_t value);
void swan_state_hash_u32(swan_state_hash_t *hash, uint32_t value);
void swan_state_hash_bool(swan_state_hash_t *hash, bool value);
uint32_t swan_state_hash_finish(const swan_state_hash_t *hash);

#endif
