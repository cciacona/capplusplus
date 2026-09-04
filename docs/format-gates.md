# Format completeness and safety gates

Cap++ treats binary-format claims as versioned, testable contracts. The gates in
this document cover the formats that `capplus-inspect` currently recognizes;
they do not imply that every original game structure has already been decoded.

## Machine-readable catalog

The source catalog is
[`format-catalog-v1.json`](../src/capplus_inspect/schemas/format-catalog-v1.json).
Its own JSON Schema is
[`format-catalog-v1.schema.json`](../src/capplus_inspect/schemas/format-catalog-v1.schema.json).
Both files are bundled in the wheel.

```bash
capplus-inspect schema-catalog
capplus-inspect schema-catalog --json > format-catalog.json
```

Catalog version 1 covers 20 recognized on-disk structures and 54 field records.
Every field has a confidence level, one or more observation methods, and a
provenance note. The dependency-free validator rejects duplicate or missing
formats, invalid status/method values, and inferred fields without provenance.

Field statuses have deliberately narrow meanings:

- `confirmed`: directly supported by structural, executable, visual, or
  controlled evidence;
- `inferred`: the interpretation is useful and evidence-backed but still needs
  stronger behavioral confirmation;
- `unknown`: bytes or relationships are preserved without a semantic claim.

Observation methods are chosen from a closed vocabulary so reviews and future
tools can query evidence consistently. Catalog version and JSON report schema
version are independent: a breaking catalog-model change increments the former,
while an incompatible CLI JSON change increments the latter.

## Byte-preserving round trips

The round-trip codec parses a non-save input into ordered immutable regions,
checks that those regions cover the file exactly once without gaps or overlap,
then reconstructs the file from the regions. It compares both bytes and SHA-256.

```bash
capplus-inspect roundtrip "RESOURCE/PAL_STD.RES"
capplus-inspect roundtrip "Capitalism Plus DOS" --json > dos-roundtrip.json
```

Directory and valid ZIP inputs select every known core asset plus the recognized
game executable, `CAPITAL.CFG`, and `CAPITAL.HOF`. The report contains sizes,
hashes, format identifiers, coverage levels, and result counts—not original
payload bytes.

Round-trip coverage has two explicit levels:

- `structural`: known boundaries such as headers, directories, records, tables,
  images, map regions, or executable wrappers are reconstructed separately;
- `opaque`: the parser makes no internal claim and preserves one immutable byte
  region exactly.

This is a preservation writer used for validation, not an editor. It never
modifies an input file and does not enable unsafe semantic changes to unknown
fields. Original save writing remains disabled.

### Private-corpus result

Both supplied installations pass independently:

| Gate | DOS | Windows |
|---|---:|---:|
| Supported non-save files | 75 | 75 |
| Structurally segmented | 73 | 73 |
| Opaque passthrough | 2 | 2 |
| Byte-identical reconstruction | 75 / 75 | 75 / 75 |
| Source formats represented | 18 | 18 |

The opaque inputs are `RESOURCE/JOB.RTI` and `RESOURCE/JOB.RTX`. Naming them in
the report prevents byte preservation from being mistaken for format decoding.

## Save normalization

`compare-saves` embeds policy
`capitalism_plus_save_cross_build` version 1 in both text and JSON output. The
policy currently registers two permitted difference classes for structurally
matched version-100 DOS/Windows saves:

1. Two four-byte fields at town-record offsets `0x4B` and `0x4F` are excluded
   from normalized record hashes. Cross-build comparison and executable analysis
   indicate that the original loader discards these runtime pointer values.
2. Four town/item `float32` fields at offsets `0x7C`, `0x80`, `0x84`, and `0x88`
   are reported in ULPs. A difference of at most four ULPs is within the observed
   cross-compiler range only when the date, scenario, RNG state, section sizes,
   and town/item keys match.

The policy never rewrites a save or declares arbitrary saves equivalent. It
counts classified and unclassified same-position byte differences separately.
For the supplied matched pair, 677 of 1,035 differing bytes fall in registered
pointer/float locations and 358 remain explicitly unclassified. Later format
work must account for those bytes before the roadmap's no-op save gate can pass.

## Reproducible parser fuzzing

The fuzzer uses 16 generated, redistributable fixtures that exercise every
parser family. It derives each bounded bit flip, truncation, span replacement,
deletion, insertion, maximum-length word, or duplication from SHA-256 of the
numeric seed, filename, and iteration. The same command therefore produces the
same transcript on every supported Python version.

```bash
capplus-inspect fuzz --iterations 2048 --seed 0x4341502B2B
```

Malformed inputs may be accepted as a valid alternative structure or rejected
with `InspectError`; either is a normal fuzz outcome. An unexpected exception,
non-exact reconstruction of an accepted non-save mutation, or unbounded input
growth fails the campaign with a reproducible case, seed, iteration, and
mutation name.

The standard 2,048-iteration campaign currently produces transcript SHA-256
`022ee92ec733c1c2545138fa5d8eb6abbe4fb25951b84450da466c2a2a8092fa`,
with 979 accepted and 1,069 rejected mutations and zero unexpected failures.

## Continuous integration

Pull requests and pushes to `main` run:

1. all synthetic unit tests on Python 3.10 through 3.14;
2. the catalog/provenance validator on Python 3.12;
3. the fixed 2,048-iteration fuzz campaign on Python 3.12;
4. one aggregate required `CI` check that fails if either job fails.

No CI job downloads or requires original game data.
