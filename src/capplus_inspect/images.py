from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import SCHEMA_VERSION
from .containers import parse_named_index, parse_offset_index, parse_sequential_images
from .errors import FormatError, InspectError
from .palette import parse_palette
from .png_writer import write_indexed_png, write_new_file
from .util import sha256_bytes, u16


def _decode_payload(
    payload: bytes, *, index: int, name: str | None, offset: int
) -> dict[str, Any] | None:
    if len(payload) < 4:
        return None
    width, height = u16(payload, 0), u16(payload, 2)
    if width == 0 or height == 0 or 4 + width * height != len(payload):
        return None
    return {
        "index": index,
        "name": name,
        "offset": offset,
        "source_size": len(payload),
        "width": width,
        "height": height,
        "pixels": payload[4:],
        "pixel_sha256": sha256_bytes(payload[4:]),
    }


def decode_indexed_images(data: bytes) -> tuple[str, list[dict[str, Any]]]:
    named = parse_named_index(data)
    if named is not None:
        images = []
        for entry in named:
            payload = data[entry["offset"] : entry["offset"] + entry["size"]]
            image = _decode_payload(
                payload,
                index=entry["index"],
                name=entry["name"],
                offset=entry["offset"],
            )
            if image is not None:
                images.append(image)
        if images:
            return "named_container", images

    offset_entries = parse_offset_index(data)
    if offset_entries is not None:
        images = []
        for entry in offset_entries:
            payload = data[entry["offset"] : entry["offset"] + entry["size"]]
            image = _decode_payload(
                payload,
                index=entry["index"],
                name=None,
                offset=entry["offset"],
            )
            if image is not None:
                images.append(image)
        if images:
            return "offset_container", images

    sequential = parse_sequential_images(data)
    if sequential is not None:
        images = []
        for entry in sequential:
            payload_offset = entry["offset"] + 4
            payload = data[payload_offset : payload_offset + entry["record_size"]]
            image = _decode_payload(
                payload,
                index=entry["index"],
                name=None,
                offset=payload_offset,
            )
            if image is None:
                raise FormatError("sequential image passed framing but not payload validation")
            images.append(image)
        return "sequential_images", images

    direct = _decode_payload(data, index=0, name=None, offset=0)
    if direct is not None:
        return "direct_indexed_image", [direct]
    raise FormatError("input contains no supported uncompressed indexed images")


def _safe_stem(name: str | None, index: int, digits: int) -> str:
    prefix = f"{index:0{digits}d}"
    if not name:
        return prefix
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._-")
    return f"{prefix}_{safe or 'image'}"


def export_indexed_images(
    data: bytes,
    palette_data: bytes,
    output_directory: Path,
    *,
    source_name: str,
    palette_name: str,
    transparent_index: int | None = 245,
    scale: int = 1,
    force: bool = False,
) -> dict[str, Any]:
    source_format, images = decode_indexed_images(data)
    palette = parse_palette(palette_data)
    output_directory = output_directory.resolve()
    if output_directory.exists() and not output_directory.is_dir():
        raise InspectError(f"output is not a directory: {output_directory}")

    digits = max(3, len(str(max(image["index"] for image in images))))
    outputs: list[tuple[Path, dict[str, Any]]] = []
    for image in images:
        filename = _safe_stem(image["name"], image["index"], digits) + ".png"
        outputs.append((output_directory / filename, image))
    manifest_path = output_directory / "manifest.json"
    conflicts = [path for path, _ in outputs if path.exists()]
    if manifest_path.exists():
        conflicts.append(manifest_path)
    if conflicts and not force:
        raise InspectError(
            f"{len(conflicts)} output file(s) already exist in {output_directory}; "
            "use --force to replace them"
        )

    output_directory.mkdir(parents=True, exist_ok=True)
    public_images: list[dict[str, Any]] = []
    for path, image in outputs:
        write_indexed_png(
            path,
            image["width"],
            image["height"],
            image["pixels"],
            palette,
            transparent_index=transparent_index,
            scale=scale,
            force=force,
        )
        public_images.append(
            {
                key: value
                for key, value in image.items()
                if key != "pixels"
            }
            | {"output": str(path), "output_filename": path.name}
        )

    result = {
        "schema_version": SCHEMA_VERSION,
        "format": "capitalism_plus_image_export",
        "source": source_name,
        "source_format": source_format,
        "source_sha256": sha256_bytes(data),
        "palette": palette_name,
        "palette_sha256": sha256_bytes(palette_data),
        "transparent_index": transparent_index,
        "scale": scale,
        "image_count": len(public_images),
        "output_directory": str(output_directory),
        "images": public_images,
    }
    manifest = json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"
    write_new_file(manifest_path, manifest, force=force)
    result["manifest"] = str(manifest_path)
    return result
