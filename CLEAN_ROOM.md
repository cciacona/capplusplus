# Clean-room and compatibility policy

This repository is intended to contain only newly written code, original
documentation, synthetic tests, and factual compatibility information.

## Repository boundaries

Do not commit:

- original executables or DLLs;
- artwork, palettes, music, sound, fonts, text, maps, scenarios, saves, or game
  sets copied from the game;
- decompiler output or reconstructed source presented as original source;
- material copied from proprietary manuals beyond short, attributed facts where
  legally permitted;
- generated JSON containing substantial original table rows or binary payloads.

Small non-expressive facts needed for interoperability—such as magic values,
field offsets, dimensions, serialization order, and hashes—may be documented.
Tests should build synthetic fixtures in memory.

## Observation records

Every new format or behavior claim should state how it was learned:

- static file comparison;
- controlled in-game experiment;
- black-box input/output observation;
- public documentation; or
- executable analysis, where lawful.

Label uncertain meanings as inferred and preserve unknown data as opaque bytes.
Do not give an unknown field a semantic name merely because a value looks
plausible.

## Engine separation

The eventual engine should depend on documented behavior and format contracts,
not on copied implementation. When practical, keep observation notes and test
vectors separate from engine implementation tasks. A contributor who writes an
engine subsystem should be able to explain its behavior in terms of documented
inputs, outputs, and experiments.

## User-owned data

The tooling must require users to supply their own game files. It must not fetch,
bundle, or redistribute proprietary data. Read-only support comes before any
input-format writer. Exporting to a new open file is allowed and must never modify
the source. An original-format writer must preserve unknown bytes or have an
explicit, tested schema for every byte it changes.

This policy is a project-development rule, not legal advice. Contributors must
follow the law that applies to them.
