# Reference projects and reuse policy

Cap++ studies mature open reimplementations for engineering and project-design
patterns. They are references, not dependencies and not evidence of Capitalism
Plus behavior. Capitalism-specific claims must still come from the evidence and
experiments required by `CLEAN_ROOM.md`.

The licenses below were reviewed from each linked upstream repository on
2026-09-08. Recheck the exact upstream commit and individual file before any
reuse; repository-level summaries do not override per-file notices.

| Project | Useful precedent | Upstream license | Cap++ use |
|---|---|---|---|
| [OpenLoco](https://github.com/OpenLoco/OpenLoco) | C++/CMake/SDL management-game reimplementation, original-data loading, platform packaging, and the need for a native format beyond original save limits. | MIT | Primary engineering reference. Selective reuse is possible only with review and attribution. |
| [CorsixTH](https://github.com/CorsixTH/CorsixTH) | Business-simulation separation, C++ plus Lua, original-data setup, editors, campaigns, and contributor-accessible gameplay logic. | MIT core; bundled dependencies have their own licenses | Architecture reference. Review each file and dependency before reuse. |
| [Julius](https://github.com/bvschaik/julius) and [Augustus](https://github.com/Keriew/augustus) | Strict original behavior and save compatibility separated from enhanced gameplay and one-way extended saves. | AGPL-3.0 | Compatibility-policy reference only while Cap++ remains MIT. Do not copy code. |
| [OpenTTD](https://github.com/OpenTTD/OpenTTD) | Long-lived save migration, content identities, replacement assets, AI/game scripts, and multiplayer operations. | GPL-2.0 | Design reference only. Do not copy code into the MIT codebase. |
| [OpenRCT2](https://github.com/OpenRCT2/OpenRCT2) | Original-asset discovery, scalable classic presentation, object/content systems, editing, multiplayer, and plugins. | GPL-3.0 | UX and extension reference only. Do not copy code into the MIT codebase. |
| [ScummVM](https://github.com/scummvm/scummvm) | Defensive original-data discovery, exact build fingerprints, release diagnostics, save migration, and modular engine boundaries. | GPL-3.0 | Detection and compatibility reference only. Cap++ deliberately uses a much narrower build manifest. |
| [VCMI](https://github.com/vcmi/vcmi) | Mod manifests, serialization, editors, scripting, and explicit client/server state authority. | GPL-2.0-or-later | Later networking and content-design reference only. Do not copy code into the MIT codebase. |

## Adopted lessons

- Use OpenLoco as the nearest technical comparison, without importing its game
  model or assuming that its reverse-engineering choices fit Capitalism Plus.
- Keep certified Classic behavior distinct from enhancements, following the
  product boundary demonstrated by Julius and Augustus while retaining one
  Cap++ codebase and explicit ruleset identities.
- Design native save migration and exact content identity early enough to avoid
  locking future work to original file limits.
- Keep original-installation discovery factual and hash-based, but do not build
  ScummVM's multi-game abstraction for a single known Capitalism Plus release.
- Allow future scripting and content only through deterministic, versioned,
  sandboxed boundaries; Classic parity remains the first goal.

## Reuse procedure

Before incorporating any third-party source or asset:

1. Open a focused issue naming the upstream repository, immutable commit, exact
   files, purpose, and license.
2. Confirm compatibility with the repository's MIT distribution and all linked
   dependencies. GPL, AGPL, and noncommercial source must not be copied into the
   MIT codebase without an explicit project-wide licensing decision.
3. Prefer a dependency or an independently written small interface over copying
   a large utility subtree.
4. Preserve required copyright and license notices and update
   [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md).
5. Record substantial imported-code formatting separately in Git history so
   provenance remains reviewable.

General ideas, public interfaces, and factual algorithms can inspire independent
work, but code expression, artwork, documentation text, and test fixtures retain
their upstream licensing and attribution requirements.
