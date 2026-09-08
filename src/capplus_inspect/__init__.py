"""Non-destructive Capitalism Plus data inspection and export."""

__version__ = "0.2.0"
SCHEMA_VERSION = 1

from .containers import inspect_resource, inspect_set
from .images import export_indexed_images
from .installation import inspect_installation
from .maps import inspect_map, render_map
from .palette import inspect_palette
from .roundtrip import validate_roundtrip_bytes, validate_roundtrip_corpus
from .schema_catalog import load_format_catalog
from .saves import compare_saves, inspect_save, save_normalization_policy
from .simulation import (
    ClockState,
    advance_clock_day,
    advance_clock_days,
    advance_clock_loops,
    clock_state_for_date,
    decode_clock_state,
    original_playing_time_display,
    rng_bounded,
    rng_next,
)

__all__ = [
    "compare_saves",
    "ClockState",
    "advance_clock_day",
    "advance_clock_days",
    "advance_clock_loops",
    "clock_state_for_date",
    "decode_clock_state",
    "export_indexed_images",
    "inspect_installation",
    "inspect_map",
    "inspect_palette",
    "inspect_resource",
    "inspect_save",
    "inspect_set",
    "load_format_catalog",
    "render_map",
    "rng_bounded",
    "rng_next",
    "original_playing_time_display",
    "save_normalization_policy",
    "validate_roundtrip_bytes",
    "validate_roundtrip_corpus",
    "SCHEMA_VERSION",
]
