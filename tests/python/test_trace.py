from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from swansong_sdk.trace import (
    BINARY_HEADER_SIZE,
    BINARY_RECORD_SIZE,
    OUTCOME_REPORT_SCHEMA,
    TRACE_SCHEMA,
    TraceCapture,
    TraceError,
    TraceFrame,
    capture_from_frames,
    decode_trace,
    encode_trace,
    load_trace,
    outcome_report_bytes,
    trace_json_bytes,
    trace_sha256,
    validate_outcome_contract,
    validate_scenario_outcome,
    validate_trace,
)


def frame(**changes: int) -> TraceFrame:
    values = {
        "boot_tick": 1,
        "session_tick": 1,
        "state_hash": 0x53570001,
        "input_held": 0x0100,
        "input_pressed": 0x0100,
        "input_released": 0,
        "actions_held": 1,
        "actions_pressed": 1,
        "actions_released": 0,
        "progress": 1,
        "audio_marker": 4,
        "transition_argument": 42,
        "reset_count": 0,
        "scene": 1,
        "transition_from": 0,
        "transition_to": 1,
        "ending": 7,
        "flags": 0x0B,
        "sprites_visible": 1,
        "audio_voice_mask": 1,
        "audio_sfx_mask": 0,
        "maximum_sprites_on_scanline": 1,
        "panic_code": 0,
    }
    values.update(changes)
    return TraceFrame(**values)


def capture() -> TraceCapture:
    return capture_from_frames((
        frame(),
        frame(
            boot_tick=2,
            session_tick=0,
            state_hash=0x53570000,
            input_held=0x0200,
            input_pressed=0x0200,
            actions_held=2,
            actions_pressed=2,
            progress=0,
            audio_marker=0,
            transition_argument=0,
            reset_count=1,
            transition_from=0xFF,
            transition_to=0xFF,
            ending=0,
            flags=0x13,
            audio_voice_mask=0,
        ),
    ), reset_count=1)


class TraceBinaryTests(unittest.TestCase):
    def test_binary_json_and_path_round_trip_are_exact(self) -> None:
        source = capture()
        binary = encode_trace(source)
        self.assertEqual(len(binary), BINARY_HEADER_SIZE + 2 * BINARY_RECORD_SIZE)
        self.assertEqual(binary[:6], b"SWTR\x01\x2a")
        self.assertEqual(binary[6:8], b"\x02\0")
        self.assertEqual(binary[12:14], b"\x01\0")
        self.assertEqual(int.from_bytes(binary[16:20], "little"), 2)
        self.assertEqual(int.from_bytes(binary[20:24], "little"), source.stream_hash)
        self.assertEqual(int.from_bytes(binary[24:26], "little"), 4)
        self.assertEqual(int.from_bytes(binary[26:28], "little"), 1)
        self.assertEqual(binary[28:32], b"\0\0\0\0")
        self.assertEqual(decode_trace(binary), source)
        self.assertEqual(encode_trace(decode_trace(binary)), binary)
        self.assertEqual(trace_sha256(source), trace_sha256(decode_trace(binary)))

        structured = json.loads(trace_json_bytes(source))
        self.assertEqual(structured["schema"], TRACE_SCHEMA)
        self.assertEqual(validate_trace(structured), source)
        self.assertEqual(trace_json_bytes(validate_trace(structured)),
                         trace_json_bytes(source))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            binary_path = root / "trace.swtr"
            json_path = root / "trace.json"
            binary_path.write_bytes(binary)
            json_path.write_bytes(trace_json_bytes(source))
            self.assertEqual(load_trace(binary_path), source)
            self.assertEqual(load_trace(json_path), source)

    def test_reader_rejects_truncation_reserved_bytes_and_invalid_relations(self) -> None:
        binary = bytearray(encode_trace(capture()))
        with self.assertRaises(TraceError):
            decode_trace(bytes(binary[:-1]))
        binary[14] = 1
        with self.assertRaises(TraceError):
            decode_trace(bytes(binary))
        with self.assertRaises(TraceError):
            encode_trace(TraceCapture((frame(transition_from=0xFF),)))
        with self.assertRaises(TraceError):
            encode_trace(TraceCapture((frame(audio_voice_mask=0x10),)))
        with self.assertRaises(TraceError):
            encode_trace(TraceCapture((frame(), frame(boot_tick=1))))


class OutcomeContractTests(unittest.TestCase):
    def contract(self) -> dict[str, object]:
        return {
            "schema": "swan-scenario-outcome-contract-v1",
            "final": {
                "scene": 1,
                "ending": 0,
                "progress": 0,
                "stateHash": 0x53570000,
            },
            "reset": {
                "expectation": "exactly-one",
                "scene": 1,
                "ending": 0,
                "progress": 0,
                "stateHash": 0x53570000,
                "sessionTick": 0,
            },
            "audio": {
                "expectation": "audible",
                "markerMask": 4,
                "peakThreshold": 0.0001,
            },
            "requireCompleteTrace": True,
        }

    def test_structured_final_reset_audio_and_state_contract_passes(self) -> None:
        report = validate_scenario_outcome(
            self.contract(), capture(),
            audio={"inspected": True, "peakAbsoluteSample": 0.25,
                   "wavSHA256": "a" * 64},
        )
        self.assertEqual(report["schema"], OUTCOME_REPORT_SCHEMA)
        self.assertTrue(report["passed"])
        self.assertEqual(report["observed"]["reset"], {"count": 1, "markedFrames": 1})
        self.assertEqual(report["observed"]["final"]["stateHash"], 0x53570000)
        self.assertEqual(outcome_report_bytes(report), outcome_report_bytes(report))
        json.loads(outcome_report_bytes(report))

    def test_failures_are_structured_and_missing_wav_never_passes(self) -> None:
        contract = self.contract()
        contract["final"] = {"scene": 2, "ending": 3, "progressAtLeast": 5}
        source = capture()
        panicked = capture_from_frames(
            source.frames[:-1] + (replace(source.frames[-1], panic_code=2),),
            reset_count=1,
        )
        report = validate_scenario_outcome(contract, panicked)
        self.assertFalse(report["passed"])
        failed = {check["id"] for check in report["checks"] if not check["passed"]}
        self.assertTrue({"final-scene", "final-ending", "final-progress-minimum",
                         "audio-inspected", "runtime-panic"}.issubset(failed))

    def test_dropped_trace_and_digest_mismatch_fail_closed(self) -> None:
        contract = self.contract()
        contract["traceSHA256"] = "0" * 64
        source = capture()
        incomplete = TraceCapture(
            source.frames,
            dropped_frame_count=3,
            reset_count=1,
            total_frame_count=len(source.frames) + 3,
            stream_hash=source.stream_hash,
            audio_marker_union=source.audio_marker_union,
            transition_count=source.transition_count,
        )
        report = validate_scenario_outcome(
            contract, incomplete,
            audio={"inspected": True, "peakAbsoluteSample": 0.25},
        )
        failed = {check["id"] for check in report["checks"] if not check["passed"]}
        self.assertIn("trace-complete", failed)
        self.assertIn("trace-sha256", failed)

    def test_contract_validation_rejects_ambiguous_progress_and_unknowns(self) -> None:
        with self.assertRaises(TraceError):
            validate_outcome_contract({
                "schema": "swan-scenario-outcome-contract-v1",
                "final": {"progress": 2, "progressAtLeast": 1},
            })
        with self.assertRaises(TraceError):
            validate_outcome_contract({
                "schema": "swan-scenario-outcome-contract-v1",
                "audio": {"expectation": "music-ish"},
            })
        with self.assertRaises(TraceError):
            validate_outcome_contract({
                "schema": "swan-scenario-outcome-contract-v1",
                "emulator": "anything-else",
            })


if __name__ == "__main__":
    unittest.main()
