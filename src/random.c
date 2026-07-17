#include <swan/random.h>

void swan_random_seed(swan_random_t *random, uint16_t seed) {
    if (random != 0) {
        random->state = seed == 0 ? 0x71D3u : seed;
    }
}

uint16_t swan_random_next(swan_random_t *random) {
    uint16_t value;
    if (random == 0) return 0;
    value = random->state;
    if (value == 0) value = 0x71D3u;
    value ^= (uint16_t)(value << 7);
    value ^= (uint16_t)(value >> 9);
    value ^= (uint16_t)(value << 8);
    random->state = value;
    return value;
}

uint16_t swan_random_bounded(swan_random_t *random, uint16_t bound) {
    uint32_t product;
    if (bound == 0) return 0;
    product = (uint32_t)swan_random_next(random) * bound;
    return (uint16_t)(product >> 16);
}

uint8_t swan_random_range_u8(swan_random_t *random, uint8_t low, uint8_t high) {
    uint16_t width;
    if (high <= low) return low;
    width = (uint16_t)high - low + 1u;
    return (uint8_t)(low + swan_random_bounded(random, width));
}
