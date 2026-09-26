# Capitalism Plus reference builds

This inventory separates **measured files** from **tested game behavior**. The
original DOS and Windows installations remain the measured Classic-parity
references. The [official Steam announcement][steam] dated 2026-09-26 calls its
updated release *Capitalism Plus version 1.01*. A user-provided folder archive
identified as that release was inspected on the same day. SteamDB associates
the announcement with [Steam build 25547109][steamdb], but the archive does not
contain a Steam app manifest to verify its exact depot build ID. A Steam build
ID, the game's release label, the executable's embedded version string, and
the version number inside a save are separate identifiers.

SteamDB [lists build 25547109][branches] on both the public and beta branches,
with the public branch updated on 2026-09-26. Its publicly visible
[depot file page][depot] still displays a manifest dated 2016. That older file
list, including DOSBox, cannot establish what files Steam 1.01 currently
installs.

| Reference | Evidence in this repository | Executable and data | Save and behavior evidence | Current role |
|---|---|---|---|---|
| Retail DOS 1.0 | Supplied unmodified installation; [executable hash](executables.md#build-identities) and [validation record](validation.md) | Known MZ/LE executable; its 72 core files match the supplied Windows installation | Paired version-100 saves and controlled executable probes | Measured Classic reference; recognized by `capplus-inspect` |
| Retail Windows 1.0 | Supplied unmodified installation; [executable hash](executables.md#build-identities) and [validation record](validation.md) | Known PE32 executable; the 72 shared core files match DOS | Paired version-100 saves, cross-loading observation and controlled executable probes | Measured Classic reference; recognized by `capplus-inspect` |
| Steam 1.01 candidate archive, received 2026-09-26 | User-supplied ZIP, hashes and static comparison below; [publisher announcement][steam] | PE32 executable, SDL3 import, 71/72 old core-file hashes match; one changed UI resource | Seven pre-update save files are present; **no save made under 1.01 or live behavior test** | Measured third artifact; **not recognized or certified** as a compatible build by the inspector |

The publisher says the Steam update uses SDL3 for video, runs on Windows 11
without DOSBox, and offers borderless windowed play. It also says the original
background music **has already been** restored; the announcement does not date
that restoration. It does not say whether DOS/Windows saves still load or
whether game rules changed. SDL3 use alone does not prove native Linux or macOS
builds. These remain open questions, not compatibility claims.

## Static inspection of the supplied 1.01 archive

The supplied `Capitalism Plus101.zip` passes ZIP CRC validation. It contains
585 files and has SHA-256
`e578a84cc7669da94973cf4eeb582a8a8aa108d524dbfbd043b6422b4c2850f2`.
It includes old user saves and configuration files, so its full inventory is
**not** proof of a pristine Steam depot's contents. Only this exact archive is
covered by the measurements below.

| Observation | Result |
|---|---|
| Main executable | `CapPlus.exe`, 1,156,608 bytes, SHA-256 `b68a781b351fb9951992906a83770d0f46eba4d000c9f2ddb145dd9a45e34cd7`; PE32/i386 Windows GUI image, with an embedded `Version 1.01` string. |
| Imports | `SDL3.dll`, `KERNEL32.dll`, `USER32.dll`, `ole32.dll`, `WINMM.dll`. The supplied ZIP includes `SDL3.dll` (2,328,064 bytes; SHA-256 `d60669949ab81274e6f6e92db3f7a1fcd04f05a344df77a365f96c33ac4f84f2`). No DOSBox executable or DOS LE game executable appears in this ZIP. |
| Known core data | All 72 core files are present; 71 have the same SHA-256 as the two measured retail 1.0 installations. `Resource/I_SCEN.RES` retains its size (1,611,364 bytes) but differs (SHA-256 `6206a056af6d5a0ac2e1b8ead174eb17285e6da87aa7d6a7f0ade9655dada379`). Its 19-member index and offsets remain intact; the main-menu member and 14 small button-image members differ. |
| Other packaged files | Relative to the supplied retail Windows **working directory** (113 files), 98 same-path files are byte-identical, four differ (the UI resource plus mutable configuration, hall of fame and sound settings), 483 paths appear only in this ZIP, and 11 only in the old working directory. The new-only paths include a different executable, SDL3, loose scenario/tutorial content and 388 OGG files. Some old-only OGGs were user-added replacement music; path additions alone do not establish new game features. |
| Binary lineage clue | After normalizing directory prefixes in printable `.cpp` filename strings, 116 of 117 basenames from the retail Windows executable also occur in the 1.01 executable. This **strongly suggests shared source lineage**; strings alone cannot establish which source was used or whether simulation behavior is unchanged. |

The current `capplus-inspect` recognized-build list still contains only the
two unmodified retail binaries. The 1.01 executable is reported as an **unknown
build with a PE header**. A synthetic regression test prevents the filename
`CapPlus.exe` from incorrectly labeling an unknown PE build as DOS. The archive
passes deep inspection of its supported data families, but four bundled saves
hit the existing save-section resolver's limits.

All seven bundled `.SAV` files carry version `100` in their headers. Three
smaller files (`21ST_001` through `003`) resolve all 24 save sections. Four
larger files (`21st_004`, `D1`, `D2`, `W1`) do not resolve with the current
fixed-section assumptions; their ZIP timestamps precede the 1.01 announcement.
These parser failures are **not evidence that 1.01 changed the save format**.
No supplied save establishes a live load or resave under this release.

## Remaining compatibility tests

Track measurements and decisions in [issue #28](https://github.com/cciacona/capplusplus/issues/28).

Keep the installed files and saves private. Record only their names, lengths,
cryptographic hashes, structural observations and sanitized experiment results
in the repository; follow the [clean-room policy](../CLEAN_ROOM.md).

### First controlled 1.01 save test

The supplied `21ST_001.SAV` is a suitable **retail DOS** starting point: it is
542,709 bytes, SHA-256
`4bf3a8f20777be56b0ade3ad3ad1f3ab593d18e12ec859cca0a1f85bbc883f4b`,
with a version-100 header, 24 resolved sections, game date 1990-01-04,
16 accumulated playing seconds and RNG state `0x47A28C03`. Its previously
supplied retail Windows resave `21ST_002.SAV` retained that date but recorded
29 seconds and RNG state `0xA58A72CE`. An unchanged date alone is therefore
insufficient to call a load/resave state preserving.

1. In Steam's **Properties → Installed Files**, record the installed build ID.
   Hash the installed `CapPlus.exe` and compare with the archive executable's
   SHA-256 above before attributing a play test to the measured archive.
2. Keep an untouched copy of `21ST_001.SAV` outside the game's save directory.
   With the game closed, ensure a copy is available for loading in 1.01. Do
   not overwrite the only copy or use an existing save slot as the output.
3. Launch 1.01, load `21ST_001.SAV`, pause as soon as the game permits, and
   save into a **different** slot without issuing gameplay commands. Record
   whether the load succeeded, any warnings, whether time advanced before the
   pause, the displayed game date before/after, and the output filename. A
   failed load is a result; do not modify the old save to make it load.
4. Start a separate new game under 1.01, pause and save in another new slot.
   This independent save establishes what 1.01 writes without requiring it to
   accept a retail save. Keep both resulting saves private and provide them
   for analysis alongside the installed build ID and installed executable hash.
5. Compare each output's header version, section chain, length, date, clock,
   RNG and section-level changes with the untouched input and the retail
   `001` → `002` control. If the game advanced a day or the start states
   differ, record that limitation; do not label the pair a no-op equivalence.

### Follow-up analysis

1. Capture the Steam app manifest or the installed build ID to pin the exact
   Steam depot represented by this archive. Resolve the four larger pre-update
   saves under [issue #8](https://github.com/cciacona/capplusplus/issues/8)
   without weakening existing fixed-section invariants.
2. On copies of the existing controlled saves, test Steam 1.01 loading and a
   paused no-op resave. Record game date, elapsed time, RNG state and other
   relevant state before/after each operation. Compare save header, version,
   length, all section markers, counters and byte ranges with the existing
   DOS/Windows controls. Document rejected saves and crashes as observations
   too. Do not treat two saves as same-state merely because they share a slot name.
3. Probe any gameplay or presentation differences that the inventory and save
   tests reveal. Add sanitized [experiment records](experiments.md) for
   behavioral claims. Decide whether 1.01 is a compatible additional oracle or
   a distinct profile, then revise the [roadmap](../ROADMAP.md), the
   [known-build decision](decisions/0001-narrow-original-build-support.md), and
   recognition code with behavioral evidence. Keep the new executable hash out
   of the recognized-build set until that scope is explicit.

The current [Cap++ 1.0 roadmap](../ROADMAP.md) is a version of **this project**.
The Steam release's 1.01 label does not change Cap++ milestone numbering or the
existing 1.0 acceptance criteria by itself.

[steam]: https://store.steampowered.com/news/app/450120/view/708909893000627895?l=english
[steamdb]: https://steamdb.info/patchnotes/25547109/
[branches]: https://steamdb.info/app/450120/depots/
[depot]: https://steamdb.info/depot/450121/
