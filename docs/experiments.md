# Sanitized experiment vectors, version 1

[`specs/experiment-v1.schema.json`](../specs/experiment-v1.schema.json) defines
portable observation records for future parity tests. It stores identifiers,
hashes, commands and selected scalar observations, not saves, table dumps,
screenshots, executable bytes or encoded payloads. Public vectors still require
content review under `CLEAN_ROOM.md`.

The [synthetic example](../tests/fixtures/experiments/synthetic-state-delta.json)
uses arbitrary invented values. It tests the schema and validator, not the
original RNG, simulator, or command implementation.

```bash
python scripts/project_gates.py experiment --input tests/fixtures/experiments/synthetic-state-delta.json
```

## Controlled observations

1. Select one narrow question and pin the original executable and initial save
   hashes. Record the build/platform, scenario identifier, date and RNG state.
2. Start participants from equivalent controlled state. Document all differences
   in provenance and comparison preconditions; the validator does not establish
   equivalence from hashes alone.
3. Specify actions in strict `(day_offset, sequence)` order, including pauses
   and relevant setup decisions. Numeric identifiers are preferred to copied
   game text. Command vocabulary is experiment-specific for now, not an engine API.
4. Record an initial checkpoint before actions on day zero, subsequent
   checkpoints at the start of their day before that day's actions, and a final
   checkpoint after the requested elapsed days. Each participant must have both
   endpoints. Actions must precede the final checkpoint day; zero-day no-op
   records cannot contain actions. Use separate observations if intra-day probes are
   needed; v1 does not encode intra-day checkpoints.
5. Keep original saves privately and publish their hashes with a small set of
   pertinent scalar values. Explain observation method, confidence and evidence.
6. Attach per-field comparisons and preconditions. Exact comparisons require
   zero tolerance; ULP counts must be integral. Integer/event/ownership outcomes
   should remain exact. Any numeric tolerance needs its own evidence.

The observed 1–4 ULP drift in selected original market fields is **not** a global
four-ULP allowance for the future simulator. Record rounding sensitivity and
decision outcomes separately. A small arithmetic difference that changes a
purchase, bankruptcy, AI branch or RNG call sequence is not harmless parity.

## Validation boundaries

`original_observation` requires Classic mode, nonsynthetic provenance, exact
build/initial-save hashes and private-save hashes at every checkpoint.
`synthetic` requires synthetic provenance and profile. Both require known,
unique participants, ordered unique actions, bounded event dates, consistent
initial state, endpoint checkpoints and observed comparison fields. Scalar
parameters/values allow finite numbers, booleans and null, not binary strings.
NaN, infinity, duplicate JSON keys and unexpected schema keys are rejected.

The schema and validator establish record consistency only. They do not run the
original game, replay actions, compare field values or prove numeric policies.
The native differential runner and the first original-observation vectors
remain separate deliverables. Schema changes that alter these semantics need
a new version; do not reinterpret existing vectors in place.
