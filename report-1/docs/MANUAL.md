# Report–1 매뉴얼

근거 달린 주간보고 초안. 한 주 동안 남은 흔적(내 커밋 · 일정 · 한 줄 일지)을 모아 사내 LLM 이 초안을 쓰고, 줄마다 근거를 붙입니다.
소개는 [README](../README.md), 설치 절차는 [INSTALL.md](../INSTALL.md)에 있습니다.

- **파일 하나** — `report-1.py` 만 있으면 됩니다. 표준 라이브러리만 씁니다 (커밋을 읽을 때 git)
- **근거 없는 실적은 없다** — 실적 · 이슈 줄에 근거가 없으면 `ERR`, 확정할 수 없습니다. 사람이 고친 줄은 `직접`
- **내 PC 전용** — `127.0.0.1` 에만 열리고, 밖으로 나가는 통신은 설정한 LLM 주소뿐. 사내 LLM 에는 체크한 근거 줄만 보냅니다
- **저장은 둘뿐** — 적어 둔 일지와 확정한 보고서 (`%LOCALAPPDATA%\report-1\`). 초안은 메모리에만

## 설정 (`%LOCALAPPDATA%\report-1\config.json`)

| 키 | 설명 |
|---|---|
| `llm.*` | 사내 LLM — [works LLM 규격](../../docs/SPEC-llm.md) 과 같은 키. 비워 두면 기본 초안(규칙으로 묶기)만 |
| `sources.git.roots` | 커밋을 찾을 폴더 목록 (저장소 자체, 또는 저장소들이 들어 있는 폴더). `--set "sources.git.roots=C:\work;D:\proj"` |
| `sources.git.authors` | 내 커밋으로 칠 작성자 이메일. `git config user.email` (전역 · 저장소마다)은 저절로 들어갑니다 |
| `sources.git.depth` | `roots` 아래로 저장소를 찾을 깊이 (기본 2, 최대 4) |
| `sources.calendar.secretary` | Secretary–1 의 `secretary-1.py` 위치. 비우면 works 저장소 안의 것 · `sources.calendar.enabled` 로 끄기 |
| `sources.journal.enabled` | 일지를 근거로 쓸지 |
| `report.sections` | 양식의 세 칸 이름 (기본 `금주 실적` · `차주 계획` · `이슈 · 협조 요청`) · `report.max_lines` 칸마다 줄 수 |
| `theme` | `dark`(기본) · `light` · `system` |
| `port` | 기본 `8775` (대장의 8775–8784 안에서 빈 곳) |
| `idle_exit_min` | 창을 닫고 이만큼(분) 지나면 저절로 꺼짐. `0` 이면 안 꺼짐 (기본 30) |
| `user_name` | 초안을 쓸 때 부를 이름 |

전체 기본값은 [`config.example.json`](../config.example.json). 폴더는 `REPORT_HOME` 환경 변수로 바꿀 수 있습니다.

## 쓰는 법

1. 매일 — `오늘 한 일 ›` 에 한 줄 적고 Enter. 일지 근거(`n`)가 됩니다
2. 금요일 — **초안 만들기** (Ctrl+Enter). 왼쪽에서 빼고 싶은 근거는 체크를 풉니다 (사내 LLM 에도 안 갑니다)
3. 줄마다 근거 칩을 봅니다. 칩에 올리면 왼쪽의 근거 줄이 켜집니다. 고칠 줄은 눌러서 고치고, 필요 없는 줄은 `×`, 더할 줄은 `+ 줄`
4. **확정** (Ctrl+S) — 도장이 찍히고 보고서 글이 클립보드로 갑니다. 메일에 붙여 넣으면 끝. 20초 안에는 Ctrl+Z 로 되돌리기
5. `근거 붙이기` 를 켜고 확정하면 줄 끝에 `(api-server a1b2c3d)` 처럼 근거가 붙습니다

노브: ① 기간(이번 주 · 지난 주 · 최근 2주 · 이번 달) ② 상세도 ③ 어조(개조식 · 서술식) ④ 분량 — Alt+1~4, Shift 를 같이 누르면 거꾸로.
창 없이: `python report-1.py --draft` (`--period last` · `--basic`).

## 근거 규칙

| 칸 | 인정하는 근거 | 근거가 없으면 |
|---|---|---|
| 실적 | 이번 기간의 커밋 `c` · 일정 `e` · 일지 `n` | `ERR` — 확정 안 됨 |
| 계획 | 위 + 다음 기간 일정 `f` | `계획` (계획은 근거가 없어도 됨) |
| 이슈 | 위 + 다음 기간 일정 `f` | `ERR` |
| 사람이 고치거나 더한 줄 | 무엇이든 | `직접` — 확정할 수 있음 |

- 다음 주 일정(`f`)을 실적의 근거로 대면 인정하지 않습니다 (아직 안 한 일이니까요).
- 확정할 때 서버가 근거를 **다시** 판정합니다. 화면이 보낸 상태는 믿지 않습니다.
- 커밋은 작성자 이메일로 거릅니다. 저장소의 작성자 이메일을 모르면 그 저장소의 커밋은 **하나도** 가져오지 않습니다 — 남의 커밋이 내 실적에 섞이지 않게.

## 화면

| # | 구역 | 보여 주는 것 |
|---|---|---|
| 01 | **SOURCES** | 오늘 한 일 입력 · 커밋 · 일정 · 일지 · 다음 일정 (체크 = 초안 · LLM 에 씀) · 근거별 상태 |
| 02 | **DRAFT** | 세 칸 초안 · 줄마다 근거 칩 · `ERR` `직접` `계획` · 노브 값 칩 · 확정 도장 |
| 03 | **DECK** | 노브 네 개 · 근거 붙이기 · 되돌리기 · 초안 만들기 · 확정 |
| 04 | **지난 보고서** | 확정한 보고서 목록 · 다시 복사 |

## 디자인

works 공통 규격(원칙 일곱 가지 · 팔레트 · 아이콘)은 [docs/DESIGN.md](../../docs/DESIGN.md) 에 있습니다. Report–1 에서는 이렇게 보입니다.

| # | 원칙 | Report–1 에서 |
|---|---|---|
| 1 | **한 화면 = 한 모드** | 근거와 초안을 한 화면에, 값은 노브 네 개로 |
| 2 | **색 = 조작** | 노브 ①파랑 ②라임 ③흰색 ④회색 — 초안 칸 위의 값 칩도 그 색 · LCD 의 주차는 ① 기간의 색 |
| 3 | **번호 붙은 구역** | `01 SOURCES` · `02 DRAFT` · `03 DECK` · `04 지난 보고서` |
| 4 | **엔지니어링을 숨기지 않기** | 근거 id(`c3` `e1`) · 커밋 해시 · 근거별 상태 줄 · LED `git` `cal` `llm` · 모델 이름 |
| 5 | **즉각 반응** | 노브가 돌고, 근거 칩에 올리면 근거 줄이 켜지고, 확정에 도장 · 되돌리기 초읽기 |
| 6 | **사각 격자** | 점 격자 바탕 · 가는 선 · 두 자리 번호 |
| 7 | **캐릭터** | 결재판 얼굴 — 초안을 쓰는 동안 생각하고, 확정하면 뛰고, ERR 이면 떤다 |

경고는 빨강 대신 가장 밝은 글자색 칩(`ERR`)과 물결 밑줄로 합니다.

## 공개 명령

Report–1 은 공개 명령을 **부르기만** 합니다 ([대장 › 공개 명령](../../docs/REGISTRY.md#공개-명령)).

- 일정: `secretary-1.py --export-events --from … --to …` (형식 `1`) — 이번 기간과 다음 기간(계획용)을 한 번에 읽습니다.
  Secretary–1 이 없거나 · 실패하거나 · 모르는 형식이면 일정 없이 동작하고, 근거 상태 줄에 이유가 보입니다.

## 개발

| 할 일 | 명령 |
|---|---|
| UI 수정 | `ui.html` 수정 → `python build.py` (report-1.py 에 내장됨 · `INDEX_HTML` 을 직접 고치지 말 것) |
| 반영 확인 | `python build.py --check` (UI · 폰트 둘 다) |
| 테스트 | `python -m unittest discover -s tests` (표준 라이브러리만 · 진짜 git · 가짜 LLM · 가짜 Secretary–1) |
| 브라우저 E2E (선택 · CI 에서는 자동) | `pip install playwright` → `python -m playwright install chromium` → `python tests/e2e_ui.py` |
| 문서 사진 다시 찍기 | `python tests/e2e_ui.py --pages` (`docs/page/` 의 hero · title · err) |
| works 규칙 검사 | 저장소 루트에서 `python tools/works_check.py` ([RULES.md](../../RULES.md)) |

`tests/fake_llm_server.py` 는 OpenAI 호환 가짜 서버입니다 (근거대로 쓰기 · 지어내기 · 코드 울타리 · 엉터리 · 500 오류).
CI(`.github/workflows/report-1.yml`)는 Windows · Ubuntu × Python 3.8 · 3.13 에서 `build.py --check` 와 단위 테스트를, Ubuntu 에서 브라우저 E2E 를 돌립니다.

## 데이터

`%LOCALAPPDATA%\report-1\` 에 저장합니다. 저장소에는 들어가지 않습니다.

| 파일 | 내용 |
|---|---|
| `config.json` | 설정 (API 키가 들어 있을 수 있음) |
| `journal.json` | 오늘 한 일 일지 (Enter 로 적은 것만) |
| `reports\<기간>.json` | 확정한 보고서 — 글 · 줄 · 쓴 근거 (예: `2026-W39.json`) |

파일이 깨져 있으면 `.broken` 으로 백업하고 새로 시작합니다. 더 새 버전의 Report–1 이 쓴 파일이면 읽기만 합니다.

## 알려진 한계

- opencode 세션 기록은 아직 근거로 읽지 않습니다 (저장 형식이 공개 규격이 아니라서)
- 일정은 Secretary–1 을 거쳐서만 읽습니다. Outlook 일정은 Secretary–1 을 `outlook` 로 설정해 두면 들어옵니다
- 커밋 날짜는 커밋의 작성 시각(이 PC 시간대)으로 거릅니다. 60일보다 더 틀린 시계로 만든 커밋은 빠질 수 있습니다
- 클립보드 복사가 막힌 PC 면 `지난 보고서` 에서 글을 골라 직접 복사합니다

## 라이선스

내장 폰트는 [GNU Unifont](https://unifoundry.com/unifont/) 15.1.01 의 부분집합(Secretary–1 과 같은 파일)이고 SIL Open Font License 1.1 을 따릅니다 ([`fonts/OFL.txt`](../fonts/OFL.txt)).
