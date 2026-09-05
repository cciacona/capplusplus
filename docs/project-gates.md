# Repository and package gates

These repository-only scripts supplement the inspector's parser, provenance,
preservation and fuzz gates. They add no runtime dependencies to the CLI.

```bash
python scripts/project_gates.py all
python scripts/project_gates.py version --tag v0.2.0
python scripts/package_check.py
```

## Content boundary

The boundary gate examines **Git index blobs**: stage only reviewed source and
synthetic fixtures before running it. In CI the index is the checked-out commit.
An unstaged harmless replacement cannot hide a staged original payload.

It rejects private/generated directory names, original-game and archive/media
extensions (case-insensitively), known original SHA-256 payloads, common binary
and disc signatures, non-UTF-8/NUL-containing files, files over one MiB, symlinks,
submodules and unresolved index entries. Fixtures should be generated in memory
from newly written source; factual offsets and hashes can remain in text.

This is a heuristic guardrail, not a copyright classifier or legal clearance.
Encoded/compressed text, copied prose, decompiler dumps, modified original files
and small JSON table exports can evade it. It does not scan remote Git history.
Review the entire staged diff before publishing; a CI failure is too late to
undo an initial public upload. Any future need for legitimate binary project
assets requires an explicit policy change and review, not bypassing the gate.

JSON itself is not forbidden. Ignore rules reserve `original-data/`,
`private-corpus/`, `analysis/`, `reports/`, `exports/`, `executable-reports/` and
`loader-reports/` for private/generated output while allowing public specs and
synthetic fixtures. Put ad-hoc inspector JSON in those directories or outside
the repository; do not rely on a blanket `*.json` ignore.

## Specifications

The ledger gate checks [content coverage](content-coverage.md),
[feature parity](parity.md) and [experiment records](experiments.md). The schema
files use a deliberately small JSON Schema subset implemented with the standard
library; the validator is not a general JSON Schema engine. Unsupported
validation keywords encountered during validation are errors. Unknown enum
values, extra properties, contradictory reconciliation and missing local
evidence references fail validation.

## Versions and distribution

The version gate compares the literal `[project].version` with the package
`__version__`. Tag builds also require `v<version>` and a matching changelog
section. Unreleased development can retain the last released version; passing
the gate does not assert that main is identical to that release.

The package check copies tracked working files to a fresh temporary directory,
builds an sdist and wheel, verifies metadata/license/schema inclusion, extracts
and tests the sdist, and compares the contents of a rebuilt wheel. It installs
that wheel into a fresh environment with no index and no dependencies, outside
the checkout, then checks imports, metadata, CLI version and schema/fuzz smoke
commands. ZIP timestamps are not part of the content-equality assertion.

The build backend must be installed beforehand. CI explicitly bootstraps
`setuptools>=77`; the actual build/install check disables package-index use.
This minimum supports the project's SPDX `license` and `license-files`
metadata ([setuptools documentation](https://setuptools.pypa.io/en/latest/userguide/pyproject_config.html)).
It is a build dependency, not an inspector runtime dependency.

CI runs unit tests on Linux/Python 3.10–3.14 and Windows/macOS/Python 3.12,
plus package checks on all three operating systems. The required aggregate
`CI` check depends on these jobs, format gates and repository gates. Actions
remain SHA-pinned with read-only permissions; this change does not alter
repository security settings or publish packages automatically.
