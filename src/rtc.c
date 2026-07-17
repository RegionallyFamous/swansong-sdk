#include <swan/rtc.h>

bool swan_rtc_decode_bcd(uint8_t value, uint8_t maximum, uint8_t *decoded) {
    uint8_t high = (uint8_t)(value >> 4);
    uint8_t low = value & 15u;
    uint8_t result;
    if (decoded == 0 || high > 9 || low > 9) return false;
    result = (uint8_t)(high * 10u + low);
    if (result > maximum) return false;
    *decoded = result;
    return true;
}

static bool leap_year(uint16_t year) {
    return (year % 4u == 0 && year % 100u != 0) || year % 400u == 0;
}

bool swan_datetime_valid(const swan_datetime_t *datetime) {
    static const uint8_t days[12] = {
        31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31
    };
    uint8_t limit;
    if (datetime == 0 || datetime->year < 2000 || datetime->year > 2099 ||
        datetime->month < 1 || datetime->month > 12 || datetime->weekday > 6 ||
        datetime->hour > 23 || datetime->minute > 59 || datetime->second > 59)
        return false;
    limit = days[datetime->month - 1u];
    if (datetime->month == 2 && leap_year(datetime->year)) ++limit;
    return datetime->day >= 1 && datetime->day <= limit;
}

swan_rtc_status_t swan_rtc_capture(const swan_rtc_backend_t *backend,
                                   swan_datetime_t *datetime) {
    uint8_t raw[7];
    uint8_t year;
    swan_rtc_status_t status;
    if (backend == 0 || backend->read == 0) return SWAN_RTC_UNAVAILABLE;
    if (datetime == 0) return SWAN_RTC_INVALID;
    status = backend->read(backend->context, raw);
    if (status != SWAN_RTC_OK) return status;
    if (!swan_rtc_decode_bcd(raw[0], 99, &year) ||
        !swan_rtc_decode_bcd(raw[1], 12, &datetime->month) ||
        !swan_rtc_decode_bcd(raw[2], 31, &datetime->day) ||
        !swan_rtc_decode_bcd(raw[3], 6, &datetime->weekday) ||
        !swan_rtc_decode_bcd(raw[4], 23, &datetime->hour) ||
        !swan_rtc_decode_bcd(raw[5], 59, &datetime->minute) ||
        !swan_rtc_decode_bcd(raw[6], 59, &datetime->second))
        return SWAN_RTC_INVALID;
    datetime->year = (uint16_t)(2000u + year);
    return swan_datetime_valid(datetime) ? SWAN_RTC_OK : SWAN_RTC_INVALID;
}
