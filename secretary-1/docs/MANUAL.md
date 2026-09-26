# Secretary–1 매뉴얼

사내 일정 비서. 텍스트로 대화하면 일정을 조회·제안·정리하고, **확정 버튼을 눌러야만** 캘린더에 반영합니다.
사내 LLM(OpenAI 호환 API)에 붙고, 내 PC에서만 돕니다. 소개는 [README](../README.md), 설치 절차는 [INSTALL.md](../INSTALL.md)에 있습니다.

- **파일 하나** — `secretary-1.py`만 있으면 실행됩니다. 표준 라이브러리만 씁니다 (Outlook 연동 때만 `pywin32`)
- **제안 → 확정** — 만들기·바꾸기·지우기는 카드로 먼저 보여주고, 확정 전엔 캘린더를 건드리지 않습니다. 확정 뒤 20초 안에는 되돌리기
- **로컬 학습** — "앞으로 스크럼은 15분으로 잡아" (학습 카드 **확정** 후) 또는 `/학습 …` → `secretary-1-rules.json`에 저장, 모든 제안·정리에 우선 적용
- **일정 위키** — "내일 김과장 미팅 준비물은 견적서랑 노트북, 안건은 단가 협상" → 목적·안건·준비·참석자·결정·메모·링크로 정리한 위키 카드 → **확정**. 반복 회의는 같은 제목 일정 모두에 붙고, 다음 일정 칸의 `위키` · 일정 서랍의 `W` · **Alt+W** · `/위키` 로 언제든 열고, 알림에는 준비물이 같이 뜹니다. "이따 회의 준비물 뭐였지?"라고 물어도 위키를 보고 답합니다 (`secretary-1-wiki.json`)
- **윈도우 알림** — 장소 있는 일정 15·5·1분 전, 장소 없는 일정 5·1분 전
- **내 PC 전용** — `127.0.0.1`에만 열리고 대화는 저장하지 않습니다 (확정한 위키 카드의 '원문 기록'만 `secretary-1-wiki.json`에 — 카드에 미리 보입니다). 밖으로 나가는 통신은 설정한 LLM 주소뿐
- **도스 픽셀 폰트 내장** — 한글 11,172자가 들어간 GNU Unifont 부분집합을 `secretary-1.py` 안에 넣었습니다. 설치·인터넷 없이 그대로 보입니다

## 설치 — OpenCode 에게 맡기기 (권장)

OpenCode 에 아래를 붙여넣으면 [`INSTALL.md`](../INSTALL.md) 순서대로 `D:\OPENCODE\secretary-1` 에 설치합니다. Terminal–1 과 같은 works 저장소(`D:\OPENCODE`)를 씁니다.

```text
Secretary–1 을 설치해줘. works 저장소를 D:\OPENCODE 에 받고, 프로그램 폴더는 D:\OPENCODE\secretary-1 이야.
1. 코드 받기: D:\OPENCODE 가 없거나 비어 있으면 git clone https://github.com/leebobegogigug-blip/Works.git "D:\OPENCODE"
   (이미 works 가 받아져 있으면 받지 말고, git 이 안 되면 Works-repo.zip 을 D:\OPENCODE 에 풀어)
2. 그다음 D:\OPENCODE\secretary-1\INSTALL.md 를 끝까지 읽고 그 순서대로만 진행해.
   API 키·토큰은 절대 출력하지 말고, [질문] 표시가 있는 곳에서는 나한테 물어봐.
```

LLM 설정은 OpenCode 설정(`opencode.json`)에서 `--setup` 이 그대로 가져옵니다. 키 값은 화면·대화 어디에도 찍히지 않습니다.

## 직접 설치 (Windows · Python 3.8+)

```bat
git clone https://github.com/leebobegogigug-blip/Works.git "D:\OPENCODE"
cd /d D:\OPENCODE\secretary-1
python secretary-1.py --setup           :: OpenCode 설정에서 LLM 값 가져오기 + 점검 (config.json · secretary-1.bat 생성)
python secretary-1.py --test-notify     :: 윈도우 알림이 뜨는지 확인
python secretary-1.py --autostart on    :: (선택) 로그인할 때 자동 실행
```

그다음부터는 `secretary-1.bat`을 더블클릭하거나, 어디서든 **Ctrl+Alt+J**. 설정 바꾸기는 `python secretary-1.py --set "키=값"` (예: `--set "llm.tool_mode=json"`).

## 설정 (`config.json`)

| 키 | 설명 |
|---|---|
| `llm.base_url` | 사내 LLM 주소 (OpenAI 호환, 보통 `…/v1`) |
| `llm.model` · `llm.api_key` | 모델 이름 · 키. 키는 `"{env:환경변수이름}"` · `"{file:경로}"` 참조도 됩니다 (OpenCode 와 같은 문법) |
| `llm.models` | 화면 아래 **모델 드롭다운**에 늘 보일 모델 목록 (선택). 서버의 `/v1/models` 목록과 합쳐 보여 주고, 고르면 `llm.model` 에 저장. `--setup` 이 OpenCode 설정의 모델들을 넣어 둠 |
| `llm.tool_mode` | `auto`(기본) · `native` · `json` — 도구 호출이 불안정하면 `json` |
| `llm.proxy` · `llm.ca_file` | 프록시 (`""` = 안 씀) · 사내 인증서 PEM (SSL 오류 날 때만) |
| `calendar.backend` | `local`(기본, `secretary-1.db`) · `outlook`(클래식 Outlook + `pip install pywin32`) |
| `alerts` | `with_location` `[15, 5, 1]` · `without_location` `[5, 1]` · `windows_toast` |
| `reminder_minutes` | Secretary–1 로 만든 Outlook 일정의 Outlook 자체 알림(분). 알림이 겹치면 `0` |
| `work_hours` | 업무시간·요일 — 빈 시간 찾기와 경고 기준 |
| `theme` | `dark`(기본, 검정 바탕) · `light`(밝은 회색 본체) · `system` — 둘 다 네이비 주색 · 라임 강조 |
| `hotkey` | 전역 단축키 (기본 `ctrl+alt+j`, `""`이면 끔) |

전체 기본값은 [`config.example.json`](../config.example.json), 설명은 `secretary-1.py` 맨 위에 있습니다.

## 쓰는 법

- 화면 맨 아래: `로컬 저장`(일정·학습 규칙·위키는 이 PC 파일에만, 대화는 끄면 사라짐) · **모델 드롭다운** (바꾸면 다음 실행에도 유지)
- "내일 3시 김과장 미팅 잡아줘" → 제안 카드 → **확정** (Ctrl+Enter · `ㅇㅇ`) / 취소 (Esc · `ㄴㄴ`)
- 확정한 뒤 **20초 안에는 되돌리기** (카드의 버튼 · **Ctrl+Z**). 그 사이 Outlook 에서 바뀌었으면 건드리지 않습니다
- 위키는 서랍에서 **직접 고치기**도 됩니다 (목록 칸은 한 줄에 하나 · Ctrl+Enter 저장)
- 빠른 키 **Alt+1~4** (① 오늘 ② 내일 ③ 이번 주 ④ 빈 시간) · 오늘 일정 펼치기 **Alt+D** · 학습 서랍 **Alt+M** · 일정 위키 **Alt+W**
- 명령어: `/학습 <규칙>` · `/잊어 r3` · `/규칙` · `/위키 [검색]` · `/알림` · `/도움`

## 화면

| # | 구역 | 보여 주는 것 |
|---|---|---|
| 01 | **NEXT** | 다음 일정까지 남은 시간 (진행 중이면 끝날 때까지 · 알림 시각부터 깜빡임) · 장소 · 위키 버튼 · 얼굴 |
| 02 | **TODAY** | 오늘 한 줄 트랙 (지난 일정은 빗금 · 지금은 라임) · 남은 개수 → 누르면 일정 서랍 |
| 03 | **LOG** | `시각 · 기호 · 내용` 로그 줄 · 제안 카드 · 도구 호출 줄 |
| 04 | **DECK** | 노브 네 개(Alt+1~4) · 고무 키 M 학습 · W 위키 |

## 디자인

works 공통 규격(원칙 일곱 가지 · 팔레트 · 아이콘)은 [docs/DESIGN.md](../../docs/DESIGN.md) 에 있습니다. Secretary–1 에서는 이렇게 보입니다.

| # | 원칙 | Secretary–1 에서 |
|---|---|---|
| 1 | **한 화면 = 한 모드** | 다음 일정까지 남은 시간 하나를 7세그먼트로 크게 · 노브 네 개 |
| 2 | **색 = 조작** | 노브 ①파랑 ②라임 ③흰색 ④회색 — works 공통 인코더 순서. 번호표도 그 색 |
| 3 | **번호 붙은 구역** | `01 NEXT` · `02 TODAY` · `03 LOG` · `04 DECK` · 서랍 `01` `02` `03` · `/도움` |
| 4 | **엔지니어링을 숨기지 않기** | 로그 줄의 도구 호출(`└ → propose_create`) · LED `llm` `cal` · 모델 드롭다운 |
| 5 | **즉각 반응** | 누른 노브의 눈금이 돈다 · 확정 도장 · 되돌리기 초읽기 |
| 6 | **사각 격자** | 8px 점 격자 · 각진 모서리 · 가는 선 · 앞자리 0 |
| 7 | **캐릭터** | Secretary–1 의 얼굴 — 네모 화면 · 노브 · 안테나 불빛. 표정 8가지 |

경고는 빨강 대신 가장 밝은 글자색 + `ERR` 칩으로 합니다. 테마는 `dark`(기본) · `light` · `system` 셋 다 있습니다.

## 개발

| 할 일 | 명령 |
|---|---|
| UI 수정 | `ui.html` 수정 → `python build.py` (secretary-1.py에 내장됨 · `INDEX_HTML`을 직접 고치지 말 것) |
| 반영 확인 | `python build.py --check` (UI · 폰트 둘 다) |
| 폰트 다시 만들기 (선택) | `pip install fonttools` → `python tools/make_font.py <unifont.otf>` → `python build.py` |
| 테스트 | `python -m unittest tests.test_secretary` (표준 라이브러리만 · 공개 명령은 `ExportEvents`) |
| works 규칙 검사 | 저장소 루트에서 `python tools/works_check.py` ([RULES.md](../../RULES.md)) |
| 브라우저 E2E (선택 · CI 에서는 자동) | `pip install playwright` → `python -m playwright install chromium` → `python tests/e2e_ui.py` (시간대는 알아서 낮으로 맞춤) |

`tests/fake_llm_server.py`는 OpenAI 호환 가짜 서버라서 사내 LLM 없이도 전체 흐름을 돌려볼 수 있습니다.
CI(`.github/workflows/secretary-1.yml`)는 Windows · Ubuntu × Python 3.8 · 3.13 에서 `build.py --check` 와 단위 테스트를, Ubuntu 에서 브라우저 E2E 를 돌립니다.

## 공개 명령

다른 works 도구가 Secretary–1 의 일정을 읽는 유일한 길입니다 ([RULES.md › W-01](../../RULES.md#w-01-폴더--앱--명령) · [대장 › 공개 명령](../../docs/REGISTRY.md#공개-명령)). 지금은 [Report–1](../../README.md) 이 주간보고의 근거로 씁니다.

```text
python secretary-1.py --export-events --from 2026-09-21 --to 2026-09-27
```

```json
{"app": "secretary-1", "version": "0.6.0", "format": 1, "backend": "local",
 "from": "2026-09-21T00:00", "to": "2026-09-28T00:00",
 "events": [{"id": "L1", "title": "주간회의", "start": "2026-09-21T10:00", "end": "2026-09-21T11:00",
             "all_day": false, "location": "3A", "recurring": false}]}
```

- `--from` · `--to` 는 `YYYY-MM-DD`, 두 날 모두 포함합니다. 설정한 캘린더(local · outlook)를 그대로 읽습니다
- **읽기만 합니다.** 설정 · 일정 DB 를 만들거나 고치지 않고, 예전 이름 이전이나 실행기 만들기도 하지 않습니다. 비서가 켜져 있어도 됩니다
- 일정의 **메모는 내주지 않습니다.** 제목 · 시각 · 장소 · 종일 · 반복 여부만
- 표준 출력에 UTF-8 JSON 한 줄. 실패하면 `"error"` 와 함께 종료 코드 1, 날짜가 틀리면 2
- 모양을 바꾸면 `format` 을 올립니다 (`EXPORT_FORMAT`). 부르는 쪽은 모르는 `format` 이면 일정 없이 동작합니다

## 커밋하면 안 되는 것

`config.json`(API 키) · `secretary-1.db`(일정) · `secretary-1-rules.json`(학습 규칙) · `secretary-1-wiki.json`(일정 위키) · `secretary-1.bat`(PC별 경로) — 모두 `.gitignore`에 들어 있습니다.

예전 이름(jaba)의 `jaba.db` · `jaba_rules.json` · `jaba_wiki.json` · `jaba.bat` · 자동 실행 `jaba.lnk` 는 `secretary-1.py` 를 처음 실행할 때 새 이름으로 옮겨집니다 (켜져 있는 예전 비서는 먼저 끕니다). 환경변수 `JABA_*` 도 계속 읽고, 새 이름은 `SECRETARY_BASE_URL` · `SECRETARY_API_KEY` · `SECRETARY_MODEL` 입니다.

## 알려진 한계

- Outlook: 반복 일정·회의 초대는 읽기만 하고(변경은 Outlook에서) 초대 메일은 보내지 않습니다. 새 Outlook은 지원하지 않습니다
- 윈도우 알림은 PowerShell로 띄웁니다. 회사 정책이 막으면 앱 안 알림으로만 동작합니다 (`--test-notify`로 확인)
- 알림은 Secretary–1 이 켜져 있을 때만 옵니다
- 설정 · 일정 · 학습 규칙 · 위키 파일은 프로그램 폴더(`D:\OPENCODE\secretary-1`)에 있습니다. works 규칙은 저장소 밖(`%LOCALAPPDATA%`)이지만, 이름을 바꾸며 이미 한 번 옮긴 파일을 또 옮기지 않으려고 그대로 둡니다 ([예외 대장](../../docs/REGISTRY.md#예외-대장)). `.gitignore` 로 커밋은 막혀 있지만, `git clean -xfd` 같은 명령은 이 파일들을 지웁니다
- 픽셀 폰트는 윈도우 배율 100%·200%에서 가장 선명하고, 125%·150%에선 살짝 부드럽게 보입니다. 한자·이모지는 시스템 글꼴로 나옵니다

## 라이선스

내장 폰트는 [GNU Unifont](https://unifoundry.com/unifont/) 15.1.01의 부분집합이고 SIL Open Font License 1.1을 따릅니다 ([`fonts/OFL.txt`](../fonts/OFL.txt)).
저작권 표기와 라이선스 전문은 `secretary-1.py` 맨 아래와 폰트 파일 안에도 들어 있습니다.
