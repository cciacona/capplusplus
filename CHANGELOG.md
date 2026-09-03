# Changelog

## Unreleased

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
