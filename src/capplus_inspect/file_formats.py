from __future__ import annotations

from typing import Any

from .audio import inspect_known_audio
from .containers import inspect_resource, inspect_set
from .executables import inspect_executable
from .maps import inspect_map
from .plans import inspect_layout_plan
from .saves import inspect_save
from .support_files import inspect_known_support_file
from .ui_resources import inspect_known_ui_resource


def inspect_auxiliary_file(
    data: bytes,
    filename: str,
    *,
    cursor_image_data: bytes | None = None,
) -> dict[str, Any]:
    audio = inspect_known_audio(data, filename)
    if audio is not None:
        return audio
    support = inspect_known_support_file(data, filename)
    if support is not None:
        return support

    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    if name.lower().endswith((".pla", ".plo", ".plp")):
        return inspect_layout_plan(data)

    ui = inspect_known_ui_resource(
        data,
        filename,
        cursor_image_data=cursor_image_data,
    )
    return ui if ui is not None else inspect_resource(data)


def inspect_file_bytes(
    data: bytes,
    filename: str,
    *,
    rows: int = 0,
    include_strings: bool = False,
    minimum_string_length: int = 5,
    cursor_image_data: bytes | None = None,
) -> dict[str, Any]:
    """Route bytes through the same filename-aware parser used by the CLI."""

    normalized = filename.replace("\\", "/")
    basename = normalized.rsplit("/", 1)[-1]
    suffix = "." + basename.rsplit(".", 1)[-1].lower() if "." in basename else ""
    if suffix == ".exe":
        return inspect_executable(
            data,
            include_strings=include_strings,
            minimum_string_length=minimum_string_length,
        )
    if suffix == ".sav":
        return inspect_save(data)
    if suffix == ".set":
        return inspect_set(data, include_rows=rows)
    if suffix == ".map":
        return inspect_map(data)
    return inspect_auxiliary_file(
        data,
        normalized,
        cursor_image_data=cursor_image_data,
    )
