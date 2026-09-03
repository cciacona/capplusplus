## Summary

Describe the user-visible or research outcome of this change.

## Evidence and provenance

For format or behavioral claims, describe the observation method and mark each
interpretation as confirmed, inferred, or unknown.

## Validation

List the tests and reproducible checks that were run.

## Checklist

- [ ] I have read and followed `CLEAN_ROOM.md`.
- [ ] This change contains no original game files, expressive extracted content,
      decompiler output, or reconstructed source code.
- [ ] New format rules have synthetic tests, including malformed-input bounds.
- [ ] Inputs remain read-only and exports retain overwrite protection.
- [ ] JSON changes are additive, or `schema_version` was incremented.
- [ ] User-facing changes are recorded in `CHANGELOG.md`; planned work remains in
      `ROADMAP.md` rather than the README.
