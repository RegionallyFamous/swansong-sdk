# Include this fragment from a Wonderful wswan/medium game Makefile before
# source discovery. It intentionally adds sources instead of hiding a second
# linker invocation.
SWANSONG_SDK_DIR ?= $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/..)

INCLUDEDIRS += $(SWANSONG_SDK_DIR)/include
SOURCEDIRS += $(SWANSONG_SDK_DIR)/src
LIBS += -lwse -lwsx -lws
