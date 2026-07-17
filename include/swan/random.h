#ifndef SWAN_RANDOM_H
#define SWAN_RANDOM_H

#include <stdint.h>

typedef struct {
    uint16_t state;
} swan_random_t;

void swan_random_seed(swan_random_t *random, uint16_t seed);
uint16_t swan_random_next(swan_random_t *random);
uint16_t swan_random_bounded(swan_random_t *random, uint16_t bound);
uint8_t swan_random_range_u8(swan_random_t *random, uint8_t low, uint8_t high);

#endif
