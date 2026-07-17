#ifndef SWAN_DEBUG_H
#define SWAN_DEBUG_H

#include <stdbool.h>
#include <stdint.h>

#define SWAN_DEBUG_TRACE_CAPACITY 32u

typedef enum {
    SWAN_PANIC_NONE = 0,
    SWAN_PANIC_ASSERTION,
    SWAN_PANIC_BAD_ARGUMENT,
    SWAN_PANIC_SCENE_CONFLICT,
    SWAN_PANIC_RESOURCE_LIMIT,
    SWAN_PANIC_PLATFORM
} swan_panic_code_t;

typedef struct {
    swan_panic_code_t code;
    const char *file;
    uint16_t line;
    uint16_t count;
} swan_debug_state_t;

typedef struct {
    uint16_t code;
    uint16_t value;
} swan_debug_trace_t;

typedef struct {
    const char *sdk_version;
    uint16_t manifest_schema;
    const char *game_id;
    const char *game_version;
} swan_build_identity_t;

extern const swan_build_identity_t swan_game_build_identity;

void swan_debug_reset(void);
void swan_debug_fail(swan_panic_code_t code, const char *file, uint16_t line);
const swan_debug_state_t *swan_debug_state(void);
bool swan_debug_ok(void);
void swan_debug_trace(uint16_t code, uint16_t value);
uint8_t swan_debug_trace_count(void);
const swan_debug_trace_t *swan_debug_trace_get(uint8_t oldest_index);
void swan_debug_set_overlay(bool enabled);
bool swan_debug_overlay_enabled(void);
const swan_build_identity_t *swan_debug_build_identity(void);

#ifndef SWAN_DISABLE_ASSERTS
#define SWAN_ASSERT(expr, code) \
    do { if (!(expr)) swan_debug_fail((code), __FILE__, (uint16_t)__LINE__); } while (0)
#else
#define SWAN_ASSERT(expr, code) ((void)sizeof(expr))
#endif

#endif
