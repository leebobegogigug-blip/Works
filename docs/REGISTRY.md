# works 대장

앱마다 이름 · 자리 · 자원을 적어 두는 곳이다 ([RULES.md › S-06](../RULES.md#규약)).
새 앱은 **코드보다 먼저** 여기에 한 줄을 넣는 PR 을 낸다. 검사기가 이 표를 읽으니 형식(표 · 백틱 · 대역 표기)을 바꾸지 않는다.

## 앱 대장

| 폴더 · 명령 | 이름 | 한 줄 | 유형 | 상태 | 데이터 폴더 | 포트 | 전역 단축키 | 환경 변수 | 캐릭터 · 부품 | 예전 이름 |
|---|---|---|---|---|---|---|---|---|---|---|
| `secretary-1` | Secretary–1 | 말하면 잡아 주는 일정 비서 | 웹형 | 운영 | 프로그램 폴더 (예외 W-06) | 8765–8774 | Ctrl+Alt+J | `SECRETARY_*` | 네모 화면 얼굴 | jaba · 이전 코드 지울 때 미정 |
| `terminal-1` | Terminal–1 | opencode 여러 개를 한 창에서 | 터미널형 | 운영 | `%LOCALAPPDATA%\terminal-1` | 4096–4195 | — | `OPENCODE_SERVER_PASSWORD` (opencode 것) | TQ–1 펫 | ocmux · 이전 코드 지울 때 미정 |

- **상태**: `예정`(등록만, 폴더 없음) · `운영` · `은퇴`
- **포트**: 앱이 쓰는 대역 전체. 겹치면 검사기가 경고한다. 다음 빈 대역은 `8775–8784` 부터 10개씩.
- **전역 단축키**: 없으면 `—`. 같은 키를 두 앱이 가질 수 없다.
- **환경 변수**: 앱 이름 접두어를 대문자로 (`SECRETARY_*`). 다른 프로그램의 변수를 읽기만 하면 그 이름을 적는다.

## PC 에 남기는 것

제거 절차([RULES.md › W-08](../RULES.md#w-08-설치는-에이전트가-되돌릴-수-있게))가 되돌려야 하는 목록이다.

| 앱 | 남기는 것 | 되돌리기 |
|---|---|---|
| `secretary-1` | 프로그램 폴더 안의 `config.json` · `secretary-1.db` · 학습 규칙 · 위키 · `secretary-1.bat` · 시작 프로그램 `secretary-1.lnk` (`--autostart on` 일 때) | `--stop` · `--autostart off` · 설정 · 데이터 파일 지우기 ([INSTALL.md › 제거](../secretary-1/INSTALL.md#제거)) |
| `terminal-1` | 사용자 PATH · Windows Terminal 색 테마 `Terminal-1 Black` (조각 파일) · (선택) 글꼴 Unifont 와 HKCU 글꼴 등록 · Windows Terminal `settings.json` 글꼴 설정 · 펫 저장 · 채널 목록 `%LOCALAPPDATA%\terminal-1` · headless opencode 서버 | [INSTALL.md › 제거](../terminal-1/INSTALL.md#제거) — 채널 `rm` · PATH · 색 테마 · 글꼴 · 데이터 순서 |

## 예외 대장

이미 있는 앱이 아직 못 지키는 조항이다. **여기 없는 위반은 위반이다.**

- **파일**: 예외가 덮는 범위. `*` 는 앱 폴더 전체, 여러 개는 쉼표로 구분.
- **기한**: `YYYY-MM-DD` 가 지나면 검사기가 `기한 지남` 으로 알린다. 날짜가 아니면(`영구` 등) 기한 없이 적어 둔다.
- 고치면 그 줄을 지운다. 검사기는 걸리는 것이 없는 줄을 "지워도 됨" 으로 알려 준다.

| 앱 | 조항 | 파일 | 내용 | 기한 |
|---|---|---|---|---|
| `secretary-1` | W-06 | * | 데이터(`config.json` · `secretary-1.db` · 학습 규칙 · 위키)가 프로그램 폴더에 있다. 세 번째 이전을 피하려고 그대로 둔다. `.gitignore` 로 커밋을 막는다 | 영구 — 다음 이름 변경이나 저장 형식 변경 때 다시 본다 |
| `terminal-1` | W-10 | terminal-1.ps1, t1_term.py | 예전 이름(ocmux)의 탭 색 변환표 — 옛 색을 읽어 새 색으로 바꾸는 데이터라 옛 색이 들어 있다 | ocmux 이전 코드와 함께 지운다 |
