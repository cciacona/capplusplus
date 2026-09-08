from __future__ import annotations

import contextlib
from dataclasses import replace
from datetime import date
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from capplus_inspect.errors import FormatError, InspectError
from capplus_inspect.known import DOS_EXECUTABLE_SHA256, WINDOWS_EXECUTABLE_SHA256
from capplus_inspect.simulation import (
    CLOCK_RECORD_SIZE,
    RNG_MAXIMUM,
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
from scripts.simulation_survey import (
    PROFILES,
    OriginalSimulationOracle,
    main as survey_main,
    read_bounded,
    survey,
)


GOLDENS = json.loads(
    (Path(__file__).parent / "fixtures/simulation-v1.json").read_text(encoding="utf-8")
)


class RandomContractTests(unittest.TestCase):
    def test_recovered_lcg_golden_sequence(self) -> None:
        state = 0x12345678
        outputs = []
        for maximum in (0, 1, 8, 100, 32767, 8, 8, 8):
            state, value = rng_bounded(state, maximum)
            outputs.append(value)
        self.assertEqual(state, 0xDA029030)
        self.assertEqual(outputs, [0, 0, 3, 24, 18878, 6, 4, 5])

    def test_zero_bound_still_advances_and_raw_bits_match(self) -> None:
        next_state, raw = rng_next(0)
        bounded_state, bounded = rng_bounded(0, 0)
        self.assertEqual(next_state, 0x00000001)
        self.assertEqual(raw, 0)
        self.assertEqual(bounded_state, next_state)
        self.assertEqual(bounded, 0)

    def test_rng_bounds_and_types_fail_closed(self) -> None:
        for state in (-1, 0x100000000, True, "0"):
            with self.subTest(state=state), self.assertRaises(FormatError):
                rng_next(state)  # type: ignore[arg-type]
        for maximum in (-1, RNG_MAXIMUM + 1, True, "8"):
            with self.subTest(maximum=maximum), self.assertRaises(FormatError):
                rng_bounded(0, maximum)  # type: ignore[arg-type]

    def test_all_original_function_golden_vectors(self) -> None:
        self.assertTrue(GOLDENS["original_builds_match"])
        self.assertEqual(GOLDENS["integer_tolerance"], 0)
        for vector in GOLDENS["rng_vectors"]:
            state = int(vector["initial_state"], 16)
            values = []
            for maximum in vector["maxima"]:
                state, value = rng_bounded(state, maximum)
                values.append(value)
            with self.subTest(seed=vector["initial_state"]):
                self.assertEqual(values, vector["values"])
                self.assertEqual(state, int(vector["final_state"], 16))


class ClockContractTests(unittest.TestCase):
    def test_clock_record_round_trip_and_calendar_decode(self) -> None:
        state = clock_state_for_date(
            date(1991, 3, 1),
            initial_date=date(1990, 1, 1),
            counters=(28, 14, 1, 1, 2, 2, 0),
            last_wallclock_sample=123,
            accumulated_playing_seconds=1147,
        )
        raw = state.to_bytes()
        self.assertEqual(len(raw), CLOCK_RECORD_SIZE)
        self.assertEqual(ClockState.from_bytes(raw), state)
        decoded = decode_clock_state(state)
        self.assertEqual(decoded["initial_date"], "1990-01-01")
        self.assertEqual(decoded["current_date"], "1991-03-01")
        self.assertEqual(decoded["weekday"], "Friday")
        self.assertEqual(decoded["years_elapsed"], 1)
        self.assertTrue(decoded["calendar_consistent"])

    def test_day_month_year_order_caps_day_and_wraps_counters(self) -> None:
        state = clock_state_for_date(
            date(1990, 12, 31),
            initial_date=date(1990, 1, 1),
            counters=(29, 29, 29, 9, 5, 11, 9),
        )
        advanced, callbacks = advance_clock_day(state)
        self.assertEqual(callbacks, ("month", "year", "day"))
        self.assertEqual(advanced.current_date_jdn, state.current_date_jdn + 1)
        self.assertEqual((advanced.day_counter, advanced.month, advanced.year), (1, 1, 1991))
        self.assertEqual(advanced.weekday_index, advanced.current_date_jdn % 7)
        self.assertEqual(advanced.years_elapsed, 1)
        self.assertEqual(
            (
                advanced.day_30_counter,
                advanced.month_30_counter,
                advanced.year_30_counter,
                advanced.year_10_counter,
                advanced.month_6_counter,
                advanced.month_12_counter,
            ),
            (0, 0, 0, 0, 0, 0),
        )

    def test_leap_day_and_fixed_duration_callbacks(self) -> None:
        state = clock_state_for_date(
            date(1992, 2, 27), initial_date=date(1990, 1, 1)
        )
        final, callbacks = advance_clock_days(state, 3)
        self.assertEqual(decode_clock_state(final)["current_date"], "1992-03-01")
        self.assertEqual(final.day_counter, 1)
        self.assertEqual(callbacks, {"day": 3, "month": 1, "year": 0})

    def test_calendar_day_caps_at_30_until_next_month(self) -> None:
        state = clock_state_for_date(date(1990, 1, 29))
        values = []
        for _ in range(3):
            state, _ = advance_clock_day(state)
            values.append(state.day_counter)
        self.assertEqual(values, [30, 30, 1])
        self.assertEqual(decode_clock_state(state)["current_date"], "1990-02-01")

    def test_loop_counter_is_independent_and_dispatches_every_ten(self) -> None:
        state = clock_state_for_date(
            date(1990, 1, 1), counters=(0, 0, 0, 0, 0, 0, 9)
        )
        final, dispatches = advance_clock_loops(state, 25)
        self.assertEqual(final.loop_10_counter, 4)
        self.assertEqual(dispatches, 3)
        self.assertEqual(final.current_date_jdn, state.current_date_jdn)

    def test_original_playing_time_conversion_preserves_62_second_quirk(self) -> None:
        self.assertEqual(original_playing_time_display(61), (0, 0))
        self.assertEqual(original_playing_time_display(62), (0, 1))
        self.assertEqual(original_playing_time_display(3719), (0, 59))
        self.assertEqual(original_playing_time_display(3720), (1, 0))

    def test_malformed_states_and_counts_fail_closed(self) -> None:
        with self.assertRaises(FormatError):
            ClockState.from_bytes(bytes(CLOCK_RECORD_SIZE - 1))
        coherent = clock_state_for_date(date(1990, 1, 1))
        with self.assertRaisesRegex(FormatError, "calendar-consistent"):
            advance_clock_day(replace(coherent, month=2))
        with self.assertRaisesRegex(FormatError, "loop_10_counter"):
            advance_clock_loops(replace(coherent, loop_10_counter=10))
        for count in (-1, 1_000_001, True, "1"):
            with self.subTest(count=count), self.assertRaises(FormatError):
                advance_clock_days(coherent, count)  # type: ignore[arg-type]

    def test_all_original_function_clock_golden_vectors(self) -> None:
        for vector in GOLDENS["clock_vectors"]:
            initial = clock_state_for_date(
                date.fromisoformat(vector["initial_date"]),
                initial_date=date.fromisoformat(vector["initial_epoch"]),
                counters=tuple(vector["initial_counters"]),
            )
            final, callbacks = advance_clock_days(initial, vector["duration_days"])
            decoded = decode_clock_state(final)
            counters = [
                final.day_30_counter,
                final.month_30_counter,
                final.year_30_counter,
                final.year_10_counter,
                final.month_6_counter,
                final.month_12_counter,
                final.loop_10_counter,
            ]
            with self.subTest(name=vector["name"]):
                self.assertEqual(decoded["current_date"], vector["final_date"])
                self.assertEqual(counters, vector["final_counters"])
                self.assertEqual(callbacks, vector["callbacks"])

        loop = GOLDENS["loop_vector"]
        initial = clock_state_for_date(
            date(1990, 1, 1),
            counters=(0, 0, 0, 0, 0, 0, loop["initial_counter"]),
        )
        final, dispatches = advance_clock_loops(initial, loop["iterations"])
        self.assertEqual(final.loop_10_counter, loop["final_counter"])
        self.assertEqual(dispatches, loop["event_11_dispatches"])

    def test_original_playing_time_golden_vectors(self) -> None:
        for vector in GOLDENS["playing_time_display"]:
            self.assertEqual(
                list(original_playing_time_display(vector["seconds"])),
                vector["display"],
            )


class SimulationSurveyTests(unittest.TestCase):
    def test_golden_fixture_names_both_exact_builds(self) -> None:
        self.assertEqual(
            GOLDENS["executable_sha256"],
            {
                "dos": DOS_EXECUTABLE_SHA256,
                "windows": WINDOWS_EXECUTABLE_SHA256,
            },
        )

    def test_unknown_executables_are_rejected_before_optional_import(self) -> None:
        with patch.dict("sys.modules", {"unicorn": None}):
            for build in ("dos", "windows", "other"):
                with self.subTest(build=build), self.assertRaisesRegex(
                    InspectError, "exact unmodified"
                ):
                    OriginalSimulationOracle(b"synthetic", build)

    def test_profiles_keep_simulation_and_presentation_rng_objects_distinct(self) -> None:
        for build, profile in PROFILES.items():
            with self.subTest(build=build):
                self.assertNotEqual(
                    profile["simulation_rng_object"],
                    profile["presentation_rng_object"],
                )
        isolation = GOLDENS["presentation_rng_isolation"]
        self.assertEqual(
            isolation["simulation_initial_state"], isolation["simulation_final_state"]
        )
        expected_state, value = rng_bounded(
            int(isolation["fixed_wallclock_seed"], 16), 8
        )
        self.assertEqual(expected_state, int(isolation["presentation_final_state"], 16))
        self.assertEqual(value + 1, isolation["selection"])

    def test_survey_rejects_missing_build_before_emulation(self) -> None:
        with self.assertRaisesRegex(InspectError, "both DOS and Windows"):
            survey({"dos": b""})

    def test_bounded_read_and_existing_output_protection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bounded = root / "bounded"
            bounded.write_bytes(bytes(9))
            self.assertEqual(read_bounded(bounded, 9), bytes(9))
            with self.assertRaises(InspectError):
                read_bounded(bounded, 8)
            output = root / "report.json"
            output.write_text("keep", encoding="utf-8")
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(
                SystemExit
            ) as error:
                survey_main(
                    [
                        "--dos-exe",
                        "missing",
                        "--windows-exe",
                        "missing",
                        "--output",
                        str(output),
                    ]
                )
            self.assertEqual(error.exception.code, 2)
            self.assertEqual(output.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
