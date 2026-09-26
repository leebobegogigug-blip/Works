# Terminal–1 — guide

opencode multi-instance dashboard for Windows Terminal, with **TOKEN QUEST (TQ–1)**, a pet that lives on your opencode tokens.

```
[ 00 overview ][ 01 api-server :4096 ][ 02 web-front :4097 ][ 03 db-migrate :4098 ][ + ]
```

Every `terminal-1 add` opens a new tab — a numbered **channel** — in the same `terminal-1` window.
Every pane speaks the same design language. Press `?` in any pane (`F1` in compose) and it labels itself.

Screenshots: [channel tab](images/channel-tab.png) · [overview tab](images/overview-tab.png) ·
[TOKEN QUEST gallery](images/token-quest-gallery.png) · [TOKEN QUEST motion](images/token-quest-motion.png) ·
[demo GIF](images/token-quest-demo.gif) · [guide](images/guide.png) · [main story](images/story.png) — Korean manual: [MANUAL](MANUAL.md) · product page: [README](../README.md) · system: [works](../../README.md)

---

## 01 install

1. clone the repository (or copy the folder), e.g. to `D:\OPENCODE` (the program folder is then `D:\OPENCODE\terminal-1`) — the program is these 8 files
   (`docs/` and `tests/` are optional):
   `terminal-1.ps1` `terminal-1.cmd` `t1_monitor.py` `t1_term.py` `t1_pet.py` `t1_pet_data.py` `t1_pet_ui.py` `t1_pet_run.py`
2. add the program folder to `PATH`
3. needs: Windows Terminal (`wt`), Python 3.8+ (standard library only), opencode.
   Terminal–1 uses `py -3` if it exists, otherwise `python` (override: `-Python`).
4. after the first `terminal-1 add` (or after updating), close **all** Windows Terminal windows once so the `Terminal-1 Black` colors load.

## 02 commands

| command | does |
|---|---|
| `terminal-1 add` | current folder → new channel (free port from 4096) |
| `terminal-1 add C:\work\web -Name web` | another project |
| `terminal-1 add C:\work\api -Headless` | hidden `opencode serve` + attached TUI (server survives closing the tab) |
| `terminal-1 add -PetName 코코` | name the new pet egg (default 토큰이) |
| `terminal-1 overview` | reopen channel 00 (opens automatically on the first add) |
| `terminal-1 ls` | channel table with state LEDs |
| `terminal-1 focus api` | reopen a closed channel on the same port |
| `terminal-1 rm api` | unregister (stops a headless server; the pet's save stays) |
| `terminal-1 prune` | drop offline channels |
| `terminal-1 setup` | install the `Terminal-1 Black` color scheme |
| `terminal-1 version` | print the version (`VERSION` in `t1_term.py`) |

```
PS> terminal-1 ls
 CH  NAME               PORT   MODE      STATE      DIR
 01  api-server         4096   tui       ● online   C:\work\api-server
 02  web-front          4097   tui       ● online   C:\work\web-front
 03  db-migrate         4098   headless  ○ offline  C:\work\db-migrate
```

Channel numbers are given once and never change (a removed channel's number is reused by the next `add`).
Options: `-Port` `-BasePort` `-NoOverview` `-Python "py -3"` · layout: `-RightWidth 0.5` `-BottomHeight 0.42`
`-GameWidth 0.58` `-ComposeHeight 0.30` `-Compact` (no bottom row) `-NoPet` (monitor only, usage fills the bottom row) `-NoLogs` `-NoCompose`

**Coming from `ocmux`:** the tool was renamed. After `git pull`, run `D:\OPENCODE\terminal-1\terminal-1.cmd setup` once — it moves
`%LOCALAPPDATA%\ocmux` (registry, pets, raids, headless logs) to `%LOCALAPPDATA%\terminal-1`, points the user PATH at the new folder,
and swaps the `ocmux Black` scheme for `Terminal-1 Black`. While an old ocmux window is still open it keeps using the old folder and
moves it on a later run.

## 03 layout

```
 channel 01 — api-server :4096                      channel 00 — overview
┌──────────────────┬──────────────────────────┐     ┌─────────────────────────────────────┐
│ ① opencode TUI   │ ② status                 │     │ ⑥ overview                          │
│                  │   01 TOKENS  02 SESSIONS │     │   01 TOKENS  02 INSTANCES           │
│                  │   03 EVENTS  04 LOGS     │     │   03 ACTIVE WORK  04 EVENTS 05 LOGS │
├──────────────────┼───────────┬──────────────┤     ├──────────────────┬──────────────────┤
│ ③ compose        │ ④ usage   │ ⑤ TOKEN QUEST│     │ ⑦ usage + mixer  │ ⑧ pet ranch      │
└──────────────────┴───────────┴──────────────┘     └──────────────────┴──────────────────┘
```

| | pane | what it shows |
|---|---|---|
| ① | opencode TUI | opencode itself |
| ② | status | 4 token readouts · session tree · events · logs · pet badge |
| ③ | compose | big input box → opencode (focus starts here) |
| ④ | usage | tokens/min readout + 10 s bar chart |
| ⑤ | TOKEN QUEST | the pet (see 07) |
| ⑥ | overview | every channel: totals · table · active work · events · WARN+ logs |
| ⑦ | usage (all) | chart + **mixer**: one level strip per channel |
| ⑧ | ranch | every pet + this week's raid |

---

## 04 design rules

Terminal–1 follows the works design spec. The seven principles, the palette and the icon table live in one place,
[docs/DESIGN.md](../../docs/DESIGN.md) (Korean — the single source; principle names below are quoted from it).
This section only says where each principle shows up in Terminal–1.
The screen grammar is inspired by small hardware instruments (synths, samplers, pocket recorders); no product's screens
or logos are copied, and there is no affiliation with any maker.

| # | principle | where you see it |
|---|---|---|
| 1 | **한 화면 = 한 모드** (one screen = one mode, 4 big values) | pet: 4 needs · status/overview: 4 token readouts (IN OUT CACHE COST) · usage: tokens/min |
| 2 | **색 = 조작** (color = control — a value drawn in a key's color is changed by that key) | pet: `F`①포만 `P`②기분 `Z`③체력 `M`④건강 · compose: `^P`① `^S`② `^R`③ `^L`④ · tokens: ①IN ②OUT ③CACHE ④COST |
| 3 | **번호 붙은 구역** (numbered parts — every region has a number; `?` shows callouts + legend) | every pane (`F1` in compose) |
| 4 | **엔지니어링을 숨기지 않기** (nothing hidden — real system state, small) | status: `rtt` `poll` `ev` · overview: `sse` `rtt` · pet: Dex → Settings → `02 SYS` (save age, fps) |
| 5 | **즉각 반응** (instant feedback — keys light up, regions blink when something happens) | pressed keycap turns lime · `●` LED next to LOG/EVENTS/SESSIONS · compose border flashes the key's color · REC LED |
| 6 | **사각 격자** (square grid — square corners, 1-cell gaps, leading zeros, small units) | spec tables (Dex → Profile, token readouts) · `01` channels · `0145` tape counter |
| 7 | **캐릭터** (one character per app) | the TQ–1 pet in every channel · the ranch in `00 overview` |

### 04.1 colors

Navy · lime · gray on pure black, and no red: warnings are the brightest white. Navy is the primary color (number badges,
pane labels, bars); lime only means *on / busy / selected*. Values are in [DESIGN.md › 02](../../docs/DESIGN.md#02-색).
The four encoder colors map to: ① IN · 포만 `F` · `^P` put — ② OUT · 기분 `P` · `^S` send — ③ CACHE · 체력 `Z` · `^R` restore — ④ COST · 건강 `M` · `^L` clear.

### 04.2 icons

Status symbols come only from `ICON` in `t1_term.py`, which follows the icon table in [DESIGN.md › 03](../../docs/DESIGN.md#03-아이콘).
Every one of them is one cell wide in GNU Unifont.

### 04.3 widgets

| widget | looks like | used for |
|---|---|---|
| top bar | navy full-width line | channel chip · name · `sys` strip · LEDs · clock · `?` |
| module | `01 ROOM ●` | numbered region + activity LED (the number badge is navy) |
| chip | ` BUSY ` ` PERM ` ` CALL ` · ` USAGE ` ` COMPOSE ` | state (lime = on, white = warning, dark = off) · pane labels are navy |
| fader | `━━━━●────` | needs, EXP, timers — slides to the new value |
| LED bar | `▮▮▮▮▯▯` | HP/MP, quest, floors, raid HP |
| knob | `○◔◑◕●` | care, discipline, forge rate |
| segment digits | 3-row LCD numbers, unlit segments faint | level, hatch %, forge `+7 › +8`, raid round, tokens/min, readouts |
| spec cells | navy cells with 1-cell black gaps | stat tables, token readouts |
| keycap | dark cap (plain) · colored cap (encoder) · lime (just pressed) | bottom key line, menus |

### 04.4 guide (`?`)

```
┌ 01 ROOM2──────────────┐┌ 02 LEVEL3┐        numbered markers sit right after each region's title
│                       ││          │
└───────────────────────┘└──────────┘
 ● 포만 ━━━━●── 64 4 ● 기분 ━━━━━●─ 88
 GUIDE  1 MODES  2 ROOM  3 LEVEL  4 NEEDS …        ← legend strip (names)
 3 LEVEL  level · EXP · HP/MP · care/discipline …   ← selected item
```

`?` opens · `1`–`9` or `←` `→` pick an item · any other key closes. Nothing else changes while it is open.

### 04.5 motion

boot (dot grid → segment wordmark → lime sweep; 1.6 s for the pet, 0.8 s for monitors; any key skips) ·
lime wipe on mode change · tape reels while the AI works / tokens flow · room level meter · mixer strips ·
fader glide · rolling gold counter · keycap light · expanding frames on evolution · gauge → segment digits at the forge ·
segment count-in and lit pads in bug-whack · typewriter text in story talks (only the speaker is lit; `Enter` completes the line).

---

## 05 status ②

```
 01 api-server :4096 v1.4.2        rtt 12ms · poll 2s · ev 431   ● ONLINE SSE 15:03:12 ?
 ── 01 TOKENS ──────────────────────────────────────────────────── SESS 5
 ● IN 110.6k    ● OUT 7.3k    ● CACHE 37.9k    ● COST $0.12        ← ①②③④
 ── 02 SESSIONS ● ────────────────────────────────────────── ACTIVE 2
  PERM  결제 API 리팩터링 1pay01        build   48.2k  3.1k …
        ‼ 허락 대기 bash pytest tests/payment -q · opencode 창에서 응답
        QUEST 2/4 ▮▮▯▯ 지금 호출부 어댑터 주입
        ◐ edit src/payment/gateway.py
 ── 03 EVENTS ● ──   ── 04 LOGS ● ──
```

- chips: `BUSY` lime · `RTRY` white · `PERM` / `ASK` blink = opencode waits for you
- `i` shows/hides idle subagent sessions
- logs: level chip `ERR` `WRN` `INF` `DBG` + time + `key=value` (keys dim, values bright)

## 06 overview ⑥ · usage ④⑦ · compose ③ · logs

- **overview**: `01 TOKENS` (all channels) · `02 INSTANCES` (channel chip, port, mode, sessions, busy, agents, tokens, pet) ·
  `03 ACTIVE WORK` (`[2/4]` todo progress, `PERM`) · `04 EVENTS` · `05 LOGS` (WARN+)
- **usage**: big tokens/min readout · `01 TOKENS` chart (①IN blue, ②OUT green) · in the overview tab `02 MIX`:
  one strip per channel in its tab color, LED on top = working · tape reels spin while tokens flow
- **compose**: `REC` blinks while there is unsent text · tape counters `CHR 00145` `LN 006` `SENT 02` ·
  `Ctrl+V`/`Insert` paste · `Enter` new line · `^S` send · `^P` put only · `^R` restore · `^L` clear · `F1` guide ·
  the box border flashes the color of the key you pressed · your pet reacts to what you send
- **logs** (`t1_monitor.py logs`): the same log formatting as the LOGS regions

---

## 07 TOKEN QUEST ⑤

A tamagotchi that grows into an RPG hero. It eats your opencode tokens, goes on dungeon runs while the AI works,
and comes home with loot when the response arrives. One pet per channel.

### 07.1 modes (`1`–`7` or `Tab`)

| mode | regions | keys |
|---|---|---|
| 1 홈 | 01 ROOM · 02 LEVEL · needs ①②③④ · status line · QUEST · 03 LOG | `F`① feed · `P`② play · `Z`③ sleep · `M`④ medicine · `C` clean · `J` pat · `G` discipline |
| 2 모험 | 01 DUNGEON · 02 INFO / RAID · 03 MAP · AUTO — in battle: floor sequencer · 01 FIELD · HP · 02 LOG | `↑↓` `Enter` `B` `W` raid `X` auto · battle `A` `S` `D` `I` `R` `T` · events `1` `2` |
| 3 가방 | pages · 01 EQUIP (+ spec cells) · 02 SPARE / 01 ITEMS … | `←→` `Enter` `U` |
| 4 상점 | pages · GOLD · 01 BUY / SELL | `←→` `↑↓` `Enter` |
| 5 공방 | pages · MATS · 01 GEAR / RECIPES · 02 ENHANCE (`+7 › +8`) | `Enter` · `P` rubber-duck protection |
| 6 도감 | profile (01 SPEC · 02 RECORD) · quests · diary · monsters · forms · hall of fame · achievements · settings (01 SETTINGS · 02 SYS) | `←→` `↑↓` `Enter` · `R` retire |
| 7 스토리 | season header · 01 CHAPTER · 02 SHARDS · 03 MISSIONS · 04 NEXT · 05 LOG — talk: place caption · stage · dialogue box — boss: `CHxx BOSS` · FIELD · HP · LOG | `←→` chapter · `Enter` talk · `B` chapter boss · talk: `Enter` next, `Esc` skip |

`?` guide everywhere. Pages show as dots `●●○○` next to the page switch.
Korean keyboard mode works (ㄹ = F, ㅁ = A …, syllables like 러 = F); a one-time hint suggests 한/영.
Pasting into the pet pane is ignored.

### 07.2 care
- needs: **fullness ①, mood ②, energy ③, health ④** + **bugs** in the room (clean → *bug shells*). Below 20 the number blinks white.
- **calls** ("배고파!" …): answer within 25 min → care up; ignore → care mistake.
- **tantrums**: screaming although every need is fine → `G` discipline. Giving in spoils it; scolding for nothing makes it sad.
- sickness: cold (medicine), overfed, **burnout** at 0 health (vacation coupon or long rest). No cure available → no call.
- sleep `Z`; it dozes off late at night. **Away** 45 min → slow drain, no calls; 8 h → hibernation.

### 07.3 growth
`egg → bit → byte → teen → adult → legend` — adult form follows how you raised it (battles → *10x Dev*, cleaning →
*Bug Hunter*, plan time → *Senior Architect*, neglect → *Overtime Zombie*, minigames → *Code Monk*, balanced → *Full-stack Druid*),
plus personality (7 kinds) and discipline. Legend *Singularity*: Lv.35 + Cloud boss + care ≥ 75 + 5 days. One secret legend.

### 07.4 generations
Adult Lv.25 + 3 days (or any legend) → **retire** (Dex → Profile → `R`) → Hall of Fame + epitaph → new egg (`토큰이 2세`).
Kept: gold, bag, decorations, achievements, dexes, streak. **Family bonus**: +5% EXP / +3% gold per ancestor (max 10).

### 07.5 adventure · raid · minigames
- 12 zones × 10 floors, mini-boss B5F, boss B10F, 78 monsters + 12 chapter bosses, choice events, level skills,
  gear +10 enhancing, room decorations. Zone *n* opens together with story chapter *n* (07.6).
- auto-expeditions only try a boss near its level (waits two levels after a loss).
- **weekly raid**: all pets of all channels hit one boss (HP 6,000 + 350 × level each), 3 sorties/day, 12 rounds, rewards + MVP.
- minigames (`P`): direction guess · bug whack (numpad pads) · typing · dev quiz O/X (5/5 → INT +1).

### 07.6 main story — season 1 「초록불을 찾아서」 (THE LAST GREEN BUILD)

One Monday morning every build in the world turns red. The last green build has shattered into twelve commit shards;
the pet, a senior owl, a rubber duck and a CI bot go and collect them. Made for heavy users: it is paced in weeks, not hours.

- **12 chapters = 12 zones.** A chapter is: prologue talk → 3 required missions (+1 bonus ☼) → chapter boss (talk + fight)
  → epilogue, commit shard `#n` with its hash, gold, gear and EXP (half a level; a full level for the last chapter).
- **missions** fill up from normal work: clear the zone boss · defeat N monsters in that zone · finish opencode todos ·
  answer permissions within a minute · minigames · crafting / enhancing … Progress counts from the chapter's start.
- **schedule**: chapters 1–4 open as fast as you play them; after that one chapter opens every **7 days** from the story's
  start date. Released chapters pile up, so a week off never locks you out — you just have more to catch up on.
  The next release date is shown under `04 NEXT` (and on locked zones in 2 모험).
- **chapter boss** (`B` when the missions are done): needs HP ≥ 50%, energy ≥ 15, fullness ≥ 10 and no expedition;
  a fight costs 10 energy and 4 fullness. Losing has no faint penalty (no gold or loot lost) — the pet is left at 10% HP
  and can retry once it is back to 50%. Retreating (`R`) is free. The final boss has a second phase.
- **news LED**: a new chapter, a ready boss or a waiting epilogue lights the LED next to `7스토리`, shows a `STORY` chip at home,
  and the ranch cards show each pet's chapter and mission count.
- **achievements**: CH3, CH6, CH9, the season finale and 6 bonus missions (four of them also give a title).
- **playtime**: about 9–10 weeks to the finale at 10 h per weekday. Simulated with 0.25M–25M tokens per day:
  day 60–71, around Lv.100 at the end.
- **token EXP taper**: per day, the first 2M tokens give full EXP, up to 10M give 25%, beyond that 5% — heavy days no longer
  outrun the story. Food from tokens is unchanged.
- **older saves** (v3 → v4) migrate on load: chapters up to your cleared zones + 1 (at least 4) open at once, and missions
  count from the update. Story progress lives in the save, not the pet, so it survives retirement.
- tuning: `STORY` (`fast` = chapters open at once, `every` = days per chapter) and `CHAPTERS` in `t1_pet_data.py`.

### 07.7 wiring to opencode

| opencode | in the game |
|---|---|
| tokens | food (≤ 60 fullness), EXP (1,000 tokens = 1, tapering above 2M tokens a day — 07.6), MP; input tokens raise INT |
| root session BUSY | auto-expedition; at home the pet types on a laptop, the room meter moves |
| idle (response arrived) | quest reward, "☼ response" banner, expedition returns with loot |
| `todo.updated` | **main quest** (QUEST line), rewards per item + list bonus |
| permission / question | "결재 부탁!" sign, `‼결재` in the top bar, optional bell (WT tab 🔔); fast answer → bonus |
| subagents | allies join fights and leave gifts |
| tool calls | crafting shards · tool error → a bug |
| `session.error` | bugs, mood drop, a **boss** (429 dragon for rate limits) |
| Esc (aborted) | reaction only |
| `session.compacted` | "꺼억~" (+fullness) |
| slash command · retry · agent | small EXP · anxious · attack/strategy stance |
| compose send | reaction + 10 min "inspired" buff |

### 07.8 save files
- `%LOCALAPPDATA%\terminal-1\pet-<name>.json` · `.live.json` (for other panes) · `bus-<name>.jsonl` · `raid-<name>.json`
  (`<name>` = the channel's instance name, e.g. `pet-api-server.json`). Save format v4 (adds `story`); older saves migrate on load
- one pane cares for a pet; a second pane is a **spectator** (`O` takes over; `O` twice within 5 s takes it from a live pane)
- closing with ✕ saves (unfinished expedition loot is banked; mid-battle −30% carried gold); killed processes recover loot next start
- a broken save is kept as `pet-<name>.corrupt-<time>.json`; a newer version's save opens read-only

---

## 08 files

- registry `%LOCALAPPDATA%\terminal-1\instances.json` (name, port, color, **ch**)
- headless logs `%LOCALAPPDATA%\terminal-1\logs\<name>.log`
- TUI logs: the first file created in `%USERPROFILE%\.local\share\opencode\log` after the tab opened
  (opened only while reading, so opencode can delete them)
- color scheme fragment `%LOCALAPPDATA%\Microsoft\Windows Terminal\Fragments\terminal-1\terminal-1.json` (only Terminal–1 tabs use it)
- old blue/pink tab colors and channel-less registries are migrated automatically

## 09 notes

- **paste**: new WT installs bind `Ctrl+V` to WT's own paste, which "types" the text and can drop characters (… — “ ” •).
  compose detects that and inserts the clipboard itself. `Insert` always pastes directly. Multi-line warning:
  `"multiLinePasteWarning": false`. If `Ctrl+V` does nothing inside opencode, add `{ "command": "paste", "keys": "ctrl+v" }`.
- **WT keys**: `Alt+Arrow` pane · `Alt+Shift+Arrow` resize · `Ctrl+Tab` tab · `Ctrl+Shift+W` close pane ·
  bind `togglePaneZoom` to blow a pane up to full size.
- **fonts**: recommended font is **GNU Unifont 15.1.01** (8×16 bitmap; set face `Unifont`, size 12 at 100% scaling,
  `"antialiasingMode": "aliased"`). It covers every glyph Terminal–1 draws, and all screenshots use it. Every icon Terminal–1
  draws is one cell wide in Unifont (`√ ‼ ⊠ ☼ ⋆ ◈` instead of `✓ ⚠ ☑ ★ ☆ ✦`, which Unifont draws two cells wide).
  With other fonts some symbols (`▮` `◔`) may come from a fallback font.

## 10 development

- tests (standard library `unittest`, 122 tests — game engine, opencode signal bridge, save/raid edge cases, main story, token taper,
  monitor polling/password/compose privacy, and `terminal-1.ps1` run end-to-end with a fake `wt` when `pwsh` is available on Linux/macOS):
  `py -3 -m unittest discover -s tests` · CI runs Windows + Ubuntu × Python 3.8/3.13 and parses `terminal-1.ps1` with Windows PowerShell 5.1
- works rules check (repo root): `python tools/works_check.py` — see [RULES.md](../../RULES.md)
- one-frame snapshot of any pane, for screenshots or checks without a live terminal:
  `py -3 t1_monitor.py rpg --name demo --once 1 --cols 80 --rows 24` (add `--guide` to show the `?` guide)
- `t1_monitor.py` modes: `status` `overview` `logs` `usage` `rpg` `compose` — `py -3 t1_monitor.py -h` lists every flag
