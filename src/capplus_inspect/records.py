from __future__ import annotations

from .errors import FormatError
from .util import require_range, u16


def read_compatible_record(
    data: bytes,
    offset: int,
    *,
    expected_size: int | None = None,
    limit: int | None = None,
) -> tuple[bytes, int, int]:
    """Read the original engine's size-prefixed compatibility record.

    A zero prefix means the caller's expected size. A smaller stored record is
    zero-extended, while a larger stored record is clipped and skipped so the
    next record remains aligned. The returned tuple is payload, next offset,
    and the size value that was physically stored in the prefix.
    """

    saved_size = u16(data, offset)
    stored_size = expected_size if saved_size == 0 else saved_size
    if stored_size is None:
        raise FormatError(
            "zero-sized record prefix requires an expected size", offset=offset
        )

    start = offset + 2
    end = start + stored_size
    if limit is not None and end > limit:
        raise FormatError("framed record crosses its section boundary", offset=offset)
    require_range(data, start, stored_size, "framed record")

    logical_size = stored_size if expected_size is None else expected_size
    copied_size = min(stored_size, logical_size)
    payload = data[start : start + copied_size]
    if copied_size < logical_size:
        payload += bytes(logical_size - copied_size)
    return payload, end, saved_size
