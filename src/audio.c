#include <string.h>

#include <swan/audio.h>

typedef struct {
    const swan_sfx_t SWAN_FAR *clip;
    uint8_t step;
    uint8_t remaining;
} sfx_playback_t;

static const swan_instrument_t SWAN_FAR *audio_instruments;
static uint8_t audio_instrument_count;
static const swan_song_t SWAN_FAR *music;
static uint16_t music_row;
static uint32_t music_accumulator_q8;
static swan_audio_voice_t voices[SWAN_AUDIO_CHANNEL_COUNT];
static swan_audio_voice_t paused_voices[SWAN_AUDIO_CHANNEL_COUNT];
static uint8_t base_volume[SWAN_AUDIO_CHANNEL_COUNT];
static sfx_playback_t effects[SWAN_AUDIO_CHANNEL_COUNT];
static uint8_t master_volume = 15;
static bool audio_paused;

static uint8_t scaled_volume(uint8_t volume) {
    if (volume > 15) volume = 15;
    return (uint8_t)(((uint16_t)volume * master_volume + 7u) / 15u);
}

static void set_command(uint8_t channel, const swan_audio_command_t *command,
                        swan_voice_owner_t owner, uint8_t priority) {
    if (command->note == SWAN_AUDIO_NOTE_OFF) {
        voices[channel].note = SWAN_AUDIO_NOTE_OFF;
        voices[channel].owner = SWAN_VOICE_SILENT;
        voices[channel].priority = 0;
        base_volume[channel] = 0;
        voices[channel].volume = 0;
        return;
    }
    if (command->note != SWAN_AUDIO_NO_CHANGE) voices[channel].note = command->note;
    if (command->instrument != SWAN_AUDIO_NO_CHANGE &&
        command->instrument < audio_instrument_count)
        voices[channel].instrument = command->instrument;
    if (command->volume != SWAN_AUDIO_NO_CHANGE) base_volume[channel] = command->volume > 15 ? 15 : command->volume;
    voices[channel].volume = scaled_volume(base_volume[channel]);
    voices[channel].owner = owner;
    voices[channel].priority = priority;
}

static void apply_music_row(void) {
    uint8_t channel;
    const swan_audio_row_t SWAN_FAR *row;
    if (music == 0 || music->row_count == 0) return;
    row = &music->rows[music_row];
    for (channel = 0; channel < SWAN_AUDIO_CHANNEL_COUNT; ++channel) {
        if (voices[channel].owner != SWAN_VOICE_SFX) {
            swan_audio_command_t command = row->channel[channel];
            set_command(channel, &command, SWAN_VOICE_MUSIC, 0);
        }
    }
}

void swan_audio_init(const swan_instrument_t SWAN_FAR *instruments, uint8_t count) {
    audio_instruments = instruments;
    audio_instrument_count = count > SWAN_AUDIO_INSTRUMENT_CAPACITY ?
        SWAN_AUDIO_INSTRUMENT_CAPACITY : count;
    master_volume = 15;
    music = 0;
    music_row = 0;
    music_accumulator_q8 = 0;
    audio_paused = false;
    memset(voices, 0, sizeof(voices));
    memset(paused_voices, 0, sizeof(paused_voices));
    memset(base_volume, 0, sizeof(base_volume));
    memset(effects, 0, sizeof(effects));
}

void swan_audio_play_music(const swan_song_t SWAN_FAR *song) {
    if (audio_paused) (void)swan_audio_resume();
    music = song;
    music_row = 0;
    music_accumulator_q8 = 0;
    audio_paused = false;
    if (music != 0 && music->rows != 0 && music->row_count != 0)
        apply_music_row();
}

void swan_audio_stop_music(void) {
    uint8_t channel;
    bool effect_active = false;
    music = 0;
    music_row = 0;
    music_accumulator_q8 = 0;
    for (channel = 0; channel < SWAN_AUDIO_CHANNEL_COUNT; ++channel) {
        if (audio_paused && paused_voices[channel].owner == SWAN_VOICE_MUSIC) {
            paused_voices[channel].owner = SWAN_VOICE_SILENT;
            paused_voices[channel].note = SWAN_AUDIO_NOTE_OFF;
            paused_voices[channel].volume = 0;
            paused_voices[channel].priority = 0;
            base_volume[channel] = 0;
        }
        if (voices[channel].owner == SWAN_VOICE_MUSIC) {
            voices[channel].owner = SWAN_VOICE_SILENT;
            voices[channel].note = SWAN_AUDIO_NOTE_OFF;
            voices[channel].volume = 0;
            base_volume[channel] = 0;
        }
        if (effects[channel].clip != 0) effect_active = true;
    }
    if (audio_paused && !effect_active) {
        memset(paused_voices, 0, sizeof(paused_voices));
        audio_paused = false;
    }
}

bool swan_audio_pause(void) {
    uint8_t channel;
    bool active = music != 0;
    if (audio_paused) return false;
    for (channel = 0; channel < SWAN_AUDIO_CHANNEL_COUNT; ++channel) {
        if (effects[channel].clip != 0) active = true;
    }
    if (!active) return false;
    memcpy(paused_voices, voices, sizeof(voices));
    for (channel = 0; channel < SWAN_AUDIO_CHANNEL_COUNT; ++channel) {
        voices[channel].owner = SWAN_VOICE_SILENT;
        voices[channel].note = SWAN_AUDIO_NOTE_OFF;
        voices[channel].volume = 0;
        voices[channel].priority = 0;
    }
    audio_paused = true;
    return true;
}

bool swan_audio_resume(void) {
    uint8_t channel;
    if (!audio_paused) return false;
    memcpy(voices, paused_voices, sizeof(voices));
    for (channel = 0; channel < SWAN_AUDIO_CHANNEL_COUNT; ++channel) {
        if (voices[channel].owner != SWAN_VOICE_SILENT)
            voices[channel].volume = scaled_volume(base_volume[channel]);
    }
    memset(paused_voices, 0, sizeof(paused_voices));
    audio_paused = false;
    return true;
}

static void start_effect_step(uint8_t channel) {
    const swan_sfx_step_t SWAN_FAR *step = &effects[channel].clip->steps[effects[channel].step];
    swan_audio_command_t command = step->command;
    effects[channel].remaining = step->duration_frames == 0 ? 1 : step->duration_frames;
    set_command(channel, &command, SWAN_VOICE_SFX,
                effects[channel].clip->priority);
}

int8_t swan_audio_play_sfx(const swan_sfx_t SWAN_FAR *sfx) {
    int8_t chosen = -1;
    uint8_t channel;
    if (audio_paused || sfx == 0 || sfx->steps == 0 ||
            sfx->step_count == 0) return -1;
    for (channel = 0; channel < SWAN_AUDIO_CHANNEL_COUNT; ++channel) {
        if (voices[channel].owner != SWAN_VOICE_SFX) {
            chosen = (int8_t)channel;
            break;
        }
    }
    if (chosen < 0) {
        uint8_t lowest = UINT8_MAX;
        for (channel = 0; channel < SWAN_AUDIO_CHANNEL_COUNT; ++channel) {
            if (voices[channel].priority < lowest) {
                lowest = voices[channel].priority;
                chosen = (int8_t)channel;
            }
        }
        if (sfx->priority < lowest) return -1;
    }
    effects[(uint8_t)chosen].clip = sfx;
    effects[(uint8_t)chosen].step = 0;
    start_effect_step((uint8_t)chosen);
    return chosen;
}

void swan_audio_stop_all(void) {
    uint8_t channel;
    music = 0;
    music_row = 0;
    music_accumulator_q8 = 0;
    audio_paused = false;
    memset(effects, 0, sizeof(effects));
    memset(paused_voices, 0, sizeof(paused_voices));
    for (channel = 0; channel < SWAN_AUDIO_CHANNEL_COUNT; ++channel) {
        voices[channel].note = SWAN_AUDIO_NOTE_OFF;
        voices[channel].volume = 0;
        voices[channel].priority = 0;
        voices[channel].owner = SWAN_VOICE_SILENT;
        base_volume[channel] = 0;
    }
}

void swan_audio_tick(void) {
    uint8_t channel;
    if (audio_paused) return;
    for (channel = 0; channel < SWAN_AUDIO_CHANNEL_COUNT; ++channel) {
        if (effects[channel].clip != 0) {
            if (effects[channel].remaining > 0) --effects[channel].remaining;
            if (effects[channel].remaining == 0) {
                ++effects[channel].step;
                if (effects[channel].step >= effects[channel].clip->step_count) {
                    effects[channel].clip = 0;
                    if (music != 0 && music->rows != 0 && music->row_count != 0) {
                        swan_audio_command_t command = music->rows[music_row].channel[channel];
                        set_command(channel, &command, SWAN_VOICE_MUSIC, 0);
                    } else {
                        voices[channel].owner = SWAN_VOICE_SILENT;
                        voices[channel].note = SWAN_AUDIO_NOTE_OFF;
                        voices[channel].volume = 0;
                        voices[channel].priority = 0;
                    }
                } else {
                    start_effect_step(channel);
                }
            }
        }
    }
    if (music != 0 && music->rows != 0 && music->row_count != 0 &&
        music->frames_per_row_q8 != 0) {
        music_accumulator_q8 += 256u;
        while (music_accumulator_q8 >= music->frames_per_row_q8) {
            music_accumulator_q8 -= music->frames_per_row_q8;
            ++music_row;
            if (music_row >= music->row_count) {
                if (music->loop) music_row = 0;
                else {
                    swan_audio_stop_music();
                    break;
                }
            }
            apply_music_row();
        }
    }
}

void swan_audio_set_master_volume(uint8_t volume) {
    uint8_t channel;
    master_volume = volume > 15 ? 15 : volume;
    for (channel = 0; channel < SWAN_AUDIO_CHANNEL_COUNT; ++channel) {
        voices[channel].volume = audio_paused ? 0 :
            scaled_volume(base_volume[channel]);
    }
    if (audio_paused) {
        for (channel = 0; channel < SWAN_AUDIO_CHANNEL_COUNT; ++channel) {
            if (paused_voices[channel].owner != SWAN_VOICE_SILENT)
                paused_voices[channel].volume = scaled_volume(base_volume[channel]);
        }
    }
}

const swan_audio_voice_t *swan_audio_voices(void) {
    (void)audio_instruments;
    return voices;
}

uint16_t swan_audio_music_row(void) {
    return music_row;
}

swan_audio_position_t swan_audio_position(void) {
    swan_audio_position_t position;
    position.row = music_row;
    position.phase_q8 = (uint16_t)music_accumulator_q8;
    position.playing = music != 0;
    position.paused = audio_paused;
    return position;
}

const swan_instrument_t SWAN_FAR *swan_audio_internal_instruments(void) {
    return audio_instruments;
}

uint8_t swan_audio_internal_instrument_count(void) {
    return audio_instrument_count;
}
