# 0005: Target only Steam Capitalism Plus 1.01

- Status: Accepted
- Decision date: 2026-09-29
- Supersedes: [0001](0001-narrow-original-build-support.md) for supported-release scope
- Applies to: Cap++ 1.0 acceptance, installation validation, data inventory,
  save compatibility, and behavioral parity

## Context

The earlier roadmap used the retail DOS and Windows 1.0 releases as both the
reference corpus and the supported asset sources. A publisher-announced Steam
1.01 release now exists. A user-supplied archive has a distinct Windows PE
executable, an SDL3 dependency, and 71 of 72 core-file hashes identical to the
retail corpus; its different core file contains menu/button images. See the
[measured reference matrix](../reference-builds.md). The archive includes
pre-update saves and mutable user settings, and has no Steam app manifest.
Its exact depot build ID and live behavior are not yet verified.

Keeping old executable compatibility as a product requirement would require
extra asset, save, presentation, and behavior profiles. The project owner has
chosen one original release for the open-source replacement.

## Decision

Steam Capitalism Plus 1.01 is the **sole supported original release** targeted
by Cap++ 1.0. The exact measured executable and its 72 measured core assets
form the initial validation fingerprint. The inspector identifies the two old
retail executables for historical research, but their installations are not
supported input for the replacement. A new Steam patch, even if labeled 1.01,
requires a new fingerprint and data review before acceptance.

Classic profile parity is judged against measured Steam 1.01 behavior. The
retail DOS and Windows observations remain useful hypotheses where the data
match; a historical result is not a substitute for a 1.01 behavior probe.
User-owned Steam files are required at runtime and proprietary bytes are never
bundled in Cap++.

Saves created by Steam 1.01 are the original-format import target. Importing
retail DOS/Windows 1.0 saves into Steam or Cap++ and exporting to retail 1.0
are optional migration research, not Cap++ 1.0 acceptance criteria. A 1.01
save sample is still required to verify the target format and persistence
behavior; cross-loading an old save is unnecessary for this scope decision.

## Consequences and limits

- The inspector's `--require-clean` gate requires the exact target executable
  and all 72 target core hashes. It establishes a measured input identity,
  **not** a complete gameplay, depot-content, or save compatibility claim.
- The retail CD inventory and DOS/Windows function probes remain labeled as
  historical evidence. A clean Steam 1.01 depot inventory, music mapping, save
  sample, and controlled game probes replace them as release-gate evidence.
- Cap++ 1.0 remains a future milestone of this project; Steam's 1.01 version
  number does not imply that the reimplementation has shipped.
- The [profile and content identities](0004-content-identity.md) still apply:
  a validated Steam asset fingerprint is the initial Certified Classic data
  source. Later patches require explicit policy and evidence.

## Subsequent save evidence (2026-09-29)

A separately supplied save reported as created in Steam 1.01 has a version-100
header and the historical 24-section marker order; the read-only inspector
parses it. Its hash and structural findings are recorded in the
[reference matrix](../reference-builds.md). This advances the target-format
inventory without changing the decision: the installed depot identity and a
controlled 1.01 load/resave still need measurement.
