#ifndef SWAN_INPUT_H
#define SWAN_INPUT_H

#include <stdbool.h>
#include <stdint.h>

typedef enum {
    SWAN_KEY_X1    = 1u << 0,
    SWAN_KEY_X2    = 1u << 1,
    SWAN_KEY_X3    = 1u << 2,
    SWAN_KEY_X4    = 1u << 3,
    SWAN_KEY_Y1    = 1u << 4,
    SWAN_KEY_Y2    = 1u << 5,
    SWAN_KEY_Y3    = 1u << 6,
    SWAN_KEY_Y4    = 1u << 7,
    SWAN_KEY_A     = 1u << 8,
    SWAN_KEY_B     = 1u << 9,
    SWAN_KEY_START = 1u << 10
} swan_key_t;

#define SWAN_KEY_ALL ((uint16_t)0x07FFu)
#define SWAN_ACTION_CAPACITY 16u
#define SWAN_INPUT_CHORD_CAPACITY 8u
#define SWAN_INPUT_DEFAULT_TAP_MAX_FRAMES 8u
#define SWAN_INPUT_DEFAULT_DOUBLE_TAP_WINDOW 12u
#define SWAN_INPUT_DEFAULT_HOLD_THRESHOLD 20u

typedef struct {
    uint16_t held;
    uint16_t pressed;
    uint16_t released;
    uint16_t repeated;
    uint16_t actions_held;
    uint16_t actions_pressed;
    uint16_t actions_released;
    uint16_t actions_repeated;
    uint16_t actions_tapped;
    uint16_t actions_double_tapped;
    uint16_t actions_hold_started;
    uint16_t actions_held_long;
    uint16_t actions_released_after_hold;
    uint16_t chords_pressed;
} swan_input_t;

typedef struct {
    uint16_t keys[SWAN_ACTION_CAPACITY];
    uint8_t repeat_delay;
    uint8_t repeat_period;
    uint16_t chord_actions[SWAN_INPUT_CHORD_CAPACITY];
    uint8_t tap_max_frames;
    uint8_t double_tap_window;
    uint8_t hold_threshold;
} swan_input_config_t;

void swan_input_init(const swan_input_config_t *config);
void swan_input_update(uint16_t raw_keys);
void swan_input_drain(void);
const swan_input_t *swan_input_get(void);
int8_t swan_input_dx(uint16_t keys);
int8_t swan_input_dy(uint16_t keys);
bool swan_action_held(uint8_t action);
bool swan_action_pressed(uint8_t action);
bool swan_action_released(uint8_t action);
bool swan_action_repeated(uint8_t action);
bool swan_action_tapped(uint8_t action);
bool swan_action_double_tapped(uint8_t action);
bool swan_action_hold_started(uint8_t action);
bool swan_action_held_long(uint8_t action);
bool swan_action_released_after_hold(uint8_t action);
bool swan_chord_pressed(uint8_t chord);

#endif
