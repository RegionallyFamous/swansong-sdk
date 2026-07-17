#include <string.h>

#include <swan/wswan.h>

#include "runtime_internal.h"

#if defined(__WONDERFUL_WSWAN__)

#include <wonderful.h>
#include <ws.h>
#include <ws/cart/rtc.h>

static uint8_t normalized_hour(uint8_t hour, bool twenty_four_hour) {
    uint8_t high;
    uint8_t low;
    uint8_t value;
    bool pm;
    if (twenty_four_hour) return hour;
    pm = (hour & WS_CART_RTC_HOUR_AMPM) != 0;
    hour &= (uint8_t)~WS_CART_RTC_HOUR_AMPM;
    high = (uint8_t)(hour >> 4);
    low = hour & 15u;
    if (high > 1 || low > 9) return 0xFFu;
    value = (uint8_t)(high * 10u + low);
    if (value > 11) return 0xFFu;
    if (pm) value = (uint8_t)(value + 12u);
    return (uint8_t)(((value / 10u) << 4) | (value % 10u));
}

static swan_rtc_status_t capture_rtc(uint8_t registers[7]) {
    ws_cart_rtc_datetime_t datetime;
    uint8_t status;
    if (!ws_cart_rtc_read_status(&status)) return SWAN_RTC_IO_ERROR;
    if ((status & WS_CART_RTC_STATUS_POWER_LOST) != 0) return SWAN_RTC_POWER_LOSS;
    if (!ws_cart_rtc_read_datetime(&datetime)) return SWAN_RTC_IO_ERROR;
    registers[0] = datetime.date.year;
    registers[1] = datetime.date.month;
    registers[2] = datetime.date.day;
    registers[3] = datetime.date.wday;
    registers[4] = normalized_hour(datetime.time.hour,
        (status & WS_CART_RTC_STATUS_24_HOUR) != 0);
    registers[5] = datetime.time.minute;
    registers[6] = datetime.time.second;
    return registers[4] == 0xFFu ? SWAN_RTC_INVALID : SWAN_RTC_OK;
}

#else

static swan_rtc_status_t capture_rtc(uint8_t registers[7]) {
    (void)registers;
    return SWAN_RTC_IO_ERROR;
}

#endif

static swan_rtc_status_t read_rtc(void *opaque, uint8_t registers[7]) {
    swan_ws_rtc_context_t *context = opaque;
    if (context == 0 || !context->cartridge_has_rtc) return SWAN_RTC_UNAVAILABLE;
    if (!swan_core_internal_booting()) return SWAN_RTC_WRONG_PHASE;
    if (!context->captured) {
        context->capture_status = capture_rtc(context->captured_registers);
        context->captured = true;
    }
    if (context->capture_status == SWAN_RTC_OK)
        memcpy(registers, context->captured_registers,
               sizeof(context->captured_registers));
    return context->capture_status;
}

void swan_ws_rtc_backend(swan_ws_rtc_context_t *context,
                         swan_rtc_backend_t *backend, bool cartridge_has_rtc) {
    if (context == 0 || backend == 0) return;
    context->cartridge_has_rtc = cartridge_has_rtc;
    context->captured = false;
    context->capture_status = SWAN_RTC_UNAVAILABLE;
    memset(context->captured_registers, 0, sizeof(context->captured_registers));
    backend->context = context;
    backend->read = read_rtc;
}
