# Flow–1 화면 가공 가이드 — 사내 LLM 용

이 문서는 Flow–1 의 **화면**(`ui.html` · 흐름도 SVG)을 고치는 LLM(opencode 등)이 읽는다. 먼저 [flow-1/AGENTS.md](../AGENTS.md) 를 읽었다고 본다.
works 공통 디자인(원칙 일곱 가지 · 팔레트 · 아이콘 · 글자)은 [docs/DESIGN.md](../../docs/DESIGN.md), Flow–1 의 치수 · 색 자리는 [GUIDE › 07 화면 규격](GUIDE.md#07-화면-규격)이 정본이다.
이 문서는 **고치는 법** — 어디를 · 무엇으로 · 어떻게 확인하는지 — 만 적는다. 색 **값**은 적지 않는다.

> **원칙 넷**
> 1. **새로 만들지 말고 있는 부품을 쓴다.** 칩 · 버튼 · 줄 · 서랍이 이미 있다 → [02](#02-부품--새로-만들지-말고-가져다-쓴다)
> 2. **색은 토큰으로만.** `var(--…)`. 새 hex 는 테스트가 막는다 → [03](#03-색)
> 3. **흐름도는 서버가 그린다.** 카드 · 알약 · 선의 모양은 `ui.html` 이 아니라 `flow1_graph.py` → [07](#07-흐름도-svg-고치기)
> 4. **한 번에 하나 고치고, 다크 · 라이트 · 좁은 창을 사진으로 본다** → [09](#09-확인)

---

## 00 어디를 고치나

| 바꾸려는 것 | 고칠 곳 | 확인 |
|---|---|---|
| 문구 (버튼 · 안내 · 빈 화면 · 알림) | `ui.html` 의 HTML, 또는 JS 의 글 (`el(…, "글")` · `toast("글")` · `.hello` 의 `innerHTML = "고정 문구"`) | 사진 · MANUAL 화면 절 |
| 색 | `ui.html` 의 토큰 블록 세 곳 (+ 흐름도 색이면 `flow1_graph.THEMES`) — [08 R2](#r2-색-하나-바꾸기--새-토큰) | 테스트 · 사진 |
| 크기 · 간격 · 배치 | `ui.html` 의 `<style>` 에서 그 부품의 규칙 | 사진 1440 · 500 |
| 구역 · 버튼 · 노브 값 · LED 더하기 | `ui.html` 의 HTML + `<script>` — [08](#08-레시피) | 테스트 · 사진 · 손으로 |
| 흐름도 카드 · 알약 · 선의 모양 | `flow1_graph.py › 06 SVG` (`SVG_CSS` · `_node_svg` · `_row_svg`) | `tests/test_graph.py` · `--svg` · 사진 |
| 카드에 보이는 줄 (상세 1 · 2 · 3) | `flow1_graph.py › 02 카드 줄` (`query_rows` · `select_rows`) | `tests/test_graph.py` · 골든 |
| 흐름도 배치 · 간격 | `flow1_graph.py › 01 치수` · `05 배치` | `test_grid_and_no_overlap` · `test_big_graph_is_fast` |
| 02 자세히에 보이는 것 | 서버 `App.detail` (`flow-1.py`) + 화면 `renderDetail` (`ui.html`) | `tests/test_app.py` › `Http` · 사진 |
| 키 | `ui.html` 끝의 `keydown` 처리 | MANUAL 키 줄 · README 사양 표 |
| 회사 이름 | **코드가 아니다** — `python flow-1.py --set "company=이름"` (로고 옆 `#brand`) | 창 |
| 유량계 표정 | `ui.html` 의 `.mascot` CSS + `mascot()` · `restMood()` | 사진 · 손으로 |

`ui.html` 을 고친 다음에는 **늘** `python build.py` 를 돌린다. 서버는 `ui.html` 이 아니라 `flow1_assets.py` 에 묶인 사본을 보여 준다 — 안 돌리면 고친 것이 창에 안 보인다.

---

## 01 화면 지도

```text
<html data-theme="__THEME__">                        서버가 dark · light · system 을 넣는다
<meta name="flow-token" content="__TOKEN__">         API 토큰 (지우지 않는다)
.device                                              본체 — 둥근 18 · 나사 넷 .screw.s1–s4
├─ .bar                                              윗줄
│  ├─ #mascot.mascot                                 유량계 (class: empty · idle · scan · run · happy · error)
│  ├─ .logo · #brand                                 FLOW–1 · 회사 이름 (설정 company, 비면 숨김)
│  ├─ .lcd › #lcd-file · #lcd-meta                   지금 파일(① 노브 색) · 파일 · 쿼리 수
│  ├─ .leds › #led-watch · #led-run                  LED (class: ok · err · busy)
│  └─ #power.power                                   끄기
├─ .main                                             세 칸 248 · 나머지 · 392
│  ├─ #p-files.pane    01 FILES   #path-form(#path-in · #path-pin) · #files · #ex-path · #explorer
│  ├─ #p-flow.pane     00 FLOW    #stats · #find · .knobvals(#v1–#v4) · #canvas › #svgwrap(SVG) · #flow-hello · #runbar
│  └─ #p-detail.pane   02 QUERY   #d-name · #d-sub · #copy-sql · #detail
├─ .deck               03 DECK    .knob.k1–k4 (값 #kl1–#kl4) · .acts › #rescan · #save-svg · #runs-btn
└─ .foot                          #hint · #watchinfo · #ver
떠 있는 것: .toast (알림) · .drawer (04 RUNS 서랍) · .off-screen (끈 뒤)
```

`<script>` 의 순서와 이름:

| 이름 | 하는 일 |
|---|---|
| `BOOT` · `TOKEN` | 서버가 넣은 값 (버전 · 회사 이름 · 폴링 초 · 예시 폴더) · API 토큰 |
| `$` · `el(태그, class, 글)` · `fmt` · `fmtMs` | 찾기 · 요소 만들기(글은 `textContent`) · 천 단위 쉼표 · 시간 |
| `S` | 화면 상태 하나 (지금 파일 `key` · 상세 · 확대 · 강조 · 고른 노드 · 찾기 · 실행) |
| `KNOBS` | 노브 넷의 값 목록 · 지금 값 · 이름 |
| `api(경로, 본문)` | 모든 서버 요청 (토큰 헤더를 붙인다 — `fetch` 를 따로 쓰지 않는다) |
| `applyState` · `poll` | `/api/state` 를 받아 LED · LCD · 파일 목록을 그린다 · 2초마다 (실행 중 1초) |
| `renderKnobs` · `turn` | 노브 눈금 · 값 칩 · LCD · 노브 돌리기 |
| `renderFiles` · `renderExplorer` · `exGo` | 01 FILES 의 감시 목록 · 탐색기 |
| `loadGraph` · `applyZoom` · `applyFocus` · `applyFind` · `highlight` · `select` | 00 FLOW 의 SVG 붙이기 · 확대 · 강조 · 찾기 · 올림 · 누름 |
| `renderDetail` · `dl` · `refBtn` · `paintRow` | 02 자세히 |
| `openRuns` · `closeDrawer` | 04 RUNS 서랍 |
| `toast` · `mascot` · `led` | 알림 · 유량계 · LED |
| 끝의 `keydown` | 키 (아래 04) |

구역 번호: `00 FLOW` · `01 FILES` · `02 QUERY` · `03 DECK` · `04 RUNS`. 새 구역은 **05** 부터. 있는 번호는 다시 매기지 않는다 (문서 · 사진 · 사람의 기억이 번호로 부른다).

---

## 02 부품 — 새로 만들지 말고 가져다 쓴다

| 부품 | 모양 | 언제 |
|---|---|---|
| 구역 | `<section class="pane"><div class="pane-h"><span class="num">05</span><span class="name">NAME</span><span>한국어 설명</span></div><div class="pane-b">…</div></section>` | 늘 보이는 칸. 이름은 영문 대문자 한 낱말 |
| 번호 배지 | `<span class="num">05</span>` | 구역 · 덱의 두 자리 번호 |
| 칩 | `.chip.navy` · `.chip.lime` · `.chip.err` · `.chip.out` | 이름표(`Q01` · `TABLE`) · **지금 · 켜짐만** · 경고 `ERR` · 수 · 통계 |
| 작은 버튼 | `<button class="ghost">` | 구역 머리 · 안내 글 안 (`SQL 복사` · `예시 폴더 보기 ›`) |
| 큰 버튼 | `<button class="btn">` · `<button class="btn key">` | 덱의 동작. 네이비 `.btn` 은 화면에 하나(가장 중요한 것), 나머지는 회색 `.btn.key` |
| 노브 | `.knob.k1` – `.k4` | **넷으로 고정** — 더하지 않는다 (원칙 2 · 인코더 네 색 순서) |
| LED | `<span class="led" id="led-…"><i></i>이름</span>` + `led("#led-…", "ok" \| "err" \| "busy" \| "")` | 윗줄의 상태 불 |
| 목록 줄 | `.file` (감시) · `.ex` (탐색기) · `.row` (서랍) | 한 줄 20 · 왼쪽 아이콘 칸 16 |
| 이름–값 줄 | `dl(box, "이름", 값, "jn"?)` | 02 자세히 — 이름 칸 64 |
| 소제목 · 메타 | `el("div", "d-sec", "…")` · `el("div", "d-meta", "…")` | 02 자세히의 절 · 흐린 한 줄 |
| 이동 버튼 | `refBtn(노드 id, "Q01 df")` | 누르면 그 카드로 |
| 안내 글 | `el("div", "hello")` | 빈 화면 · 처음 쓰는 사람에게 |
| 알림 | `toast("…")` | 3초 한 줄. `alert` · `confirm` 대신 |
| 서랍 | `openRuns` 의 `.drawer` 모양 | 잠깐 열어 고르는 목록 (`Esc` 로 닫힘) |
| 경고 줄 · 닫기 | `el("div", "warn", "! …")` · `<button class="x">×</button>` | 파일 아래 경고 · 목록에서 빼기 |
| 막대 | `.hist` 안의 `<i>` | 실행 시간 막대 (라임 = 지금 · 흰 = 실패) |

- 요소는 `el(태그, class, 글)` 로 만든다. 글은 `textContent` 로 들어가 안전하다.
- `innerHTML` 에는 **고정 문구만** (`<b>` 로 키를 굵게 하는 정도). 파일 이름 · 경로 · SQL · 오류 글 같은 **값**은 넣지 않는다 — 스크립트가 끼어든다 (`test_inner_html_only_fixed_text`).
- 새 부품이 꼭 필요하면 위 부품의 CSS 를 본떠 같은 토큰 · 같은 치수로 만든다.

---

## 03 색

팔레트와 원칙은 [DESIGN › 02 색](../../docs/DESIGN.md#02-색), Flow–1 의 토큰 목록은 [GUIDE › 7-3](GUIDE.md#7-3-색-자리-토큰). 여기는 **고를 때** 보는 표다.

| 칠하려는 것 | 쓸 토큰 |
|---|---|
| 화면 바탕 · 본체 · 구역 바탕 | `--bg` · `--panel` · `--panel-2` |
| 본문 글자 | `--ink-2` |
| 흐린 라벨 · 설명 · 단위 · 시각 | `--ink-3` |
| 제목 · 값 · 강조 · 경고 글자 | `--ink` |
| 가는 선 · 구분선 / 테두리 · 굵은 선 | `--line` / `--line-2` |
| 올렸을 때 · 지금 줄의 바탕 | `--hl` |
| 번호 배지 · 이름표 칩 | `--prime` 바탕 + `--prime-ink` 글자 |
| 주요 버튼 · 회색 버튼 | `--btn` · `--btn-ink` · `--btn-edge` / `--key` · `--key-edge` |
| 지금 · 켜짐 · 진행 · 선택 (점 · 테두리 · 막대 · 커서) | `--accent` — **글자**로 쓸 때는 `--accent-ink` (라이트에서 읽히게) |
| 라임 바탕 위 글자 | `--on-accent` |
| 경고 · 실패 | `.chip.err` (`--err` 바탕 + `--err-ink` 글자, 글은 `ERR`) — 빨강 대신 |
| 노브가 바꾸는 값 | 그 노브 색 `--kN` 바탕 + `--kN-ink` 글자 (값 칩 · LCD 파일 이름 · 지금 파일 표시) |
| 흐름도 안 | `--fbg` · `--card` · `--card-head` · `--card-edge` · `--num` · `--head-ink` · `--head-meta` · `--tbl` · `--edge` · `--bar` · `--pill` |

- 라임을 장식 · 제목 · 링크 색으로 쓰지 않는다. "지금 무엇이 켜져 있나" 에만.
- 흐리게는 `opacity` 로 한다 — 이미 쓰는 값(`.12` · `.25` · `.3` · `.45`) 중에서.
- 그림자는 본체 · 서랍 · 버튼 받침 · LCD 안쪽에만. 흐름도 안은 그림자 · 그라데이션 없음.
- JS 로 색을 넣지 않는다 (`style.color = …` 금지). class 를 붙이고 CSS 에서 토큰으로 칠한다.

---

## 04 글자 · 문구 · 키

- **글꼴은 하나**: `font: … var(--dos)` (내장 Unifont). `font-family` 를 새로 쓰지 않는다.
- **크기는 이미 쓰는 것만**: 16 (기본 · 줄 높이 24 또는 20) · 14 (작은 글 · 메타) · 20 (02 제목) · 24 (LCD) · 32 (로고). Unifont 는 16 의 정수배에서 가장 선명하다.
- **굵게**: `<b>` 또는 `text-shadow:var(--b)` (1px 옆에 한 번 더). `font-weight` 는 번진다. SVG 는 `_text(…, bold=True)`.
- **글자가 폰트에 있나**: 한글 11,172자와 ASCII 는 모두 있다. 한자 · 이모지는 없다 — 다른 글꼴로 그려져 칸이 어긋난다. 새 기호는 [DESIGN › 03 아이콘](../../docs/DESIGN.md#03-아이콘) 표의 폭 1칸 기호만 쓴다.
  확인: `python tests/ui_check.py glyphs "새 문구 ◐"` → 폰트에 없는 글자 · 폭 2칸 기호를 알려 준다.
- **말투** ([DESIGN › 06](../../docs/DESIGN.md#06-문서와-말투)): 존댓말 · 짧은 문장 · 구분은 ` · ` · 넘어가기 `›`. 구역 이름 · 칩은 영문 대문자, 설명은 한국어. 버튼은 동사(`다시 읽기` · `SVG 저장`). 안내 글 안의 키는 `<b>` 로.
- **숫자**: `fmt(n)` (천 단위 쉼표) · `fmtMs(ms)` · 번호는 두 자리 (`String(n).padStart(2, "0")` → `Q01`).
- **넘치는 글**: 한 줄 칸은 `white-space:nowrap; overflow:hidden; text-overflow:ellipsis` (끝이 `…`). 흐름도는 서버가 `clip` 으로 자른다.

키 — 지금 쓰는 것 (겹치게 만들지 않는다):

| 키 | 동작 | 키 | 동작 |
|---|---|---|---|
| `/` | 찾기 | `[` `]` | 앞 · 뒤 쿼리 |
| `+` `=` `-` `0` | 확대 · 축소 · 맞춤 | `R` | 다시 읽기 |
| `Esc` | 서랍 닫기 · 고른 것 · 찾기 풀기 | `Alt+1`–`Alt+4` (+`Shift`) | 노브 (거꾸로) |
| `Ctrl+휠` | 확대 | `Ctrl+V` · 끌어다 놓기 | 코드 붙여 넣기 |

새 키는 한 글자(입력 칸에 글을 쓰는 중이면 무시 — `typing` 검사 안쪽에 둔다). `Ctrl+…` 는 브라우저 키라 쓰지 않는다. 더하면 MANUAL 키 줄 · README 사양 표 · 버튼의 `title` 에도 적는다.

---

## 05 치수 · 배치

- 틀의 치수는 [GUIDE › 7-2](GUIDE.md#7-2-틀-px). 새 간격 · 크기는 **4 의 배수**(되도록 8).
- **둥근 모서리는 본체 18 · 구역 12 · LCD · 버튼 · 서랍 10–12 · 노브 원뿐.** 새 부품 · 흐름도 안은 각지게.
- 선은 1px (강조 2px). 점선은 `4 3` · `2 2` 두 가지.
- 세 칸 폭(248 · 392)을 바꾸면 꺾이는 폭 두 곳(`@media (max-width:1100px)` · `(max-width:760px)`)도 같이 본다.
- 좁은 창(760 이하)은 한 줄로 쌓인다. 새 부품이 가로로 넘치지 않게: flex 자식에 `min-width:0` · 글에 `text-overflow:ellipsis` · 줄에 `flex-wrap:wrap`. 좁은 창에서 숨길 것은 760 규칙에 `display:none` 으로.
- 겹침 순서(`z-index`): 나사 4 · 서랍 5 · 알림 6 · 끈 화면 9. 새로 떠 있는 것은 이 사이에 넣는다.

---

## 06 움직임

- 짧고 기계적으로: 깜빡임은 `steps(2)` · 전환 0.06–0.35초 · 한 번 튀기 `cubic-bezier(.3,1.6,.5,1)`. 1초 넘는 연출은 만들지 않는다 (유량계 흔들기 2.4초 반복만 예외).
- 이미 있는 `@keyframes` 를 쓴다: `caret` · `blink` · `sway` · `sweep` · `jitter` · `bounce` · `shake` · `rise` · `drop`.
- `prefers-reduced-motion` 이면 모든 움직임이 꺼진다 (`<style>` 끝의 한 줄). 새 움직임에 `!important` 를 붙여 이 규칙을 이기지 않는다.
- 누름 반응: 버튼 · 노브는 3px 내려간다 (`:active` · `.pressed`). 새 버튼도 `.btn` 을 쓰면 저절로 된다.

---

## 07 흐름도 SVG 고치기

- 흐름도는 **서버가 그린다**: `flow1_graph.svg(그래프, theme=…)`. 화면은 받은 SVG 를 `#svgwrap` 에 그대로 붙이고, SVG 저장 · `--svg` 도 같은 함수다.
- 모양 규칙은 `flow1_graph.SVG_CSS` **한 곳** (화면과 내려받은 SVG 가 같이 쓴다). 거기 쓰는 색은 `var(--토큰)` 만 (`test_colors_only_in_token_blocks`). 화면에서만 필요한 반응 — 올림 · 흐림 · 찾기 · 강조 — 은 `ui.html` 의 `.flow …` 규칙에.
- 화면 JS 가 기대는 SVG 이름 — 바꾸면 `ui.html` 도 같이:

  | 이름 | 누가 쓰나 |
  |---|---|
  | `.n[data-id]` · `.n-box` | 누르기 · 올림 · 찾기(`.hit`) · 고름(`.sel`) — 테두리 |
  | `.e[data-e]` · `.port[data-e]` · `.e-join` · `.e-param` | 올림 강조(`.hl`) · ④ 강조 |
  | `.r` 줄 · `.jn` · `.has-p` | ④ 강조 (JOIN 줄 · 자리가 든 줄) |
  | `.n-query` · `.n-op` · `.ran` | ④ 실행 강조 (`.ran` 은 JS 가 붙인다) |
  | `text.run-busy` + 부모의 `data-since` | 실행 중 초 세기 |

- 좌표 · 크기는 8 의 배수, 글 폭은 `cells()` (반각 8 · 전각 16) 로 잰다. 카드 줄 이름은 7칸 안 (이름 칸 64).
- 바꾼 뒤: `python flow-1.py --svg out.svg --theme light --detail 3 tests/examples/daily_sales.py` 로 SVG 한 장을 만들어 브라우저로 본다 (다크도). 그리고 `python -m unittest tests.test_graph`.

---

## 08 레시피

### R1 문구 하나 바꾸기
1. `grep -n "바꿀 글" ui.html` — HTML 이면 그 자리, JS 글이면 그 줄
2. 04 의 말투로 고친다. 영문 대문자 이름(`FLOW` · `QUERY`)은 번호와 짝이라 바꾸지 않는다
3. `python build.py` → 테스트 → 사진. 사람이 보는 문구면 MANUAL 의 그 설명도

### R2 색 하나 바꾸기 · 새 토큰
1. 03 의 표에서 **있는 토큰으로 되는지** 다시 본다 (대부분 된다)
2. 값을 바꾸면: 그 토큰을 `ui.html` 의 **세 블록**(다크 `:root` · 라이트 · 시스템의 라이트)에서 모두 찾아 바꾼다. 라이트에만 있는 토큰이면 라이트 · 시스템 두 곳. 흐름도 토큰이면 `flow1_graph.THEMES` 의 그 테마도
3. 새 토큰이면: 이름은 쓰임새로(`--run-bar` 처럼), 세 블록에 같은 이름. 값은 [DESIGN › 02](../../docs/DESIGN.md#02-색) 팔레트에 있는 값이나 무채색만
4. `python -m unittest discover -s tests` (색 테스트 셋) → `python ../tools/works_check.py` (팔레트 밖의 유채색이면 실패) → 다크 · 라이트 사진

### R3 02 자세히에 절 하나 더
1. 서버: `flow-1.py` 의 `App.detail` 이 돌려주는 dict 에 키를 더한다 (JSON 으로 옮길 수 있는 값만)
2. 테스트: `tests/test_app.py` › `Http.test_state_graph_detail` 에 그 키를 보는 줄
3. 화면: `renderDetail` 에서 `box.appendChild(el("div", "d-sec", "제목"))` → `dl(box, "이름", 값)` 줄들
4. `python build.py` → 테스트 → 카드를 눌러 본 사진 (Playwright 가 없으면 `python flow-1.py` 로 손으로)

### R4 덱에 버튼 하나 (+ 키)
1. `.acts` 안에 `<button class="btn key" id="새-id" title="키 · 설명">동사</button>` — 네이비 `.btn` 은 이미 `실행 기록` 이 쓴다
2. JS: `$("#새-id").addEventListener("click", async () => { try { … await api(…) … toast("…") } catch (e) { toast(e.message) } })`
3. 키가 필요하면 끝의 `keydown` 에 `else if (e.key === "x") $("#새-id").click();` — 04 표와 겹치지 않게
4. 서버 API 가 새로 필요하면 `make_handler` 에 경로를 더하고 **토큰 검사를 지나는 쪽**(`/api/…`)에 둔다 + `tests/test_app.py` 에 401 · 성공 둘 다
5. 좁은 창(500 사진)에서 버튼이 줄바꿈되는지 · MANUAL 화면 절(03 DECK) · 키 줄

### R5 ④ 강조에 모드 하나 더
1. `KNOBS[4].vals` 에 값, `label` 에 이름(짧게 — 값 칩에 들어간다)
2. `applyFocus` 는 `f-<값>` class 를 SVG 에 붙인다 → `ui.html` 에 `.flow.f-<값> …` 규칙 (흐리기 `opacity:.12`–`.3` · 강조 `var(--accent)`)
3. 강조할 요소에 class 가 없으면 서버 쪽(`_node_svg` · `_row_svg`)에서 class 를 붙인다 — 07 의 표에 한 줄
4. 사진 (강조를 켠 상태는 Playwright 또는 손으로)

### R6 LED 하나 더
1. `.leds` 안에 `<span class="led" id="led-이름" title="라임 = … · 흰색 = …"><i></i>이름</span>` — 이름은 영문 소문자 한 낱말
2. `applyState` 에서 `led("#led-이름", 상태 ? "ok" : "")` — `busy` 는 깜빡임(진행 중), `err` 는 흰색(문제)
3. MANUAL 의 LED 줄에 뜻

### R7 새 구역 — 서랍으로 (05)
늘 보일 필요가 없으면 **서랍**이 먼저다 (세 칸 배치를 건드리지 않는다).
1. `openRuns` 를 본떠 `openXxx()`: `el("div", "drawer")` → `pane-h` 에 `num` `05` · `name` 영문 대문자 · 한국어 설명 · `닫기 Esc` → `pane-b`
2. 여는 버튼은 R4, `Esc` 는 이미 `closeDrawer()` 가 모든 서랍을 닫는다
3. MANUAL 화면 절의 구역 표 · 원칙 3 줄에 `05 NAME`

### R8 흐름도 카드 모양
1. 07 을 읽는다. 모양은 `SVG_CSS` 의 class 규칙 · 그리는 법은 `_node_svg`
2. 새 모양이면 class 를 더하고 `SVG_CSS` 에 규칙 (토큰만 · 점선은 `4 3` · `2 2`)
3. 치수를 바꾸면 8 의 배수 · GUIDE 7-4 표를 같이 고친다
4. `python -m unittest tests.test_graph` → `--svg` 로 다크 · 라이트 → 사진

### R9 유량계 표정 하나 더
1. `.mascot.<이름> .needle{…}` — 바늘 각도 `--a` 와 있는 keyframes 로만. 몸통 · 다리 모양은 바꾸지 않는다 (앱마다 캐릭터 하나 — 원칙 7)
2. `mascot("<이름>")` 을 부를 곳. 잠깐 보이고 돌아와야 하면 `mascot()` 안의 되돌림 목록에 이름을 더한다
3. MANUAL 원칙 7 줄에 뜻

### R10 문서 사진 다시 찍기
화면이 눈에 띄게 바뀌었을 때만. Playwright 가 있어야 한다: `python tests/e2e_ui.py --pages` → `docs/page/` 의 hero · title · card · flow · explorer · run. 사진은 지어낸 예시(`tests/examples`)로만 찍힌다 — 사내 코드가 찍힌 사진은 커밋하지 않는다.

---

## 09 확인

1. **자동** — `python build.py --check` · `python -m unittest discover -s tests` · `python ../tools/works_check.py`
2. **사진** — `python tests/ui_check.py shots` (Playwright 없이 Edge · Chrome 으로. 예시 폴더를 띄워 `shots/ui-dark-1440.png` · `ui-dark-500.png` · `ui-light-1440.png` · `ui-light-500.png`). 네 장을 이 표로 본다:

   | 볼 것 | 합격 |
   |---|---|
   | 테마 | 다크 · 라이트 둘 다 모든 글자가 읽힌다 (라이트의 라임 글자는 `--accent-ink`) |
   | 색 | 빨강 · 주황 · 노랑 · 보라 · 분홍이 없다. 경고는 흰(라이트는 검은) `ERR` 칩 |
   | 라임 | 지금 · 켜짐 · 선택 · 진행에만 (노브 ② · 값 칩 · LED · 커서 · 고른 카드) |
   | 흐름도 | 카드 · 알약 · 선이 각지다 · 선은 가로 · 세로 · 카드끼리 안 겹친다 |
   | 좁은 창 | 500 사진에서 본체 테두리가 다 보이고 가로로 넘친 부품이 없다 |
   | 글자 | 다른 글꼴로 보이는 글자가 없다 · 굵은 글자는 1px 겹친 모양 · 잘린 글은 `…` |
   | 구역 | 번호 배지(두 자리) + 영문 이름 + 한국어 설명 |

   내 폴더로 보려면 `--watch "D:\분석 폴더"` (코드는 읽기만). 사진은 `shots/` 에 — 커밋하지 않는다.
3. **브라우저 E2E** — Playwright 가 있으면 `python tests/e2e_ui.py` (마지막 줄 `E2E OK`, 폭 460 · 누르기 · 강조 · 서랍 · 실행 중까지). 없으면 CI 가 돌린다
4. **손으로** — `python flow-1.py` → 카드 누르기 · 올리기 · 노브 넷 · `/` 찾기 · 붙여 넣기 · `실행 기록` 서랍 · 테마(`--set theme=light`)

---

## 10 하지 않는다 (화면)

[GUIDE › 10](GUIDE.md#10-자주-틀리는-것) 의 표에 더해:

| 틀린 것 | 결과 | 맞게 |
|---|---|---|
| 외부 CSS · JS · 폰트 · 이미지 링크 (CDN 포함) | 사내망에서 안 뜬다 · W-03 위반 | 전부 `ui.html` 안에. 그림은 CSS · 인라인 SVG |
| JS 라이브러리 · 프레임워크 추가 | 한 파일 · 표준 라이브러리 원칙이 깨진다 | 지금처럼 바닐라 JS |
| `innerHTML` 에 파일 이름 · 경로 · SQL · 오류 글 | 스크립트가 끼어든다 | `el(태그, class, 글)` · `textContent` |
| `style.color = …` 처럼 JS 로 색 | 테마가 안 바뀐다 · 토큰을 우회 | class 를 붙이고 CSS 에서 토큰 |
| 이모지 · 폭 2칸 기호(체크 · 경고 삼각형 · 별)로 상태 | 칸이 어긋난다 · DESIGN 03 위반 | `√` · `×` · `●` · `○` · `◐` · `‼` |
| 새 `font-size` · `letter-spacing` · `font-weight` | 흐려지고 칸이 어긋난다 | 04 의 크기 · `<b>` |
| 흐름도 안의 둥근 모서리 · 그림자 · 그라데이션 | works 디자인과 어긋난다 | 각진 1px 선 |
| 노브 다섯 번째 · 노브 색 순서 바꾸기 | 원칙 2 (색 = 조작) 가 깨진다 | 노브 값(`KNOBS`)을 바꾸거나 버튼 |
| 구역 번호 다시 매기기 | 문서 · 사진 · 사람의 기억과 어긋난다 | 새 구역은 05 부터 |
| `localStorage` 에 코드 · SQL · 경로 목록 | W-05 (원문은 메모리에만) | 화면 자리(`flow1.exbase` 처럼)만 · 이름은 `flow1.` 로 시작 |
| 폴링을 1초보다 자주 | PC 가 바빠진다 | 설정 `scan.poll_sec` |
| `alert` · `confirm` · `prompt` | 창 흐름이 끊긴다 | `toast` · 서랍 · 버튼 두 개 |
| `!important` 새로 쓰기 | 테마 · 움직임 끄기(reduced-motion)를 이긴다 | 더 구체적인 선택자 |
| `ui.html` 만 고치고 `build.py` 를 안 돌림 | 창에 안 보이고 CI 가 실패한다 | 고칠 때마다 `python build.py` |

화면을 고치다 막히면 고친 것을 되돌리고(`git checkout -- ui.html flow1_assets.py`) 한 가지씩 다시 한다. 예쁜 화면보다 읽히는 화면이 먼저입니다.
