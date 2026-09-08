# Changelog

## Unreleased

- Recovered save section `1005` as the 65-byte calendar/playing-time clock,
  including every field offset, day/month/year transition order and periodic
  counter cadence.
- Added exact clock and RNG models plus an optional exact-build Unicorn survey;
  all 12 RNG sequences, six fixed-duration calendar runs and two loop probes
  match the DOS and Windows functions with zero tolerance.
- Confirmed separate saved-simulation and presentation RNG objects in both
  builds, rejecting the earlier hypothesis that Windows music selection changes
  the RNG serialized in saves.
- Recorded the original 62-second playing-time minute as a profile-controlled
  compatibility quirk and added synthetic original-function golden vectors.
- Added accepted architecture records for narrow original-build support, native
  save invariants, compatibility-quirk policy, and future content identity;
  added a validated quirks ledger, reference-project license matrix, and
  third-party attribution policy.
- Reconstructed all four post-shading world-initialization passes: base tile
  classification, `TERRAIN.RES` shoreline transitions, climate/rainfall/soil
  generation and deterministic terrain-variant selection.
- Confirmed runtime cell bytes 5–7 as climate, rainfall and soil fertility,
  preserved unresolved bytes 2–3, and retained the DOS/Windows signed-`char`
  fertility difference as an explicit compatibility profile.
- Extended the isolated-function terrain survey with normalized user-owned
  terrain resources, final RNG-state checks and synthetic runtime regressions.
- Corrected stale roadmap and format-catalog references to the map's 29-byte
  city-array header and unknown city-record dword.
- Reconstructed full-map terrain shading with separate DOS/Windows lookup
  tables, signed arithmetic, neighbor lighting and original border-copy order.
- Added `render-map --terrain-profile dos|windows`, independently selectable
  palette conversion and working-grid fingerprints; source-preview defaults
  remain unchanged.
- Added an optional, exact-build Unicorn terrain-function survey and synthetic
  output-hash regressions without introducing an inspector runtime dependency.
- Recovered the editor's two-grid partial terrain-update contract and added a
  bounded `update_terrain_rectangle` API with exact outside-cell preservation.
- Added 22 terrain tests and verified all 132 original-function grid comparisons
  across both builds, both x87 precision settings, shipped maps, full-grid probes
  and twelve partial rectangles. Native editor and rendering validation remain pending.
- Documented the original city editor's limit, 7×7 terrain predicate,
  axis-aligned separation rule, exact-name check and runtime name synchronization.
- Reclassified city-record offset 4 as unknown after confirming the editor does
  not assign it; retained `population` as an explicitly unconfirmed JSON alias.
- Corrected `.MAP` framing from a 52-byte header and 32-byte footer to the
  executable-confirmed 55-byte header and 29-byte city-array header. Added map
  `layout_version: 2`, counted cities and optional unframed settings blocks.
- Decoded signed terrain heights, initial height/water-shade conversion and
  transient city-array metadata. Preserved all unresolved cell/header bytes.
- Corrected the old overview interpretation: exports preview source-height low
  bytes, not original runtime shading. Existing preview pixels are unchanged.
- Added 13 synthetic map tests for flag combinations, counts, bounds, negative
  heights, pointer preservation, CLI routing and byte-exact reconstruction.
- Added deterministic graphics catalogs and cross-installation comparison for
  decoded images, font glyphs, palettes, cursor bindings and opaque members.
- Added stable source/record identifiers and explicit storage-order groups
  without treating unverified frame timing or palette choices as known behavior.
- Recovered the shared six-bit palette load conversion and the Windows upload
  expansion; added an optional Windows palette profile for image/map PNG exports.
- Added 19 synthetic graphics tests covering catalog equivalence, malformed
  inputs, resource limits, cursor references and palette/pixel preservation.
- Fixed direct CLI inspection and reconstruction of damaged extensionless sound
  effects by retaining parent-path context through parser dispatch.
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
