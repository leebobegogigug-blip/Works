# Flow–1 — 고치는 에이전트 규칙

> **적용 범위.** 이 파일은 `flow-1/` 의 코드 · 문서를 **고치는** 작업에만 적용한다.
> Flow–1 설치(`INSTALL.md` 따라 하기) · 사용 · 다른 폴더의 작업 중이라면 이 파일을 무시하고 원래 지시를 따른다.

opencode 는 이 폴더에서 일하거나 이 폴더의 파일을 읽을 때 이 파일을 자동으로 붙인다.
works 전체 규칙은 [../AGENTS.md](../AGENTS.md) → [../RULES.md](../RULES.md) 가 정본이고, 여기는 **Flow–1 에만 있는 약속**이다.

## 00 먼저 읽을 것

| 하려는 일 | 읽을 곳 (끝까지) |
|---|---|
| 무엇이든 | 이 파일 → [docs/GUIDE.md › 00 읽는 법](docs/GUIDE.md#00-읽는-법) 표에서 할 일의 절 |
| 화면 · 색 · 글자 · 배치 · 문구 · 흐름도 모양 | [docs/UI.md](docs/UI.md) + [../docs/DESIGN.md](../docs/DESIGN.md) |
| 쿼리를 못 찾음 · 잘못 찾음 · SQL 방언 | GUIDE 04 · 05 · 06 · 09 · 10 |
| 사내 패키지 이름 넣기 | 코드가 아니라 설정이다 — GUIDE 05 |

## 01 절대 바꾸지 않는다

이것과 부딪히는 요청을 받으면 **하기 전에** 몇 번과 부딪히는지 사용자에게 말하고 멈춘다.
까닭과 지키는 테스트는 [GUIDE › 08](docs/GUIDE.md#08-바꾸면-안-되는-것).

1. **사용자 코드를 실행하지 않는다.** 분석은 `ast` 로 읽기만 한다. 확인도 `--scan` 으로만 (실행은 사용자가 `--run` 할 때만)
2. **로컬 서버 안전장치.** `127.0.0.1` 바인딩 · 실행마다 새 토큰(`<meta name="flow-token">` ↔ `X-Flow-Token`) · Host 검사 · 응답 헤더 `nosniff` · `DENY` · `no-referrer`. 밖으로 나가는 요청 · CDN · 웹 폰트 · 외부 이미지 없음
3. **디스크에 남기지 않는 것.** SQL 원문 · 인자 값 · 결과 데이터 · 명령줄 인자 · 붙여 넣은 코드. 저장은 `.tmp` 에 쓰고 `os.replace`
4. **`flow1_assets.py` 는 생성 파일.** 손대지 않는다. `ui.html` · `fonts/` 를 고친 뒤 `python build.py`
5. **`ui.html` 의 자리표시자** `__THEME__` · `__TOKEN__` · `__BOOT__` · `__SVGCSS__` 를 지우거나 이름을 바꾸지 않는다 (서버가 바꿔 넣는다). `ui.html` 안에 큰따옴표 세 개(`"""`)를 쓰지 않고, 파일이 역슬래시로 끝나지 않게 한다 (`build.py` 가 거부)
6. **색.** 새 hex · rgb 값을 쓰지 않는다 — 있는 토큰 `var(--…)` 만. 빨강 · 주황 · 노랑 · 보라 · 분홍 없음. 라임은 지금 · 켜짐 · 진행 · 선택에만 ([docs/UI.md › 03](docs/UI.md#03-색))
7. **글꼴.** `fonts/flow-1-dos.woff` · `fonts/OFL.txt` 를 지우거나 바꾸지 않는다. 다른 글꼴 · `font-weight` 굵게 금지 (굵게는 `<b>` · `text-shadow:var(--b)`)
8. **흐름도 문법.** 8px 격자 · 각진 모서리 · 가로 · 세로 선만 · 왼쪽 → 오른쪽 · 테이블 선은 그 테이블이 나오는 줄에
9. **이름과 자리.** 폴더 `flow-1` · 화면 이름 `Flow–1`(en dash) · 포트 8785 (대장의 8785–8794) · 데이터 폴더 `%LOCALAPPDATA%\flow-1` · 환경 변수 `FLOW_*` · 설정 키 이름 · 결과 dict 의 `FORMAT`. 바꿔야 하면 사람에게 먼저 ([RULES › W-09](../RULES.md#w-09-이름을-바꾸면-데려간다))
10. **Python 3.8 · 표준 라이브러리만** (실행 경로). 쓰면 안 되는 3.9+ 문법은 GUIDE › 10
11. **테스트를 지우거나 · 건너뛰거나 · 기대값을 느슨하게 해서** 통과시키지 않는다. 골든(`tests/golden/`)은 `git diff` 를 한 줄씩 보고 의도한 줄만 바꾼다
12. **사내 이름**(패키지 · 테이블 · 서버 · 회사 · 사람)은 공개 저장소로 가는 커밋에 넣지 않는다. 회사 이름은 설정 `company`, 사내 패키지는 설정 `query.*` 에

## 02 하나를 바꾸면 같이 바꾸는 곳

| 바꾸는 것 | 같이 바꿀 곳 | 빠뜨리면 잡는 것 |
|---|---|---|
| 색 토큰 값 · 새 토큰 | `ui.html` 의 세 블록 — 다크 `:root` · 라이트 `[data-theme="light"]` · 시스템의 라이트 `@media … [data-theme="system"]`. 흐름도 색이면 `flow1_graph.THEMES` 두 테마도 | `test_theme_values_match_ui` · `test_system_theme_repeats_light` · `test_colors_only_in_token_blocks` |
| 흐름도 모양 (SVG class) | `flow1_graph.SVG_CSS` 한 곳 (화면 · 내려받은 SVG 가 같이 쓴다). 올림 · 흐림 · 강조 반응만 `ui.html` 의 `.flow …` | 사진 · `--svg` |
| 흐름도 치수 상수 | 8 의 배수 · GUIDE 7-4 표 | `test_grid_and_no_overlap` · 골든 |
| 흐름도에 새 글자 · 기호 | 내장 폰트에 있는지 · `flow1_graph.cw` 칸 수 · `Measure` 테스트 | `python tests/ui_check.py glyphs "글자"` |
| 화면 요소의 id · class 이름 | `ui.html` 의 JS · `tests/e2e_ui.py` 선택자 · [docs/UI.md › 07](docs/UI.md#07-흐름도-svg-고치기) 의 SVG 이름 | `test_e2e_selectors_exist` (id) |
| JS 가 만드는 글 | 값(파일 이름 · 경로 · SQL)은 `el(태그, class, 글)` · `textContent` 로만. `innerHTML` 에는 고정 문구만 | `test_inner_html_only_fixed_text` |
| API 경로 · 응답 키 | `flow-1.py` 의 `make_handler` · `App` · `ui.html` 의 `api(…)` 부르는 곳 · GUIDE 02 API 표 | `tests/test_app.py` › `Http` |
| 설정 키 | `DEFAULT_CONFIG` · `validate_config` · `config.example.json` · MANUAL 설정 표 | `test_defaults_and_example_file_match` |
| `ui.html` · 폰트 | `python build.py` → `flow1_assets.py` 도 같이 커밋 | `build.py --check` · `test_build_is_in_sync` |
| 보이는 것 (문구 · 구역 · 키) | `docs/MANUAL.md` 의 화면 절 · 키 줄 · README 사양 표의 키 줄 | 사람 |
| 테스트 수 | README 의 두 곳 (사양 줄 · 사양 표) | `python ../tools/works_check.py` |
| 기능 · 고침 | `flow-1.py` 의 `VERSION` — 고침은 셋째 자리 · 새 기능은 둘째 자리 | — |

## 03 끝내기 전에 — 전부 통과해야 끝

`flow-1` 폴더에서. 자세한 합격 표는 [GUIDE › 01](docs/GUIDE.md#01-합격-기준).

```text
python build.py --check                 종료 코드 0
python -m unittest discover -s tests    마지막 줄 OK — Python 3.8 과 사내 최신 파이썬 둘 다
python flow-1.py --check                마지막 줄 "결과: OK"
python tests/ui_check.py shots          화면을 고쳤으면: "결과: OK" + 사진 네 장을 docs/UI.md › 09 표로 본다
python tests/e2e_ui.py                  Playwright 가 있을 때만: "E2E OK"
python ../tools/works_check.py          새 경고 없음
```

보고는 [GUIDE › 11-6](docs/GUIDE.md#11-프롬프트-모음) 틀로 한다. 돌리지 못한 확인은 돌리지 못했다고 쓴다.

## 04 사내 사본에서 고칠 때 — 업데이트와 부딪히지 않게

`D:\OPENCODE` 는 공개 저장소의 사본이다. [INSTALL.md › 업데이트](INSTALL.md#업데이트)의 `git pull --ff-only` 는 **고친 파일이 있으면 멈추고**, zip 을 덮어 풀면 고친 것이 **말없이 사라진다.** 그래서:

1. **처음 한 번** — 사내용 가지를 만든다: `git -C "D:\OPENCODE" checkout -b inhouse` (이미 있으면 `git -C "D:\OPENCODE" checkout inhouse`).
   zip 으로 받아 `.git` 이 없으면 고치기 전에 **[질문]** "업데이트 때 고친 것을 지키려면 git 으로 다시 받아야 합니다. 받을까요?"
2. **고칠 때마다 커밋** — `git -C "D:\OPENCODE" add flow-1` → `git -C "D:\OPENCODE" commit -m "flow-1: 무엇 · 무엇"`.
   커밋이 이름 · 메일이 없다고 멈추면 **[질문]** 으로 사용자에게 받는다. 사내 설정 값(패키지 이름 등)은 커밋하지 않고 `--set` 으로 넣는다 (데이터 폴더에 저장된다)
3. **업데이트** — `--ff-only` 대신 합친다:
   ```text
   python "D:\OPENCODE\flow-1\flow-1.py" --stop
   git -C "D:\OPENCODE" fetch origin
   git -C "D:\OPENCODE" merge origin/main
   ```
   부딪히면(conflict) — `flow1_assets.py` 는 아무 쪽이나 고른 뒤 `python build.py` 로 다시 만든다 · `tests/golden/*.txt` 는 GUIDE › 09 의 5번대로 다시 쓰고 diff 를 한 줄씩 본다 · 나머지는 **양쪽 뜻을 다 살려** 합친다 (모르면 **[질문]**). 그다음 03 을 전부 돌린다
4. `inhouse` 가지는 공개 저장소로 push 하지 않는다 (01 의 12)
