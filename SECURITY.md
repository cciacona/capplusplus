# Security Policy

## Supported code

Security fixes are made on the `main` branch and included in the next release.
The latest tagged release receives best-effort fixes; older pre-1.0 releases are
not maintained as separate security-support lines.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting from this repository's Security
page. Please do not open a public issue for a suspected vulnerability.

Include the affected version or commit, operating system and Python version,
the smallest reproducible command sequence, expected and actual behavior, and
a sanitized proof of concept when possible. Reports involving parser inputs
should use generated fixtures or precise hashes, offsets, lengths, and numeric
values.

Do not attach original Capitalism Plus executables, saves, artwork, audio,
maps, scenarios, decompiler output, or other proprietary material. If private
verification requires a user-owned original file, first describe the minimum
information needed so maintainers can arrange a lawful reproduction.

Maintainers will acknowledge reports and provide status updates on a best-effort
basis. A fix may be coordinated privately and disclosed through a GitHub
security advisory after users have a reasonable opportunity to update.

Compatibility differences, unknown original-format fields, and vulnerabilities
in the original proprietary game should use the ordinary issue process unless
they also create a security problem in Cap++ code.
