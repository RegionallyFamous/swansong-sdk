"""Deterministic save-journal and boot-time RTC laboratory models.

These models mirror the SDK's documented record format and RTC validation for
tooling experiments.  They do not emulate a WonderSwan or execute game code.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import struct
from typing import Any, Mapping, Sequence
import zlib


SCHEMA = "swansong-laboratory-report-v1"
SAVE_MAGIC = 0x4E415753
SAVE_FORMAT_VERSION = 1
SAVE_COMMITTED = 0xA55A
SAVE_HEADER_SIZE = 24


class LaboratoryError(ValueError):
    pass


@dataclass(frozen=True)
class LaboratoryReport:
    save_cases: tuple[Mapping[str, Any], ...]
    rtc_cases: tuple[Mapping[str, Any], ...]

    @property
    def passed(self) -> bool:
        return all(bool(case.get("passed")) for case in self.save_cases + self.rtc_cases)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "passed": self.passed,
            "saveCases": [dict(case) for case in self.save_cases],
            "rtcCases": [dict(case) for case in self.rtc_cases],
        }


@dataclass(frozen=True)
class SaveResult:
    status: str
    payload: bytes = b""
    schema: int | None = None
    generation: int | None = None
    slot: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "payloadHex": self.payload.hex(),
            "schema": self.schema,
            "generation": self.generation,
            "slot": self.slot,
        }


@dataclass(frozen=True)
class _Header:
    schema: int
    length: int
    generation: int
    payload_crc: int


class JournalModel:
    """Two-slot byte-storage model matching ``src/save.c`` commit ordering."""

    def __init__(self, byte_count: int, *, erased_value: int = 0xFF) -> None:
        if byte_count < SAVE_HEADER_SIZE * 2:
            raise LaboratoryError("save storage must hold two headers")
        if not 0 <= erased_value <= 255:
            raise LaboratoryError("erased_value must be a byte")
        self.media = bytearray([erased_value] * byte_count)

    @property
    def slot_size(self) -> int:
        return len(self.media) // 2

    @property
    def capacity(self) -> int:
        return min(0xFFFF, self.slot_size - SAVE_HEADER_SIZE)

    @staticmethod
    def _empty(raw: bytes) -> bool:
        return all(value == 0 for value in raw) or all(value == 0xFF for value in raw)

    @staticmethod
    def _encode(schema: int, payload: bytes, generation: int) -> bytes:
        first = struct.pack(
            "<IHHHHII", SAVE_MAGIC, SAVE_FORMAT_VERSION, schema, len(payload),
            SAVE_COMMITTED, generation & 0xFFFFFFFF, zlib.crc32(payload) & 0xFFFFFFFF,
        )
        return first + struct.pack("<I", zlib.crc32(first) & 0xFFFFFFFF)

    def _decode(self, slot: int) -> tuple[_Header | None, bool]:
        offset = slot * self.slot_size
        raw = bytes(self.media[offset:offset + SAVE_HEADER_SIZE])
        if self._empty(raw):
            return None, True
        try:
            magic, version, schema, length, committed, generation, payload_crc, header_crc = (
                struct.unpack("<IHHHHIII", raw)
            )
        except struct.error:
            return None, False
        if (magic != SAVE_MAGIC or version != SAVE_FORMAT_VERSION or
                committed != SAVE_COMMITTED or length > self.capacity or
                zlib.crc32(raw[:20]) & 0xFFFFFFFF != header_crc):
            return None, False
        payload = bytes(self.media[
            offset + SAVE_HEADER_SIZE:offset + SAVE_HEADER_SIZE + length
        ])
        if zlib.crc32(payload) & 0xFFFFFFFF != payload_crc:
            return None, False
        return _Header(schema, length, generation, payload_crc), False

    def inspect(self) -> tuple[list[_Header | None], bool]:
        decoded = [self._decode(0), self._decode(1)]
        return [item[0] for item in decoded], all(item[1] for item in decoded)

    @staticmethod
    def _newest(headers: Sequence[_Header | None]) -> int | None:
        if headers[0] is None:
            return 1 if headers[1] is not None else None
        if headers[1] is None:
            return 0
        difference = (headers[1].generation - headers[0].generation) & 0xFFFFFFFF
        return 1 if 0 < difference < 0x80000000 else 0

    def load(self, *, expected_schema: int | None = None,
             destination_capacity: int | None = None) -> SaveResult:
        headers, all_empty = self.inspect()
        slot = self._newest(headers)
        if slot is None:
            return SaveResult("empty" if all_empty else "corrupt")
        header = headers[slot]
        assert header is not None
        offset = slot * self.slot_size + SAVE_HEADER_SIZE
        payload = bytes(self.media[offset:offset + header.length])
        info = dict(schema=header.schema, generation=header.generation, slot=slot)
        if expected_schema is not None and header.schema != expected_schema:
            return SaveResult("schema_mismatch", **info)
        if destination_capacity is not None and header.length > destination_capacity:
            return SaveResult("capacity", **info)
        return SaveResult("ok", payload=payload, **info)

    def store(self, schema: int, payload: bytes, *,
              interrupt_after: str | None = None) -> SaveResult:
        if not 0 <= schema <= 0xFFFF:
            raise LaboratoryError("schema must fit uint16")
        payload = bytes(payload)
        if len(payload) > self.capacity:
            return SaveResult("capacity")
        if interrupt_after not in {None, "invalidate", "payload", "commit"}:
            raise LaboratoryError("unknown interruption point")
        headers, _ = self.inspect()
        current = self._newest(headers)
        target = 0 if current is None else 1 - current
        generation = 1 if current is None else (
            headers[current].generation + 1  # type: ignore[union-attr]
        ) & 0xFFFFFFFF
        offset = target * self.slot_size
        self.media[offset:offset + SAVE_HEADER_SIZE] = bytes(SAVE_HEADER_SIZE)
        if interrupt_after == "invalidate":
            return SaveResult("interrupted", schema=schema, generation=generation, slot=target)
        self.media[offset + SAVE_HEADER_SIZE:offset + SAVE_HEADER_SIZE + len(payload)] = payload
        if interrupt_after == "payload":
            return SaveResult("interrupted", schema=schema, generation=generation, slot=target)
        self.media[offset:offset + SAVE_HEADER_SIZE] = self._encode(schema, payload, generation)
        result = SaveResult("ok", payload, schema, generation, target)
        if interrupt_after == "commit":
            return SaveResult("interrupted", payload, schema, generation, target)
        return result

    def corrupt_payload(self, slot: int, *, byte_index: int = 0) -> None:
        header, _ = self._decode(slot)
        if header is None or not 0 <= byte_index < header.length:
            raise LaboratoryError("cannot corrupt the requested payload byte")
        offset = slot * self.slot_size + SAVE_HEADER_SIZE + byte_index
        self.media[offset] ^= 0x80


def _case(name: str, expected: str, result: SaveResult,
          **detail: Any) -> dict[str, Any]:
    return {
        "id": name,
        "expectedStatus": expected,
        "observed": result.to_dict(),
        "passed": result.status == expected,
        **detail,
    }


def run_save_laboratory(*, storage_bytes: int = 256) -> tuple[Mapping[str, Any], ...]:
    empty = JournalModel(storage_bytes)
    empty_case = _case("empty-media", "empty", empty.load(expected_schema=1))

    corrupt = JournalModel(storage_bytes)
    corrupt.store(1, b"old")
    newest = corrupt.store(1, b"new")
    assert newest.slot is not None
    corrupt.corrupt_payload(newest.slot)
    corrupt_result = corrupt.load(expected_schema=1)
    corrupt_case = _case(
        "corrupt-newest-slot", "ok", corrupt_result,
        recoveredPreviousGeneration=corrupt_result.generation == 1,
    )
    corrupt_case["passed"] = bool(corrupt_case["passed"] and
                                  corrupt_case["recoveredPreviousGeneration"])

    interrupted = JournalModel(storage_bytes)
    interrupted.store(1, b"stable")
    interrupted.store(1, b"partial", interrupt_after="payload")
    interrupted_result = interrupted.load(expected_schema=1)
    interrupted_case = _case(
        "interrupted-commit", "ok", interrupted_result,
        recoveredPayloadHex=interrupted_result.payload.hex(),
    )
    interrupted_case["passed"] = bool(interrupted_case["passed"] and
                                      interrupted_result.payload == b"stable")

    mismatch = JournalModel(storage_bytes)
    mismatch.store(2, b"schema-two")
    mismatch_case = _case("schema-mismatch", "schema_mismatch",
                          mismatch.load(expected_schema=1))

    capacity = JournalModel(storage_bytes)
    capacity_case = _case("capacity-failure", "capacity",
                          capacity.store(1, bytes(capacity.capacity + 1)),
                          capacityBytes=capacity.capacity)
    return empty_case, corrupt_case, interrupted_case, mismatch_case, capacity_case


def decode_bcd(value: int, maximum: int) -> int | None:
    if not 0 <= value <= 0xFF or maximum < 0:
        return None
    high, low = value >> 4, value & 0x0F
    decoded = high * 10 + low
    if high > 9 or low > 9 or decoded > maximum:
        return None
    return decoded


def capture_rtc(raw: Sequence[int] | None, *, status: str = "ok") -> dict[str, Any]:
    if status != "ok":
        return {"status": status, "datetime": None}
    if raw is None or len(raw) != 7:
        return {"status": "invalid", "datetime": None}
    maxima = (99, 12, 31, 6, 23, 59, 59)
    decoded = [decode_bcd(int(value), maximum) for value, maximum in zip(raw, maxima)]
    if any(value is None for value in decoded):
        return {"status": "invalid", "datetime": None}
    year, month, day, weekday, hour, minute, second = (int(value) for value in decoded)
    try:
        datetime(2000 + year, month, day, hour, minute, second)
    except ValueError:
        return {"status": "invalid", "datetime": None}
    return {
        "status": "ok",
        "datetime": {
            "year": 2000 + year,
            "month": month,
            "day": day,
            "weekday": weekday,
            "hour": hour,
            "minute": minute,
            "second": second,
        },
    }


def _bcd(value: int) -> int:
    return ((value // 10) << 4) | (value % 10)


def _rtc_raw(value: datetime) -> tuple[int, ...]:
    if not 2000 <= value.year <= 2099:
        raise LaboratoryError("RTC seed must resolve to a year from 2000 through 2099")
    return tuple(_bcd(item) for item in (
        value.year - 2000, value.month, value.day, (value.weekday() + 1) % 7,
        value.hour, value.minute, value.second,
    ))


def run_rtc_laboratory(*, rtc_seed_unix: int | None = None,
                       ) -> tuple[Mapping[str, Any], ...]:
    if rtc_seed_unix is None:
        fixed_raw = (0x24, 0x02, 0x29, 0x04, 0x23, 0x59, 0x58)
        traveled_raw = (0x24, 0x03, 0x01, 0x05, 0x00, 0x00, 0x02)
    else:
        if isinstance(rtc_seed_unix, bool) or not isinstance(rtc_seed_unix, int):
            raise LaboratoryError("RTC seed must be an integer Unix timestamp")
        try:
            seeded = datetime.fromtimestamp(rtc_seed_unix, timezone.utc)
        except (OverflowError, OSError, ValueError) as exc:
            raise LaboratoryError("RTC seed is outside the supported timestamp range") from exc
        fixed_raw = _rtc_raw(seeded)
        traveled_raw = _rtc_raw(seeded + timedelta(days=1, seconds=4))
    fixed = capture_rtc(fixed_raw)
    invalid = capture_rtc((0x24, 0x13, 0x01, 0x05, 0x00, 0x00, 0x00))
    unavailable = capture_rtc(None, status="unavailable")
    power_loss = capture_rtc(None, status="power_loss")
    traveled = capture_rtc(traveled_raw)
    before = fixed["datetime"]
    after = traveled["datetime"]
    assert isinstance(before, Mapping) and isinstance(after, Mapping)
    before_dt = datetime(before["year"], before["month"], before["day"],
                         before["hour"], before["minute"], before["second"])
    after_dt = datetime(after["year"], after["month"], after["day"],
                        after["hour"], after["minute"], after["second"])
    return (
        {"id": "fixed-time", "expectedStatus": "ok", "observed": fixed,
         "passed": fixed["status"] == "ok"},
        {"id": "invalid-bcd", "expectedStatus": "invalid", "observed": invalid,
         "passed": invalid["status"] == "invalid"},
        {"id": "unavailable", "expectedStatus": "unavailable", "observed": unavailable,
         "passed": unavailable["status"] == "unavailable"},
        {"id": "power-loss", "expectedStatus": "power_loss", "observed": power_loss,
         "passed": power_loss["status"] == "power_loss"},
        {"id": "time-travel", "expectedStatus": "ok", "observed": traveled,
         "deltaSeconds": int((after_dt - before_dt).total_seconds()),
         "injectionBoundary": "new-boot-capture",
         "passed": traveled["status"] == "ok" and after_dt > before_dt},
    )


def run_laboratory(*, storage_bytes: int = 256,
                   rtc_seed_unix: int | None = None) -> LaboratoryReport:
    return LaboratoryReport(
        tuple(run_save_laboratory(storage_bytes=storage_bytes)),
        tuple(run_rtc_laboratory(rtc_seed_unix=rtc_seed_unix)),
    )
