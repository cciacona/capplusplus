from __future__ import annotations

from typing import Any

from .containers import inspect_resource
from .plans import inspect_layout_plan
from .support_files import inspect_known_support_file
from .ui_resources import inspect_known_ui_resource


def inspect_auxiliary_file(
    data: bytes,
    filename: str,
    *,
    cursor_image_data: bytes | None = None,
) -> dict[str, Any]:
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
