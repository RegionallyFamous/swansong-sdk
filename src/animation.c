#include <swan/animation.h>

bool swan_sprite_animation_init(swan_sprite_animation_t *animation,
                                uint16_t first_tile, uint8_t frame_count,
                                uint8_t ticks_per_frame, bool loop) {
    if (animation == 0 || frame_count == 0 || ticks_per_frame == 0)
        return false;
    animation->first_tile = first_tile;
    animation->frame_count = frame_count;
    animation->ticks_per_frame = ticks_per_frame;
    animation->loop = loop;
    swan_sprite_animation_reset(animation);
    return true;
}

void swan_sprite_animation_reset(swan_sprite_animation_t *animation) {
    if (animation == 0) return;
    animation->frame = 0;
    animation->tick = 0;
    animation->finished = false;
}

bool swan_sprite_animation_advance(swan_sprite_animation_t *animation,
                                   uint16_t ticks) {
    uint32_t elapsed;
    uint32_t transitions;
    uint16_t remaining;
    if (animation == 0 || animation->frame_count == 0 ||
        animation->ticks_per_frame == 0 || ticks == 0 || animation->finished)
        return false;
    elapsed = (uint32_t)animation->tick + ticks;
    transitions = elapsed / animation->ticks_per_frame;
    animation->tick = (uint8_t)(elapsed % animation->ticks_per_frame);
    if (transitions == 0) return false;
    if (animation->loop) {
        animation->frame = (uint8_t)((animation->frame + transitions) %
                                     animation->frame_count);
        return true;
    }
    remaining = (uint16_t)(animation->frame_count - animation->frame);
    if (transitions >= remaining) {
        animation->frame = (uint8_t)(animation->frame_count - 1u);
        animation->tick = 0;
        animation->finished = true;
    } else {
        animation->frame = (uint8_t)(animation->frame + transitions);
    }
    return true;
}

uint16_t swan_sprite_animation_tile(const swan_sprite_animation_t *animation) {
    return animation != 0 ? (uint16_t)(animation->first_tile + animation->frame) : 0;
}
