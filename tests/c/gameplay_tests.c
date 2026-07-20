#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#include <swan/animation.h>
#include <swan/camera.h>
#include <swan/collision.h>
#include <swan/grid.h>
#include <swan/path.h>
#include <swan/pool.h>
#include <swan/tile_grid.h>

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

int main(void) {
    test_tile_grid();
    test_camera();
    test_animation();
    test_collision();
    test_pool();
    test_grid_cursor();
    test_pathfinding();
    if (tests_failed != 0) {
        printf("FAIL %u of %u gameplay primitive checks\n",
               tests_failed, tests_run);
        return 1;
    }
    printf("OK   %u gameplay primitive checks\n", tests_run);
    return 0;
}
