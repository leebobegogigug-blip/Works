# Terminal–1 Claude 채널 — 사내 작업 지침

- **누가 읽나**: 사내 PC 에서 Terminal–1 을 고치는 에이전트 (opencode 의 사내 LLM 또는 사내 Claude Code) 와 그 사람. 이 문서 하나로 시작해서 끝낼 수 있게 썼다.
- **선택이다**: Diode 는 Claude CLI 에 설치하는 플러그인이라 Terminal–1 없이 Claude CLI 만으로 돈다 ([Diode 기획서](diode-plan-draft.md) 7판). 이 지침은 사내에서 Terminal–1 안에 Claude CLI 를 열어 쓰고 싶을 때의 튜닝이다 — 하지 않아도 Diode 의 기능은 그대로다.
- **무엇**: Terminal–1 에 **Claude 채널** 을 더한다. 사람은 이 탭에서 사내 Claude Code 와 일하고, Claude 는 Diode 를 거쳐 짝지은 opencode 채널 (일꾼 · 원자료가 있는 프로젝트) 에 일을 넘긴다. Diode 의 설계는 [Diode 기획서](diode-plan-draft.md) 6판 › 07 › Claude 가 앞에서.
- **자리**: 구현은 사내에서 한다 (사용자 결정 · 2026-11-05). 이 지침은 공개 저장소에 있고, 사내 PC 는 works 저장소를 받아 이 파일을 읽는다.
- **정본 관계**: 규칙의 정본은 [RULES.md](../../RULES.md) · [DEVELOP.md](../DEVELOP.md) 다. 이 지침은 그 위에 **이 변경에만 있는 금지 · 같이 바꿀 곳 · 합격 기준** 을 더한다 (앱 `AGENTS.md` 와 같은 역할). 부딪히면 RULES.md 가 이긴다.
- **내력**: 기획 1–3판 (옛 이름 `terminal-1-claude-plan-draft.md`) 은 git 기록에 있다. 이 판에서 기획을 사내 작업 지침으로 바꿨고, 03 의 사실은 2026-11-05 의 이 저장소 코드에서 읽었다. 사내 PC 의 판이 다르면 C1 에서 먼저 맞춘다.
- **번호**: 사내 규칙 IH-1–IH-7 · 여는 문턱 GT-1–GT-6 · 합격 기준 AC-01–AC-18 · 작업 C1–C6 · 위험 TR1–TR12.

## 00 시작 프롬프트 — 그대로 붙여 넣는다

작업 세션은 `D:\OPENCODE\terminal-1` 에서 연다 (IH-1). 그다음 첫 마디로:

```text
works 저장소의 Terminal–1 에 Claude 채널을 더한다. 손대기 전에 AGENTS.md → RULES.md → docs/DEVELOP.md →
docs/plans/terminal-1-claude-guide.md (이 지침) 를 끝까지 읽어. 지침 › 01 의 사내 규칙 IH-1–IH-7 을 먼저 지켜.
고칠 곳은 terminal-1/ 폴더와 지침 › 06 의 같이 바꿀 곳뿐이야. 규칙과 부딪히면 하기 전에 조항 번호를 말하고 기다려.
할 일: 지침 › 08 의 C1 부터 차례로. 단계마다 › 09 의 합격 기준을 돌리고, 끝나면 › 10 의 틀로 보고해.
사내 이름 (명령 이름 · 모델 이름 · 사내 경로 · 회사 이름) 은 코드 · 테스트 · 문서 · 커밋에 쓰지 마. 키 · 비밀번호는 출력하지 마.
```

## 01 사내 규칙 — 이 지침의 헌법

| # | 규칙 | 까닭 |
|---|---|---|
| IH-1 | 작업 세션 (opencode · Claude Code) 은 `D:\OPENCODE\terminal-1` 에서만 연다. 저장소 루트 (`D:\OPENCODE`) · 원자료가 있는 프로젝트 폴더에서 열지 않는다 | 루트 아래에는 데이터를 프로그램 폴더에 두는 앱이 있다 (Secretary–1 · 예외 대장 W-06). 이 일은 공개 코드만 다룬다 |
| IH-2 | 사내 Claude Code 로 일하면 Diode 안전벨트가 있을 때 켠다. 없으면 사람이 원문 · 사내 화면을 붙여 넣지 않게 첫 마디에 알린다 | Claude 는 회사 밖 모델이다 |
| IH-3 | 사내 이름 — 사내 Claude Code 를 여는 명령 이름 · 모델 이름 · 사내 경로 · 회사 이름 · 동료 이름 — 은 코드 · 테스트 · 문서 · 커밋 메시지에 쓰지 않는다. 이 PC 의 데이터 폴더 설정에만 둔다 | W-12 (공개 저장소) |
| IH-4 | 테스트 · 예시 자료는 지어낸 것만 쓴다. 주소는 `127.0.0.1` · `example.com` | W-12 |
| IH-5 | 고친 것을 공개 저장소로 되가져갈 때는 사람이 diff 를 한 줄씩 본다 — IH-3 의 이름 · 사내 경로 · 사내 화면 스크린샷 (11) | W-12 |
| IH-6 | Diode 가 없거나 계약 (04-5) 대로 답하지 않으면 Claude 채널은 **열리지 않는 것이 정상** 이다. 열리게 하려고 문턱을 풀거나 우회 옵션을 만들지 않는다. 가짜 Diode 는 테스트에서만 쓴다 | 막는 쪽 실패 · 원자료 폴더에서 Claude 가 열리는 사고를 Terminal–1 이 먼저 막는다 |
| IH-7 | 키 · 비밀번호를 명령줄 · 로그 · 화면 출력 · 커밋에 남기지 않는다. opencode 의 비밀번호도 Claude 칸에 넘기지 않는다 | W-04 |

## 02 범위

- **만든다**: `add -Claude [-Worker]` · `claude-cmd` · Claude 채널 탭 배치 · 여는 문턱 (GT) · DIODE 칸 · Claude 탭 안의 일꾼 상태 칸 · `ls` · `focus` · `rm` · `prune` · `00 overview` 가 Claude 채널을 안다.
- **만들지 않는다**: Diode 자체 (별도 저장소) · Claude 칸에 글을 넣는 기능 · Claude 채널의 TOKEN QUEST · Claude Code 의 파일을 읽는 기능.
- **바꾸지 않는다**: opencode 채널의 동작 · `instances.json` 의 모양 (04-1) · 기존 명령의 출력 · 기존 테스트의 기대값.
- **정해 둔 것** (기획 3판 질문 TQ1–TQ4 의 추천 — 바꾸려면 사람이 정한다): Claude 채널의 펫은 끔 · 명령 이름은 `claude-cmd` 로 이 PC 에 한 번 · 방이 아닌 폴더는 안전벨트가 켜졌을 때만 질문 뒤 · 일꾼 opencode 채널은 보이는 탭으로 (headless 로 숨기지 않는다).

## 03 지금 구조 — 고치기 전에 읽을 곳

[문헌: 2026-11-05 이 저장소] 아래를 끝까지 읽고 시작한다 (D-01). 사내 판과 다르면 C1 에서 이 표부터 고친다.

| 파일 | 지금 | 이 변경과 닿는 곳 |
|---|---|---|
| `terminal-1.ps1` | 명령 `add` · `overview` · `ls` · `focus` · `rm` · `prune` · `setup` · `company` · `version` · `help` (`param` 의 `ValidateSet`) · Windows Terminal 탭 · 채널 목록 | `Get-InstanceTabArgs` — 주 칸 `cmd /k opencode --port N` · 오른쪽 `status` · 아래 `Get-BottomRow` (usage · rpg) · `compose` · `Get-Reg` · `Save-Reg` · `Get-FreeCh` · `Q()` (`;` 를 `\;` 로 · 끝의 `\` 를 겹침) · `Py()` (칸 명령 `cmd /k <Python> t1_monitor.py <모드> …`) · `Sync-PwFile` (새 탭은 이 셸의 환경을 물려받지 않는다 — 그래서 비밀번호는 파일로 넘긴다) · `company` 블록 (`settings.json` 을 **통째로** 다시 쓴다) · headless 의 `%` 경로 거부 |
| `t1_monitor.py` | 칸 모드 `status` · `overview` · `logs` · `usage` · `rpg` · `compose` (argparse `choices`) · `instances.json` 을 배열로 읽는다 (배열이 아니면 `[객체]`) | 새 모드 `diode` · overview 가 Claude 채널을 읽음 · status 칸의 job 표시 |
| `t1_term.py` | `VERSION = "1.1.0"` · `data_dir()` · `company()` (`settings.json` 의 `company` 만 읽음) · 디자인 부품 | VERSION · `claude_cmd` 읽기 |
| `tests/` | unittest. `test_ps1.py` 는 pwsh 가 있고 **Windows 가 아닐 때만** `terminal-1.ps1` 을 가짜 wt 로 실제 실행한다 (Windows 는 CI 에서 문법만) | 사내 Windows 에서는 PS 동작 시험이 건너뛰어진다 (07) |
| `docs/MANUAL.md` · `README.md` · `INSTALL.md` · `docs/GUIDE.md` | 사용자 문서 · README 의 테스트 수는 검사기가 본다 | 06 |

## 04 설계 — 정해 둔 것

### 04-1 Claude 채널 목록은 따로 된 파일에

- `%LOCALAPPDATA%\terminal-1\claude-channels.json` · `{"format": 1, "channels": [ … ]}`.
- 항목: `name` · `dir` (방) · `ch` (채널 번호) · `color` · `created` · `worker` (짝지은 opencode 채널 이름 · 없으면 `null`).
- 쓰기는 `.tmp` 에 쓴 뒤 바꿔치기 (지금 `company` 블록과 같은 방법). 읽다가 깨져 있으면 `.broken` 으로 옮기고 빈 목록. 더 새 `format` 이면 읽기만 하고 쓰지 않는다 (W-06).
- **왜 따로인가**: `instances.json` 은 형식 버전이 없는 배열이고, Python 쪽은 배열이 아니면 `[객체]` 로 읽는다. 모양을 바꾸면 지금의 opencode 칸들이 깨지고, 옛 판이 새 파일을 잘못 읽는다. 따로 된 파일이면 opencode 채널의 코드 · 파일은 그대로이고, 옛 판은 Claude 채널을 못 볼 뿐이다.
- 채널 번호 `ch` 와 이름은 **두 파일을 합쳐** 겹치지 않는다 (`Get-FreeCh` · 이름 검사가 둘 다 본다).
- `instances.json` 에 형식 버전이 없는 것 자체는 이번 범위 밖이다 — 보고 › 남은 위험에 적는다.

### 04-2 명령

| 명령 | 하는 일 |
|---|---|
| `terminal-1 add "<방>" -Claude [-Worker <opencode 채널 이름>] [-Name <이름>]` | 04-4 문턱 → 통과하면 Claude 채널 탭을 연다 |
| `terminal-1 claude-cmd ["<명령>"]` | 사내 Claude Code 를 여는 명령을 이 PC 에 저장한다. 인자가 없으면 지금 값을 보이고, `-` 는 지운다 (기본 `claude`) |
| `terminal-1 ls` | 종류 칸 (`opencode` · `claude`) · Claude 채널은 포트 `—` · 짝지은 일꾼 이름 |
| `terminal-1 focus <이름>` | Claude 채널이면 04-4 를 처음부터 다시 한다 |
| `terminal-1 rm <이름>` · `prune` | Claude 채널은 목록에서만 지운다 (멈출 서버가 없다). `prune` 은 방 폴더가 없어진 Claude 채널을 지운다 |

- `-Claude` 는 `-Headless` · `-Port` 와 같이 쓰지 않는다 → 사용법 오류 · 종료 코드 2 (S-03).
- 방 경로에 `%` 가 있으면 거부한다. 주 칸이 cmd 를 거치므로 `%이름%` 이 펼쳐진다 (지금 headless 가 거부하는 까닭과 같다).

### 04-3 `claude-cmd` 저장

- 같은 `settings.json` 의 `claude_cmd` 키에 둔다.
- **지금 `company` 블록은 파일을 통째로 다시 써서 다른 키를 지운다.** `company` 와 `claude-cmd` 둘 다 "읽고 → 고칠 키만 바꾸고 → 나머지 키를 지켜 원자적으로 쓴다" 로 고친다 (같은 커밋). `version` 은 1 그대로다 — 키를 더할 뿐이고 읽는 쪽 (`t1_term.company()`) 은 모르는 키를 무시한다.
- 검증: 200자 이하 · 제어 문자 없음 · `;` `&` `|` `<` `>` `^` `%` `"` 없음 (wt 는 `;` 를 하위 명령 구분으로 읽고, cmd 는 나머지를 해석한다). 저장 전에 `Get-Command` 로 찾아보고, 못 찾으면 저장은 하되 경고한다.
- 값은 비밀이 아니라 화면에 보여도 되지만, 사내 이름이라 테스트 · 문서 · 커밋에 쓰지 않는다 (IH-3). 테스트는 지어낸 이름 (`fake-claude`) 을 쓴다.

### 04-4 여는 문턱 (GT)

| # | 조건 | 결과 | 종료 코드 |
|---|---|---|---|
| GT-1 | `add -Claude` · Claude 채널 `focus` 때마다 Diode 상태 명령 (04-5) 을 부른다. 제한 시간 5초 [제안] | — | — |
| GT-2 | `room.is_room` 이 `true` 이고 `room.profile` 이 `ok` | 연다 | 0 |
| GT-3 | `room.is_room` 이 `false` 이고 `seatbelt` 가 `on` | 방 경로를 크게 보이고 "원자료가 있는 폴더면 여기서 멈추세요" → `[질문]` (기본 아니오) → 예면 연다 | 예 0 · 아니오 3 |
| GT-4 | `room.is_room` 이 `false` 이고 `seatbelt` 가 `on` 이 아님 | 열지 않는다 | 1 |
| GT-5 | 명령 없음 · 실행 실패 · 시간 초과 · JSON 깨짐 · `format` 이 1 이 아님 · 필수 칸 없음 · 필수 칸에 모르는 값 · `room.profile` 이 `missing` · `changed` | 열지 않는다 · 까닭 한 줄 (Diode 출력은 찍지 않는다) | 1 |
| GT-6 | `-Worker` 가 없음 · 그 이름의 opencode 채널이 없음 · 그 채널 주소가 `127.0.0.1` 이 아님 | Claude 채널은 연다 · 일꾼 없이 (DIODE 칸에 '일꾼 없음') | 0 |

- 입력이 리디렉션된 비대화 실행에서 GT-3 은 아니오로 본다.
- 판정은 함수 하나 (예: `Test-ClaudeGate`) 에 모으고, 결과 객체 (`open` · `reason` · `code`) 를 돌려준다. 테스트는 이 함수를 직접 본다.
- 이 문턱은 Terminal–1 로 열 때만 막는다. 다른 창에서 `claude` 를 직접 열면 Terminal–1 은 모른다 — 그 길은 Diode 안전벨트의 몫이다 (MANUAL › 알려진 한계).

### 04-5 Diode 상태 명령 — 계약 (format 1)

- **부르기**: `<Python> "D:\claude\diode\diode.py" --status --json --room "<방>"`. `<Python>` 은 칸을 띄울 때 쓰는 그 값 (`$Python` — `py -3` 또는 `python`).
- **Diode 자리는 고정한다**: `D:\claude\diode\diode.py` (사용자 결정 · Diode 의 설치 폴더 `D:\claude` — [Diode 기획서](diode-plan-draft.md) › 07 › 자리). `terminal-1.ps1` 위쪽의 상수 하나 (예: `$DiodePy`) 로만 두고, 설정 · 환경 변수 · 명령 인자로 바꾸지 않는다 — 가짜 Diode 가 늘 '방' 이라고 답하게 만드는 손잡이를 없앤다 (TR10). 테스트는 문턱 함수 (`Test-ClaudeGate`) 를 직접 부르며 가짜 Diode 경로를 **함수 인자** 로 넘긴다. `add` · `focus` 는 언제나 상수를 넘긴다 — 그 인자는 명령줄에 드러나지 않는다.
- **출력**: 표준 출력에 UTF-8 JSON 하나.

```json
{
  "format": 1,
  "tool": "diode",
  "room": {"is_room": true, "profile": "ok"},
  "seatbelt": "on",
  "worker": {"set": true, "reachable": true},
  "queue": {"confirm": 0, "outbox": 0, "inbox": 0},
  "jobs": [{"job": "J-0007", "state": "working"}],
  "month": {"pct": 12, "estimated": false},
  "last": {"effort": "high"}
}
```

- **필수 칸**: `format` · `room.is_room` · `room.profile` · `seatbelt`. 나머지는 없으면 DIODE 칸에 `—`.
- **값**: `room.profile` ∈ `ok` · `missing` · `changed` · `seatbelt` ∈ `on` · `off` · `unknown` · `jobs[].state` ∈ `sent` · `working` · `reported` · `rejected` · `month.pct` 0–999 · `last.effort` ∈ `low` · `medium` · `high` · `xhigh` · `max` · `auto`. 필수 칸에 모르는 값이면 GT-5, 나머지 칸이면 `—`.
- **모르는 키는 무시한다** (Diode 가 칸을 더해도 깨지지 않게). 뜻이 바뀌면 Diode 가 `format` 을 올리고, Terminal–1 은 모르는 `format` 이면 GT-5 다.
- 출력은 화면에만 쓰고 로그 · 파일에 남기지 않는다. 출력에는 사전 단어 · 봉인 글 · 답 · 모델 이름이 없다 (Diode 쪽 약속 — Diode 기획 T6 · T11).
- **job 표시 약속**: Diode 허브는 일꾼에 넣는 지시의 첫 줄을 `[diode J-0007]` 꼴로 시작한다 (Diode 기획 T18). 일꾼 상태 칸은 세션의 첫 사용자 메시지가 이 꼴이면 그 세션에 `DIODE J-0007` 표시를 단다 — 바깥 지시에서 온 일이라는 것을 사람이 허락하기 전에 안다 (TR11).
- 이 계약은 Diode 기획 T6 · T11 · T18 의 입력이다. 바꾸려면 두 문서를 같이 고치고 `format` 을 올린다.

### 04-6 Claude 채널 탭 배치

| 칸 | 명령 |
|---|---|
| 주 칸 | `cmd /k set "DIODE_WORKER_URL=http://127.0.0.1:<일꾼 포트>" && <claude_cmd>` · 작업 폴더 `-d <방>`. 일꾼이 없으면 `set` 없이 |
| 오른쪽 | `Py 'diode' "--room <방> --name <이름> --color <색>"` (새 모드 · 04-7) |
| 아래 | 일꾼이 있으면 `Py 'status' "--url <일꾼 url> --name <일꾼 이름> --color <일꾼 색> --reg-dir --since <일꾼 created>"` — 지금의 status 모드를 일꾼 포트로 띄운다. 세션 트리 · 할 일 · 허락 대기 칩이 그대로 보인다 |

- `DIODE_WORKER_URL` 은 Diode 플러그인 설정의 `worker_url` 보다 앞선다 — Terminal–1 이 짝지은 일꾼을 그 탭에서만 쓰게 한다. 넘기지 않으면 Diode 는 자기 설정의 주소를 쓴다.
- 새 탭은 이 셸의 환경을 물려받지 않으므로 (`Sync-PwFile` 의 주석) 일꾼 주소는 명령줄로 넘긴다. 주소는 비밀이 아니다. `set "…"` 의 따옴표가 `Q()` · wt 를 지나 그대로 남는지는 C2 에서 가짜 wt 로 확인하고, Windows 에서는 손 점검표 (09) 로 본다 [제안].
- **비밀번호는 넘기지 않는다** (IH-7). Diode 허브는 opencode 의 `OPENCODE_SERVER_PASSWORD` 를 자기 환경에서 읽거나 Diode 자기 설정의 참조로 받는다 — Terminal–1 의 `server-password` 파일을 Diode 가 읽지 않는다 (W-01 의 뜻).
- compose 칸 · 펫 칸은 두지 않는다. 사용량 칸도 따로 두지 않는다 — 이번 달 사용은 DIODE 칸에 있다.
- 탭 제목은 `<ch> <이름> CLAUDE` (지금의 `:포트` 자리에). 탭 색은 팔레트에서.

### 04-7 DIODE 칸 — `t1_monitor.py diode`

- 5초마다 04-5 를 부른다 (제한 시간 5초 · 앞 호출이 끝나기 전에는 겹쳐 부르지 않는다).
- 보이는 것: 방 (`OK` · `MISSING` · `CHANGED`) · 안전벨트 (`ON` · `OFF`) · 일꾼 (연결 · 없음) · 확정 대기 · outbox · inbox · 일 목록 (최근 5) · 이번 달 % (어림이면 앞에 `~`) · effort.
- Diode 가 실패하거나 모르는 `format` 이면 칸에 `DIODE —` 와 까닭 번호만 보인다. 이미 열린 Claude 칸은 건드리지 않는다 — 다음 `focus` 때 문턱이 다시 본다.
- `?` 가이드 · `--once` 한 장 찍기 · 폭 1칸 아이콘 · 세그먼트 숫자 · 빨강 없음 (DESIGN.md · Terminal–1 칸 문법 · S-04).

### 04-8 overview · ls

- overview 의 인스턴스 표에 Claude 채널 줄을 더한다 — 종류 `CLAUDE` · 포트 `—` · 방 상태는 DIODE 칸과 같은 값 (overview 가 채널마다 Diode 를 부르지 않게, 마지막으로 읽은 값을 칸끼리 나누는 지금의 `poll-*.json` 방식을 따른다 [제안]).
- 펫 목장 · 주간 레이드에는 Claude 채널을 넣지 않는다 (v1 펫 끔).

## 05 하지 말 것

- opencode 채널의 동작 · `instances.json` 의 모양 · 기존 명령의 출력 · 기존 테스트의 기대값을 바꾸기.
- Claude Code 의 대화 기록 (`~/.claude/projects` · `transcript_path`) · 설정 · 자격 파일을 읽기.
- Claude 칸에 글을 넣기 — SendKeys · 클립보드 자동 붙여 넣기 · wt 입력 흉내. 다른 창으로 샐 수 있고, 봉인 글은 Diode 가 건넨다.
- Diode 자리를 설정 · 환경 변수 · 인자로 받기 · Diode 코드를 복사하기 · Diode 의 데이터 파일을 읽기.
- 문턱을 푸는 옵션 (`-Force` · "Diode 없이 열기" 등) 을 만들기 (IH-6).
- 비밀번호를 Claude 칸 명령줄 · 로그 · 화면에 넣기 (IH-7).
- 사내 이름을 코드 · 테스트 · 문서 · 커밋에 쓰기 (IH-3).
- 테스트 건너뛰기 · 기대값 느슨하게 하기 · 검사기나 워크플로를 고쳐 통과시키기 (D-02 · D-07).

## 06 같이 바꿀 곳 (D-08)

| 바꾸는 것 | 같은 커밋에서 같이 |
|---|---|
| 새 기능 | `t1_term.py` 의 `VERSION` 1.1.0 → 1.2.0 (새 기능 = 둘째 자리 · PR 하나에 한 번) |
| 명령 · 옵션 · 칸 | `docs/MANUAL.md` (02 기능 · 03 화면 · 05 사용법 · 08 구조 · 10 알려진 한계 — Terminal–1 밖에서 연 `claude` 는 막지 못함 · 사내 Windows 에서는 PS 동작 시험이 건너뛰어짐) · `docs/GUIDE.md` (commands · layout) · README 사양 줄 |
| 테스트 수 | README 의 테스트 수 — 돌려서 얻은 값 (검사기가 본다 · W-11) |
| PC 에 남기는 것 | `docs/REGISTRY.md` › PC 에 남기는 것의 `terminal-1` 줄에 `claude-channels.json` · `settings.json` 의 `claude_cmd` · `INSTALL.md` 제거 절 |
| 설치 | `INSTALL.md` 에 `claude-cmd` 를 `[질문]` 단계로 — 사내 명령 이름은 사람에게 묻는다 |
| 저장 파일 | `claude-channels.json` format 1 (새로) · `settings.json` version 1 그대로 (키만 더함 · `company` 쓰기 고침) |

## 07 사내에서 못 도는 시험 — 미리 알 것

- `test_ps1.py` 는 Windows 에서 건너뛰어진다 (`os.name != "nt"` 조건). 사내 Windows PC 에서는 `terminal-1.ps1` 의 동작 시험 (가짜 wt 로 탭 인자 확인) 이 돌지 않는다.
- 그래서:
  1. 문턱 판정 (`Test-ClaudeGate`) · 탭 인자 만들기 · JSON 읽기는 작은 함수로 두고, 같은 판정 규칙을 Python 쪽 (`t1_monitor.py` 의 계약 읽기) 에서도 unittest 로 확인한다.
  2. 사내에 WSL 이나 pwsh 가 있는 리눅스가 있으면 `PWSH` 환경 변수로 `test_ps1.py` 를 돌린다.
  3. 없으면 09 › 손 점검표를 사람이 Windows 에서 하고, 보고에 "test_ps1 은 사내에서 못 돌림 · 손 점검표로 대신함" 이라고 쓴다 (D-09). CI 는 공개 저장소에 올라갔을 때만 돈다.
- `test_ps1.py` 를 Windows 에서도 돌게 바꾸는 것은 이번 범위 밖이다 — 남은 위험에 적는다.

## 08 순서

| 단계 | 할 일 | 확인 | 실패하면 |
|---|---|---|---|
| C1 | 03 의 파일을 끝까지 읽고, 03 의 사실이 사내 판과 맞는지 본다. 다르면 이 지침의 03 · 04 에서 고쳐야 할 줄을 적어 사람에게 보인다 | 다른 곳 목록 (없으면 `없음`) | 다른 곳이 04 의 설계를 흔들면 멈추고 묻는다 (D-02) |
| C2 | `terminal-1.ps1` — `claude-channels.json` 읽기 · 쓰기 (04-1) · `claude-cmd` 와 `company` 의 settings 쓰기 고침 (04-3) · `add -Claude -Worker` · `ls` · `focus` · `rm` · `prune` (04-2) · 탭 배치 (04-6). PowerShell 5.1 · CRLF · UTF-8 BOM · 경로는 큰따옴표 | AC-01–AC-06 · AC-12–AC-15 | 기존 opencode 채널 테스트가 하나라도 깨지면 되돌리고 다시 |
| C3 | 여는 문턱 (04-4) 과 계약 읽기 (04-5) — 가짜 Diode 로 테스트 (정상 · 방 아님 · 안전벨트 꺼짐 · 모르는 format · 깨진 JSON · 느림 · 실패 · profile missing · changed) | AC-07–AC-11 | 문턱을 풀어서 통과시키지 않는다 (IH-6) |
| C4 | `t1_monitor.py` — `diode` 모드 (04-7) · overview 의 Claude 줄 (04-8) · status 칸의 `DIODE J-…` 표시 (04-5) · 모든 화면 스모크 테스트에 Claude 채널 | AC-16 · AC-17 | Diode 실패가 Claude 칸이나 다른 칸을 멈추면 고친다 |
| C5 | 06 의 같이 바꿀 곳 전부 · `VERSION` | AC-18 · `works_check` 새 경고 0 | — |
| C6 | 09 전부를 다시 · 손 점검표 · 10 의 보고 | 10 의 틀 | 실패는 출력 그대로 보인다 |

## 09 합격 기준

| # | 기준 | 어떻게 |
|---|---|---|
| AC-01 | 지금의 테스트가 모두 통과하고 개수가 줄지 않는다 | `py -3 -m unittest discover -s tests` |
| AC-02 | opencode 채널의 `add` · `ls` · `focus` · `rm` · `prune` 출력과 탭 인자가 바뀌지 않는다 | 가짜 wt (test_ps1) · 손 점검표 |
| AC-03 | `instances.json` 은 바이트 하나 바뀌지 않는다 (Claude 채널만 있는 동안) | 테스트 |
| AC-04 | `claude-channels.json` — 원자적 쓰기 · 깨지면 `.broken` · 더 새 format 이면 쓰지 않음 | 테스트 |
| AC-05 | 채널 번호 · 이름이 두 파일을 합쳐 겹치지 않는다 | 테스트 |
| AC-06 | `company` 를 써도 `claude_cmd` 가 남고, 그 반대도 같다 | 테스트 |
| AC-07 | Diode 가 없으면 `add -Claude` 가 열지 않고 종료 코드 1 | 가짜 Diode 없음 |
| AC-08 | 모르는 format · 깨진 JSON · 필수 칸 없음 · 5초 넘김 · profile `missing` · `changed` → 열지 않음 · 종료 코드 1 | 가짜 Diode 여섯 가지 |
| AC-09 | 방이 아니고 안전벨트가 켜짐 → 질문 · 아니오 (그리고 비대화) 면 열지 않고 종료 코드 3 | 테스트 |
| AC-10 | Claude 채널 `focus` 는 문턱을 다시 지난다 — 그 사이 방 프로필이 바뀌면 열지 않는다 | 테스트 |
| AC-11 | Diode 자리는 상수 `D:\claude\diode\diode.py` 로만 정해진다 — 설정 · 환경 변수 · 명령 인자로 바뀌지 않고, 가짜 경로는 테스트가 문턱 함수에 직접 넘길 때만 쓰인다 | 코드 검토 · 테스트 |
| AC-12 | 주 칸 명령줄에 비밀번호가 없다 (`OPENCODE_SERVER_PASSWORD` 를 설정한 상태에서도) | 가짜 wt 인자 검사 |
| AC-13 | 일꾼 주소는 `http://127.0.0.1:<포트>` 꼴만 넘어간다 · 일꾼이 없으면 `set` 이 없다 | 가짜 wt 인자 검사 |
| AC-14 | `-Claude` 와 `-Headless` · `-Port` 를 같이 주면 종료 코드 2 · 방 경로의 `%` 는 거부 | 테스트 |
| AC-15 | `claude-cmd` 는 04-3 의 글자를 거부하고, 지어낸 명령 이름으로만 테스트한다 | 테스트 · `grep` 으로 사내 이름 없음 |
| AC-16 | DIODE 칸 — Diode 실패 · 모르는 format 에서 `DIODE —` 만 보이고 칸이 멈추지 않는다 · `--once` 한 장 | 테스트 · `--once` |
| AC-17 | 일꾼 상태 칸이 `[diode J-0007]` 로 시작하는 세션에 표시를 단다 · 그 밖의 세션에는 달지 않는다 | 가짜 opencode 응답 테스트 |
| AC-18 | `python tools/works_check.py` 새 경고 0 · README 테스트 수가 돌린 값과 같다 | 저장소 루트에서 |

**손 점검표 (사내 Windows · test_ps1 대신)** — 지어낸 폴더 · 지어낸 명령으로 한다.

1. Diode 를 설치하기 전에 `terminal-1 add "<지어낸 방>" -Claude` → 열리지 않고 까닭 한 줄 · 종료 코드 1.
2. Diode 를 설치하고 (`D:\claude\diode`) `/diode:room` 으로 방 (`D:\claude\room`) 을 만든 뒤 `terminal-1 add "D:\claude\room" -Claude` → Claude 탭 · 오른쪽 DIODE 칸 · compose · 펫 없음. (1 은 Diode 를 설치하기 전에 한다 — 진짜 Diode 자리에 가짜를 두지 않는다.)
3. `-Worker <opencode 채널>` 로 다시 → 아래에 일꾼 status 칸 · Claude 칸에서 `echo %DIODE_WORKER_URL%` 가 `http://127.0.0.1:<포트>`.
4. 작업 관리자 · `wmic process get commandline` 등으로 Claude 칸 명령줄을 보고 비밀번호가 없음을 확인 (값은 화면에 찍지 않는다 — 있으면 '있음' 만 적는다).
5. 기존 opencode 채널 `add` · `ls` · `focus` · `rm` 을 한 번씩 → 예전과 같다.
6. `terminal-1 company "x"` 뒤 `terminal-1 claude-cmd` 가 지운 적 없는 값 그대로인지.

## 10 보고 틀

[DEVELOP.md › D-11](../DEVELOP.md#d-11-보고는-한-모양으로) 의 여섯 칸에 사내 칸 둘을 더한다. 칸을 빼지 않는다 — 없으면 `없음`.

```text
## 한 일          한 줄 · terminal-1
## 고친 곳        파일 › 함수
## 테스트         더하거나 바꾼 테스트 이름 · 돌린 개수
## 검사           AC-01–AC-18 마다 결과 · works_check 마지막 줄 그대로 · 못 돌린 것은 못 돌렸다고 (test_ps1 등)
## 부딪힌 조항    W · S · IH 번호와 고른 길
## 남은 위험      못 한 것 · 사람이 볼 것 · 보이는 김에 발견한 것
## 사내 이름 확인  git diff 에서 IH-3 의 이름을 찾았는가 — 찾은 개수 (이름은 적지 않는다)
## 되가져가기     공개 저장소로 갈 diff 인가 · 사내에만 둘 것은 무엇인가
```

## 11 공개 저장소로 되가져가기

- 사내에서 고친 Terminal–1 코드는 사내 이름이 없는 일반 코드다. 공개 저장소로 되가져가려면 사람이 diff 를 한 줄씩 본다 (IH-5): 사내 명령 이름 · 모델 이름 · 사내 경로 · 회사 이름 · 동료 이름 · 사내 화면이 찍힌 스크린샷 · 실제 일정 · 대화가 없는가.
- 되가져가는 길은 공개 저장소의 작업 가지와 PR 이다 (D-10 · `main` 에 바로 push 하지 않는다 · 머지는 사람이). 회사가 사내 PC 에서 GitHub 로 올리는 것을 막고 있으면, 사내에만 두고 공개 저장소는 그대로 둔다 — 그 판단은 사람이 한다.
- 되가져가면 CI 가 Windows · Ubuntu 에서 `test_ps1.py` 까지 돌린다. 사내에서 못 돌린 시험은 그때 처음 돈다.

## 12 알고 갈 위험

| # | 위험 | 줄이는 것 | 남는 것 |
|---|---|---|---|
| TR1 | 원자료 폴더에서 Claude 채널을 연다 | GT-1–GT-6 | Terminal–1 밖에서 연 `claude` → Diode 안전벨트 |
| TR2 | GT-3 의 질문에 습관처럼 예 | 경로를 크게 · 경고 문구 · 기본 아니오 | 사람 |
| TR3 | DIODE 칸이 민감한 것을 보인다 (화면 공유 · 스크린샷) | 계약의 칸이 닫혀 있다 (04-5) | 방 경로는 보인다 |
| TR4 | Windows Terminal 붙여넣기가 글자를 빠뜨려 봉인 글이 깨진다 [문헌: MANUAL › 알려진 한계] | Diode 가 그 글자를 쓰지 않음 · 토큰은 ASCII | — |
| TR5 | `instances.json` 에 형식 버전이 없다 | 이번에는 모양을 바꾸지 않는다 (04-1) | 다음 변경 때 |
| TR6 | Claude 채널이 opencode 를 가정한 코드 (status · usage · rpg · overview · 펫 이벤트) 를 깨뜨린다 | 따로 된 파일 · 종류 분기 · 모든 화면 스모크 | — |
| TR7 | 사내 Claude Code 명령이 `claude` 가 아니다 | `claude-cmd` · `Get-Command` 경고 | — |
| TR8 | Diode 가 아직 없을 때 Claude 채널을 못 쓴다 | 의도한 동작 (IH-6) · 안내 문구 | 불편 |
| TR9 | 사내 Windows 에서 PS 동작 시험이 돌지 않는다 | 07 · 손 점검표 | CI 에 올리기 전까지 |
| TR10 | 가짜 Diode 가 늘 '방 ok' 라고 답한다 (자리 바꿔치기) | 상수 하나로 고정 · 설정 손잡이 없음 (04-5) | 같은 계정이면 `D:\claude\diode` 의 파일 자체를 바꿀 수 있다 — 그 저장소의 `git status` 로 사람이 본다 |
| TR11 | 사람이 일꾼의 허락 요청을 습관처럼 허락한다 — 바깥 지시에서 온 일이다 | `DIODE J-…` 표시 (04-5) · Diode 의 넘기기 확정 | 사람 |
| TR12 | 일꾼 주소 명령줄이 바꿔치기된다 | Diode 허브가 127.0.0.1 만 받는다 · 바뀌어도 안쪽의 다른 opencode 일 뿐 바깥으로 가지 않는다 | — |

## 13 작업표 (하위 에이전트용)

이 세션의 사용자 설정 (4단 모델 배정) 에 따른 작업표다. `assigned_model` 은 급을 뜻한다 — 사내에서는 사내가 정한 같은 급의 Claude 모델로 읽는다 (이름은 사내 설정 · IH-3). 사용자의 방침 (Claude 토큰은 기획 · 검토에) 에 따라 구현 단계 (C2 · C4 · C5) 는 사내 LLM (opencode) 이 맡고 사내 Claude 는 판단 · 검토 단계 (C1 · C3 · C6) 를 맡아도 된다 — 고르는 것은 사람이다. 어느 쪽이든 IH-1–IH-7 을 지킨다.

```json
{
  "project_title": "Terminal–1 Claude 채널 — 사내 작업 (Claude 가 일하는 자리 · opencode 는 짝지은 일꾼 · Diode 와 같이)",
  "executive_summary": "사내 PC 에서 Terminal–1 에 Claude 채널을 더한다. 채널 목록은 따로 된 파일에 두어 opencode 채널과 instances.json 을 건드리지 않고, Claude 채널은 D:\\claude\\diode 에 설치된 Diode 의 상태 명령 (format 1 계약) 이 방이라고 확인할 때만 열며 그 밖은 막는 쪽으로 실패한다. 사내 이름은 이 PC 설정에만 두고, 사내 Windows 에서 돌지 않는 PS 동작 시험은 손 점검표로 대신해 보고한다.",
  "total_estimated_effort": 43,
  "tasks": [
    {"task_id": "C1", "task_name": "사내 판 확인", "description": "작업 세션을 D:\\OPENCODE\\terminal-1 에서 열고 (IH-1) AGENTS.md · RULES.md · DEVELOP.md · 이 지침을 끝까지 읽은 뒤, 지침 03 에 적힌 사실 (명령 목록 · Get-InstanceTabArgs 의 칸 · Q() · Sync-PwFile · company 블록이 settings.json 을 통째로 씀 · t1_monitor.py 의 모드 · instances.json 을 배열로 읽음 · VERSION · test_ps1 의 Windows 건너뜀) 이 사내 판과 같은지 하나씩 확인한다. 다르면 지침 03 · 04 에서 고칠 줄과 까닭을 적어 사람에게 보이고, 04 의 설계를 흔드는 차이면 멈추고 묻는다.", "tier": "Tier 1", "difficulty": "High", "effort_level": 5, "assigned_model": "claude-opus-5.5", "agent_role": "Codebase_Auditor", "expected_output": "사내 판과 지침의 차이 목록 (없으면 없음) · 고칠 줄 제안", "dependencies": []},
    {"task_id": "C2", "task_name": "terminal-1.ps1 — 채널 파일 · 명령 · 탭 배치", "description": "지침 04-1 대로 claude-channels.json (format 1 · 원자적 쓰기 · .broken · 더 새 format 은 읽기만) 을 읽고 쓰는 함수를 더하고, Get-FreeCh · 이름 검사가 두 파일을 합쳐 보게 한다. 04-3 대로 settings.json 쓰기를 '읽고 고칠 키만 바꾸고 나머지를 지켜 원자적으로' 로 고쳐 company 와 claude-cmd 가 서로 지우지 않게 하고, claude-cmd 명령 (검증 · Get-Command 경고) 을 더한다. 04-2 대로 add -Claude -Worker · ls · focus · rm · prune 을 Claude 채널에 맞게 하고 (-Headless · -Port 와 같이 쓰면 종료 코드 2 · 방 경로의 % 거부), 04-6 대로 주 칸 (DIODE_WORKER_URL 은 127.0.0.1 만 · 비밀번호 없음) · 오른쪽 diode 칸 · 아래 일꾼 status 칸을 만든다. instances.json 과 opencode 채널의 동작 · 출력은 바꾸지 않는다. PowerShell 5.1 · CRLF · UTF-8 BOM · 경로는 큰따옴표. 테스트 자료 · 명령 이름은 지어낸 것만 (IH-3 · IH-4).", "tier": "Tier 2", "difficulty": "Medium-High", "effort_level": 9, "assigned_model": "claude-sonnet", "agent_role": "Shell_Integration_Engineer", "expected_output": "terminal-1.ps1 변경 · 테스트 (AC-02–AC-06 · AC-12–AC-15)", "dependencies": ["C1"]},
    {"task_id": "C3", "task_name": "여는 문턱 · Diode 계약 읽기", "description": "지침 04-4 의 GT-1–GT-6 을 함수 하나 (Test-ClaudeGate · 결과 객체 open · reason · code) 로 만들고, 04-5 의 계약 (format 1 · 필수 칸 · 값 범위 · 모르는 키 무시 · 모르는 format 은 GT-5 · 제한 시간 5초 · 출력은 화면에만) 대로 Diode 상태 명령을 부르고 읽는다. Diode 자리는 상수 D:\\claude\\diode\\diode.py 하나로 두고 설정 · 환경 변수 · 명령 인자로 받지 않는다 (AC-11). 문턱 함수에 가짜 Diode 경로를 함수 인자로 넘기는 테스트로 정상 · 방 아님 · 안전벨트 꺼짐 · 모르는 format · 깨진 JSON · 느림 · 실패 · profile missing · changed · focus 재검사를 본다. 같은 판정 규칙을 Python 쪽 계약 읽기에도 두어 사내 Windows 에서도 unittest 로 돈다 (지침 07). 문턱을 푸는 옵션은 만들지 않는다 (IH-6).", "tier": "Tier 1", "difficulty": "High", "effort_level": 7, "assigned_model": "claude-opus-5.5", "agent_role": "Security_Logic_Developer", "expected_output": "문턱 함수 · 계약 읽기 · 가짜 Diode 테스트 (AC-07–AC-11)", "dependencies": ["C1"]},
    {"task_id": "C4", "task_name": "t1_monitor.py — DIODE 칸 · overview · job 표시", "description": "지침 04-7 대로 diode 모드를 더해 5초마다 (겹쳐 부르지 않게) Diode 상태 명령을 읽고 방 · 안전벨트 · 일꾼 · 대기 수 · 일 목록 · 이번 달 % · effort 를 Terminal–1 칸 문법 (세그먼트 숫자 · 폭 1칸 아이콘 · ? 가이드 · --once · 빨강 없음) 으로 보인다. Diode 실패 · 모르는 format 이면 DIODE — 와 까닭 번호만 보이고 칸이 멈추지 않게 한다. 04-8 대로 overview 의 인스턴스 표에 Claude 채널 줄을 더하되 펫 목장 · 레이드에는 넣지 않는다. 04-5 의 job 표시 약속대로 status 칸이 [diode J-0007] 로 시작하는 세션에 DIODE J-0007 표시를 단다. 모든 화면 스모크 테스트에 Claude 채널을 더한다.", "tier": "Tier 2", "difficulty": "Medium-High", "effort_level": 8, "assigned_model": "claude-sonnet", "agent_role": "UI_Engineer", "expected_output": "t1_monitor.py 변경 · --once 한 장 · 테스트 (AC-16 · AC-17)", "dependencies": ["C3"]},
    {"task_id": "C5", "task_name": "같이 바꿀 곳 · 문서", "description": "지침 06 의 표를 모두 한다: VERSION 1.2.0 · MANUAL (02 · 03 · 05 · 08 · 10 알려진 한계 둘) · GUIDE.md commands · layout · README 사양 줄과 테스트 수 (돌려서 얻은 값) · INSTALL 의 claude-cmd [질문] 단계와 제거 절 · REGISTRY › PC 에 남기는 것의 terminal-1 줄. 사내 이름 · 사내 화면 스크린샷을 넣지 않는다.", "tier": "Tier 3", "difficulty": "Medium", "effort_level": 5, "assigned_model": "claude-sonnet", "agent_role": "Documentation_Specialist", "expected_output": "문서 변경 · works_check 새 경고 0 (AC-18)", "dependencies": ["C2", "C4"]},
    {"task_id": "C6", "task_name": "통합 검증 · 보고", "description": "지침 09 의 AC-01–AC-18 을 모두 다시 돌리고, 사내 Windows 에서는 손 점검표 1–6 을 사람과 함께 한다. 원자료처럼 꾸민 지어낸 폴더에 Claude 채널 열기 · Diode 없음 · 모르는 format · 방 프로필 바뀜 · focus 재검사 · 비밀번호가 명령줄에 없는지 · 기존 opencode 채널이 예전 그대로인지 · DIODE 칸에 민감한 칸이 없는지를 본다. git diff 에서 IH-3 의 사내 이름을 찾아 개수만 적는다. 결함마다 실패하는 테스트를 붙이고, 지침 10 의 틀로 보고한다 (못 돌린 시험은 못 돌렸다고).", "tier": "Tier 0", "difficulty": "Extreme", "effort_level": 9, "assigned_model": "claude-opus-5.5", "agent_role": "Security_Integrity_Auditor", "expected_output": "지침 10 틀의 보고 · 결함마다 실패하는 테스트", "dependencies": ["C5"]}
  ]
}
```
