# 0002: Fix native-save invariants before its wire format

- Status: Accepted
- Decision date: 2026-09-08
- Wire-format deadline: before the 0.5 vertical-slice save implementation

## Context

Cap++ must import original version-100 saves and aims to export them when every
changed byte can be handled safely. The original format also carries unknown
bytes and apparent runtime residue. It is therefore unsuitable as the sole
long-term persistence format for larger maps, higher limits, mods, replay data,
or future simulation structures.

Choosing exact byte layouts before the 0.3 state inventory is complete would
freeze guesses. Waiting until after gameplay implementation would encourage
serialization of C++ object layouts, pointers, padding, or unstable identifiers.

## Decision

Cap++ will have a separate, open native save format. Its exact extension, magic,
chunk directory, and encoding remain deferred, but the following requirements
are accepted now.

### State boundaries

- Persist simulation state using fixed-width values and stable object IDs, never
  host pointers, compiler padding, object addresses, or raw C++ memory images.
- Separate deterministic simulation state from local UI preferences, caches,
  renderer state, and other reproducible derived data.
- Store an explicit simulation date/tick and the complete deterministic RNG state.
- Give every independently migratable state group a stable type ID and version.

### Identity and reproducibility

- Record the engine save-schema version, compatibility profile, ruleset identity,
  and ordered content identities described by [decision 0004](0004-content-identity.md).
- Store enough command/replay metadata to reproduce the state when that feature
  is enabled, without making replay history mandatory for an ordinary save.
- Record original-import provenance as hashes and metadata only; never embed
  proprietary input files in a native save.

### Evolution

- Every stable Cap++ release must load native saves written by earlier stable
  releases unless the file is corrupt or exceeds documented safety limits.
- Migrations operate on explicit schema versions and are covered by synthetic
  fixtures. Loading must not silently discard a required unknown chunk.
- Optional chunks may be retained opaquely only when doing so is bounded and
  cannot conceal executable content or alter deterministic state.
- Pre-release experimental saves must identify themselves as such and receive a
  documented migration or an explicit expiry before the next stable release.

### Integrity and failure behavior

- Validate all lengths, counts, identifiers, dependencies, and decompression
  bounds before allocating or mutating live state.
- Detect accidental corruption with per-section or whole-file checksums;
  cryptographic signing is a separate future decision.
- Load into temporary state and publish it only after complete validation.
- Save through a temporary file, flush it, and replace the destination atomically
  where the platform permits. Preserve a recoverable previous save when replacing
  an existing file.
- Metadata inspection must never execute scripts or load native code from a save.

### Original-format relationship

- Original version-100 import and native save loading are separate codecs feeding
  the same canonical state model.
- Original-format export remains disabled for any structure whose unknown bytes
  cannot be preserved or regenerated safely.
- A native Classic save must retain enough profile information to prevent a mod
  or Extended ruleset from being applied silently.

## Deferred wire decisions

The following require the complete 0.3 state inventory or a native prototype:

- file extension, magic, byte order, and container encoding;
- chunk table placement, compression, and checksum algorithms;
- canonical numeric representation for fields where the original builds drift;
- mandatory versus optional chunk set;
- replay/checkpoint storage and thumbnail handling;
- human-readable debugging or conversion representation.

The 0.4 engine shell may prototype the envelope. The 0.5 milestone must approve
and test version 1 of the wire format before vertical-slice saves are treated as
stable.
