#include <swan/debug.h>
#include <swan/version.h>

static swan_debug_state_t debug_state;
static swan_debug_trace_t traces[SWAN_DEBUG_TRACE_CAPACITY];
static uint8_t trace_count;
static uint8_t trace_next;
static bool overlay_enabled;

const swan_build_identity_t swan_game_build_identity __attribute__((weak)) = {
    SWAN_VERSION_STRING, SWAN_MANIFEST_SCHEMA_VERSION, "unknown", "0"
};

void swan_debug_reset(void) {
    debug_state.code = SWAN_PANIC_NONE;
    debug_state.file = 0;
    debug_state.line = 0;
    debug_state.count = 0;
    trace_count = 0;
    trace_next = 0;
    overlay_enabled = false;
}

void swan_debug_fail(swan_panic_code_t code, const char *file, uint16_t line) {
    if (debug_state.code == SWAN_PANIC_NONE) {
        debug_state.code = code;
        debug_state.file = file;
        debug_state.line = line;
    }
    if (debug_state.count != UINT16_MAX) {
        ++debug_state.count;
    }
}

const swan_debug_state_t *swan_debug_state(void) {
    return &debug_state;
}

bool swan_debug_ok(void) {
    return debug_state.code == SWAN_PANIC_NONE;
}

void swan_debug_trace(uint16_t code, uint16_t value) {
    traces[trace_next].code = code;
    traces[trace_next].value = value;
    trace_next = (uint8_t)((trace_next + 1u) % SWAN_DEBUG_TRACE_CAPACITY);
    if (trace_count < SWAN_DEBUG_TRACE_CAPACITY) ++trace_count;
}

uint8_t swan_debug_trace_count(void) {
    return trace_count;
}

const swan_debug_trace_t *swan_debug_trace_get(uint8_t oldest_index) {
    uint8_t first;
    if (oldest_index >= trace_count) return 0;
    first = trace_count == SWAN_DEBUG_TRACE_CAPACITY ? trace_next : 0;
    return &traces[(uint8_t)((first + oldest_index) % SWAN_DEBUG_TRACE_CAPACITY)];
}

void swan_debug_set_overlay(bool enabled) {
    overlay_enabled = enabled;
}

bool swan_debug_overlay_enabled(void) {
    return overlay_enabled;
}

const swan_build_identity_t *swan_debug_build_identity(void) {
    return &swan_game_build_identity;
}
