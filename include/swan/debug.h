#ifndef SWAN_DEBUG_H
#define SWAN_DEBUG_H

#include <stdbool.h>
#include <stdint.h>

#define SWAN_DEBUG_TRACE_CAPACITY 32u

/*
 * Deterministic frame tracing is intentionally opt-in. Shipping builds pay no
 * storage cost and marker arguments are not evaluated unless the build defines
 * SWAN_DETERMINISTIC_TRACE=1.
 */
#ifndef SWAN_DETERMINISTIC_TRACE
#define SWAN_DETERMINISTIC_TRACE 0
#endif

#ifndef SWAN_DEBUG_FRAME_TRACE_CAPACITY
#define SWAN_DEBUG_FRAME_TRACE_CAPACITY 64u
#endif

#define SWAN_DEBUG_FRAME_TRACE_BINARY_VERSION 1u
#define SWAN_DEBUG_FRAME_TRACE_RECORD_SIZE 42u
#define SWAN_DEBUG_FRAME_TRACE_HEADER_SIZE 32u
#define SWAN_DEBUG_FRAME_TRACE_MAILBOX_VERSION 2u
#define SWAN_DEBUG_FRAME_TRACE_MAILBOX_HEADER_SIZE 36u

#if SWAN_DEBUG_FRAME_TRACE_CAPACITY == 0u || SWAN_DEBUG_FRAME_TRACE_CAPACITY > 255u
#error "SWAN_DEBUG_FRAME_TRACE_CAPACITY must be from 1 through 255"
#endif

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

typedef enum {
    SWAN_DEBUG_FRAME_DIRTY = 1u << 0,
    SWAN_DEBUG_FRAME_RENDERED = 1u << 1,
    SWAN_DEBUG_FRAME_PRESENTED = 1u << 2,
    SWAN_DEBUG_FRAME_TRANSITION = 1u << 3,
    SWAN_DEBUG_FRAME_SESSION_RESET = 1u << 4,
    SWAN_DEBUG_FRAME_ANIMATED = 1u << 5,
    SWAN_DEBUG_FRAME_SPRITE_OVERFLOW = 1u << 6
} swan_debug_frame_flag_t;

/*
 * This in-memory layout is an API, not a wire format. Serialize with
 * swan_debug_frame_trace_serialize(), which emits the exact endian-stable v1
 * record defined by SWAN_DEBUG_FRAME_TRACE_RECORD_SIZE.
 */
typedef struct {
    uint32_t boot_tick;
    uint32_t session_tick;
    uint32_t state_hash;
    uint16_t input_held;
    uint16_t input_pressed;
    uint16_t input_released;
    uint16_t actions_held;
    uint16_t actions_pressed;
    uint16_t actions_released;
    uint16_t progress;
    uint16_t audio_marker;
    uint16_t transition_argument;
    uint16_t reset_count;
    uint8_t scene;
    uint8_t transition_from;
    uint8_t transition_to;
    uint8_t ending;
    uint8_t flags;
    uint8_t sprites_visible;
    uint8_t audio_voice_mask;
    uint8_t audio_sfx_mask;
    uint8_t maximum_sprites_on_scanline;
    uint8_t panic_code;
} swan_debug_frame_trace_t;

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

#if SWAN_DETERMINISTIC_TRACE
void swan_debug_frame_mark_state(uint16_t progress, uint32_t state_hash);
void swan_debug_frame_mark_ending(uint8_t ending);
void swan_debug_frame_mark_audio(uint16_t marker_bits);
uint8_t swan_debug_frame_trace_count(void);
uint32_t swan_debug_frame_trace_dropped(void);
uint16_t swan_debug_frame_trace_reset_count(void);
uint32_t swan_debug_frame_trace_total_count(void);
uint32_t swan_debug_frame_trace_stream_hash(void);
uint16_t swan_debug_frame_trace_audio_markers(void);
uint16_t swan_debug_frame_trace_transition_count(void);
const swan_debug_frame_trace_t *swan_debug_frame_trace_get(uint8_t oldest_index);
uint16_t swan_debug_frame_trace_serialized_size(void);
uint16_t swan_debug_frame_trace_serialize(uint8_t *output,
                                          uint16_t output_capacity);
#else
#define swan_debug_frame_mark_state(progress_value, state_hash_value) ((void)0)
#define swan_debug_frame_mark_ending(ending_value) ((void)0)
#define swan_debug_frame_mark_audio(marker_bits_value) ((void)0)
static inline uint8_t swan_debug_frame_trace_count(void) { return 0; }
static inline uint32_t swan_debug_frame_trace_dropped(void) { return 0; }
static inline uint16_t swan_debug_frame_trace_reset_count(void) { return 0; }
static inline uint32_t swan_debug_frame_trace_total_count(void) { return 0; }
static inline uint32_t swan_debug_frame_trace_stream_hash(void) { return 0; }
static inline uint16_t swan_debug_frame_trace_audio_markers(void) { return 0; }
static inline uint16_t swan_debug_frame_trace_transition_count(void) { return 0; }
static inline const swan_debug_frame_trace_t *
swan_debug_frame_trace_get(uint8_t oldest_index) {
    (void)oldest_index;
    return 0;
}
static inline uint16_t swan_debug_frame_trace_serialized_size(void) { return 0; }
static inline uint16_t swan_debug_frame_trace_serialize(uint8_t *output,
                                                        uint16_t output_capacity) {
    (void)output;
    (void)output_capacity;
    return 0;
}
#endif

#ifndef SWAN_DISABLE_ASSERTS
#define SWAN_ASSERT(expr, code) \
    do { if (!(expr)) swan_debug_fail((code), __FILE__, (uint16_t)__LINE__); } while (0)
#else
#define SWAN_ASSERT(expr, code) ((void)sizeof(expr))
#endif

#endif
