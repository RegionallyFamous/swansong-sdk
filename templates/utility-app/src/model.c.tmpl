#include "model.h"

static uint8_t wrap_coordinate(uint8_t value, int8_t delta, uint8_t capacity) {
    int16_t next = (int16_t)value + delta;
    while (next < 0) next += capacity;
    while (next >= capacity) next -= capacity;
    return (uint8_t)next;
}

static void select_symbol(utility_model_t *model, bool alternate) {
    uint8_t symbol = (uint8_t)(
        model->grid_row * UTILITY_GRID_COLUMNS + model->grid_column + 1u
    );
    if (alternate) symbol = (uint8_t)(symbol + UTILITY_SYMBOL_COUNT);
    if (model->symbols[model->text_cursor] != symbol) {
        model->symbols[model->text_cursor] = symbol;
        model->dirty = true;
    }
    model->outcome = UTILITY_OUTCOME_EDITING;
}

void utility_model_reset(utility_model_t *model) {
    uint8_t index;
    model->grid_column = 0;
    model->grid_row = 0;
    model->text_cursor = 0;
    model->confirm_frames = 0;
    model->confirm_used_alternate = false;
    model->dirty = false;
    model->outcome = UTILITY_OUTCOME_EDITING;
    for (index = 0; index < UTILITY_TEXT_CAPACITY; ++index)
        model->symbols[index] = 0;
}

void utility_model_move_grid(utility_model_t *model, int8_t dx, int8_t dy) {
    model->grid_column = wrap_coordinate(
        model->grid_column, dx, UTILITY_GRID_COLUMNS
    );
    model->grid_row = wrap_coordinate(model->grid_row, dy, UTILITY_GRID_ROWS);
    model->outcome = UTILITY_OUTCOME_EDITING;
}

void utility_model_move_text(utility_model_t *model, int8_t dx, int8_t dy) {
    uint8_t column = (uint8_t)(model->text_cursor % UTILITY_TEXT_COLUMNS);
    uint8_t row = (uint8_t)(model->text_cursor / UTILITY_TEXT_COLUMNS);
    column = wrap_coordinate(column, dx, UTILITY_TEXT_COLUMNS);
    row = wrap_coordinate(row, dy, UTILITY_TEXT_ROWS);
    model->text_cursor = (uint8_t)(row * UTILITY_TEXT_COLUMNS + column);
    model->outcome = UTILITY_OUTCOME_EDITING;
}

bool utility_model_update_confirm(utility_model_t *model, bool pressed,
                                  bool held, bool released) {
    bool changed = false;
    if (pressed) {
        model->confirm_frames = 1;
        model->confirm_used_alternate = false;
    } else if (held && model->confirm_frames != 0 &&
               model->confirm_frames != UINT8_MAX) {
        ++model->confirm_frames;
    }
    if (held && model->confirm_frames >= UTILITY_LONG_PRESS_FRAMES &&
        !model->confirm_used_alternate) {
        select_symbol(model, true);
        model->confirm_used_alternate = true;
        changed = true;
    }
    if (released) {
        if (model->confirm_frames != 0 && !model->confirm_used_alternate) {
            select_symbol(model, false);
            changed = true;
        }
        model->confirm_frames = 0;
        model->confirm_used_alternate = false;
    }
    return changed;
}

bool utility_model_erase(utility_model_t *model) {
    if (model->symbols[model->text_cursor] == 0) return false;
    model->symbols[model->text_cursor] = 0;
    model->dirty = true;
    model->outcome = UTILITY_OUTCOME_EDITING;
    return true;
}

bool utility_model_has_text(const utility_model_t *model) {
    uint8_t index;
    for (index = 0; index < UTILITY_TEXT_CAPACITY; ++index)
        if (model->symbols[index] != 0) return true;
    return false;
}

void utility_model_make_record(const utility_model_t *model,
                               utility_record_t *record) {
    uint8_t index;
    record->format = UTILITY_RECORD_FORMAT;
    for (index = 0; index < UTILITY_TEXT_CAPACITY; ++index)
        record->symbols[index] = model->symbols[index];
}

bool utility_model_restore(utility_model_t *model,
                           const utility_record_t *record) {
    uint8_t index;
    utility_model_reset(model);
    if (record->format != UTILITY_RECORD_FORMAT) return false;
    for (index = 0; index < UTILITY_TEXT_CAPACITY; ++index) {
        if (record->symbols[index] > UTILITY_SYMBOL_COUNT * 2u) {
            utility_model_reset(model);
            return false;
        }
        model->symbols[index] = record->symbols[index];
    }
    return true;
}

void utility_model_reset_document(utility_model_t *model) {
    utility_model_reset(model);
    model->dirty = true;
    model->outcome = UTILITY_OUTCOME_RESET;
}

void utility_model_mark_persisted(utility_model_t *model,
                                  utility_outcome_t outcome) {
    model->dirty = false;
    model->outcome = outcome;
}

void utility_model_mark_save_error(utility_model_t *model) {
    model->outcome = UTILITY_OUTCOME_SAVE_ERROR;
}
