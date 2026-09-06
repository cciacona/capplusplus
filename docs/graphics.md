# Graphics catalog and presentation evidence

`catalog-graphics` produces a deterministic, payload-free inventory of every
currently decoded installation image and font glyph. It resolves cursor image
references and records palette identities, storage order and presentation
unknowns. This is the data foundation for the renderer; it does not certify
animation timing, per-call palette selection or complete presentation parity.

## Commands

```powershell
capplus-inspect catalog-graphics "C:\Games\Capitalism Plus" --require-reference
capplus-inspect catalog-graphics "Capitalism Plus DOS.zip" --json > graphics-catalog.json
capplus-inspect compare-graphics "Capitalism Plus DOS.zip" "Capitalism Plus WIN.zip" --json
```

Directory and ZIP inputs use the same normalized relative paths. ZIPs are read
without extraction. The catalog contains no host paths, timestamps, executable
identities, ZIP metadata, RGB tables or bitmap payloads, so identical graphics
produce the same catalog regardless of platform, installation location or
archive ordering. Its hashes are fingerprints of user-owned data, not assets.

Exit 2 indicates malformed, ambiguous or unsupported input. Comparison exits 3
when catalogs differ. `--require-reference` exits 3 unless every known graphics
source matches its reference hash. Without that option, valid custom or partial
sets can be inspected; missing, changed and additional sources remain explicit.
Two equal partial catalogs do not become a complete reference installation.

## Scope and validated inventory

The selector includes `RESOURCE/I_*.RES`, `LANGUAGE.RES`, `FNT_*.RES`, both
palette resources, `CURSOR.RES`, and game-set `.II`, `.II2`, `.DFI`, `.FI`, `.IP`
and `.PIC` files. It deliberately does not treat arbitrary sound, text, map or
other resources as images because their first bytes happen to resemble image
dimensions. An unsupported selected graphics source causes an error instead of
silently reducing coverage.

Both intact supplied installations produce this inventory:

| Category | Count |
|---|---:|
| Reference source files matched | 37 / 37 |
| Indexed images | 1,161 |
| Font glyph slots | 286 |
| Total image/glyph entries | 1,447 |
| Storage groups | 34 |
| Palette resources | 2 |
| Cursor-table rows | 8 |
| Resolved cursor-image references | 7 |
| Explicitly blank cursor references | 1 |
| Non-image members retained as metadata | 10 |

The 1,161 indexed images comprise 606 resource images and 555 game-set images.
The three fonts contribute 286 slots, including any empty slots. Five members
in each of `I_SCEN.RES` and `I_SCENW.RES` do not decode as indexed images; their
names, source spans and hashes remain visible in `opaque_members`.

The two catalogs are exactly equal, with catalog SHA-256
`7da5ff39258adc44e0b46dfd50c6db550d872f357a8e50ce63b5977a1ca4f824`.
These totals concern supported installation graphics. They do not close the
[retail inventory gap](content-coverage.md), turn the map overview into a decoded
world renderer, or establish complete animation semantics.

## Stable identities and source geometry

Catalog version 1 uses canonical lower-case paths with forward slashes and
the following identities:

| Entry | Identifier form | Ordering |
|---|---|---|
| Indexed image | `resource/i_example.res#image:000003` | Original zero-based member or stream index |
| Font glyph | `resource/fnt_example.res#glyph:065` | Original numeric glyph code |
| Cursor binding | `resource/cursor.res#cursor:002` | Original one-based DBF record number |
| Storage group | `resource/i_example.res#storage` | Original file member order |

Skipped non-image members never renumber later images. Names remain metadata
because repeated names or replacements must not erase a record's identity.
Changing pixels can retain an ID while changing its content hash. The ID alone
is not a claim of equivalence between modified installations.

For an indexed image, `payload_offset` addresses its `u16 width`, `u16 height`
and exact index buffer. `record_offset` includes the preceding four-byte size
prefix for sequential streams and otherwise equals `payload_offset`. A font
glyph instead has a bit range, bitmap offset and row stride because its rows
are slices of a shared one-bit sheet, not a contiguous indexed-image payload.

Each source has a hash and structural format; each image/glyph has dimensions
and a pixel hash. The catalog digest hashes its JSON object before adding
`catalog_sha256`, using sorted keys, ASCII escaping and compact separators.
Lists retain their documented deterministic order. `compare-graphics` also
reports changed source files, so a palette, cursor or opaque-member change is
visible even when no image pixels changed.

## Cursor bindings and hotspots

`CURSOR.RES` supplies identifiers, X/Y hotspots and either a blank bitmap slot
or an absolute offset into `I_CURSOR.RES`. That offset addresses the sequential
record prefix, which is four bytes before the image payload. Offset zero is a
valid image reference and must not be confused with a blank slot.

| Cursor identifier | Image stream index | Hotspot X | Hotspot Y |
|---|---:|---:|---:|
| `EDIT` | Blank reference | 10 | 10 |
| `NORMAL` | 2 | 0 | 0 |
| `PRESSED` | 3 | 0 | 0 |
| `WAIT` | 4 | 10 | 10 |
| `ZOOM` | 0 | 10 | 8 |
| `M_NORMAL` | 6 | 0 | 0 |
| `M_PRESS` | 1 | 0 | 0 |
| `M_WAIT` | 5 | 10 | 10 |

A present image source with a dangling reference is malformed input. If the
image source is absent from a partial set, the binding is explicitly unresolved.
The blank `EDIT` row stays blank; no fallback image or procedural cursor is
invented. Generic image origins and non-cursor hotspots remain unknown.

## Storage order, animation and transparency

Groups represent source storage order. A sequence of portraits, product
pictures, button states or town icons is not automatically an animation.
`frame_durations` and `loop` are null until executable or controlled evidence
assigns them. The dimensions/index-buffer record itself contains no timing
field. Similar names, repeated dimensions and numerical suffixes are not
sufficient to label frames or prescribe playback order.

Indexed image records contain no alpha channel or transparent-color field.
The catalog reports index 245 as the existing export/preview candidate and
counts its pixels. It leaves the original transparency mode unverified because
an opaque blit and a keyed blit may use the same source image differently.
`PAL_STD.RES` is likewise the preview default, not a verified per-image palette
binding. Font data is a one-bit mask whose runtime foreground/background choices
are separate from the source bits.

## Palette loading

Static analysis establishes a conversion that the prior exact-source PNG
exports did not emulate. These addresses apply only to the executable hashes
in [audio evidence](audio.md#reference-inputs), with the same PE/LE mapping as
the [loader survey](loaders.md).

| Build and address | Observed operation |
|---|---|
| Windows `0x0044E050` | Seek past eight header bytes, read 768 RGB bytes, shift each channel right by two |
| Windows `0x0040C7A0` | Shift six-bit channels left by two into four-byte palette entries, then submit them to DirectDraw |
| DOS `0x0008C89E` | Read the same RGB region and integer-divide each unsigned channel by four |
| DOS `0x00094093` | Submit those six-bit components through VGA DAC ports `0x3C8`/`0x3C9` |

For Windows, the load/upload composition is therefore
`submitted_channel = (source_channel >> 2) << 2`, or `source_channel & 0xFC`.
It discards the lowest two bits; it does not rescale 63 to 255. The four-byte
entry and call layout match Microsoft's
[IDirectDrawPalette::SetEntries contract](https://learn.microsoft.com/en-us/windows/win32/api/ddraw/nf-ddraw-idirectdrawpalette-setentries).
These are submitted palette values, not measurements of monitor output, gamma
or color management. DOS output records retain the six-bit DAC values without
inventing an eight-bit hardware-response curve.

Windows initialization calls the standard-palette wrapper at `0x0041D7C2` with
`RESOURCE/PAL_STD.RES`. The separate interface-color initializer at
`0x00433F30` passes `RESOURCE/IFCOLOR.RES` to the same loader with immediate
activation disabled. Subsequent interface selection, fades, palette animation
and recoloring require further tracing; neither file is assigned universally
to every original draw operation.

| Palette | Source file SHA-256 | Colors changed by Windows quantization |
|---|---|---:|
| `PAL_STD.RES` | `8a20759e6063baa177d632324ec10b1c76b53e756ece23b44cd46526ce595d5c` | 37 / 256 |
| `IFCOLOR.RES` | `011a0c1a977665e24b41400e729175063ae8342e506547912d1e4479b82d3920` | 98 / 256 |

Catalog palette records include fingerprints for source RGB, six-bit DAC values
and submitted Windows RGB. No original color table is embedded in the report.

## Optional Windows palette export

Existing export defaults retain exact source RGB. Select the audited Windows
conversion explicitly when comparing presentation:

```powershell
capplus-inspect export-images "RESOURCE\I_FIRM.RES" ".\private-corpus\firm-windows" --palette "RESOURCE\PAL_STD.RES" --palette-profile windows
capplus-inspect render-map "MAPS\WORLD.MAP" ".\private-corpus\world-windows.png" --palette "RESOURCE\PAL_STD.RES" --palette-profile windows
```

The profile changes PNG palette colors only. Pixel indices, transparency choice,
geometry and original inputs remain unchanged. Manifests identify both the source
palette hash and the submitted output palette hash. `--palette-profile source`
is the default and preserves the previous behavior. Neither profile implements
runtime fades, palette cycling or per-image palette selection.

## Validation and remaining work

Synthetic tests cover stable IDs, skipped-member order, empty font slots, cursor
offset zero, blank/dangling references, directory/ZIP equivalence, source changes,
path collisions, ambiguous roots, traversal, input budgets, and command exit
codes. PNG checks independently inspect PLTE and decompressed IDAT chunks to
verify that the Windows profile changes colors without changing indexed pixels.

Inputs are bounded to 20,000 paths, 16 MiB per graphics source, 1 MiB per font,
256 MiB of selected source data and 100,000 combined image, glyph, opaque-member
and cursor-binding records across all sources. The record budget is checked
before each catalog append. ZIP and directory sizes are
checked before reads. Sequential record counts are bounded before allocating
decoded image records. No exporter or decoder dependency is added.

Issue [#6](https://github.com/cciacona/capplusplus/issues/6) retains the remaining
work: real animation groups/timing, non-cursor placement, per-call transparency,
palette selection/cycling, and original-game presentation experiments. The
catalog provides stable references for that evidence; storage order alone does
not establish it.
