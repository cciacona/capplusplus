# Third-party notices

Cap++ currently incorporates no third-party source code or assets into its
distributed source, wheel, or future game data. `capplus-inspect` has no
third-party runtime dependencies.

The project uses external development services and a declared setuptools build
backend, but those tools are not copied into the distributed project. The open
reimplementations listed in [reference projects](docs/reference-projects.md) are
studied as design references; their source is not incorporated and they are not
Cap++ dependencies.

When third-party material is introduced, this file must identify:

- component and version or immutable source commit;
- upstream project and source location;
- files or binary package included by Cap++;
- copyright holder and license;
- local modifications and purpose;
- location of the complete required license text.

An entry here does not replace compliance with the third party's license. New
dependencies and copied source require review under `CONTRIBUTING.md` and
`CLEAN_ROOM.md` before they enter the repository.
