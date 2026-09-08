# Architecture decisions

Architecture decision records capture choices that should remain stable across
individual implementation pull requests. They explain why a boundary exists,
what has been decided, and which details are deliberately deferred.

Statuses have the following meanings:

- **Accepted**: the decision governs new work unless replaced by a later record.
- **Proposed**: review is still required before implementation depends on it.
- **Superseded**: a later record replaces the decision; the old record remains
  for history.

| Record | Status | Decision |
|---|---|---|
| [0001](0001-narrow-original-build-support.md) | Accepted | Keep original-build recognition intentionally narrow. |
| [0002](0002-native-save-invariants.md) | Accepted | Fix native-save invariants before fixing its wire format. |
| [0003](0003-compatibility-quirks.md) | Accepted | Track compatibility quirks independently from feature completion. |
| [0004](0004-content-identity.md) | Accepted | Give profiles, rulesets, and future content stable identities. |

An accepted record can still contain explicitly deferred details. Those details
must be resolved by the named milestone before code relies on them. Changing an
accepted requirement requires a new decision record rather than silently
rewriting the old rationale.
