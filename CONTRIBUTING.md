# Contributing

Contributions should make an observation reproducible and keep proprietary game
data outside the repository.

## Development setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -t . -v
```

On Windows, activate the environment from `.venv\Scripts` and use `py` or
`python` as appropriate.

## Change checklist

1. Read `CLEAN_ROOM.md`.
2. Add or update a synthetic test for every format rule.
3. Reject impossible lengths and counts before allocating or iterating.
4. Never modify an input file. New export files must use explicit destinations
   and overwrite protection; any future original-format writer requires a
   separate design and review.
5. Mark interpretations as confirmed, inferred, or unknown.
6. Add every supported format and field to the machine-readable catalog. Every
   inferred field requires an observation method, confidence, and provenance note.
7. Preserve existing JSON keys. Additive fields are preferred; incompatible
   changes require a `schema_version` increment.
8. Run the full standard-library test suite, catalog gate, and deterministic
   fuzz campaign.
9. Update the content/parity ledgers when scope or evidence changes. Use the
   versioned experiment schema for sanitized original observations.
10. Review and stage only intended source files, then run repository and package
    gates. Stage new specs/fixtures explicitly; the boundary gate reads the index
    and the package check includes only tracked paths.

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -t . -v
PYTHONPATH=src python3 -m capplus_inspect schema-catalog
PYTHONPATH=src python3 -m capplus_inspect fuzz --iterations 2048 --seed 0x4341502B2B
python3 scripts/project_gates.py all
python3 scripts/package_check.py
```

The package check needs the declared setuptools build backend already installed;
it performs its build/install checks offline. See [project gates](docs/project-gates.md)
for limits and [experiment records](docs/experiments.md) for observation contracts.

## Documentation scope

- Keep `README.md` evergreen: explain the project, its capabilities, setup, and
  everyday usage without narrating individual development updates.
- Record released and unreleased changes in `CHANGELOG.md`.
- Keep planned milestones and future scope in `ROADMAP.md`.
- Put detailed technical findings in focused files under `docs/` and link them
  from the README when they are useful to users or contributors.

## Reporting an observation

Useful reports include the game build hash, exact action sequence, initial and
final dates, RNG state if known, and byte/section differences. Do not attach game
files to a public issue. A compact hexdump should include only the minimum bytes
needed to show the structure.
