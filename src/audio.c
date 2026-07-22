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
static swan_audio_voice_t music_voices[SWAN_AUDIO_CHANNEL_COUNT];
static uint8_t base_volume[SWAN_AUDIO_CHANNEL_COUNT];
static uint8_t music_base_volume[SWAN_AUDIO_CHANNEL_COUNT];
static sfx_playback_t effects[SWAN_AUDIO_CHANNEL_COUNT];
static swan_audio_sfx_policy_t sfx_policy;
static uint8_t master_volume = 15;
static bool audio_paused;

static bool channel_in_mask(uint8_t mask, uint8_t channel) {
    return (mask & (uint8_t)(1u << channel)) != 0;
}

static bool effect_active(uint8_t channel) {
    return effects[channel].clip != 0;
}

static bool any_effect_active(void) {
    uint8_t channel;
    for (channel = 0; channel < SWAN_AUDIO_CHANNEL_COUNT; ++channel) {
        if (effect_active(channel)) return true;
    }
    return false;
}

static uint8_t scaled_volume(uint8_t volume, swan_voice_owner_t owner) {
    uint16_t scaled;
    if (volume > 15) volume = 15;
    scaled = (uint16_t)(((uint16_t)volume * master_volume + 7u) / 15u);
    if (owner == SWAN_VOICE_MUSIC && any_effect_active() &&
            sfx_policy.music_duck_volume < 15) {
        scaled = (uint16_t)((scaled * sfx_policy.music_duck_volume + 7u) /
                            15u);
    }
    return (uint8_t)scaled;
}

static void silence_voice(swan_audio_voice_t *voice, uint8_t *volume) {
    voice->note = SWAN_AUDIO_NOTE_OFF;
    voice->volume = 0;
    voice->priority = 0;
    voice->owner = SWAN_VOICE_SILENT;
    *volume = 0;
}

static void mute_voice(swan_audio_voice_t *voice) {
    voice->note = SWAN_AUDIO_NOTE_OFF;
    voice->volume = 0;
    voice->priority = 0;
    voice->owner = SWAN_VOICE_SILENT;
}

static void set_command(swan_audio_voice_t *voice, uint8_t *volume,
                        const swan_audio_command_t *command,
                        swan_voice_owner_t owner, uint8_t priority) {
    if (command->note == SWAN_AUDIO_NOTE_OFF) {
        silence_voice(voice, volume);
        return;
    }
    if (command->note != SWAN_AUDIO_NO_CHANGE) {
        voice->note = command->note;
        voice->owner = owner;
    }
    if (command->instrument != SWAN_AUDIO_NO_CHANGE &&
            command->instrument < audio_instrument_count) {
        voice->instrument = command->instrument;
    }
    if (command->volume != SWAN_AUDIO_NO_CHANGE) {
        *volume = command->volume > 15 ? 15 : command->volume;
    }
    if (voice->owner != SWAN_VOICE_SILENT) {
        voice->owner = owner;
        voice->priority = priority;
        voice->volume = scaled_volume(*volume, owner);
    } else {
        voice->priority = 0;
        voice->volume = 0;
    }
}

static void reset_sfx_policy(void) {
    uint8_t channel;
    sfx_policy.preferred_channel = SWAN_AUDIO_CHANNEL_AUTO;
    sfx_policy.reserved_channel_mask = 0;
    sfx_policy.music_steal_channel_mask = SWAN_AUDIO_CHANNEL_MASK_ALL;
    sfx_policy.music_duck_volume = 15;
    for (channel = 0; channel < SWAN_AUDIO_CHANNEL_COUNT; ++channel) {
        sfx_policy.music_priority[channel] = 0;
    }
}

static void clear_music_voices(void) {
    uint8_t channel;
    for (channel = 0; channel < SWAN_AUDIO_CHANNEL_COUNT; ++channel) {
        silence_voice(&music_voices[channel], &music_base_volume[channel]);
    }
}

static void present_music_voice(uint8_t channel, swan_audio_voice_t *target) {
    if (music == 0 || music_voices[channel].owner != SWAN_VOICE_MUSIC ||
            channel_in_mask(sfx_policy.reserved_channel_mask, channel)) {
        silence_voice(target, &base_volume[channel]);
        return;
    }
    *target = music_voices[channel];
    target->priority = sfx_policy.music_priority[channel];
    base_volume[channel] = music_base_volume[channel];
    target->volume = scaled_volume(base_volume[channel], SWAN_VOICE_MUSIC);
}

static void refresh_presented_state(void) {
    swan_audio_voice_t *target = audio_paused ? paused_voices : voices;
    uint8_t channel;
    for (channel = 0; channel < SWAN_AUDIO_CHANNEL_COUNT; ++channel) {
        if (effect_active(channel)) {
            if (target[channel].owner != SWAN_VOICE_SILENT) {
                target[channel].owner = SWAN_VOICE_SFX;
                target[channel].priority = effects[channel].clip->priority;
                target[channel].volume = scaled_volume(base_volume[channel],
                                                       SWAN_VOICE_SFX);
            }
        } else {
            present_music_voice(channel, &target[channel]);
        }
    }
}

static void apply_music_row(void) {
    uint8_t channel;
    const swan_audio_row_t SWAN_FAR *row;
    if (music == 0 || music->rows == 0 || music->row_count == 0) return;
    row = &music->rows[music_row];
    for (channel = 0; channel < SWAN_AUDIO_CHANNEL_COUNT; ++channel) {
        swan_audio_command_t command = row->channel[channel];
        set_command(&music_voices[channel], &music_base_volume[channel],
                    &command, SWAN_VOICE_MUSIC,
                    sfx_policy.music_priority[channel]);
    }
    refresh_presented_state();
}

void swan_audio_init(const swan_instrument_t SWAN_FAR *instruments,
                     uint8_t count) {
    uint8_t channel;
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
    memset(music_voices, 0, sizeof(music_voices));
    memset(base_volume, 0, sizeof(base_volume));
    memset(music_base_volume, 0, sizeof(music_base_volume));
    memset(effects, 0, sizeof(effects));
    reset_sfx_policy();
    for (channel = 0; channel < SWAN_AUDIO_CHANNEL_COUNT; ++channel) {
        mute_voice(&voices[channel]);
        mute_voice(&paused_voices[channel]);
    }
    clear_music_voices();
}

void swan_audio_play_music(const swan_song_t SWAN_FAR *song) {
    if (audio_paused) (void)swan_audio_resume();
    music = song;
    music_row = 0;
    music_accumulator_q8 = 0;
    audio_paused = false;
    clear_music_voices();
    if (music != 0 && music->rows != 0 && music->row_count != 0) {
        apply_music_row();
    } else {
        refresh_presented_state();
    }
}

void swan_audio_stop_music(void) {
    uint8_t channel;
    music = 0;
    music_row = 0;
    music_accumulator_q8 = 0;
    clear_music_voices();
    if (audio_paused && !any_effect_active()) {
        for (channel = 0; channel < SWAN_AUDIO_CHANNEL_COUNT; ++channel) {
            mute_voice(&paused_voices[channel]);
        }
        audio_paused = false;
    }
    refresh_presented_state();
}

bool swan_audio_pause(void) {
    uint8_t channel;
    bool active = music != 0 || any_effect_active();
    if (audio_paused || !active) return false;
    memcpy(paused_voices, voices, sizeof(voices));
    for (channel = 0; channel < SWAN_AUDIO_CHANNEL_COUNT; ++channel) {
        mute_voice(&voices[channel]);
    }
    audio_paused = true;
    return true;
}

bool swan_audio_resume(void) {
    uint8_t channel;
    if (!audio_paused) return false;
    memcpy(voices, paused_voices, sizeof(voices));
    for (channel = 0; channel < SWAN_AUDIO_CHANNEL_COUNT; ++channel) {
        mute_voice(&paused_voices[channel]);
    }
    audio_paused = false;
    refresh_presented_state();
    return true;
}

void swan_audio_set_sfx_policy(const swan_audio_sfx_policy_t *policy) {
    uint8_t channel;
    if (policy == 0) {
        reset_sfx_policy();
    } else {
        sfx_policy.preferred_channel =
            policy->preferred_channel < SWAN_AUDIO_CHANNEL_COUNT ?
            policy->preferred_channel : SWAN_AUDIO_CHANNEL_AUTO;
        sfx_policy.reserved_channel_mask =
            (uint8_t)(policy->reserved_channel_mask &
                      SWAN_AUDIO_CHANNEL_MASK_ALL);
        sfx_policy.music_steal_channel_mask =
            (uint8_t)(policy->music_steal_channel_mask &
                      SWAN_AUDIO_CHANNEL_MASK_ALL);
        sfx_policy.music_duck_volume = policy->music_duck_volume > 15 ?
            15 : policy->music_duck_volume;
        for (channel = 0; channel < SWAN_AUDIO_CHANNEL_COUNT; ++channel) {
            sfx_policy.music_priority[channel] =
                policy->music_priority[channel];
        }
    }
    for (channel = 0; channel < SWAN_AUDIO_CHANNEL_COUNT; ++channel) {
        if (music_voices[channel].owner == SWAN_VOICE_MUSIC) {
            music_voices[channel].priority =
                sfx_policy.music_priority[channel];
        }
    }
    refresh_presented_state();
}

static void start_effect_step(uint8_t channel) {
    const swan_sfx_step_t SWAN_FAR *step =
        &effects[channel].clip->steps[effects[channel].step];
    swan_audio_command_t command = step->command;
    effects[channel].remaining = step->duration_frames == 0 ?
        1 : step->duration_frames;
    set_command(&voices[channel], &base_volume[channel], &command,
                SWAN_VOICE_SFX, effects[channel].clip->priority);
}

static bool tie_break_channel(uint8_t candidate, int8_t chosen) {
    uint8_t current;
    bool candidate_preferred;
    bool current_preferred;
    bool candidate_reserved;
    bool current_reserved;
    if (chosen < 0) return true;
    current = (uint8_t)chosen;
    candidate_preferred = candidate == sfx_policy.preferred_channel;
    current_preferred = current == sfx_policy.preferred_channel;
    if (candidate_preferred != current_preferred) return candidate_preferred;
    candidate_reserved = channel_in_mask(sfx_policy.reserved_channel_mask,
                                         candidate);
    current_reserved = channel_in_mask(sfx_policy.reserved_channel_mask,
                                       current);
    if (candidate_reserved != current_reserved) return candidate_reserved;
    return candidate < current;
}

static int8_t choose_effect_channel(const swan_sfx_t SWAN_FAR *sfx) {
    int8_t chosen = -1;
    uint8_t channel;
    uint8_t lowest = UINT8_MAX;

    if (sfx_policy.preferred_channel < SWAN_AUDIO_CHANNEL_COUNT) {
        channel = sfx_policy.preferred_channel;
        if (!effect_active(channel) &&
                (channel_in_mask(sfx_policy.reserved_channel_mask, channel) ||
                 voices[channel].owner == SWAN_VOICE_SILENT)) {
            return (int8_t)channel;
        }
    }
    for (channel = 0; channel < SWAN_AUDIO_CHANNEL_COUNT; ++channel) {
        if (!effect_active(channel) &&
                channel_in_mask(sfx_policy.reserved_channel_mask, channel)) {
            return (int8_t)channel;
        }
    }
    for (channel = 0; channel < SWAN_AUDIO_CHANNEL_COUNT; ++channel) {
        if (!effect_active(channel) &&
                voices[channel].owner == SWAN_VOICE_SILENT) {
            return (int8_t)channel;
        }
    }
    for (channel = 0; channel < SWAN_AUDIO_CHANNEL_COUNT; ++channel) {
        uint8_t priority;
        if (effect_active(channel) ||
                voices[channel].owner != SWAN_VOICE_MUSIC ||
                !channel_in_mask(sfx_policy.music_steal_channel_mask,
                                 channel)) {
            continue;
        }
        priority = sfx_policy.music_priority[channel];
        if (priority < lowest ||
                (priority == lowest && tie_break_channel(channel, chosen))) {
            lowest = priority;
            chosen = (int8_t)channel;
        }
    }
    if (chosen >= 0) return chosen;

    lowest = UINT8_MAX;
    for (channel = 0; channel < SWAN_AUDIO_CHANNEL_COUNT; ++channel) {
        uint8_t priority;
        if (!effect_active(channel)) continue;
        priority = effects[channel].clip->priority;
        if (priority < lowest ||
                (priority == lowest && tie_break_channel(channel, chosen))) {
            lowest = priority;
            chosen = (int8_t)channel;
        }
    }
    if (chosen < 0 || sfx->priority < lowest) return -1;
    return chosen;
}

int8_t swan_audio_play_sfx(const swan_sfx_t SWAN_FAR *sfx) {
    int8_t chosen;
    if (audio_paused || sfx == 0 || sfx->steps == 0 ||
            sfx->step_count == 0) return -1;
    chosen = choose_effect_channel(sfx);
    if (chosen < 0) return -1;
    effects[(uint8_t)chosen].clip = sfx;
    effects[(uint8_t)chosen].step = 0;
    start_effect_step((uint8_t)chosen);
    refresh_presented_state();
    return chosen;
}

void swan_audio_stop_all(void) {
    uint8_t channel;
    music = 0;
    music_row = 0;
    music_accumulator_q8 = 0;
    audio_paused = false;
    memset(effects, 0, sizeof(effects));
    clear_music_voices();
    for (channel = 0; channel < SWAN_AUDIO_CHANNEL_COUNT; ++channel) {
        silence_voice(&voices[channel], &base_volume[channel]);
        mute_voice(&paused_voices[channel]);
    }
}

void swan_audio_tick(void) {
    uint8_t channel;
    bool effects_changed = false;
    if (audio_paused) return;
    for (channel = 0; channel < SWAN_AUDIO_CHANNEL_COUNT; ++channel) {
        if (effect_active(channel)) {
            if (effects[channel].remaining > 0) --effects[channel].remaining;
            if (effects[channel].remaining == 0) {
                ++effects[channel].step;
                if (effects[channel].step >= effects[channel].clip->step_count) {
                    effects[channel].clip = 0;
                    effects[channel].step = 0;
                    effects_changed = true;
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
                if (music->loop) {
                    music_row = 0;
                } else {
                    swan_audio_stop_music();
                    break;
                }
            }
            apply_music_row();
        }
    }
    if (effects_changed) refresh_presented_state();
}

void swan_audio_set_master_volume(uint8_t volume) {
    master_volume = volume > 15 ? 15 : volume;
    refresh_presented_state();
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
