#include <string.h>

#include <swan/input.h>

#define PHYSICAL_KEY_COUNT 11u

static swan_input_t input_state;
static swan_input_config_t input_config;
static uint8_t held_frames[PHYSICAL_KEY_COUNT];
static uint16_t drained_keys;

static uint16_t action_bits(uint16_t keys) {
    uint16_t actions = 0;
    uint8_t action;
    for (action = 0; action < SWAN_ACTION_CAPACITY; ++action) {
        if ((keys & input_config.keys[action]) != 0) {
            actions |= (uint16_t)(1u << action);
        }
    }
    return actions;
}

void swan_input_init(const swan_input_config_t *config) {
    memset(&input_state, 0, sizeof(input_state));
    memset(held_frames, 0, sizeof(held_frames));
    drained_keys = 0;
    memset(&input_config, 0, sizeof(input_config));
    if (config != 0) {
        input_config = *config;
    } else {
        input_config.repeat_delay = 20;
        input_config.repeat_period = 5;
    }
}

void swan_input_update(uint16_t raw_keys) {
    uint16_t previous = input_state.held;
    uint16_t repeated = 0;
    uint8_t key;

    raw_keys &= SWAN_KEY_ALL;
    drained_keys &= raw_keys;
    input_state.held = raw_keys & (uint16_t)~drained_keys;
    input_state.pressed = input_state.held & (uint16_t)~previous;
    input_state.released = previous & (uint16_t)~input_state.held;

    for (key = 0; key < PHYSICAL_KEY_COUNT; ++key) {
        uint16_t bit = (uint16_t)(1u << key);
        if ((input_state.held & bit) == 0) {
            held_frames[key] = 0;
        } else if ((input_state.pressed & bit) != 0) {
            held_frames[key] = 0;
            repeated |= bit;
        } else {
            if (held_frames[key] != UINT8_MAX) {
                ++held_frames[key];
            }
            if (input_config.repeat_period != 0 &&
                held_frames[key] >= input_config.repeat_delay &&
                (uint8_t)(held_frames[key] - input_config.repeat_delay) %
                    input_config.repeat_period == 0) {
                repeated |= bit;
            }
        }
    }

    input_state.repeated = repeated;
    input_state.actions_held = action_bits(input_state.held);
    input_state.actions_pressed = action_bits(input_state.pressed);
    input_state.actions_released = action_bits(input_state.released);
    input_state.actions_repeated = action_bits(input_state.repeated);
}

void swan_input_drain(void) {
    drained_keys |= input_state.held;
    input_state.held = 0;
    input_state.pressed = 0;
    input_state.released = 0;
    input_state.repeated = 0;
    input_state.actions_pressed = 0;
    input_state.actions_held = 0;
    input_state.actions_released = 0;
    input_state.actions_repeated = 0;
}

const swan_input_t *swan_input_get(void) {
    return &input_state;
}

int8_t swan_input_dx(uint16_t keys) {
    int8_t value = 0;
    if ((keys & (SWAN_KEY_X4 | SWAN_KEY_Y1)) != 0) --value;
    if ((keys & (SWAN_KEY_X2 | SWAN_KEY_Y3)) != 0) ++value;
    return value;
}

int8_t swan_input_dy(uint16_t keys) {
    int8_t value = 0;
    if ((keys & (SWAN_KEY_X3 | SWAN_KEY_Y2)) != 0) --value;
    if ((keys & (SWAN_KEY_X1 | SWAN_KEY_Y4)) != 0) ++value;
    return value;
}

bool swan_action_held(uint8_t action) {
    return action < SWAN_ACTION_CAPACITY &&
        (input_state.actions_held & (uint16_t)(1u << action)) != 0;
}

bool swan_action_pressed(uint8_t action) {
    return action < SWAN_ACTION_CAPACITY &&
        (input_state.actions_pressed & (uint16_t)(1u << action)) != 0;
}

bool swan_action_released(uint8_t action) {
    return action < SWAN_ACTION_CAPACITY &&
        (input_state.actions_released & (uint16_t)(1u << action)) != 0;
}

bool swan_action_repeated(uint8_t action) {
    return action < SWAN_ACTION_CAPACITY &&
        (input_state.actions_repeated & (uint16_t)(1u << action)) != 0;
}
