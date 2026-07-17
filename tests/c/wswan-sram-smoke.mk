BUILD := ../../build/wswan-sram-smoke
ROM := $(BUILD)/runtime-sram-smoke.wsc
ELF := $(BUILD)/runtime-sram-smoke.elf
STAGE1 := $(BUILD)/runtime-sram-smoke-stage1.elf
OBJECT := $(BUILD)/wswan_sram_smoke_game.o
WFCONFIG := wfconfig-sram.toml
SMOKE_CPPFLAGS := -DSWAN_SMOKE_SRAM

include wswan-smoke.mk
