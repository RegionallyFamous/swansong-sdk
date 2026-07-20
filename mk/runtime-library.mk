WONDERFUL_TOOLCHAIN ?= /opt/wonderful
TARGET ?= wswan/medium
include $(WONDERFUL_TOOLCHAIN)/target/$(TARGET)/makedefs.mk

NAME := swansong
SWAN_GFX_HARDWARE_TILE_CAPACITY ?= 1024
SWAN_DETERMINISTIC_TRACE ?= 0
SWAN_DEBUG_FRAME_TRACE_CAPACITY ?= 64
BUILD_ROOT ?= build
BUILDDIR := $(BUILD_ROOT)/$(TARGET)/runtime
ARCHIVE := $(BUILD_ROOT)/$(TARGET)/libswan.a
SOURCES := $(wildcard src/*.c)
OBJECTS := $(patsubst src/%.c,$(BUILDDIR)/%.o,$(SOURCES))
INCLUDEFLAGS := -Iinclude $(foreach path,$(WF_ARCH_LIBDIRS),-isystem $(path)/include)
CFLAGS += -std=gnu11 -Wall -Wextra -Werror \
          -DSWAN_GFX_HARDWARE_TILE_CAPACITY=$(SWAN_GFX_HARDWARE_TILE_CAPACITY) \
          -DSWAN_DETERMINISTIC_TRACE=$(SWAN_DETERMINISTIC_TRACE) \
          -DSWAN_DEBUG_FRAME_TRACE_CAPACITY=$(SWAN_DEBUG_FRAME_TRACE_CAPACITY) \
          $(WF_ARCH_CFLAGS) $(INCLUDEFLAGS) \
          -ffunction-sections -fdata-sections -fno-common -O2

.PHONY: all clean
all: $(ARCHIVE)

$(ARCHIVE): $(OBJECTS)
	@$(MKDIR) -p $(@D)
	$(AR) rcs $@ $^

$(BUILDDIR)/%.o: src/%.c
	@$(MKDIR) -p $(@D)
	$(CC) $(CFLAGS) -MMD -MP -c -o $@ $<

clean:
	$(RM) -r $(BUILDDIR) $(ARCHIVE)

-include $(OBJECTS:.o=.d)
