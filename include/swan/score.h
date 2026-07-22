#ifndef SWAN_SCORE_H
#define SWAN_SCORE_H

#include <stdbool.h>
#include <stdint.h>

typedef struct {
    uint16_t chain_timeout_frames;
    uint8_t hits_per_multiplier;
    uint8_t maximum_multiplier;
} swan_score_config_t;

typedef struct {
    uint32_t points;
    uint16_t chain;
    uint16_t best_chain;
    uint16_t chain_remaining;
    uint16_t chain_timeout_frames;
    uint8_t hits_per_multiplier;
    uint8_t maximum_multiplier;
    uint8_t multiplier;
} swan_score_t;

bool swan_score_init(swan_score_t *score,
                     const swan_score_config_t *config);
void swan_score_reset(swan_score_t *score);
bool swan_score_advance(swan_score_t *score, uint16_t frames);
uint32_t swan_score_award(swan_score_t *score, uint16_t base_points);
bool swan_score_break_chain(swan_score_t *score);

#endif
