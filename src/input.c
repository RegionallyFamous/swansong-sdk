#include <string.h>

#include <swan/input.h>

#define PHYSICAL_KEY_COUNT 11u

static swan_input_t input_state;
static swan_input_config_t input_config;
static uint8_t held_frames[PHYSICAL_KEY_COUNT];
static uint8_t action_held_frames[SWAN_ACTION_CAPACITY];
static uint8_t double_tap_remaining[SWAN_ACTION_CAPACITY];
static uint16_t action_long_held;
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

static bool chord_is_valid(uint16_t actions) {
    return actions != 0 && (actions & (uint16_t)(actions - 1u)) != 0;
}

static void update_gestures(uint16_t previous_actions, uint16_t current_actions) {
    uint16_t semantic_pressed = current_actions & (uint16_t)~previous_actions;
    uint16_t semantic_released = previous_actions & (uint16_t)~current_actions;
    uint8_t action;
    uint8_t chord;

    input_state.actions_tapped = 0;
    input_state.actions_double_tapped = 0;
    input_state.actions_hold_started = 0;
    input_state.actions_released_after_hold = 0;
    input_state.chords_pressed = 0;

    for (action = 0; action < SWAN_ACTION_CAPACITY; ++action) {
        uint16_t bit = (uint16_t)(1u << action);
        bool tapped = false;

        if ((semantic_pressed & bit) != 0) {
            action_held_frames[action] = 1;
        } else if ((current_actions & bit) != 0 &&
                   action_held_frames[action] != UINT8_MAX) {
            ++action_held_frames[action];
        }

        if ((current_actions & bit) != 0 &&
            action_held_frames[action] >= input_config.hold_threshold &&
            (action_long_held & bit) == 0) {
            action_long_held |= bit;
            input_state.actions_hold_started |= bit;
            double_tap_remaining[action] = 0;
        }

        if ((semantic_released & bit) != 0) {
            if ((action_long_held & bit) != 0) {
                input_state.actions_released_after_hold |= bit;
            } else if (action_held_frames[action] != 0 &&
                       action_held_frames[action] <= input_config.tap_max_frames) {
                input_state.actions_tapped |= bit;
                tapped = true;
            } else {
                double_tap_remaining[action] = 0;
            }
            action_held_frames[action] = 0;
            action_long_held &= (uint16_t)~bit;
        }

        if (tapped) {
            if (double_tap_remaining[action] != 0) {
                input_state.actions_double_tapped |= bit;
                double_tap_remaining[action] = 0;
            } else {
                double_tap_remaining[action] = input_config.double_tap_window;
            }
        } else if (double_tap_remaining[action] != 0) {
            --double_tap_remaining[action];
        }
    }

    input_state.actions_held_long = action_long_held;
    for (chord = 0; chord < SWAN_INPUT_CHORD_CAPACITY; ++chord) {
        uint16_t actions = input_config.chord_actions[chord];
        if (chord_is_valid(actions) &&
            (semantic_pressed & actions) == actions) {
            input_state.chords_pressed |= (uint16_t)(1u << chord);
        }
    }
}

void swan_input_init(const swan_input_config_t *config) {
    memset(&input_state, 0, sizeof(input_state));
    memset(held_frames, 0, sizeof(held_frames));
    memset(action_held_frames, 0, sizeof(action_held_frames));
    memset(double_tap_remaining, 0, sizeof(double_tap_remaining));
    action_long_held = 0;
    drained_keys = 0;
    memset(&input_config, 0, sizeof(input_config));
    if (config != 0) {
        input_config = *config;
    } else {
        input_config.repeat_delay = 20;
        input_config.repeat_period = 5;
    }
    if (input_config.tap_max_frames == 0)
        input_config.tap_max_frames = SWAN_INPUT_DEFAULT_TAP_MAX_FRAMES;
    if (input_config.double_tap_window == 0)
        input_config.double_tap_window = SWAN_INPUT_DEFAULT_DOUBLE_TAP_WINDOW;
    if (input_config.hold_threshold == 0)
        input_config.hold_threshold = SWAN_INPUT_DEFAULT_HOLD_THRESHOLD;
}

void swan_input_update(uint16_t raw_keys) {
    uint16_t previous = input_state.held;
    uint16_t previous_actions = input_state.actions_held;
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
    update_gestures(previous_actions, input_state.actions_held);
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
    input_state.actions_tapped = 0;
    input_state.actions_double_tapped = 0;
    input_state.actions_hold_started = 0;
    input_state.actions_held_long = 0;
    input_state.actions_released_after_hold = 0;
    input_state.chords_pressed = 0;
    memset(action_held_frames, 0, sizeof(action_held_frames));
    memset(double_tap_remaining, 0, sizeof(double_tap_remaining));
    action_long_held = 0;
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

bool swan_action_tapped(uint8_t action) {
    return action < SWAN_ACTION_CAPACITY &&
        (input_state.actions_tapped & (uint16_t)(1u << action)) != 0;
}

bool swan_action_double_tapped(uint8_t action) {
    return action < SWAN_ACTION_CAPACITY &&
        (input_state.actions_double_tapped & (uint16_t)(1u << action)) != 0;
}

bool swan_action_hold_started(uint8_t action) {
    return action < SWAN_ACTION_CAPACITY &&
        (input_state.actions_hold_started & (uint16_t)(1u << action)) != 0;
}

bool swan_action_held_long(uint8_t action) {
    return action < SWAN_ACTION_CAPACITY &&
        (input_state.actions_held_long & (uint16_t)(1u << action)) != 0;
}

bool swan_action_released_after_hold(uint8_t action) {
    return action < SWAN_ACTION_CAPACITY &&
        (input_state.actions_released_after_hold & (uint16_t)(1u << action)) != 0;
}

bool swan_chord_pressed(uint8_t chord) {
    return chord < SWAN_INPUT_CHORD_CAPACITY &&
        (input_state.chords_pressed & (uint16_t)(1u << chord)) != 0;
}
