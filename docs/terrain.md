# Terrain conversion and shading

`shade_terrain_grid` reconstructs the full-map conversion performed on the
240×198 working grid. `update_terrain_rectangle` reproduces the map editor's
partial, inclusive rectangle update over separate source and working grids.
`render-map --terrain-profile dos` or `windows` exports full-map shade bytes as
indexed PNG pixels. Without that option, `render-map` keeps the historical
source-height low-byte preview.

```powershell
capplus-inspect render-map "MAPS\WORLD.MAP" ".\terrain.png" --palette "RESOURCE\PAL_STD.RES" --terrain-profile windows --palette-profile windows --scale 4
```

Terrain and palette profiles are independent. The terrain profile determines
the arithmetic used to obtain pixel indices; the palette profile determines
their RGB colors. Optional city markers are an inspector overlay. This is a
terrain preview, not the complete game's camera, sprites, buildings or UI.

Render JSON records `terrain_profile`, `terrain_model_version: 1`, a SHA-256 of
the complete derived working grid, and `whole_game_rendering_validated: false`.
The first three values are null for the source preview. The source file and
its stored shade bytes are never replaced by the derived grid.

## Recovered algorithm

First apply the signed height and water-shade conversion in [maps](maps.md#eight-byte-cells).
All resulting heights are in `0..255`. Byte 4 holds the derived shade; bytes
2, 3, 5, 6 and 7 are copied unchanged by this stage. The later runtime
initializer overwrites working-grid bytes 5 and 6 and non-water byte 7; that
does not assign meanings to the corresponding stored source bytes.

For each interior cell, the converted heights of its eight neighbors determine
the normal vector:

```text
dx = 256*(W-E) + 128*(NW+SW-NE-SE)
dy = 256*(N-S) + 128*(NW+NE-SW-SE)
normal = normalize(dx, dy, 21845)
light = normalize(9703, -64813, 65536)
dot = trunc(normal.x*light.x/65536)
    + trunc(normal.y*light.y/65536)
    + trunc(normal.z*light.z/65536)
intensity = max(trunc((dot-35000)/1000), 0)
```

Each dot-product component is truncated separately. `trunc` always means toward
zero. Water (converted height zero) skips this land calculation and retains its
initial water shade until the border-copy pass.

The original normalizer uses a 1,025-word approximation table, not a square root:

```text
pair_length(a, b):
    high, low = max(abs(a), abs(b)), min(abs(a), abs(b))
    if high == 0: return 0
    index = floor(floor(low*65536/high)/64)
    return floor(high*(65536 + table[index])/65536)

normalize(x, y, z):
    length = pair_length(pair_length(x, y), z)
    return trunc(x*65536/length), trunc(y*65536/length), trunc(z*65536/length)
```

Intensity selects a shade-table entry according to the converted height:

| Height | Conditional remapping of intensity `i` | Maximum entry |
|---|---|---:|
| Below 100 | None | 31 |
| 100–234 | When `16 < i < 32`: `(i-16)//2 + 32` | 38 |
| 235–250 | When `16 < i < 39`: `(i-16)//4 + 39` | 44 |
| 251–255 | When `16 < i < 44`: `(i-16)//5 + 45` | 47 |

Entries 0–31 map to palette indices `80 + entry//2`; entries 32–47 map to
96–111. Iteration visits x=1..238, then y=1..196 for each x. The full-rectangle
edge pass copies shade bytes in this order: top from row 1, bottom from row
196, left from column 1, right from column 238. Corners consequently take the
diagonal interior shade. Heights and opaque bytes retain their own cell values.

## Post-shading runtime initialization

`initialize_runtime_terrain(shaded_grid, terrain_resource, rng_state,
profile=...)` reconstructs the four passes performed before the source grid is
released. It returns a new grid, final 32-bit RNG state, selected climate-center
row and exact RNG-call counts. Its component functions are independently
available for bounded testing:

1. `classify_terrain_tiles` replaces working word 0 with a base tile ID.
2. `apply_water_transitions` chooses shoreline corner patterns from
   `TERRAIN.RES`.
3. `initialize_terrain_cell_fields` writes climate, rainfall and soil fertility.
4. `randomize_terrain_variants` selects variants from consecutive equal-corner
   groups.

Neither the input grid nor `TERRAIN.RES` is modified. Working bytes 2, 3 and 4
survive all four passes exactly. This API models runtime state; it does not
rewrite a `.MAP` file.

### Tile classification and shoreline grammar

Converted working height `h` becomes one of three base IDs:

| Condition | Tile ID | `TERRAIN.RES` record |
|---|---:|---:|
| `h >= 215` | `0x2013` | 20 |
| `h > 0` | `0x2000` | 1 |
| Otherwise | `0x202D` | 46 |

`TERRAIN.RES` is a 49-row dBASE table. Its four one-byte corner fields are
`NW_TYPE`, `NE_TYPE`, `SW_TYPE` and `SE_TYPE`; `PROBABILTY` and the eight-byte
`FILENAME` follow. At load time, consecutive records with identical corners
form variant groups. The first record stores the number of additional variants:
4 for base land, 11 for hills and 3 for water in the shipped table.

For every water cell, the transition pass visits left, right, up, down, then the
four diagonals. It rewrites each non-water neighbor's corners that touch the
water to `S`, maps retained `H` corners to `G`, and selects the first exact
corner-pattern record. Mutations are immediate, so row-major cell order and
neighbor order are part of the contract. A missing tile ID or corner pattern is
an explicit format error in the replacement.

After field generation, each group-start tile with `n > 0` additional variants
advances the RNG with `random(n + 1)` and adds the result to the tile ID. The
confirmed generator is:

```text
state = state * 0x015A4E35 + 1       (32-bit wraparound)
raw = (state >> 16) & 0x7FFF
random(maximum) = (raw * maximum) >> 15
```

### Climate, rainfall and soil fertility

The original terrain-information UI reads working bytes 5, 6 and 7 beside the
labels `Climate`, `Rainfall` and `Soil Fertility`, respectively. Generation is
row-major. First, `climate_center = random(130) + 34`, placing it in rows
34–163. For cell row `y`:

```text
climate = max(4 - floor(abs(y - climate_center) / 34), 0)
```

Byte 5 therefore ranges from 0 to 4. At every x coordinate divisible by 10, a
new `jitter = random(11) - 5` is selected for that row's next ten columns.

Rainfall byte 6 begins with `random(63)` on row 0 or column 0. Elsewhere it is
the truncation-toward-zero average of the left and upper rainfall values, plus
`random(5) + jitter - 2`. Water values below 32 have bit 4 set; all values are
then clamped to 10–63. After the entire grid is generated, every rainfall byte
is arithmetically shifted right by four, yielding the final 0–3 scale.

Water does not consume a soil-fertility random value and retains its incoming
byte 7. Non-water edge cells receive `random(100)` directly. Interior non-water
cells average left and upper fertility, add `random(5) + jitter - 2`, and clamp
to 0–100. Tiles other than base ID `0x2000` are first masked with `0x1F`.
The edge branch deliberately skips that mask and clamp.

The compilers disagree on one signed-`char` edge case. A negative interior
fertility intermediate on base land becomes 100 in the DOS build (unsigned
comparison) and 0 in the Windows build (signed comparison). The `dos` and
`windows` profiles preserve this difference. RNG state and call counts remain
the same.

## Partial editor rectangles

The editor maintains two complete cell grids. `World + 0x24` is the stored
source grid containing signed raw heights; `World + 0x08` is the converted
working grid used for display and later world initialization. A terrain edit:

1. Changes an inclusive `(left, top, right, bottom)` rectangle in the source.
2. Copies every complete eight-byte source cell in that rectangle to the same
   working-grid positions, one contiguous span per row.
3. Runs the same conversion and shading routine on that working rectangle.

`update_terrain_rectangle(source_grid, working_grid, bounds, profile=...)`
implements this contract without mutating either input. The working heights
outside the rectangle must already be converted values in `0..255`; every byte
outside the rectangle remains unchanged. All eight source bytes are copied
inside before the height and shade fields are recomputed, so the five opaque
bytes follow the source cells exactly.

Conversion visits only the requested rectangle. Shading is clamped to its
intersection with the global interior (`x=1..238`, `y=1..196`) and may read the
already-converted neighbors just outside the rectangle. Border shade copying is
performed only when the rectangle touches that global edge, and only across the
rectangle's span. Its order remains top, bottom, left, right; this order matters
at corners. The replacement requires explicit in-grid bounds instead of exposing
the original routine's negative-left full-map sentinel.

Twelve procedural rectangles cover a single cell, a 7×7 interior, all four
edges, all four corners, one complete row and one complete column. Under both
builds and both tested x87 control words, all 48 partial results match every
byte produced by the original routine. Together with the 84 full-grid cases,
the shading portion of the current survey contains 132 passing grid comparisons.

## Build-specific lookup tables and arithmetic

Start with `value = 0`, `step = float32(0.2)` and `delta = float32(0.015)`.
For 1,025 iterations append `trunc(value)`, then add step to value and delta
to step. DOS stores both accumulators as binary32 after each addition;
Windows retains the intermediate values in x87 registers.

The Windows sequence can be computed exactly in binary64: both starting
constants are dyadic fractions, and the bounded sums require fewer than 53
significand bits. Ten words differ between the two generated tables:

| Index | Windows | DOS |
|---:|---:|---:|
| 16 | 5 | 4 |
| 225 | 422 | 423 |
| 241 | 481 | 482 |
| 400 | 1276 | 1277 |
| 416 | 1377 | 1378 |
| 800 | 4953 | 4954 |
| 816 | 5150 | 5151 |
| 869 | 5830 | 5831 |
| 972 | 7272 | 7273 |
| 997 | 7646 | 7647 |

Both end at 8061. SHA-256 of the 2,050 little-endian table bytes:

- DOS: `11084a7919dfc351deaefd4ed81c79d25f25c814b5450a83480137b4f029ebd9`
- Windows: `cba9ae8c537b2d08e24a5e35f012c3b5996972962719300eb65cacc486870885`

The replacement expresses subsequent multiply/divide/truncate steps as integer
ratios. The converted-height bound gives `abs(dx), abs(dy) <= 130560`; relevant
vector lengths stay below `2^18`. Integer operands are exactly representable,
and the products fit within binary64's exact-integer range. Nonintegral
quotients are separated from integer boundaries by more than the rounding
error of the original 53- or 64-bit x87 operations. This reasoning applies to
these bounded terrain inputs, not arbitrary vectors or the economic simulator.

## Executable references

These are the exact unmodified builds in [executable identities](executables.md#build-identities).
Windows addresses are virtual addresses. DOS code uses the mapped LE code
object; its data operands are relative to data-segment base `0xA0000`.

| Function or data | Windows | DOS |
|---|---:|---:|
| Table initialization | `0x43CAC0` | `0x48384` |
| Initial conversion and shading call | `0x423AB0` | `0x47519` |
| Runtime tile classification | `0x423CA0` | `0x4776C` |
| Runtime tile variants | `0x423CE0` | `0x477AF` |
| Shoreline transition pass | `0x423D20` | `0x477F7` |
| Shoreline neighbor helper | `0x423E50` | `0x47958` |
| Climate/rainfall/fertility generation | `0x423F20` | `0x47A4F` |
| Terrain corner-pattern lookup | `0x45CA60` | `0x7F6E6` |
| Terrain record lookup | `0x45D000` | `0x7FD77` |
| RNG range function | `0x47C560` | `0x907A3` |
| Sculpt-tool source/working row copy | `0x4631E9` | `0x499FE` |
| Sculpt-tool partial update call | `0x463251` | `0x49ABE` |
| Flat-tool source/working row copy | `0x4634C8` | `0x49CE7` |
| Flat-tool partial update call | `0x463502` | `0x49D7D` |
| Neighbor shading | `0x43CB50` | `0x48412` |
| Normalize vector | `0x43CF30` | `0x48861` |
| Approximate three-dimensional length | `0x43CFD0` | `0x488FE` |
| Truncation helper | `0x487590` | `0x964FC` |
| Length table | `0x4A3690` | DS-relative `0x164E8` |
| Shade-to-palette table | `0x4A3E98` | DS-relative `0x16CEA` |

## Reproducing isolated original-function comparisons

The optional research script uses [Unicorn's CPU emulation API](https://www.unicorn-engine.org/docs/tutorial.html).
Install `unicorn==2.1.4` into a separate research environment, then run from the
source checkout with user-owned reference inputs:

```bash
PYTHONPATH=src python scripts/terrain_survey.py \
  --dos-exe /path/to/dos/CAPPLUS.EXE \
  --windows-exe /path/to/windows/CapWin.exe \
  --terrain-resource /path/to/dos/RESOURCE/TERRAIN.RES \
  --maps /path/to/dos/MAPS \
  --output /private/reports/terrain.json
```

The installed inspector, renderer and normal CI suite have no Unicorn
dependency. The script refuses other executable hashes before emulation,
limits inputs to one MiB each and at most 64 maps, uses 12 MiB of emulated
memory, protects original code pages against writes, and rejects execution
outside audited code ranges. Calls have both instruction and time bounds;
the output must be new. No original-code or asset payload is emitted.

The environment is explicit and limited:

- x87 control words `0x027F` and `0x037F`: nearest rounding, masked exceptions,
  respectively 53- and 64-bit significands.
- Windows event polling at `0x41CE40` returns without platform work. The
  initialized FDIV-workaround flag is zero; CPU detection is not run.
- DOS stack checking at `0x96017` returns after its four-byte argument cleanup.
  Fixed emulated stack space replaces the original stack-availability check.
- A minimal world object points to the supplied working grid. A normalized
  in-memory terrain table is built from the user-owned `TERRAIN.RES`; image
  pointers are zero because these functions never dereference them. The partial probes
  prepare the source-to-working copy independently, then call the shared routine
  with explicit bounds. No original process initialization, window, editor or
  event loop is executed.

The survey compares all 380,160 output bytes, not just image pixels. Shading
checks require its five untouched bytes to follow the prepared input; runtime
checks require bytes 2, 3 and 4 to remain exact and compare final RNG state and
climate-center row. It always
includes six full-grid procedural probes and twelve partial rectangle probes.
Runtime initialization adds six procedural grids per build; user maps are
optional additional inputs to both stages. JSON
contains input/output hashes, bounds, first mismatch and mismatch count, table
hashes, profiles, control words and stub descriptions. `whole_game_validation`
remains false even when every function comparison passes.

With all 15 shipped maps supplied, 132 shading and 42 runtime grids pass, for
174 complete-grid original-function comparisons. Runtime checks also match the
final RNG state and climate-center row in every case.

Regression fixtures in `tests/fixtures/terrain-v1.json` and
`terrain-runtime-v1.json` contain only hashes of newly generated synthetic grids,
a procedural synthetic terrain grammar and their observed function outputs.
They are not hashes generated from the replacement and then asserted against
itself. Run them without original data or the emulator:

```bash
PYTHONPATH=src python -m unittest tests.test_terrain -v
```

Native editor exports, live working-grid captures, camera/palette-held
screenshots and the remaining source/working-cell semantics remain the experiments in
[maps](maps.md#corpus-validation-and-remaining-experiments). Isolated function
emulation does not certify those behaviors or the entire 0.3 milestone.
