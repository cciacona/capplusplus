# Cap++

**Cap++** is an independent, open-source reimplementation of **Capitalism Plus**
for modern systems. The project is currently in its reverse-engineering and data
compatibility phase; it is not yet a playable replacement.

`capplus-inspect` is the project's dependency-free, non-destructive command-line
inspector and exporter for user-supplied Capitalism Plus installations and data
files. It turns the original binary formats into versioned JSON that the future
engine and parity-test harness can consume.

The project contains no game executable, artwork, audio, maps, scenarios, or
other proprietary game data. You must provide files from your own copy.

## Capabilities

- Validate a DOS or Windows installation directory, or inspect its ZIP directly.
- Recognize the analyzed unmodified DOS and Windows executables by SHA-256.
- Verify all 72 files shared by the supplied DOS and Windows builds.
- Parse `.SET` game sets as named containers of embedded dBASE tables.
- Parse the confirmed 380,244-byte `.MAP` core and 29-byte city records.
- Decode the core as a 240×198 grid of 47,520 eight-byte cells and render its
  palette-indexed overview with optional city markers.
- Decode the original 256-color palette and export supported indexed images to
  lossless PNG with exact palette indices and optional transparency.
- Decode original bitmap fonts, DOS text screens, supplemental language glyphs,
  cursor metadata/images, and context-help rectangles.
- Parse 3×3 layout plans plus compatible-record configuration and hall-of-fame
  support files while keeping unknown fields explicit.
- Identify named, offset-indexed, and sequential-image resource containers.
- Parse version-100 `.SAV` metadata and the complete 24-section marker chain.
- Decode the confirmed town array, town/item keys, selected market floats, and RNG state.
- Compare two saves section-by-section and measure cross-build float drift in ULPs.
- Inspect MZ/LE and PE32 executable structure, including objects, sections, and imports.
- Survey original file-loader boundaries across the DOS and Windows builds.
- Emit human-readable summaries or deterministic, schema-versioned JSON.

Original inputs are never modified. ZIP archives are streamed without extraction,
and export commands refuse to replace existing files unless `--force` is supplied.

## Requirements

- Python 3.10 or newer
- No third-party runtime packages

## Install

From the extracted project directory:

```powershell
py -m pip install .
capplus-inspect --version
```

On Linux or macOS, use `python3 -m pip install .` if `py` is not available.

You can also run directly from a checkout:

```bash
PYTHONPATH=src python3 -m capplus_inspect --version
```

## Examples

Inspect and validate a complete installation:

```powershell
capplus-inspect inspect "C:\Games\Capitalism Plus" --deep --require-clean
```

Inspect the original directory ZIP without extracting it:

```powershell
capplus-inspect inspect "Capitalism Plus DOS.zip" --deep
```

Export a stable machine-readable inventory:

```powershell
capplus-inspect inspect "Capitalism Plus WIN.zip" --deep --json > windows-build.json
```

Inspect a game set, including the first two rows from every embedded table:

```powershell
capplus-inspect inspect "GAMESET\1STD.SET" --rows 2 --json
```

Inspect and compare saves:

```powershell
capplus-inspect inspect "21ST_001.SAV"
capplus-inspect compare-saves "21ST_001.SAV" "QUAA_001.SAV"
capplus-inspect compare-saves "21ST_001.SAV" "QUAA_001.SAV" --json
```

Inspect an executable without including proprietary strings in the report:

```powershell
capplus-inspect inspect "CAPPLUS.EXE" --json
capplus-inspect inspect "CapWin.exe" --include-strings --minimum-string-length 8 --json
```

Export sprites and render a map:

```powershell
capplus-inspect export-images "RESOURCE\I_PERSON.RES" ".\people" --palette "RESOURCE\PAL_STD.RES"
capplus-inspect render-map "MAPS\WORLD.MAP" ".\world.png" --palette "RESOURCE\PAL_STD.RES" --scale 4
```

Inspect UI resources and export a font atlas:

```powershell
capplus-inspect inspect "RESOURCE\HELP.RES" --json
capplus-inspect inspect "GAMESET\1STD.PLA" --json
capplus-inspect export-font "RESOURCE\FNT_STD.RES" ".\font-std" --scale 4
```

Exit codes are `0` for success, `2` for an unreadable or invalid input, and `3`
when `--require-clean` detects missing or changed core files.

## Tests

The tests are synthetic and redistributable; they do not require or contain game
data.

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -t . -v
```

## Documentation

- [Observed binary formats](docs/formats.md)
- [Executable survey](docs/executables.md)
- [Original file-loader contracts](docs/loaders.md)
- [UI, layout-plan, and support-file formats](docs/ui-resources.md)
- [Validation results](docs/validation.md)
- [Clean-room development policy](CLEAN_ROOM.md)
- [Security policy](SECURITY.md)
- [Contributing](CONTRIBUTING.md)
- [Release history](CHANGELOG.md)
- [Complete 1.0 parity roadmap](ROADMAP.md)

## Status and caveats

This is reverse-engineering tooling, not yet a playable engine. Fields described as
“confirmed” have been checked against the supplied files; fields described as
“inferred” still need controlled experiments. The JSON schema starts at version
`1`, but the project itself is pre-1.0 and may gain new fields.

Capitalism Plus is the property of its respective rights holders. This project
is an independent compatibility effort and is not affiliated with or endorsed by
them. Laws governing reverse engineering differ by jurisdiction; contributors
are responsible for following applicable law.

## License

New source code and documentation in this repository are available under the
[MIT License](LICENSE). That license does not apply to the original game or its
assets.
