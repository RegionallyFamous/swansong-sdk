#ifndef SWAN_SCENE_H
#define SWAN_SCENE_H

#include <stdbool.h>
#include <stdint.h>

typedef uint8_t swan_scene_id_t;

#define SWAN_SCENE_NONE ((swan_scene_id_t)0xFFu)

typedef struct {
    swan_scene_id_t current;
    swan_scene_id_t pending;
    uint16_t pending_argument;
    bool active;
    bool conflict;
} swan_scene_runtime_t;

struct swan_frame;

/* These fixed game symbols are implemented by the game, normally via generated dispatch. */
void swan_game_boot(void);
void swan_scene_enter(swan_scene_id_t scene, uint16_t argument);
void swan_scene_update(swan_scene_id_t scene, const struct swan_frame *frame);
void swan_scene_render(swan_scene_id_t scene);
void swan_scene_exit(swan_scene_id_t scene);

void swan_scene_runtime_init(swan_scene_runtime_t *runtime);
bool swan_scene_begin(swan_scene_runtime_t *runtime, swan_scene_id_t scene,
                      uint16_t argument);
bool swan_scene_request(swan_scene_runtime_t *runtime, swan_scene_id_t scene,
                        uint16_t argument);
bool swan_scene_apply(swan_scene_runtime_t *runtime);

#endif
