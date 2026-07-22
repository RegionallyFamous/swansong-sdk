#ifndef SWAN_AUDIO_H
#define SWAN_AUDIO_H

#include <stdbool.h>
#include <stdint.h>
#include <swan/types.h>

#define SWAN_AUDIO_CHANNEL_COUNT 4u
#define SWAN_AUDIO_INSTRUMENT_CAPACITY 16u
#define SWAN_AUDIO_NOTE_OFF 0xFFu
#define SWAN_AUDIO_NO_CHANGE 0xFEu
#define SWAN_AUDIO_CHANNEL_AUTO 0xFFu
#define SWAN_AUDIO_CHANNEL_MASK_ALL \
    ((uint8_t)((1u << SWAN_AUDIO_CHANNEL_COUNT) - 1u))

typedef struct {
    uint8_t wave[16];
    uint8_t attack;
    uint8_t release;
} swan_instrument_t;

typedef struct {
    uint8_t note;
    uint8_t instrument;
    uint8_t volume;
} swan_audio_command_t;

typedef struct {
    swan_audio_command_t channel[SWAN_AUDIO_CHANNEL_COUNT];
} swan_audio_row_t;

typedef struct {
    const swan_audio_row_t SWAN_FAR *rows;
    uint16_t row_count;
    uint16_t frames_per_row_q8;
    bool loop;
} swan_song_t;

typedef struct {
    swan_audio_command_t command;
    uint8_t duration_frames;
} swan_sfx_step_t;

typedef struct {
    const swan_sfx_step_t SWAN_FAR *steps;
    uint8_t step_count;
    uint8_t priority;
} swan_sfx_t;

typedef enum {
    SWAN_VOICE_SILENT = 0,
    SWAN_VOICE_MUSIC,
    SWAN_VOICE_SFX
} swan_voice_owner_t;

typedef struct {
    uint8_t note;
    uint8_t instrument;
    uint8_t volume;
    uint8_t priority;
    swan_voice_owner_t owner;
} swan_audio_voice_t;

typedef struct {
    uint16_t row;
    uint16_t phase_q8;
    bool playing;
    bool paused;
} swan_audio_position_t;

/*
 * Optional deterministic SFX routing. Reserved channels do not present music,
 * although their resolved music state continues to advance for later reuse.
 * The preferred channel breaks ties inside the best available class. Music is
 * stolen only from music_steal_channel_mask, lowest music_priority first.
 * music_duck_volume is a 0..15 multiplier applied to music while any SFX is
 * active; 15 disables ducking. Audio initialization and a null pointer passed
 * to swan_audio_set_sfx_policy() restore these defaults.
 */
typedef struct {
    uint8_t preferred_channel;
    uint8_t reserved_channel_mask;
    uint8_t music_steal_channel_mask;
    uint8_t music_duck_volume;
    uint8_t music_priority[SWAN_AUDIO_CHANNEL_COUNT];
} swan_audio_sfx_policy_t;

#define SWAN_AUDIO_SFX_POLICY_DEFAULT { \
    .preferred_channel = SWAN_AUDIO_CHANNEL_AUTO, \
    .reserved_channel_mask = 0u, \
    .music_steal_channel_mask = SWAN_AUDIO_CHANNEL_MASK_ALL, \
    .music_duck_volume = 15u, \
    .music_priority = { 0u, 0u, 0u, 0u } \
}

void swan_audio_init(const swan_instrument_t SWAN_FAR *instruments, uint8_t count);
void swan_audio_play_music(const swan_song_t SWAN_FAR *song);
void swan_audio_stop_music(void);
bool swan_audio_pause(void);
bool swan_audio_resume(void);
void swan_audio_set_sfx_policy(const swan_audio_sfx_policy_t *policy);
int8_t swan_audio_play_sfx(const swan_sfx_t SWAN_FAR *sfx);
void swan_audio_stop_all(void);
void swan_audio_tick(void);
void swan_audio_set_master_volume(uint8_t volume);
const swan_audio_voice_t *swan_audio_voices(void);
uint16_t swan_audio_music_row(void);
swan_audio_position_t swan_audio_position(void);

#endif
