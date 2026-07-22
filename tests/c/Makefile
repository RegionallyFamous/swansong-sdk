CC ?= cc
CFLAGS ?= -std=c11 -O2 -Wall -Wextra -Werror -pedantic
TRACE_CFLAGS := $(CFLAGS) -DSWAN_DETERMINISTIC_TRACE=1
SDK_ROOT := ../..
BUILD := $(SDK_ROOT)/build/host-tests
RUNTIME_SOURCES := $(filter-out $(SDK_ROOT)/src/platform_wonderswan.c,$(wildcard $(SDK_ROOT)/src/*.c))
TEST := $(BUILD)/runtime_tests
TRACE_DISABLED_TEST := $(BUILD)/trace_disabled
GAMEPLAY_SOURCES := $(addprefix $(SDK_ROOT)/src/,animation.c camera.c collision.c grid.c motion.c path.c pool.c records.c score.c tile_grid.c timing.c)
GAMEPLAY_TEST := $(BUILD)/gameplay_tests

.PHONY: all test clean
all: test

$(TEST): runtime_tests.c $(RUNTIME_SOURCES)
	@mkdir -p $(@D)
	$(CC) $(TRACE_CFLAGS) -I$(SDK_ROOT)/include -o $@ $^

$(TRACE_DISABLED_TEST): trace_disabled.c
	@mkdir -p $(@D)
	$(CC) $(CFLAGS) -I$(SDK_ROOT)/include -o $@ $^

$(GAMEPLAY_TEST): gameplay_tests.c $(GAMEPLAY_SOURCES)
	@mkdir -p $(@D)
	$(CC) $(CFLAGS) -I$(SDK_ROOT)/include -o $@ $^

test: $(TEST) $(TRACE_DISABLED_TEST) $(GAMEPLAY_TEST)
	$(TEST)
	$(TRACE_DISABLED_TEST)
	$(GAMEPLAY_TEST)

clean:
	rm -rf $(BUILD)
