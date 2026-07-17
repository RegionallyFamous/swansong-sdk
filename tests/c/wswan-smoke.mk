WONDERFUL_TOOLCHAIN ?= /opt/wonderful
TARGET := wswan/medium
include $(WONDERFUL_TOOLCHAIN)/target/$(TARGET)/makedefs.mk

SDK_ROOT ?= ../..
BUILD ?= $(SDK_ROOT)/build/wswan-smoke
ROM ?= $(BUILD)/runtime-smoke.wsc
ELF ?= $(BUILD)/runtime-smoke.elf
STAGE1 ?= $(BUILD)/runtime-smoke-stage1.elf
OBJECT ?= $(BUILD)/wswan_smoke_game.o
WFCONFIG ?= wfconfig.toml
SMOKE_CPPFLAGS ?=
RUNTIME := $(SDK_ROOT)/build/$(TARGET)/libswan.a
INCLUDEFLAGS := -I$(SDK_ROOT)/include $(foreach path,$(WF_ARCH_LIBDIRS),-isystem $(path)/include)
LIBDIRFLAGS := $(foreach path,$(WF_ARCH_LIBDIRS),-L$(path)/lib)
CFLAGS += -std=gnu11 -Wall -Wextra -Werror $(WF_ARCH_CFLAGS) $(INCLUDEFLAGS) \
          -ffunction-sections -fdata-sections -fno-common -O2
LDFLAGS := -T$(WF_LDSCRIPT) $(LIBDIRFLAGS) $(WF_ARCH_LDFLAGS) -lwse -lwsx -lws

.PHONY: all clean
all: $(ROM)

$(RUNTIME):
	$(MAKE) -C $(SDK_ROOT) -f mk/runtime-library.mk all

$(OBJECT): wswan_smoke_game.c
	@$(MKDIR) -p $(@D)
	$(CC) $(CFLAGS) $(SMOKE_CPPFLAGS) -c -o $@ $<

$(STAGE1): $(OBJECT) $(RUNTIME)
	$(CC) -r -o $@ $(OBJECT) $(RUNTIME) $(WF_CRT0) $(LDFLAGS)

$(ROM): $(STAGE1) $(WFCONFIG)
	$(BUILDROM) --config $(WFCONFIG) -o $@ --output-elf $(ELF) $<

clean:
	$(RM) -r $(BUILD)
