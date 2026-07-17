#include <swan/input.h>
#include <swan/wswan.h>

uint16_t swan_ws_translate_keys(uint16_t keys) {
    uint16_t translated = 0;
    if ((keys & 0x0010u) != 0) translated |= SWAN_KEY_X1;
    if ((keys & 0x0020u) != 0) translated |= SWAN_KEY_X2;
    if ((keys & 0x0040u) != 0) translated |= SWAN_KEY_X3;
    if ((keys & 0x0080u) != 0) translated |= SWAN_KEY_X4;
    if ((keys & 0x0100u) != 0) translated |= SWAN_KEY_Y1;
    if ((keys & 0x0200u) != 0) translated |= SWAN_KEY_Y2;
    if ((keys & 0x0400u) != 0) translated |= SWAN_KEY_Y3;
    if ((keys & 0x0800u) != 0) translated |= SWAN_KEY_Y4;
    if ((keys & 0x0004u) != 0) translated |= SWAN_KEY_A;
    if ((keys & 0x0008u) != 0) translated |= SWAN_KEY_B;
    if ((keys & 0x0002u) != 0) translated |= SWAN_KEY_START;
    return translated;
}
