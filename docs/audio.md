# Audio formats and playback evidence

The inspector frames and exports the original sound bank and XMIDI members,
compares Windows effects against the shared bank, and reads sound settings and
single-BIN CUE geometry. It does not play audio, synthesize XMIDI, or decode OGG
or FLAC. Structural preservation and observed playback behavior are separate
contracts; the latter still needs controlled original-game experiments.

## Reference inputs

These identities refer to unmodified user-owned files. Only metadata and
newly written readers belong in the repository.

| Input | Bytes | SHA-256 |
|---|---:|---|
| `SOUND.RES` | 483,576 | `59c26d11bc013e74e71dba27d62c611c61d64cad9a5ba82cb51832b029ef29da` |
| `MUSIC.RES` | 163,201 | `2047c2de2ad5c34b7f5c3abf3c34d73c3c6e63acf7e54e0b0e7d3f23e1d6bb19` |
| DOS `CAPPLUS.EXE` | 848,637 | `76867a7cb9ba913cfb3390731361ef8e560b2ed087632389e525ad22ccb07bda` |
| Windows `CapWin.exe` | 709,120 | `f887e1c4d16c7370caccbb362515e45a406e249bdf5397cd6f494edea2e16c0c` |

Both installations have byte-identical banks. The 25 intact Windows files in
`Sounds/` have extensionless names matching the sound-bank directory. Their
PCM payloads were freshly compared with every bank member: all 25 match exactly.

## Bank framing and identifiers

Both banks use the existing named-resource container: a little-endian `u16`
count, followed by count-plus-one 13-byte directory slots. Each slot contains a
nine-byte name and little-endian `u32` absolute offset. The final slot is an
empty-name EOF sentinel. Consecutive offsets bound each payload.

| Bank | Entries | First payload offset | Member contract |
|---|---:|---:|---|
| `SOUND.RES` | 25 | 340 | Headerless mono unsigned eight-bit PCM |
| `MUSIC.RES` | 24 | 327 | Complete XDIR/CAT XMID file |

Reports retain the previous `named_container` format and member metadata,
adding `audio_family` and audio fields. `logical_id` is the inspector's stable
one-based directory ordinal; it is not a claim that an executable dispatches
every member by that ordinal. Names are case-insensitively unique, entries must
be nonempty, and offsets and payload hashes cover every member. Export filenames
use the ordinal and a sanitized name, so a member cannot select an output path.

## PCM rates and Windows WAVs

There is no sample-rate field in `SOUND.RES`. The two builds provide different
rate evidence, which must remain selectable instead of being silently normalized.

| Export profile | Rate in Hz | Evidence |
|---|---:|---|
| `windows` (default) | 11,127 | Every loose WAV declares this rate, byte rate 11,127 and block alignment 1 |
| `dos` | 11,000 | DOS effect routine `0x00090E69` writes `0x2AF8` into its driver sample descriptor |

These are declared/requested rates. Actual hardware output and audible pitch
have not been measured. The DOS streamed-audio routine separately requests
22,050 Hz; that is not evidence for assigning 22,050 Hz to bank effects.

Each supplied WAV contains `fmt `, `INFO`, and `data` chunks. The `fmt ` payload
is 16 bytes, with PCM format tag 1, one channel and eight-bit samples. The
`INFO` payload is preserved as uninterpreted metadata. Chunk lengths exclude
their headers and any word-alignment byte, following the
[RIFF specification](https://learn.microsoft.com/en-us/windows/win32/xaudio2/resource-interchange-file-format--riff-).
Channel count, bit depth, block alignment, and byte rate are validated together
according to [WAVEFORMATEX](https://learn.microsoft.com/en-us/windows/win32/api/mmeapi/ns-mmeapi-waveformatex).

Ten original WAVs omit the alignment byte after an odd-sized final `data`
chunk. The reader accepts exactly this terminal case and reports
`missing_terminal_padding`. Other truncated headers, payloads, or padding are
errors. Byte-preserving round trips retain the omission; new WAV exports write
the standard zero pad. Export adds a new minimal PCM header without changing
any source sample. It does not attempt to recreate the loose file's metadata.

## XMIDI framing

All 24 music members have the following bounded structure. IFF chunk sizes are
big-endian; the observed INFO and TIMB counts are little-endian.

| Structure | Contract |
|---|---|
| `FORM XDIR` | Directory containing one two-byte `INFO` sequence count |
| `CAT XMID` | Ordered `FORM XMID` children matching that count |
| `TIMB` | Optional per-sequence `u16` count and exactly two bytes per entry |
| `EVNT` | One nonempty event payload per sequence, preserved opaquely |
| Other chunks | Bounded and preserved, with no invented meaning |

Every reference member has one sequence, one TIMB and one EVNT. The parser
also handles multiple correctly counted sequences, odd-chunk padding and
unknown leaf chunks. It limits input to 64 MiB, 4,096 chunks and eight nested
group levels. Banks are limited to 4,096 nonempty members.

Event timing, notes, controllers, instrument semantics, loops and synthesis
are not decoded. Export writes each complete original member unchanged as
`.xmi`; it is not an SMF/MIDI conversion. No correspondence between these 24
members and the eight CD tracks has been established. The exact executables
contain no discovered printable `MUSIC.RES` reference; this absence does not
prove that every possible music-bank path is unreachable.

## Sound settings

`CAPITAL.SND` consists of nine unframed little-endian `u16` slots, exactly 18
bytes. Windows writer `0x0041E1B0` and reader `0x0041E2E0` issue nine matching
word operations. The supplied DOS values are `1,1,1,1,1,0,1,1,0`; Windows has
nine ones. Slot names and value domains remain unassigned: the parser does not
enforce a Boolean interpretation from just these samples.

## Static playback contracts

The addresses below are virtual addresses in the exact reference profiles,
using the same LE mapping as the [loader survey](loaders.md). They document
manually audited call paths, not runtime traces or portable symbols.

| Windows address | Observed operation |
|---|---|
| `0x00410230` | Poll enabled music; request another selection when the playing flag is clear |
| `0x00410290` | Reseed Misc, request `random(8)`, add one, invoke the CD wrapper |
| `0x004423F0` | Open MCI CD audio and select TMSF time format |
| `0x00442480` | Translate logical selections 1–8 to physical tracks 2–9 |
| `0x0046AA10` | Stop the prior CD command, start selection and set a playing flag |
| `0x0041CDE3` | Clear that flag on the `MM_MCINOTIFY` message path |
| `0x0046AA70` | Open a named loose effect and start a looping DirectSound buffer |
| `0x0047C530` | Reseed the global Misc object through the local-time conversion path |

For selection `n < 8`, MCI playback starts at track `n+1` and ends at the start
of track `n+2`; selection 8 starts track 9 without a TO boundary. The commands
request notification. This agrees with the documented
[MCI_PLAY flags](https://learn.microsoft.com/en-us/windows/win32/multimedia/mci-play)
and [TMSF track addressing](https://learn.microsoft.com/en-us/windows/win32/multimedia/playing-a-compact-disc-track).
The notification branch clears the playing flag without testing notification
success. Polling can then choose another track. No no-repeat filter is present
in the inspected selector, and this is not a proven fixed playlist. The inner
play wrapper returns success even along an MCI-error path, so a set flag alone
does not prove that physical playback started.

Music selection passes the same global Misc object (`0x004A6180`) used by the
known RNG contract. Its reseed path reaches `GetLocalTime` through IAT slot
`0x004B12FC` and stores the resulting seed at Misc offset `0x79`. Subsequent
selection uses the recovered LCG. **Inference requiring experiment:** enabled
music may change simulation RNG state according to wall-clock time. Issue
[#11](https://github.com/cciacona/capplusplus/issues/11) must control music state
and observe RNG before/after initial selection and track notifications.

| DOS address | Observed operation and limit |
|---|---|
| `0x00090C19` | Initialize `RESOURCE/SOUND.RES` |
| `0x00090E69` | Resolve an effect, accept at most 44,100 bytes and request 11,000 Hz |
| `0x00090F0E` | Set up streamed audio with a separate 22,050 Hz descriptor |
| `0x00090D42` | Contained CD selector uses the reported disc track range |
| `0x00090DAA` | Resolve a CD track position/length and issue playback |
| `0x000910AF` | Poll CD position with timing and boundary checks |

No direct call to the DOS CD selector was found in the bounded call scan.
Indirect reachability, active DOS music behavior, complete effect triggers,
stream refill/stop behavior and runtime CD failure handling remain unverified.
Presence of a routine is not proof that the shipped game uses it.

## CD layout and replacement names

The following geometry comes from the earlier complete-disc analysis, not a
fresh read of the now-truncated local CD ZIP. Its single raw BIN was 603,473,808
bytes (256,579 sectors of 2,352 bytes), SHA-256
`e677583ed80e8871dc02b7e4b1ca30856d9dc73108f4dc2261c7e5fb20087b75`.
The CUE SHA-256 was
`05e9a190c4b43232152be60c4b0652dd3bbacee7619b7b086d6e7cf557657721`.
Track 1 is MODE1/2352 at `00:00:00`; tracks 2–9 are CD audio.

| Selection | CD track | INDEX 01 (MM:SS:FF) | Program sectors | Future replacement stem |
|---:|---:|---|---:|---|
| 1 | 2 | 49:12:12 | 4,445 | `music/track02` |
| 2 | 3 | 50:11:32 | 4,302 | `music/track03` |
| 3 | 4 | 51:08:59 | 4,272 | `music/track04` |
| 4 | 5 | 52:05:56 | 4,660 | `music/track05` |
| 5 | 6 | 53:07:66 | 4,463 | `music/track06` |
| 6 | 7 | 54:07:29 | 3,714 | `music/track07` |
| 7 | 8 | 54:56:68 | 4,665 | `music/track08` |
| 8 | 9 | 55:59:08 | 4,646 | `music/track09` |

An audio sector represents 588 stereo sample frames at 44,100 Hz. The original
CUE labels no INDEX 00 or PREGAP, although the earlier raw-sector analysis found
150 stored audio pregap sectors after 221,262 valid Mode 1 sectors and before
track 2. CUE geometry alone cannot discover that boundary; it attributes the
whole preceding span to track 1.

The CUE reader accepts this single-BINARY-file mixed-mode layout, with optional
INDEX 00 before an audio track. Multiple FILEs, other track modes and explicit
PREGAP/POSTGAP directives produce an unsupported-layout error. The FILE path is
metadata only and is never opened. Optional `--bin-size` supplies geometry for
the final track; it does not authenticate a BIN, extract audio, validate sectors
or prove that a declared track actually contains CD audio.

The `.ogg`/`.flac` replacement names are a proposed engine convention. Earlier
complete-disc work compared the supplied OGGs with CD samples, but this pass
does not revalidate those transcodes. Decoder choice, missing-track fallback
and runtime track lifecycle belong to the engine milestone.

## Reproduction and CLI

```powershell
capplus-inspect inspect "RESOURCE\SOUND.RES" --json
capplus-inspect inspect "RESOURCE\MUSIC.RES" --json
capplus-inspect inspect "CAPITAL.SND" --json
capplus-inspect export-audio "RESOURCE\SOUND.RES" ".\private-corpus\effects" --kind sound
capplus-inspect export-audio "RESOURCE\SOUND.RES" ".\private-corpus\effects-dos" --kind sound --sound-profile dos
capplus-inspect export-audio "RESOURCE\MUSIC.RES" ".\private-corpus\xmidi" --kind music
capplus-inspect compare-audio "RESOURCE\SOUND.RES" "Sounds" --json
capplus-inspect inspect-cue "Capitalism Plus.cue" --bin-size 603473808 --json
```

Exports include a manifest of member order, names, offsets and input/output
hashes. All output collisions are checked before writing; `--force` permits
replacement of regular outputs but never the source or symlink destinations.
Writes are atomic per file, not a transaction across an entire export directory.
Comparison returns exit 3 for missing, additional, malformed or differing loose
effects; malformed bank or CUE input returns exit 2.

```bash
PYTHONPATH=src python scripts/audio_survey.py \
  --dos /private/dos/CAPPLUS.EXE --windows /private/win/CapWin.exe \
  --sound-bank /private/dos/RESOURCE/SOUND.RES \
  --music-bank /private/dos/RESOURCE/MUSIC.RES --sounds /private/win/Sounds \
  --output private-corpus/audio-survey.json
```

The script independently checks member structure, PCM equality and executable
identity, then reports address/file-offset mappings and direct-call candidates.
It does not rediscover semantics automatically. Only the documented executable
hashes permit playback-reference claims. Reports contain no sample/event bytes.

Issue [#5](https://github.com/cciacona/capplusplus/issues/5) remains responsible
for the outstanding playback experiments, XMIDI event semantics and any proven
music-bank/CD relationship. A complete user-owned BIN/CUE is needed to repeat
the full disc integrity and raw audio checks. The current structural slice and
synthetic tests do not certify native-engine audio parity.
