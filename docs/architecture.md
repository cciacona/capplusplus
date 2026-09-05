# Pre-engine decisions

The roadmap's C++20/CMake/SDL3 direction is retained. The boundaries below are
proposals to settle before 0.4, not claims that native targets already exist.
Keep Python research usable while adding the engine incrementally to this
repository; no immediate source-tree migration or second repository is needed.

| Boundary | Proposed contract | Decision/evidence still needed |
|---|---|---|
| `capplus_data` | Independent native readers load user-owned original files directly. Inspector JSON supports research and interoperability, not a mandatory runtime conversion. | Select shared conformance vectors and lossless unknown-byte representation. |
| `capplus_sim` | Headless deterministic state; explicit RNG, stable object IDs and ordered commands. | Numeric/rounding policy, update order, state hashing and replay checkpoints. |
| `capplus_client` | SDL3 UI/render/audio reads state and emits commands; cannot drive economic time implicitly. | Logical coordinates, scaling/input policy, asset discovery and fallback behavior. |
| `capplus_net` | Session commands and synchronization separated from simulation. | Verify original multiplayer turn/session rules and player limits before choosing transport or lockstep design. |
| `capplus_test` | Synthetic conformance tests plus opt-in private original-game experiments. | Differential runner, private-corpus contract and crash/desync diagnostics. |

The existing matched saves do not establish cross-platform deterministic
long-running simulation. Floating-point and iteration-order decisions need
controlled probes before promising replay or multiplayer stability. Do not
infer the original network/session protocol from platform-era conventions.

Before the native shell PR, record short architecture decisions for:

- CMake target layout (candidate `engine/`, leaving Python `src/` intact),
  compiler support and sanitizer CI;
- native dependency acquisition, pinning, license review and offline builds;
- install-data discovery, compatibility profiles and missing-asset behavior;
- numeric policy and deterministic command/update/RNG ordering;
- original-save import/export, native-save migration and Classic/Extended IDs;
- version/tag ownership when both inspector and native application ship.

For now `v*` tags describe the Python distribution and must match its metadata.
Do not label the inspector's unreleased research as a released native game.
These decisions must preserve the [1.0 parity contract](../ROADMAP.md); unresolved
choices are not implied approvals to remove features or add new dependencies.
