# Original file-loader boundaries

This document records clean-room file-loading contracts recovered from the
user-supplied, unmodified Capitalism Plus DOS and Windows executables. It
contains addresses, observable inputs and outputs, and behavioral facts—not
decompiler output or copied implementation.

Generate the underlying reports locally from files you own:

```bash
PYTHONPATH=src python3 scripts/loader_survey.py \
  --dos /path/to/CAPPLUS.EXE \
  --windows /path/to/CapWin.exe \
  --output loader-reports
```

The command writes detailed DOS and Windows reports, a compact cross-build
summary, and a synthetic framed-record probe. It refuses unknown builds unless
`--allow-unknown` is supplied and never writes to either executable.

## Result

Both builds contain the same file abstraction above different compiler
runtimes. Seven operations have matching inputs, outputs, edge behavior, and
call relationships. The DOS build also exposes a separate current-position
helper. Addresses below are loaded virtual/linear addresses; the generated
reports also include their raw file offsets.

| Operation | Windows address | DOS address | Observable contract |
|---|---:|---:|---|
| Open | `0x0044B590` | `0x0008F398` | Open a binary file for reading and return a success flag |
| Create | `0x0044B640` | `0x0008F41A` | Create/truncate a binary read/write file and return a success flag |
| Close | `0x0044B6F0` | `0x0008F47B` | Close a valid handle and restore the closed sentinel |
| Write | `0x0044B750` | `0x0008F505` | Write exactly the requested bytes, optionally preceded by a 16-bit size |
| Compatible read | `0x0044B7E0` | `0x0008F58F` | Read a size-prefixed record with old/new-size tolerance |
| Seek | `0x0044BB90` | `0x0008F910` | Move relative to an origin and return the resulting position |
| Size | `0x0044BBB0` | `0x0008F994` | Return the open file's length or a negative error value |
| Current position | folded into seek | `0x0008F929` | Query the current position without changing it |

The object keeps a 33-character path plus terminator, a handle at offset
`0x22`, an error-reporting flag at `0x26`, and a framed-record flag at `0x2A`.
The two compilers use different numeric open flags, but both select binary mode
and the same read versus create/truncate behavior.

## Windows operating-system boundary

The PE import-address-table slots are now part of the deterministic executable
report. Core open/read/write/seek/close paths lead through the compiler runtime
and the shared `File` abstraction. The standalone deletion path and an
additional writer are listed separately rather than forced into that chain.

| Win32 API | IAT address | Code references | Immediate engine/runtime boundary |
|---|---:|---:|---|
| `CreateFileA` | `0x004B12B0` | 1 | runtime open beginning at `0x004904C0` |
| `ReadFile` | `0x004B12B4` | 2 | runtime read at `0x00490250` |
| `WriteFile` | `0x004B1280` | 3 | runtime write at `0x0048D300` plus one separate writer |
| `SetFilePointer` | `0x004B1268` | 1 | runtime seek at `0x0048D530` |
| `CloseHandle` | `0x004B12C4` | 2 | runtime close at `0x0048F900` and open-error cleanup |
| `DeleteFileA` | `0x004B1258` | 1 | standalone deletion helper |

This is a platform seam, not an economic-simulation dependency. A modern
implementation can replace it with ordinary cross-platform file services while
preserving the contracts above.

## Filename and extension mapping

The survey maps 32-bit references to printable file names and extensions, then
associates them with direct open/create callers and their immediate callers.
Function-boundary discovery uses MSVC `0xCC` padding on Windows and the Watcom
stack-check prologue on DOS. Associations are therefore labeled candidates in
the machine report even when the cross-build match is exact.

Representative matched boundaries are:

| Family | Observed reference(s) | Windows boundary | DOS boundary |
|---|---|---:|---:|
| Configuration | `CAPITAL.CFG` | `0x0041DEF0` create, `0x0041DF90` open | `0x0002011A` create, `0x00020183` open |
| Hall of fame | `CAPITAL.HOF` | `0x0041E030` create, `0x0041E0F0` open | `0x000201D7` create, `0x0002025E` open |
| Sound settings | `CAPITAL.SND` | `0x0041E1B0` create, `0x0041E2E0` open | `0x000202D2` create, `0x000203C1` open |
| Save/scenario list | `*.SAV`, `*.SCN` | `0x0041E3F0` | `0x00020485` |
| General resources | `RESOURCE\…`, game-set auxiliaries | `0x00403350` | `0x00080384` |
| Firm/town/logo resources | `.DFI`, `.FI`, `.IL`, named image resources | `0x0043D1F0` | `0x00080094` |
| Item/person resources | `.II`, `.IP`, `I_PERSON.RES` | `0x004566C0` | `0x00080956` |
| Resource text/index pair | `.RTX`, `.RTI` | `0x0047AB40` | `0x00080A9C` |
| Interface colors | `RESOURCE\IFCOLOR.RES` | `0x0044E050` | `0x0008C89E` |
| Selected scenario | `SELSCEN.SCP` | `0x0047D850` | `0x0001BF42` |
| Scenario definition | `.SCP`, `.SCT` | `0x0047DF00` | `0x0001C5EB` |
| Tutorial/translation | `.TUT`, `.HIN`, `.SPH`, `TRANSLAT.RES` | `0x0047E800` | `0x0008F9FC` |
| Map list | `*.MAP` | `0x0047F520` | `0x0004A713` |
| Save write/load | caller-supplied `.SAV`; `AUTOSAVE.SAV` upstream | `0x0047C8E0` / `0x0047C9C0` | `0x0001DB44` / `0x0001DBF6` |
| Map write/load | caller-supplied `.MAP` | `0x0047F6D0` / `0x0047F810` | `0x0004A876` / `0x0004A992` |

The detailed reports found six referenced families in each build: resources,
game sets, maps, saves, scenarios, and support files. Every one of the 58
Windows and 83 DOS file-like strings retained by the filter has at least one
candidate code reference. The DOS count is higher primarily because it retains
additional platform resources and extensions.

There are 23 direct callers of the Windows read-open routine and 24 in DOS.
Both builds have six direct create callers. The extra DOS open path is
platform-specific; it does not imply a data-format difference.

## Framed-record compatibility contract

When framing is enabled, a record begins with a little-endian 16-bit stored
size. The caller also supplies the size it understands:

1. A zero stored size means “use the caller's expected size.”
2. If the stored size is smaller, the loader reads it and fills the remaining
   destination bytes with zero.
3. If the stored size is larger, the loader reads the understood prefix and
   seeks past the unknown tail.
4. If the physical file ends before the declared stored size, the read fails
   through the ordinary short-read path.

This explains the explicit version tolerance already observed in version-100
saves. `read_compatible_record()` is the independent replacement contract used
by the save inspector.

### Controlled malformed-file probe

`run_framed_record_probe()` performs four in-memory tests with synthetic data:

| Case | Stored size | Expected size | Result |
|---|---:|---:|---|
| Exact | 8 | 8 | eight payload bytes preserved |
| Older/smaller | 4 | 8 | four bytes read, four zero bytes appended |
| Newer/larger | 12 | 8 | eight bytes returned, four-byte tail skipped |
| Malformed truncation | declares 8, contains 4 | 8 | rejected at the payload boundary |

All four checks pass in the committed synthetic suite and against the packaged
survey command. The malformed case reports the exact required and available
byte counts. No original bytes are part of the fixture. This validates the
replacement behavior contract derived independently from matching DOS and
Windows control flow; it is not a claim that the original GUI was run under an
emulator for this test.

## Confidence and limits

- **Confirmed by static executable analysis:** addresses, direct-call counts,
  PE IAT slots, file-like strings, and immediate value references.
- **Confirmed across both builds:** the seven shared contracts, record-size
  tolerance, and the representative loader pairs above.
- **Confirmed by synthetic behavior test:** exact, smaller, larger, and
  physically truncated framed records.
- **Heuristic:** candidate function boundaries and filename associations in the
  generated reports. They are useful routing evidence, not reconstructed source.

The scanner deliberately recognizes only direct x86 `E8` calls and 32-bit
immediate references. It does not pretend to be a disassembler and may omit
indirect paths. Known-build call counts are an explicit verification gate, so a
changed executable fails closed unless generic inspection is requested.
