#include <stdint.h>

#include <swan/debug.h>

static uint16_t evaluated;

uint16_t side_effect_u16(void) {
    ++evaluated;
    return evaluated;
}

uint32_t side_effect_u32(void) {
    ++evaluated;
    return evaluated;
}

int main(void) {
    swan_debug_frame_mark_state(side_effect_u16(), side_effect_u32());
    swan_debug_frame_mark_ending((uint8_t)side_effect_u16());
    swan_debug_frame_mark_audio(side_effect_u16());
    if (evaluated != 0) return 1;
    if (swan_debug_frame_trace_count() != 0) return 2;
    if (swan_debug_frame_trace_get(0) != 0) return 3;
    if (swan_debug_frame_trace_serialized_size() != 0) return 4;
    if (swan_debug_frame_trace_serialize(0, 0) != 0) return 5;
    if (swan_debug_frame_trace_dropped() != 0) return 6;
    if (swan_debug_frame_trace_reset_count() != 0) return 7;
    if (swan_debug_frame_trace_total_count() != 0) return 8;
    if (swan_debug_frame_trace_stream_hash() != 0) return 9;
    if (swan_debug_frame_trace_audio_markers() != 0) return 10;
    if (swan_debug_frame_trace_transition_count() != 0) return 11;
    return 0;
}
