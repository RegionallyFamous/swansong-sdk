#include <swan/debug.h>
#include <swan/scene.h>

void swan_scene_runtime_init(swan_scene_runtime_t *runtime) {
    if (runtime == 0) return;
    runtime->current = SWAN_SCENE_NONE;
    runtime->pending = SWAN_SCENE_NONE;
    runtime->pending_argument = 0;
    runtime->active = false;
    runtime->conflict = false;
}

bool swan_scene_begin(swan_scene_runtime_t *runtime, swan_scene_id_t scene,
                      uint16_t argument) {
    if (runtime == 0 || scene == SWAN_SCENE_NONE || runtime->active) {
        SWAN_ASSERT(false, SWAN_PANIC_BAD_ARGUMENT);
        return false;
    }
    runtime->current = scene;
    runtime->active = true;
    swan_scene_enter(scene, argument);
    return true;
}

bool swan_scene_request(swan_scene_runtime_t *runtime, swan_scene_id_t scene,
                        uint16_t argument) {
    if (runtime == 0 || !runtime->active || scene == SWAN_SCENE_NONE) {
        SWAN_ASSERT(false, SWAN_PANIC_BAD_ARGUMENT);
        return false;
    }
    if (runtime->pending != SWAN_SCENE_NONE) {
        runtime->conflict = true;
        SWAN_ASSERT(false, SWAN_PANIC_SCENE_CONFLICT);
        return false;
    }
    runtime->pending = scene;
    runtime->pending_argument = argument;
    return true;
}

bool swan_scene_apply(swan_scene_runtime_t *runtime) {
    swan_scene_id_t next;
    uint16_t argument;
    if (runtime == 0 || runtime->pending == SWAN_SCENE_NONE) return false;
    next = runtime->pending;
    argument = runtime->pending_argument;
    runtime->pending = SWAN_SCENE_NONE;
    runtime->pending_argument = 0;
    swan_scene_exit(runtime->current);
    runtime->current = next;
    swan_scene_enter(next, argument);
    return true;
}
