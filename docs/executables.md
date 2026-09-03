# Executable survey

This document records the first reproducible static survey of the user-supplied,
unmodified Capitalism Plus executables. It describes file-format facts and
observable platform boundaries only. It does not contain executable bytes,
decompiler output, or reconstructed proprietary source.

Run the survey locally with files from your own copy:

```bash
capplus-inspect inspect CAPPLUS.EXE --json > capplus-dos.json
capplus-inspect inspect CapWin.exe --json > capplus-windows.json
```

Or create two detailed reports and a compact cross-build comparison in one
reproducible step from a source checkout:

```bash
PYTHONPATH=src python3 scripts/executable_survey.py \
  --dos /path/to/CAPPLUS.EXE \
  --windows /path/to/CapWin.exe \
  --output executable-reports
```

The script refuses to replace an existing report unless `--force` is supplied.

Printable strings are counted by default but included in JSON only when
`--include-strings` is supplied. Use `--minimum-string-length N` to adjust the
default threshold of five characters. Treat extracted strings as leads rather
than proof of program behavior.

## Sources and method

The parser is independently written from public format documentation:

- Microsoft's [PE format specification](https://learn.microsoft.com/en-us/windows/win32/debug/pe-format)
  defines the Windows headers, sections, data directories, and imports.
- Open Watcom's pinned
  [`exe386.mh`](https://github.com/open-watcom/open-watcom-v2/blob/75cae3a12af14dd18428e96f53763c1d57ded4bb/bld/os2api/incl32/exe386.mh)
  and
  [`strucs.inc`](https://github.com/open-watcom/open-watcom-v2/blob/75cae3a12af14dd18428e96f53763c1d57ded4bb/bld/causeway/inc/strucs.inc)
  define the relevant Linear Executable fields and flags.

Results were cross-checked with `file` and GNU `objdump` where those tools
support the format. `objdump` independently agrees with the Windows PE header,
section table, and complete import table. The installed `objdump` does not parse
the DOS LE payload, so the LE result is checked against the public structures
and synthetic tests.

## Build identities

| Build | File size | SHA-256 | Container |
|---|---:|---|---|
| DOS `CAPPLUS.EXE` | 848,637 bytes | `76867a7cb9ba913cfb3390731361ef8e560b2ed087632389e525ad22ccb07bda` | MZ stub + 32-bit LE |
| Windows `CapWin.exe` | 709,120 bytes | `f887e1c4d16c7370caccbb362515e45a406e249bdf5397cd6f494edea2e16c0c` | PE32 |

These hashes identify only the analyzed files. A different hash is not by
itself evidence of tampering; it may be another legitimate release.

## DOS executable

`CAPPLUS.EXE` contains an LE header at file offset `0x28B8`. The header declares
an Intel 80386 module with a 4,096-byte page size and entry point object 1 plus
`0x8621C`.

| Object | Base | Virtual size | Pages | Declared flags |
|---:|---:|---:|---:|---|
| 1 | `0x00010000` | `0x8FFD0` | 144 | read, execute, 32-bit default |
| 2 | `0x000A0000` | `0x1F880` | 16 | read, write, 32-bit default |

The LE target-OS field is `1`, whose format-defined label is OS/2. That field
does not mean the game requires OS/2: strings in the executable identify the
Watcom 32-bit runtime and Rational DOS/4G, and the supplied installation starts
it through DOS/4GW. The LE imported-module table is empty, so there is no
module-name boundary equivalent to the Windows import table.

## Windows executable

`CapWin.exe` is an Intel i386 PE32 Windows GUI image. Its PE header starts at
`0x80`, the image base is `0x00400000`, and the entry point RVA is `0x00088E00`.
The COFF timestamp decodes to `1997-04-29T13:58:52Z`; this is a header value,
not independent proof of the source-build date. The linker-version field is
`3.0`.

| Section | RVA | Raw file range | Virtual size | Main permissions |
|---|---:|---:|---:|---|
| `.text` | `0x00001000` | `0x00000400` + `0x8FE00` | `0x8FD9F` | read, execute |
| `.rdata` | `0x00091000` | `0x00090200` + `0x4000` | `0x3EC8` | read |
| `.data` | `0x00095000` | `0x00094200` + `0xB000` | `0x1BEA0` | read, write |
| `.idata` | `0x000B1000` | `0x0009F200` + `0xC00` | `0xA38` | read, write |
| `.rsrc` | `0x000B2000` | `0x0009FE00` + `0x400` | `0x39C` | read |
| `.reloc` | `0x000B3000` | `0x000A0200` + `0xD000` | `0xCF02` | read, discardable |

The image imports 96 symbols from six libraries:

| Library | Symbols | Observable boundary |
|---|---:|---|
| `KERNEL32.dll` | 56 | files, memory, process, time, and runtime services |
| `USER32.dll` | 25 | windows, messages, input, dialogs, and cursors |
| `GDI32.dll` | 1 | Windows graphics-device interface |
| `WINMM.dll` | 12 | multimedia timing and audio services |
| `DSOUND.dll` | 1 | DirectSound creation |
| `DDRAW.dll` | 1 | DirectDraw creation |

This makes the Windows platform seam unusually clear: a modern engine can
replace those presentation and operating-system services without treating them
as economic-simulation rules. The imports do not reveal the simulation itself.

## Reproducibility and limits

The automated suite builds synthetic PE32 and LE fixtures in memory. It tests
header bounds, sections, imports, LE objects and names, opt-in string output,
plain-MZ handling, CLI routing, and the three-report survey workflow without
including original data.

The current parser intentionally stops short of disassembly and control-flow
analysis. The next executable-analysis targets are:

1. Cross-reference file-format strings and imported file APIs to locate the
   original resource, map, game-set, and save loaders.
2. Identify the simulation clock and random-number state update sites using
   save observations as external test oracles.
3. Map DirectDraw, DirectSound, WinMM, and Windows-message call sites to isolate
   rendering, audio, timing, and input from platform-independent behavior.
4. Record behavior as black-box contracts and synthetic tests before writing
   replacement engine code.
