from __future__ import annotations

import struct
import tempfile
from pathlib import Path
import unittest
import zlib

from swansong_sdk.png2bpp import PNGError, convert_2bpp, read_png


def chunk(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)


def rgba_png(width: int, height: int, pixels: list[tuple[int, int, int, int]]) -> bytes:
    rows = b"".join(b"\0" + bytes(component for color in pixels[y * width:(y + 1) * width] for component in color) for y in range(height))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


class PngTests(unittest.TestCase):
    def test_converts_and_deduplicates_flipped_tiles(self) -> None:
        white, black = (255, 255, 255, 255), (0, 0, 0, 255)
        left_tile = [black if x < y else white for y in range(8) for x in range(8)]
        right_tile = [left_tile[y * 8 + (7 - x)] for y in range(8) for x in range(8)]
        rows = [left_tile[y * 8:(y + 1) * 8] + right_tile[y * 8:(y + 1) * 8] for y in range(8)]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "image.png"
            path.write_bytes(rgba_png(16, 8, [value for row in rows for value in row]))
            result = convert_2bpp(read_png(path), flip_dedupe=True)
            self.assertEqual(result.width_tiles, 2)
            self.assertEqual(len(result.tiles), 1)
            self.assertEqual(result.tilemap, (0, 0x4000))
            self.assertEqual(len(result.tiles[0]), 16)

    def test_rejects_more_than_four_colors(self) -> None:
        colors = [(index * 30, 0, 0, 255) for index in range(5)]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "colors.png"
            path.write_bytes(rgba_png(5, 1, colors))
            with self.assertRaisesRegex(PNGError, "at most four"):
                convert_2bpp(read_png(path))

    def test_rejects_bad_crc(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.png"
            payload = bytearray(rgba_png(1, 1, [(0, 0, 0, 255)]))
            payload[-1] ^= 1
            path.write_bytes(payload)
            with self.assertRaisesRegex(PNGError, "CRC"):
                read_png(path)

    def test_rejects_truncated_chunk_without_struct_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "truncated.png"
            path.write_bytes(b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR")
            with self.assertRaisesRegex(PNGError, "truncated PNG chunk"):
                read_png(path)


if __name__ == "__main__":
    unittest.main()
