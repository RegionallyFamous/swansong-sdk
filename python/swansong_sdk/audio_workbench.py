"""Deterministic, source-only audio authoring previews.

The renderer is deliberately not a WonderSwan emulator.  It makes SDK music
patterns easy to audition on a host while keeping SwanSong WAV evidence as the
only authority for shipping cartridge audio.
"""

from __future__ import annotations

from contextlib import nullcontext
from decimal import Decimal, ROUND_HALF_UP, localcontext
import hashlib
import io
from pathlib import Path
import struct
import tomllib
import wave
from typing import BinaryIO, Mapping, Sequence


REPORT_SCHEMA = "swansong-audio-workbench-report-v1"
ARBITRATION_SCHEMA = "swansong-sfx-arbitration-report-v1"
NATIVE_REFRESH_HZ = 75
NOTE_OFF = 255
NO_CHANGE = 254


class AudioWorkbenchError(RuntimeError):
    pass


def _integer(value: object, context: str, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise AudioWorkbenchError(f"{context} must be {minimum}..{maximum}")
    return value


def _music_document(source: Path | bytes | Mapping[str, object]) -> tuple[dict[str, object], bytes]:
    if isinstance(source, Mapping):
        document = dict(source)
        payload = repr(sorted(document.items())).encode("utf-8")
    else:
        try:
            payload = source if isinstance(source, bytes) else source.read_bytes()
            document = tomllib.loads(payload.decode("utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
            raise AudioWorkbenchError(f"could not read audio source: {exc}") from exc
    if document.get("type") != "music":
        raise AudioWorkbenchError("audio workbench currently requires type = \"music\"")
    instruments = document.get("instruments")
    rows = document.get("rows")
    if not isinstance(instruments, list) or not 1 <= len(instruments) <= 16:
        raise AudioWorkbenchError("music requires 1..16 instruments")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 65535:
        raise AudioWorkbenchError("music requires 1..65535 rows")
    for index, instrument in enumerate(instruments):
        if not isinstance(instrument, dict):
            raise AudioWorkbenchError(f"instrument {index} must be a table")
        wave_data = instrument.get("wave")
        if not isinstance(wave_data, list) or len(wave_data) != 16:
            raise AudioWorkbenchError(f"instrument {index} wave must contain 16 samples")
        for sample_index, sample in enumerate(wave_data):
            _integer(sample, f"instrument {index} wave {sample_index}", 0, 15)
        _integer(instrument.get("attack", 0), f"instrument {index} attack", 0, 255)
        _integer(instrument.get("release", 0), f"instrument {index} release", 0, 255)
    for row_index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise AudioWorkbenchError(f"row {row_index} must be a table")
        channels = row.get("channels")
        if not isinstance(channels, list) or len(channels) != 4:
            raise AudioWorkbenchError(f"row {row_index} requires four channels")
        for channel_index, command in enumerate(channels):
            if not isinstance(command, list) or len(command) != 3:
                raise AudioWorkbenchError(
                    f"row {row_index} channel {channel_index} must be [note, instrument, volume]"
                )
            note, instrument, volume = command
            _integer(note, f"row {row_index} channel {channel_index} note", 0, 255)
            if note not in range(128) and note not in (NO_CHANGE, NOTE_OFF):
                raise AudioWorkbenchError("music note must be 0..127, 254, or 255")
            _integer(instrument, f"row {row_index} channel {channel_index} instrument", 0, 254)
            if instrument != NO_CHANGE and instrument >= len(instruments):
                raise AudioWorkbenchError("music command references an unavailable instrument")
            _integer(volume, f"row {row_index} channel {channel_index} volume", 0, 254)
            if volume != NO_CHANGE and volume > 15:
                raise AudioWorkbenchError("music volume must be 0..15 or 254")
    frames = _integer(document.get("frames_per_row_q8"), "frames_per_row_q8", 1, 65535)
    if not isinstance(document.get("loop", True), bool):
        raise AudioWorkbenchError("music loop must be true or false")
    document["frames_per_row_q8"] = frames
    return document, payload


def _frequency_microhertz(note: int) -> int:
    with localcontext() as context:
        context.prec = 48
        frequency = Decimal(440) * (Decimal(2) ** (Decimal(note - 69) / Decimal(12)))
        return int((frequency * Decimal(1_000_000)).to_integral_value(rounding=ROUND_HALF_UP))


def _wav_bytes(document: Mapping[str, object], *, sample_rate: int, loops: int) -> tuple[bytes, dict[str, object]]:
    _integer(sample_rate, "sample rate", 8000, 96000)
    _integer(loops, "loops", 1, 16)
    instruments = document["instruments"]
    rows = document["rows"]
    assert isinstance(instruments, list) and isinstance(rows, list)
    frames_per_row_q8 = int(document["frames_per_row_q8"])
    phase = [0, 0, 0, 0]
    note = [NOTE_OFF, NOTE_OFF, NOTE_OFF, NOTE_OFF]
    instrument_id = [0, 0, 0, 0]
    volume = [0, 0, 0, 0]
    note_events = [0, 0, 0, 0]
    active_rows = [0, 0, 0, 0]
    max_polyphony = 0
    peak = 0
    pcm = bytearray()
    sample_accumulator = 0

    for _ in range(loops):
        for raw_row in rows:
            assert isinstance(raw_row, dict)
            channels = raw_row["channels"]
            assert isinstance(channels, list)
            for channel, raw_command in enumerate(channels):
                assert isinstance(raw_command, list)
                command_note, command_instrument, command_volume = (int(item) for item in raw_command)
                if command_note == NOTE_OFF:
                    note[channel] = NOTE_OFF
                    volume[channel] = 0
                elif command_note != NO_CHANGE:
                    note[channel] = command_note
                    phase[channel] = 0
                    note_events[channel] += 1
                if command_instrument != NO_CHANGE:
                    instrument_id[channel] = command_instrument
                if command_volume != NO_CHANGE:
                    volume[channel] = command_volume
            active = sum(1 for channel in range(4) if note[channel] != NOTE_OFF and volume[channel] > 0)
            max_polyphony = max(max_polyphony, active)
            for channel in range(4):
                if note[channel] != NOTE_OFF and volume[channel] > 0:
                    active_rows[channel] += 1

            sample_accumulator += frames_per_row_q8 * sample_rate
            row_samples, sample_accumulator = divmod(sample_accumulator, 256 * NATIVE_REFRESH_HZ)
            for _sample in range(row_samples):
                left = 0
                right = 0
                for channel in range(4):
                    if note[channel] == NOTE_OFF or volume[channel] == 0:
                        continue
                    instrument = instruments[instrument_id[channel]]
                    assert isinstance(instrument, dict)
                    wave_data = instrument["wave"]
                    assert isinstance(wave_data, list)
                    value = (int(wave_data[(phase[channel] >> 28) & 15]) * 2 - 15) * volume[channel] * 32
                    left += value * (4 - channel) // 4
                    right += value * (channel + 1) // 4
                    increment = (_frequency_microhertz(note[channel]) << 32) // (sample_rate * 1_000_000)
                    phase[channel] = (phase[channel] + increment) & 0xFFFFFFFF
                left = max(-32768, min(32767, left))
                right = max(-32768, min(32767, right))
                peak = max(peak, abs(left), abs(right))
                pcm.extend(struct.pack("<hh", left, right))

    stream = io.BytesIO()
    with wave.open(stream, "wb") as destination:
        destination.setnchannels(2)
        destination.setsampwidth(2)
        destination.setframerate(sample_rate)
        destination.writeframes(bytes(pcm))
    wav_payload = stream.getvalue()
    first_left = first_right = last_left = last_right = 0
    if len(pcm) >= 4:
        first_left, first_right = struct.unpack_from("<hh", pcm, 0)
        last_left, last_right = struct.unpack_from("<hh", pcm, len(pcm) - 4)
    loop_seam = max(
        abs(last_left - first_left), abs(last_right - first_right)
    ) / 32768
    metrics = {
        "activeRowsByVoice": active_rows,
        "durationMilliseconds": (len(pcm) // 4) * 1000 // sample_rate,
        "frameCount": len(pcm) // 4,
        "maxPolyphony": max_polyphony,
        "noteEventsByVoice": note_events,
        "channelAllocation": [
            {
                "voice": voice,
                "activeRows": active_rows[voice],
                "noteEvents": note_events[voice],
            }
            for voice in range(4)
        ],
        "instrumentEnvelopes": [
            {
                "instrument": index,
                "attackFrames": int(instrument.get("attack", 0)),
                "releaseFrames": int(instrument.get("release", 0)),
            }
            for index, instrument in enumerate(instruments)
            if isinstance(instrument, Mapping)
        ],
        "loopEnabled": bool(document.get("loop", True)),
        "loopSeamNormalized": round(loop_seam, 9),
        "peakSample": peak,
        "rowCount": len(rows) * loops,
        "sampleRate": sample_rate,
    }
    return wav_payload, metrics


def render_music_preview(source: Path | bytes | Mapping[str, object], *,
                         output: Path | None = None, sample_rate: int = 22050,
                         loops: int = 1, replace: bool = False) -> dict[str, object]:
    """Render an intentionally approximate deterministic authoring WAV."""
    document, source_payload = _music_document(source)
    wav_payload, metrics = _wav_bytes(document, sample_rate=sample_rate, loops=loops)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        mode = "wb" if replace else "xb"
        try:
            with output.open(mode) as destination:
                destination.write(wav_payload)
        except FileExistsError as exc:
            raise AudioWorkbenchError(f"refusing to overwrite audio preview: {output}") from exc
        except OSError as exc:
            raise AudioWorkbenchError(f"could not write audio preview {output}: {exc}") from exc
    return {
        "schema": REPORT_SCHEMA,
        "gameplayEvidence": False,
        "hardwareAccurate": False,
        "sourceSHA256": hashlib.sha256(source_payload).hexdigest(),
        "wavSHA256": hashlib.sha256(wav_payload).hexdigest(),
        "output": str(output) if output is not None else None,
        "metrics": metrics,
        "findings": [
            {
                "severity": "info",
                "code": "authoring-preview-only",
                "message": "Verify timing, panning, envelopes, and channel stealing in SwanSong before acceptance.",
            }
        ],
    }


def simulate_sfx_arbitration(events: Sequence[Mapping[str, object]], *,
                             channels: int = 4) -> dict[str, object]:
    """Explain deterministic priority-based channel selection without playback."""
    _integer(channels, "channels", 1, 4)
    owners: list[dict[str, object] | None] = [None] * channels
    decisions: list[dict[str, object]] = []
    for index, event in enumerate(events):
        event_id = event.get("id")
        if not isinstance(event_id, str) or not event_id:
            raise AudioWorkbenchError(f"event {index} requires a non-empty id")
        priority = _integer(event.get("priority"), f"event {index} priority", 0, 255)
        free = next((channel for channel, owner in enumerate(owners) if owner is None), None)
        stolen: str | None = None
        accepted = True
        if free is None:
            lowest = min(int(owner["priority"]) for owner in owners if owner is not None)
            free = next(
                channel for channel, owner in enumerate(owners)
                if owner is not None and int(owner["priority"]) == lowest
            )
            if priority < lowest:
                accepted = False
            else:
                assert owners[free] is not None
                stolen = str(owners[free]["id"])
        if accepted:
            owners[free] = {"id": event_id, "priority": priority}
        decisions.append({
            "accepted": accepted,
            "channel": free if accepted else None,
            "event": event_id,
            "priority": priority,
            "stolen": stolen,
        })
    return {
        "schema": ARBITRATION_SCHEMA,
        "channels": channels,
        "decisions": decisions,
        "finalOwners": owners,
        "gameplayEvidence": False,
    }
