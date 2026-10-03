# Analysis–1 — 에이전트 규칙

> **적용 범위.** 이 파일은 이 저장소 (`analysis-1`) 의 코드 · 문서를 **고치는** 작업에만 적용한다.
> 앱 설치 (`INSTALL.md` 따라 하기 — M1-a 부터) · 앱 사용 중이라면 이 파일을 무시하고 원래 지시를 따른다.
>
> **works 규칙은 이 저장소에 적용되지 않는다.** 이 폴더는 `D:\OPENCODE` (works 저장소) 안에 있어, 도구가 위 폴더의 works `AGENTS.md` · `CLAUDE.md` 를 함께 읽을 수 있다. 그 파일은 works 를 고칠 때만 쓴다. 이 저장소의 규칙은 [RULES.md](RULES.md) (AN) 이고, works 조항은 RULES.md 가 번호로 채택한 만큼만 쓴다 (예: works W-02 '표준 라이브러리만' 대신 AN-02 'DuckDB 하나').

## 시작하기 전에

1. [RULES.md](RULES.md) (무엇을 지키나) → works [DEVELOP.md](https://github.com/leebobegogigug-blip/Works/blob/447758f4b43ebafe7b3ec89acf7eec458ea2e27e/docs/DEVELOP.md) (어떻게 일하나 — D-01–D-11 을 채택) 순서로 끝까지 읽는다. DEVELOP 은 아래 표대로 바꿔 읽는다.
2. 화면 · 문서 · 이미지를 만지면 [DESIGN.md](DESIGN.md) 와 works [DESIGN.md](https://github.com/leebobegogigug-blip/Works/blob/447758f4b43ebafe7b3ec89acf7eec458ea2e27e/docs/DESIGN.md) 도 읽는다. 사내 LLM 기능이면 works [SPEC-llm.md](https://github.com/leebobegogigug-blip/Works/blob/447758f4b43ebafe7b3ec89acf7eec458ea2e27e/docs/SPEC-llm.md) (S-09).
3. 기획 · 설정 값 (포트 · 환경 변수 · 데이터 폴더) 은 [docs/PLAN.md](docs/PLAN.md) 에 있다 — 설정 표는 15 › B.
4. 규칙과 부딪히는 요청을 받으면, 하기 전에 어느 AN 과 부딪히는지 사용자에게 말하고 답을 기다린다 (D-02). 예외 대장 길은 없다.
5. works 파일을 옮겨 오거나 works 문서를 따라 고치면 [docs/UPSTREAM.md](docs/UPSTREAM.md) 를 같이 고친다.

| works DEVELOP 에서 | 이 저장소에서 |
|---|---|
| 헌법 W | AN ([RULES.md](RULES.md)) |
| `python tools/works_check.py` | `tests/test_rules.py` 와 CI — M1-a 전에는 없다 |
| 대장 (REGISTRY.md) | [docs/PLAN.md](docs/PLAN.md) › 15 › B 설정 표 |
| 예외 대장 | 없음 — AN 을 고치는 PR 로 간다 |

나머지 바꿔 읽기는 [RULES.md › 작업 방식](RULES.md#작업-방식).

## 규칙 요약 — 정본은 RULES.md

- AN-01 **저장소 = 앱** — 저장소 루트가 앱 폴더 · 명령 `analysis-1.py`. works 앱과 코드를 공유하지 않고 사본으로 옮긴다
- AN-02 **실행 의존성** — 표준 라이브러리 + DuckDB 하나 (버전 하나로 고정) · 앱 코드는 Python 3.8 문법 · 엔진이 없으면 `--version` · `--help` · `--check` 만
- AN-03 **내 PC 에서만** — `127.0.0.1` · 실행마다 새 토큰 · 밖으로는 사용자가 설정한 LLM 주소만 · 엔진 확장 · 외부 접근 잠금
- AN-04 **비밀** — 화면 · 로그 · 명령줄 · 커밋 · 대화 기록 어디에도 찍지 않는다
- AN-05 **기록은 이 PC 에** — 대화 · 조작 기록 · 판정 카드를 데이터 폴더에 · '기록 중' 표시 · 끄기 · 지우기
- AN-06 **저장은 깨지지 않게** — 버전 · 원자적 쓰기 · `%LOCALAPPDATA%\analysis-1` · 엔진 사본 수명 주기
- AN-07 **주체는 사용자** — 모든 조작은 손으로 · 조수는 제안 카드만 (Enter 적용 · Esc 버림) · 확정은 사용자만
- AN-08 **설치는 에이전트가, 되돌릴 수 있게** — INSTALL 필수 절 · 관리자 권한 금지 · `D:\OPENCODE\analysis-1` · git 길이 기본
- AN-09 **디자인** — 화면 틀은 works DESIGN 그대로 · 차트 데이터 표지만 데이터 팔레트 · 선택 · 마킹은 lime
- AN-10 **약속은 CI 가** — Windows + Ubuntu × 최소 · 최신 Python · 가짜 LLM · 엔진 job 은 건너뛰기를 실패로
- AN-11 **사내 정보 금지** — 비공개여도 · 합성 데이터만 · 영감 고지문 · 글꼴 라이선스

## 끝내기 전에

- 검사: 지금 (M0) 은 앱 코드 · `tests/` · `docs/MANUAL.md` 가 없다. 문서만 고쳤으면 상대 링크 · works 고정 링크 · 표기 (` · ` · `›` · en dash · 이모지와 폭 2칸 기호 없음) 를 손으로 보고, 돌리지 못한 검사는 돌리지 못했다고 쓴다. M1-a 부터는 `docs/MANUAL.md` › 개발 절의 검사와 `python -m unittest discover -s tests` (`tests/test_rules.py` 포함) 를 돌린다.
- 커밋: 한국어 `analysis-1: 무엇 · 무엇` (S-08 · D-10). 작업 가지에서 PR 로 낸다.
- 사내 LLM 은 works SPEC-llm 의 설정 키 · 명령을 따른다 (S-09).
- 키 · 토큰은 출력하지 않는다 (AN-04). 사내 정보는 비공개 저장소에도 커밋하지 않는다 (AN-11).
- 보고는 works [DEVELOP.md › D-11](https://github.com/leebobegogigug-blip/Works/blob/447758f4b43ebafe7b3ec89acf7eec458ea2e27e/docs/DEVELOP.md#d-11-보고는-한-모양으로) 틀로 한다. 돌리지 못한 검사는 못 돌렸다고 쓴다.
