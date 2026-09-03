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
6. Preserve existing JSON keys. Additive fields are preferred; incompatible
   changes require a `schema_version` increment.
7. Run the full standard-library test suite.

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
