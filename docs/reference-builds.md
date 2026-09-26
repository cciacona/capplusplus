# Capitalism Plus reference builds

This inventory separates an **announced release** from builds whose files and
behavior have been measured. The original DOS and Windows installations remain
the measured Classic-parity references. The [official Steam announcement][steam]
dated 2026-09-26 calls its updated release *Capitalism Plus version 1.01*; its
files have not yet been supplied for inspection. SteamDB associates the
announcement with [Steam build 25547109][steamdb]. A Steam build ID, a game's
release label, the menu's internal version and the version number inside a save
are separate identifiers.

| Reference | Evidence in this repository | Executable and data | Save and behavior evidence | Current role |
|---|---|---|---|---|
| Retail DOS 1.0 | Supplied unmodified installation; [executable hash](executables.md#build-identities) and [validation record](validation.md) | Known MZ/LE executable; its 72 core files match the supplied Windows installation | Paired version-100 saves and controlled executable probes | Measured Classic reference; recognized by `capplus-inspect` |
| Retail Windows 1.0 | Supplied unmodified installation; [executable hash](executables.md#build-identities) and [validation record](validation.md) | Known PE32 executable; the 72 shared core files match DOS | Paired version-100 saves, cross-loading observation and controlled executable probes | Measured Classic reference; recognized by `capplus-inspect` |
| Steam 1.01, announced 2026-09-26 | [Publisher announcement][steam]; SteamDB's [build record][steamdb] | Executable identity, dependencies, file list, core-file hashes and data differences **not measured** | Save version, load/resave compatibility, simulation and UI differences **not measured** | Candidate third reference; **not recognized or certified** by the inspector |

The publisher says the Steam update uses SDL3 for video, runs on Windows 11
without DOSBox, and offers borderless windowed play. It also says the original
background music **has already been** restored; the announcement does not date
that restoration. It does not say how the game logic was ported, whether old
source code was used, whether DOS/Windows saves still load, or whether the new
release contains changed game rules or content. SDL3 use alone does not prove
native Linux or macOS builds. These remain open questions, not compatibility
claims.

## Inspection plan for an owned Steam installation

Track measurements and decisions in [issue #28](https://github.com/cciacona/capplusplus/issues/28).

Keep the installed files and saves private. Record only their names, lengths,
cryptographic hashes, structural observations and sanitized experiment results
in the repository; follow the [clean-room policy](../CLEAN_ROOM.md).

1. Capture the Steam app and build IDs, acquisition date, complete file inventory
   and SHA-256 digests. Preserve the current installation before Steam replaces
   it with a later build. Record executable names, format, imports, bundled
   libraries and version strings; distinguish inspected bytes from the
   announcement's description.
2. Run `capplus-inspect inspect <installation> --deep --json` read-only and record
   which analyses work and which checks reject an unknown executable or changed
   data. Compare paths and hashes for the 72 known shared core files against
   both 1.0 installations. Do not add a known-build fingerprint from the release
   label alone.
3. On copies of the existing controlled saves, test Steam 1.01 loading and a
   paused no-op resave. Record game date, elapsed time, RNG state and other
   relevant state before/after each operation. Compare save header, version,
   length, all section markers, counters and byte ranges with the existing
   DOS/Windows controls under [issue #8](https://github.com/cciacona/capplusplus/issues/8).
   Document rejected saves and crashes as observations too. Do not treat two
   saves as same-state merely because they share a slot name.
4. Probe any gameplay or presentation differences that the inventory and save
   tests reveal. Add sanitized [experiment records](experiments.md) for
   behavioral claims. Decide whether 1.01 is a compatible additional oracle or
   a distinct profile, then revise the [roadmap](../ROADMAP.md), the
   [known-build decision](decisions/0001-narrow-original-build-support.md), and
   recognition code with measured evidence.

The current [Cap++ 1.0 roadmap](../ROADMAP.md) is a version of **this project**.
The Steam release's 1.01 label does not change Cap++ milestone numbering or the
existing 1.0 acceptance criteria by itself.

[steam]: https://store.steampowered.com/news/app/450120/view/708909893000627895?l=english
[steamdb]: https://steamdb.info/patchnotes/25547109/
