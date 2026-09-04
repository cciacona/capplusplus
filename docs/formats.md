# Observed Capitalism Plus formats

This document describes only structure that `capplus-inspect` currently reads.
All integers are little-endian. Offsets are relative to the start of the
containing file or payload unless stated otherwise.

Terminology:

- **Confirmed**: consistent across every relevant supplied file and checked by
  the parser.
- **Inferred**: strongly supported by cross-file or cross-build comparison, but
  still needs a controlled in-game experiment.
- **Unknown**: preserved as opaque bytes.

The versioned, machine-readable counterpart to these notes is the
[binary-format catalog](../src/capplus_inspect/schemas/format-catalog-v1.json).
Its provenance, exact-reconstruction, normalization, and fuzzing requirements
are described in [Format completeness and safety gates](format-gates.md).

## Game sets (`.SET`)

A game set is a named container. Its members are complete dBASE streams.

| Offset | Type | Meaning |
|---:|---|---|
| `0x00` | `u16` | Member count, `N` |
| `0x02` | `N + 1` directory entries | Member index plus sentinel |

Each 13-byte directory entry is:

| Entry offset | Type | Meaning |
|---:|---|---|
| `0x00` | `char[9]` | NUL-terminated ASCII member name |
| `0x09` | `u32` | Absolute payload offset |

The final sentinel has an empty name and an offset equal to the file size. A
member's size is the next entry's offset minus its own offset.

All three observed sets contain dBASE III-compatible tables. `1STD.SET` contains
16: `RICH`, `ITEMCLAS`, `FIRMJOB`, `JOB`, `RAW`, `GROUP`, `PERSON`, `METHOD`,
`FARMPROD`, `HEADER`, `TOWN`, `FIRM`, `ITEMPAE`, `ITEM`, `FARMLIVE`, and
`FARMCROP`.

The DBF parser exposes field names, types, widths, decimal counts, row counts,
and optionally decoded rows. DBF definitions are therefore immediately usable
as product/economy input for a replacement engine without hard-coding the
shipped data.

## Palettes (`PAL_STD.RES`, `IFCOLOR.RES`)

Both observed palette resources are 776 bytes:

| Offset | Type | Meaning |
|---:|---|---|
| `0x00` | `u32` | Total size, `776` |
| `0x04` | `u32` | Unknown header word; preserved and reported |
| `0x08` | `RGB[256]` | 256 consecutive three-byte RGB colors |

The channels already use the 0–255 range and require no VGA-style multiplication.
Original uncompressed images store one palette index per pixel. Index 245 is the
observed transparent background for the sprite resources; the exporter makes it
transparent by default but can preserve it as opaque.

## Maps (`.MAP`)

The first 380,244 bytes have four confirmed regions:

| Offset | Size | Meaning |
|---:|---:|---|
| `0x00000` | 22 | NUL-terminated internal map path |
| `0x00016` | 30 | NUL-terminated display name |
| `0x00034` | 380,160 | 240×198 grid of eight-byte cells |
| `0x5CD34` | 32 | Undecoded footer |

The grid contains 47,520 row-major cells. Byte offset `0x03` within each cell is
the `PAL_STD.RES` index used by the game's overview map. Rendering this byte
directly produces the recognizable region/world image, and all city coordinates
fall within the same 240×198 coordinate space. Meanings of the other seven bytes
and the footer remain unknown.

The bytes after the 380,244-byte core are zero or more 29-byte city records:

| Record offset | Type | Meaning |
|---:|---|---|
| `0x00` | `u16` | X coordinate |
| `0x02` | `u16` | Y coordinate |
| `0x04` | `u32` | Population/value field |
| `0x08` | `char[21]` | NUL-terminated city name |

The parser rejects a file shorter than the fixed core or a city tail not evenly
divisible by 29.

## Indexed image export

`capplus-inspect export-images` supports every uncompressed image layout currently
identified:

- a direct `u16 width`, `u16 height`, and `width * height` index buffer;
- direct images stored as members of named or offset-only containers;
- sequential images whose outer `u32` record size precedes that same payload.

PNG output uses indexed color (PNG color type 3), an exact 256-entry `PLTE`, and
an optional `tRNS` entry. Integer scaling duplicates indices without filtering.
The exporter writes a JSON manifest containing source offsets, dimensions, source
and pixel hashes, and output filenames. Mixed containers such as `I_SCEN.RES`
export image members while leaving non-image members untouched.

## Resources (`.RES` and related files)

The resource inspector detects three structural families before falling back to
an opaque binary description.

### Named container

Identical directory structure to `.SET`: `u16 N`, followed by `N + 1` entries of
`char[9]` and `u32 offset`.

### Offset-only container

| Offset | Type | Meaning |
|---:|---|---|
| `0x00` | `u16` | Member count, `N` |
| `0x02` | `u32[N + 1]` | Absolute offsets; final value is file size |

### Sequential image stream

Repeated records with no global directory:

| Offset | Type | Meaning |
|---:|---|---|
| `0x00` | `u32` | Payload size, equal to `4 + width * height` |
| `0x04` | `u16` | Width |
| `0x06` | `u16` | Height |
| `0x08` | `u8[width * height]` | Indexed pixels |

An indexed-image member in a container omits the outer `u32` and begins with the
width and height. Palette-aware indexed-PNG export is described above.

## UI, layout-plan, and support formats

The following filename-specific formats now have strict parsers and distinct
schema names:

- `TEXT.RES` 80×25 CP437/VGA text screens;
- `LANGUAGE.RES` supplemental indexed glyphs;
- `FNT_*.RES` one-bit bitmap fonts and cumulative glyph boundaries;
- `CURSOR.RES` cursor metadata and `I_CURSOR.RES` cursor images;
- `HELP.RES` named help topics and ordered hotspot rectangles;
- `.PLA`, `.PLO`, and `.PLP` 3×3 layout plans;
- `CAPITAL.CFG` and `CAPITAL.HOF` compatible-record support files.

Their complete field layouts, unknown regions, validation rules, and executable
provenance are in [UI, layout-plan, and support-file formats](ui-resources.md).

## Saves (`.SAV`)

The supplied DOS and Windows saves are mutually loadable and use save version
100. They share this outer structure:

| Order | Type | Meaning |
|---:|---|---|
| 1 | `u16` | Metadata byte count |
| 2 | bytes | Metadata payload |
| 3 | `i16` | Save version (`100`) |
| 4 | `u16` | Settings byte count |
| 5 | bytes | Embedded scenario/settings state |
| 6 | sections | Ordered marker/payload sequence |

Confirmed metadata fields:

| Metadata offset | Type | Meaning |
|---:|---|---|
| `0x00` | `char[13]` | Internal save filename |
| `0x10` | `u32` | Current date as Julian day number |
| `0x14` | `char[31]` | Company name |
| `0x44` | `char[32]` | Scenario title, blank in some custom games |

The settings block is currently preserved as opaque data. The inspector reports
embedded `.SCT` references.

### Section chain

Every observed version-100 save contains these 24 two-byte markers in order:

```text
100B 100C 100D 100E 100F 1010 1011 1001
1002 1003 1004 1005 1006 1007 1008 1015
1016 1017 1018 1019 101A 101B 101C 101D
```

The marker is immediately followed by its payload. Confirmed fixed payload sizes
help disambiguate marker-like byte pairs occurring inside variable data:

| Marker | Payload bytes | Current interpretation |
|---:|---:|---|
| `100B` | 28,884 | Unknown |
| `100C` | 0 | Empty |
| `100D` | 152 | Unknown |
| `100E` | 0 | Empty |
| `100F` | 9,684 | Unknown |
| `1010` | 2 | Unknown |
| `1011` | 223 | Unknown |
| `1001` | 4 | RNG state (`u32`, confirmed by cross-save equality) |
| `1002` | 46 | Unknown |
| `1005` | 67 | Unknown |
| `1006` | 380,174 | Likely map/simulation grid; interpretation unknown |
| `1007` | 182 | Unknown |
| `1008` | 31 | Unknown |
| `101C` | 78 | Unknown |
| `101D` | 6,613 | Unknown |

Sizes of omitted markers are variable. Marker labels are serialization tags, not
yet semantic names.

### Town array (`101B`)

The payload begins with a 10-byte header:

| Offset | Type | Meaning |
|---:|---|---|
| `0x00` | `u16` | Unknown; observed `100` |
| `0x02` | `u16` | Unknown; observed `100` |
| `0x04` | `u32` | Date as Julian day number |
| `0x08` | `u16` | Town count |

Each town then has three size-framed records:

1. A 371-byte town record. Name is at record offset `0x02`, within 21 bytes.
2. A 168-byte item-index record.
3. A 364-byte firm-index record.

A frame begins with a `u16` saved size. A zero prefix means the reader supplies
the expected structure size; this is necessary for data blocks larger than
65,535 bytes. Two 32-bit values at town-record offsets `0x4B` and `0x4F` behave
like transient pointers: they differ between DOS and Windows serialization and
are excluded from normalized record hashes. This interpretation is inferred.

The town list is followed by a size-framed 44-byte dynamic-array header. Its
first fields are:

| Offset | Type | Meaning |
|---:|---|---|
| `0x00` | `u32` | Capacity |
| `0x04` | `u32` | Growth block size |
| `0x08` | `u32` | Active/current record index |
| `0x0C` | `u32` | Element count |
| `0x10` | `u32` | Element size; observed `238` |

The next frame contains `element_count * element_size` bytes. Each 238-byte
element is keyed by `(u16 town_id, u16 item_id)` at offsets `0x00` and `0x02`.
Four finite `float32` fields at offsets `0x7C`, `0x80`, `0x84`, and `0x88` are
tracked for comparison. Their economic meanings remain unknown.

### Cross-build comparison

The comparator aligns sections by tag, not by raw file offset. Town/item elements
are aligned by `(town_id, item_id)`. It separately reports changes in inferred
transient pointer bytes and the IEEE-754 ULP distance of the four known floats.

Comparison output includes the complete versioned normalization policy, the
structural conditions required before that policy applies, and separate counts
for registered and unclassified difference bytes. Pointer bytes may be excluded
from normalized record hashes; float drift is measured but never silently
rewritten. See [Save normalization](format-gates.md#save-normalization).

No current parser writes saves. Unknown bytes are never silently rewritten.
