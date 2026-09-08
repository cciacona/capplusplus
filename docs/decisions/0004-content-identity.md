# 0004: Use explicit profile, ruleset, and content identities

- Status: Accepted
- Decision date: 2026-09-08
- Manifest-syntax deadline: before Extended content loading is implemented

## Context

Classic parity, future mods, native saves, replays, and multiplayer all need to
say precisely which behavior and data produced a state. A list of filenames is
not sufficient: ordering can affect overrides, versions can change semantics,
and original proprietary assets must never be confused with redistributable
packages.

Building a complete mod manager before Classic parity would distract from the
reimplementation. Omitting identity boundaries until afterward would make saves
and network compatibility difficult to repair.

## Decision

Model identity in separate layers:

| Layer | Purpose |
|---|---|
| Engine protocol | Compatibility of commands, state snapshots, saves, and networking. |
| Profile | `classic` or `extended`; determines which compatibility contract applies. |
| Ruleset | Stable ID plus semantic version for simulation behavior. |
| Content package | Stable ID, version, type, dependencies, load order, and content digest. |
| Original data | Installation fingerprints used for validation, never treated as redistributable packages. |

Reserve `capplusplus.classic` and `capplusplus.extended` as built-in ruleset IDs.
External package IDs must use lowercase dotted tokens under a namespace controlled
by their publisher. A package version and content digest are both required:
versions express compatibility, while digests identify the exact bytes used.

The digest input must be canonical and independent of installation path, file
timestamps, archive ordering, and host case-folding. SHA-256 is the initial
digest algorithm; replacing it requires a versioned identifier rather than
changing the meaning of an existing digest.

## Profile boundaries

- **Certified Classic** uses the built-in Classic ruleset and validated original
  data with no external package affecting simulation or presentation. This is
  the configuration used by the complete parity matrix.
- **Classic rules** may eventually permit explicitly presentation-only or
  localization packages. Such a session retains Classic simulation identity but
  is not certified for presentation parity.
- **Extended** permits declared packages and altered limits. Its saves and
  sessions must never masquerade as certified Classic.

Until package compatibility is implemented, only certified Classic is a valid
runtime target. These categories define identity; they do not promise an early
mod loader.

## Save and multiplayer requirements

- Native saves record the profile, ruleset ID/version, and ordered package list
  with exact digests.
- Loading reports missing, extra, reordered, or digest-mismatched packages before
  constructing simulation state. It must not silently substitute content.
- Multiplayer peers compare the same deterministic identity before joining.
  Presentation-only packages may differ only after their non-simulation status
  is enforceable and covered by tests.
- Replays carry the same identity as saves and fail with a precise diagnostic
  when their deterministic content is unavailable.

## Security and distribution

- A data package cannot load native libraries or run installation-time code.
- Any future scripting runtime must be sandboxed, deterministic for simulation
  use, resource-bounded, and separately versioned.
- Cap++ infrastructure must not download or redistribute original game assets.
- Package manifests will declare license and attribution metadata before public
  distribution support is added.

## Deferred details

Manifest syntax, dependency constraint grammar, archive format, signature/trust
model, repository protocol, override rules, and scripting ABI remain deferred.
They should be designed against a real Extended content prototype after the
Classic data model is stable.
