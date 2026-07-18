WONDERFUL_TOOLCHAIN ?= /opt/wonderful
SWANSONG_SDK_DIR ?= ../..
SWAN ?= swan
SWAN_GFX_HARDWARE_TILE_CAPACITY ?= $(shell $(SWAN) hardware-tile-capacity --project swan.toml)
TARGET := wswan/medium
-include $(WONDERFUL_TOOLCHAIN)/target/$(TARGET)/makedefs.mk

NAME := tideglass_relay
BUILDDIR := build/obj
ELF := build/$(NAME).elf
ELF_STAGE1 := build/$(NAME)_stage1.elf
ROM := $(NAME).wsc
SWANSONG_RUNTIME_BUILD := $(abspath build/swansong-sdk-$(SWAN_GFX_HARDWARE_TILE_CAPACITY))
SWANSONG_RUNTIME := $(SWANSONG_RUNTIME_BUILD)/$(TARGET)/libswan.a

INCLUDEDIRS := src build/generated/include $(SWANSONG_SDK_DIR)/include
LIBDIRS := $(WF_ARCH_LIBDIRS)
SOURCES_C := $(sort $(wildcard src/*.c) $(wildcard build/generated/src/*.c))
OBJS := $(addprefix $(BUILDDIR)/,$(addsuffix .o,$(SOURCES_C)))
DEPS := $(OBJS:.o=.d)

INCLUDEFLAGS := $(foreach path,$(INCLUDEDIRS),-I$(path)) $(foreach path,$(LIBDIRS),-isystem $(path)/include)
LIBDIRSFLAGS := $(foreach path,$(LIBDIRS),-L$(path)/lib)
CFLAGS += -std=gnu11 -Wall -Wextra -Werror -DSWAN_GFX_HARDWARE_TILE_CAPACITY=$(SWAN_GFX_HARDWARE_TILE_CAPACITY) $(WF_ARCH_CFLAGS) $(INCLUDEFLAGS) -ffunction-sections -fdata-sections -fno-common -O2
LDFLAGS := -T$(WF_LDSCRIPT) $(LIBDIRSFLAGS) $(WF_ARCH_LDFLAGS) \
	-Wl,--start-group -lwse -lwsx -lws -lc -Wl,--end-group

.PHONY: all assets clean sdk-runtime test usage

all: assets $(ROM)

assets:
	$(SWAN) assets --project swan.toml

$(ROM) $(ELF): $(ELF_STAGE1) wfconfig.toml
	@mkdir -p build
	$(BUILDROM) -o $(ROM) --output-elf $(ELF) $<

sdk-runtime:
	$(MAKE) -C $(SWANSONG_SDK_DIR) -f mk/runtime-library.mk TARGET=$(TARGET) BUILD_ROOT=$(SWANSONG_RUNTIME_BUILD) SWAN_GFX_HARDWARE_TILE_CAPACITY=$(SWAN_GFX_HARDWARE_TILE_CAPACITY) all

$(ELF_STAGE1): $(OBJS) | sdk-runtime
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
