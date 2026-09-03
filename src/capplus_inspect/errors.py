class InspectError(Exception):
    """Base class for expected inspection failures."""


class FormatError(InspectError):
    """Raised when input does not satisfy a supported binary format."""

    def __init__(self, message: str, *, offset: int | None = None) -> None:
        self.offset = offset
        suffix = f" at 0x{offset:X}" if offset is not None else ""
        super().__init__(f"{message}{suffix}")

