from __future__ import annotations

import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from capplus_inspect.errors import InspectError
from capplus_inspect.images import decode_indexed_images, export_indexed_images
from capplus_inspect.palette import inspect_palette, parse_palette
from capplus_inspect.png_writer import PNG_SIGNATURE, encode_indexed_png

from .helpers import make_named_container, make_palette


def png_chunks(data: bytes) -> list[tuple[bytes, bytes]]:
    if not data.startswith(PNG_SIGNATURE):
        raise AssertionError("not a PNG")
    result = []
    offset = len(PNG_SIGNATURE)
    while offset < len(data):
        size = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + size]
        result.append((kind, payload))
        offset += 12 + size
    return result


class PaletteTests(unittest.TestCase):
    def test_palette_header_and_colors(self) -> None:
        data = make_palette()
        result = inspect_palette(data)
        self.assertEqual(result["color_count"], 256)
        self.assertEqual(result["header_word_1"], 0x12345678)
        self.assertEqual(parse_palette(data)[7], (7, 248, 21))


class PngTests(unittest.TestCase):
    def test_encodes_scaled_indexed_png_with_transparency(self) -> None:
        data = encode_indexed_png(
            2,
            1,
            bytes((1, 2)),
            parse_palette(make_palette()),
            transparent_index=2,
            scale=2,
        )
        chunks = png_chunks(data)
        ihdr = next(payload for kind, payload in chunks if kind == b"IHDR")
        self.assertEqual(struct.unpack_from(">II", ihdr), (4, 2))
        transparency = next(payload for kind, payload in chunks if kind == b"tRNS")
        self.assertEqual(transparency, b"\xff\xff\0")
        compressed = b"".join(payload for kind, payload in chunks if kind == b"IDAT")
        self.assertEqual(zlib.decompress(compressed), b"\0\x01\x01\x02\x02" * 2)


class ImageExportTests(unittest.TestCase):
    def test_decodes_named_images_and_skips_non_images(self) -> None:
        image = struct.pack("<HH", 2, 2) + bytes((1, 2, 3, 4))
        kind, images = decode_indexed_images(
            make_named_container([("META", b"opaque"), ("ICON", image)])
        )
        self.assertEqual(kind, "named_container")
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0]["name"], "ICON")

    def test_exports_png_and_manifest_without_overwrite(self) -> None:
        image = struct.pack("<HH", 2, 2) + bytes((1, 2, 3, 4))
        data = make_named_container([("ICON", image)])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "sprites"
            result = export_indexed_images(
                data,
                make_palette(),
                output,
                source_name="synthetic.res",
                palette_name="synthetic.pal",
            )
            manifest = json.loads((output / "manifest.json").read_text())
            exported = output / "000_ICON.png"
            self.assertTrue(exported.is_file())
            self.assertEqual(result["image_count"], 1)
            self.assertEqual(manifest["images"][0]["output_filename"], exported.name)
            with self.assertRaises(InspectError):
                export_indexed_images(
                    data,
                    make_palette(),
                    output,
                    source_name="synthetic.res",
                    palette_name="synthetic.pal",
                )


if __name__ == "__main__":
    unittest.main()
