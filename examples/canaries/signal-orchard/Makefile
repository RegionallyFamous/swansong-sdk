WONDERFUL_TOOLCHAIN ?= /opt/wonderful
SWANSONG_SDK_DIR ?= $(shell if command -v swan >/dev/null 2>&1; then swan sdk-path; else printf '%s' ../swansong-sdk; fi)
SWAN ?= swan
SWAN_GFX_HARDWARE_TILE_CAPACITY ?= $(shell $(SWAN) hardware-tile-capacity --project swan.toml)
TARGET := wswan/medium
SWAN_TRACE ?= 0
SWAN_TRACE_CAPACITY ?= 64
-include $(WONDERFUL_TOOLCHAIN)/target/$(TARGET)/makedefs.mk
.DEFAULT_GOAL := all

NAME := signal_orchard
BUILD_VARIANT := tiles$(SWAN_GFX_HARDWARE_TILE_CAPACITY)-trace$(SWAN_TRACE)-$(SWAN_TRACE_CAPACITY)
BUILDDIR := build/obj/$(BUILD_VARIANT)
ELF := build/$(NAME).elf
ELF_STAGE1 := build/$(NAME)_stage1.elf
ROM := $(NAME).wsc
SWANSONG_RUNTIME_BUILD := $(abspath build/swansong-sdk-$(SWAN_GFX_HARDWARE_TILE_CAPACITY)-trace$(SWAN_TRACE)-$(SWAN_TRACE_CAPACITY))
SWANSONG_RUNTIME := $(SWANSONG_RUNTIME_BUILD)/$(TARGET)/libswan.a
SWANSONG_RUNTIME_SOURCES := $(sort \
	$(wildcard $(SWANSONG_SDK_DIR)/include/swan/*.h) \
	$(wildcard $(SWANSONG_SDK_DIR)/src/*.c) \
	$(wildcard $(SWANSONG_SDK_DIR)/src/*.h) \
	$(SWANSONG_SDK_DIR)/mk/runtime-library.mk)
SDK_TOOL_INPUTS := $(shell find -L "$(SWANSONG_SDK_DIR)/python/swansong_sdk" -type f)
ASSET_INPUTS := swan.toml $(shell find assets authoring tests/play tests/outcomes -type f 2>/dev/null)
GENERATED_SOURCES_MK := build/generated/sources.mk

ifneq ($(filter clean,$(MAKECMDGOALS)),clean)
-include $(GENERATED_SOURCES_MK)
endif

INCLUDEDIRS := src build/generated/include $(SWANSONG_SDK_DIR)/include
LIBDIRS := $(WF_ARCH_LIBDIRS)
SOURCES_C := $(sort $(wildcard src/*.c) $(SWAN_GENERATED_SOURCES_C))
OBJS := $(addprefix $(BUILDDIR)/,$(addsuffix .o,$(SOURCES_C)))
DEPS := $(OBJS:.o=.d)

INCLUDEFLAGS := $(foreach path,$(INCLUDEDIRS),-I$(path)) $(foreach path,$(LIBDIRS),-isystem $(path)/include)
LIBDIRSFLAGS := $(foreach path,$(LIBDIRS),-L$(path)/lib)
CFLAGS += -std=gnu11 -Wall -Wextra -Werror -DSWAN_GFX_HARDWARE_TILE_CAPACITY=$(SWAN_GFX_HARDWARE_TILE_CAPACITY) -DSWAN_DETERMINISTIC_TRACE=$(SWAN_TRACE) -DSWAN_DEBUG_FRAME_TRACE_CAPACITY=$(SWAN_TRACE_CAPACITY) $(WF_ARCH_CFLAGS) $(INCLUDEFLAGS) -ffunction-sections -fdata-sections -fno-common -O2
LDFLAGS := -T$(WF_LDSCRIPT) $(LIBDIRSFLAGS) $(WF_ARCH_LDFLAGS) \
	-Wl,--start-group -lwse -lwsx -lws -lc -Wl,--end-group

.PHONY: all assets clean force test usage

force:

all: assets $(ROM)

assets: $(GENERATED_SOURCES_MK)

$(GENERATED_SOURCES_MK): $(ASSET_INPUTS) $(SDK_TOOL_INPUTS)
	$(SWAN) assets --project swan.toml
	@touch $(GENERATED_SOURCES_MK)

$(ROM) $(ELF): force $(ELF_STAGE1) wfconfig.toml
	@mkdir -p build
	$(BUILDROM) -o $(ROM) --output-elf $(ELF) $(ELF_STAGE1)

$(SWANSONG_RUNTIME): $(SWANSONG_RUNTIME_SOURCES)
	$(MAKE) -C $(SWANSONG_SDK_DIR) -f mk/runtime-library.mk TARGET=$(TARGET) BUILD_ROOT=$(SWANSONG_RUNTIME_BUILD) SWAN_GFX_HARDWARE_TILE_CAPACITY=$(SWAN_GFX_HARDWARE_TILE_CAPACITY) SWAN_DETERMINISTIC_TRACE=$(SWAN_TRACE) SWAN_DEBUG_FRAME_TRACE_CAPACITY=$(SWAN_TRACE_CAPACITY) all

$(ELF_STAGE1): force $(OBJS) $(SWANSONG_RUNTIME)
	@mkdir -p build
	$(CC) -r -o $@ $(OBJS) $(SWANSONG_RUNTIME) $(WF_CRT0) $(LDFLAGS)

$(BUILDDIR)/%.c.o: %.c
	@mkdir -p $(@D)
	$(CC) $(CFLAGS) -MMD -MP -c -o $@ $<

$(OBJS): | assets

test:
	@mkdir -p build
	$(HOST_CC) -std=c11 -Wall -Wextra -Werror -Isrc -o build/host_tests tests/host/test_model.c src/model.c
	build/host_tests

HOST_CC ?= cc

usage: $(ELF)
	$(ROMUSAGE) $< -g

clean:
	rm -rf build $(ROM) wfconfig.toml compile_commands.json
	rm -f src/*.o src/*.d

-include $(DEPS)
