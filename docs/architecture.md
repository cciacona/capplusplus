# Pre-engine architecture

The roadmap's C++20/CMake/SDL3 direction is retained. The component names below
remain proposals; the decision table distinguishes accepted requirements from
open implementation choices. Keep Python research usable while adding the engine
incrementally to this repository; no immediate source-tree migration or second
repository is needed.

Accepted choices live in [architecture decision records](decisions/README.md).
They are requirements for later implementation, not claims that a native engine,
save codec, or package manager already exists.

## Proposed native components

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

## Decision status

| Area | Status | Record or remaining decision |
|---|---|---|
| Supported original builds | Accepted | [Keep recognition narrow](decisions/0001-narrow-original-build-support.md); OS-specific discovery and missing-data UX remain for 0.4. |
| Native saves | Requirements accepted; wire format deferred | [Native-save invariants](decisions/0002-native-save-invariants.md); approve wire version 1 before stable 0.5 saves. |
| Compatibility quirks | Accepted and active | [Quirk policy](decisions/0003-compatibility-quirks.md) and [validated ledger](compatibility-quirks.md). |
| Profile/content identity | Boundary accepted; manifest syntax deferred | [Content identity](decisions/0004-content-identity.md); implement package syntax only against a real Extended prototype. |
| Native target layout | Open before 0.4 | Choose the CMake directory/target layout, supported compilers, warnings, sanitizers, and test targets. |
| Native dependencies | Open before the first dependency PR | Choose acquisition, version pinning, offline-build behavior, license review, and platform packaging. |
| Numeric determinism | Open before 0.5 | Fix numeric representation plus command, update, iteration, RNG, hashing, and replay order. |
| Release ownership | Open before 0.4 ships | Decide whether inspector and native application versions/tags advance together or independently. |

For now `v*` tags describe the Python distribution and must match its metadata.
Do not label the inspector's unreleased research as a released native game.
These decisions must preserve the [1.0 parity contract](../ROADMAP.md); unresolved
choices are not implied approvals to remove features or add new dependencies.
