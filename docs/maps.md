# Map layout and terrain evidence

`capplus-inspect inspect MAPS/WORLD.MAP --json` reports the stored map, not a
loaded runtime world. `roundtrip` reconstructs every byte without normalizing
unknown fields, string residue, selected indexes or stored process pointers.

## Layout correction

Map report `layout_version: 2` corrects the earlier 52-byte-header and
32-byte-footer interpretation. The Windows **and** DOS readers/writers transfer
55 header bytes and 380,160 grid bytes, then serialize a 29-byte dynamic-array
header. The corrected grid starts three bytes later. Consequently the previous
cell byte 3 is actually cell byte 0, and the last three bytes previously assigned
to the footer belong to the final cell. City records still start at 380,244.

The old source preview remains pixel-identical because `52 + 8*i + 3` equals
`55 + 8*i`. Visual recognition of that preview did not establish cell framing
or original rendering behavior. The field interpretation is now based on both
executables, with static-file and synthetic checks recorded below.

`schema_version` remains 1. Consumers of map offsets must use `layout_version`
2: `header_size` is 55, `grid.offset` is 55 and the legacy `footer` object is
now the 29-byte `city_array_header` (the two keys describe the same region).
For files without terrain, `grid`, `footer` and `city_array_header` are null.
`core_size` is the end of that header, or 55 when terrain is absent.

## Block framing

All multibyte scalar values are little-endian. There are no size-prefix words
around these map blocks; the map loader opens its file with framing disabled.

| File offset | Size | Contract |
|---:|---:|---|
| 0 | 22 | Internal path, fixed NUL-terminated string slot |
| 22 | 31 | Display name, fixed NUL-terminated string slot |
| 53 | 1 | Nonzero means terrain grid and city array are present |
| 54 | 1 | Nonzero means settings block is present |
| 55 | 380,160 if enabled | 240×198 row-major cells, eight bytes each |
| 380,215 | 29 if terrain enabled | Packed city-array header |
| 380,244 | `count * 29` if terrain enabled | Ordered city records |
| After enabled terrain/cities, otherwise 55 | 737 if enabled | Unframed configuration object |

The flags use **nonzero tests**, not an enum restricted to 0/1. Both are
preserved verbatim. The original writer's UI selects which blocks to include;
the parser supports all four combinations permitted by the loader. The supplied
15 maps all contain terrain/cities and no settings. Other combinations are
static-code-supported and synthetically tested, not runtime-certified exports.

The embedded settings object is the same 737-byte memory region serialized by
the configuration routines. Unlike `CAPITAL.CFG`, there is no leading `u16`
size word here. It is framed, hashed and preserved; individual settings fields
remain undecoded. No speculative parsing of strings inside it affects framing.

## Eight-byte cells

| Cell offset | Size/type | Stored field and confidence |
|---:|---|---|
| 0–1 | `i16le` | Signed terrain height; confirmed signed reads and terrain conversion |
| 2 | `u8` | Unknown; bounded to this byte, retained without masking |
| 3 | `u8` | Unknown; bounded to this byte, retained without masking |
| 4 | `u8` | Derived shade storage; confirmed writes during terrain conversion/shading |
| 5 | `u8` | Unknown; bounded to this byte, retained without masking |
| 6 | `u8` | Unknown; bounded to this byte, retained without masking |
| 7 | `u8` | Unknown; bounded to this byte, retained without masking |

The original loader reads into `World + 0x24`'s grid, copies the complete grid
to `World + 0x08`'s working grid, and transforms the latter. It does not require
stored bytes 2–7 to be zero. They are zero across the supplied files, but the
inspector accepts and preserves all 256 values in each byte. A future writer
must not clear them merely because their purpose is still unresolved.

The original editor uses the same two grids for incremental changes. It edits
the source, copies each complete cell in the inclusive changed rectangle into
the working grid, then converts and shades only that rectangle. The replacement
`terrain.update_terrain_rectangle` reproduces this behavior, including global
edge handling and outside-neighbor reads. See [terrain shading](terrain.md#partial-editor-rectangles).

`decode_map_cell(eight_bytes)` exposes the signed height, stored shade, five
opaque bytes and the first per-cell conversion. With stored height `h`, both
builds perform:

| Input range | Initial working height | Initial water shade at byte 4 |
|---|---:|---|
| `h < 100` | 0 | `min((240 + trunc(h / 10)) & 255, 249)` |
| `100 <= h < 215` | `((h - 100) * 2) // 3 + 1` | Not assigned by this branch |
| `215 <= h < 255` | `h` | Not assigned by this branch |
| `h >= 255` | 255 | Not assigned by this branch |

`trunc` is signed division toward zero. Negative inputs must not use Python's
floor division: `-1` gives shade 240, not 239. The discontinuity at 215 is
present in both executables; it is not smoothed or "corrected" by the inspector.

This first pass then calls a neighbor-based shading routine that reads nearby
heights and writes byte 4. The full-map operation is implemented by
`terrain.shade_terrain_grid`, with independent DOS and Windows lookup profiles
checked against isolated original functions. See [terrain shading](terrain.md)
for the algorithm, arithmetic and validation limits. A single cell lacks the
neighbor context, so `decode_map_cell` still reports `final_runtime_shade: null`.
The stored shade byte is reported separately from any derived result.

`render-map` defaults to the historical low-byte source preview, mapping
`h & 255` through the supplied palette. `--terrain-profile dos|windows` instead
exports the derived working-grid shades. Either preview can overlay city
markers. Text and JSON distinguish the two modes. The independent Windows
palette profile changes palette quantization only; neither mode renders the
complete original world's sprites, buildings, camera or UI.

## City-array header and records

The former "footer" is the same packed dynamic-array structure used by layout
plans. Offsets below are relative to file position 380,215:

| Header offset | Type | Meaning/status |
|---:|---|---|
| 0 | `i32` | Allocated capacity; confirmed allocation and append use |
| 4 | `i32` | Capacity growth increment; confirmed append/reset use |
| 8 | `i32` | Current/selected one-based index, or zero; confirmed array operations |
| 12 | `i32` | Serialized record count; confirmed transfer multiplier |
| 16 | `i32` | Record size, 29 for map cities; confirmed transfer multiplier |
| 20 | `i32` | Inferred sort-key offset from the shared array contract; preserved unrestricted |
| 24 | `u8` | Unknown control byte; preserved unrestricted |
| 25 | `u32` | Transient data pointer; confirmed replacement on load |

Before loading the header, both builds retain the destination array's existing
allocation pointer. After reading the stored header they resize that local
allocation using capacity × record size and replace the serialized pointer.
They read count × record size bytes and reset selection to `min(count, 1)`.
The inspector does neither allocation nor pointer dereferencing and preserves
the stored pointer/selection exactly during a no-op round trip.

Each city record is `u16 x`, `u16 y`, an unresolved `u32` at offset 4 and a
21-byte name slot. Coordinates are bounded to `0..239` and `0..197`. JSON now
reports the scalar as `unknown_04_u32`; the older `population` key remains as an
equal-value compatibility alias with `population_semantics` explicitly marking
the interpretation unconfirmed.

The map editor's add-city path assigns the coordinates and name but does not
assign the offset-4 dword before appending the 29-byte record. The later runtime
town synchronization reads the coordinates and copies the 21 name bytes from
record offset 8, skipping offset 4. Some shipped nonzero values resemble real
city populations, but neither observation establishes a serialization or
runtime contract. The field therefore remains unknown and byte-preserved.

The parser validates nonnegative capacity/count, positive growth, count no
larger than capacity or the 16,384-record inspection budget, selected index in
`0..count`, record size 29, available records, coordinates and exact file end.
The inspection budget is not asserted to be the original gameplay limit.
Capacity itself does not cause allocation, even if it is very large. Bytes
after a string NUL, unknown control fields and process-pointer residue remain
intact. Unsupported layouts fail explicitly rather than absorbing extra bytes
as cities or silently discarding them.

## Recovered city-editor rules

Both executables implement the same placement predicate:

- The editor refuses to add a thirteenth city; this is an editor limit, while
  the read-only parser retains its larger defensive inspection budget.
- Every cell in the 7×7 square centered on the proposed coordinate must be
  inside the map and have a raw source height `100 <= h < 215`. Consequently a
  city center must be at least three cells from each global edge.
- When a name is supplied, it must not exactly match an existing 21-byte city
  name. The dialog separately rejects an empty or spaces-only name.
- A position is too close when both `abs(new_x-old_x) < 15` and
  `abs(new_y-old_y) < 15`. This is an axis-aligned 29×29 exclusion square, not
  an inferred Euclidean radius.

The delete tool searches existing records in reverse order and removes the
first city satisfying the same two-axis `< 15` proximity test. These are static
editor contracts from both builds; native dialog, redraw and saved-export
experiments are still pending.

## Executable evidence

Addresses refer to the exact unmodified reference executables identified by
SHA-256 in [the executable report](executables.md#build-identities). Windows
values are virtual addresses; DOS values use the loader survey's mapped LE
object addresses, not raw file offsets. No executable payloads or decompiler
dumps are included in this repository.

| Operation | Windows | DOS | Relevant observation |
|---|---:|---:|---|
| Map list/read header | `0x0047F520` | `0x0004A713` | Header read is 55 bytes |
| Write map | `0x0047F6D0` | `0x0004A876` | 55-byte header, flags at 53/54, conditional grid/array/settings |
| Load map | `0x0047F810` | `0x0004A992` | Same block sizes and flags; copies source to working grid |
| Write array | `0x004764B0` | `0x0008DE82` | 29-byte header then count × record size |
| Read array | `0x00476500` | `0x0008DECB` | Local allocation pointer replaces stored pointer; selection reset |
| Initial terrain conversion | `0x00423AB0` | `0x00047519` | 240×198, eight-byte stride, signed heights and threshold formula |
| Subsequent shading | `0x0043CB50` | `0x00048412` | Both bodies read neighbor heights and write byte 4; see terrain-function survey |
| Add city | `0x00463520` | `0x00049D90` | Limit 12; validates terrain/proximity/name before appending |
| Delete nearby city | `0x00463700` | `0x00049EEB` | Reverse scan; both axis differences must be below 15 |
| Validate city placement | `0x00463A20` | `0x0004A1FB` | 7×7 source-height range, exact name and axis-aligned separation checks |
| Synchronize city names | `0x00463980` | `0x0004A16B` | Coordinates locate runtime town; copies record bytes 8–28 only |

Useful Windows call sites: `0x0047F779` writes 55 bytes; `0x0047F790` writes
380,160 grid bytes; `0x0047F79C` invokes array serialization; `0x0047F7B4`
writes 737 settings bytes. Matching reads are at `0x0047F8B5`, `0x0047F8C1`
and `0x0047F8D9` after a 55-byte seek. Array capacity/growth/selection use can
also be checked at `0x004762D0` and `0x00476300`. The later Windows shading
write is `0x0043CE11`; [terrain evidence](terrain.md) covers both implementations.

## Corpus validation and remaining experiments

All 15 DOS maps are byte-identical to their Windows counterparts. Parsing and
reconstruction pass on all 30 inputs. The corpus contains 102 city records;
each matches its array count and has in-bounds coordinates. Every array has
capacity/growth 15, record size 29, inferred sort-key offset -1 and control
byte zero. Selection varies independently of count and is preserved.

Source heights range from -1 to 255. Europe has 86 negative cells, South East
Asia 4 and World 97; each negative value is -1. Other maps contain no negative
heights. All six stored bytes after the height are zero in this corpus.
Synthetic tests deliberately use nonzero values to prevent zero-only assumptions.

Reproduce inspection and preservation locally with user-owned data:

```bash
capplus-inspect inspect MAPS/WORLD.MAP --json
capplus-inspect roundtrip MAPS/WORLD.MAP --json
capplus-inspect roundtrip /path/to/installation --json
PYTHONPATH=src python -m unittest tests.test_maps -v
```

## Native editor capture protocol

Use one privately retained, user-created baseline map in both builds. Verify the
starting files are byte-identical, then make a fresh copy for every row below.
Export once without an edit first: a no-op rewrite must be measured rather than
assumed harmless. Each edited export changes only the listed property.

| Vector | Single action | Required observation |
|---|---|---|
| `map-noop` | Open and export without editing | Full hash, size and every changed byte range |
| `terrain-interior` | Apply one terrain tool wholly inside the map | Selected bounds; per-cell changes by byte offset |
| `terrain-edge` | Apply the same tool against one global edge | Clipped bounds and conditional edge shades |
| `terrain-corner` | Apply the same tool at one global corner | Corner copy order and unchanged outside cells |
| `terrain-thresholds` | Cross raw heights 99/100 and 214/215 one at a time | Source heights and loaded working height/shade |
| `city-add` | Add one uniquely named city on valid land | New record bytes, array metadata and runtime town name |
| `city-delete` | Delete only that city | Removed record, count/selection and retained record order |
| `city-invalid` | Attempt edge, water, duplicate-name and too-close placements separately | Rejection result and unchanged export hash |
| `map-flags` | Toggle terrain and settings inclusion separately | Header flags, conditional block boundaries and exact size |

Run every vector in DOS and Windows and try each resulting file in the opposite
build. Record executable hashes, baseline/export hashes, exact UI actions and
scalar observations under the [experiment contract](experiments.md); retain all
maps and screenshots privately. For terrain vectors, compare the stored source
grid with a separately captured loaded working grid. Hold palette, camera and
city markers fixed when taking screenshots. The offset-4 city value receives a
separate vector only if an editor control actually addresses it.

This experiment set is **planned, not performed**. Unknown cell bytes must stay
unknown when an action does not isolate their role, and there is still no claim
of native map-editor or complete rendering parity.
