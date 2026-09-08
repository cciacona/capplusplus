# 0001: Keep original-build recognition narrow

- Status: Accepted
- Decision date: 2026-09-08
- Applies to: installation discovery, validation, and compatibility reporting

## Context

Cap++ supports one game: Capitalism Plus. The evidence corpus currently contains
one unmodified DOS 1.0 executable and one unmodified Windows 1.0 executable.
Their shared `GAMESET`, `MAPS`, and `RESOURCE` trees are byte-identical.

A generalized game/version detection database would add schema and maintenance
cost without representing another known release. DOS and Windows still need
distinct executable fingerprints because they are different binaries, even
though they identify the same game version and use the same shared data.

## Decision

Keep a small, explicit manifest for the two known executable fingerprints and
the shared core-file hashes already recognized by `capplus-inspect`.

- Do not build a multi-game detector or speculative edition/language hierarchy.
- Report an unknown executable or changed core file accurately; do not guess
  that it is compatible from a filename or version string.
- Treat executable identity and data identity as separate checks.
- Add another build only after a redistributable evidence record establishes
  that the release exists and identifies its relevant differences.

## Consequences

The current implementation stays simple and auditable. If another patch,
regional executable, or legitimately distinct data set is found later, this
record should be superseded with the smallest model supported by that evidence.
No 1.0 requirement depends on hypothetical variants.
