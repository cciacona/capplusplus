"""Deterministic clock and random-number contracts recovered from both builds."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
import struct
from typing import Any

from .errors import FormatError


RNG_MULTIPLIER = 0x015A4E35
RNG_INCREMENT = 1
RNG_MAXIMUM = 0x7FFF
RNG_MODEL_VERSION = 1

CLOCK_RECORD_SIZE = 65
CLOCK_MODEL_VERSION = 1
MAX_CLOCK_ADVANCE_DAYS = 1_000_000
_JDN_ORDINAL_OFFSET = 1_721_425
_CLOCK_STRUCT = struct.Struct("<16IB")
_WEEKDAYS = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)


def _u32(value: int, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFFFFFFFF:
        raise FormatError(f"{label} must be an unsigned 32-bit integer")


def rng_next(state: int) -> tuple[int, int]:
    """Advance one original LCG state and return its 15-bit output."""

    _u32(state, "RNG state")
    state = (state * RNG_MULTIPLIER + RNG_INCREMENT) & 0xFFFFFFFF
    return state, (state >> 16) & RNG_MAXIMUM


def rng_bounded(state: int, maximum: int) -> tuple[int, int]:
    """Match ``Misc::random(maximum)`` for an inclusive valid bound range."""

    if (
        isinstance(maximum, bool)
        or not isinstance(maximum, int)
        or not 0 <= maximum <= RNG_MAXIMUM
    ):
        raise FormatError(f"RNG maximum must be between 0 and {RNG_MAXIMUM}")
    state, raw = rng_next(state)
    return state, (raw * maximum) >> 15


@dataclass(frozen=True)
class ClockState:
    """The 65-byte state saved in version-100 section ``1005``.

    Counter names describe their proven update cadence and wrap value. They do
    not assign unverified economic meanings to those counters.
    """

    initial_date_jdn: int
    current_date_jdn: int
    day_counter: int
    month: int
    year: int
    weekday_index: int
    years_elapsed: int
    last_wallclock_sample: int
    accumulated_playing_seconds: int
    day_30_counter: int
    month_30_counter: int
    year_30_counter: int
    year_10_counter: int
    month_6_counter: int
    month_12_counter: int
    loop_10_counter: int
    deferred_event_flag: int

    @classmethod
    def from_bytes(cls, data: bytes | bytearray | memoryview) -> "ClockState":
        if len(data) != CLOCK_RECORD_SIZE:
            raise FormatError(
                f"clock state must contain exactly {CLOCK_RECORD_SIZE} bytes"
            )
        return cls(*_CLOCK_STRUCT.unpack(bytes(data)))

    def _dwords(self) -> tuple[int, ...]:
        return (
            self.initial_date_jdn,
            self.current_date_jdn,
            self.day_counter,
            self.month,
            self.year,
            self.weekday_index,
            self.years_elapsed,
            self.last_wallclock_sample,
            self.accumulated_playing_seconds,
            self.day_30_counter,
            self.month_30_counter,
            self.year_30_counter,
            self.year_10_counter,
            self.month_6_counter,
            self.month_12_counter,
            self.loop_10_counter,
        )

    def to_bytes(self) -> bytes:
        values = self._dwords()
        labels = (
            "initial_date_jdn",
            "current_date_jdn",
            "day_counter",
            "month",
            "year",
            "weekday_index",
            "years_elapsed",
            "last_wallclock_sample",
            "accumulated_playing_seconds",
            "day_30_counter",
            "month_30_counter",
            "year_30_counter",
            "year_10_counter",
            "month_6_counter",
            "month_12_counter",
            "loop_10_counter",
        )
        for label, value in zip(labels, values):
            _u32(value, label)
        if (
            isinstance(self.deferred_event_flag, bool)
            or not isinstance(self.deferred_event_flag, int)
            or not 0 <= self.deferred_event_flag <= 0xFF
        ):
            raise FormatError("deferred_event_flag must be an unsigned byte")
        return _CLOCK_STRUCT.pack(*values, self.deferred_event_flag)


def _date_from_jdn(value: int, label: str) -> date:
    _u32(value, label)
    try:
        return date.fromordinal(value - _JDN_ORDINAL_OFFSET)
    except (ValueError, OverflowError) as error:
        raise FormatError(f"{label} is outside the supported Gregorian range") from error


def clock_state_for_date(
    value: date,
    *,
    initial_date: date | None = None,
    years_elapsed: int | None = None,
    counters: tuple[int, int, int, int, int, int, int] = (0, 0, 0, 0, 0, 0, 0),
    last_wallclock_sample: int = 0,
    accumulated_playing_seconds: int = 0,
    deferred_event_flag: int = 0,
) -> ClockState:
    """Create a coherent synthetic state for parity probes."""

    if not isinstance(value, date) or (
        initial_date is not None and not isinstance(initial_date, date)
    ):
        raise FormatError("clock dates must be datetime.date values")
    if not isinstance(counters, tuple) or len(counters) != 7:
        raise FormatError("clock counters must be a seven-integer tuple")
    for label, item in zip(
        (
            "day_30_counter",
            "month_30_counter",
            "year_30_counter",
            "year_10_counter",
            "month_6_counter",
            "month_12_counter",
            "loop_10_counter",
        ),
        counters,
    ):
        _u32(item, label)
    initial = initial_date or value
    if initial > value:
        raise FormatError("initial clock date cannot follow the current date")
    if years_elapsed is None:
        years_elapsed = value.year - initial.year
    for label, item in (
        ("years_elapsed", years_elapsed),
        ("last_wallclock_sample", last_wallclock_sample),
        ("accumulated_playing_seconds", accumulated_playing_seconds),
    ):
        _u32(item, label)
    initial_jdn = initial.toordinal() + _JDN_ORDINAL_OFFSET
    current_jdn = value.toordinal() + _JDN_ORDINAL_OFFSET
    state = ClockState(
        initial_jdn,
        current_jdn,
        min(value.day, 30),
        value.month,
        value.year,
        current_jdn % 7,
        years_elapsed,
        last_wallclock_sample,
        accumulated_playing_seconds,
        *counters,
        deferred_event_flag,
    )
    _validate_running_clock(state)
    return state


def _validate_running_clock(state: ClockState) -> None:
    """Reject states outside the invariants produced by the original clock."""

    state.to_bytes()
    decoded = decode_clock_state(state)
    if not decoded["calendar_consistent"]:
        raise FormatError("clock state is not calendar-consistent")
    ranges = (
        ("day_counter", state.day_counter, 1, 30),
        ("weekday_index", state.weekday_index, 0, 6),
        ("day_30_counter", state.day_30_counter, 0, 29),
        ("month_30_counter", state.month_30_counter, 0, 29),
        ("year_30_counter", state.year_30_counter, 0, 29),
        ("year_10_counter", state.year_10_counter, 0, 9),
        ("month_6_counter", state.month_6_counter, 0, 5),
        ("month_12_counter", state.month_12_counter, 0, 11),
        ("loop_10_counter", state.loop_10_counter, 0, 9),
    )
    for label, value, minimum, maximum in ranges:
        if not minimum <= value <= maximum:
            raise FormatError(f"{label} must be between {minimum} and {maximum}")


def decode_clock_state(state: ClockState) -> dict[str, Any]:
    """Return a JSON-ready interpretation while retaining all saved fields."""

    if not isinstance(state, ClockState):
        raise FormatError("clock state must be a ClockState")
    try:
        initial = _date_from_jdn(state.initial_date_jdn, "initial clock date")
    except FormatError:
        initial = None
    try:
        current = _date_from_jdn(state.current_date_jdn, "current clock date")
    except FormatError:
        current = None
    expected_day = min(current.day, 30) if current else None
    expected_weekday = state.current_date_jdn % 7 if current else None
    checks = {
        "day_counter": expected_day is not None and state.day_counter == expected_day,
        "month": current is not None and state.month == current.month,
        "year": current is not None and state.year == current.year,
        "weekday_index": expected_weekday is not None
        and state.weekday_index == expected_weekday,
    }
    return {
        "model_version": CLOCK_MODEL_VERSION,
        "initial_date_jdn": state.initial_date_jdn,
        "initial_date": initial.isoformat() if initial else None,
        "current_date_jdn": state.current_date_jdn,
        "current_date": current.isoformat() if current else None,
        "day_counter": state.day_counter,
        "day_counter_caps_calendar_day_at_30": True,
        "month": state.month,
        "year": state.year,
        "weekday_index": state.weekday_index,
        "weekday": (
            _WEEKDAYS[state.weekday_index]
            if 0 <= state.weekday_index < len(_WEEKDAYS)
            else None
        ),
        "years_elapsed": state.years_elapsed,
        "last_wallclock_sample": state.last_wallclock_sample,
        "accumulated_playing_seconds": state.accumulated_playing_seconds,
        "day_30_counter": state.day_30_counter,
        "month_30_counter": state.month_30_counter,
        "year_30_counter": state.year_30_counter,
        "year_10_counter": state.year_10_counter,
        "month_6_counter": state.month_6_counter,
        "month_12_counter": state.month_12_counter,
        "loop_10_counter": state.loop_10_counter,
        "deferred_event_flag": state.deferred_event_flag,
        "calendar_checks": checks,
        "calendar_consistent": all(checks.values()),
    }


def advance_clock_day(state: ClockState) -> tuple[ClockState, tuple[str, ...]]:
    """Advance one original game day and report ordered calendar callbacks."""

    if not isinstance(state, ClockState):
        raise FormatError("clock state must be a ClockState")
    _validate_running_clock(state)
    current = _date_from_jdn(state.current_date_jdn, "current clock date")
    try:
        following = date.fromordinal(current.toordinal() + 1)
    except (ValueError, OverflowError) as error:
        raise FormatError("clock cannot advance past the supported Gregorian range") from error

    next_jdn = state.current_date_jdn + 1
    day_counter = min(state.day_counter + 1, 30)
    day_30 = (state.day_30_counter + 1) % 30
    month_30 = state.month_30_counter
    year_30 = state.year_30_counter
    year_10 = state.year_10_counter
    month_6 = state.month_6_counter
    month_12 = state.month_12_counter
    years_elapsed = state.years_elapsed
    callbacks: list[str] = []

    if following.month != state.month:
        day_counter = 1
        month_30 = (month_30 + 1) % 30
        month_6 = (month_6 + 1) % 6
        month_12 = (month_12 + 1) % 12
        callbacks.append("month")
    if following.year != state.year:
        years_elapsed = (years_elapsed + 1) & 0xFFFFFFFF
        year_30 = (year_30 + 1) % 30
        year_10 = (year_10 + 1) % 10
        callbacks.append("year")
    callbacks.append("day")

    return (
        replace(
            state,
            current_date_jdn=next_jdn,
            day_counter=day_counter,
            month=following.month,
            year=following.year,
            weekday_index=next_jdn % 7,
            years_elapsed=years_elapsed,
            day_30_counter=day_30,
            month_30_counter=month_30,
            year_30_counter=year_30,
            year_10_counter=year_10,
            month_6_counter=month_6,
            month_12_counter=month_12,
        ),
        tuple(callbacks),
    )


def advance_clock_days(state: ClockState, count: int) -> tuple[ClockState, dict[str, int]]:
    """Run a bounded fixed-duration clock probe."""

    if not isinstance(state, ClockState):
        raise FormatError("clock state must be a ClockState")
    _validate_running_clock(state)
    if (
        isinstance(count, bool)
        or not isinstance(count, int)
        or not 0 <= count <= MAX_CLOCK_ADVANCE_DAYS
    ):
        raise FormatError(
            f"clock day count must be between 0 and {MAX_CLOCK_ADVANCE_DAYS}"
        )
    callback_counts = {"day": 0, "month": 0, "year": 0}
    for _ in range(count):
        state, callbacks = advance_clock_day(state)
        for callback in callbacks:
            callback_counts[callback] += 1
    return state, callback_counts


def advance_clock_loops(state: ClockState, count: int = 1) -> tuple[ClockState, int]:
    """Advance the separately saved per-loop counter and count event-11 dispatches."""

    if not isinstance(state, ClockState):
        raise FormatError("clock state must be a ClockState")
    _validate_running_clock(state)
    if (
        isinstance(count, bool)
        or not isinstance(count, int)
        or not 0 <= count <= MAX_CLOCK_ADVANCE_DAYS
    ):
        raise FormatError(
            f"clock loop count must be between 0 and {MAX_CLOCK_ADVANCE_DAYS}"
        )
    counter = state.loop_10_counter
    dispatches = 0
    for _ in range(count):
        counter += 1
        if counter >= 10:
            counter = 0
            dispatches += 1
    return replace(state, loop_10_counter=counter), dispatches


def original_playing_time_display(total_seconds: int) -> tuple[int, int]:
    """Return original displayed hours/minutes, including its 62-second minute."""

    _u32(total_seconds, "playing time")
    return total_seconds // (62 * 60), (total_seconds // 62) % 60
