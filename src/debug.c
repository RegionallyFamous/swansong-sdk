#include <swan/debug.h>
#include <swan/version.h>

#if SWAN_DETERMINISTIC_TRACE
#include <string.h>

#include <swan/input.h>
#include <swan/scene.h>
#endif

static swan_debug_state_t debug_state;
static swan_debug_trace_t traces[SWAN_DEBUG_TRACE_CAPACITY];
static uint8_t trace_count;
static uint8_t trace_next;
static bool overlay_enabled;

#if SWAN_DETERMINISTIC_TRACE
static swan_debug_frame_trace_t frame_traces[SWAN_DEBUG_FRAME_TRACE_CAPACITY];
static swan_debug_frame_trace_t frame_draft;
static uint8_t frame_trace_count;
static uint8_t frame_trace_next;
static uint32_t frame_trace_dropped;
static uint32_t frame_trace_total;
static uint32_t frame_trace_stream_hash;
static uint32_t frame_trace_retained_hash;
static uint16_t frame_audio_markers;
static uint16_t frame_pending_audio_markers;
static uint16_t frame_transition_count;
static uint16_t frame_reset_count;
static uint16_t frame_progress;
static uint32_t frame_state_hash;
static uint8_t frame_ending;
static bool frame_open;
/* Private SwanSong bridge ABI: header plus ring-ordered 42-byte wire records. */
uint8_t swan_debug_frame_trace_mailbox[
    SWAN_DEBUG_FRAME_TRACE_MAILBOX_HEADER_SIZE +
    SWAN_DEBUG_FRAME_TRACE_CAPACITY * SWAN_DEBUG_FRAME_TRACE_RECORD_SIZE];
static void update_trace_mailbox(void);
#endif

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
#if SWAN_DETERMINISTIC_TRACE
    memset(frame_traces, 0, sizeof(frame_traces));
    memset(&frame_draft, 0, sizeof(frame_draft));
    frame_trace_count = 0;
    frame_trace_next = 0;
    frame_trace_dropped = 0;
    frame_trace_total = 0;
    frame_trace_stream_hash = 2166136261u;
    frame_trace_retained_hash = 0;
    frame_audio_markers = 0;
    frame_pending_audio_markers = 0;
    frame_transition_count = 0;
    frame_reset_count = 0;
    frame_progress = 0;
    frame_state_hash = 0;
    frame_ending = 0;
    frame_open = false;
    memset(swan_debug_frame_trace_mailbox, 0,
           sizeof(swan_debug_frame_trace_mailbox));
    swan_debug_frame_trace_mailbox[0] = 'S';
    swan_debug_frame_trace_mailbox[1] = 'W';
    swan_debug_frame_trace_mailbox[2] = 'M';
    swan_debug_frame_trace_mailbox[3] = 'B';
    swan_debug_frame_trace_mailbox[4] = SWAN_DEBUG_FRAME_TRACE_MAILBOX_VERSION;
    swan_debug_frame_trace_mailbox[5] = SWAN_DEBUG_FRAME_TRACE_RECORD_SIZE;
    swan_debug_frame_trace_mailbox[6] = SWAN_DEBUG_FRAME_TRACE_CAPACITY;
    update_trace_mailbox();
#endif
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

#if SWAN_DETERMINISTIC_TRACE
static void write_u16(uint8_t *output, uint16_t value) {
    output[0] = (uint8_t)value;
    output[1] = (uint8_t)(value >> 8);
}

static void write_u32(uint8_t *output, uint32_t value) {
    output[0] = (uint8_t)value;
    output[1] = (uint8_t)(value >> 8);
    output[2] = (uint8_t)(value >> 16);
    output[3] = (uint8_t)(value >> 24);
}

static uint32_t record_hash(const uint8_t *record) {
    uint32_t hash = 2166136261u;
    uint8_t index;
    for (index = 0; index < SWAN_DEBUG_FRAME_TRACE_RECORD_SIZE; ++index) {
        hash ^= record[index];
        hash *= 16777619u;
    }
    return hash;
}

static void update_trace_mailbox(void) {
    swan_debug_frame_trace_mailbox[7] = frame_trace_count;
    swan_debug_frame_trace_mailbox[8] = frame_trace_next;
    write_u32(&swan_debug_frame_trace_mailbox[12], frame_trace_dropped);
    write_u16(&swan_debug_frame_trace_mailbox[16], frame_reset_count);
    write_u16(&swan_debug_frame_trace_mailbox[18], frame_transition_count);
    write_u32(&swan_debug_frame_trace_mailbox[20], frame_trace_total);
    write_u32(&swan_debug_frame_trace_mailbox[24], frame_trace_stream_hash);
    write_u16(&swan_debug_frame_trace_mailbox[28], frame_audio_markers);
    write_u32(&swan_debug_frame_trace_mailbox[32], frame_trace_retained_hash);
}

static void serialize_frame_record(uint8_t *output,
                                   const swan_debug_frame_trace_t *record) {
    write_u32(&output[0], record->boot_tick);
    write_u32(&output[4], record->session_tick);
    write_u32(&output[8], record->state_hash);
    write_u16(&output[12], record->input_held);
    write_u16(&output[14], record->input_pressed);
    write_u16(&output[16], record->input_released);
    write_u16(&output[18], record->actions_held);
    write_u16(&output[20], record->actions_pressed);
    write_u16(&output[22], record->actions_released);
    write_u16(&output[24], record->progress);
    write_u16(&output[26], record->audio_marker);
    write_u16(&output[28], record->transition_argument);
    write_u16(&output[30], record->reset_count);
    output[32] = record->scene;
    output[33] = record->transition_from;
    output[34] = record->transition_to;
    output[35] = record->ending;
    output[36] = record->flags;
    output[37] = record->sprites_visible;
    output[38] = record->audio_voice_mask;
    output[39] = record->audio_sfx_mask;
    output[40] = record->maximum_sprites_on_scanline;
    output[41] = record->panic_code;
}

void swan_debug_frame_mark_state(uint16_t progress, uint32_t state_hash) {
    frame_progress = progress;
    frame_state_hash = state_hash;
    if (frame_open) {
        frame_draft.progress = progress;
        frame_draft.state_hash = state_hash;
    }
}

void swan_debug_frame_mark_ending(uint8_t ending) {
    frame_ending = ending;
    if (frame_open) frame_draft.ending = ending;
}

void swan_debug_frame_mark_audio(uint16_t marker_bits) {
    if (frame_open) {
        frame_draft.audio_marker |= marker_bits;
    } else {
        frame_pending_audio_markers |= marker_bits;
    }
}

void swan_debug_frame_internal_begin(uint8_t scene, uint32_t boot_tick,
                                     uint32_t session_tick,
                                     const swan_input_t *input) {
    memset(&frame_draft, 0, sizeof(frame_draft));
    frame_draft.boot_tick = boot_tick;
    frame_draft.session_tick = session_tick;
    frame_draft.scene = scene;
    frame_draft.transition_from = SWAN_SCENE_NONE;
    frame_draft.transition_to = SWAN_SCENE_NONE;
    frame_draft.progress = frame_progress;
    frame_draft.state_hash = frame_state_hash;
    frame_draft.ending = frame_ending;
    frame_draft.audio_marker = frame_pending_audio_markers;
    frame_pending_audio_markers = 0;
    frame_draft.reset_count = frame_reset_count;
    if (input != 0) {
        frame_draft.input_held = input->held;
        frame_draft.input_pressed = input->pressed;
        frame_draft.input_released = input->released;
        frame_draft.actions_held = input->actions_held;
        frame_draft.actions_pressed = input->actions_pressed;
        frame_draft.actions_released = input->actions_released;
    }
    frame_open = true;
}

void swan_debug_frame_internal_session_reset(void) {
    /* Boot/scene setup resets occur outside an observed gameplay frame. */
    if (!frame_open) return;
    if (frame_reset_count != UINT16_MAX) ++frame_reset_count;
    frame_draft.flags |= SWAN_DEBUG_FRAME_SESSION_RESET;
    frame_draft.session_tick = 0;
    frame_draft.reset_count = frame_reset_count;
}

void swan_debug_frame_internal_end(uint32_t boot_tick, uint32_t session_tick,
                                   uint8_t scene, uint8_t transition_from,
                                   uint8_t transition_to,
                                   uint16_t transition_argument,
                                   uint8_t flags, uint8_t sprites_visible,
                                   uint8_t maximum_sprites_on_scanline,
                                   uint8_t audio_voice_mask,
                                   uint8_t audio_sfx_mask,
                                   uint8_t panic_code) {
    uint8_t serialized[SWAN_DEBUG_FRAME_TRACE_RECORD_SIZE];
    uint8_t byte_index;
    uint16_t mailbox_record_offset;
    if (!frame_open) return;
    frame_draft.boot_tick = boot_tick;
    frame_draft.session_tick = session_tick;
    frame_draft.scene = scene;
    frame_draft.flags |= flags;
    frame_draft.sprites_visible = sprites_visible;
    frame_draft.maximum_sprites_on_scanline = maximum_sprites_on_scanline;
    frame_draft.audio_voice_mask = audio_voice_mask;
    frame_draft.audio_sfx_mask = audio_sfx_mask;
    frame_draft.panic_code = panic_code;
    frame_draft.reset_count = frame_reset_count;
    if (transition_from != SWAN_SCENE_NONE) {
        frame_draft.transition_from = transition_from;
        frame_draft.transition_to = transition_to;
        frame_draft.transition_argument = transition_argument;
        frame_draft.flags |= SWAN_DEBUG_FRAME_TRANSITION;
        if (frame_transition_count != UINT16_MAX) ++frame_transition_count;
    }
    frame_audio_markers |= frame_draft.audio_marker;
    serialize_frame_record(serialized, &frame_draft);
    for (byte_index = 0; byte_index < SWAN_DEBUG_FRAME_TRACE_RECORD_SIZE;
            ++byte_index) {
        frame_trace_stream_hash ^= serialized[byte_index];
        frame_trace_stream_hash *= 16777619u;
    }
    if (frame_trace_total != UINT32_MAX) ++frame_trace_total;
    mailbox_record_offset = (uint16_t)(
        SWAN_DEBUG_FRAME_TRACE_MAILBOX_HEADER_SIZE +
        (uint16_t)frame_trace_next * SWAN_DEBUG_FRAME_TRACE_RECORD_SIZE
    );
    if (frame_trace_count == SWAN_DEBUG_FRAME_TRACE_CAPACITY) {
        frame_trace_retained_hash ^=
            record_hash(&swan_debug_frame_trace_mailbox[mailbox_record_offset]);
    }
    frame_trace_retained_hash ^= record_hash(serialized);
    memcpy(
        &swan_debug_frame_trace_mailbox[mailbox_record_offset],
        serialized, SWAN_DEBUG_FRAME_TRACE_RECORD_SIZE
    );
    frame_traces[frame_trace_next] = frame_draft;
    frame_trace_next = (uint8_t)((frame_trace_next + 1u) %
                                 SWAN_DEBUG_FRAME_TRACE_CAPACITY);
    if (frame_trace_count < SWAN_DEBUG_FRAME_TRACE_CAPACITY) {
        ++frame_trace_count;
    } else if (frame_trace_dropped != UINT32_MAX) {
        ++frame_trace_dropped;
    }
    update_trace_mailbox();
    frame_open = false;
}

uint8_t swan_debug_frame_trace_count(void) { return frame_trace_count; }

uint32_t swan_debug_frame_trace_dropped(void) { return frame_trace_dropped; }

uint16_t swan_debug_frame_trace_reset_count(void) { return frame_reset_count; }

uint32_t swan_debug_frame_trace_total_count(void) { return frame_trace_total; }

uint32_t swan_debug_frame_trace_stream_hash(void) {
    return frame_trace_stream_hash;
}

uint16_t swan_debug_frame_trace_audio_markers(void) {
    return frame_audio_markers;
}

uint16_t swan_debug_frame_trace_transition_count(void) {
    return frame_transition_count;
}

const swan_debug_frame_trace_t *swan_debug_frame_trace_get(uint8_t oldest_index) {
    uint8_t first;
    if (oldest_index >= frame_trace_count) return 0;
    first = frame_trace_count == SWAN_DEBUG_FRAME_TRACE_CAPACITY ?
        frame_trace_next : 0;
    return &frame_traces[(uint8_t)((first + oldest_index) %
                                  SWAN_DEBUG_FRAME_TRACE_CAPACITY)];
}

uint16_t swan_debug_frame_trace_serialized_size(void) {
    return (uint16_t)(SWAN_DEBUG_FRAME_TRACE_HEADER_SIZE +
        (uint16_t)frame_trace_count * SWAN_DEBUG_FRAME_TRACE_RECORD_SIZE);
}

uint16_t swan_debug_frame_trace_serialize(uint8_t *output,
                                          uint16_t output_capacity) {
    uint16_t required = swan_debug_frame_trace_serialized_size();
    uint16_t offset = SWAN_DEBUG_FRAME_TRACE_HEADER_SIZE;
    uint8_t index;
    if (output == 0 || output_capacity < required) return 0;
    output[0] = 'S';
    output[1] = 'W';
    output[2] = 'T';
    output[3] = 'R';
    output[4] = SWAN_DEBUG_FRAME_TRACE_BINARY_VERSION;
    output[5] = SWAN_DEBUG_FRAME_TRACE_RECORD_SIZE;
    write_u16(&output[6], frame_trace_count);
    write_u32(&output[8], frame_trace_dropped);
    write_u16(&output[12], frame_reset_count);
    write_u16(&output[14], 0);
    write_u32(&output[16], frame_trace_total);
    write_u32(&output[20], frame_trace_stream_hash);
    write_u16(&output[24], frame_audio_markers);
    write_u16(&output[26], frame_transition_count);
    write_u32(&output[28], 0);
    for (index = 0; index < frame_trace_count; ++index) {
        const swan_debug_frame_trace_t *record =
            swan_debug_frame_trace_get(index);
        serialize_frame_record(&output[offset], record);
        offset = (uint16_t)(offset + SWAN_DEBUG_FRAME_TRACE_RECORD_SIZE);
    }
    return required;
}
#endif
