#include <string.h>

#include <swan/path.h>

static bool visited_at(const swan_pathfinder_t *pathfinder, uint16_t index) {
    return (pathfinder->visited[index >> 3] &
            (uint8_t)(1u << (index & 7u))) != 0;
}

static void mark_visited(swan_pathfinder_t *pathfinder, uint16_t index) {
    pathfinder->visited[index >> 3] |= (uint8_t)(1u << (index & 7u));
}

swan_path_status_t swan_path_find(swan_pathfinder_t *pathfinder,
                                  const uint8_t *cell_flags, uint8_t width,
                                  uint8_t height, uint8_t blocked_mask,
                                  swan_grid_point_t start,
                                  swan_grid_point_t goal,
                                  swan_grid_point_t *path,
                                  uint16_t path_capacity,
                                  uint16_t *path_length) {
    static const int8_t dx[4] = {0, 1, 0, -1};
    static const int8_t dy[4] = {-1, 0, 1, 0};
    uint16_t cell_count;
    uint16_t start_index;
    uint16_t goal_index;
    uint16_t head = 0;
    uint16_t tail = 0;
    uint16_t current;
    uint16_t length;
    uint16_t output_index;
    uint16_t index;
    bool found = false;
    if (path_length != 0) *path_length = 0;
    if (pathfinder == 0 || cell_flags == 0 || path == 0 || path_length == 0 ||
        path_capacity == 0 || width == 0 || height == 0 ||
        width > SWAN_GRID_MAX_WIDTH || height > SWAN_GRID_MAX_HEIGHT ||
        start.x >= width || start.y >= height || goal.x >= width ||
        goal.y >= height) return SWAN_PATH_INVALID;
    cell_count = (uint16_t)width * height;
    start_index = (uint16_t)start.y * width + start.x;
    goal_index = (uint16_t)goal.y * width + goal.x;
    if ((cell_flags[start_index] & blocked_mask) != 0 ||
        (cell_flags[goal_index] & blocked_mask) != 0)
        return SWAN_PATH_UNREACHABLE;
    memset(pathfinder->visited, 0, sizeof(pathfinder->visited));
    for (index = 0; index < cell_count; ++index)
        pathfinder->parent[index] = UINT16_MAX;
    pathfinder->queue[tail++] = start_index;
    mark_visited(pathfinder, start_index);
    while (head < tail) {
        uint8_t direction;
        current = pathfinder->queue[head++];
        if (current == goal_index) {
            found = true;
            break;
        }
        for (direction = 0; direction < 4; ++direction) {
            int16_t x = (int16_t)(current % width) + dx[direction];
            int16_t y = (int16_t)(current / width) + dy[direction];
            uint16_t next;
            if (x < 0 || y < 0 || x >= width || y >= height) continue;
            next = (uint16_t)y * width + (uint16_t)x;
            if (visited_at(pathfinder, next) ||
                (cell_flags[next] & blocked_mask) != 0) continue;
            mark_visited(pathfinder, next);
            pathfinder->parent[next] = current;
            pathfinder->queue[tail++] = next;
        }
    }
    if (!found) return SWAN_PATH_UNREACHABLE;
    current = goal_index;
    length = 1;
    while (current != start_index) {
        current = pathfinder->parent[current];
        if (current == UINT16_MAX) return SWAN_PATH_UNREACHABLE;
        ++length;
    }
    *path_length = length;
    if (length > path_capacity) return SWAN_PATH_CAPACITY;
    current = goal_index;
    output_index = length;
    while (output_index != 0) {
        --output_index;
        path[output_index].x = (uint8_t)(current % width);
        path[output_index].y = (uint8_t)(current / width);
        if (current == start_index) break;
        current = pathfinder->parent[current];
    }
    return SWAN_PATH_FOUND;
}
