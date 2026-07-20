#ifndef SWAN_POOL_H
#define SWAN_POOL_H

#include <stdbool.h>
#include <stdint.h>

#define SWAN_POOL_MAX_OBJECTS 128u
#define SWAN_POOL_USED_BYTES (SWAN_POOL_MAX_OBJECTS / 8u)
#define SWAN_POOL_NONE UINT8_MAX

typedef struct {
    uint8_t used[SWAN_POOL_USED_BYTES];
    uint8_t capacity;
    uint8_t count;
} swan_pool_t;

bool swan_pool_init(swan_pool_t *pool, uint8_t capacity);
uint8_t swan_pool_acquire(swan_pool_t *pool);
bool swan_pool_release(swan_pool_t *pool, uint8_t slot);
bool swan_pool_is_active(const swan_pool_t *pool, uint8_t slot);
bool swan_pool_next_active(const swan_pool_t *pool, uint8_t *cursor,
                           uint8_t *slot);

#endif
