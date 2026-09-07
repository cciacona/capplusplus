# Terrain conversion and shading

`shade_terrain_grid` reconstructs the full-map conversion performed on the
240×198 working grid. `render-map --terrain-profile dos` or `windows` exports
its shade bytes as indexed PNG pixels. Without that option, `render-map` keeps
the historical source-height low-byte preview.

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
2, 3, 5, 6 and 7 are copied unchanged. No meaning is assigned to those five
opaque bytes.

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

Only the loader's full-map operation is implemented. Partial rectangles used
by editing operations need their own contract and original-function checks.

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
- A minimal world object points to the supplied working grid. No original
  process initialization, window, editor or event loop is executed.

The survey compares all 380,160 output bytes, not just image pixels, and also
requires the five opaque bytes of every cell to remain unchanged. It always
includes six procedural probes: flat water, land and peaks, a spatial ramp,
a threshold checker pattern, and a signed-height stress pattern. User maps are
optional additional inputs. JSON contains input/output hashes, first mismatch
and mismatch count, table hashes, profiles, control words and stub descriptions.
`whole_game_validation` remains false even when every function comparison passes.

Regression fixtures in `tests/fixtures/terrain-v1.json` contain only hashes of
these newly generated synthetic grids and their observed function outputs.
They are not hashes generated from the replacement and then asserted against
itself. Run them without original data or the emulator:

```bash
PYTHONPATH=src python -m unittest tests.test_terrain -v
```

Whole-game editor exports, live working-grid captures, camera/palette-held
screenshots and unresolved cell semantics remain the experiments in
[maps](maps.md#corpus-validation-and-remaining-experiments). Isolated function
emulation does not certify those behaviors or the entire 0.3 milestone.
