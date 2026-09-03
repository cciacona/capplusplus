# Cap++ 1.0 roadmap

**Cap++** is a clean, open-source reimplementation of **Capitalism Plus**.
Version 1.0 is not merely “playable.” Its target is complete
player-visible parity with the original game, running as a native modern
application while requiring assets from a legally owned DOS or Windows copy.

This roadmap is grounded in the shipped DOS and Windows data, the compatible
version-100 saves examined so far, and the feature inventory in the
[Capitalism Plus manual](https://cdn.akamai.steamstatic.com/steam/apps/450120/manuals/Capitalism_Plus_Manual.pdf).

## Definition of 1.0

Cap++ 1.0 is complete only when it can replace the original executable for
a normal player. It must:

1. Locate and validate an original DOS or Windows installation without changing it.
2. Load every shipped game set, map, scenario, tutorial, plan, graphic, sound,
   music track, and supported version-100 save.
3. Reproduce all original game modes, firms, functional units, reports,
   economic systems, AI behavior, goals, editors, and multiplayer functionality.
4. Preserve the original rules and limits in a selectable **Classic profile**.
5. Run natively on current 64-bit Windows, Linux, and macOS without DOSBox,
   Win16/Win32 compatibility layers, optical-disc checks, or mounted CD images.
6. Provide reliable windowed, borderless, and fullscreen operation; modern audio;
   arbitrary display scaling; remappable input; and deterministic simulation.
7. Save and resume all supported modes. Original version-100 save import is
   mandatory. Original-format export is a 1.0 target and may be disabled only
   for a structure that cannot be written without corrupting unknown data.
8. Pass a published parity test matrix against both original executables.
9. Ship no copyrighted game assets. The open-source release contains only new
   engine code, documentation, schemas, and synthetic tests.

“Player-visible parity” does not require reproducing original crashes, unsafe
pointer serialization, obsolete CD checks, timing tied to CPU speed, or the
IPX/serial/modem transport itself. It does require equivalent multiplayer play
over a modern network transport.

## Compatibility contract

Parity is divided into five independently testable layers.

| Layer | 1.0 requirement |
|---|---|
| Content | All supplied original data loads with the correct meaning and ordering. |
| Simulation | Given equivalent state, decisions and economic results match the original within documented numeric tolerances. |
| Interaction | Every original command, setup option, report, map mode, editor action, and shortcut has an equivalent. |
| Presentation | Original graphics, fonts, palette behavior, animation, sound effects, and music are presented correctly from user-owned files. |
| Persistence/network | Saves, scenarios, layout plans, hall of fame, configuration, and multiplayer state survive round trips. |

Integer, identifier, inventory, ownership, and event outcomes must match exactly.
Floating-point comparisons use field-specific tolerances established by controlled
experiments. The DOS and Windows originals already differ by 1–4 ULPs in several
market fields, so one deterministic canonical result is preferable to emulating
platform-dependent drift unless that drift changes a gameplay decision.

## Architecture fixed before gameplay work

The engine should keep compatibility and future expansion separate:

| Component | Responsibility |
|---|---|
| `capplus-inspect` | Fast-evolving Python format research, exporters, differential analysis, and experiment reports. |
| `libopencap-data` | Audited C++ readers/writers for original and open formats; no gameplay logic. |
| `opencap-sim` | Headless deterministic clock, economy, firms, people, finance, stock market, goals, and AI. |
| `opencap-client` | SDL3 renderer, UI, input, audio, music, maps, reports, and editors. |
| `opencap-net` | Command serialization, lobby, deterministic session control, checksums, reconnect, and spectator/replay foundations. |
| `opencap-test` | Black-box original-game probes, simulation snapshots, replay tests, and parity reports. |

The simulation must run headlessly and must not read wall-clock time, rendering
state, or nondeterministic platform APIs. Player and AI actions enter it as
timestamped commands. This makes save validation, multiplayer, replay, and
behavioral comparison use the same path.

The client uses a 640×480-compatible logical layout for Classic mode, but the
renderer itself is resolution-independent. Pixel-perfect integer scaling and a
modern scalable layout can coexist without changing simulation behavior.

## Release sequence

Versions are capability gates, not calendar promises. A milestone advances only
after its acceptance tests pass.

### 0.2 — Asset visibility and map overview

Status: implemented in `capplus-inspect` 0.2.

- Decode the 256-color palette structure.
- Export direct, sequential, offset-indexed, and named indexed images to lossless PNG.
- Preserve palette indices and the observed transparent index.
- Identify the `.MAP` core as a 240×198 grid of 47,520 eight-byte cells.
- Render the confirmed overview-palette byte and overlay city positions.
- Produce JSON manifests without modifying source data.

Exit gate: all 15 shipped maps render recognizable overviews; representative
portraits, terrain, firm, interface, scenario, and game-set images export
correctly from both identical asset sets.

### 0.3 — Complete original-data specification

- Decode all eight map-cell bytes and the 32-byte map footer through controlled
  map-editor experiments.
- Decode text, font, cursor, palette, terrain, help, language, layout-plan, and
  configuration resources.
- Catalog every graphic and animation frame, hotspot, transparent color, and
  palette rule.
- Decode the sound bank, music index, Windows extracted sounds, and CD/OGG track mapping.
- Specify `.SET`, `.II`, `.II2`, `.DFI`, `.FI`, `.IP`, `.PIC`, `.PLA`, `.PLO`,
  `.PLP`, `.RTI`, `.RTP`, `.RTX`, `.MAP`, `.SCT`, `.SAV`, `.CFG`, and `.HOF`.
- Assign semantic names to all 24 save sections and every persistent structure.
- Add bounds tests, malformed-input tests, corpus validation, and parser fuzzing.
- Publish versioned schemas and a provenance note for every inferred field.

Exit gate: a round-trip reader/writer can reconstruct every supported non-save
file byte-for-byte; save normalization can explain every changed byte in a
controlled no-op load/save test.

### 0.4 — Native engine shell

- Establish C++20, CMake, SDL3, continuous integration, sanitizers, and packaged
  builds for Windows, Linux, and macOS.
- Add installation discovery and hash-based compatibility reporting.
- Load original palettes, fonts, sprites, maps, strings, sound effects, and music.
- Reproduce the title sequence, main menu, browser/spinner controls, windows,
  pointer behavior, keyboard shortcuts, and pause/speed controls.
- Render regional and detailed maps with panning, selection, map modes, filters,
  firm markers, and original palette effects.
- Add pixel-perfect, aspect-correct, borderless/fullscreen, HiDPI, and modern audio options.

Exit gate: the application reaches every empty UI shell, displays every original
asset in the right palette and geometry, and can navigate a loaded map without
running an economic simulation.

### 0.5 — End-to-end business vertical slice

- Implement the deterministic calendar, speed levels, pause, RNG stream, command
  log, and an open development-save format.
- Mirror all new-game setup choices needed for one controlled configuration.
- Implement towns, consumers, one product chain, one local competitor, and
  import/local-market supply.
- Build, name, select, and demolish a department store and factory.
- Implement the nine-slot firm layout, functional-unit placement and links,
  purchasing, inventory, manufacturing, and sales.
- Implement quantities, capacity, utilization, costs, price, basic demand,
  revenue, expense, cash, and firm/product summaries.
- Save, reload, and replay the same vertical slice deterministically.

Exit gate: a scripted player can create a raw-material-to-retail chain and its
daily results match controlled original-game observations for a full simulated year.

### 0.6 — Complete production, logistics, and marketing economy

Implement every firm type:

- department store;
- factory;
- farm;
- research and development center;
- mine, oil well, and logging camp;
- television station and newspaper publisher.

Implement every functional-unit family and its original detail panel:

- advertising;
- crop growing;
- inventory;
- livestock raising and processing;
- manufacturing;
- private labeling;
- purchasing;
- research and development;
- sales;
- mining, oil extraction, and logging.

Complete:

- production methods and multi-input recipes;
- seasonal crops, soil/site effects, livestock cycles, quality, yield, and spoilage;
- raw-resource sites, reserves, discovery, extraction, and depletion;
- labor, wages, staffing, equipment procurement, training, experience, and unit levels;
- capacity, bottleneck diagnosis, internal sale, supplier choice, and auto-purchase links;
- technology levels, R&D progress, product invention, and technology transfer into quality;
- product necessity, price/quality/brand concern, overall rating, demand, and local competition;
- corporate, range, and unique brand strategies; awareness, loyalty, and decay;
- advertising links, media reach, frequency, cost, and interaction with product quality.

Exit gate: every shipped product and production method can participate in a
working economy, and isolated formula tests plus multi-year market probes meet
their documented tolerances.

### 0.7 — Corporation, finance, people, and AI

Complete the corporate layer:

- loans, repayment, interest, cash shortage, rescue behavior, and bankruptcy;
- stock prices, public trading, shareholders/investors, issue and buyback,
  dividends, tender offers, takeovers, mergers, and trading restrictions;
- balance sheet, income statement, cash flow effects, valuation, score, dominance,
  wealth, career, and Billionaires 100;
- presidents, hiring, salary expectations and raises, attitude, resignation,
  layoff, expertise, personality, concerns, policies, and delegated firms.

Implement two AI layers:

1. Presidents operating delegated firms under the original policy settings.
2. Competing corporations choosing industries, sites, layouts, prices, brands,
   technology, financing, stock actions, and expansion.

AI parity is behavioral rather than source-code parity. Each original personality
receives a probe suite covering priorities, risk, response to shortages, pricing,
expansion, R&D, and takeover behavior under fixed seeds.

Exit gate: hands-off benchmark games remain economically coherent, reproduce the
original personalities' measurable tendencies, and reach equivalent win/loss and
bankruptcy decisions under controlled setups.

### 0.8 — Complete interface, reports, content, and creation tools

- Implement instructional games, all shipped scenarios, normal-game goals,
  winning/losing, scoring, and hall of fame.
- Complete game setup, product/industry selection, competitor settings, starting
  capital, difficulty, and every scenario option.
- Implement the map editor: terrain editing, city create/delete/edit, firms and
  resource sites, starting conditions, objectives, products/industries,
  competitors, validation, and save/load.
- Implement the layout-plan library: create, name, inspect, apply, delete, and
  compatible plan persistence.
- Implement manufacturer, farmer, and manager guides.
- Implement newspaper, display options, news log, and event tracker.
- Implement every product, firm, corporate, person, financial, and goal report,
  including browsers, filters, searches, graphs, navigation, and editable controls.
- Load and resume original version-100 saves from both original builds.

Exit gate: every player-facing item in the original manual has an automated or
documented manual acceptance test and every shipped scenario/tutorial can be completed.

### 0.9 — Multiplayer and parity beta

- Implement host/join lobby and cross-platform multiplayer over a modern encrypted
  transport; preserve the original player count and game rules.
- Use deterministic command synchronization, periodic state hashes, desync dumps,
  reconnect, pause, speed voting/authority rules, and headless-server support.
- Reproduce the original auto mode used when a participant is temporarily absent.
- Finish original-save export, configuration migration, hall-of-fame persistence,
  music order/looping, sound triggers, animation timing, and all display modes.
- Run long-duration soak tests, save/load at every game state, network fault tests,
  performance profiling, controller/input edge cases, and accessibility review.
- Freeze the Classic ruleset and data schemas except for parity fixes.

Exit gate: feature-complete beta with no known data-loss defect, deterministic
multiplayer across supported operating systems, and zero missing manual features.

### 1.0 — Certified classic replacement

The 1.0 release gate requires all of the following:

- Every shipped tutorial, scenario, map, game set, layout plan, and version-100
  save used by the test corpus loads successfully.
- Every firm, unit, product, report, editor action, stock action, personnel action,
  goal, and game mode has a passing parity test.
- Ten-year fixed-seed simulation runs are deterministic across Windows, Linux,
  and macOS and contain no unexplained state divergence.
- Single-player AI, delegated presidents, and multiplayer all survive soak tests.
- Save/load is transaction-safe and never modifies original installation files.
- Classic mode starts with original rules, content, limits, timing choices, and
  numeric compatibility tolerances documented.
- The binary packages include licenses and source correspondence but no original assets.
- A clean machine can install, locate user-owned data, configure audio/video, and
  begin a game without a command line.

## Original feature inventory tracked to 1.0

| Domain | Required surface |
|---|---|
| Start and progression | Instructional games, normal game, scenarios, load/save, multiplayer, auto mode, win/loss, goals, score, hall of fame, quit. |
| World | Regional/detailed maps, modes, filters, display modes, towns, local competitors, resource sites, firm placement, map editor. |
| Firm construction | Build/demolish, site rules, naming, nine-slot layouts, functional units, links, training/equipment, experience, auto purchase, internal sale, summaries. |
| Production | All firm and unit types, raw materials, crops, livestock, recipes, inventory, quality, capacity, bottlenecks, technology, R&D, new products. |
| Market | Consumer demand, necessity, price, quality, brand concern, ratings, awareness, loyalty, brand strategies, advertising, media firms, local competition. |
| Stock and finance | Public trading, holders/investors, issue/buyback, dividends, tender, takeover, merger, regulation, loans, interest, bankruptcy, accounting. |
| Personnel | Presidents, salary/raises, attitude, resignation/layoff, delegation, policies, expertise, personality, concerns. |
| Information | Manufacturer/farmer/manager guides, plan library, newspaper, news log, tracker, all product/firm/corporate/person/financial/goal reports and graphs. |
| Presentation | Original palettes, sprites, fonts, animations, cursor, sound effects, music, display timing, shortcuts, numerical formatting. |
| Persistence | Configuration, saves, scenarios, maps, layout plans, hall of fame, original-data validation, safe error reporting. |

This inventory is a release checklist. A feature is not complete merely because
its screen exists; its simulation, persistence, AI use, reporting, sound/event
hooks, and multiplayer behavior must also work.

## Parity test strategy

### Controlled probes

Each unknown formula receives a minimal experiment: one variable changes, the
game advances a fixed number of days, and before/after saves plus visible reports
are captured. Examples include a one-point price change, one training purchase,
one extra advertising link, one share issue, or one president-policy change.

### Differential state comparison

`capplus-inspect` aligns original save sections and masks only fields proven to be
transient. The replacement simulation exports a canonical state snapshot using
the same identifiers. Tests compare decisions and integer state exactly and
float state in ULPs or domain-specific error bounds.

### Scenario replays

Recorded command streams are replayed in the DOS original, Windows original, and
Cap++. Checkpoints cover daily, monthly, yearly, goal, bankruptcy, takeover,
and save/reload boundaries. Multiplayer uses the same command stream on multiple
operating systems and verifies state hashes.

### No proprietary public fixtures

Continuous integration uses synthetic data. A local owner-data suite records only
hashes and pass/fail summaries in public artifacts. Contributors never commit
original assets, saves, manual pages, or decompiler output.

## Expansion boundary after parity

The engine should be extensible from the start, but major new gameplay remains
disabled until the Classic profile passes its 1.0 gate. This prevents improvements
from hiding compatibility errors.

After 1.0, an **Extended profile** can add:

- open JSON/TOML definitions for products, recipes, firms, units, people, maps,
  scenarios, goals, and balance parameters;
- package manifests, dependencies, load order, content IDs, and save-safe mod hashes;
- larger maps and higher firm, product, competitor, and town limits;
- new industries, service products, media, logistics, finance, and market systems;
- alternate AI modules and difficulty models;
- optional scripting in a sandboxed, deterministic runtime;
- improved graphs, search, tooltips, automation, alerts, accessibility, localization,
  and scalable modern UI layouts;
- dedicated servers, spectators, replays, and asynchronous/long-running games;
- fully original free-content packs that allow play without proprietary assets.

Extended saves must declare their ruleset and enabled packages. Classic saves
remain isolated so loading a mod cannot silently change a parity game.

## Effort and project reality

Complete parity is likely an 8,000–16,000-hour engineering and QA project, with
the largest uncertainty in economic formulas, AI, and original-save writing.
A focused team of two to four experienced contributors could plausibly reach 1.0
in several years; a solo spare-time effort should expect longer. The milestone
gates make partial releases useful even if full parity takes substantial time.

The immediate path is therefore: finish the data specification, build a headless
deterministic vertical slice, and refuse to call anything 1.0 until the full
feature and parity matrices are green.
