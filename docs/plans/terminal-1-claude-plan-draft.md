# Terminal–1 Claude 채널 기획서 (초안 1판)

- 상태: 기획 초안 1판 · 2026-11-05 · 코드 0줄. [Diode–1 기획서](diode-1-plan-draft.md) 4판의 Q10 에서 나왔다 — 사용자는 사내 Claude Code 를 Terminal–1 안에서 쓰면서 Diode–1 을 같이 쓰려 한다. Terminal–1 의 변경이므로 Diode–1 과 커밋 · 버전을 나눈다 (W-01 · S-08). 구현은 Terminal–1 폴더에서만 하고, Diode–1 과는 공개 명령 하나로만 잇는다.
- 표기: [문헌] 저장소 문서 · 공개 문서에서 읽은 것 · [미확인] 확인하지 못한 사실 · [제안] 근거 없이 정한 문턱.
- 번호: 여는 문턱 GT-1–GT-5 · 리스크 TR1–TR9 · 질문 TQ1–TQ3 · 작업 C1–C6. Diode–1 기획의 번호와 겹치지 않게 골랐다.
- 공개 저장소다 (W-12). 사내 Claude Code 의 명령 이름 · 경로 · 모델 이름은 적지 않는다. 이 PC 의 설정에만 둔다.

## 00 한 장 요약

- **무엇**: `terminal-1 add "<폴더>" -Claude` 로 **Claude 채널** 을 연다. 탭 하나에 사내 Claude Code 칸 · DIODE 칸 (Diode–1 상태) · 사용량 칸. 지금의 opencode 채널은 그대로다.
- **왜 새로 짜나**: 지금 Terminal–1 의 상태 · 입력 (compose) · 사용량 · 펫 칸은 모두 opencode 의 127.0.0.1 HTTP · SSE (`/session` · `/event` · `/tui/append-prompt` …) 를 본다 [문헌: MANUAL › 08 구조]. Claude Code 대화형에는 그런 HTTP 가 없다. 그래서 Claude 채널의 칸은 opencode 를 보지 않고, 숫자는 모두 Diode–1 공개 명령에서 받는다.
- **가장 중요한 규칙**: Claude 채널은 **Diode–1 이 방이라고 확인한 폴더에서만** 연다. 방이 아니면 안전벨트가 켜졌을 때만 경고와 `[질문]` 뒤에 연다. Diode–1 이 없거나 · 실패하거나 · 모르는 `format` 이면 Claude 채널 기능을 끈다 (02). 원자료가 있는 프로젝트 폴더에 Claude 채널을 여는 실수를 Terminal–1 이 먼저 막는다.
- **한계**: 이 문턱은 Terminal–1 로 열 때만이다. 다른 창에서 `claude` 를 직접 열면 Terminal–1 은 모른다 — 그 길은 Diode–1 안전벨트의 몫이다.

## 01 채널 모양

| 칸 | opencode 채널 (지금) | Claude 채널 (새) |
|---|---|---|
| 주 칸 | `opencode --port N` · headless 면 `opencode attach` | 사내 Claude Code 명령 (기본 `claude` · 이 PC 설정 — TQ2) · 작업 폴더 = 그 방 |
| 오른쪽 위 | status (세션 트리 · 할 일 · 허락 대기 · 로그) | DIODE — Diode–1 공개 명령을 몇 초마다 [제안: 5초] 읽어 보인다: 방 · 방 프로필 · 안전벨트 · outbox · inbox 대기 · 이번 달 사용 · 마지막 모델 · effort |
| compose | 큰 입력창 → opencode `/tui/append-prompt` | 없음 — Claude Code 대화형에 글을 넣을 API 가 없다. 봉인 글은 Diode–1 확정 창이 복사하거나 방 파일로 건넨다 |
| 아래 | usage · TOKEN QUEST | usage — Diode–1 이 방 statusLine 으로 받은 실제 사용량 (없으면 어림 표시를 그대로) · TOKEN QUEST 는 v1 에서 끔 (TQ1) |
| 포트 | 4096 부터 빈 포트 | 없음 |

- `ls` · `focus` · `rm` · `prune` · `00 overview` 가 Claude 채널을 안다. overview 의 인스턴스 표에 종류 칸 (`opencode` · `claude`) 을 더하고, 포트 칸은 `—`.
- Terminal–1 은 Claude Code 의 대화 기록 · 설정 · 자격 파일을 열지 않는다. Claude 채널에 보이는 숫자는 모두 Diode–1 공개 명령에서 온다.
- 모든 새 칸에 `?` 가이드와 `--once` 한 장 찍기 (S-04 터미널형).

### 채널 목록 파일

- 지금 `instances.json` 은 형식 버전이 없는 배열이다 [문헌: `terminal-1.ps1` › `Get-Reg`]. Claude 채널 항목 (`kind: "claude"` · 포트 · 주소 없음) 을 더하면 모양이 바뀐다.
- 그래서 C1 에서 형식 버전을 더하는 방법을 정한다 (W-06 · D-08): 새 판은 옛 배열을 읽어 옮기고, 옛 판이 새 파일을 만나면 덮어쓰지 않게. 이 판에서 처음 생기는 버전이라 옛 판 쪽 보호가 약하다 — 리스크 TR5.

## 02 여는 문턱

| # | 문턱 | 결과 |
|---|---|---|
| GT-1 | `add … -Claude` · `focus` 할 때마다 Diode–1 공개 명령 `diode-1.py --status --json --room "<폴더>"` 를 부른다 (제한 시간 [제안: 5초]) | — |
| GT-2 | `room` 이 방이고 방 프로필이 `ok` | 연다 |
| GT-3 | 방이 아니고 안전벨트가 켜짐 | 폴더 경로를 크게 보이고 "원자료가 있는 폴더면 여기서 멈추세요" 경고 → `[질문]` → 예면 연다. Diode–1 사내 마무리의 검토 세션 (`D:\OPENCODE\diode-1`) 이 이 길 |
| GT-4 | 방이 아니고 안전벨트가 꺼짐 · 모름 | 열지 않는다 |
| GT-5 | 명령 없음 · 실패 · 시간 초과 · 모르는 `format` · 방 프로필 `missing` · `changed` | 열지 않는다 — 그 까닭을 한 줄로 |

- W-01 은 "부르는 앱은 명령이 없거나 · 실패하거나 · 모르는 `format` 이면 그 기능만 끄고 계속 돈다" 고 한다. Claude 채널에서는 그 "기능만 끈다" 가 곧 막는 쪽 실패다. opencode 채널은 Diode–1 과 상관없이 그대로 돈다.
- `focus` 로 다시 열 때도 GT-1 부터 다시 한다 — 그 사이 방 프로필이 바뀌었을 수 있다.
- Diode–1 을 부르는 경로는 works 설치 자리 (`D:\OPENCODE\diode-1\diode-1.py` · W-08) 다. 대장 › 공개 명령에 `diode-1` 행 (쓰는 앱 `terminal-1`) 이 먼저 들어가야 한다 (Diode–1 작업 T11).

## 03 works 규칙

| 조항 | 이 변경에서 |
|---|---|
| W-01 | Diode–1 과는 공개 명령 하나로만 · Diode–1 코드 import · 데이터 파일 읽기 없음 |
| W-02 | 표준 라이브러리만 (지금과 같음) |
| W-03 | Terminal–1 은 Claude 채널에서도 밖과 통신하지 않는다. Claude Code 의 통신은 Claude Code 와 사내 설정의 몫 |
| W-04 | Claude Code 의 키 · 토큰을 다루지 않는다 |
| W-06 | `instances.json` 형식 버전 (01) · Claude 명령 설정 파일도 형식 버전 · 원자적 쓰기 |
| W-08 | 새로 남기는 것: Claude 명령 설정 파일 (데이터 폴더) → 대장 › PC 에 남기는 것 · INSTALL 제거 절 |
| W-10 | DIODE 칸은 DESIGN.md · Terminal–1 칸 문법 (폭 1칸 아이콘 · 세그먼트 숫자) · 빨강 없음 |
| W-11 | 가짜 Diode–1 명령 (`format` 1 · 모르는 `format` · 실패 · 시간 초과) · 가짜 wt 로 테스트 · README 테스트 수 |
| W-12 | 명령 이름 · 경로는 이 PC 설정에만 · 예시는 지어낸 것 |
| S-04 | 터미널형 — `?` 가이드 · `--once` |
| S-05 | PowerShell 5.1 · `.ps1` 은 CRLF · UTF-8 BOM |
| D-08 | 새 기능이라 `VERSION` 둘째 자리 · MANUAL · README 사양 · 테스트 수 |

## 04 리스크

| # | 리스크 | 줄이는 것 | 남는 것 |
|---|---|---|---|
| TR1 | 원자료 폴더에서 Claude 채널을 연다 | GT-1–GT-5 | Terminal–1 밖에서 연 `claude` → Diode–1 안전벨트 |
| TR2 | GT-3 의 `[질문]` 에 습관처럼 예 | 경로를 크게 · 경고 문구 · 방으로 여는 길을 먼저 권함 | 사람 |
| TR3 | DIODE 칸이 민감한 것을 보인다 (화면 공유 · 스크린샷) | Diode–1 공개 명령이 내주는 칸을 닫음 (Diode–1 T6 · T14) | 폴더 경로는 보인다 |
| TR4 | Windows Terminal 붙여넣기가 글자를 빠뜨려 봉인 글이 깨진다 [문헌: MANUAL › 알려진 한계] | Diode–1 이 그 글자를 쓰지 않음 · 토큰은 ASCII · Diode–1 U1 | — |
| TR5 | `instances.json` 형식 변경이 옛 판과 부딪힌다 (지금 형식 버전이 없음) | C1 에서 옮기기 · 읽기 전용 규칙 · 테스트 | 이미 깔린 옛 판이 새 파일을 만나는 첫 번 |
| TR6 | Claude 채널 항목이 opencode 를 가정한 코드 (status · usage · rpg · overview · 펫 이벤트) 를 깨뜨린다 | 종류 분기 · 모든 화면 스모크 테스트 | — |
| TR7 | 사내 Claude Code 명령이 `claude` 가 아니다 | 이 PC 설정 (TQ2) · `check` 가 명령이 있는지 봄 | — |
| TR8 | Diode–1 이 아직 없을 때 Claude 채널을 못 쓴다 | 의도한 동작 (막는 쪽 실패) · 안내 문구 | 불편 |
| TR9 | Terminal–1 이 무거워진다 | v1 은 칸 셋 · 펫 끔 | — |

## 05 질문

| # | 질문 | 선택지 (추천이 앞) |
|---|---|---|
| TQ1 | Claude 채널의 TOKEN QUEST | **v1 은 끔 · Diode–1 이 실제 사용량을 내주는 것을 확인한 뒤 v2 에서 Claude 토큰도 먹이로** · 처음부터 켬 |
| TQ2 | 사내 Claude Code 명령 이름 | **`terminal-1 claude-cmd "<명령>"` 로 이 PC 데이터 폴더에 한 번 (지금의 `company` 처럼)** · `add` 때마다 `-ClaudeCmd` |
| TQ3 | 방이 아닌 폴더 (GT-3) | **안전벨트가 켜졌을 때만 경고와 `[질문]` 뒤 연다** · 방에서만 연다 (사내 검토 세션도 방에서) |

## 06 작업표 (하위 에이전트용)

이 세션의 사용자 설정 (4단 모델 배정) 에 따른 작업표다. C2 · C3 는 Diode–1 의 공개 명령 (Diode–1 작업 T11) 이 대장에 오른 뒤에 머지한다. 구현 전에 `terminal-1/docs/MANUAL.md` › 개발 · `docs/GUIDE.md` · `terminal-1.ps1` 의 `add` · `Get-Reg` · `t1_monitor.py` 의 칸 모드를 끝까지 읽는다 (D-01).

```json
{
  "project_title": "Terminal–1 Claude 채널 — 사내 Claude Code 를 Terminal–1 에서 Diode–1 과 같이",
  "executive_summary": "Terminal–1 에 opencode 채널과 나란히 Claude 채널 (사내 Claude Code 칸 · DIODE 칸 · 사용량 칸) 을 더한다. Claude 채널은 Diode–1 공개 명령으로 방이라고 확인한 폴더에서만 열고, 방이 아니면 안전벨트가 켜졌을 때만 묻고 열며, Diode–1 이 없거나 모르는 format 이면 기능을 꺼 막는 쪽으로 실패한다. 칸의 숫자는 모두 Diode–1 에서 받고 Claude Code 의 파일은 열지 않는다.",
  "total_estimated_effort": 43,
  "tasks": [
    {"task_id": "C1", "task_name": "채널 종류 · 목록 파일 형식 명세", "description": "terminal-1.ps1 의 add · focus · rm · prune · ls · Get-Reg 와 t1_monitor.py 의 칸 모드를 끝까지 읽고, 채널 종류 (opencode · claude) 를 더하는 설계를 쓴다. instances.json 에 형식 버전을 더하는 방법 (옛 배열 읽어 옮기기 · 원자적 쓰기 · 더 새 판이면 읽기 전용) 과 claude 항목의 칸 (name · dir · kind · ch · color · created · 포트 없음), Claude 명령 설정 파일 형식, GT-1–GT-5 의 정확한 판정과 메시지, DIODE 칸이 읽을 Diode–1 공개 명령 format 1 의 칸을 명세로 적는다.", "tier": "Tier 1", "difficulty": "High", "effort_level": 6, "assigned_model": "claude-opus-5.5", "agent_role": "Logic_Developer", "expected_output": "설계 메모 (기획서 2판에 합칠 것) · 형식 · 판정 표", "dependencies": []},
    {"task_id": "C2", "task_name": "terminal-1.ps1 — add -Claude · 목록 · overview", "description": "add 에 -Claude 를 더해 주 칸에 이 PC 설정의 Claude Code 명령 (기본 claude) 을 그 폴더에서 열고, 오른쪽에 DIODE 칸 · 아래에 usage 칸을 두며 compose · 펫은 두지 않는다. claude-cmd 명령 (TQ2) 으로 명령 이름을 데이터 폴더에 저장한다. ls · focus · rm · prune · overview 가 종류를 알게 하고, instances.json 형식 버전을 C1 대로 옮긴다. PowerShell 5.1 · CRLF · UTF-8 BOM · 경로는 큰따옴표. 기존 opencode 채널 동작이 바뀌지 않는 테스트를 같이 넣는다.", "tier": "Tier 2", "difficulty": "Medium-High", "effort_level": 8, "assigned_model": "claude-sonnet", "agent_role": "Shell_Integration_Engineer", "expected_output": "terminal-1.ps1 변경 · 가짜 wt 실행 테스트", "dependencies": ["C1"]},
    {"task_id": "C3", "task_name": "여는 문턱 GT-1–GT-5", "description": "Diode–1 공개 명령을 제한 시간 안에 부르고 format 을 검사해 GT-2 연다 · GT-3 경고와 [질문] · GT-4 · GT-5 열지 않음을 가른다. 명령 없음 · 실패 · 시간 초과 · 모르는 format · 깨진 JSON · 방 프로필 missing · changed 를 모두 열지 않음으로 끝낸다. focus 때도 다시 검사한다. 가짜 Diode–1 명령 (정상 · 방 아님 · 안전벨트 꺼짐 · 모르는 format · 느림 · 실패) 으로 단위 테스트를 쓴다. 공개 명령은 Diode–1 작업 T11 이 대장에 올린 모양 그대로만 쓴다.", "tier": "Tier 1", "difficulty": "High", "effort_level": 7, "assigned_model": "claude-opus-5.5", "agent_role": "Security_Logic_Developer", "expected_output": "문턱 함수 · 가짜 명령 테스트", "dependencies": ["C1"]},
    {"task_id": "C4", "task_name": "DIODE 칸 · Claude 채널 usage 칸", "description": "t1_monitor.py 에 diode 모드를 더해 Diode–1 공개 명령을 몇 초마다 읽고 방 · 방 프로필 · 안전벨트 · outbox · inbox 대기 · 이번 달 사용 · 마지막 모델 · effort 를 Terminal–1 칸 문법 (세그먼트 숫자 · 폭 1칸 아이콘 · ? 가이드 · --once) 으로 보인다. usage 칸은 Claude 채널에서 Diode–1 이 준 실제 사용량 (어림이면 어림 표시) 을 보인다. Diode–1 이 실패하면 칸에 그 사실만 보이고 Claude 칸은 건드리지 않는다. 모든 화면 스모크 테스트에 Claude 채널을 더한다.", "tier": "Tier 2", "difficulty": "Medium-High", "effort_level": 8, "assigned_model": "claude-sonnet", "agent_role": "UI_Engineer", "expected_output": "t1_monitor.py 변경 · --once 스크린샷 · 테스트", "dependencies": ["C3"]},
    {"task_id": "C5", "task_name": "문서 · 설치 · 대장", "description": "MANUAL (Claude 채널 · 여는 문턱 · claude-cmd · 알려진 한계: Terminal–1 밖에서 연 claude 는 막지 못함) · README 사양과 테스트 수 · INSTALL (claude-cmd 를 [질문] 으로 · 제거 절에 설정 파일) · 대장 › PC 에 남기는 것 행을 고친다. VERSION 둘째 자리를 올린다. 숫자는 돌려서 얻은 값만.", "tier": "Tier 3", "difficulty": "Medium", "effort_level": 5, "assigned_model": "claude-sonnet", "agent_role": "Documentation_Specialist", "expected_output": "문서 변경 · works_check 새 경고 0", "dependencies": ["C2", "C4"]},
    {"task_id": "C6", "task_name": "통합 검증", "description": "원자료처럼 꾸민 합성 폴더에 Claude 채널 열기 · Diode–1 없음 · 모르는 format · 방 프로필 바뀜 · focus 재검사 · 옛 형식 instances.json · 더 새 형식 instances.json · Claude 명령 없음을 하나씩 일으켜 모두 열지 않거나 안전하게 끝나는지 본다. opencode 채널이 예전처럼 도는지, DIODE 칸에 사전 단어 · 봉인 글이 찍히지 않는지 본다. 결함마다 실패하는 테스트를 붙인다.", "tier": "Tier 0", "difficulty": "Extreme", "effort_level": 9, "assigned_model": "claude-opus-5.5", "agent_role": "Security_Integrity_Auditor", "expected_output": "검증 보고서 · 결함마다 실패하는 테스트", "dependencies": ["C5"]}
  ]
}
```
