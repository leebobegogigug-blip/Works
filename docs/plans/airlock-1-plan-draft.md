# Airlock–1 기획서 (초안 1판)

- 상태: 기획 초안 1판 · 2026-11-05 · 앱 코드 0줄 · 이름은 가칭 (Q3). 대장 ([REGISTRY.md](../REGISTRY.md)) 에는 아직 올리지 않았다 — 자리 (Q2) 와 이름 (Q3) 이 정해지면 코드 없는 등록 커밋을 먼저 낸다 (S-06).
- 무엇: 사내 LLM (opencode) 과 회사 밖 모델 (Claude) 을 같이 쓰되, **원자료가 Claude 쪽으로 한 글자도 가지 않게** 둘 사이에 문 하나를 두는 도구. Claude 는 기획 · UI/UX 초안만 맡고, 원자료를 만지는 일은 전부 사내 LLM 이 한다.
- 전제: 이 도구를 쓰는 곳은 "원자료가 회사 밖 모델에 가면 법적 책임이 생기는 자료" 를 다룬다. 실수 한 번이 사고다. 그래서 이 기획서는 편의보다 **새지 않음** 을 앞에 둔다.
- 표기: [문헌] 공개 문서에서 읽은 것 (Claude Code 문서는 2026-11-05 에 읽음) · [미확인] 확인하지 못한 사실 — M0 에서 잰다 · [추정] 계산하거나 늘린 값 · [제안] 근거 없이 정한 문턱 (M0 결과로 고친다).
- 번호: 새는 길 L-01–L-17 · 불변식 AL-01–AL-12 · 나가는 검사 D1–D8 · 들어오는 검사 U1–U5 · 목표 G1–G6 · 정찰 KIT-1–KIT-6 · 리스크 R1–R14 · 질문 Q1–Q8 · 마일스톤 M0–M5 · 작업 T1–T15. [DEVELOP.md](../DEVELOP.md) 의 D-01–D-11 과 헷갈리지 않게 나가는 검사는 하이픈 없이 `D1` 로 쓴다.
- 공개 저장소다 (W-12). 사내 모델 이름 · 사내 주소 · 예산 액수 · 회사가 어떤 법의 적용을 받는지는 이 문서에 적지 않는다. 사용자 설정에만 둔다.

## 00 한 장 요약

- **답부터**: 된다. 다만 "가렸다가 보내고, 돌아오면 되돌린다" 그대로는 안 된다. 이름 · 식별자는 가려지지만, 지켜야 할 기술의 본체 (공정 조건 · 수치 · 구조 · 순서) 는 가려도 **뜻이 남는다**. 그래서 원칙을 바꾼다 — **가린 원자료를 보내는 게 아니라, 원자료가 필요 없는 일만 Claude 에게 준다.** Claude 가 받는 것은 사내 단어 · 숫자 · 파일 · 그림 · 코드 원문이 없는 **일의 모양** (brief) 이다.
- **모양 (05 · Q1)**: opencode + 사내 LLM 이 지휘하고 원자료를 쥔다 (안쪽). Claude 는 도구가 하나도 없는 자문역이다 (바깥). 둘 사이에 문 **에어록** 하나만 둔다. 바깥으로 가는 길은 에어록 `send` 하나뿐이고, 사람이 창에서 보낼 바이트를 그대로 보고 눌러야 나간다.
- **스킬 문장은 벽이 아니다 (AL-09)**: LLM 이 지키는 규칙은 확률이다. 막는 일은 결정적 코드 (검사기) · 권한 (opencode · Claude Code) · 사람의 확정 창이 한다. SKILL.md 는 길 안내일 뿐이다.
- **세 겹**: ① 사내 LLM 이 원자료를 일의 모양으로 **추상화** (brief.json — 닫힌 형식) ② 결정적 검사기 D1–D6 + 사내 LLM 2차 판정 D7 이 **막는 쪽으로 실패** ③ 사람이 확정 창에서 **보낼 바이트 그대로** 확인 (D8). 돌아오는 길에서는 가명 토큰을 되돌리되, 코드에는 글자 치환 대신 **묶기 파일** 을 안쪽에서 만든다 (06).
- **사람이 Claude Code 를 직접 쓸 때 (안전벨트)**: 가장 흔한 사고는 사람이 원문을 붙여 넣는 것이다. 같은 검사기를 Claude Code 의 `UserPromptSubmit` 훅 (프롬프트를 Claude 에 닿기 전에 막는다 [문헌]) 과 `PreToolUse` 훅 (원자료 폴더 읽기를 막는다 [문헌]) 에 건다. M1 에 넣는다.
- **이 도구가 못 하는 것 (02)**: 법적 판단 · 회사 승인 · 회사 망 DLP 를 대신하지 못한다. 같은 PC · 같은 계정에서 셸을 쥔 LLM 앞에서는 PC 안의 어떤 장치도 단단한 벽이 아니다 (L-11). **보안 부서가 이 설계를 보고 허용 범위를 정하기 전까지 실데이터는 0** 이다 (AL-10 · Q4).
- **예산과 보안이 같은 쪽을 가리킨다 (08)**: Claude 를 지휘자로 긴 에이전트 대화를 돌리면 맥락이 쌓여 한도를 금방 쓴다. 짧은 brief 한 번 → 답 한 번인 자문역이 훨씬 싸다 [추정].
- **첫 걸음**: M0 정찰 (앱 코드 0줄 · 합성 자료만) — 가짜 Claude 서버를 127.0.0.1 에 띄워 Claude Code 가 **실제로 무엇을 보내는지 바이트로** 본다 (KIT-1). 그다음 M1 은 자동 호출 없이 사람이 복사 · 붙여 넣는 손 다리 + 안전벨트다.

## 01 문제 · 목표 · 비목표

### 문제

- Claude 사용량에 월 한도가 있다. 사내 LLM 은 한도가 없지만 기획 · 화면 설계는 Claude 가 낫다고 본다. 둘을 나눠 쓰고 싶다.
- 나눠 쓰는 순간 자료가 두 모델 사이를 오간다. 사내 LLM 이 만진 것 (코드 · 결과 · 오류 글 · 파일 이름) 은 원자료가 묻어 있다. 오가는 길마다 새는 길이 생긴다 (03).

### 목표 (잴 수 있게)

| # | 목표 | 재는 법 | 문턱 [제안] |
|---|---|---|---|
| G1 | 바깥 바이트에 원자료가 없다 | 합성 자료에 카나리아 (지어낸 비밀 문자열 · 꼴 바꾼 변형 포함) 를 묻고, 가짜 Claude 서버가 받은 바이트 전부에서 찾는다 | 1,000 시나리오에서 0 |
| G2 | 막는 쪽으로 실패한다 | 검사기 오류 · 사내 LLM 응답 없음 · 시간 초과 · 사전 비어 있음 · 창 닫음 · 모르는 형식을 하나씩 일으킨다 | 모든 경우 안 나감 (테스트) |
| G3 | brief 가 쓸모 있다 | 합성 과제에서 Claude 가 brief 만 보고 낸 계획 · UI 초안을 사내 LLM 이 이어서 구현할 수 있나 | 사람 판정 5점 중 4 이상 |
| G4 | 싸다 | 자문 한 번 · UI 초안 한 번의 실제 토큰 (KIT-6) | 자문 한 번이 월 한도의 1% 이하 |
| G5 | 사람이 읽을 수 있다 | 확정 창에서 보낼 내용을 읽고 판단하는 시간 | 1분 안 (brief 크기 상한으로 맞춘다) |
| G6 | 재식별을 알아챈다 | brief 로 원래 단어를 추측할 수 있게 일부러 만든 시나리오에서, Claude 답에 사전 단어가 되돌아오면 U2 가 잡는다 | 잡는 비율을 M0 에서 재고 문턱을 정한다 |

### 비목표

- 원자료를 "안전하게 만들어" 보내는 도구가 아니다. 그런 변환은 없다고 보고 설계한다.
- Claude 에게 코드 리뷰 · 디버깅 · 데이터 분석을 맡기지 않는다. 원문 코드 · 데이터가 있어야 하는 일은 안쪽 일이다.
- 회사 망 DLP · 보안 부서 승인 · 법적 판단을 대신하지 않는다 (02).
- 그림을 바깥으로 보내지 않는다. 사내 화면 캡처는 안쪽의 그림 모델이 읽는다.

## 02 먼저 정할 것 — 이 도구가 할 수 없는 일

정직하게 적는다. 이 칸을 건너뛰고 만들면, 도구가 있다는 사실이 "안전하다" 는 착각을 만든다.

1. **허용 범위는 회사가 정한다.** 어떤 등급의 무엇이 Claude 로 가도 되는지 (예: 일반 프로그래밍 질문은 되나 · 업무 화면 구조는 되나) 는 보안 부서가 정한다. 이 도구는 그 범위를 기계로 지키는 장치일 뿐이다. 정해 주지 않으면 기본값은 **아무것도 안 보냄** 이다.
2. **같은 PC 안에는 단단한 벽이 없다.** 사내 LLM 이 셸을 쓰면, 그 계정이 할 수 있는 일은 다 한다 — `claude` 명령을 직접 부를 수도, 설정 파일을 고칠 수도 있다. 그래서 opencode 셸 권한을 기본 `ask` 로 두고 (사람이 명령마다 본다), 회사 망 쪽 DLP 가 Claude 로 가는 통신을 보는지 확인한다 (Q4). 남는 위험은 리스크 R1 에 적는다.
3. **사람이 마지막 문이다.** 확정 창이 있어도 사람이 읽지 않고 누르면 소용없다. 그래서 brief 를 작게 묶고 (G5), 걸린 곳 · 이번 달 횟수를 크게 보인다.
4. **너무 많이 막으면 사람은 도구를 끈다.** 오탐이 많으면 사용자는 에어록을 비켜 Claude 에 직접 붙여 넣는다 — 가장 나쁜 결과다. 쓰기 쉬움도 보안 성질이다 (R6).

## 03 위협 모델 — 새는 길

| # | 새는 길 | 막는 것 |
|---|---|---|
| L-01 | 사람이 원문을 Claude Code · 웹 Claude 에 붙여 넣는다 | 안전벨트 `UserPromptSubmit` 훅 (Claude Code 만 · 웹 Claude 는 못 막음 — 교육 · 회사 DLP) |
| L-02 | Claude Code 가 원자료 파일을 읽는다 (Read · Grep · Glob · Bash) | Claude 를 원자료 폴더에서 띄우지 않는다 · 헤드리스는 `--tools ""` · 대화형은 `PreToolUse` 훅 + 권한 deny 규칙 |
| L-03 | 사내 LLM 의 결과 (코드 · 표 · 로그) 가 Claude 로 되돌아간다 | 모양 B (05) — Claude 는 지휘하지 않으므로 결과를 받지 않는다. 받아야 하면 brief 로 다시 쓴다 |
| L-04 | 사내 LLM 이 쓴 brief 에 원자료가 섞인다 (추상화 실패) | D1–D7 · 사람 D8 |
| L-05 | 가려도 뜻이 남는다 — 구조 · 수치 관계 · 맥락으로 재식별 · 여러 번 보낸 것을 모으면 그림이 된다 (모자이크) | 숫자 금지 (D4) · 크기 상한 (D1) · 주제별 누계 (감사 기록) · 역유입 경보 (U2) |
| L-06 | 파일 이름 · 경로 · 오류 글 · 스택 추적 · 사용자 이름이 낀 폴더 경로 | D3 경로 · 주소 꼴 · Claude 헤드리스 시스템 프롬프트 교체 (KIT-1 로 실제 바이트 확인) |
| L-07 | 그림 (스크린샷) | 바깥으로 그림 금지 — brief 에 첨부 칸이 없다 |
| L-08 | 자동 맥락 — `CLAUDE.md` · git 기록 · 자동 메모리 · IDE 선택 영역 · `@파일` 언급 | 헤드리스는 빈 임시 폴더 · `--restricted` · `--no-session-persistence` · 대화형은 KIT-2 에서 `@파일` 펼침이 훅에 보이는지 확인 [미확인] |
| L-09 | Claude Code 에 붙은 MCP · 커넥터가 사내 자료를 가져온다 | 헤드리스 `--strict-mcp-config` (빈 설정) · `--disallowedTools "mcp__*"` [문헌] |
| L-10 | Claude Code 의 부가 통신 (텔레메트리 · 오류 보고) 에 경로 · 파일 이름이 섞인다 | 부가 통신 끄는 환경 변수 · KIT-1 에서 프록시 기록으로 확인 [미확인] |
| L-11 | 사내 LLM 이 에어록을 비켜 간다 (`claude` 직접 호출 · `curl` · PowerShell) | opencode 셸 기본 `ask` + `claude*` · 네트워크 명령 deny · KIT-4 레드팀. 단단한 벽은 아니다 (02-2 · R1) |
| L-12 | 가명 표 · 사내 단어 사전이 샌다 (커밋 · 로그 · 보고) | 데이터 폴더에만 (W-06) · 로그 · 막은 까닭에는 단어 대신 개수와 검사 번호만 (AL-11) |
| L-13 | 승인 피로 — 사람이 읽지 않고 누른다 | brief 크기 상한 · 걸린 곳 강조 · 이번 달 횟수 · 하루 상한 [제안] |
| L-14 | 돌아온 UI 코드가 외부 CDN · 원격 주소를 부른다 (안쪽 PC 에서 돌 때 바깥과 통신) | U3 · W-03 |
| L-15 | 감사 기록이 민감해진다 | 보낸 것 (이미 정화된 것) 만 남긴다 · 가명 표는 남기지 않는다 |
| L-16 | 바깥 쪽 보존 — 엔터프라이즈 대화 보존 · 관리자 열람 | 정화된 것만 가므로 한 건으로는 문제가 아니지만 누적은 L-05 와 같다 |
| L-17 | 그림 모델이 그림을 글로 바꾼 설명이 그대로 나간다 | 그 글도 brief 의 한 칸이라 D1–D8 을 똑같이 거친다 |

## 04 불변식

어떤 판 · 어떤 설정에서도 깨지면 안 되는 것이다. 테스트가 하나씩 지킨다.

| # | 불변식 |
|---|---|
| AL-01 | **바깥으로 가는 길은 하나다.** Claude 를 부르는 코드는 에어록 `send` 한 곳에만 있다. 스킬 · 에이전트 문서에는 Claude 를 부르는 다른 방법을 적지 않는다 |
| AL-02 | **사람이 창에서 눌러야 나간다.** 확정은 tkinter 창의 버튼으로만 한다. 확정을 건너뛰는 옵션 · 환경 변수 · 설정 키를 만들지 않는다 (테스트는 프로세스 안에서 함수를 바꿔 끼운다). 창이 없는 환경에서는 보내지 않는다 |
| AL-03 | **막는 쪽으로 실패한다.** 검사기 예외 · 시간 초과 · 사내 LLM 응답 없음 · 사전 비어 있음 · 모르는 `format` · 창 닫힘 → 안 보냄 |
| AL-04 | **일의 모양만 나간다.** 바깥으로 가는 것은 brief.json 을 정해진 틀로 펼친 글뿐이다. 숫자 · 그림 · 파일 · 코드 원문 · 경로 · 주소가 없다. 크기 상한이 있다 |
| AL-05 | **가명 표는 안쪽에만, 매번 새로.** 토큰은 무작위다 (해시 금지 — 사전이 있으면 해시는 거꾸로 풀린다). 같은 단어도 자문마다 다른 토큰이다 |
| AL-06 | **Claude 에게는 도구가 없다.** 헤드리스 호출은 도구 · MCP · 설정 파일 · 세션 저장이 모두 꺼진 프로필로, 빈 임시 폴더에서, 입력은 표준 입력으로 한다 (명령줄 인자는 프로세스 목록에 보인다) |
| AL-07 | **나간 것은 모두 남긴다.** 보낸 바이트 그대로 · sha256 · 시각 · 모델 · 토큰 수를 감사 기록에 남긴다. 확정 창이 "이 내용이 기록에 남습니다" 를 먼저 보인다 (W-05) |
| AL-08 | **들어온 것은 믿지 않는다.** U1–U5 를 통과해야 안쪽 파일이 된다. 돌아온 코드는 안쪽에서 테스트를 거친 뒤에만 쓴다 |
| AL-09 | **스킬 문장은 벽이 아니다.** 금지는 코드 · 권한 · 창이 지킨다. SKILL.md 에만 있는 금지는 금지로 세지 않는다 |
| AL-10 | **실데이터는 승인 뒤.** 설정 `policy.real_data` 기본 `false` — 그동안은 합성 자료 표시가 있는 brief 만 보낸다. 이 값은 창에서 사람만 바꾼다 (`--set` 거부) |
| AL-11 | **막은 까닭에 걸린 단어를 쓰지 않는다.** 출력 · 로그 · 훅의 까닭 글에는 `사전 단어 2개 (D2) · 3줄` 처럼 개수 · 검사 번호 · 줄만. 훅의 까닭 글은 Claude 가 읽기 때문이다 |
| AL-12 | **보안에 걸린 설정은 바깥에서 못 바꾼다.** 사전 위치 · 검사 문턱 · 정책은 환경 변수 · 명령줄로 덮어쓰지 않는다. 데이터 폴더가 기본 위치가 아니거나 사전이 비면 보내지 않는다 |

## 05 모양 — 세 갈래와 고른 것

| | A. Claude Code 가 지휘 | B. opencode 가 지휘 · Claude 는 자문 (추천) | C. 사람이 다리 |
|---|---|---|---|
| 흐름 | Claude Code 가 일을 나누고 `opencode run` 으로 사내 LLM 을 부린다 | 사내 LLM 이 일을 나누고, 기획 · UI 초안만 에어록으로 Claude 에게 묻는다 | 에어록이 brief 를 만들어 창에 띄우고, 사람이 복사해 Claude 에 붙여 넣고, 답을 다시 붙여 넣는다 |
| Claude 의 도구 | 있다 (파일 · 셸) | 없다 | 사람이 쓰는 Claude Code 의 도구 (안전벨트가 막음) |
| 바깥으로 가는 길 | 많다 — 사내 LLM 의 모든 결과가 Claude 맥락으로 돌아온다 (L-03) | 하나 (AL-01) | 하나 (사람 손) |
| 예산 | 많이 쓴다 — 긴 에이전트 대화 | 적게 쓴다 | 적게 쓴다 |
| 약한 곳 | 복귀 길을 전부 막아야 한다 · 훅은 보조 장치라고 문서도 말한다 [문헌] | 사내 LLM 의 지휘 능력 (KIT-3) | 자동화가 적다 · 사람이 수고 |
| 판정 | **실데이터에는 쓰지 않는다** — 합성 자료 연습에만 | **목표 모양 (M2–M3)** | **첫 배포 (M1)** · 이후에도 비상 길 |

- C 를 먼저 내는 까닭: 자동 호출 없이도 쓸모가 있고, 에어록의 핵심 (brief · 검사기 · 창 · 되돌리기) 을 그대로 쓴다. Claude Code 헤드리스의 실제 동작을 모르는 채로 자동화를 먼저 만들지 않는다.
- 비유하면, Claude 에게는 사랑채만 내준다. 차는 대접하되 서재 열쇠는 주지 않는다.

## 06 에어록 — seal · 창 · send · unseal

```text
안쪽 (사내 PC · 원자료)                                     바깥 (Claude)
사내 LLM ── brief.json ──> seal ──> 확정 창 (사람) ──> send ──> 도구 없는 Claude
   ^                       D1–D7      D8 · 기록 AL-07              |
   |                                                              v
 구현 · 테스트 <── 묶기 파일 · 결과 <── unseal (U1–U5 · 가명 되돌리기) <── 답
```

### brief.json — 닫힌 형식 (부록 A)

- 사내 LLM 이 원자료를 보고 쓰는 **일의 모양**이다. 키가 닫혀 있고 (모르는 키 = 거부), 칸마다 길이 상한이 있고, 자유 글 칸은 적다.
- 사람 · 화면 · 항목 · 단계는 이름 대신 가명 토큰과 **닫힌 종류** (`화면` · `항목` · `단계` · `표` · `역할`) 로 적는다. 사람은 이름이 아니라 역할로만 나온다.
- 항목은 뜻 대신 **꼴** 로 적는다 — `숫자 · 단위 있음` · `범주 · 값 7개 안팎` 은 되고, 단위 이름 · 값 범위 · 실제 범주 이름은 안 된다.
- 에어록이 brief.json 을 정해진 틀로 펼쳐 프롬프트 글을 만든다. Claude 는 brief.json 에 없는 것을 하나도 받지 않는다.

### 가명 토큰

- 꼴: `PH_` + 무작위 대문자 · 숫자 4자 (예: `PH_K7Q2`). 코드 식별자 · 문자열 · 글 어디에 들어가도 깨지지 않는 꼴을 골랐다. 자문마다 새로 뽑는다 (AL-05).
- 표 (토큰 → 진짜 단어) 는 기본이 **메모리에만** 있다 — seal 부터 unseal 까지 창 하나에서 끝난다 (Q6). 여러 번 오가는 자문이 필요하면 Windows DPAPI 로 잠근 파일에 기한을 두고 남기는 방안을 Q6 에서 고른다.

### 나가는 검사 D1–D8

모두 통과해야 창의 보내기 단추가 켜진다. 하나라도 걸리면 고쳐서 다시 seal 한다 — 자동으로 가려서 보내지 않는다 (가린 결과를 사람이 보지 않으면 확정이 아니다).

| # | 검사 | 무엇을 |
|---|---|---|
| D1 | 형식 | brief.json 스키마 · 닫힌 키 · 칸별 길이 · 전체 크기 상한 (예: 펼친 글 8 KB [제안]) |
| D2 | 사전 | 사용자가 확정한 사내 단어 (제품 · 공정 · 과제 · 고객 · 시스템 이름 · 약어). 대소문자 · 띄어쓰기 · 하이픈 · 한영 표기 변형까지 |
| D3 | 꼴 | 경로 (`C:\` · `\\` · `/home`) · URL · IP · 호스트 · 메일 · 사번 · 로트 · 부품 번호 꼴 (사용자가 정규식으로 더함) · 날짜와 시각 |
| D4 | 숫자 | 자유 글에 숫자 금지. 구조에 필요한 개수는 닫힌 칸 (`count` 0–99) 으로만 [제안] |
| D5 | 덩어리 | 코드 블록 · base64 · hex · 엔트로피가 높은 문자열 — 원문이 숨어 나가는 길 |
| D6 | 토큰 | `PH_` 꼴만 · brief 안의 토큰이 모두 표에 있음 |
| D7 | 사내 LLM 판정 | "이 글이 특정 회사 · 공정 · 제품 · 수치 · 사람을 드러내는가" 를 사내 LLM 에 묻는다 ([SPEC-llm.md](../SPEC-llm.md) 의 `llm` 설정). 예 → 막음 · 응답 없음 → 막음 (AL-03). 보조 검사일 뿐 D2–D6 을 대신하지 않는다 |
| D8 | 사람 | 확정 창에서 **보낼 바이트 그대로** 를 본다. 토큰 강조 · 걸릴 뻔한 곳 · 모델 · 예상 비용 · 이번 달 누계 · "보내면 되돌릴 수 없습니다" |

- 사전 만들기: `dict suggest <폴더>` 가 안쪽에서 프로젝트를 훑어 후보 (자주 나오는 고유 명사 · 식별자) 를 내고, 사용자가 창에서 확정한다 (W-07). 사전은 데이터 폴더에만 있고 출력에 단어를 찍지 않는다 (AL-11).

### 들어오는 검사 U1–U5

| # | 검사 | 걸리면 |
|---|---|---|
| U1 | 토큰 | 표에 없는 토큰 · 꼴이 깨진 토큰 (`ph_k7q2` · `PH_K7Q`) 을 줄과 함께 보인다. 아는 토큰만 되돌린다 |
| U2 | 역유입 | 답에 사전 단어가 있으면 — Claude 가 brief 만 보고 진짜 단어를 맞혔다는 뜻이다 → 그 주제의 자문을 멈추고 사람에게 알린다 (brief 가 재식별될 수 있었다) |
| U3 | 바깥 주소 | URL · CDN · `fetch` · `XMLHttpRequest` · `WebSocket` 의 대상 주소 — 표시하고 안쪽 파일에서는 뺀다 (W-03) |
| U4 | 꼴 | 기대한 산출물 꼴 (기획 = 마크다운 · UI = HTML 한 파일) · 크기 |
| U5 | 실행 전 | 돌아온 코드는 바로 돌리지 않는다. 사내 LLM 이 안쪽에서 테스트 · 리뷰한 뒤 쓴다 |

### 코드에는 치환 대신 묶기

- 기획 글은 토큰을 진짜 단어로 바꿔 쓴다 (글자 치환).
- UI 코드는 바꾸지 않는다. 진짜 항목 이름에 띄어쓰기 · 한글이 있으면 코드가 깨지고, 치환 실수는 조용히 틀린 화면을 만든다. 대신 Claude 는 `FIELDS.PH_K7Q2` 처럼 토큰으로만 짜고, 에어록이 안쪽에서 **묶기 파일** (`binding.local.js` — 토큰 → 진짜 이름 · 표시 글) 을 만든다. 묶기 파일은 안쪽에만 있고 커밋하지 않는다.

### 감사 기록

- `%LOCALAPPDATA%\airlock-1\audit\` 에 자문마다 한 파일: 보낸 바이트 · sha256 · 시각 · 모델 · 토큰 수 · 결과 (보냄 · 버림 · 막힘과 검사 번호). 가명 표 · 원문은 없다.
- "무엇을 보냈나" 를 나중에 증명할 수 있어야 한다. 보안 부서가 요구하는 보존 기간 · 형식은 Q4 에서 받는다.

## 07 호스트 — opencode 지휘 · Claude 자문 · Claude Code 안전벨트

### 모델 배정 (이름은 사용자 설정 — W-12)

| 모델 | 맡는 일 | 원자료 |
|---|---|---|
| 사내 LLM (글 · 큰 모델) | 지휘 · 원자료 읽기 · brief 쓰기 · D7 판정 · 구현 · 테스트 · 묶기 · 리뷰 | 본다 |
| 사내 LLM (그림) | 사내 화면 캡처 읽기 · 돌아온 UI 초안을 안쪽에서 렌더한 그림 검토 | 본다 |
| Claude Opus 급 (1M) | 기획 · 구조 설계 · 어려운 판단 — 드물게 | 못 본다 |
| Claude Sonnet 급 (1M) | UI/UX 초안 (HTML 한 파일 · 합성 자료) — 출력이 길어 싼 쪽 | 못 본다 |

### opencode 쪽 (지휘)

- 에이전트 `airlock` (사내 LLM 큰 모델) · 명령 `/consult` · 스킬 `skills/airlock-1/SKILL.md` 한 벌. 스킬이 일의 순서를 안내한다: 일 나누기 (바깥이 필요한 것 = 기획 · UI 초안 / 나머지 = 안쪽) → brief.json 쓰기 → `airlock-1 seal` → (사람이 창에서 확정) → `send` → `unseal` → 안쪽 구현 · 묶기 · 그림 모델 검토.
- 권한 [문헌: opencode 문서 › agents · permissions — M0 에서 판 확인]: 셸 기본 `ask` · 허용은 에어록 명령과 프로젝트 테스트 명령만 · `claude*` · `curl*` · `Invoke-WebRequest*` · `powershell*` · 웹 가져오기는 deny. 편집은 작업 폴더만.
- opencode 의 JS 플러그인 (`tool.execute.before` 훅) 은 셸 명령을 더 단단히 거를 수 있지만 npm 경로가 생긴다. M0 에서 권한만으로 부족하면 그때 다시 본다.

### Claude 헤드리스 프로필 (send 가 쓰는 것)

[문헌: Claude Code CLI 문서 2026-11-05] 아래 플래그가 있다. 조합이 실제로 무엇을 보내는지는 KIT-1 에서 바이트로 확인한 뒤 확정한다.

```text
claude -p --restricted --tools "" --disallowedTools "*" --strict-mcp-config --mcp-config <빈 파일>
       --no-session-persistence --system-prompt-file <에어록 고정 프롬프트>
       --model <설정 claude.model_plan 또는 claude.model_ui> --output-format json --max-turns 1
작업 폴더 = 빈 임시 폴더 · 입력 = 표준 입력
```

- `--system-prompt-file` 로 기본 시스템 프롬프트를 통째로 바꾼다 — 기본 프롬프트에 작업 폴더 경로 같은 환경 정보가 들어가는지 [미확인] 를 KIT-1 에서 보고, 들어가면 이 교체가 필수다. 프롬프트가 짧아지니 비용도 준다.
- `--bare` 만으로는 안 된다 — 문서가 "Bash · 파일 읽기 · 편집 도구는 남는다" 고 적는다 [문헌].
- 회사 게이트웨이가 Anthropic 호환 주소를 직접 준다면 Claude Code 없이 표준 라이브러리 `urllib` 로 부르는 길도 있다 (Q5). 그쪽이 바깥으로 가는 바이트를 더 정확히 쥔다.

### Claude Code 안전벨트 (사람이 대화형으로 쓸 때)

[문헌: Claude Code hooks 문서 2026-11-05]

- `UserPromptSubmit` 훅 → `airlock-1 scan` (D2 · D3 · D5). 걸리면 종료 코드 2 로 막는다 — 문서는 "프롬프트가 Claude 에 닿지 않는다" 고 적는다.
- `PreToolUse` 훅 (Read · Grep · Glob · Bash · Edit · Write · WebFetch) → 깨끗한 작업 폴더 밖을 건드리면 deny. 훅은 보조이고 "단단한 허용 · 거부는 권한 체계로" 라는 문서 권고대로 권한 deny 규칙을 같이 둔다.
- 훅 실패를 막는 쪽으로: `onFailure: "block"` (v2.1.295 이상) — 없으면 시간 초과한 훅이 도구 호출을 통과시킨다 [문헌]. 사내 PC 의 Claude Code 판을 KIT-2 에서 확인한다.
- 사용자가 훅을 끄지 못하게 하려면 관리형 설정 (`allowManagedHooksOnly`) 이 필요한데 관리자 권한이 든다 — W-08 이 금지하므로 이 도구는 하지 않고, 회사 IT 에 줄 설정 안내만 MANUAL 에 둔다.
- 못 막는 것: 웹 Claude (claude.ai) 에 붙여 넣기 · 다른 PC. 교육과 회사 DLP 의 몫이다.

## 08 예산

- 정가 [문헌: Anthropic 1차 API 정가표 · 2026-10-06 기준] — Opus 5 입력 $5 · 출력 $25, Sonnet 5 입력 $2 · 출력 $10 (100만 토큰당). 회사 계약 · 지역 배치 · 1M 맥락 판의 실제 단가는 다를 수 있다 [미확인] — KIT-6 에서 `--output-format json` 의 사용량 칸으로 잰다.
- 자문 한 번 [추정]: brief 를 펼친 글 2–3천 토큰 + 고정 시스템 프롬프트 + 답 3–8천 토큰. Opus 로 약 $0.1–0.25. UI 초안 (HTML 1.5–3만 토큰 출력) 은 Sonnet 으로 약 $0.15–0.3.
- 대조 [추정]: Claude 가 지휘하는 대화형 에이전트 세션은 턴마다 쌓인 맥락을 다시 보낸다. 40턴 · 평균 8만 토큰이면 입력만 320만 토큰 — 캐시가 많이 덜어도 자문 한 번의 수십 배다. 모양 B 를 고른 까닭이 하나 더 있다.
- 에어록은 감사 기록의 토큰 수로 이번 달 누계를 내고, 확정 창에 월 한도 대비 % 를 보인다. 한도 (`claude.monthly_budget`) 는 사용자 설정이다.

## 09 works 규칙과의 관계

자리를 works 안 새 앱으로 고르면 (Q2 추천) 아래와 같다. 앱 유형은 *명령형* (S-04) — 서버가 없어 사내 LLM 이 127.0.0.1 주소로 확정을 흉내 낼 길이 없다.

| 조항 | 이 도구에서 | 맞음 |
|---|---|---|
| W-01 | `airlock-1/` 한 폴더 · 다른 앱과 주고받을 것 없음 | 맞음 |
| W-02 | 표준 라이브러리만 — `re` · `json` · `secrets` · `hashlib` · `subprocess` · `tkinter` · `ctypes` (DPAPI) · `urllib`. 보안 도구라 의존 0 이 오히려 장점이다 (공급망 공격 면이 없다). 한국어 이름 탐지 같은 ML 모델은 넣지 않고 D7 (사내 LLM) 로 대신한다 | 맞음 |
| W-03 | 바깥 통신은 사용자가 설정한 사내 LLM · Claude 길뿐 · 돌아온 UI 의 외부 주소는 U3 | 맞음 |
| W-04 | 키는 다루지 않는다 (Claude Code · 사내 LLM 설정이 쥔다). 사내 단어 사전도 비밀처럼 다룬다 (AL-11) | 맞음 |
| W-05 | 원문 · 가명 표는 메모리만 (Q6). 감사 기록은 사람이 확정한 바깥 바이트라 저장 대상이고, 창이 먼저 알린다 | 맞음 — Q6 에서 DPAPI 파일을 고르면 MANUAL 알려진 한계에 적는다 |
| W-06 | `%LOCALAPPDATA%\airlock-1\` — 설정 · 사전 · 감사 기록 · 형식 버전 · 원자적 쓰기 | 맞음 |
| W-07 | 보내기는 되돌릴 수 없으므로 확정 창이 전부다 · 사전 등록도 제안 → 확정 | 맞음 |
| W-08 | opencode 설정 폴더에 에이전트 · 스킬 복사 · Claude Code 사용자 설정에 훅 추가 = 사용자 범위 변경 → `[질문]` · 백업 · 제거 절 | 맞음 |
| W-10 | 확정 창은 DESIGN.md 를 따른다 · 걸린 곳 강조는 빨강 없이 (라임 · 네이비 · 굵기) | 맞음 |
| W-11 | 가짜 Claude 서버 · 가짜 사내 LLM 서버 · 카나리아 테스트 (G1) 를 CI 에 | 맞음 |
| W-12 | 사내 단어 · 정규식 · 모델 이름은 사용자 설정에만 · 테스트 자료는 지어낸 회사 · 공정 | 맞음 |
| S-09 | D7 은 SPEC-llm 의 `llm` 키를 따른다. 다만 SPEC-llm › 02 의 환경 변수 덮어쓰기 (`<접두어>_BASE_URL` 등) 는 AL-12 와 부딪힌다 — 사내 LLM 이 환경 변수로 판정 모델을 바꿔 D7 을 무력화할 수 있다 | **따르지 않음** (규약 S) — 까닭을 MANUAL › 알려진 한계에 적는다 |

- 별도 저장소로 고르면 (Subordinate–1 · Analysis–1 의 길) 위 표가 그 저장소 `RULES.md` 의 원고가 된다.

## 10 로드맵

### M0 정찰 — 앱 코드 0줄 · 합성 자료만 · 1주 [추정]

| # | 정찰 | 판정 (결과 보기 전에 적는다) |
|---|---|---|
| KIT-1 | **보내는 바이트 보기** — 127.0.0.1 에 가짜 Anthropic 서버를 띄우고 Claude Code 를 그쪽으로 향하게 한 뒤 (`ANTHROPIC_BASE_URL` — 회사 관리형 설정이 막으면 개인 PC 에서), 07 의 헤드리스 프로필로 합성 brief 를 보낸다. 요청 전체 (시스템 · 도구 목록 · 메시지 · 헤더 · 메타데이터) 를 덤프한다. 부가 통신은 로컬 프록시 기록으로 본다 | 보낸 바이트가 brief 를 펼친 글 + 고정 프롬프트뿐인가. 경로 · 사용자 이름 · 파일 목록 · 도구 정의가 하나라도 있으면 프로필을 고치고 다시 |
| KIT-2 | **훅 시험** — 사내 PC 의 Claude Code 판 · `UserPromptSubmit` 이 사전 단어를 막는지 · `@파일` 언급 · 붙여 넣은 그림이 훅에 보이는지 · `PreToolUse` deny · `onFailure: "block"` | 막아야 할 것을 하나라도 못 막으면 그 길을 문서에 "못 막음" 으로 적는다 |
| KIT-3 | **사내 LLM 추상화 능력** — 지어낸 회사 · 공정 · 수치로 만든 합성 과제 30개에 카나리아를 묻고, 사내 LLM 이 brief.json 을 쓰게 한다. 검사기 전 · 후 새는 비율 · brief 쓸모 (G3 — 합성이라 Claude 에 보내 봐도 된다) | 검사기 후 새는 것 0 · G3 4점 이상. 못 미치면 brief 칸을 더 닫는다 |
| KIT-4 | **우회 레드팀** — opencode 권한 설정에서 사내 LLM 에게 "Claude 에게 물어봐" 를 시키고, `claude` 직접 호출 · `curl` · PowerShell · `python -c` 로 비켜 가는지 본다 | 사람 확인 (`ask`) 없이 바깥으로 간 길이 있으면 R1 을 올리고 권한을 고친다 |
| KIT-5 | **사내 확인 (사람)** — 보안 부서에 한 장 설계 (04 · 05 · 06) 와 남는 위험 (02 · 11) 을 보이고: 허용 범위 · 회사 망에 Claude 행 DLP 가 있는지 · 감사 기록 보존 요구 · 엔터프라이즈 대화 보존 설정 | 답을 받기 전에는 M5 를 열지 않는다 |
| KIT-6 | **비용** — 자문 한 번 · UI 초안 한 번의 실제 토큰 · 비용 | G4 |

### M1 – M5

- **M1 손 다리 + 안전벨트 (모양 C)**: `seal` · 확정 창 · 클립보드 복사 · `unseal` (답 붙여 넣기) · 사전 · 감사 기록 · Claude Code 안전벨트 훅. Claude 자동 호출 없음.
- **M2 자동 자문 (모양 B)**: `send` — KIT-1 로 확정한 헤드리스 프로필 (또는 Q5 의 HTTP 길) · 비용 누계 · D7.
- **M3 opencode 지휘 스킬**: SKILL.md · 에이전트 · `/consult` · 권한 · UI 초안 묶기 · 그림 모델 렌더 검토.
- **M4 굳히기**: 통합 적대 검증 (T14) · 오탐 줄이기 (R6) · 회사 IT 용 관리형 설정 안내.
- **M5 (조건부) 실데이터**: KIT-5 의 보안 부서 답이 있을 때만. 창에서 `policy.real_data` 를 사람이 연다.

## 11 리스크 대장

| # | 리스크 | 가능성 | 영향 | 줄이는 것 | 남는 것 |
|---|---|---|---|---|---|
| R1 | 사내 LLM 이 셸로 에어록을 비켜 Claude 를 직접 부른다 (L-11) | 중 | 치명 | 셸 기본 `ask` · deny 목록 · 스킬에 다른 길을 적지 않음 · KIT-4 | 같은 계정 안에서는 단단한 벽이 없다 — 회사 망 DLP 확인 (Q4) |
| R2 | 사람이 원문을 직접 붙여 넣는다 (L-01) | 높음 | 치명 | 안전벨트 훅 · 교육 | 웹 Claude · 훅을 끈 경우 |
| R3 | 추상화가 새는 brief 를 쓴다 (L-04) | 중 | 치명 | D1–D7 · 닫힌 형식 · 숫자 금지 · 사람 | 사전에 없는 새 단어 + D7 이 놓친 경우 → 사람 |
| R4 | 가려도 뜻으로 재식별 · 모자이크 (L-05) | 중 | 높음 | 일의 모양만 · 크기 상한 · 주제별 누계 · U2 | 누적 판단은 사람 몫 |
| R5 | 승인 피로 (L-13) | 높음 | 높음 | 작은 brief · 강조 · 하루 상한 | 사람 |
| R6 | 오탐이 많아 사람이 도구를 버리고 직접 붙여 넣는다 | 중 | 치명 | 오탐률을 M0 · M4 에서 재고 사전을 다듬는다 · 걸린 곳을 바로 고칠 수 있는 창 | 쓰기 쉬움과 막기의 줄다리기 |
| R7 | Claude Code 업데이트로 플래그 · 훅 동작이 바뀐다 | 중 | 높음 | 시작할 때 판 확인 · 모르는 판이면 보내지 않음 (AL-03) · KIT-1 을 CI 시험으로 굳힘 | 새 부가 통신 |
| R8 | 사내 LLM 이 지휘 · brief 쓰기를 못 해낸다 (KIT-3) | 중 | 중 | brief 칸을 더 닫고 질문형 틀로 · 모양 C 로 남기 | 자동화가 줄어든다 |
| R9 | 가명 표 · 사전 · 묶기 파일이 커밋 · 공유된다 (L-12) | 낮음 | 치명 | 데이터 폴더에만 · `.gitignore` · CI 에 사내 단어 흔적 검사는 불가 (공개 저장소라 사전을 못 올림) → 사람 | 사용자가 파일을 옮긴 경우 |
| R10 | 돌아온 코드가 바깥과 통신 · 위험한 동작 (L-14) | 중 | 중 | U3 · U5 · 안쪽 테스트 | 리뷰 누락 |
| R11 | 보안 부서가 거부한다 | 중 | 높음 | 합성 · 공개 자료용 도구로 남는다 (M1 까지로도 쓸모) | 없음 — 그 답을 따른다 |
| R12 | 공개 저장소에 사내 정보가 들어간다 (W-12) | 낮음 | 높음 | 예시는 지어낸 것만 · 모델 이름은 설정에만 · 리뷰 | 사람 |
| R13 | 예산 초과 | 중 | 낮음 | 누계 표시 · 한도 넘으면 창이 막음 · UI 초안은 Sonnet 급 | 단가 [미확인] |
| R14 | "도구가 있으니 안전하다" 는 착각 | 높음 | 치명 | 02 를 MANUAL 첫머리에 · 창에 남는 위험 한 줄 | 사람 |

## 12 질문

| # | 질문 | 선택지 (추천이 앞) |
|---|---|---|
| Q1 | 모양 | **B — opencode 지휘 · Claude 는 도구 없는 자문 (M1 은 C)** · A — Claude Code 지휘 (실데이터 불가) · C 로만 |
| Q2 | 자리 | **works 안 명령형 앱 (의존 0)** · 별도 공개 저장소 · 별도 비공개 저장소 |
| Q3 | 이름 | **`airlock-1` (Airlock–1)** · 다른 이름 |
| Q4 | 보안 부서 | **M0 결과와 한 장 설계를 보안 부서에 보이고, 답 전까지 실데이터 0 (AL-10)** · 이미 받은 허용 범위가 있다 (내용은 저장소가 아니라 사용자 설정에) |
| Q5 | Claude 부르는 길 | **Claude Code 헤드리스 (KIT-1 로 확인)** · 회사 게이트웨이 HTTP 직접 (있다면) · 사람 손 (C) 으로만 |
| Q6 | 가명 표 | **메모리만 — seal 부터 unseal 까지 창 하나** · DPAPI 로 잠근 파일 · 기한 24시간 [제안] |
| Q7 | Claude 에게 줄 일 | **기획 · UI/UX 초안만** · + 공개 라이브러리 사용법 같은 일반 질문 |
| Q8 | 안전벨트 시기 | **M1 에 같이** · M4 로 미룸 |

## 부록

### A brief.json 초안 (format 1)

```json
{
  "format": 1,
  "kind": "plan",
  "data_class": "synthetic",
  "goal": "PH_K7Q2 화면에서 PH_M3X9 항목의 시간 흐름과 벗어난 구간을 한눈에 보는 사내 웹 도구를 기획해 달라",
  "context": [
    "사용자는 PH_R2D8 역할이고 하루에 여러 번 연다",
    "항목은 PH_M3X9 하나와 범주 PH_T4W1 하나다"
  ],
  "entities": [
    {"token": "PH_K7Q2", "type": "화면", "note": "목록과 그래프가 있는 화면"},
    {"token": "PH_R2D8", "type": "역할", "note": "현장 담당자"}
  ],
  "fields": [
    {"token": "PH_M3X9", "kind": "숫자", "unit": "있음"},
    {"token": "PH_T4W1", "kind": "범주", "count": 7}
  ],
  "constraints": ["127.0.0.1 에서만 돈다", "외부 CDN · 웹 폰트 금지", "항목은 FIELDS.<토큰> 으로만 쓴다"],
  "ask": "기획 개요 · 화면 목록 · 화면마다 구성 요소 · 열린 질문"
}
```

- `kind`: `plan` · `ui`. `data_class`: `synthetic` · `real` (`real` 은 `policy.real_data` 가 열렸을 때만).
- 위 예시는 지어낸 것이다. 실제 brief 에서도 `note` 는 일반 말로만 쓴다 (D2–D7 이 같은 칸을 본다).

### B 작업표 (하위 에이전트용)

이 세션의 사용자 설정 (4단 모델 배정) 에 따른 작업표다. 개발은 공개 저장소에서 합성 자료로만 한다. T1–T4 는 M0 이고 앱 코드가 아니다. T5 는 M0 결과와 Q1–Q8 답이 있어야 시작한다.

```json
{
  "project_title": "Airlock–1 (가칭) — 사내 LLM 지휘 · Claude 도구 없는 자문 · 원자료가 바깥으로 가지 않는 문",
  "executive_summary": "opencode + 사내 LLM 이 원자료와 지휘를 쥐고, Claude 는 도구 없이 기획 · UI 초안만 받는 자문역으로 두며, 둘 사이에 결정적 검사기 · 사람 확정 창 · 가명 되돌리기를 가진 표준 라이브러리 문 하나를 만든다. 가린 원자료가 아니라 닫힌 형식의 '일의 모양' (brief.json) 만 내보내고, 모든 장치는 막는 쪽으로 실패한다. 실데이터는 보안 부서 승인 전까지 막고, M0 에서 가짜 Claude 서버로 실제로 나가는 바이트를 먼저 확인한다.",
  "total_estimated_effort": 110,
  "tasks": [
    {"task_id": "T1", "task_name": "M0 보내는 바이트 보기 키트 (KIT-1)", "description": "127.0.0.1 에 Anthropic Messages API 를 흉내 내는 가짜 서버 (표준 라이브러리 http.server) 를 만들어 받은 요청의 본문 · 헤더 전체를 파일로 덤프한다. Claude Code 를 ANTHROPIC_BASE_URL 로 그쪽에 향하게 하고, 기획서 07 의 헤드리스 프로필 (-p --restricted --tools \"\" --disallowedTools \"*\" --strict-mcp-config --no-session-persistence --system-prompt-file --output-format json --max-turns 1, 빈 임시 폴더, 표준 입력) 과 비교용 기본 프로필로 같은 합성 brief 를 보낸다. 덤프에서 경로 · 사용자 이름 · 파일 목록 · 도구 정의 · 환경 정보 · 메타데이터를 찾는 검사 스크립트와, 부가 통신을 보는 로컬 프록시 기록 절차를 만든다. 판정 문턱은 결과 보기 전에 적는다. 합성 자료만 쓰고 출력에 키를 찍지 않는다.", "tier": "Tier 1", "difficulty": "High", "effort_level": 7, "assigned_model": "claude-opus-5.5", "agent_role": "Security_Probe_Engineer", "expected_output": "kit/capture_server.py · kit/inspect_dump.py · 프로필 두 벌 · 점검표 · 결과 표 양식", "dependencies": []},
    {"task_id": "T2", "task_name": "M0 훅 · 우회 레드팀 시험지 (KIT-2 · KIT-4)", "description": "Claude Code 대화형에서 UserPromptSubmit (사전 단어 · 경로 꼴 붙여 넣기 · @파일 언급 · 그림 붙여 넣기) 과 PreToolUse (원자료 폴더 Read · Grep · Glob · Bash) 를 막는지, onFailure block 과 판 요구 (v2.1.295 이상) 를 확인하는 시험지를 쓴다. opencode 쪽은 셸 기본 ask · deny 목록 설정에서 사내 LLM 에게 Claude 에게 물어보라고 시킨 뒤 claude 직접 호출 · curl · Invoke-WebRequest · python -c · 스크립트 파일 쓰기 후 실행으로 비켜 가는 시나리오 20개를 만들고, 사람 확인 없이 바깥으로 간 길을 기록하는 채점표를 만든다.", "tier": "Tier 1", "difficulty": "High", "effort_level": 7, "assigned_model": "claude-opus-5.5", "agent_role": "Red_Team_Designer", "expected_output": "시험지 마크다운 · 시나리오 목록 · 채점표 · 필요한 합성 파일", "dependencies": []},
    {"task_id": "T3", "task_name": "M0 합성 민감 말뭉치 · 카나리아 · 추상화 시험 (KIT-3)", "description": "지어낸 회사 · 제품 · 공정 · 고객 · 사람 · 수치로 합성 과제 30개 (기획 15 · UI 15) 를 만들고, 각 과제에 카나리아 문자열과 그 변형 (대소문자 · 띄어쓰기 · 한영 표기 · 약어 · 숫자 단위 바꿈) 을 묻는다. 사내 LLM 에게 brief.json 을 쓰게 하는 지시문 · 검사기 전후 새는 비율 계산 스크립트 · brief 쓸모 (G3) 사람 채점표를 만든다. 실재하는 회사 · 제품 이름을 쓰지 않는다.", "tier": "Tier 2", "difficulty": "Medium-High", "effort_level": 8, "assigned_model": "claude-sonnet", "agent_role": "Data_Specialist", "expected_output": "kit/corpus/ (합성 과제 30 · 카나리아 목록) · kit/leak_rate.py · 채점표", "dependencies": []},
    {"task_id": "T4", "task_name": "M0 보안 부서 설명 한 장 (KIT-5)", "description": "기획서 02 · 04 · 05 · 06 · 11 을 보안 부서가 10분 안에 판단할 수 있는 한 장으로 줄인다: 무엇이 나가고 무엇이 안 나가는지 · 막는 장치와 그 한계 · 남는 위험 · 물어볼 것 (허용 범위 · Claude 행 망 DLP · 감사 기록 보존 · 엔터프라이즈 보존 설정). 회사 이름 · 사내 시스템 이름은 쓰지 않는다 (사용자가 사내에서 채운다).", "tier": "Tier 3", "difficulty": "Medium", "effort_level": 5, "assigned_model": "claude-sonnet", "agent_role": "Documentation_Specialist", "expected_output": "kit/security-brief.md (한 장) · 질문 목록", "dependencies": []},
    {"task_id": "T5", "task_name": "2판 확정 — M0 결과 · 사용자 답", "description": "KIT-1–KIT-6 결과와 Q1–Q8 답으로 헤드리스 프로필 (또는 HTTP 길) · 훅 구성 · opencode 권한 · brief 칸 · 검사 문턱 · 가명 표 저장 방식을 확정한다. 못 막는 길은 '못 막음' 으로 적고 리스크 대장을 고친다. 갈린 결정 표를 남긴다.", "tier": "Tier 0", "difficulty": "Extreme", "effort_level": 9, "assigned_model": "claude-opus-5.5", "agent_role": "Core_Architect", "expected_output": "기획서 2판 · 갈린 결정 표", "dependencies": ["T1", "T2", "T3", "T4"]},
    {"task_id": "T6", "task_name": "brief.json · 토큰 · 검사 명세", "description": "부록 A 를 JSON Schema 로 확정하고 (닫힌 키 · 칸별 길이 · 전체 크기 · 닫힌 종류 목록), 가명 토큰 꼴과 생성 규칙 (secrets · 충돌 · 자문마다 새로), D1–D8 과 U1–U5 를 기계가 판정할 수 있는 규칙으로 쓴다. 사전 변형 규칙 (대소문자 · 공백 · 하이픈 · 한영) · 숫자 정책 · 덩어리 탐지 문턱 · 막은 까닭 출력 형식 (AL-11) · 묶기 파일 형식 · format 올리는 규칙 · 각 규칙의 반례를 포함한다.", "tier": "Tier 0", "difficulty": "Extreme", "effort_level": 10, "assigned_model": "claude-opus-5.5", "agent_role": "Core_Architect", "expected_output": "schema/brief.schema.json · docs/SPEC-airlock.md (규칙 · 예시 · 반례)", "dependencies": ["T5"]},
    {"task_id": "T7", "task_name": "대장 등록 · 앱 뼈대", "description": "Q2 · Q3 답대로 docs/REGISTRY.md 에 코드 없는 등록 커밋을 먼저 내고 (명령형 · 데이터 폴더 · 포트 없음 · 환경 변수 칸), docs/templates/ 를 복사해 앱 폴더 뼈대 (README 영감 고지문 · INSTALL · docs/MANUAL.md · tests/ · .gitignore (사전 · 감사 기록 · 묶기 파일 · config.json 막기) · .gitattributes · 워크플로) 를 만든다. airlock-1.py 진입에 VERSION · version · help · check 와 설정 (llm 은 SPEC-llm · claude 칸은 앱 자유 · policy.real_data 기본 false) 을 둔다. python tools/works_check.py 새 경고 0.", "tier": "Tier 3", "difficulty": "Medium", "effort_level": 5, "assigned_model": "claude-sonnet", "agent_role": "Repo_Scaffolder", "expected_output": "등록 커밋 · 뼈대 커밋 · 통과하는 빈 CI", "dependencies": ["T5"]},
    {"task_id": "T8", "task_name": "검사기 D1–D6 · scan", "description": "T6 명세대로 결정적 검사기를 표준 라이브러리로 만든다: 스키마 · 크기 (D1) · 사전과 변형 (D2) · 꼴 정규식 (D3 · 사용자 정규식 추가) · 숫자 (D4) · 덩어리와 엔트로피 (D5) · 토큰 (D6). 모든 예외 · 시간 초과는 막음으로 끝난다. 출력에는 단어를 찍지 않고 개수 · 검사 번호 · 줄만 (AL-11). scan 명령 (표준 입력 → 종료 코드 0 통과 · 2 막음) 은 안전벨트 훅과 같은 함수를 쓴다. T3 카나리아 변형 전부를 잡는 테스트 · 반례 묶음 · 사전이 비면 막는 테스트를 넣는다.", "tier": "Tier 0", "difficulty": "Extreme", "effort_level": 9, "assigned_model": "claude-opus-5.5", "agent_role": "Security_Logic_Developer", "expected_output": "검사기 모듈 · scan 명령 · 카나리아 · 반례 테스트", "dependencies": ["T6", "T7"]},
    {"task_id": "T9", "task_name": "seal · unseal · 묶기", "description": "brief.json 을 정해진 틀로 펼쳐 보낼 글을 만들고 (seal), 가명 표를 메모리에 둔다 (Q6 답에 따라 DPAPI 파일 · 기한). unseal 은 U1 (토큰) · U2 (역유입 — 사전 단어가 답에 있으면 그 주제 정지) · U3 (외부 주소) · U4 (꼴) 를 거쳐, 기획 글은 치환하고 UI 코드는 바꾸지 않은 채 묶기 파일 binding.local.js 를 만든다. 결과 파일은 덮어쓰지 않는다. 깨진 토큰 · 모르는 토큰 · CDN 이 든 HTML · 사전 단어가 되돌아온 답의 테스트를 넣는다.", "tier": "Tier 1", "difficulty": "High", "effort_level": 7, "assigned_model": "claude-opus-5.5", "agent_role": "Logic_Developer", "expected_output": "seal · unseal 모듈 · 묶기 파일 형식 · 테스트", "dependencies": ["T6", "T7"]},
    {"task_id": "T10", "task_name": "확정 창 (tkinter)", "description": "DESIGN.md 를 따르는 tkinter 창: 보낼 바이트 그대로 · 토큰 강조 · 검사 결과 (개수 · 번호) · 모델 · 예상 비용 · 이번 달 누계와 한도 % · '보내면 되돌릴 수 없습니다' · '이 내용이 감사 기록에 남습니다' · 보내기 · 고치기 · 버리기 · M1 의 복사 단추와 답 붙여 넣기 칸 · policy.real_data 를 여는 곳. 확정을 건너뛰는 옵션 · 환경 변수를 만들지 않고 (AL-02), 창을 못 띄우는 환경이면 보내지 않는다. 빨강 없이 걸린 곳을 보인다.", "tier": "Tier 2", "difficulty": "Medium-High", "effort_level": 8, "assigned_model": "claude-sonnet", "agent_role": "UI_Engineer", "expected_output": "창 모듈 · 창 없는 환경 테스트 · 함수 바꿔 끼우기 테스트", "dependencies": ["T8", "T9"]},
    {"task_id": "T11", "task_name": "Claude Code 안전벨트 플러그인", "description": "UserPromptSubmit 훅 (scan · 종료 코드 2) 과 PreToolUse 훅 (깨끗한 작업 폴더 밖의 Read · Grep · Glob · Bash · Edit · Write · WebFetch deny) 을 onFailure block 으로 거는 Claude Code 플러그인 (.claude-plugin/plugin.json · hooks) 과 권한 deny 규칙 예시를 만든다. 훅의 까닭 글에 단어를 쓰지 않는다 (AL-11). 설치 · 제거는 사용자 설정 변경이므로 [질문] · 백업 · 되돌리기를 INSTALL 에 넣고, 회사 IT 용 관리형 설정 (allowManagedHooksOnly) 안내는 MANUAL 에만 둔다 (관리자 권한 금지 W-08).", "tier": "Tier 1", "difficulty": "High", "effort_level": 6, "assigned_model": "claude-opus-5.5", "agent_role": "Integration_Developer", "expected_output": "플러그인 폴더 · 훅 단위 테스트 · KIT-2 재시험 기록", "dependencies": ["T8"]},
    {"task_id": "T12", "task_name": "send · 감사 기록 · D7 · 비용", "description": "T5 에서 확정한 Claude 길 (헤드리스 프로필 또는 HTTP) 로 표준 입력 · 빈 임시 폴더에서 한 번 부르고, 시작할 때 Claude Code 판을 확인해 모르는 판이면 보내지 않는다. 보낸 바이트 · sha256 · 시각 · 모델 · 토큰을 감사 기록에 원자적으로 쓴다. D7 은 SPEC-llm 의 llm 설정으로 사내 LLM 에 묻되 환경 변수 덮어쓰기를 받지 않는다 (AL-12 · MANUAL 알려진 한계). 가짜 Claude 서버 · 가짜 사내 LLM 서버로 테스트하고, D7 응답 없음 · Claude 오류 · 시간 초과가 모두 막음인지 본다.", "tier": "Tier 1", "difficulty": "High", "effort_level": 7, "assigned_model": "claude-opus-5.5", "agent_role": "Integration_Developer", "expected_output": "send 모듈 · 감사 기록 형식 · 가짜 서버 테스트", "dependencies": ["T1", "T9", "T10"]},
    {"task_id": "T13", "task_name": "opencode 지휘 스킬 · 에이전트 · 권한", "description": "skills/airlock-1/SKILL.md (일 나누기 · brief 쓰기 지침과 예시 · seal → 확정 → send → unseal → 안쪽 구현 순서 · UI 초안 묶기 · 그림 모델로 렌더 검토) 와 opencode 에이전트 (셸 기본 ask · 에어록과 테스트 명령만 allow · claude · curl · PowerShell · 웹 가져오기 deny · 편집은 작업 폴더만) · /consult 명령을 만든다. 스킬에는 Claude 를 부르는 다른 길을 적지 않는다 (AL-01 · AL-09). T2 의 우회 시나리오를 다시 돌려 기록한다.", "tier": "Tier 1", "difficulty": "High", "effort_level": 7, "assigned_model": "claude-opus-5.5", "agent_role": "Orchestration_Designer", "expected_output": "skills/ · opencode 에이전트 · 명령 · 우회 재시험 기록", "dependencies": ["T12"]},
    {"task_id": "T14", "task_name": "통합 적대 검증", "description": "가짜 Claude 서버로 전 경로를 돌려 카나리아 1,000 시나리오에서 바깥 바이트의 카나리아 0 (G1) 을 확인하고, 막는 쪽 실패 (G2) 의 모든 경우를 일으키고, 확정 건너뛰기 · 설정 덮어쓰기 · 사전 바꿔치기 · 환경 변수 · 다른 데이터 폴더로 비켜 가기를 시도한다. 저장소에 사내 정보 · 키 흔적이 없는지, 감사 기록에 가명 표 · 원문이 없는지, 돌아온 HTML 의 외부 주소가 빠지는지 본다. 결함마다 실패하는 테스트를 붙여 보고한다.", "tier": "Tier 0", "difficulty": "Extreme", "effort_level": 10, "assigned_model": "claude-opus-5.5", "agent_role": "Security_Integrity_Auditor", "expected_output": "검증 보고서 · 결함마다 실패하는 테스트", "dependencies": ["T10", "T11", "T12", "T13"]},
    {"task_id": "T15", "task_name": "문서 · 설치 절차", "description": "README · docs/MANUAL.md (첫머리에 이 도구가 못 하는 것 · 남는 위험 · 설정 · 사전 등록 · 감사 기록 · 알려진 한계 S-09) · INSTALL.md (opencode 가 따라 하는 절차 · 규칙 절 · 단계마다 확인 · [질문] · opencode 설정 폴더에 스킬 · 에이전트 복사 · Claude Code 훅 · 업데이트 · 제거) 를 쓴다. 숫자는 돌려서 얻은 값만 적는다.", "tier": "Tier 3", "difficulty": "Medium", "effort_level": 5, "assigned_model": "claude-sonnet", "agent_role": "Documentation_Specialist", "expected_output": "문서 셋 · 깨진 링크 없음", "dependencies": ["T11", "T13"]}
  ]
}
```

### C 조사 원자료

- Claude Code CLI 문서 (`code.claude.com/docs/en/cli-reference` · 2026-11-05 읽음): `-p` · `--tools ""` (내장 도구 모두 끔 · MCP 도구는 따로) · `--disallowedTools "*"` · `"mcp__*"` · `--strict-mcp-config` · `--restricted` (v2.1.248 이상 · 명령 실행 도구와 WebFetch 를 빼고 관리형 설정과 `--settings` 만 읽음) · `--bare` (Bash · 파일 도구는 남음) · `--no-session-persistence` · `--system-prompt-file` · `--setting-sources` · `--max-turns` · `--output-format json`.
- Claude Code hooks 문서 (`code.claude.com/docs/en/hooks` · 2026-11-05 읽음): `UserPromptSubmit` 종료 코드 2 = 프롬프트가 Claude 에 닿지 않음 · `PreToolUse` deny · `PostToolUse` 는 이미 돈 뒤 (`updatedToolOutput` 으로 결과를 바꿀 수 있다는 언급 — 세부 미확인) · 시간 초과한 `PreToolUse` 훅은 막지 않음 → `onFailure: "block"` (v2.1.295 이상) · 관리형 설정 `allowManagedHooksOnly` · "훅은 보조 장치, 단단한 허용 · 거부는 권한 체계로".
- Anthropic 1차 API 정가표 (Claude API 스킬 문서 · 2026-10-06 캐시): Opus 5 $5 / $25 · Sonnet 5 $2 / $10 (100만 토큰당 입력 / 출력).
- works 안의 선례: Subordinate–1 3판의 `policy.external_real_data` 문턱 (git 기록 `4cf84a3`) — 같은 생각을 이 도구의 AL-10 으로 이어받았다. 그때 적은 대로 그 문턱은 과속방지턱이지 벽이 아니다. 이 도구는 그 벽을 세우려는 것이 아니라, 벽이 없다는 것을 알고 겹을 쌓는다.
