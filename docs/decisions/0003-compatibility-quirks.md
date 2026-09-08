# 0003: Track compatibility quirks separately

- Status: Accepted
- Decision date: 2026-09-08
- Catalog: [`specs/compatibility-quirks-v1.json`](../../specs/compatibility-quirks-v1.json)

## Context

The DOS and Windows executables share the same core design but can disagree at
compiler and platform edges. The original game also serializes values that a
modern engine should not reproduce literally. A feature checklist alone cannot
say whether Cap++ must preserve, canonicalize, sanitize, reject, or postpone one
of these behaviors.

Embedding such decisions as scattered code comments would make Classic parity,
save normalization, and deterministic multiplayer difficult to audit.

## Decision

Maintain a versioned, machine-validated compatibility-quirks catalog alongside
the feature-parity and content-coverage ledgers.

Each entry records:

- the observed behavior and affected reference builds;
- whether the interpretation is confirmed, inferred, or pending;
- the intended Classic and Extended policies;
- compatibility, integrity, safety, or determinism risk;
- repository evidence and tests.

Classic behavior is selected deliberately per entry:

- `preserve`: reproduce the original behavior;
- `canonicalize`: choose one documented deterministic result;
- `sanitize`: accept compatible input but exclude unsafe/transient state;
- `reject`: fail safely rather than reproduce invalid or dangerous behavior;
- `pending`: gather more evidence before implementation depends on a choice.

Extended mode either inherits the Classic resolution, fixes a deliberately
preserved quirk, has no applicable behavior, or remains pending.

## Evidence rules

A confirmed entry needs a focused repository test and factual evidence. An
inferred entry must remain labeled as such even if a provisional safety policy
is already clear. Reference-project behavior is design inspiration, not evidence
of Capitalism Plus behavior.

The prose view and update procedure live in
[compatibility quirks](../compatibility-quirks.md). The ledger is not a list of
every unfinished feature and must not duplicate the parity catalog.
