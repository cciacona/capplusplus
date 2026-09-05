# Feature-parity ledger

[`specs/feature-parity-v1.json`](../specs/feature-parity-v1.json) translates the
roadmap into stable feature IDs, acceptance requirements, target milestones,
content-family dependencies and independently tracked dimensions:

- data loading and meaning;
- simulation;
- user interaction and presentation;
- persistence;
- AI use;
- multiplayer use.

The initial 43 rows are candidate groups derived from `ROADMAP.md`, **not a
completed independent manual crosswalk**. `manual_crosswalk_status` is `pending`.
Every original feature needs a precise manual section and/or a controlled
reference observation before validation. Split grouped requirements into
separate IDs whenever their implementation or verification can diverge. An
omitted requirement discovered in the manual is a new row, not an excuse to
reduce the 1.0 contract.

All native-engine dimensions initially say `not_started`: inspector research
does not mean a game system exists. Later states are `in_progress`,
`implemented`, `validated`, `blocked` or `not_applicable`. Use `implemented` when
code exists but reference tests are incomplete. Use `not_applicable` only with
an explicit rationale in the row; do not automatically exempt AI or multiplayer.
The ledger is not a percentage-complete estimator.

`python scripts/project_gates.py ledgers` checks schemas, unique IDs, all six
dimensions, known content-family references, evidence/test file existence and
completion-state consistency. `validated` requires test references and a
checked reference status; a complete manual crosswalk cannot retain unchecked
rows. It does not execute those tests or judge whether an evidence citation is
sufficient. Code review and the test suite remain necessary.

For each parity claim, attach a sanitized [experiment](experiments.md) and the
test that consumes it. Record the original build, starting state, commands,
checkpoints and field-specific comparison rule. A parser unit test alone is not
an economic-behavior test. Native replay and differential runners are future
work; this ledger deliberately does not imply they already exist.
