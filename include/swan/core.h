#ifndef SWAN_CORE_H
#define SWAN_CORE_H

#include <stdbool.h>
#include <stdint.h>

#include <swan/input.h>
#include <swan/scene.h>

typedef enum {
    SWAN_HARDWARE_MONO = 1u << 0,
    SWAN_HARDWARE_COLOR = 1u << 1,
    SWAN_HARDWARE_RTC = 1u << 2
} swan_hardware_capability_t;

typedef struct swan_frame {
    const swan_input_t *input;
    uint32_t boot_tick;
    uint32_t session_tick;
} swan_frame_t;

typedef struct {
    swan_scene_id_t initial_scene;
    uint16_t initial_argument;
    uint8_t capabilities;
    bool vertical;
    swan_input_config_t input;
} swan_core_config_t;

/* Generated once per game from swan.toml. */
extern const swan_core_config_t swan_game_config;

void swan_core_init(const swan_core_config_t *config);
void swan_core_step(uint16_t raw_keys);
void swan_core_reset_session(void);
bool swan_core_request_scene(swan_scene_id_t scene, uint16_t argument);
void swan_core_invalidate(void);
void swan_core_set_animated(bool animated);
uint32_t swan_core_boot_tick(void);
uint32_t swan_core_session_tick(void);
uint8_t swan_core_capabilities(void);
bool swan_core_vertical(void);
void swan_core_set_vertical(bool vertical);
const swan_frame_t *swan_core_frame(void);
swan_scene_runtime_t *swan_core_scenes(void);

#endif
