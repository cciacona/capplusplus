# UI, layout-plan, and support-file formats

This document specifies the Capitalism Plus UI and support formats decoded by
`capplus-inspect`. All JSON results use top-level `schema_version: 1`. All
integers are little-endian, and all offsets are from the start of the containing
file unless stated otherwise.

The terminology in [Observed Capitalism Plus formats](formats.md) applies:
**confirmed** fields are enforced by the parser and supported by every supplied
file; **inferred** meanings are structurally strong but still need a controlled
gameplay experiment; **unknown** bytes remain explicitly identified.

No original text, glyph bitmap, cursor image, or plan record is stored in the
repository. Tests construct small synthetic files with the same framing.

Despite their names, the supplied `TEXT.RES` and `LANGUAGE.RES` are graphical
text-support assets rather than localization string tables: the former is a DOS
text-mode screen and the latter contains four indexed glyph images. The
executables reference an optional `TRANSLAT.RES`, but no such file exists in
either supplied installation or the retail-disc corpus, so its format is not
claimed here.

## Evidence and provenance

The formats were established from two independent sources:

1. byte-level comparison of the supplied DOS and Windows installations; and
2. bounded static analysis of the known, unmodified Windows executable, with
   the executable retained only as a local input.

The three fonts, the five UI resources, and all nine layout-plan files are
byte-identical between the supplied DOS and Windows installations. The config
and hall-of-fame files use the same framing in both builds but contain different
user state.

Relevant Windows routines and references are recorded as reproducibility
anchors, not as copied code:

| Subject | Windows virtual address | Observed operation |
|---|---:|---|
| Font load | `0x00414F60` | Reads the 88-byte header, boundaries, and bitmap |
| Glyph width | `0x00415070` | Subtracts adjacent cumulative boundaries |
| Plan read | `0x00436CE0` | Reads category IDs, arrays, records, and references |
| Plan write | `0x00436C50` | Writes the same ordered plan structure |
| Plan reference write | `0x00436DC0` | Converts nine item IDs to stable identifiers |
| Plan reference read | `0x00436EC0` | Resolves stable identifiers back to item IDs |
| Compatible array read/write | `0x00476500` / `0x004764B0` | Serializes the 29-byte array header and records |
| Config read/write | `0x00446CB0` / `0x00446C90` | Reads/writes one 737-byte compatible record |
| Hall of fame read/write | `0x0041E0F0` / `0x0041E030` | Reads/writes 580- and 13-byte records |

The `.PLO`, `.PLA`, and `.PLP` selection references occur at `0x00477F1D`,
`0x00477ECB`, and `0x00477EC4`, respectively. See
[Original file-loader contracts](loaders.md) for the file abstraction and
address-mapping method.

## Bitmap fonts (`FNT_*.RES`)

JSON format name: `capitalism_plus_bitmap_font`.

Each font has an 88-byte header, a cumulative horizontal-boundary table, and a
one-bit bitmap sheet:

| Offset | Type | Meaning |
|---:|---|---|
| `0x00` | `u8[88]` | Legacy header; unassigned bytes remain opaque |
| `0x24` | `u16` | First character code |
| `0x26` | `u16` | Last character code, inclusive |
| `0x50` | `u16` | Bitmap row stride in bytes |
| `0x52` | `u16` | Glyph/sheet height |
| `0x58` | `u16[glyph_count + 1]` | Cumulative X boundaries |
| after boundaries | `u8[row_stride * height]` | One-bit bitmap sheet |

Bits are most-significant-bit first within each byte. The bitmap is row-major.
Glyph `i` occupies columns `boundary[i]` through `boundary[i + 1] - 1`; equal
adjacent boundaries encode a valid zero-width glyph. Padding bits may follow the
last boundary to complete the final byte of each row.

The parser requires monotonic boundaries, a final boundary no greater than the
row stride in bits, and an exact file-size match. `export-font` writes the used
portion of the sheet as a lossless two-color indexed PNG and a schema-versioned
manifest.

Observed files:

| File | Codes | Glyph slots | Row stride | Height | Used width |
|---|---:|---:|---:|---:|---:|
| `FNT_STD.RES` | 32–127 | 96 | 88 | 11 | 700 |
| `FNT_SAN.RES` | 32–127 | 96 | 67 | 11 | 536 |
| `FNT_MID.RES` | 33–126 | 94 | 146 | 23 | 1,164 |

## DOS text screens (`TEXT.RES`)

JSON format name: `capitalism_plus_text_screens`.

`TEXT.RES` is an offset-only container. Each ordered member is exactly 4,000
bytes and represents an 80×25 DOS text screen. Every two-byte cell contains a
CP437 character code followed by its VGA text attribute byte. JSON preserves:

- the decoded 80-character rows;
- the original character-code rows as hexadecimal; and
- the original attribute rows as hexadecimal.

The supplied resource contains one screen. Its geometry is confirmed by the
4,000-byte member, character/attribute alternation, and the reconstructed 80×25
display. The normal VGA foreground/background interpretation of the attribute
byte is not required by the parser.

## Supplemental language glyphs (`LANGUAGE.RES`)

JSON format name: `capitalism_plus_language_glyphs`.

This is an offset-only container of direct indexed images. Each member is
`u16 width`, `u16 height`, then exactly `width * height` palette indices. The
supplied file contains four ordered glyph images: one 8×10 and three 8×9. Their
semantic character assignments remain unknown, so the schema deliberately uses
stable numeric indices rather than guessed character names.

## Cursors (`CURSOR.RES` and `I_CURSOR.RES`)

JSON format names: `capitalism_plus_cursor_table` and
`capitalism_plus_cursor_images`.

`CURSOR.RES` is a dBASE III table with eight records and this exact schema:

| Field | DBF type | Width | Meaning |
|---|---|---:|---|
| `FILENAME` | `C` | 8 | Cursor identifier |
| `HOTSPOT_X` | `N` | 3 | X hotspot |
| `HOTSPOT_Y` | `N` | 3 | Y hotspot |
| `BITMAPPTR` | `C` | 4 | Raw little-endian image-stream offset, or four spaces |

Despite its declared character type, `BITMAPPTR` is binary. A zero value is a
valid reference to the first image; four spaces mean no image reference.

`I_CURSOR.RES` is a sequential indexed-image stream. A cursor offset points to
the outer `u32 record_size` of one image, not its pixel payload. When the two
files are inspected together, every nonblank supplied reference resolves to one
of the seven images. The cursor table retains identifier and ordering even when
no companion image file is available.

## Context help (`HELP.RES`)

JSON format name: `capitalism_plus_context_help`.

`HELP.RES` is a named container. Member names are stable topic identifiers, and
member payloads are CP1252 text with CRLF line endings. A topic contains:

1. a title line;
2. an underline line;
3. a blank line; and
4. zero or more form-feed-separated help regions.

Each nonempty region starts with `left, top, right, bottom`, followed by a label
line and zero or more description lines. A final DOS `0x1A` marker is accepted
and reported. The parser preserves topic order, region order, rectangle values,
labels, and original description line breaks. Empty topic members are valid.

The supplied file has one named topic and fifteen ordered rectangles.

## Layout plans (`.PLA`, `.PLO`, `.PLP`)

JSON format name: `capitalism_plus_layout_plans`.

The file begins with `u16 category_count`, followed by this structure once per
category:

| Order | Size | Meaning |
|---:|---:|---|
| 1 | 4 | Category identifier, NUL-padded when shorter |
| 2 | 29 | Serialized dynamic-array header |
| 3 | `record_count * 127` | Contiguous layout-plan records |
| 4 | `record_count * 72` | Contiguous stable item-reference records |

The 29-byte array header is the original engine's packed dynamic-array state:

| Header offset | Type | Meaning |
|---:|---|---|
| `0x00` | `i32` | Allocated record capacity |
| `0x04` | `i32` | Allocation growth increment |
| `0x08` | `i32` | Selected/current one-based index |
| `0x0C` | `i32` | Record count |
| `0x10` | `i32` | Record size; `127` in this format |
| `0x14` | `i32` | Sort-key offset; observed as `-1` |
| `0x18` | `u8` | Unknown control byte |
| `0x19` | `u32` | Transient process pointer; never dereferenced by the inspector |

Each 127-byte record contains a 29-byte CP1252 plan name at offset `0x00`, a
one-based record number at `0x1D`, and two ordered arrays of nine `u16` values:

- offsets `0x25..0x36`: inferred functional-unit IDs;
- offsets `0x37..0x48`: item IDs.

Those positions correspond to the plan's 3×3 grid in row-major order. The
associated 72-byte reference record contains nine consecutive eight-byte stable
item identifiers in the same order. The executable explicitly converts between
the numeric IDs and these identifiers during save/load, confirming their role.

Bytes `0x1F..0x24`, the 36-byte pointer-like region at `0x49..0x6C`, and the
18-byte tail at `0x6D..0x7E` remain unknown. The JSON result reports their
locations and hashes without assigning semantics.

All supplied `.PLA` and `.PLP` pairs are byte-identical within each game set.
The three `.PLO` files contain the ten category headers with zero plan records.

## Configuration (`CAPITAL.CFG`)

JSON format name: `capitalism_plus_configuration`.

The file is one original compatible record: `u16 saved_size` followed by a
logical 737-byte payload. The normal supplied prefix is `737`. As in saves, a
shorter record is zero-extended logically, an oversized tail is skipped, and a
zero prefix means the caller's expected size.

The 737-byte object layout is not yet semantically assigned. The inspector
reports its physical and logical hashes and emits ordered, offset-bearing
candidate ASCII text fields as an explicitly heuristic convenience. Candidate
values ending in `.SCT` are also listed as scenario references. No candidate is
treated as a stable field until executable use or a controlled configuration
change establishes its meaning.

## Hall of fame (`CAPITAL.HOF`)

JSON format name: `capitalism_plus_hall_of_fame`.

The file contains two compatible records in order:

| Record | Expected logical size | Current interpretation |
|---:|---:|---|
| 1 | 580 | Hall-of-fame/leaderboard state |
| 2 | 13 | NUL-terminated save filename |

The first payload divides exactly into ten 58-byte slots in the original
object. Their individual field meanings remain unknown because both supplied
leaderboards are empty. The parser preserves slot order and reports hashes,
nonzero-byte counts, and offset-bearing candidate text without inventing names
or score fields. The second record is decoded as CP1252 and also retained as
hexadecimal bytes.
