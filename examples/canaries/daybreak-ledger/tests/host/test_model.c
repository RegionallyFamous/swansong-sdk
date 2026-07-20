#include <assert.h>
#include <string.h>

#include "model.h"

static void quick_confirm(utility_model_t *model) {
    assert(!utility_model_update_confirm(model, true, true, false));
    assert(utility_model_update_confirm(model, false, false, true));
}

static void held_confirm(utility_model_t *model) {
    uint8_t frame;
    assert(!utility_model_update_confirm(model, true, true, false));
    for (frame = 1; frame < UTILITY_LONG_PRESS_FRAMES - 1u; ++frame)
        assert(!utility_model_update_confirm(model, false, true, false));
    assert(utility_model_update_confirm(model, false, true, false));
    assert(!utility_model_update_confirm(model, false, false, true));
}

int main(void) {
    utility_model_t model;
    utility_model_t restored;
    utility_record_t record;
    utility_record_t invalid;

    utility_model_reset(&model);
    assert(model.grid_column == 0 && model.grid_row == 0);
    assert(model.text_cursor == 0 && !model.dirty);
    assert(!utility_model_has_text(&model));

    utility_model_move_grid(&model, -1, -1);
    assert(model.grid_column == 3 && model.grid_row == 2);
    utility_model_move_text(&model, -1, -1);
    assert(model.text_cursor == 7);
    quick_confirm(&model);
    assert(model.symbols[7] == UTILITY_SYMBOL_COUNT);
    assert(model.dirty && utility_model_has_text(&model));

    utility_model_make_record(&model, &record);
    utility_model_mark_persisted(&model, UTILITY_OUTCOME_SAVED);
    assert(!model.dirty && model.outcome == UTILITY_OUTCOME_SAVED);
    assert(utility_model_restore(&restored, &record));
    assert(restored.symbols[7] == UTILITY_SYMBOL_COUNT);
    assert(!restored.dirty);

    utility_model_reset(&model);
    held_confirm(&model);
    assert(model.symbols[0] == UTILITY_SYMBOL_COUNT + 1u);
    assert(model.confirm_frames == 0 && !model.confirm_used_alternate);
    assert(utility_model_erase(&model));
    assert(!utility_model_has_text(&model));
    assert(!utility_model_erase(&model));

    utility_model_reset_document(&model);
    assert(model.dirty && model.outcome == UTILITY_OUTCOME_RESET);
    utility_model_make_record(&model, &record);
    assert(record.format == UTILITY_RECORD_FORMAT);
    assert(!memcmp(record.symbols, model.symbols, UTILITY_TEXT_CAPACITY));
    utility_model_mark_persisted(&model, UTILITY_OUTCOME_RESET);
    assert(!model.dirty && model.outcome == UTILITY_OUTCOME_RESET);

    memset(&invalid, 0, sizeof(invalid));
    invalid.format = UTILITY_RECORD_FORMAT;
    invalid.symbols[2] = UTILITY_SYMBOL_COUNT * 2u + 1u;
    assert(!utility_model_restore(&restored, &invalid));
    assert(!utility_model_has_text(&restored));
    utility_model_mark_save_error(&restored);
    assert(restored.outcome == UTILITY_OUTCOME_SAVE_ERROR);
    return 0;
}
