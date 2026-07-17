CC ?= cc
CFLAGS ?= -std=c11 -O2 -Wall -Wextra -Werror -pedantic
SDK_ROOT := ../..
BUILD := $(SDK_ROOT)/build/host-tests
RUNTIME_SOURCES := $(filter-out $(SDK_ROOT)/src/platform_wonderswan.c,$(wildcard $(SDK_ROOT)/src/*.c))
TEST := $(BUILD)/runtime_tests

.PHONY: all test clean
all: test

$(TEST): runtime_tests.c $(RUNTIME_SOURCES)
	@mkdir -p $(@D)
	$(CC) $(CFLAGS) -I$(SDK_ROOT)/include -o $@ $^

test: $(TEST)
	$(TEST)

clean:
	rm -rf $(BUILD)
