# Flow–1 가공 가이드 — 사내 LLM 용

이 문서는 Flow–1 을 **사내에서 이어 고치는 LLM**(opencode 등)이 읽는다. 사람은 [MANUAL](MANUAL.md) 을 읽으면 된다.
opencode 에 자동으로 붙는 요약(절대 바꾸지 않는 것 · 같이 바꾸는 곳 · 끝내기 전 · 사내 사본 업데이트)은 [flow-1/AGENTS.md](../AGENTS.md), 화면을 고치는 법은 [UI.md](UI.md) 에 있다.
목표는 하나다: 사내에서 고친 Flow–1 이 이 저장소의 Flow–1 과 **같은 품질** — 같은 분석 결과 · 같은 화면 · 같은 안전장치 — 로 도는 것.

> **원칙 넷**
> 1. **새로 짜지 않는다.** 이 코드를 그대로 가져가 설정과 작은 고침으로 맞춘다. 같은 품질로 가는 가장 짧은 길이다.
> 2. **설정으로 되는 일은 코드를 고치지 않는다.** 사내 패키지 이름 · 함수 이름은 설정(`query.modules` · `query.calls`)이다 → [05](#05-사내-쿼리-패키지-맞추기)
> 3. **테스트가 계약이다.** 이 문서와 코드가 다르면 코드와 테스트가 맞다. 이 문서를 고친다.
> 4. **고칠 곳만 읽는다.** 모듈마다 1,500줄 안쪽이다. [02 코드 지도](#02-코드-지도)에서 구역을 찾고 그 구역만 읽는다.

---

## 00 읽는 법

| 하려는 일 | 읽을 절 | 고칠 파일 |
|---|---|---|
| 설치 · 사내 패키지 이름 넣기 | [INSTALL.md](../INSTALL.md) 4단계 → [05](#05-사내-쿼리-패키지-맞추기) | 없음 (설정) |
| 어떤 호출이 쿼리로 안 잡힘 · 잘못 잡힘 | [04](#04-분석-규칙) → [09](#09-작업-절차) → [10](#10-자주-틀리는-것) | `flow1_scan.py` |
| SQL 절이 이상하게 나뉨 · 테이블을 못 찾음 | [06](#06-sql-방언-맞추기) | `flow1_sql.py` |
| 화면 · 카드 · 선 · 색 · 치수 · 문구 | [UI.md](UI.md) (고치는 법 · 레시피) · [07](#07-화면-규격) (치수 · 색 자리) · [08](#08-바꾸면-안-되는-것) | `ui.html` · `flow1_graph.py` |
| 실행 시간 · 행 수 (`--run`) | [03](#03-데이터-모델) › 실행 기록 · [12](#12-문제-해결) | `flow1_trace.py` |
| 서버 · 설정 · 감시 · 탐색기 | [02](#02-코드-지도) › HTTP API | `flow-1.py` |
| 사용자가 붙여 넣을 요청 글 | [11](#11-프롬프트-모음) | — |

낱말:

| 낱말 | 뜻 |
|---|---|
| 쿼리 호출 | SQL 을 실행하는 파이썬 호출 하나 (`dq.query(sql)`). 카드 한 장 = 쿼리 호출 하나 |
| 자리 | SQL 에 코드의 값이 들어가는 곳. 흐름도에 `{이름}` 상자로 보인다 (파이썬 쪽 자리). `:x` · `?` · `%s` · `${x}` · `@x` 는 SQL 쪽 **바인드** |
| 결과 dict | `flow1_scan` 이 파일 하나를 읽은 결과 (format 1) — [03](#03-데이터-모델) |
| 그래프 | `flow1_graph.build` 의 결과 — 노드 · 간선 · 좌표 |
| 층 · 열 | 흐름도의 왼쪽 → 오른쪽 칸. 간선은 늘 왼쪽 열에서 오른쪽 열로 간다 |
| 판 | 이미 읽힌 테이블에 다시 쓰면 새 판 (`tmp.x #2`) — 흐름에 순환이 생기지 않게 |
| 벌 | 읽기만 하는 테이블을 여러 열에서 쓰면 쓰는 열마다 한 벌 (`t:dw.orders~2`) — 열을 가로지르는 긴 선이 생기지 않게 |
| 상세 | 카드에 보이는 줄의 양 — 1 간단 · 2 보통 · 3 전부 |

---

## 01 합격 기준

고친 뒤 **전부** 통과해야 끝이다. 하나라도 안 되면 끝난 것이 아니다.

| # | 확인 | 명령 (flow-1 폴더에서) | 합격 |
|---|---|---|---|
| 1 | 단위 · 통합 | `python -m unittest discover -s tests` | 마지막 줄 `OK` — **Python 3.8** 과 사내 최신 파이썬 둘 다 |
| 2 | 화면 내장 | `python build.py --check` | 종료 코드 0 |
| 3 | 자체 시험 | `python flow-1.py --check` | `- 자체 시험 : 내장 예시 쿼리 6 · 테이블 6 · 조인 5 · 정상` 과 마지막 줄 `결과: OK` |
| 4 | 분석 결과 | `python flow-1.py --scan tests/examples/daily_sales.py` | `tests/golden/daily_sales.py.txt` 와 한 글자도 다르지 않다 (1번이 확인한다) |
| 5 | 브라우저 | `python tests/e2e_ui.py` | 마지막 줄 `E2E OK` (Playwright 가 있을 때 · CI 에서는 자동). 화면을 고쳤는데 Playwright 가 없으면 `python tests/ui_check.py shots` → `결과: OK` + 사진 네 장을 [UI.md › 09](UI.md#09-확인) 표로 |
| 6 | 속도 | 1번의 `test_big_graph_is_fast` | 쿼리 150개 파일의 흐름도 + SVG 10초 안. 기준 PC: 분석 0.3초 · 배치 + SVG 0.04초 · 예시 파일 분석 5 ms |
| 7 | 사내 코드 | 사내 분석 스크립트 세 개 이상 `--scan` | 아래 표 |

7번 — 사람이 SQL 원문과 `--scan` 출력을 나란히 보고 확인한다:

| 볼 것 | 합격 |
|---|---|
| 쿼리 수 | 사람이 센 SQL 실행 호출 수와 카드(`Qnn`) 수가 같다. 모자라면 [04](#04-분석-규칙) · [05](#05-사내-쿼리-패키지-맞추기), 남으면 [10](#10-자주-틀리는-것) |
| FROM · JOIN | 카드의 테이블 = SQL 원문의 테이블 (별칭 · 조인 종류까지) |
| WHERE | 조건 줄 수 = 괄호 밖 `AND` 로 나뉜 조건 수 (괄호 밖에 `OR` 가 있으면 한 줄) |
| 흐름 | 앞 쿼리의 결과를 쓰는 SQL 이면 `{자리} ← Qnn` 줄이 있다 (화면에서는 점선) |
| 오탐 | `print` · 로그 · 문자열 만들기 · UI 글이 카드가 되지 않는다 |
| 멈춤 | 어떤 파일에서도 예외로 멈추지 않는다 — 못 읽으면 `error` · 경고 글로 남는다 |

눈으로 보는 합격은 [07](#07-화면-규격) 끝의 표.

---

## 02 코드 지도

```text
 .py · .ipynb · .sql ─▶ flow1_scan.scan_file ─▶ 결과 dict (format 1) ─▶ flow1_graph.build ─▶ 그래프 ─▶ flow1_graph.svg ─▶ SVG
                          │ SQL 글마다                                     ▲ runs (노드마다 실행 요약)
                          └▶ flow1_sql.parse_sql                           │
 --run  flow1_trace.run_script ─▶ runs\…\<시각>.json ─▶ flow1_trace.match ─┘
 flow-1.py  Watch (감시 · 바뀐 파일만 다시 읽기) ─▶ App (HTTP API · 그래프 캐시) ─▶ ui.html (2초 폴링 · SVG 붙이기 · 02 자세히)
```

| 파일 | 줄 | 하는 일 | 바깥에 내주는 것 |
|---|---|---|---|
| `flow1_sql.py` | 약 1,200 | SQL → 문장 · 절 · 읽는/쓰는 테이블 · 색칠 조각 | `parse_sql` · `looks_like_sql` · `sql_spans` · `tokens` |
| `flow1_scan.py` | 약 1,250 | 파이썬 · 노트북 → 쿼리 호출 · 자리 · 병합 · 입출력 · 간선 | `scan_file` · `scan_text` · `DEFAULT_CALLS` · `DEFAULT_SINKS` |
| `flow1_graph.py` | 약 1,250 | 결과 dict → 카드 줄 · 층 배치 · 직각 간선 · SVG · `--scan` 글 | `build` · `svg` · `summary` · `query_rows` · `columns_of` · `THEMES` · `SVG_CSS` |
| `flow1_trace.py` | 약 450 | `--run`: 쿼리 호출 자리만 감싸 시간 · 행 수 기록 · 기록 읽기 | `run_script` · `list_runs` · `pick_run` · `match` |
| `flow-1.py` | 약 1,450 | 진입점 · 설정 · 감시 · 탐색기 · 로컬 서버 · 점검 | 명령줄 (`--help`) · HTTP API |
| `ui.html` | 약 860 | 화면 한 파일 (HTML · CSS · JS) | — |
| `build.py` | 46 | `ui.html` · 폰트 → `flow1_assets.py` | `--check` |
| `flow1_assets.py` | 생성 | 내장 화면 · 폰트 | **고치지 않는다** |

모듈 안은 `# ──── 01 이름` 줄로 구역을 나눴다. 구역 이름으로 찾아 읽는다 (`grep -n "# ──" flow1_scan.py`).

| 모듈 | 구역 | 주요 함수 |
|---|---|---|
| `flow1_sql` | 01 토큰 | `tokens` · `Tok` · `KEYWORDS` · `AGGREGATES` · `NOT_COLUMN` · `ALIAS_STOP` · `JOIN_WORDS` · `SET_OPS` |
| | 02 조건 · 컬럼 | `col_refs` · `params_in` · `Parser`(`statement` · `query` · `with_list` · `select` · `branch` · `clauses` · `columns` · `sources` · `table_ref` · `conditions`) |
| | 03 읽는 테이블 · 쓰는 테이블 · 자리 | `statement_io` · `AT_ORDER` · `_fallback_reads` |
| | 04 바깥에 내주는 것 | `split_statements` · `looks_like_sql` · `parse_sql` · `sql_spans` |
| `flow1_scan` | 01 값 | `Val` · `Env` · `concat` · `map_text` |
| | 02 파일 읽기 | `read_text_file`(utf-8 · cp949) · `notebook_cells` |
| | 03 스캐너 | `Scanner`(`stmt` · `assign` · `for_loop` · `if_stmt` · `_expr` · `binop` · `percent` · `str_format` · `call` · `_sql_arg` · `_module_call` · `read_sql_file` · `inline_call` · `make_query` · `make_op` · `make_input` · `make_output` · `uncalled`) |
| | 04 결과 | `_stats` · `scan_text` · `scan_file` |
| `flow1_graph` | 01 치수 | `CELL` · `ROW` · `HEAD` · `WIDTH` … · `cw` · `cells` · `clip` |
| | 02 카드 줄 | `join_label` · `row` · `select_rows` · `query_rows` · `columns_of` |
| | 03 그래프 만들기 | `build` (테이블 판 · 노드 · 간선) |
| | 04 포트 | `ports` · `_anchor_y` (선이 붙는 줄) |
| | 05 배치 | `layout` (층 · 벌 · 더미 · 순서 · 높이 · 트랙 · 열) |
| | 06 SVG | `THEMES` · `SVG_CSS` · `_row_svg` · `_node_svg` · `_run_svg` · `svg` |
| | 07 글 요약 | `summary` (`--scan`) |
| `flow1_trace` | 01 감싸기 | `_Wrap` · `spots_of` · `instrument` · `_Finder` · `_Loader` |
| | 02 기록 · 03 실행 · 04 읽기 | `Recorder` · `run_script` · `list_runs` · `pick_run` · `match` |
| `flow-1.py` | 01 설정 | `DEFAULT_CONFIG` · `validate_config` · `set_config_values` · `watch_edit` |
| | 02 감시 | `Watch` · `list_dir` · `places` · `sql_hint` |
| | 03 앱 · 로컬 서버 | `App` · `make_handler` |
| | 04 창 · 05 창 없이 · 06 진입점 | `open_app_window` · `cli_scan` · `cli_svg` · `run_check` · `main` |

`ui.html` 순서: `<style>` 토큰 → `.device` → `.bar`(유량계 · 로고 · 회사 이름 · LCD · LED · 전원) → `.main`(`#p-files` · `#p-flow` · `#p-detail`) → `.deck`(노브 · 버튼) → `.foot` → `<script>`(상태 `S` · `api` · `poll` · `loadGraph` · `select` · `renderDetail` · 탐색기 `EX` · `openRuns` · 키). 서버가 `__THEME__` · `__TOKEN__` · `__BOOT__` · `__SVGCSS__` 를 바꿔 넣는다 (`App.render_index`).

### HTTP API

| 방법 | 경로 | 받는 것 | 주는 것 |
|---|---|---|---|
| GET | `/` | — | 화면 (토큰 · 테마 · 설정 일부를 박아 넣음) |
| GET | `/font/flow-1-dos.woff` | — | 폰트 (토큰 없이) |
| GET | `/api/ping` | — | `{app, version}` (토큰 없이 — 켜져 있는지) |
| GET | `/api/state` | — | 감시 목록 · 파일마다 요약 · 실행 상태 · `gen`(무엇이든 바뀔 때마다 +1 — 화면은 이것이 바뀌면 흐름도를 다시 받는다) |
| GET | `/api/graph` | `f`(파일 키 · `all`) · `d`(1–3) · `run` | SVG 글 · 노드 요약(좌표 · 찾기용 글) · 간선 · 통계 · 보이는 실행 |
| GET | `/api/detail` | `f` · `id` | 노드 하나의 전부 — 쿼리면 결과 dict 항목 · 색칠 조각 · 상세 3 줄 · 테이블별 컬럼 · 실행 이력 12회 |
| GET | `/api/runs` | `f` | 실행 기록 목록 |
| GET | `/api/browse` | `path` | 탐색기 한 단계 (폴더 · 코드 파일 · SQL 표시 `●`) |
| GET | `/api/svg` | `f` · `d` · `run` · `theme` | 내려받을 SVG (색 · 폰트를 안에 담음) |
| POST | `/api/watch` | `{add}` 또는 `{remove}` | 새 상태 |
| POST | `/api/open` · `/api/close` | `{path}` · `{key}` | 이번만 연 파일 (설정에 안 남음) |
| POST | `/api/paste` · `/api/paste/delete` | `{text, name}` · `{key}` | 붙여 넣은 코드 (메모리에만) |
| POST | `/api/rescan` · `/api/example` · `/api/shutdown` | `{}` | — |

지키는 것: Host 헤더가 `127.0.0.1:포트` · `localhost:포트` 가 아니면 403 · `/api/*` 는 `X-Flow-Token` 헤더(화면의 `<meta name="flow-token">`)가 맞지 않으면 401 · POST 는 `Content-Type: application/json` 만(415) · 본문은 `MAX_PASTE × 3` 바이트까지(413) · 모든 응답에 `nosniff` · `DENY` · `no-referrer`.

---

## 03 데이터 모델

모든 결과는 JSON 으로 옮길 수 있는 dict · list · str · int · float · bool · None 만 쓴다.

### 결과 dict (format 1) — `scan_text` · `scan_file` · `--json`

```text
{ "format": 1, "file": 절대 경로 또는 "", "name": 파일 이름, "kind": "py" · "ipynb" · "sql",
  "error": "" 또는 파일을 못 읽은 까닭 (이때 queries … 는 빈 목록),
  "warnings": [글…]            셀 건너뜀 · SQL 파일 못 찾음 · 노드 한도
  "lines": 줄 수, "cells": [[셀 번호, 첫 줄, 줄 수]…]   (ipynb)
  "queries": [쿼리…], "ops": [병합…], "inputs": [파일 입력…], "outputs": [출력…],
  "edges": [간선…], "sql_files": [읽은 SQL 파일 절대 경로…],
  "stats": {"queries", "tables", "joins", "conds", "ops", "inputs", "outputs", "params"} }
```

쿼리 (`queries[]`):

| 키 | 예 | 뜻 |
|---|---|---|
| `id` · `n` | `"q3"` · `3` | 파일 안 번호 (카드 `Q03`) |
| `seq` | `7` | 파일 안에서 만든 순서 (쿼리 · 병합 · 입출력 통틀어) — 흐름도 순서의 기준 |
| `line` · `end` | `45` · `45` | 카드에 적는 줄. 펼친 함수 안이면 **부른 줄** |
| `pos` | `[45, 11, 45, 29]` | 실제 호출 자리 (줄 · 칸 · 끝 줄 · 끝 칸) — `--run` 이 이 자리를 감싸고, 기록을 이 자리로 잇는다 |
| `via` · `scope` | `"load() L12"` · `"def load"` | 펼친 함수 경로 · 부르지 않은 함수 안 |
| `loop` · `branch` | `false` · `true` | 반복 안 · if 갈래 안 |
| `cell` · `cell_line` | `3` · `2` | 노트북 셀 번호 · 셀 안 줄 (ipynb) |
| `call` · `var` | `"dq.query"` · `"df_items"` | 부른 식 · 결과를 받은 변수 |
| `sql` | `"SELECT … IN ({order_ids})"` | 되살린 SQL. 모르는 값은 `{이름}` |
| `sql_src` | `literal` · `fstring` · `format` · `percent` · `concat` · `cell` · `file:sql/a.sql` · `dynamic` | SQL 을 만든 방법 |
| `sql_file` | `"sql/a.sql"` | `sql_src` 가 `file:` 일 때만 |
| `dynamic` | `false` | SQL 을 통째로 모름 → 카드 테두리 점선 |
| `params` | `[{"name", "expr", "deps", "line"}]` | 자리마다 원래 식 · 기대는 노드 id. `arg: true` 는 SQL 밖 인자 |
| `parsed` | `{stmts, reads, writes, error}` | `flow1_sql.parse_sql` 결과 그대로 |
| `reads` · `writes` | `[{"key": "dw.orders", "name": "dw.orders", "at": [[0, "src", 0]]}]` | = `parsed.reads` · `parsed.writes` |

`at` = `[문장 번호, 종류, 번호]`. 종류 순서는 `src` · `using` · `where` · `having` · `select` · `union` · `with` · `head` (`AT_ORDER`) 이고 **첫 자리가 흐름도의 선이 붙는 줄**이다. CTE 안에서 읽은 테이블은 그 CTE 를 쓰는 FROM 줄에 붙는다.

문장 (`parsed.stmts[]`):

| 키 | 뜻 |
|---|---|
| `kind` | `select` · `insert` · `create` · `update` · `delete` · `merge` · `drop` · `truncate` · `values` · `other` |
| `target` · `target_key` | 쓰는 테이블 (원래 글 · 소문자 키) |
| `select` | SELECT 구조 (아래). INSERT … SELECT · CREATE … AS SELECT 도 여기 |
| `ctes` | `[{name, key, cols, select}]` |
| `set` · `where` · `using` | UPDATE 의 SET · UPDATE/DELETE 조건 · MERGE USING · UPDATE FROM 의 `{sources}` |
| `note` | `EXPLAIN` · `VIEW` · `TEMP` · 모르는 문장이면 첫 낱말 |
| `n` · `span` · `reads` · `writes` · `error` | 문장 번호 · 원문 위치 · 이 문장의 읽기/쓰기 · 다 못 읽은 까닭 |

SELECT: `distinct` · `top` · `columns` · `sources` · `where` · `group` · `having` · `order` · `limit` · `union[{op, select}]` · `ctes` · `subs` · `extra`(모르는 절 · `SORT BY` 등을 글 그대로).
컬럼: `{text, expr, alias, star, agg, win, cols, params, subs}`.
FROM 항목: `{kind, name, key, alias, join, on, using, select, text, pos}` — `kind` 는 `table` · `cte` · `subquery` · `values` · `function` · `lateral`, `join` 은 `""`(첫 항목) · `INNER` · `LEFT` · `RIGHT` · `FULL` · `CROSS` · `,` · `LEFT SEMI` · `LEFT ANTI` · `NATURAL …` · `… APPLY` · `LATERAL VIEW` · `USING`(MERGE).
조건: `{text, kind, cols, params, binds, subs}` — `kind` 는 `filter` · `join`(`a.x = b.y` 처럼 양쪽 별칭이 다른 등호) · `sub`(서브쿼리) · `or`(괄호 밖 OR — 조건 전체가 한 줄) · `qualify`.

병합 (`ops[]`): `{id: "j1", n, seq, 자리…, kind, how, on, left_on, right_on, index, call, var, inputs}` — `kind` 는 `merge` · `join` · `concat`, `inputs` 는 `[{side, label, deps}]` 이고 `side` 는 `L` · `R` · `+`.
파일 입력 (`inputs[]`): `{id: "i1", kind: "read_csv" …, target, var, call, 자리…}`.
출력 (`outputs[]`): `{id: "o1", kind: "to_csv" …, target, var, call, 자리…}` — `to_sql` 은 `table: {key, name}` 이 더 있다 (그 테이블에 쓰기).
간선 (`edges[]`): `{from, to, kind, label, side}` — `kind` 는 `param`(앞 노드의 값이 SQL 자리로 · label = 자리 이름) · `df`(데이터가 병합 · 출력으로). 테이블 선은 결과 dict 에 없다 — 그래프가 `reads` · `writes` 로 만든다.

### 그래프 — `flow1_graph.build(results, detail, runs)`

노드 id: 파일 하나면 `q1` · `j1` · `i1` · `o1` · `t:dw.orders`(테이블은 소문자 키) · `t:tmp.x#2`(둘째 판) · `t:dw.orders~2`(열마다 한 벌). 여러 파일(`00 전체`)이면 앞에 `f0:` · `f1:` 이 붙고, 테이블은 앞붙이 없이 파일끼리 **공유**한다 — 그래서 파일 사이 흐름이 이어진다.

| 노드 | 키 |
|---|---|
| 공통 | `id` · `kind`(`query` · `op` · `table` · `input` · `output`) · `x` · `y` · `w` · `h` · `layer` · `file` · `ref` · `line` |
| 쿼리 · 병합 | `rows` · `title` · `meta` · `num`(`Q01` · `J01`) · `dyn` · `loop` · `run` · `has_run` · `params` |
| 테이블 | `name` · `key` · `ver` · `role`(`source` · `temp` · `sink`) · `readers` · `writers` · `label` · `dup`(벌) |
| 입출력 | `label`(`read_csv · a.csv`) · `target` · `meta` · `table` |

줄 (`rows[]`): `{lbl, text, kind, anchor, ph, segs, cls}` — `lbl` 은 왼쪽 칸 글(`FROM` · `LEFT` · `WHERE` …), `ph` 는 그 줄의 자리 · 바인드, `segs` 는 `[[글, 색 class]…]`, `cls` 는 `jn`(조인 줄 · 굵게) · `j`(조인 조건) · `d`(흐림).
`anchor`: `src:문장:i` · `using:문장:i` · `where:문장:i` · `where+:문장`(더 보기) · `having:문장:i` 또는 `having:문장:*` · `select:문장:0` · `union:문장:k` · `with:문장:키` · `head:문장`. 테이블 선은 `at` 과 같은 anchor 의 줄에, 자리 선은 그 자리 이름이 `ph` 에 든 줄에 붙는다 (`ports`).
간선: `{id, from, to, kind, label, sy, ty, join, chain, back, pts}` — `kind` 는 `read` · `write` · `param` · `df`, `sy` · `ty` 는 노드 위에서 잰 붙는 높이, `pts` 는 직각 꺾은선 좌표.

### 실행 기록 — `%LOCALAPPDATA%\flow-1\runs\<스크립트>-<해시>\<날짜-시각>.json`

```text
{ "version": 1, "run": "20260927-101500-123", "file": 스크립트 절대 경로, "started": ISO 시각, "t0": 시작(epoch 초),
  "pid", "python", "ended", "ms", "exit", "ok", "error"(비밀번호 꼴은 가림),
  "calls": [{"seq", "tag": "파일:줄:칸", "stack": [[파일, 줄]…], "t": 시작(초), "ms", "rows", "cols", "ok", "err"}] }
```

`live.json` 은 같은 모양에 `busy[]` · `beat` 가 더 있고, 끝나면 지운다. 화면은 `beat` 가 15초 넘게 멈추면 끊긴 실행으로 본다.
`match(run, results)` 는 `tag` 의 파일:줄:칸 = 쿼리의 `pos` 로 노드를 찾는다. 같은 자리가 여럿(함수를 여러 곳에서 부름)이면 `stack` 의 줄로 가른다.
**SQL 원문 · 인자 값 · 결과 데이터 · 명령줄 인자는 넣지 않는다** ([08](#08-바꾸면-안-되는-것)).

---

## 04 분석 규칙

이 절이 정본이다. 코드는 `flow1_scan.py › 03 스캐너`. 코드를 **실행하지 않고** `ast` 로 읽으며, 값은 정적으로 아는 만큼만 안다.

### 4-1 값 (`Val`)

`kind`: `str` · `num` · `df`(데이터 · 쿼리 결과) · `mod`(모듈에서 나온 이름) · `list` · `dict` · `obj`(로컬 클래스 인스턴스) · `file` · `path` · `func` · `class` · `none` · `other`.
문자열은 `parts` = `("t", 글)` · `("p", 자리 이름)` 조각의 목록. `deps` = 이 값이 기대는 노드 id (쿼리 결과를 쓰면 `{"q1"}`) — **흐름 선은 전부 `deps` 에서 나온다.**

### 4-2 호출 하나를 읽는 순서 (`Scanner.call`)

위에서부터 **처음 맞는 하나**만 한다. 순서를 바꾸면 오탐 · 누락이 생긴다.

1. **문자열 다루기** — 받는 쪽이 아는 문자열: `format` · `join` · `strip` 류 · `upper` · `lower` · `replace` · `split` → 새 문자열 (쿼리 아님)
2. `textwrap.dedent` · `inspect.cleandoc` · `str(x)` → 문자열
3. **파일 · 경로** — `open` · `io.open` · `codecs.open` · `Path(…)` · `os.path.join` · `dirname` · `abspath` · `realpath` · 경로 `/` 경로 → 경로. `.read()` · `.read_text()` · `.readlines()` → 스크립트 옆 `.sql` · `.hql` · `.txt` 파일(1 MB 까지)을 읽은 문자열 (`file:상대 경로`). 다른 확장자는 읽지 않는다
4. **목록 · 사전** — `append` · `extend` · `items` · `values` · `keys` · `get`
5. 인자를 모두 평가한다 (인자 안의 쿼리 호출도 여기서 잡힌다)
6. 노트북 줄 매직 `%sql …` (스캐너가 `__flow1_sql__(…)` 로 바꿔 둔 것) → 쿼리
7. **로컬 함수 · 클래스 · 메서드** → 펼쳐 읽는다 (4-5)
8. **판다스 병합** — `pd.merge` · `pd.concat` · `merge_asof` · `merge_ordered` · `df.merge` · `df.join`(상대가 데이터일 때) · `df.append(데이터)` → 병합 노드
9. **판다스 입력** — `pd.read_csv` · `read_excel` · `read_parquet` · `read_pickle` · `read_json` · `read_feather` · `read_table` · `read_fwf` · `read_hdf` · `read_orc` · `read_xml` → 파일 입력 노드
10. **출력** — 데이터(또는 쿼리 결과에 기대는 값)의 `query.sinks` 메서드 → 출력 노드. `to_sql` 은 테이블 쓰기
11. **쿼리** — 아래 ① ② ③ 중 하나이고, 마지막 이름이 `DENY_CALLS` 가 아니면 쿼리 노드
    - ① 인자(위치 · 키워드) 가운데 **SQL 모양 문자열**(4-3)이 있다 — 패키지 이름을 몰라도 된다
    - ② `query.modules` 에서 나온 이름(모듈 · 거기서 만든 객체)의 `query.calls` 이름 호출 — SQL 이 변수여도 잡는다
    - ③ 판다스 `read_sql` · `read_sql_query`
    - ② ③ 인데 SQL 을 못 읽었으면 SQL 인자를 이 순서로 고른다 (`_sql_arg`): 키워드 `sql` · `query` · `stmt` · `statement` · `q` · `hql` → 첫 위치 인자 → 이름에 `sql` · `hql` · `query` · `stmt` 가 든 키워드(숫자 값은 빼고). 그 값이 `.sql` · `.hql` · `.txt` 경로면 **그 파일을 읽는다**. 그래도 모르면 식 전체가 `{자리}` 하나 (카드 테두리 점선)
    - `DENY_CALLS` 는 SQL 을 **다루기만** 하는 호출이다: `print` · 로그(`debug` · `info` · `warning` · `error` …) · `write` · `append` · `format` · `join` · `replace` · `strip` · `len` · `hash` · `encode` · `split` · `sub` · `search` · `match` · `compile` · `loads` · `dumps` · `set_description` · `assertEqual` 등 (전체는 코드). ② ③ 이면 이름이 겹쳐도 쿼리다
12. **그 밖** — 결과는 인자 · 받는 쪽의 `deps` 를 이어받는다 (데이터에서 나온 값은 데이터). 모듈에서 나온 호출의 결과는 다시 `mod` 다: `dq.connect()` → `demo_query.connect()` 이고, 여기에 부른 `query` 도 ② 에 걸린다

### 4-3 SQL 모양 (`flow1_sql.looks_like_sql`)

앞의 공백 · 주석을 떼고 첫 낱말로 가른다. **강함** = 첫 낱말이 전부 대문자 · 전부 소문자이거나, 글에 SQL 기호(줄바꿈 · `*` · `,` · `.` · `=` · `(` · 따옴표) 또는 절(`WHERE` · `JOIN` · `GROUP BY` · `ORDER BY` · `LIMIT` · `UNION` · `DISTINCT` · `AS`)이 있다.

| 첫 낱말 | SQL 로 보는 조건 |
|---|---|
| `SELECT` | 뒤에 `FROM` + 강함 |
| `WITH` | `AS (` 와 `SELECT` 가 있다 |
| `INSERT` · `UPSERT` | 바로 뒤 `INTO` · `OVERWRITE` |
| `REPLACE` | 바로 뒤 `INTO` |
| `CREATE` | 120자 안에 `TABLE` · `VIEW` + 강함 |
| `MERGE` | 바로 뒤 `INTO` + `USING` |
| `UPDATE` | `SET` + 강함 + 바로 뒤가 `the` · `a` · `an` · `your` · `my` 가 아님 |
| `DELETE` | 바로 뒤 `FROM` + 강함 |
| `DROP` · `TRUNCATE` | 바로 뒤 `TABLE` · `VIEW` |
| `EXPLAIN` | 나머지가 SQL 모양 |

그래서 `"Select files from the list"` 는 SQL 이 아니다 (대소문자가 섞인 첫 낱말 · 기호 없음).

### 4-4 SQL 되살리기

| 코드 | 결과 (`sql_src`) |
|---|---|
| 문자열 · 여러 줄 문자열 | 그대로 (`literal`) |
| f-string `f"…{START}…"` | 값을 아는 문자열이면 그 글, 모르면 `{이름}` (`fstring`). 서식(`:>10`) · 변환(`!r`)이 붙으면 늘 자리 |
| `"…{d}…".format(d=x)` · `"{}".format(x)` · `"{0}"` | 같은 규칙 (`format`). `{{` · `}}` 는 중괄호 글자 |
| `"…%s…" % x` · `% (a, b)` · `"%(k)s" % 사전` | 같은 규칙 (`percent`) |
| `a + b` · `s += t` | 이어 붙임 (`concat`). 모르는 쪽은 자리 |
| `", ".join(["a", "b"])` | 원소를 다 알면 이어 붙임, 아니면 식 전체가 자리 하나 |
| `dedent` · `cleandoc` · `strip` · `lstrip` · `rstrip` · `upper` · `lower` · `replace(글, 글)` | 글 조각에만 적용 (자리는 그대로) |
| `SQLS["daily"]` · `SQLS.get("daily")` · `LIST[0]` | 상수 키 · 번호면 그 원소 |
| `open("a.sql").read()` · `Path(…).read_text()` | 파일 글 (`file:a.sql`) |
| 사내 호출에 넘긴 경로 `dq.run_file("a.sql")` | 파일 글 (`file:a.sql`) — 그 이름이 `query.calls` 에 있을 때 |
| `%%sql` 셀 · `%sql` 줄 | 셀 글 (`cell`) · 줄 글 |

자리 이름 (`_ph_name`): ① 점으로 이은 이름이면 그대로(`cfg.start`) ② 식 안의 이름 가운데 노드에 기대는 첫 이름 ③ 식 안의 첫 이름(내장 함수 · 컴프리헨션 변수 빼고) ④ 호출이면 `함수()` ⑤ `expr`.
통째로 모르는 문자열을 변수에 담으면 자리 이름이 그 **변수 이름**이 된다 (`ids = ",".join(…)` → SQL 에는 `{ids}`, 02 에는 원래 식).

### 4-5 흐름 · 제어

- **자리 선(점선)**: 자리의 `deps` 마다 `앞 노드 → 쿼리` (`param`, label = 자리 이름). SQL 밖 인자(`params=` 등)가 노드에 기대면 그것도 (`arg: true`)
- **병합**: 입력마다 `df` 간선 (`L` · `R` · `+`). `how` 기본은 merge `inner` · join `left` · concat 없음(`axis=1` 이면 `axis=1`)
- **변수 이름**: 문장이 만든 노드가 하나면 그 노드의 `var` = 받은 이름 (`df = dq.query(…)` → `df`)
- **if**: 두 갈래를 다 읽는다. 한쪽만 바꾼 변수는 그 값, 둘 다 바꿨으면 if 쪽 값에 의존을 합친다. `if __name__ == "__main__":` 은 그냥 본문
- **for**: 목록(원소가 문자열 · 목록)이고 20개 이하면 원소마다 한 번씩 펼친다 (`for name, sql in SQLS.items()` 도). 아니면 한 번 읽고 `loop` 표시
- **while** 한 번 · **with** `as` 이름에 값 · **try** 본문 · except · finally 모두 · **match** 갈래 모두
- **로컬 함수**: 부른 자리마다 인자를 넣어 펼쳐 읽는다. 3단계까지 · 재귀는 멈춘다. 카드의 줄 = 부른 줄, `via` = 경로. 한 번도 부르지 않은 함수는 매개변수를 자리로 두고 한 번 읽는다 (`scope` → 카드에 `DEF`)
- **클래스**: `obj = C(…)` 는 `__init__` 을 펼치고 `self.x = …` 를 기억한다. `obj.m(…)` · 메서드 안의 `self.m(…)` 도 펼친다
- **import**: `import a.b` → `a` · `import a as x` → `x` = `a` · `from a import b` → `b` = `a.b`. **다른 파일의 함수는 펼치지 않는다** (알려진 한계 — 그 파일도 감시하면 그 파일의 흐름도에 나온다)

### 4-6 노트북

코드 셀만 이어 붙여 한 파일처럼 읽는다 (줄 번호는 이어 붙인 줄 · 카드에는 `셀n:줄`). `%` · `!` 로 시작하는 줄은 `pass` 로 바꿔 줄 번호를 지킨다. `%%sql` 셀은 SQL 카드 (`%%sql 변수 <<` 면 결과 변수). `%%time` · `%%timeit` · `%%capture` · `%%prun` 은 첫 줄만 뺀다. 그 밖의 `%%` 셀은 건너뛴다. 문법이 틀린 셀은 경고를 남기고 그 셀만 건너뛴다. 아주 옛 형식(`worksheets`)도 읽는다.

### 4-7 한도 · 약속

| 이름 | 값 | 뜻 |
|---|---|---|
| `MAX_NODES` | 400 | 파일 하나의 노드 수 — 넘으면 경고를 남기고 멈춘다 |
| `MAX_INLINE` | 3 | 함수 펼치기 깊이 |
| `MAX_UNROLL` | 20 | 반복을 원소마다 펼치는 한도 |
| `MAX_SQL_FILE` | 1,000,000 바이트 | 읽는 SQL 파일 크기 |
| `scan.max_files` | 400 | 감시 파일 수 (설정) |
| `MAX_PASTE` | 2,000,000 글자 | 붙여 넣기 |

- `scan_text` · `scan_file` · `parse_sql` 은 **예외를 던지지 않는다**. 못 읽으면 `error` · `warnings` · `kind: "other"` 로 글을 남긴다
- 같은 입력이면 같은 출력이다 (순서까지). 골든 파일이 이것을 본다
- 파일은 utf-8(BOM 포함) → cp949 순서로 읽는다

---

## 05 사내 쿼리 패키지 맞추기

**정본은 사내 스킬이다.** 데이터를 뽑는 사내 패키지의 사용법은 사내 LLM 에 스킬로 이미 들어 있다. 이 절은 그 스킬에서 **무엇을 꺼내 어디에 넣는지**만 정한다.
이 저장소는 공개 저장소라서 사내 패키지의 진짜 이름을 어디에도 적지 않았다 ([RULES.md](../../RULES.md) › W-12). 예시는 지어낸 `demo_query`(`tests/fake_pkg/demo_query`)로 든다. 진짜 이름은 **이 PC 의 설정에만** 넣는다.

### 5-1 스킬에서 꺼낼 것

| # | 꺼낼 것 | 예 (지어낸 것) | 넣는 곳 |
|---|---|---|---|
| 1 | import 이름 (여럿이면 전부 · 클라이언트를 만들어 주는 사내 도우미 모듈 포함) | `demo_query` | `query.modules` |
| 2 | SQL 을 받는 함수 · 메서드 이름 전부 | `query` · `execute` · `fetch_df` | `query.calls` |
| 3 | SQL 파일 경로를 받는 함수 | `run_file` | `query.calls` 에 같이 |
| 4 | 연결 · 클라이언트를 만드는 법 | `dq.connect()` · `Client("prod")` | 없음 — 4-2 의 12 로 따라간다 (5-2 로 확인만) |
| 5 | SQL 을 넘기는 인자 | 첫 위치 · `sql=` · `hive_sql=` | 없음 — 4-2 의 11 (확인만) |
| 6 | SQL 안의 변수 문법 | `{name}` · `${name}` · `:name` | `{…}` · `${…}` · `:x` · `?` · `%s` · `@x` 는 이미 안다. 그 밖이면 [06](#06-sql-방언-맞추기) 6-3 |
| 7 | 결과의 모양 | DataFrame · 행 목록 · 커서 | `--run` 의 행 수 — `shape` · `len()` · `rowcount` 가 있으면 된다 |

```text
python flow-1.py --set "query.modules=<import 이름1>;<import 이름2>"
python flow-1.py --set "query.calls=<함수1>;<함수2>;<파일 함수>" --check
```

`query.calls` 는 기본값(`query` · `execute` · `read_sql` · `sql` · `run` · `fetch`)을 **바꾼다**. 기본값에 있던 이름도 쓰면 모두 적는다.
반대로 기본값에 있지만 사내 패키지에서 SQL 과 상관없는 이름(예: 작업을 도는 `run`)은 **빼야** 오탐이 없다.

### 5-2 이렇게 따라간다 (확인용)

```python
import demo_query as dq            # dq = 모듈 demo_query
from demo_query import Client      # Client = demo_query.Client
c = Client("prod")                 # c = demo_query.Client()
with dq.connect() as conn:         # conn = demo_query.connect()
    df = conn.execute(sql)         # demo_query.… 의 execute ∈ query.calls → 쿼리 (sql 을 몰라도)
rows = c.fetch_df(make_sql(day))   # 쿼리 · SQL = {make_sql} (카드 테두리 점선)
dq.run_file("sql/daily.sql")       # run_file ∈ query.calls → sql/daily.sql 을 읽어 절로 나눈다
dq.query(hive_sql=text)            # 인자 이름에 sql 이 들었다 → SQL = text 의 값
```

클라이언트를 함수 인자로 넘기거나 `self.cli = dq.Client()` 로 담아도 따라간다 (펼치는 함수 · 인스턴스 안이면).
**다른 파일**에서 만든 클라이언트(`from utils import get_client`)는 모른다 → `query.modules` 에 그 모듈 이름(`utils`)도 넣는다. 그러면 `get_client()` 가 준 객체의 `query.calls` 호출도 쿼리다. 대신 그 모듈의 **같은 이름 함수는 모두** 쿼리로 보니, 이름이 겹치는 다른 함수가 있으면 `query.calls` 를 좁힌다.
SQL 을 객체로 만들어 실행하는 모양(`dq.Query(sql).run()`)이면 **만드는 이름**(`Query`)을 `query.calls` 에 넣고 실행 이름(`run`)은 뺀다 — 만드는 자리가 카드가 된다. 이때 `--run` 의 시간은 만드는 호출의 시간이라 실행 시간과 다를 수 있다 (알려 둔다).

### 5-3 확인

1. `python flow-1.py --check` → `- 쿼리 패키지: <이름> · 이 파이썬에서 import 할 수 있음` · `- 찾는 호출 : …` 이 스킬과 같다
2. 스킬의 **예제 코드**를 임시 파일로 두고 `python flow-1.py --scan 예제.py` → 예제의 쿼리 호출마다 카드 하나 (`Qnn` 수 = 호출 수)
3. 실제 분석 폴더에서 파일 셋 `--scan` → [01](#01-합격-기준) 7번 표. **스크립트는 실행하지 않는다**

### 5-4 설정으로 안 될 때

| 증상 (`--scan`) | 까닭 | 고칠 곳 |
|---|---|---|
| 사내 함수가 SQL 을 받는데 카드가 없다 | 이름이 `query.calls` 에 없음 · import 이름이 다름 · 다른 파일에서 만든 클라이언트 | 5-1 · 5-2 부터 다시. 그래도면 `Scanner.call` 의 11 앞에서 `module` · `attr` · `full` 을 임시로 찍어 본다 (커밋 전에 지운다) |
| 카드는 있는데 SQL 이 `(SQL 을 코드에서 찾지 못함)` | SQL 인자 이름이 규칙 밖 (`text=` · `body=` 등) | `flow1_scan.SQL_KWARGS` 에 그 이름 + `tests/test_scan.py` 의 `test_sql_argument_is_picked_by_keyword_name` 에 한 줄 |
| 사내 템플릿 문법 자리에서 테이블 · 조건이 깨진다 | 토큰이 모르는 문법 | [06](#06-sql-방언-맞추기) 6-3 |
| 쓰기만 하는 사내 함수(`dq.save(df, "tmp.x")`)의 테이블 선이 없다 | SQL 이 없어 쓰는 테이블을 모른다 | `query.sinks` 에 `save` 를 넣으면 출력 알약이 된다. 테이블로 이으려면 `Scanner.make_output` 의 `to_sql` 분기처럼 `table` 을 붙인다 |
| 결과가 데이터가 아닌 객체라 다음 병합이 안 이어진다 | `df` 가 아닌 값 | 정상 — `deps` 는 이어진다. 병합 카드는 판다스 이름(`merge` · `join` · `concat`)만 |

---

## 06 SQL 방언 맞추기

`flow1_sql` 은 완전한 문법기가 아니라 **절 나누기**다. 흐름도에 필요한 것 — 읽는 테이블 · 쓰는 테이블 · 조인 · 조건 · 컬럼 — 만 뽑고, 모르는 것은 글 그대로 둔다. Hive · Spark · Impala · Presto/Trino · Oracle · ANSI 가 섞여도 멈추지 않는다. **완전한 문법기로 바꾸지 않는다** — 모르는 방언 한 줄에 흐름도 전체가 멈추게 된다.

### 6-1 흐름

```text
tokens(글) → split_statements(괄호 밖의 ;) → Parser.statement(문장)
  SELECT · WITH  → query → with_list · select(UNION 가지) → branch → clauses(괄호 밖 절 키워드)
                   → columns · sources(FROM · JOIN · ON · USING) · conditions(AND · OR)
  INSERT · CREATE · UPDATE · DELETE · MERGE · DROP · TRUNCATE → 대상 이름 + 안의 SELECT
  그 밖          → kind "other" + FROM · JOIN · USING · INTO · TABLE · UPDATE 뒤의 이름 (_fallback_reads)
→ statement_io(문장) → reads [{key, name, at}] · writes [{key, name}]
```

토큰 종류: `ws` · `com`(주석) · `str`(`'…'`) · `qid`(큰따옴표 · 백틱 이름) · `num` · `word` · `op` · `(` · `)` · `,` · `.` · `;` · `ph`(파이썬 자리 `{name}`) · `bind`(`:x` · `?` · `%s` · `%(x)s` · `${x}` · `@x`) · `other`.
작은따옴표 안의 역슬래시 이스케이프(Hive · Spark 식)와 `''` 이스케이프를 둘 다 안다. 주석 · 문자열 안의 `;` 로는 문장을 나누지 않는다.

### 6-2 어디를 고치나

| 증상 | 고칠 곳 | 예 |
|---|---|---|
| 방언 키워드가 컬럼 · 별칭으로 잡힌다 | `KEYWORDS`(문법 낱말) · `NOT_COLUMN`(괄호 없이 쓰는 함수 · 의사 컬럼) · `ALIAS_STOP`(테이블 뒤에 와도 별칭이 아닌 낱말) | `FINAL` · `SAMPLE` |
| 새 조인 낱말 | `JOIN_WORDS` · `_join_type` · 흐름도 줄 이름 `flow1_graph.JOIN_LBL` | `LEFT ANY JOIN` |
| SELECT 안의 새 절 | `Parser.CLAUSE_STARTS`(두 낱말이면 둘째 낱말을 값으로) → `Parser.branch` 에 처리. 처리가 없으면 `extra` 에 글 그대로 (상세 3 에 보임) | `PREWHERE` 를 WHERE 처럼 |
| 새 문장 | `Parser.statement` 에 분기 + `looks_like_sql` 의 `_HEAD_RE` · 조건. 쓰는 문장이면 `kind` 를 `create` · `insert` 중 하나로 (그래야 `statement_io` 가 writes 로 · 카드 줄 이름은 `flow1_graph.STMT_LBL`) | `CACHE TABLE t AS SELECT …` (6-4) |
| 테이블 뒤 꼬리표를 별칭으로 본다 | `Parser.table_ref` 끝의 꼬리표 반복 (`TABLESAMPLE (…)` · `WITH (…)` 처럼) | `FOR SYSTEM_TIME AS OF …` |
| 템플릿 · 바인드 문법이 깨진다 | `tokens` — SQL 쪽 변수면 `bind`, 파이썬 쪽 값이면 `ph` | `{{ ds }}` (6-3) |
| 대괄호 이름이 깨진다 | `tokens` 의 따옴표 분기에 `[` … `]` 를 `qid` 로 · `unquote` | `[dbo].[t]` |

규칙: **먼저 `tests/test_sql.py` 에 그 문장을 넣은 테스트**를 쓰고 실패를 본 뒤 고친다. 모르는 모양은 예외 대신 `kind: "other"` 로 둔다. `AT_ORDER` 를 바꾸지 않는다.

### 6-3 예: Jinja 식 `{{ ds }}` 를 바인드로

```python
# flow1_sql.tokens — `if c == "{":` 분기 바로 앞에 넣는다
        if c == "{" and text.startswith("{{", i):          # Jinja 식 {{ ds }} — SQL 쪽 변수
            j = text.find("}}", i + 2)
            if 0 < j - i < 80:
                add(Tok("bind", text[i:j + 2], i, j + 2, text[i:j + 2]))
                i = j + 2
                continue
```

화면에서 상자로 보이게 `flow1_graph._segs_for` 의 바인드 앞글자 목록 `(":", "?", "%", "$", "@")` 에 `"{{"` 를 더한다.
확인: `parse_sql("SELECT a FROM {{ schema }}.t x WHERE x.d = {{ ds }}")` → reads 에 `{{ schema }}.t` · 조건의 `binds` 에 `{{ ds }}`. 파이썬 f-string 안에서는 `{{{{ ds }}}}` 로 써야 SQL 에 `{{ ds }}` 가 된다는 것도 테스트에 한 줄.

### 6-4 예: 새 문장 `CACHE [LAZY] TABLE t [AS] SELECT …`

```python
# flow1_sql.Parser.statement — `elif head in ("DROP", "TRUNCATE"):` 바로 앞에
        elif head == "CACHE" and len(t) > 2 and t[1].up in ("TABLE", "LAZY"):   # Spark
            st["kind"], st["note"] = "create", "TEMP"
            i = 1
            while i < len(t) and t[i].up in ("LAZY", "TABLE"):
                i += 1
            name, i = self._name(tt, i)
            st["target"], st["target_key"] = name, name.lower()
            if i < len(t) and t[i].up == "AS":
                i += 1
            if i < len(t) and t[i].up in ("SELECT", "WITH", "("):
                st["select"] = self.query(t[i:])
```

그리고 `looks_like_sql`: `_HEAD_RE` 의 낱말 목록에 `cache` 를 더하고, 마지막 `return` 앞에 `if kw == "CACHE": return has(r"^\s+(?:LAZY\s+)?TABLE\b")`.
확인: `parse_sql("CACHE LAZY TABLE tmp_a AS SELECT a FROM s.src")` → `kind` `create` · writes `tmp_a` · reads `s.src`, 그리고 `looks_like_sql("Cache the table please")` 는 거짓.
(6-3 · 6-4 의 코드는 이 저장소의 코드에 붙여 기존 테스트가 모두 통과하는 것을 확인했다.)

---

## 07 화면 규격

works 공통 디자인(원칙 일곱 가지 · 팔레트 · 아이콘 · 글자)은 [docs/DESIGN.md](../../docs/DESIGN.md) 가 정본이다. 이 절은 Flow–1 의 **자리 · 치수 · 색 자리**다. 색 **값**은 적지 않는다 — `ui.html` 의 `:root` 와 `flow1_graph.THEMES` 가 정본이고 둘이 같아야 한다 (`test_theme_values_match_ui`).

### 7-1 글자

- 글꼴: 내장 **GNU Unifont 15.1.01** 부분집합 `Flow1DOS` (`fonts/flow-1-dos.woff` · OFL). 16px · 줄 24px. 반각 8px · 전각(한글) 16px
- 굵게는 **도스식**: `text-shadow: var(--b)` (1px 옆에 한 번 더). SVG 는 `_text(…, bold=True)`. `font-weight` 는 쓰지 않는다 — Unifont 가 번진다
- 로고 `FLOW–1` 32px(2px 그림자) 뒤에 라임 `_` 커서 깜빡임 · LCD 의 파일 이름 24px(① 노브 색) · 작은 글 14px · 02 제목 20px
- 흐름도 글자 폭은 서버가 Unifont 와 **똑같이** 센다 (`flow1_graph.cw` — 폰트에서 뽑은 예외 표 포함). 새 기호를 쓰기 전에 `tests/test_graph.py` 의 `Measure` 에 그 글자의 칸 수를 더한다

### 7-2 틀 (px)

| 자리 | 치수 |
|---|---|
| 바탕 | 16px 점 격자 · `body` 바깥 여백 8 |
| 본체 `.device` | 둥근 18 · 1px 테두리 · 네 귀퉁이 나사 9 (귀에서 8) |
| 윗줄 `.bar` | 안쪽 10 24 8 · 간격 12 · 유량계 30×34 · LCD 둥근 10 (안쪽 그림자 · 주사선) · LED 8×8 · 전원 32 원 |
| 가운데 `.main` | 세 칸 **248 · 나머지 · 392** · 간격 8 · 좌우 12 |
| 구역 `.pane` | 둥근 12 · 1px 테두리 · 머리 40 높이(안쪽 8 12 · 번호 칩 + 영문 이름 굵게 + 한국어 설명) · 몸 안쪽 8 12 12 |
| 01 파일 줄 | 20 · 아이콘 칸 16 · 지금 파일은 왼쪽 3px ① 색 줄 |
| 00 흐름도 | `--fbg` 바탕 + 16px 점 격자 · 끌어서 옮기기 · 아래 실행 줄 20 |
| 02 자세히 | 이름 칸 64 + 값 · SQL 원문 16/20 · 실행 막대 8 폭 × 24 높이까지 |
| 아랫줄 `.deck` | 안쪽 10 24 8 · 노브 다이얼 44 원(아래 4px 받침 · 누르면 3px 내려감 · 눈금 4×13) · 버튼 높이 40 · 둥근 10 · 아래 4px 받침 |
| 맨 아래 `.foot` | 안쪽 5 24 8 · 16 줄 · `--ink-3` |
| 알림 · 서랍(04 RUNS) | 알림은 아래 112 · 서랍은 위 56 아래 112 · 2px `--card-edge` · 둥근 12 |
| 좁은 창 | 1100 이하: 파일 200 + 흐름도, 02 는 아래(높이 40vh) · 760 이하: 한 줄 (파일 30vh · 흐름도 60vh · LED · 값 칩 · 통계 숨김) |

### 7-3 색 자리 (토큰)

| 토큰 | 자리 |
|---|---|
| `--bg` · `--dot` · `--panel` · `--panel-2` | 바탕 · 점 격자 · 본체 · 구역 |
| `--ink` · `--ink-2` · `--ink-3` | 글자: 가장 밝음(강조 · 경고) · 보통 · 흐림 |
| `--line` · `--line-2` · `--hl` | 가는 선 · 굵은 선 · 올렸을 때 바탕 |
| `--prime` · `--prime-2` · `--prime-deep` · `--prime-ink` | 네이비: 번호 칩 · 막대 · 카드 머리 · 그 위 글자 |
| `--accent` · `--accent-ink` · `--accent-glow` · `--on-accent` | 라임: **지금 · 켜짐 · 진행 · 선택에만** |
| `--err` · `--err-ink` | 경고 칩 `ERR` = 가장 밝은 글자색 바탕 (빨강 없음) |
| `--k1` … `--k4` (+ `-ink` · `-edge`) | 노브 ① 파랑 ② 라임 ③ 흰색 ④ 회색. 값 칩 · LCD 파일 이름 · 지금 파일 표시도 그 노브 색 |
| `--btn` · `--key` | 기본 버튼(네이비) · 회색 키 버튼 |
| `--fbg` · `--card` · `--card-head` · `--card-edge` · `--num` · `--head-ink` · `--head-meta` · `--tbl` · `--edge` · `--bar` · `--pill` | 흐름도 — `THEMES` 와 **같은 값** |

새 색이 필요하면 hex 를 쓰지 말고 토큰을 더한다 — 다크(`:root`) · 라이트(`[data-theme="light"]` · `system` 의 라이트) **세 곳**에, 흐름도 색이면 `THEMES` 두 곳에도.

### 7-4 흐름도 치수 (`flow1_graph › 01 치수`)

| 이름 | 값 | 뜻 |
|---|---|---|
| `CELL` | 8 | 반각 한 칸 · 모든 좌표 · 크기는 8 의 배수 |
| `HEAD` | 24 | 카드 머리 |
| `ROW` | 20 | 카드 한 줄 (글자 16 + 위아래 2) · 글자 기준선 `BASE` 16 |
| `PAD` | 8 | 카드 아래 여백 (높이는 8 의 배수로 올림) |
| `LBL` | 64 | 줄 이름 칸 (왼쪽 여백 8 포함) — 글은 x = 64 에서 |
| `WIDTH` | 288 · 400 · 480 | 쿼리 카드 폭 (상세 1 · 2 · 3) |
| `OP_W` | 232 | 병합 카드 폭 |
| `PILL_H` · `PILL_MIN` · `PILL_MAX` | 24 · 96 · 320 | 알약 높이 · 폭 (글 폭 + 16, 8 의 배수) |
| `GAP_Y` · `GAP_X` · `TRACK` · `MARGIN` | 16 · 48 · 8 · 32 | 같은 열 노드 사이 · 열 사이 최소 · 간선 트랙 간격 · 가장자리 |
| `MAX_SELECT_ROWS` · `MAX_WHERE_ROWS` | 2 · 5 | 상세 2 에서 SELECT · WHERE 줄 수 |

카드 한 장:

```text
x 0        40    48                                              w
  ┌─────────┬────────────────────────────────────────────────────┐ 0
  │ Q03     │ df_items                        dq.query · L45     │ 머리 24 · 번호 칸 40 (--num) · 이름 굵게 · 오른쪽 meta (--head-meta)
  ├─────────┴────────────────────────────────────────────────────┤ 24
  │ SELECT  i.order_id, i.product_id, p.category,                │ 줄 20 · 이름 칸 64 (--ink-3) · 쉼표로 나눠 담고 넘치면 +n · 한 줄이 넘치면 …
  │         i.qty, i.price                                       │
  │ FROM    dw.order_items i                                     │ 테이블 이름 --tbl
  │ LEFT    dw.products p                                        │ 조인 줄: 이름 굵게 --ink · 테이블 선이 이 줄에 붙는다
  │ ON      i.product_id = p.product_id                          │
  │ WHERE   i.order_id IN ({order_ids})                          │ 자리 상자 1px --card-edge · 점선이 이 줄에 붙는다
  │ AND     i.qty > 0                                            │
  │ √ 1.2s · 12,340행                                            │ 실행 줄 (기록이 있을 때만) · 막대 --bar = 가장 느린 쿼리 대비
  └──────────────────────────────────────────────────────────────┘ + PAD 8
```

줄 이름 (`join_label`): 첫 항목 `FROM` · `INNER` → `JOIN` · `LEFT` · `RIGHT` · `FULL` · `CROSS` · `,` · `LEFT SEMI` → `SEMI` · `LEFT ANTI` → `ANTI` · `LATERAL` · `NATURAL` · `APPLY` · MERGE 의 `USING`. 쓰는 문장은 `INSERT` · `CREATE` · `UPDATE` · `DELETE` · `MERGE` · `DROP` · `TRUNC` 줄이 맨 위.

상세마다 보이는 줄:

| 줄 | 1 간단 | 2 보통 | 3 전부 |
|---|---|---|---|
| `VIA` · `DEF` (펼친 함수 경로 · 부르지 않은 함수) | — | — | ○ |
| `SQL n/m` (문장이 여럿일 때) · 쓰는 대상 줄 | ○ | ○ | ○ |
| `WITH 이름 ← 읽는 테이블` | — | — | ○ |
| `SELECT` | — | 2줄까지 · 별칭 우선 · 넘치면 `+n` | 전부 · `식 AS 별칭` |
| `FROM` · `JOIN` · `LEFT` … | ○ | ○ | ○ |
| `ON` · `USING` | — | 한 줄 (`AND` 로 이음) | 조건마다 한 줄 |
| `WHERE` · `AND` · `QUALIFY` | — | 5줄까지 + `+ 조건 n개 더` | 전부 |
| `GROUP` · `HAVING` · `ORDER` · `LIMIT` | — | ○ (HAVING 한 줄) | ○ (HAVING 조건마다) |
| 모르는 절 (`extra`) | — | — | ○ |
| `UNION` · `INTERSECT` · `EXCEPT` 가지 | ○ | ○ | ○ |

모양 (SVG class — 규칙은 `SVG_CSS` 한 곳, 화면과 내려받기가 같이 쓴다):

| 모양 | class | 그리는 법 |
|---|---|---|
| 쿼리 카드 | `n n-query` | `--card` 바탕 · 1px `--card-edge` · 머리 `--card-head` · 번호 칸 `--num` |
| SQL 을 모르는 카드 | `n-dyn` | 테두리 점선 4 3 |
| 병합 카드 | `n n-op` | 쿼리 카드와 같고 줄은 `L` · `R` · `+` 입력 + `INNER` · `LEFT` … · `CONCAT` |
| 테이블 알약 (읽기만) | `n-table n-pill` | `--pill` 바탕 · 1px `--ink-3` · 마지막 `.` 까지 흐리게 · 그 뒤 이름은 `--tbl` |
| 쓰는 테이블 (임시 · 끝) | `n-temp` | 점선 4 3 `--card-edge` |
| 파일 입력 · 출력 | `n-input` · `n-output` | 잔 점선 2 2 `--ink-3` · `read_csv · 경로` |
| 테이블 → 줄 · 데이터 흐름 | `e e-read` · `e e-df` | 1px `--edge` · 가로 · 세로만 |
| 테이블에 쓰기 | `e e-write` | 2px |
| 자리 흐름 | `e e-param` | 점선 4 3 |
| 선 끝 | `port` | 4×5 네모 `--card-edge` |
| 실행 줄 | `run-ok` · `run-busy` · `run-err` · `run-none` | `√ 시간 · 행` `--ink-2` · `◐` 라임 깜빡임 · `× 오류` 흰 칩 · `○ 기록 없음` |

배치 (`layout`): 층은 위상 순서의 가장 긴 경로 → 원천(읽기만 하는 테이블 · 파일)은 처음 쓰는 열 바로 앞 → 여러 열에서 읽으면 열마다 한 벌 → 긴 선은 층마다 더미 → 무게중심 쓸기 8번(교차 수가 **실제로 줄 때만** 받아들인다 — 아니면 코드 순서 = 위에서 아래) → 높이는 선이 곧게 가도록 PAVA 10번 → 8 에 맞추고 겹침을 민다 → 열 사이 트랙(`TRACK`)에서 꺾는다 (내려가는 선은 오른쪽 트랙부터).

### 7-5 움직임 · 반응

| 언제 | 무엇 |
|---|---|
| 카드에 올림 | 이어진 노드 · 선만 남고 나머지는 25% · 이어진 선은 라임 2px · 선 끝도 라임 |
| 누름 | 02 에 자세히 · 카드 테두리 라임 2px |
| 찾기 `/` | 맞는 카드 라임 점선 4 2 · 나머지 30% · Enter 로 다음 |
| ④ 강조 | JOIN: 조인 선 · 조인 줄만 · 병합 카드 라임 / 조건: 자리 선 · 자리 든 줄만 / 실행: 실행한 카드만 |
| 파일이 바뀜 | 다시 그림 (보던 자리 · 확대 유지) · 유량계 한 번 휘젓기 0.9초 |
| `--run` 중 | LED `run` 깜빡임 0.8초 · 카드 `◐` 깜빡임 · 유량계 떨림 · 폴링 1초 |
| 유량계 | 빈 화면 누움 · 평소 2.4초 흔들 · 성공 튐 · 실패 떨어져 흔들림 |
| 노브 | 누르면 3px 내려감 · 눈금이 튀며 돈다 0.18초 · 값 칩 = 노브 색 |
| 흐리게 · 강조 | 0.12초 전환 · `prefers-reduced-motion` 이면 모든 움직임을 끈다 |

키: `/` 찾기 · `[` `]` 앞 · 뒤 쿼리 · `+` `-` `0` 확대 · 맞춤 · `Ctrl+휠` · 끌어서 옮기기 · `R` 다시 읽기 · `Esc` 풀기 · `Alt+1–4` 노브 (Shift = 거꾸로).

### 7-6 눈으로 보는 합격

다크 · 라이트, 폭 1440 과 460 에서 본다 (`python tests/e2e_ui.py` 의 `shots/`).

| 볼 것 | 합격 |
|---|---|
| 색 | 빨강 · 노랑 · 자홍이 없다. 경고는 흰 `ERR` 칩. 라임은 지금 · 켜짐 · 선택 · 진행에만 |
| 모서리 | 흐름도 안(카드 · 알약 · 선)은 모두 각지다. 둥근 것은 본체 · 구역 · LCD · 버튼 · 노브뿐 |
| 선 | 가로 · 세로만 · 왼쪽 → 오른쪽 · 테이블 선은 그 테이블이 나오는 줄에 · 점선은 그 `{자리}` 가 든 줄에 |
| 격자 | 카드 · 알약의 x · y · 폭 · 높이가 8 의 배수 (`test_grid_and_no_overlap`) · 겹치지 않는다 |
| 글자 | 흐리지 않다 (16px · 반각 8) · 굵은 글자는 1px 겹쳐 찍은 모양 · 잘린 글은 `…` |
| 좁은 창 | 460 에서 가로 스크롤이 없다 |

---

## 08 바꾸면 안 되는 것

| # | 약속 | 까닭 | 지키는 것 |
|---|---|---|---|
| 1 | 사용자 코드를 **실행하지 않는다** — `import` · `exec` · `eval` 로 읽지 않는다. 실행은 사용자가 `--run` 을 줄 때만 | 흐름도를 보러 왔는데 DB 에 쓰면 사고다 | ast 만 · `test_handling_sql_text_is_not_running_it` |
| 2 | `127.0.0.1` 에만 연다 · 실행마다 새 토큰 · Host 확인 · 밖으로 나가는 요청 없음 · 폰트 내장 | [RULES.md](../../RULES.md) › W-03 | `Http.test_binds_localhost_and_guards` |
| 3 | SQL 원문 · 인자 값 · 결과 데이터 · 명령줄 인자 · 붙여 넣은 코드는 디스크에 쓰지 않는다. 오류 글의 비밀번호 꼴은 가린다 | W-04 · W-05 — SQL 에 고객 번호가 박혀 있을 수 있다 | `test_run_records_timing_rows_and_errors_but_no_sql_or_data` · `test_paste_is_memory_only` · `test_redact` |
| 4 | 저장은 `.tmp` 에 쓰고 `os.replace` · 설정 · 기록에 `version` | W-06 — 끄다가 죽어도 깨진 파일이 없다 | `write_json` |
| 5 | 실행은 표준 라이브러리만 · **Python 3.8** 에서 돈다 | W-02 — 사내 PC 의 파이썬이 오래됐을 수 있다 | CI 3.8 |
| 6 | `flow1_assets.py` 는 생성 파일 | 두 곳이 어긋난다 | `test_build_is_in_sync` · `build.py --check` |
| 7 | 흐름도 색 값: `ui.html` `:root` = `flow1_graph.THEMES` | 화면과 내려받은 SVG 가 같아야 한다 | `test_theme_values_match_ui` |
| 8 | `parse_sql` · `scan_text` · `scan_file` 은 예외를 밖으로 던지지 않는다 | 파일 하나 때문에 흐름도 전체가 멈추면 안 된다 | `test_never_raises_on_garbage` · `test_syntax_error_and_cp949` |
| 9 | 같은 입력 → 같은 출력 (순서까지) | 골든 · 캐시 · 사람의 기억 | `Golden.test_examples` · `test_well_formed_escaped_and_deterministic` |
| 10 | 색은 네이비 · 라임 · 회색 · 빨강 없음 | W-10 | `tools/works_check.py` |
| 11 | 8px 격자 · 반각 8 · 전각 16 (내장 Unifont 와 같게 센다) | 카드 크기 · 자르기를 서버에서 정확히 정한다 | `Measure` · `test_grid_and_no_overlap` |
| 12 | 선은 직각 · 왼쪽 → 오른쪽 · 테이블 선은 그 줄에 | 흐름도의 문법 | `test_edges_are_orthogonal_and_touch_node_sides` · `test_table_edges_land_on_their_join_rows` |
| 13 | 결과 dict 의 모양을 바꾸면 `FORMAT` 을 올린다 | `--json` 을 읽는 다른 도구 | — |
| 14 | 설정 키 이름을 바꾸지 않는다 (바꾸면 옛 키를 읽어 옮긴다) | W-09 | `Config` 테스트 |
| 15 | 포트 8785 (대장의 8785–8794 안) | 다른 works 앱과 겹치지 않게 | [docs/REGISTRY.md](../../docs/REGISTRY.md) |
| 16 | 사내 패키지 · 테이블 · 서버 이름은 이 공개 저장소에 커밋하지 않는다 (사내 사본 · 설정은 괜찮다) | W-12 | 사람의 눈 |
| 17 | `ui.html` 의 자리표시자 `__THEME__` · `__TOKEN__` · `__BOOT__` · `__SVGCSS__` 를 지우거나 바꾸지 않는다 · 안에 큰따옴표 세 개를 쓰지 않는다 | 서버가 실행마다 바꿔 넣고, `build.py` 가 파이썬 문자열로 묶는다 | `test_build_is_in_sync` · `Http` |
| 18 | 색 값은 `ui.html` 의 토큰 블록 세 곳(다크 · 라이트 · 시스템의 라이트)에만 · 시스템의 라이트 = 라이트 | 한 곳만 고치면 어느 한 테마에서만 옛 색이 남는다 | `test_colors_only_in_token_blocks` · `test_system_theme_repeats_light` |
| 19 | `innerHTML` 에는 고정 문구만 (값은 `el()` · `textContent`) | 파일 이름 · 경로에 든 태그가 토큰을 가진 창에서 스크립트로 돈다 | `test_inner_html_only_fixed_text` |
| 20 | 브라우저 E2E 가 찾는 id 를 지우거나 이름을 바꾸지 않는다 | 사내에서 못 돌리는 E2E 가 CI 에서만 깨진다 | `test_e2e_selectors_exist` |
| 21 | 내장 폰트 `fonts/flow-1-dos.woff` · `fonts/OFL.txt` 를 바꾸거나 지우지 않는다 | 흐름도 글자 폭(`cw`)이 이 폰트에 맞춰져 있다 · 라이선스 (W-12) | `Measure` · `tools/works_check.py` |

---

## 09 작업 절차

1. **재현** — 사용자가 준 코드에서 문제가 되는 모양만 남긴 짧은 코드를 만든다. 테스트 안의 문자열(`scan("""…""")`)로 둔다. 공개 저장소로 보낼 테스트면 사내 이름을 지어낸 이름으로 바꾼다
2. **지금 출력** — `python flow-1.py --scan 파일.py` (글) · `--json` (결과 dict). 틀린 것을 한 줄로 적는다: "Q03 의 LEFT 줄이 없다"
3. **테스트 먼저** — 모듈마다 테스트 파일이 하나다. 쓰고 나서 **지금 실패하는 것**을 확인한다

   | 고칠 모듈 | 테스트 | 모양 |
   |---|---|---|
   | `flow1_sql.py` | `tests/test_sql.py` | `p = fs.parse_sql("…")` → `p["stmts"][0]["select"]["sources"]` … |
   | `flow1_scan.py` | `tests/test_scan.py` | `r = scan("""…""")` → `r["queries"]` · `r["edges"]` … |
   | `flow1_graph.py` | `tests/test_graph.py` | `g = fg.build([r], 2)` → 노드 · 줄 · 간선 · 좌표 |
   | `flow1_trace.py` · `flow-1.py` | `tests/test_app.py` | 임시 데이터 폴더(`FLOW_HOME`) · 가짜 패키지 `tests/fake_pkg` |
   | `ui.html` | `tests/test_app.py` › `Assets` · `tests/e2e_ui.py` | 색 · id · `innerHTML` 가드 (문자열 검사) · Playwright |

4. **고친다** — [02](#02-코드-지도) 에서 구역을 찾아 그 구역만 읽는다. 한 번에 한 모듈 · 한 함수. 새 한도 · 이름은 모듈 위의 상수로 둔다
5. **전부 돌린다** — `python -m unittest discover -s tests`. 골든(`tests/golden/*.txt`)이 달라지면, 의도한 변화일 때만 다시 쓰고 **`git diff tests/golden` 을 한 줄씩** 본다. 의도하지 않은 줄이 하나라도 바뀌었으면 되돌리고 다시 고친다

   ```text
   bash        FLOW_GOLDEN_WRITE=1 python -m unittest tests.test_graph
   PowerShell  $env:FLOW_GOLDEN_WRITE=1; python -m unittest tests.test_graph; $env:FLOW_GOLDEN_WRITE=""
   ```

6. **화면을 고쳤으면** — [UI.md](UI.md) 의 레시피대로 → `python build.py` → `python build.py --check` → `python tests/ui_check.py shots` (Playwright 없이 사진 네 장 · [UI.md › 09](UI.md#09-확인)) → Playwright 가 있으면 `python tests/e2e_ui.py` → 문서 사진이 바뀌면 `python tests/e2e_ui.py --pages` (`docs/page/`)
7. **합격 기준** [01](#01-합격-기준) 을 전부 돌린다
8. **문서** — 사용자에게 보이는 것이 바뀌면 `docs/MANUAL.md`, 규칙이 바뀌면 이 문서의 그 절, 숫자가 바뀌면 README
9. **버전** — `flow-1.py` 의 `VERSION`: 고침은 셋째 자리 · 새 기능은 둘째 자리
10. **보고** — [11](#11-프롬프트-모음) 의 보고 틀로

---

## 10 자주 틀리는 것

| 틀린 것 | 결과 | 맞게 |
|---|---|---|
| `flow1_assets.py` 를 직접 고침 | 다음 `build.py` 에 덮이고 `--check` 가 실패 | `ui.html` 을 고치고 `python build.py` |
| Python 3.9+ 문법 — `ast.unparse` · `match` 문 · `str.removeprefix` · 사전 합치기 `a \| b` · 실행되는 `list[int]` · 괄호로 묶은 여러 `with` | 사내 PC(3.8)에서 문법 · 속성 오류 | `ast.get_source_segment` · if/elif · 자르기 · `{**a, **b}` · `typing.List[int]` |
| 쿼리 판정을 호출 이름만으로 (`if attr == "query"`) | `print(query)` · 남의 `query` 가 카드가 됨 | 4-2 의 순서 — 이름은 ②(설정한 패키지)에서만 본다 |
| `looks_like_sql` 을 느슨하게 (첫 낱말만) | 영어 문장 · UI 글이 카드가 됨 | 첫 낱말 + 짝 낱말 + 강함 (4-3) · `LooksLikeSql` 테스트에 영어 한 줄 |
| 테이블 키를 대소문자 그대로 | `DW.Orders` 와 `dw.orders` 가 알약 둘 | `key` 는 소문자, 보이는 이름은 `name` |
| 쓰고 다시 읽는 테이블을 한 노드로 | 순환 → 층을 못 나눔 | 이미 읽힌 판에 다시 쓰면 새 판 (`build` 안의 `table()`) |
| 읽기만 하는 테이블을 한 노드로 두고 멀리 이음 | 열을 가로지르는 긴 선 · 교차 | 열마다 한 벌 (`~L`). 02 는 벌을 합쳐 보여 준다 (`_table_detail`) |
| 새 색을 hex 로 씀 | 팔레트 밖 · 라이트 테마에서 안 보임 | 토큰 (7-3) |
| `font-weight: bold` | Unifont 가 번진다 | `text-shadow: var(--b)` · SVG 는 `bold=True` |
| 흐름도에 둥근 모서리 · 그림자 · 그라데이션 | works 디자인과 어긋남 | 각진 1px 선. 점선은 4 3 · 2 2 두 가지만 |
| 결과 dict 에 `set` · `tuple` · 객체 | `--json` · API 가 깨짐 | list · dict · str · int · bool (`test_result_is_json`) |
| 파서에서 예외를 던짐 | 그 파일 전체가 빈 흐름도 | 그 문장만 `kind: "other"` + `error` |
| 새 설정 키를 `DEFAULT_CONFIG` 에만 | 예시 파일 · 검사 · 문서와 어긋남 | `DEFAULT_CONFIG` + `validate_config` + `config.example.json` + MANUAL 설정 표 + `test_defaults_and_example_file_match` |
| 골든을 확인 없이 다시 씀 | 틀린 결과가 정답이 됨 | `git diff tests/golden` 을 한 줄씩 |
| 확인하려고 사용자 스크립트를 실행 | DB 에 쓰는 쿼리가 돈다 | `--scan` 만. 실행은 사용자가 `--run` 할 때만 |
| `--run` 기록에 SQL · 결과를 넣음 | 고객 정보가 디스크에 남는다 | 시간 · 행 수 · 열 수 · 오류 이름만 (08 의 3) |
| 사내 이름을 이 저장소의 코드 · 테스트 · 문서에 넣음 | 공개 저장소에 사내 정보 (W-12) | 설정 · 사내 사본에만. 테스트는 `demo_query` · 지어낸 테이블 |
| 모듈을 통째로 다시 씀 | 테스트가 지키던 동작이 조용히 사라짐 | 구역 하나 · 함수 하나씩 |

---

## 11 프롬프트 모음

사용자가 사내 LLM 에게 그대로 붙여 넣는 글이다. `<…>` 만 바꾼다. 경로는 [INSTALL.md](../INSTALL.md) 의 기본(`D:\OPENCODE`) 기준.

**11-1 설치**

```text
D:\OPENCODE\flow-1\INSTALL.md 를 처음부터 끝까지 읽고 그대로 설치해 줘.
4단계(사내 쿼리 패키지)는 데이터 추출 사내 스킬을 먼저 읽고 import 이름 · SQL 을 받는 함수 이름을 채워 줘.
[질문] 표시가 있는 곳에서만 나에게 묻고, 끝나면 --check 출력의 '자체 시험' 줄과 마지막 줄을 보여 줘.
```

**11-2 사내 패키지에 맞추기 (설치 뒤)**

```text
Flow–1 을 우리 데이터 추출 패키지에 맞춰 줘.
1) 사내 스킬에서 import 이름 · SQL(또는 .sql 경로)을 받는 함수 · 메서드 이름 · SQL 을 넘기는 인자 이름 ·
   SQL 안의 변수 문법 · 결과 모양을 뽑아 D:\OPENCODE\flow-1\docs\GUIDE.md 05 절 5-1 표 모양으로 보여 줘
2) 05 절대로 --set 으로 설정만 해 줘 (코드는 고치지 마)
3) 스킬의 예제 코드를 임시 파일로 두고 --scan 해서, 예제의 쿼리 호출 수와 카드(Qnn) 수가 같은지 보여 줘
4) <분석 폴더> 에서 파일 셋을 골라 --scan 하고 GUIDE 01 절 7번 표로 점검해 줘. 스크립트는 실행하지 마
```

**11-3 안 잡히는 · 잘못 잡힌 쿼리**

```text
<파일 경로> 의 <줄> 쿼리가 흐름도에서 <안 나온다 / 이렇게 틀린다: …>.
D:\OPENCODE\flow-1\docs\GUIDE.md 의 04 · 09 · 10 절을 읽고 09 절 절차대로 고쳐 줘.
설정으로 되는 일이면 설정만. 코드를 고치면 재현 테스트를 먼저 쓰고 실패를 보여 준 뒤 고치고,
01 절 합격 기준 1–4 결과를 보여 줘. 사용자 스크립트는 실행하지 마.
```

**11-4 SQL 방언**

```text
우리 SQL 의 <문법 — 예: CACHE TABLE · {{ ds }} · PREWHERE> 가 흐름도에서 깨진다. 예:
<SQL 한 문장>
D:\OPENCODE\flow-1\docs\GUIDE.md 06 절 표에서 고칠 곳을 찾아, tests/test_sql.py 에 이 문장 테스트를 먼저 더하고 고쳐 줘.
완전한 문법기로 바꾸지 말 것. 01 절 합격 기준 1–4.
```

**11-5 화면**

```text
Flow–1 화면에서 <무엇을 어떻게>.
D:\OPENCODE\flow-1\AGENTS.md · docs\UI.md · docs\GUIDE.md 07 · 08 절과 D:\OPENCODE\docs\DESIGN.md 를 먼저 읽어 줘.
UI.md 08 절에 맞는 레시피가 있으면 그대로. 색은 토큰만 (새 hex 금지), 굵게는 text-shadow.
python build.py → python -m unittest discover -s tests → python tests/ui_check.py shots.
사진 네 장을 UI.md 09 절 표로 점검한 결과와 사진 경로를 보여 줘.
```

**11-6 보고 틀** — 사내 LLM 이 일을 끝내면 이 모양으로 보고한다.

```text
## 무엇이 틀렸나      (증상 한 줄 · 재현 코드)
## 고친 곳            (파일 › 함수 · 설정이면 --set 줄)
## 더한 테스트        (파일 › 테스트 이름)
## 합격 기준          (01 절 1–7 · 각 명령의 마지막 줄)
## 남은 위험          (못 고친 것 · 사람이 확인할 것)
```

---

## 12 문제 해결

설치 · 실행 문제는 [INSTALL.md](../INSTALL.md) › 문제 해결. 여기는 **고치는 사람**의 표다.

| 증상 | 확인 | 고칠 곳 |
|---|---|---|
| `--scan` 에 쿼리가 0 | `--check` 의 `쿼리 패키지` · `찾는 호출` 줄 | [05](#05-사내-쿼리-패키지-맞추기) 설정 → 그래도면 5-4 |
| 카드가 너무 많다 (print · 로그 · UI 글) | 카드 머리의 부른 식 | `DENY_CALLS` 에 그 이름 · `query.calls` 좁히기 · `looks_like_sql` (4-3) |
| SQL 이 `{…}` 투성이 | `--json` 의 `params[].expr` | 다른 파일 · 실행 때 정해지는 값이면 정상. 같은 파일인데 모르면 4-4 표 밖 → `Scanner._expr` · `call` |
| 알약이 둘로 (`DW.ORDERS` · `dw.orders`) | `reads[].key` | 키는 소문자여야 — `Parser._source` |
| 선이 엉뚱한 줄에 붙는다 | 그래프 간선의 `tanchors` · 줄의 `anchor` | `statement_io` 의 `at` · `select_rows` 의 anchor · `ports` |
| 흐름도가 느리다 (수백 쿼리) | `test_big_graph_is_fast` · 노드 수 | 파일을 나눠 본다 · `MAX_NODES`. `layout` 의 쓸기(8) · PAVA(10) 횟수는 마지막 수단 |
| 노트북이 통째로 빈다 | `--scan` 의 `error` | JSON 이 깨졌거나 아주 옛 형식 — `notebook_cells` |
| `--run` 시간이 카드에 안 붙는다 | 기록 `calls[].tag` 와 카드의 `pos` | 스크립트를 고친 뒤면 다시 `--run` (자리가 바뀌면 안 이어진다). 스크립트 폴더 밖 모듈의 쿼리는 재지 않는다 |
| `--run` 행 수가 비었다 | 결과 객체에 `shape` · `len()` · `rowcount` | `flow1_trace.shape_of` |
| 창이 흰 화면 · 401 | `python flow-1.py --status` · 브라우저 콘솔 | 서버를 다시 켜면 토큰이 바뀐다 — 창을 새로 연다 |
| `build.py --check` 실패 | — | `python build.py` 를 돌리고 `flow1_assets.py` 도 같이 커밋 |
| 글자가 다른 글꼴로 보인다 · 칸이 어긋난다 | 그 글자가 내장 폰트 부분집합에 있는지 | 폰트에 있는 글자로 바꾼다. 새 글자가 꼭 필요하면 Unifont 15.1.01 에서 부분집합을 다시 뽑고(OFL 유지) `cw` · `Measure` 를 맞춘다 |

흐름도가 스파게티처럼 보이면, 대개 흐름도가 아니라 코드가 스파게티입니다.
