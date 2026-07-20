#include <string.h>

#include <swan/pool.h>

static uint8_t slot_mask(uint8_t slot) {
    return (uint8_t)(1u << (slot & 7u));
}

bool swan_pool_init(swan_pool_t *pool, uint8_t capacity) {
    if (pool == 0 || capacity == 0 || capacity > SWAN_POOL_MAX_OBJECTS)
        return false;
    memset(pool, 0, sizeof(*pool));
    pool->capacity = capacity;
    return true;
}

bool swan_pool_is_active(const swan_pool_t *pool, uint8_t slot) {
    return pool != 0 && slot < pool->capacity &&
        (pool->used[slot >> 3] & slot_mask(slot)) != 0;
}

uint8_t swan_pool_acquire(swan_pool_t *pool) {
    uint8_t slot;
    if (pool == 0 || pool->count >= pool->capacity) return SWAN_POOL_NONE;
    for (slot = 0; slot < pool->capacity; ++slot) {
        if (!swan_pool_is_active(pool, slot)) {
            pool->used[slot >> 3] |= slot_mask(slot);
            ++pool->count;
            return slot;
        }
    }
    return SWAN_POOL_NONE;
}

bool swan_pool_release(swan_pool_t *pool, uint8_t slot) {
    if (!swan_pool_is_active(pool, slot)) return false;
    pool->used[slot >> 3] &= (uint8_t)~slot_mask(slot);
    --pool->count;
    return true;
}

bool swan_pool_next_active(const swan_pool_t *pool, uint8_t *cursor,
                           uint8_t *slot) {
    uint8_t index;
    if (pool == 0 || cursor == 0 || slot == 0) return false;
    for (index = *cursor; index < pool->capacity; ++index) {
        if (swan_pool_is_active(pool, index)) {
            *slot = index;
            *cursor = (uint8_t)(index + 1u);
            return true;
        }
    }
    *cursor = pool->capacity;
    return false;
}
