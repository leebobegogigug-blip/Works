# Report–1 설치 가이드 — OpenCode 에이전트용

> **사람용 한 줄:** OpenCode 에 아래 프롬프트를 붙여넣으면 이 문서대로 설치합니다.
> Report–1 은 works 저장소(`https://github.com/leebobegogigug-blip/Works`)의 `report-1` 폴더입니다.
>
> ```text
> Report–1 을 설치해줘. works 저장소를 D:\OPENCODE 에 받고, 프로그램 폴더는 D:\OPENCODE\report-1 이야.
> 1. 코드 받기: D:\OPENCODE 가 없거나 비어 있으면 git clone https://github.com/leebobegogigug-blip/Works.git "D:\OPENCODE"
>    (이미 works 가 받아져 있으면 받지 말고, git 이 안 되면 Works-repo.zip 을 D:\OPENCODE 에 풀어)
> 2. 그다음 D:\OPENCODE\report-1\INSTALL.md 를 끝까지 읽고 그 순서대로만 진행해.
>    API 키·토큰은 절대 출력하지 말고, [질문] 표시가 있는 곳에서는 나한테 물어봐.
> ```

---

이 아래는 **OpenCode(에이전트)가 실행할 절차**입니다.

## 0. 목표와 규칙

**목표**: `D:\OPENCODE\report-1` 의 Report–1 이 사내 LLM 점검을 통과하고, 창이 뜨는 상태로 끝낸다.
설정과 데이터는 `%LOCALAPPDATA%\report-1\` 에 생긴다 (프로그램 폴더에는 아무것도 만들지 않는다).

**규칙 — 반드시 지킬 것**

1. **명령은 이 문서에 적힌 것만** 실행한다. 모든 명령은 Git Bash · cmd · PowerShell 어디서나 그대로 동작하게 적혀 있다 (경로는 항상 큰따옴표).
2. **비밀 금지**: `opencode.json` · `opencode.jsonc` · `auth.json` · `%LOCALAPPDATA%\report-1\config.json` 을 읽기 도구나 `cat`/`type`/`Get-Content` 로 열거나 출력하지 않는다. LLM 설정 옮기기는 `--setup` 이 하고, 키 값은 어디에도 표시하지 않는다. 사용자가 키를 채팅에 붙여넣으려 하면 말린다.
3. **사용자 자료를 읽지 않는다**: `%LOCALAPPDATA%\report-1\topics\` · `reports\` 는 사용자가 붙여 넣은 원문과 보고서다. 열거나 출력하지 않는다.
4. **관리자 권한 · 레지스트리 · 시스템 설정 변경 금지.** 시작 메뉴 바로가기는 4단계에서 사용자가 원할 때만.
5. **[질문]** 표시가 있는 곳에서는 멈추고 사용자에게 묻는다.
6. 출력이 예상과 다르면 추측해서 우회하지 말고, 출력을 그대로 보여 주고 [문제 해결](#문제-해결) 표를 따른다. 표에 없으면 멈추고 보고한다.
7. 명령은 한 번에 하나씩 실행하고, 결과를 확인한 뒤 다음으로 간다.

## 1. 파이썬 확인

```text
python --version
```

- **확인**: `Python 3.8` 이상이면 통과.
- **실패하면**: `py -3 --version` 을 실행한다. 이게 되면 **이후 모든 명령의 `python` 을 `py -3` 으로 바꿔서** 실행한다. 이것도 안 되면 **[질문]** 사용자에게 파이썬 설치를 부탁하고 (회사 소프트웨어 센터나 python.org, 설치할 때 "Add python.exe to PATH" 체크) 멈춘다.

## 2. 코드 받기

```text
python -c "import os; print(os.path.isfile(r'D:\OPENCODE\report-1\report-1.py'))"
```

- **확인**: `True` 면 3단계로.
- **실패하면**: `D:\OPENCODE` 의 상태를 본다.

```text
python -c "import os; r=r'D:\OPENCODE'; print('git' if os.path.isdir(os.path.join(r, '.git')) else ('empty' if not os.path.isdir(r) or not os.listdir(r) else 'other'))"
```

| 결과 | 할 일 |
|---|---|
| `empty` | `git clone https://github.com/leebobegogigug-blip/Works.git "D:\OPENCODE"` · git 이 없거나 막혔으면 **[질문]** 저장소 zip 을 `D:\OPENCODE` 에 풀어 달라고 부탁한다 (폴더가 한 겹 더 생기면 이 문서의 경로를 모두 그쪽으로 바꾼다) |
| `git` | 다른 works 도구가 이미 받아 두었다. `git -C "D:\OPENCODE" pull --ff-only` 로 업데이트만. 실패하면 [문제 해결](#문제-해결) |
| `other` | **[질문]** 다른 파일이 있는 폴더다. 목록을 보여 주고 어떻게 할지 묻는다. 아무것도 지우거나 옮기지 않는다 |

## 3. 설정 + 점검

```text
python "D:\OPENCODE\report-1\report-1.py" --setup
```

하는 일: `%LOCALAPPDATA%\report-1\config.json` 만들기 → OpenCode 설정에서 사내 LLM 의 주소 · 모델 · 키 · 헤더를 옮기기 (키는 표시 안 함) → 점검. 마지막 줄의 **결과**로 판단한다.

| 마지막 줄 | 할 일 |
|---|---|
| `결과: OK` | 4단계로 |
| `결과: 확인 필요` + `provider 가 여러 개입니다 → … : a, b` | **[질문]** 사내 LLM 이 어느 것인지 묻고 → `python "D:\OPENCODE\report-1\report-1.py" --setup --provider "a"` |
| `결과: 확인 필요` + `모델이 여러 개입니다 → … : x, y` | **[질문]** 어느 모델을 쓸지 묻고 → `… --setup --provider "a" --model "x"` |
| `결과: 확인 필요` + `OpenCode 설정 파일…을 찾지 못했습니다` · `OpenAI 호환 provider … 가 없습니다` | **[질문]** "사내 LLM 없이 기본 초안(자료를 그대로 묶기)만 쓸까요, 주소를 알려 주시겠어요?" → 주소를 받으면 `--set "llm.base_url=<주소>" --set "llm.model=<모델>"` (**키는 받지 않는다** — 필요하면 사용자가 `config.json` 에 직접 넣거나 `--set "llm.api_key={env:환경변수이름}"`). 그다음 `--setup` 을 다시. 기본 초안만이면 `--check` 로 끝 |
| `결과: 점검 실패` | [문제 해결](#문제-해결) 표대로 고치고 `python "D:\OPENCODE\report-1\report-1.py" --check` → `결과: OK` 가 될 때까지 |

점검 출력의 `양식` 줄에 기본 양식 다섯 가지와 `자료 한도 20,000자` 가 보인다.
**[질문]** "회사에서 쓰는 보고서 양식이 따로 있나요? (칸 이름만 알려 주시면 됩니다)" → 있으면

```text
python "D:\OPENCODE\report-1\report-1.py" --set "report.forms.<양식 이름>=<칸1>;<칸2>;<칸3>"
```

(예: `--set "report.forms.주간 점검=현황;이슈;다음 주 계획"` · 쓰지 않는 기본 양식은 `--set "report.forms.검토 보고="` 로 지운다)

**[질문]** "화면 위 이름 옆에 회사 이름을 작게 넣을까요?" → 넣는다면 `python "D:\OPENCODE\report-1\report-1.py" --set "company=<회사 이름>"` (24자까지 · 이 PC 설정에만 저장)

## 4. 시작 메뉴 바로가기 (선택)

**[질문]** "시작 메뉴에 Report–1 바로가기를 만들까요? (지울 때는 --shortcut off)"
예라면:

```text
python "D:\OPENCODE\report-1\report-1.py" --shortcut on
```

`바로가기 만듦:` 이 나오면 성공. 실패하면 출력을 그대로 보고하고 넘어간다 (바로가기 없이도 `python report-1.py` 로 켠다).

## 5. 실행하고 확인

에이전트 셸이 끝나도 꺼지지 않게 따로 띄운다:

```text
python -c "import subprocess, sys; subprocess.Popen([sys.executable, r'D:\OPENCODE\report-1\report-1.py'], creationflags=0x00000208, close_fds=True)"
python "D:\OPENCODE\report-1\report-1.py" --status
```

- `실행 중: http://127.0.0.1:…/` → **[질문]** "Report–1 창이 떴나요? 아무 메일이나 복사해서 창에 붙여 넣어 보세요 (Ctrl+V). 왼쪽에 '자료 1' 이 생기면 성공입니다."
- `꺼져 있음` → `--status` 를 한 번 더. 그래도 꺼져 있으면 사용자에게 시작 메뉴의 Report-1 (또는 `python "D:\OPENCODE\report-1\report-1.py"`)을 직접 실행해 달라고 한다.

창을 닫으면 30분 뒤 저절로 꺼진다 (`idle_exit_min`). 단, 보관 안 한 자료가 있으면 꺼지지 않고 기다린다 — 다시 열면 그대로 있다.

## 6. 완료 보고

아래 형식으로 사용자에게 보고한다. **키 값은 쓰지 않는다.**

```text
Report–1 설치 완료
- 위치     : D:\OPENCODE\report-1 (버전 · python "D:\OPENCODE\report-1\report-1.py" --version)
- 데이터   : %LOCALAPPDATA%\report-1 (보관한 토픽 · 확정한 보고서)
- 파이썬   : (1단계 결과)
- LLM      : (주소) · (모델) · 키 (설정됨 / 참조 / 없음) — 또는 '없음 · 기본 초안'
- 양식     : (점검의 양식 줄)
- 바로가기 : 시작 메뉴 / 안 함
- 상태     : 실행 중 (주소)
- 쓰는 법  : 토픽 적기 → 메일 · 메신저 · 메모 · 표를 그냥 붙여 넣기 → [초안 만들기] → 근거 칩 확인 · 고치기 → [확정] (클립보드로)
             며칠에 걸쳐 모을 때는 [보관] (Ctrl+S) — 보관해야 원문이 저장된다
```

---

## 문제 해결

`--setup` / `--check` 출력이나 창의 알림에 나온 문구로 찾는다. 고친 뒤에는 항상 `python "D:\OPENCODE\report-1\report-1.py" --check` → `결과: OK`.

| 보이는 것 | 조치 |
|---|---|
| `LLM 서버 오류 404` · `/v1 이 필요한지 확인` | 주소 끝에 `/v1` 추가 → `--set "llm.base_url=https://…/v1"` |
| `LLM 서버 오류 401` · `403` | 키 또는 인증 헤더 문제. OpenCode 설정이 바뀌었으면 `--setup --force`. 아니면 **[질문]** |
| `CERTIFICATE_VERIFY_FAILED` · `SSL` | **[질문]** 사내 인증서 파일(PEM, 보통 `NODE_EXTRA_CA_CERTS` 의 경로)을 묻고 → `--set "llm.ca_file=<PEM 경로>"` |
| `응답 시간 초과` · `연결할 수 없습니다` · `407` | 사내 주소면 `--set "llm.proxy="` · 프록시가 필요하면 `--set "llm.proxy=http://<프록시>:<포트>"` · 자료가 많아 느리면 `--set "llm.timeout_sec=180"` |
| 창: `체크된 자료가 한도보다 깁니다` | 정상 동작 (사내 LLM 입력 한도를 넘지 않게 막음). 사용자가 체크를 풀어 줄이면 된다. **[질문]** 사내 LLM 의 입력 한도(토큰)를 알면, 거기서 `llm.max_tokens` 와 여유 2,000 을 뺀 값을 글자 수로 (한글은 한 글자 ≈ 한 토큰으로 잡으면 안전) → `--set "report.budget_chars=<글자 수>"` |
| 창: `LLM 서버 오류 400 … 입력 한도를 넘었을 수 있습니다` | 한도가 너무 크다 → `--set "report.budget_chars=12000"` 처럼 줄인다 |
| 창: `llm.max_tokens(…)에서 잘렸습니다` | 답이 길다 → `--set "llm.max_tokens=4096"` (사내 LLM 이 허용하는 만큼) · 또는 사용자가 ② 분량을 '짧게' |
| `포트 … 를 열 수 없습니다` | `--set "port=8778"` (대장의 8775–8784 안에서) |
| `설정 오류: … 형식 오류` · `report.forms …` | 사용자가 메모장으로 `%LOCALAPPDATA%\report-1\config.json` 을 고치거나, 이름을 `config.bak.json` 으로 바꾸고 3단계부터 다시 |
| `--set` 이 `API 키는 --set 으로 넣지 않습니다` | 정상 동작 (키가 명령 기록에 남지 않게 막음). 메모장 방법 또는 `{env:이름}` 참조 |
| `git pull` 이 `untracked working tree files would be overwritten` 와 함께 `AGENTS.md` · `CLAUDE.md` 를 보여 줌 | `D:\OPENCODE` 에 사용자가 만든 같은 이름 파일이 있다 (opencode `/init` 등). **[질문]** "`D:\OPENCODE\AGENTS.md` 를 `AGENTS.local.md` 로 이름을 바꿔도 될까요?" → 바꾼 뒤 pull 을 다시 한다. 그 내용을 계속 쓰려면 opencode 설정의 `instructions` 에 `AGENTS.local.md` 를 넣도록 사용자에게 안내한다 (설정 파일은 에이전트가 고치지 않는다) |

## 업데이트

사용자가 업데이트를 요청했을 때. 끄면 **보관 안 한 자료는 사라지므로** 먼저 **[질문]** "창에 보관 안 한 자료가 있으면 보관(Ctrl+S)해 주세요. 됐나요?" → 된 뒤에:

```text
python "D:\OPENCODE\report-1\report-1.py" --stop
git -C "D:\OPENCODE" pull --ff-only
python "D:\OPENCODE\report-1\report-1.py" --check
```

zip 으로 받았다면 `git pull` 대신 **[질문]** 새 zip 을 `D:\OPENCODE` 에 덮어 풀어 달라고 부탁한다.
설정 · 보관한 토픽 · 확정한 보고서는 `%LOCALAPPDATA%\report-1\` 에 있어서 업데이트로 바뀌지 않는다.

## 제거

**[질문]** "창에 보관 안 한 자료가 있으면 끄는 순간 사라집니다. 꺼도 될까요?" → 된다고 하면:

```text
python "D:\OPENCODE\report-1\report-1.py" --stop
python "D:\OPENCODE\report-1\report-1.py" --shortcut off
```

그다음 **[질문]** "`%LOCALAPPDATA%\report-1` 의 보관한 토픽 · 확정한 보고서를 백업할까요?" → 백업이 끝났거나 필요 없다고 하면, 확인 후에만 지운다 (`config.json` 에는 API 키가, `topics\` 에는 붙여 넣은 원문이 들어 있다):

```text
python -c "import os, shutil; shutil.rmtree(os.path.join(os.environ['LOCALAPPDATA'], 'report-1'), ignore_errors=True)"
```

프로그램 폴더 `D:\OPENCODE\report-1` 은 works 저장소의 일부라서 **지우지 않는다** — 지우면 git 이 '바뀐 파일' 로 보고 다른 works 도구의 업데이트(`git pull`)가 멈춘다. 켜지 않은 코드는 남아 있어도 아무 일도 하지 않는다.
works 전체를 지울 때만 **[질문]** "다른 works 도구도 함께 지워집니다. `D:\OPENCODE` 를 지울까요?" → 확인 후 지운다.

## 참고: 명령 모음

| 명령 | 하는 일 |
|---|---|
| (없음) | 창을 연다 (이미 켜져 있으면 창만) |
| `--setup [--provider P] [--model M] [--force]` | OpenCode 설정에서 LLM 값 가져오기 + 점검 (키는 표시 안 함) |
| `--check` | 데이터 · 양식 · LLM 점검 (마지막 줄 `결과: …`) |
| `--set "키=값"` | config.json 값 바꾸기 (여러 번 가능, 틀리면 되돌림) · 양식은 `report.forms.<이름>=칸1;칸2` |
| `--draft 파일… [--topic T] [--form F] [--basic]` | 창 없이 — 파일 하나 = 자료 하나로 초안 글만 출력 (`-` = 표준 입력 · 근거 없는 줄이 있으면 종료 코드 1 · 아무것도 저장하지 않음) |
| `--shortcut on` · `--shortcut off` | 시작 메뉴 바로가기 만들기 · 지우기 |
| `--status` · `--stop` | 실행 중인지 확인 · 끄기 (보관 안 한 자료는 사라짐) |
| `--version` | 버전 |
