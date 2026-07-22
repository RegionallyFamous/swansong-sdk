#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#include <swan/animation.h>
#include <swan/camera.h>
#include <swan/collision.h>
#include <swan/grid.h>
#include <swan/motion.h>
#include <swan/path.h>
#include <swan/pool.h>
#include <swan/records.h>
#include <swan/score.h>
#include <swan/tile_grid.h>
#include <swan/timing.h>

static unsigned tests_run;
static unsigned tests_failed;

#define CHECK(expression) do { \
    ++tests_run; \
    if (!(expression)) { \
        ++tests_failed; \
        printf("FAIL %s:%u: %s\n", __FILE__, (unsigned)__LINE__, #expression); \
    } \
} while (0)

static void test_tile_grid(void) {
    swan_tile_grid_t grid;
    swan_tile_change_t change;
    uint16_t values[6] = {9, 8, 9, 7, 7, 7};
    uint16_t cursor = 0;
    unsigned changes = 0;
    CHECK(!swan_tile_grid_init(&grid, 0, 2, 0));
    CHECK(swan_tile_grid_init(&grid, 3, 2, 7));
    CHECK(grid.cell_count == 6 && grid.dirty_count == 6);
    while (swan_tile_grid_next_dirty(&grid, &cursor, &change)) {
        CHECK(change.value == 7);
        ++changes;
    }
    CHECK(changes == 6);
    swan_tile_grid_clear_dirty(&grid);
    CHECK(grid.dirty_count == 0 && !swan_tile_grid_is_dirty(&grid, 0, 0));
    CHECK(!swan_tile_grid_set(&grid, 1, 0, 7));
    CHECK(swan_tile_grid_set(&grid, 1, 0, 8));
    CHECK(swan_tile_grid_get(&grid, 1, 0) == 8 && grid.dirty_count == 1);
    swan_tile_grid_clear_dirty(&grid);
    CHECK(swan_tile_grid_sync(&grid, values, 6) == 2);
    CHECK(grid.dirty_count == 2 && swan_tile_grid_is_dirty(&grid, 0, 0));
    CHECK(swan_tile_grid_is_dirty(&grid, 2, 0));
    CHECK(!swan_tile_grid_is_dirty(&grid, 1, 0));
    CHECK(swan_tile_grid_sync(&grid, values, 5) == 0);
}

static void test_camera(void) {
    swan_camera_t camera = {-20, 90};
    const swan_camera_bounds_t bounds = {0, 0, 68, 56};
    const swan_camera_bounds_t invalid = {5, 0, 4, 8};
    CHECK(swan_camera_clamp(&camera, &bounds));
    CHECK(camera.x == 0 && camera.y == 56);
    CHECK(swan_camera_move_clamped(&camera, INT16_MAX, INT16_MIN, &bounds));
    CHECK(camera.x == 68 && camera.y == 0);
    CHECK(swan_camera_center_clamped(&camera, 50, 50, 32, 24, &bounds));
    CHECK(camera.x == 34 && camera.y == 38);
    CHECK(swan_camera_center_clamped(&camera, -50, 200, 32, 24, &bounds));
    CHECK(camera.x == 0 && camera.y == 56);
    CHECK(!swan_camera_clamp(&camera, &invalid));
    CHECK(!swan_camera_center_clamped(&camera, 0, 0, 0, 10, &bounds));
}

static void test_animation(void) {
    swan_sprite_animation_t animation;
    CHECK(!swan_sprite_animation_init(&animation, 10, 0, 2, true));
    CHECK(swan_sprite_animation_init(&animation, 10, 3, 2, true));
    CHECK(swan_sprite_animation_tile(&animation) == 10);
    CHECK(!swan_sprite_animation_advance(&animation, 1));
    CHECK(swan_sprite_animation_advance(&animation, 1));
    CHECK(swan_sprite_animation_tile(&animation) == 11);
    CHECK(swan_sprite_animation_advance(&animation, 4));
    CHECK(swan_sprite_animation_tile(&animation) == 10 && !animation.finished);
    CHECK(swan_sprite_animation_init(&animation, 20, 2, 2, false));
    CHECK(swan_sprite_animation_advance(&animation, 2));
    CHECK(swan_sprite_animation_tile(&animation) == 21 && !animation.finished);
    CHECK(swan_sprite_animation_advance(&animation, 2));
    CHECK(animation.finished && swan_sprite_animation_tile(&animation) == 21);
    CHECK(!swan_sprite_animation_advance(&animation, 100));
    swan_sprite_animation_reset(&animation);
    CHECK(!animation.finished && swan_sprite_animation_tile(&animation) == 20);
}

static void test_collision(void) {
    static const uint8_t flags[12] = {
        0, 0, 0, 0,
        0, 0, 1, 0,
        0, 0, 0, 0
    };
    const swan_aabb_t a = {0, 0, 8, 8};
    const swan_aabb_t touching = {8, 0, 8, 8};
    const swan_aabb_t overlapping = {7, 7, 2, 2};
    const swan_aabb_t solid = {16, 8, 8, 8};
    const swan_aabb_t clear = {8, 8, 8, 8};
    const swan_aabb_t outside = {-1, 0, 1, 1};
    swan_tile_collision_map_t map = {flags, 4, 3, 8, 8, 1, true};
    CHECK(!swan_aabb_overlaps(&a, &touching));
    CHECK(swan_aabb_overlaps(&a, &overlapping));
    CHECK(swan_aabb_contains(&a, 0, 0));
    CHECK(swan_aabb_contains(&a, 7, 7));
    CHECK(!swan_aabb_contains(&a, 8, 7));
    CHECK(swan_tile_collision_aabb(&map, &solid));
    CHECK(!swan_tile_collision_aabb(&map, &clear));
    CHECK(swan_tile_collision_aabb(&map, &outside));
    map.outside_solid = false;
    CHECK(!swan_tile_collision_aabb(&map, &outside));
}

static void test_pool(void) {
    swan_pool_t pool;
    uint8_t cursor = 0;
    uint8_t slot = SWAN_POOL_NONE;
    uint8_t seen[3] = {0, 0, 0};
    CHECK(!swan_pool_init(&pool, 0));
    CHECK(swan_pool_init(&pool, 3));
    CHECK(swan_pool_acquire(&pool) == 0);
    CHECK(swan_pool_acquire(&pool) == 1);
    CHECK(swan_pool_release(&pool, 0));
    CHECK(!swan_pool_release(&pool, 0));
    CHECK(swan_pool_acquire(&pool) == 0);
    CHECK(swan_pool_acquire(&pool) == 2);
    CHECK(swan_pool_acquire(&pool) == SWAN_POOL_NONE && pool.count == 3);
    while (swan_pool_next_active(&pool, &cursor, &slot)) ++seen[slot];
    CHECK(seen[0] == 1 && seen[1] == 1 && seen[2] == 1);
}

static void test_grid_cursor(void) {
    swan_grid_cursor_t cursor;
    CHECK(!swan_grid_cursor_init(&cursor, 17, 2, false));
    CHECK(swan_grid_cursor_init(&cursor, 3, 2, false));
    CHECK(!swan_grid_cursor_move(&cursor, -1, 0));
    CHECK(swan_grid_cursor_move(&cursor, 2, 1));
    CHECK(cursor.x == 2 && cursor.y == 1);
    CHECK(swan_grid_cursor_toggle(&cursor));
    CHECK(swan_grid_cursor_is_selected(&cursor, 2, 1));
    CHECK(swan_grid_cursor_select(&cursor, 0, 0, true));
    CHECK(cursor.selected_count == 2);
    CHECK(!swan_grid_cursor_select(&cursor, 0, 0, true));
    CHECK(swan_grid_cursor_select(&cursor, 2, 1, false));
    CHECK(cursor.selected_count == 1);
    swan_grid_cursor_clear_selection(&cursor);
    CHECK(cursor.selected_count == 0);
    CHECK(swan_grid_cursor_init(&cursor, 3, 2, true));
    CHECK(swan_grid_cursor_move(&cursor, -1, -1));
    CHECK(cursor.x == 2 && cursor.y == 1);
}

static void test_pathfinding(void) {
    swan_pathfinder_t pathfinder;
    uint8_t flags[25] = {0};
    swan_grid_point_t path[32];
    const swan_grid_point_t start = {0, 0};
    const swan_grid_point_t goal = {4, 0};
    uint16_t length = 0;
    uint16_t index;
    flags[2] = 1;
    flags[7] = 1;
    flags[12] = 1;
    flags[22] = 1;
    CHECK(swan_path_find(&pathfinder, flags, 5, 5, 1, start, goal,
                         path, 32, &length) == SWAN_PATH_FOUND);
    CHECK(length > 4 && path[0].x == start.x && path[0].y == start.y);
    CHECK(path[length - 1u].x == goal.x && path[length - 1u].y == goal.y);
    for (index = 1; index < length; ++index) {
        int16_t dx = (int16_t)path[index].x - path[index - 1u].x;
        int16_t dy = (int16_t)path[index].y - path[index - 1u].y;
        if (dx < 0) dx = (int16_t)-dx;
        if (dy < 0) dy = (int16_t)-dy;
        CHECK(dx + dy == 1);
        CHECK((flags[(uint16_t)path[index].y * 5u + path[index].x] & 1u) == 0);
    }
    CHECK(swan_path_find(&pathfinder, flags, 5, 5, 1, start, goal,
                         path, 2, &length) == SWAN_PATH_CAPACITY);
    CHECK(length > 2);
    flags[17] = 1;
    CHECK(swan_path_find(&pathfinder, flags, 5, 5, 1, start, goal,
                         path, 32, &length) == SWAN_PATH_UNREACHABLE);
    CHECK(length == 0);
    CHECK(swan_path_find(&pathfinder, flags, 0, 5, 1, start, goal,
                         path, 32, &length) == SWAN_PATH_INVALID);
}

static void test_timing(void) {
    swan_timer_t timer;
    const swan_timing_windows_t windows = {1, 3, 5};
    const swan_timing_windows_t invalid = {3, 2, 5};
    swan_timer_start(&timer, 10);
    CHECK(swan_timer_active(&timer));
    CHECK(!swan_timer_advance(&timer, 3));
    CHECK(timer.remaining == 7 && swan_timer_elapsed(&timer) == 3);
    CHECK(swan_timer_progress_q8(&timer) == 76);
    CHECK(swan_timer_advance(&timer, 7));
    CHECK(!swan_timer_active(&timer) && swan_timer_progress_q8(&timer) == 255);
    CHECK(!swan_timer_advance(&timer, 1));
    swan_timer_start(&timer, 5);
    swan_timer_stop(&timer);
    CHECK(!swan_timer_active(&timer) && swan_timer_elapsed(&timer) == 0);
    CHECK(swan_timer_progress_q8(&timer) == 0);
    swan_timer_start(&timer, 0);
    CHECK(!swan_timer_active(&timer) && swan_timer_elapsed(&timer) == 0);
    CHECK(swan_timing_windows_valid(&windows));
    CHECK(!swan_timing_windows_valid(&invalid));
    CHECK(swan_timing_grade(100, 100, &windows) == SWAN_TIMING_PERFECT);
    CHECK(swan_timing_grade(100, 103, &windows) == SWAN_TIMING_GREAT);
    CHECK(swan_timing_grade(100, 95, &windows) == SWAN_TIMING_GOOD);
    CHECK(swan_timing_grade(100, 94, &windows) == SWAN_TIMING_MISS);
    CHECK(swan_timing_grade(100, 100, &invalid) == SWAN_TIMING_MISS);
    CHECK(swan_timing_direction(100, 99) == -1);
    CHECK(swan_timing_direction(100, 100) == 0);
    CHECK(swan_timing_direction(100, 101) == 1);
}

static void test_score(void) {
    swan_score_t score;
    const swan_score_config_t config = {5, 2, 3};
    const swan_score_config_t invalid = {5, 0, 3};
    const swan_score_config_t persistent = {0, 1, 2};
    CHECK(!swan_score_init(&score, &invalid));
    CHECK(swan_score_init(&score, &config));
    CHECK(swan_score_award(&score, 100) == 100);
    CHECK(score.chain == 1 && score.multiplier == 1);
    CHECK(swan_score_award(&score, 100) == 100);
    CHECK(swan_score_award(&score, 100) == 200);
    CHECK(score.points == 400 && score.chain == 3 && score.multiplier == 2);
    CHECK(!swan_score_advance(&score, 4) && score.chain_remaining == 1);
    CHECK(swan_score_advance(&score, 1));
    CHECK(score.chain == 0 && score.multiplier == 1 && score.best_chain == 3);
    CHECK(!swan_score_break_chain(&score));
    score.points = UINT32_MAX - 5u;
    CHECK(swan_score_award(&score, 10) == 5);
    CHECK(score.points == UINT32_MAX);
    swan_score_reset(&score);
    CHECK(score.points == 0 && score.best_chain == 0 && score.multiplier == 1);
    CHECK(swan_score_init(&score, &persistent));
    CHECK(swan_score_award(&score, 0) == 0 && score.chain == 1);
    CHECK(!swan_score_advance(&score, UINT16_MAX) && score.chain == 1);
    score.chain = UINT16_MAX;
    CHECK(swan_score_award(&score, 1) == 2 && score.chain == UINT16_MAX);
}

static void test_records(void) {
    swan_record_t records[3];
    swan_record_t decoded[3] = {{1, 1}, {1, 1}, {1, 1}};
    swan_record_t large[UINT8_MAX];
    uint8_t wire[SWAN_RECORDS_HEADER_SIZE + 3u * SWAN_RECORDS_RECORD_SIZE];
    uint8_t count = 0;
    uint8_t decoded_count = 99;
    uint16_t index;
    CHECK(swan_records_valid(records, count, 3));
    CHECK(swan_records_insert(records, &count, 3, 100, 1) == 0);
    CHECK(swan_records_insert(records, &count, 3, 200, 2) == 0);
    CHECK(swan_records_insert(records, &count, 3, 100, 3) == 2);
    CHECK(count == 3 && records[1].tag == 1 && records[2].tag == 3);
    CHECK(swan_records_insert(records, &count, 3, 50, 4) == SWAN_RECORD_NO_RANK);
    CHECK(swan_records_insert(records, &count, 3, 150, 5) == 1);
    CHECK(records[0].score == 200 && records[1].score == 150 &&
          records[2].score == 100 && records[2].tag == 1);
    CHECK(swan_records_serialized_size(count) == sizeof(wire));
    CHECK(swan_records_serialize(records, count, wire, sizeof(wire)) ==
          sizeof(wire));
    CHECK(wire[0] == 'S' && wire[1] == 'R' && wire[2] == 1 && wire[3] == 3);
    CHECK(wire[4] == 200 && wire[5] == 0 && wire[8] == 2 && wire[9] == 0);
    CHECK(swan_records_deserialize(wire, sizeof(wire), decoded, 3,
                                   &decoded_count));
    CHECK(decoded_count == 3 && decoded[0].score == 200 &&
          decoded[0].tag == 2 && decoded[1].score == 150 &&
          decoded[1].tag == 5 && decoded[2].score == 100 &&
          decoded[2].tag == 1);
    wire[2] = 2;
    CHECK(!swan_records_deserialize(wire, sizeof(wire), decoded, 3,
                                    &decoded_count));
    wire[2] = 1;
    wire[10] = 250;
    CHECK(!swan_records_deserialize(wire, sizeof(wire), decoded, 3,
                                    &decoded_count));
    CHECK(decoded_count == 3 && decoded[0].score == 200);
    CHECK(!swan_records_deserialize(wire, sizeof(wire) - 1u, decoded, 3,
                                    &decoded_count));
    records[2].score = 300;
    CHECK(!swan_records_valid(records, count, 3));
    CHECK(swan_records_insert(records, &count, 3, 400, 6) == SWAN_RECORD_NO_RANK);
    for (index = 0; index < UINT8_MAX; ++index) {
        large[index].score = (uint32_t)(UINT8_MAX - index);
        large[index].tag = index;
    }
    count = UINT8_MAX;
    CHECK(swan_records_valid(large, count, UINT8_MAX));
    CHECK(swan_records_insert(large, &count, UINT8_MAX, UINT32_MAX, 500) == 0);
    CHECK(count == UINT8_MAX && large[0].score == UINT32_MAX &&
          large[UINT8_MAX - 1u].score == 2);
}

static void test_motion(void) {
    swan_motion_t motion = {0, 0, 0, 0};
    const swan_motion_bounds_t bounds = {
        0, 0, swan_fixed_from_int(10), swan_fixed_from_int(10)
    };
    uint8_t hits;
    CHECK(swan_fixed_from_int(2) == 512);
    CHECK(swan_fixed_to_int_floor(511) == 1);
    CHECK(swan_fixed_to_int_floor(-257) == -2);
    CHECK(swan_fixed_approach(0, 100, 30) == 30);
    CHECK(swan_fixed_approach(90, 100, 30) == 100);
    CHECK(swan_fixed_approach(20, -20, 50) == -20);
    swan_motion_integrate(&motion, 128, -64);
    CHECK(motion.x == 128 && motion.y == -64 &&
          motion.velocity_x == 128 && motion.velocity_y == -64);
    CHECK(swan_motion_clamp_velocity(&motion, 64, 32));
    CHECK(motion.velocity_x == 64 && motion.velocity_y == -32);
    CHECK(swan_motion_brake(&motion, 16, 32));
    CHECK(motion.velocity_x == 48 && motion.velocity_y == 0);
    motion.x = swan_fixed_from_int(11);
    motion.y = -1;
    motion.velocity_x = 256;
    motion.velocity_y = -128;
    hits = swan_motion_bounce(&motion, &bounds, 128);
    CHECK(hits == (SWAN_MOTION_HIT_RIGHT | SWAN_MOTION_HIT_TOP));
    CHECK(motion.x == swan_fixed_from_int(10) && motion.y == 0);
    CHECK(motion.velocity_x == -128 && motion.velocity_y == 64);
    motion.x = -1;
    motion.y = 0;
    motion.velocity_x = 64;
    motion.velocity_y = 0;
    CHECK(swan_motion_bounce(&motion, &bounds, 0) == SWAN_MOTION_HIT_LEFT);
    CHECK(motion.x == 0 && motion.velocity_x == 64);
    motion.x = -1;
    motion.velocity_x = INT32_MIN;
    CHECK(swan_motion_bounce(&motion, &bounds, 256) == SWAN_MOTION_HIT_LEFT);
    CHECK(motion.velocity_x == INT32_MAX);
    motion.velocity_x = 100;
    motion.velocity_y = -100;
    CHECK(!swan_motion_clamp_velocity(&motion, -1, 1));
    CHECK(motion.velocity_x == 100 && motion.velocity_y == -100);
    CHECK(!swan_motion_brake(&motion, 1, -1));
    CHECK(motion.velocity_x == 100 && motion.velocity_y == -100);
    motion.x = INT32_MAX - 1;
    motion.velocity_x = 10;
    swan_motion_integrate(&motion, 0, 0);
    CHECK(motion.x == INT32_MAX);
}

int main(void) {
    test_tile_grid();
    test_camera();
    test_animation();
    test_collision();
    test_pool();
    test_grid_cursor();
    test_pathfinding();
    test_timing();
    test_score();
    test_records();
    test_motion();
    if (tests_failed != 0) {
        printf("FAIL %u of %u gameplay primitive checks\n",
               tests_failed, tests_run);
        return 1;
    }
    printf("OK   %u gameplay primitive checks\n", tests_run);
    return 0;
}
