# Validation record through the 0.3 development snapshot

The tool was checked against the user-supplied, unmodified DOS and Windows
game directories and three mutually compatible version-100 saves.

## Installations

| Check | DOS directory ZIP | Windows directory ZIP |
|---|---:|---:|
| Files under detected root | 149 | 113 |
| Shared core files matched | 72 / 72 | 72 / 72 |
| Executable recognized | `CAPPLUS.EXE` | `CAPWIN.EXE` |
| Game sets parsed | 3 | 3 |
| Maps parsed | 15 | 15 |
| Resources inspected | 33 | 33 |
| Deep-inspection errors | 0 | 0 |

The 72 shared game-set, map, and resource files are byte-identical between the
two supplied builds. Their expected SHA-256 values are embedded only as hashes;
no source file bytes are included.

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

## Automated suite

The development suite contains 39 tests covering DBF parsing, all three
resource-container patterns, palettes, indexed PNG encoding, image export and
overwrite protection, map structure/rendering, version-100 save framing, save
comparison, installation-root discovery, CLI exit behavior, and malformed input rejection.
It also covers synthetic PE32 sections and imports, LE objects and names,
printable-string extraction, plain-MZ handling, executable CLI routing, and the
cross-build survey workflow. All fixtures are generated synthetically and
contain no original game data. Loader tests additionally cover PE virtual
addresses and IAT slots, LE page/object-relative references, cross-build report
generation, compatible-record size handling, and malformed truncation.
