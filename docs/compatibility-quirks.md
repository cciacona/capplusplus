# Compatibility quirks

The canonical catalog is
[`specs/compatibility-quirks-v1.json`](../specs/compatibility-quirks-v1.json),
validated by `python scripts/project_gates.py ledgers`. This page explains how to
use it; it does not replace the machine-readable entries.

Quirks are behaviors that need an explicit compatibility choice, not ordinary
unfinished features. A quirk may be a DOS/Windows compiler disagreement,
platform residue in a save, an original bug whose preservation affects gameplay,
or unsafe legacy behavior that must be accepted only at an input boundary.

## Current decisions

| ID | Evidence state | Classic policy | Summary |
|---|---|---|---|
| `town_pointer_residue` | Inferred | Sanitize | Two town-record dwords vary like runtime residue; original-save normalization handles only their registered byte ranges. Native state must never contain host pointers. |
| `town_market_float_drift` | Confirmed | Pending | Four tracked town/item floats differ by 1–4 ULPs across the matched DOS/Windows saves; their meanings and canonical arithmetic still need controlled probes. |
| `terrain_fertility_signed_char` | Confirmed | Pending | A negative intermediate clamps to 100 in DOS and 0 in Windows because the compilers compare the byte differently. The gameplay consequence must be measured before Classic selects a result. |
| `playing_time_62_second_minute` | Confirmed | Preserve | Both builds divide accumulated seconds by 62 for displayed minutes and 3,720 for hours. Classic preserves that display; Extended may use conventional time. |

`pending` is intentional and blocks code from quietly selecting a compatibility
answer. It does not block continued research or APIs that expose both original
profiles explicitly.

## Adding an entry

1. Establish the smallest reproducible observation and classify its provenance
   under [controlled experiments](experiments.md).
2. Add a stable identifier and all required policy fields to the JSON catalog.
3. Link focused factual documentation and a synthetic regression test. Confirmed
   entries cannot omit tests.
4. Explain whether the choice affects Classic parity, save integrity,
   deterministic simulation, AI, or multiplayer.
5. Run the ledger and repository gates.

Do not add a quirk merely because a field is unknown. Unknown structures remain
in the format catalog or parity ledger until an actual compatibility choice is
identified. Do not relabel an inference as confirmed when only its safety policy
is known.
