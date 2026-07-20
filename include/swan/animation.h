#ifndef SWAN_ANIMATION_H
#define SWAN_ANIMATION_H

#include <stdbool.h>
#include <stdint.h>

typedef struct {
    uint16_t first_tile;
    uint8_t frame_count;
    uint8_t ticks_per_frame;
    uint8_t frame;
    uint8_t tick;
    bool loop;
    bool finished;
} swan_sprite_animation_t;

bool swan_sprite_animation_init(swan_sprite_animation_t *animation,
                                uint16_t first_tile, uint8_t frame_count,
                                uint8_t ticks_per_frame, bool loop);
void swan_sprite_animation_reset(swan_sprite_animation_t *animation);
bool swan_sprite_animation_advance(swan_sprite_animation_t *animation,
                                   uint16_t ticks);
uint16_t swan_sprite_animation_tile(const swan_sprite_animation_t *animation);

#endif
