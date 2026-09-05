# Original-content coverage

[`specs/content-coverage-v1.json`](../specs/content-coverage-v1.json) is the
inventory ledger. It includes unsupported families; the bundled inspector
format catalog describes implemented structures and is not an inventory of
everything the original game needs. Counts are evidence, not progress percentages.

## Inventory baseline

| Source | Files | Evidence and limitation |
|---|---:|---|
| Shared installation core | 72 | Exact hashes in `src/capplus_inspect/known.py`; game sets 24, maps 15, resources 33. |
| `CapPlus.gam` data image | 1,001 | Directory recount only from a truncated local copy; historical complete-image identity in the ledger. |
| Retail CD filesystem | 1,604 | Earlier verified disc comparison; not freshly re-enumerated in this hardening pass. |
| Retail files not yet classified here | 531 | 1,604 minus the two disjoint inventories above. This is an open gap. |
| Retail CD audio | 8 tracks | Separate from filesystem counts; playback semantics remain under issue #5. |

The `CapPlus.gam` inventory comprises:

| Family | Files |
|---|---:|
| Scenario `.SCN` / `.SCP` / `.SCS` / `.SCT` | 20 / 21 / 20 / 20 |
| Extensionless scenario content | 20 |
| Tutorial `.TUT` / `.HIN` / `.SAM` / `.SPH` | 8 / 8 / 8 / 8 |
| Extensionless tutorial content, including nested directories | 792 |
| Loose sound effects | 25 |
| Legacy VESA utilities/support | 50 |
| DOS reference executable | 1 |

The currently available CD ZIP is truncated; a complete retail inventory still
needs recovery or a new user-owned input. The local `CapPlus.gam` is also
truncated: 36,738,560 bytes versus the previously verified 279,402,496 bytes,
with a different SHA-256. Its readable directory tree retains all 1,001 entries
and their family counts, but this pass does **not** reverify original payload
hashes or completeness. The ledger distinguishes the historical image hash
from the current directory-only evidence. The remaining 531 retail files must be
classified individually before declaring inventory completeness. Do not assume
that all additions are disposable setup, demos, manuals, or drivers. The known
50 VESA files are explicitly legacy-ignored for the modern engine, not silently
missing. Reference executables are analysis inputs, not engine dependencies.
Windows configuration, hall of fame, saves and optional replacement music have
families even where a stable corpus-wide file count is not appropriate.

## Independent coverage states

Each family records four independent dimensions:

| Dimension | Meaning |
|---|---|
| Framing | Whether boundaries, sizes and ordering are understood. |
| Preservation | Whether unchanged input reconstructs exactly, including opaque bytes. |
| Semantics | Whether field meanings, references and usage are decoded. |
| Behavior | Whether original-game use has been experimentally validated. |

Copying an opaque block exactly is not semantic decoding. The existing 75/75
installation reconstruction result excludes most disc content and includes
opaque `JOB.RTI`/`JOB.RTX`; it is not a 0.3 completion claim. Similarly, the map
overview does not decode all eight cell bytes or the footer. The ledger preserves
these distinctions and links families to follow-up issues.

## Recounting an inventory

Use paths relative to the source root, without payload bytes, in a private JSON
array. The classification command emits aggregate family counts, not filenames:

```bash
python scripts/project_gates.py inventory --source gam_image --input private-corpus/gam-paths.json
python scripts/project_gates.py ledgers
```

The inventory gate rejects duplicates, case collisions, traversal and ambiguous
selectors. Unclassified paths, missing/extra families or count mismatches return
a nonzero exit status. Case and path separators are normalized; selectors use
Python `fnmatch` (so `*` can include nested path components). Path/count checks
do not authenticate payloads: retain separate original-image/hash validation.
This command consumes a manifest; it does not add a CD or ISO reader to the CLI.

New evidence should update the source identity, family counts and coverage
dimensions together. Any retail reconciliation must demonstrate disjoint path
sets rather than adding unrelated installation totals.
