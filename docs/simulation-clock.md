# Simulation clock and random-number contracts

Cap++ now has exact, dependency-free models for the original calendar clock and
linear-congruential random-number generator (RNG). Both were compared against
isolated routines from the known unmodified DOS and Windows executables. This is
not yet a complete game loop or proof of economic-simulation parity.

Run the private exact-build survey with executables from your own copy:

```bash
PYTHONPATH=src:/path/to/unicorn-2.1.4 \
  python3 scripts/simulation_survey.py \
  --dos-exe /path/to/CAPPLUS.EXE \
  --windows-exe /path/to/CapWin.exe \
  --output /private/path/simulation-survey.json
```

The script verifies exact executable SHA-256 before importing its optional
Unicorn 2.1.4 research dependency. It executes only audited ranges, replaces
calendar conversion and subsystem callbacks with explicit deterministic stubs,
and emits scalar values and synthetic state—not executable bytes or decompiler
output. `capplus-inspect` itself remains dependency-free.

## State topology

The original builds have two independent `Misc` objects. The simulation object
is serialized in save section `1001`; the presentation object is used by
presentation/music/effect paths and has a separate time-seed call.

| State or routine | Windows | DOS |
|---|---:|---:|
| Saved simulation RNG object | `0x004A4948` | DS-relative `0x0000F710` |
| Presentation RNG object | `0x004A6180` | DS-relative `0x0000F78D` |
| RNG state within either object | `+0x79` | `+0x79` |
| Bounded RNG routine | `0x0047C560` | `0x000907A3` |
| Time-seed routine | `0x0047C530` | `0x00090772` |
| Save RNG writer | `0x00446CF0` | `0x0001E99A` |
| Save RNG reader | `0x00446D10` | `0x0001E9BC` |
| Saved clock object | `0x004A7850` | DS-relative `0x0001255C` |
| Daily clock routine | `0x00476FA0` | `0x0002755A` |
| Per-loop counter routine | `0x00476F80` | `0x00027530` |
| Month routine | `0x00477060` | `0x0002762F` |
| Year routine | `0x00477120` | `0x000276F8` |
| Playing-time formatter | `0x00477250` | `0x00027839` |
| Clock save writer / reader | `0x00446E10` / `0x00446E20` | `0x0001EAC2` / `0x0001EADD` |

DOS data addresses are logical offsets through a data selector whose base is
`0xA0000`; they are not flat process addresses. Addresses apply only to the
exact executable identities in the [executable survey](executables.md#build-identities).

## Random-number generator

For each call, unsigned 32-bit arithmetic wraps naturally:

```text
state = state * 0x015A4E35 + 1
raw = (state >> 16) & 0x7FFF
random(maximum) = (raw * maximum) >> 15
```

The accepted `maximum` range is `0..32767`, inclusive. A zero maximum returns
zero but still advances the state. `rng_next` and `rng_bounded` implement these
contracts without process-global state, so a future simulation can own and
serialize its RNG stream explicitly.

Six seeds were tested through the same sequence of eight bounds in both builds.
All 96 returned integers and all twelve final states matched the model exactly.
The committed synthetic golden vectors are in
[`tests/fixtures/simulation-v1.json`](../tests/fixtures/simulation-v1.json).

## Saved clock record (`1005`)

Section `1005` is a 67-byte payload: a little-endian `u16` compatible-record
size of 65, followed by the complete 65-byte clock object. The three supplied
saves use size 65 and have calendar fields consistent with the date in their
metadata record.

| Record offset | Type | Confirmed behavior |
|---:|---|---|
| `0x00` | `u32` | Initial date, Julian day number |
| `0x04` | `u32` | Current date, Julian day number |
| `0x08` | `u32` | Calendar day, capped at 30 and reset to 1 on a month change |
| `0x0C` | `u32` | Gregorian month |
| `0x10` | `u32` | Gregorian year |
| `0x14` | `u32` | Weekday, `current_jdn % 7`; 0 is Monday |
| `0x18` | `u32` | Years elapsed; incremented on a year change |
| `0x1C` | `u32` | Last wall-clock sample |
| `0x20` | `u32` | Accumulated playing seconds |
| `0x24` | `u32` | Daily counter modulo 30 |
| `0x28` | `u32` | Monthly counter modulo 30 |
| `0x2C` | `u32` | Yearly counter modulo 30 |
| `0x30` | `u32` | Yearly counter modulo 10 |
| `0x34` | `u32` | Monthly counter modulo 6 |
| `0x38` | `u32` | Monthly counter modulo 12 |
| `0x3C` | `u32` | Main-loop counter; dispatches event 11 and resets at 10 |
| `0x40` | `u8` | Deferred event flag; deeper mode semantics remain unassigned |

Cadence and wrap values are confirmed. The economic meanings of the six
periodic counters are not: neutral cadence-based names deliberately avoid
turning call-frequency evidence into a gameplay claim. Wall-clock fields are
presentation/transient state and are not advanced by the calendar model.

## Daily transition contract

The daily routine performs these clock-local operations in order:

1. Increment the calendar-day field, capped at 30.
2. Increment current JDN and store `JDN % 7` as the weekday.
3. Increment the daily modulo-30 counter.
4. If the Gregorian month changed, reset the calendar day to 1, store the month,
   update the three monthly counters, then invoke monthly subsystem callbacks.
5. If the Gregorian year changed, store month 1 and the new year, increment
   years elapsed, update the two yearly counters, then invoke yearly callbacks.
6. Dispatch daily event 11.

The separate per-loop routine increments only offset `0x3C`; at ten it resets
that counter and dispatches event 11. A loop iteration is therefore not a game
day, and the two APIs remain separate in the replacement model.

## Exact-build comparison

The deterministic survey used three fixed-duration cases per build:

| Case | Start | Days | End | Month callbacks | Year callbacks |
|---|---|---:|---|---:|---:|
| Day cap and month boundary | 1990-01-29 | 4 | 1990-02-02 | 1 | 0 |
| Leap day | 1992-02-27 | 3 | 1992-03-01 | 1 | 0 |
| Year and counter wraps | 1990-12-30 | 3 | 1991-01-02 | 1 | 1 |

Both builds matched every one of the 65 final bytes and every callback count.
A separate 25-iteration loop probe starting at counter 9 ended at 4 and emitted
three event-11 callbacks in both builds. RNG integers, calendar integers,
callback counts and complete clock-state bytes all use tolerance zero. No float
tolerance applies to these contracts.

Calendar conversion and downstream subsystem work were stubbed intentionally.
The test establishes the clock's sequencing and boundary calls; it does not
claim that monthly or yearly economic updates have been reconstructed.

## Presentation RNG isolation

Windows music selector `0x00410290` time-seeds the presentation object,
requests `random(8)`, adds one, then passes selection 1–8 to the CD wrapper. An
isolated selector run with a fixed wall-clock seed produced the modeled
selection and presentation state while a sentinel in the saved simulation RNG
remained byte-exact.

DOS has the same separate presentation object and its sole time-seed call site
at `0x00011158` passes that object. The deterministic time-seed-plus-`random(8)`
pipeline also left the saved simulation object unchanged. Direct reachability
of the contained DOS CD selector remains unresolved and belongs to the broader
[audio investigation](audio.md#static-playback-contracts).

Consequently, music selection cannot alter the RNG serialized in section
`1001` through these paths. Whole-game music on/off captures are no longer
needed to distinguish the two objects, although runtime audio reachability and
playlist behavior still require testing.

## Playing-time display quirk

Both original formatters accumulate wall-clock seconds at offset `0x20`, then
compute:

```text
hours = seconds // 3720
minutes = (seconds // 62) % 60
```

The displayed minute is therefore 62 seconds and the displayed hour is 3,720
seconds. This likely-original defect is recorded in the
[compatibility-quirks ledger](compatibility-quirks.md): Classic preserves the
display conversion, while Extended may show conventional 60-second minutes.
Canonical saved time remains seconds in either profile.

## Remaining boundary

The following are still open:

- map the periodic clock counters to the subsystem operations they schedule;
- recover pause/speed-to-day scheduling around the daily routine;
- identify every caller's ownership of the saved simulation RNG stream;
- validate the future native engine over long, command-driven save checkpoints;
- resolve DOS music-selector reachability and complete audio trigger behavior.

Those tasks must not be described as complete merely because clock-local
functions now match.
