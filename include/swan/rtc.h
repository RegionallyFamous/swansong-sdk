#ifndef SWAN_RTC_H
#define SWAN_RTC_H

#include <stdbool.h>
#include <stdint.h>

typedef enum {
    SWAN_RTC_OK = 0,
    SWAN_RTC_UNAVAILABLE,
    SWAN_RTC_POWER_LOSS,
    SWAN_RTC_INVALID,
    SWAN_RTC_IO_ERROR,
    SWAN_RTC_WRONG_PHASE
} swan_rtc_status_t;

typedef struct {
    uint16_t year;
    uint8_t month;
    uint8_t day;
    uint8_t weekday;
    uint8_t hour;
    uint8_t minute;
    uint8_t second;
} swan_datetime_t;

typedef swan_rtc_status_t (*swan_rtc_read_fn)(void *context, uint8_t registers[7]);

typedef struct {
    void *context;
    swan_rtc_read_fn read;
} swan_rtc_backend_t;

bool swan_rtc_decode_bcd(uint8_t value, uint8_t maximum, uint8_t *decoded);
bool swan_datetime_valid(const swan_datetime_t *datetime);
swan_rtc_status_t swan_rtc_capture(const swan_rtc_backend_t *backend,
                                   swan_datetime_t *datetime);

#endif
