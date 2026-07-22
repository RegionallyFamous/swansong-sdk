#include <limits.h>

#include <swan/score.h>

bool swan_score_init(swan_score_t *score,
                     const swan_score_config_t *config) {
    if (score == 0 || config == 0 || config->hits_per_multiplier == 0 ||
        config->maximum_multiplier == 0) return false;
    score->chain_timeout_frames = config->chain_timeout_frames;
    score->hits_per_multiplier = config->hits_per_multiplier;
    score->maximum_multiplier = config->maximum_multiplier;
    swan_score_reset(score);
    return true;
}

void swan_score_reset(swan_score_t *score) {
    if (score == 0) return;
    score->points = 0;
    score->chain = 0;
    score->best_chain = 0;
    score->chain_remaining = 0;
    score->multiplier = 1;
}

bool swan_score_advance(swan_score_t *score, uint16_t frames) {
    if (score == 0 || score->chain == 0 ||
        score->chain_timeout_frames == 0 || frames == 0) return false;
    if (frames < score->chain_remaining) {
        score->chain_remaining = (uint16_t)(score->chain_remaining - frames);
        return false;
    }
    return swan_score_break_chain(score);
}

uint32_t swan_score_award(swan_score_t *score, uint16_t base_points) {
    uint32_t requested;
    uint32_t awarded;
    uint16_t ladder;
    if (score == 0 || score->hits_per_multiplier == 0 ||
        score->maximum_multiplier == 0) return 0;
    if (score->chain != UINT16_MAX) ++score->chain;
    if (score->chain > score->best_chain) score->best_chain = score->chain;
    ladder = (uint16_t)((score->chain - 1u) / score->hits_per_multiplier);
    if (ladder >= score->maximum_multiplier)
        score->multiplier = score->maximum_multiplier;
    else
        score->multiplier = (uint8_t)(ladder + 1u);
    score->chain_remaining = score->chain_timeout_frames;
    requested = (uint32_t)base_points * score->multiplier;
    awarded = requested > UINT32_MAX - score->points ?
        UINT32_MAX - score->points : requested;
    score->points += awarded;
    return awarded;
}

bool swan_score_break_chain(swan_score_t *score) {
    bool changed;
    if (score == 0) return false;
    changed = score->chain != 0;
    score->chain = 0;
    score->chain_remaining = 0;
    score->multiplier = 1;
    return changed;
}
