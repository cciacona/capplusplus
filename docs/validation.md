# Validation record through the 0.3 development snapshot

The tool was checked against the user-supplied, unmodified DOS and Windows
game directories and three mutually compatible version-100 saves.

## Installations

| Check | Extracted DOS directory | Extracted Windows directory |
|---|---:|---:|
| Files under detected root | 149 | 113 |
| Shared core files matched | 72 / 72 | 72 / 72 |
| Executable recognized | `CAPPLUS.EXE` | `CAPWIN.EXE` |
| Game sets parsed | 3 | 3 |
| Layout-plan files parsed | 9 | 9 |
| Maps parsed | 15 | 15 |
| Resources inspected | 33 | 33 |
| Config/HOF/sound-settings files parsed | 3 | 3 |
| Loose PCM WAVs parsed | 0 | 25 |
| Deep-inspection errors | 0 | 0 |

The 72 shared game-set, map, and resource files are byte-identical between the
two supplied builds. Their expected SHA-256 values are embedded only as hashes;
no source file bytes are included. This audio pass rechecks the intact extracted
files; the original installation ZIP validation is earlier evidence.

## Saves

| Check | DOS scenario save | Matching Windows scenario save | Windows autosave |
|---|---:|---:|---:|
| Save version | 100 | 100 | 100 |
| Sections resolved | 24 / 24 | 24 / 24 | 24 / 24 |
| Towns decoded | 7 | 7 | 5 |
| Town/item records | 343 | 343 | 245 |
| Town/item element size | 238 | 238 | 238 |

The paired DOS/Windows scenario saves have the same size (542,709 bytes), date,
scenario reference, town/item keys, and RNG state. They agree at 541,674 byte
positions, or 99.8093% of the file. Section-aware comparison found:

- all 24 tags at identical offsets and all payload sizes equal;
- 56 differing bytes inside the two inferred transient pointer fields across
  seven town records;
- 370 changed values among the four tracked market floats;
- every changed tracked float within 1–4 ULPs.

Those results support using one shared data/save compatibility layer for both
original builds while treating platform-dependent pointer bytes and floating
point rounding as normalization concerns.

## Palette, images, and maps

- Both builds contain the same 776-byte, 256-color standard palette.
- All 15 maps resolve to a 240×198 eight-byte-cell grid, render as recognizable
  map overviews, and place every city coordinate inside that grid.
- Every rendered map was independently opened as a valid indexed PNG at 2× scale.
- 606 uncompressed indexed images are exportable from 19 resource files.
- 555 more are exportable from 12 game-set auxiliary files, for 1,161 decoded
  image records across the supplied DOS data.
- Direct (`.PIC`), sequential, offset-indexed, named, and mixed-resource exports
  were checked visually against portraits, terrain, firm icons, scenario buttons,
  and game-set title art.
- Because the corresponding source assets are byte-identical, DOS and Windows
  exports are also byte-identical.

## Executable loader boundaries

- Both known executable profiles pass exact hash and direct-call-count gates.
- The shared file layer resolves to seven matching DOS/Windows contracts.
- Read-open has 24 direct DOS callers and 23 direct Windows callers; create has
  six in each build.
- Six Windows file APIs resolve to exact PE IAT slots and code references.
- Referenced strings cover resources, game sets, maps, saves, scenarios, and
  support files in both builds.
- The synthetic framed-record probe preserves exact records, zero-extends
  smaller records, skips oversized tails, and rejects declared truncation.

## UI and support resources

- All three fonts resolve to an exact 88-byte header, a monotonic cumulative
  boundary table, and an MSB-first one-bit bitmap with no unexplained trailing
  bytes. Their 286 total glyph slots export to valid indexed PNG atlases.
- `TEXT.RES` resolves to one 80×25 CP437/VGA text screen with exact character
  and attribute preservation.
- All four `LANGUAGE.RES` glyphs, seven cursor images, eight cursor rows, and
  fifteen help rectangles parse in their original order. Every nonblank cursor
  image offset resolves against `I_CURSOR.RES`.
- Each installation's nine plan files parse to ten ordered categories. The
  `.PLA`/`.PLP` files contain 79, 111, and 126 records for the three game sets;
  the three `.PLO` files contain zero records. Every record resolves nine grid
  cells and nine stable item identifiers.
- Both builds' `CAPITAL.CFG` and `CAPITAL.HOF` files pass compatible-record
  framing checks. Their differing user state does not change the structure.

## Automated suite

The development suite contains 121 tests covering DBF parsing, all three
resource-container patterns, palettes, indexed PNG encoding, image export and
overwrite protection, map structure/rendering, version-100 save framing, save
comparison, installation-root discovery, CLI exit behavior, and malformed input rejection.
It also covers synthetic PE32 sections and imports, LE objects and names,
printable-string extraction, plain-MZ handling, executable CLI routing, and the
cross-build survey workflow. All fixtures are generated synthetically and
contain no original game data. Loader tests additionally cover PE virtual
addresses and IAT slots, LE page/object-relative references, cross-build report
generation, compatible-record size handling, and malformed truncation.
UI tests additionally cover font bit order and empty glyphs, text and language
containers, cursor offset resolution, ordered help geometry, empty plan/help
cases, malformed offsets, 3×3 plan records, and framed config/HOF data.

Audio tests cover independent WAV decoding, sample preservation, the original
terminal-padding variant, malformed PCM/IFF lengths, bounded XMIDI recursion,
opaque event handling, stable bank order, export collisions, filename traversal,
loose-file mismatches, unassigned settings, exact-executable profile rejection,
and CUE geometry with unsupported and malformed layouts. All 24 audio tests use
newly generated fixtures.

Format-gate tests additionally cover the 26-format machine-readable catalog,
mandatory provenance for all nine currently inferred field records, exhaustive
region coverage, preservation-writer mutation, disabled save writing, directory
corpus selection, save normalization limits, fuzz bounds, and deterministic
fuzz transcript reproduction.

Repository-gate tests additionally cover ledger reconciliation, unsupported and
extensionless families, incomplete inventories, false completion states,
experiment provenance/checkpoint/tolerance constraints, staged payload checks,
version consistency and safe source-archive extraction. The 27 new fixtures
are synthetic and introduce no original payloads.

The package gate builds a wheel and source distribution in a tracked-only
temporary copy, runs all 121 tests from the extracted source distribution,
rebuilds an equal-content wheel, and installs it offline in a fresh environment
outside the checkout. Local Linux checks pass for installed metadata, CLI
version, both bundled schemas, catalog validation and a 32-iteration fuzz smoke
test. Cross-platform results are recorded by the Windows/macOS/Linux CI jobs.
The inventory recount is directory-only evidence from currently truncated local
media; see [content coverage](content-coverage.md) for the precise limitation.

## Reconstruction and fuzz gates

The supplied DOS installation reconstructs 76 selected non-save files exactly:
74 structurally segmented files and two opaque files across 22 source formats.
Windows reconstructs 101 files: 99 structural and the same two opaque inputs
across 23 formats. The opaque inputs remain `JOB.RTI` and `JOB.RTX`. Audio adds
`CAPITAL.SND` to both selections and 25 loose WAVs to Windows; these totals do
not claim coverage of the entire retail disc.

The fixed 2,048-iteration synthetic fuzz campaign covers 21 generated inputs.
With seed `0x4341502B2B`, it accepts 792 structurally valid mutations, rejects
1,256 malformed mutations, reports no unexpected exception, and produces
transcript SHA-256
`c8e3d89eab90c206545ca92a3d7fb78c1084e19a3a399dcbddc761f7ceacae83`.

The matched DOS/Windows save comparison satisfies every structural precondition
for normalization. It classifies 677 of the 1,035 same-position differing bytes
inside registered pointer or tracked-float locations and leaves 358 differences
explicitly unclassified. All 370 changed tracked floats remain within the
observed one-to-four-ULP cross-build range.

## Audio evidence

- All 25 `SOUND.RES` members match the PCM data in their extensionless Windows
  WAV counterparts, including all ten missing-terminal-padding variants.
- Both 25-file export profiles decode with Python's independent `wave` reader
  to the exact original samples: 11,000 Hz for DOS and 11,127 Hz for Windows.
- All 24 `MUSIC.RES` members have one bounded XMID sequence; their unchanged
  exports pass framing checks and byte-for-byte source comparisons.
- Both sound-settings files have exactly nine words. The 29 bank, loose-effect
  and settings inputs used in export validation retained their original hashes.
- The exact-build survey reproduces Windows/DOS address mappings and PCM
  equality. It does not execute either game or validate audible behavior.
- CUE geometry is tested synthetically. The retail layout and prior OGG
  comparison in [audio evidence](audio.md) are historical complete-disc results;
  fresh BIN integrity and sample checks require a complete user-owned input.
