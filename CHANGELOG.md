# Changelog

## Unreleased

- Added PCM bank inspection/export with separate DOS and Windows rate profiles,
  extensionless WAV comparison, and nine-slot sound-settings framing.
- Added bounded XMIDI/IFF inspection and unchanged member export; musical event
  semantics and CD correspondence remain explicitly unresolved.
- Added metadata-only mixed-mode CUE geometry and an exact-build audio survey,
  documenting Windows CD selection, notification handling, and music RNG use.
- Extended structural round trips to audio, the catalog to 26 formats, and
  deterministic fuzzing to 21 fixtures; added 24 synthetic audio tests.
- Added versioned original-content and feature-parity ledgers with separate
  framing, preservation, semantics and behavior states; unresolved retail
  inventory and manual-crosswalk work remain explicit.
- Added a sanitized experiment-vector specification, synthetic example and
  consistency gates without claiming a native replay runner.
- Added Git-index content-boundary checks and replaced blanket JSON ignoring
  with scoped private/generated output directories.
- Added Windows/macOS test coverage, clean wheel/sdist rebuild and offline
  installation checks, and source/metadata/CLI/tag version validation.
- Corrected the setuptools build minimum for SPDX/license-file metadata and
  retained native-architecture decisions as explicit pre-0.4 work.
- Refocused the README on evergreen project information and moved development
  history to this changelog.
- Hardened CI with scoped triggers, concurrency cancellation, SHA-pinned
  official actions, Python 3.14 coverage, and a stable aggregate `CI` check.
- Added monthly grouped Dependabot updates for GitHub Actions.
- Added a security policy, structured issue forms, and a clean-room pull request
  checklist.
- Added bounded MZ, PE32/PE32+, and LE executable inspection.
- Added PE section, data-directory, library, and imported-symbol decoding.
- Added LE object, module-name, and resident-name decoding.
- Added opt-in ASCII and UTF-16LE string output with summary counts by default.
- Added a reproducible three-report DOS/Windows executable survey and synthetic
  fixtures.
- Added PE import-address-table locations and LE page-to-file mappings.
- Added a deterministic cross-build loader survey for original resources,
  game sets, maps, scenarios, saves, and support files.
- Documented matching DOS/Windows file-operation contracts and their runtime/API
  boundaries without committing decompiler output.
- Implemented size-prefixed compatibility reads, including zero-extension,
  oversized-tail skipping, and a controlled malformed-record probe.
- Added strict parsers for bitmap fonts, DOS text screens, supplemental language
  glyphs, cursor metadata/images, and context-help hotspots.
- Added lossless font-atlas export with cumulative glyph geometry in its JSON
  manifest.
- Decoded layout-plan category framing, 127-byte records, ordered 3×3 unit/item
  grids, and stable eight-byte item references.
- Added compatible-record inspection for configuration and hall-of-fame files,
  keeping their unassigned fields explicit.
- Added a bundled, versioned machine-readable catalog covering 20 original
  on-disk structures and enforcing provenance for inferred fields.
- Added byte-preserving structural round-trip validation for individual files,
  directories, and installation ZIPs, with opaque coverage reported separately.
- Added an explicit versioned save-normalization policy that distinguishes
  registered pointer/float drift from unclassified differences.
- Added a deterministic bounded mutation fuzzer with 16 synthetic parser-family
  fixtures and a fixed CI campaign.
- Expanded the synthetic suite to 70 tests and added aggregate schema,
  provenance, and fuzz gates to CI.

## 0.2.0 — 2026-09-02

- Identified the `.MAP` core as a 240×198 grid of 47,520 eight-byte cells plus a
  52-byte header and 32-byte footer.
- Added exact palette-indexed map rendering with city markers.
- Added 256-color palette inspection.
- Added lossless indexed-PNG export for direct, sequential, offset-indexed, and
  named/mixed original image resources.
- Added palette transparency, integer scaling, JSON manifests, atomic output,
  and overwrite protection.
- Expanded the synthetic suite to 20 tests.
- Replaced the short roadmap with a complete feature-parity plan through 1.0.

## 0.1.0 — 2026-09-02

- Added directory and ZIP installation validation for the analyzed DOS and
  Windows builds.
- Added named, offset-indexed, and sequential-image container inspection.
- Added embedded dBASE table parsing for `.SET` files.
- Added `.MAP` city-tail parsing.
- Added version-100 save metadata, section-chain, RNG, and town-array parsing.
- Added section-aware save comparison with pointer normalization evidence and
  float ULP statistics.
- Added schema-versioned JSON and a synthetic 15-test suite.
