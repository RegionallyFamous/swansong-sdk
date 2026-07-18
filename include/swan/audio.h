#ifndef SWAN_AUDIO_H
#define SWAN_AUDIO_H

#include <stdbool.h>
#include <stdint.h>
#include <swan/types.h>

#define SWAN_AUDIO_CHANNEL_COUNT 4u
#define SWAN_AUDIO_INSTRUMENT_CAPACITY 16u
#define SWAN_AUDIO_NOTE_OFF 0xFFu
#define SWAN_AUDIO_NO_CHANGE 0xFEu

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

void swan_audio_init(const swan_instrument_t SWAN_FAR *instruments, uint8_t count);
void swan_audio_play_music(const swan_song_t SWAN_FAR *song);
void swan_audio_stop_music(void);
bool swan_audio_pause(void);
bool swan_audio_resume(void);
int8_t swan_audio_play_sfx(const swan_sfx_t SWAN_FAR *sfx);
void swan_audio_stop_all(void);
void swan_audio_tick(void);
void swan_audio_set_master_volume(uint8_t volume);
const swan_audio_voice_t *swan_audio_voices(void);
uint16_t swan_audio_music_row(void);
swan_audio_position_t swan_audio_position(void);

#endif
