# Capitalism Plus reference builds

This inventory separates **measured files** from **tested game behavior**. Steam
1.01 is the sole [Cap++ 1.0 target](decisions/0005-steam-1-01-only-target.md);
retail DOS and Windows 1.0 remain historical research references. The
[official Steam announcement][steam] dated 2026-09-26 calls its
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
| Retail DOS 1.0 | Supplied unmodified installation; [executable hash](executables.md#build-identities) and [validation record](validation.md) | Known MZ/LE executable; its 72 core files match the supplied Windows installation | Paired version-100 saves and controlled executable probes | Historical evidence; identifiable by `capplus-inspect`, **not supported** by Cap++ 1.0 |
| Retail Windows 1.0 | Supplied unmodified installation; [executable hash](executables.md#build-identities) and [validation record](validation.md) | Known PE32 executable; the 72 shared core files match DOS | Paired version-100 saves, cross-loading observation and controlled executable probes | Historical evidence; identifiable by `capplus-inspect`, **not supported** by Cap++ 1.0 |
| Steam 1.01 measured archive, received 2026-09-26 | User-supplied ZIP, hashes and static comparison below; [publisher announcement][steam] | PE32 executable, SDL3 import, 71/72 retail core-file hashes match; one changed UI resource | Seven pre-update saves are in the archive; one separately supplied 1.01-created save parses as version 100 with 24 sections; no controlled resave or gameplay probe | Sole supported **input target** for Cap++ 1.0; exact executable and 72 target core hashes recognized, gameplay parity not certified |

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

`capplus-inspect` identifies the exact 1.01 executable and all 72 target core
files. It reports the archive as a supported **asset/input target**, while
separately identifying old retail executables as historical. A synthetic
regression test prevents an *unknown* PE called `CapPlus.exe` from being labeled
as DOS. Matching an executable and core data does not certify the game's
behavior, the exact Steam depot, or save compatibility. Four bundled old saves
hit the existing save-section resolver's limits during deep inspection.

All seven bundled `.SAV` files carry version `100` in their headers. Three
smaller files (`21ST_001` through `003`) resolve all 24 save sections. Four
larger files (`21st_004`, `D1`, `D2`, `W1`) do not resolve with the current
fixed-section assumptions; their ZIP timestamps precede the 1.01 announcement.
These parser failures are **not evidence that 1.01 changed the save format**.

## Separately supplied Steam 1.01 save

On 2026-09-29 the user identified a separately uploaded `21ST_001.SAV` as a
save written by the Steam release. It is **not** the older same-named DOS save
in the ZIP. The new file is 539,679 bytes, SHA-256
`98eab55b7813d979a38262cc68ac1dd08a7d1b81c8950cf25a86df184dfc4bbd`.
Its saved wall-clock sample corresponds to 2026-09-29T15:47:39Z, consistent
with the reported fresh creation, though a save file alone cannot establish
the installed Steam depot build ID or executable hash.

The read-only inspector resolves a **single complete 24-marker chain** in the
same marker order as the historical version-100 saves. The header still reports
version `100`; all 15 currently cataloged fixed-size sections retain their
expected sizes. It decodes a consistent 65-byte clock record (1990-01-02,
five accumulated playing seconds), RNG state `0x6169BC67`, seven towns and 343
town/item records. These are structural observations of **one** 1.01-created
save, not evidence that every later game state, load, writer, or multiplayer
save behaves identically.

The older `21ST_001.SAV` is 542,709 bytes, SHA-256
`4bf3a8f20777be56b0ade3ad3ad1f3ab593d18e12ec859cca0a1f85bbc883f4b`,
and represents 1990-01-04 with a different RNG state. The filenames and
scenario reference match, but the dates, RNG and variable section sizes differ.
They are **not equivalent starting states**, so a byte-level comparison cannot
measure a 1.01 load/resave or establish retail save migration.

## Target validation still needed

Track measurements and decisions in [issue #28](https://github.com/cciacona/capplusplus/issues/28).

Keep the installed files and saves private. Record only their names, lengths,
cryptographic hashes, structural observations and sanitized experiment results
in the repository; follow the [clean-room policy](../CLEAN_ROOM.md).

1. Record the installed Steam build ID (or app manifest) and hash the installed
   executable to connect a live play test to this measured archive. The archive
   alone does not identify its depot manifest.
2. The first 1.01-created save is now measured. Preserve it privately and, when
   testing persistence, load a copy in Steam 1.01, pause and resave to a **new**
   slot without gameplay commands. Compare its version, sections, date, clock,
   RNG and byte changes with this exact starting save. Record any time advance
   or failed load. **No retail save needs to be loaded into Steam** for this target.
3. Inventory a clean Steam installation, including scenarios, tutorials, sound,
   music and other loose content; distinguish depot files from user saves and
   settings. Probe gameplay and presentation behavior under this exact target
   and publish sanitized [experiment records](experiments.md). Historical
   retail observations can guide probes but cannot certify Steam 1.01 parity.

Retail 1.0 save loading and DOS/Windows normalization remain optional migration
research under [issue #8](https://github.com/cciacona/capplusplus/issues/8).
They do not block the [Cap++ 1.0 roadmap](../ROADMAP.md).

The current [Cap++ 1.0 roadmap](../ROADMAP.md) is a version of **this project**.
The Steam release's 1.01 label does not change Cap++ milestone numbering.

[steam]: https://store.steampowered.com/news/app/450120/view/708909893000627895?l=english
[steamdb]: https://steamdb.info/patchnotes/25547109/
[branches]: https://steamdb.info/app/450120/depots/
[depot]: https://steamdb.info/depot/450121/
