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

## Subsequent evidence (2026-09-26)

The publisher [announced Steam Capitalism Plus version 1.01](../reference-builds.md)
after this decision was accepted. The historical premise that no other release
was known no longer holds. The narrow-recognition decision remains in effect:
a user-supplied 1.01 archive now has a measured executable fingerprint and a
71/72 core-file match, but no live save or behavior validation. The inspector
reports the executable as an unknown build with a PE header. A controlled save
probe and scope decision will determine whether to supersede this record and
recognize it as a supported build.
