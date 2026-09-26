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

**목표**: `D:\OPENCODE\report-1` 의 Report–1 이 사용자의 커밋 · 일정 · 일지를 읽고, 점검을 통과하고, 창이 뜨는 상태로 끝낸다.
설정과 데이터는 `%LOCALAPPDATA%\report-1\` 에 생긴다 (프로그램 폴더에는 아무것도 만들지 않는다).

**규칙 — 반드시 지킬 것**

1. **명령은 이 문서에 적힌 것만** 실행한다. 모든 명령은 Git Bash · cmd · PowerShell 어디서나 그대로 동작하게 적혀 있다 (경로는 항상 큰따옴표).
2. **비밀 금지**: `opencode.json` · `opencode.jsonc` · `auth.json` · `%LOCALAPPDATA%\report-1\config.json` 을 읽기 도구나 `cat`/`type`/`Get-Content` 로 열거나 출력하지 않는다. LLM 설정 옮기기는 `--setup` 이 하고, 키 값은 어디에도 표시하지 않는다. 사용자가 키를 채팅에 붙여넣으려 하면 말린다.
3. **관리자 권한 · 레지스트리 · 시스템 설정 변경 금지.** 시작 메뉴 바로가기는 7단계에서 사용자가 원할 때만.
4. **[질문]** 표시가 있는 곳에서는 멈추고 사용자에게 묻는다.
5. 출력이 예상과 다르면 추측해서 우회하지 말고, 출력을 그대로 보여 주고 [문제 해결](#문제-해결) 표를 따른다. 표에 없으면 멈추고 보고한다.
6. 명령은 한 번에 하나씩 실행하고, 결과를 확인한 뒤 다음으로 간다.

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

## 3. git 확인

```text
git --version
```

- **확인**: 버전이 나오면 통과 (Report–1 은 이 git 으로 사용자의 커밋을 읽는다).
- **실패하면**: **[질문]** "git 이 없으면 커밋 없이 일정 · 일지로만 주간보고를 씁니다. 그대로 갈까요, git 을 먼저 설치할까요?" — 그대로 가면 계속한다.

## 4. 설정 + 점검

```text
python "D:\OPENCODE\report-1\report-1.py" --setup
```

하는 일: `%LOCALAPPDATA%\report-1\config.json` 만들기 → OpenCode 설정에서 사내 LLM 의 주소 · 모델 · 키 · 헤더를 옮기기 (키는 표시 안 함) → 커밋 폴더 확인 → 점검. 마지막 줄의 **결과**로 판단한다.

| 마지막 줄 | 할 일 |
|---|---|
| `결과: OK` | 5단계로 |
| `결과: 확인 필요` + `provider 가 여러 개입니다 → … : a, b` | **[질문]** 사내 LLM 이 어느 것인지 묻고 → `python "D:\OPENCODE\report-1\report-1.py" --setup --provider "a"` |
| `결과: 확인 필요` + `모델이 여러 개입니다 → … : x, y` | **[질문]** 어느 모델을 쓸지 묻고 → `… --setup --provider "a" --model "x"` |
| `결과: 확인 필요` + `OpenCode 설정 파일…을 찾지 못했습니다` · `OpenAI 호환 provider … 가 없습니다` | **[질문]** "사내 LLM 없이 기본 초안(규칙으로 묶기)만 쓸까요, 주소를 알려 주시겠어요?" → 주소를 받으면 `--set "llm.base_url=<주소>" --set "llm.model=<모델>"` (**키는 받지 않는다** — 필요하면 사용자가 `config.json` 에 직접 넣거나 `--set "llm.api_key={env:환경변수이름}"`). 그다음 `--setup` 을 다시 |
| `결과: 확인 필요` + `커밋을 찾을 작업 폴더` | **[질문]** "커밋을 모을 작업 폴더가 어디인가요? (저장소들이 들어 있는 폴더, 예: C:\work)" → `python "D:\OPENCODE\report-1\report-1.py" --set "sources.git.roots=C:\work" --check` (여러 개는 `;` 로: `C:\work;D:\proj`) |
| `결과: 점검 실패` | [문제 해결](#문제-해결) 표대로 고치고 `python "D:\OPENCODE\report-1\report-1.py" --check` → `결과: OK` 가 될 때까지 |

## 5. 내 커밋 확인

4단계 점검 출력의 `내 커밋으로 칠 작성자:` 줄을 본다.

- 이메일이 보이면 → **[질문]** "이 이메일로 쓴 커밋만 주간보고에 들어갑니다: (이메일). 다른 이메일로도 커밋하시나요?" → 더 있으면 `python "D:\OPENCODE\report-1\report-1.py" --set "sources.git.authors=a@example.com;b@example.com" --check`
- `없음` 이면 → **[질문]** 커밋에 쓰는 이메일을 받아 위 명령으로 넣는다. (작성자를 모르면 Report–1 은 커밋을 **하나도** 가져오지 않는다 — 남의 커밋이 섞이지 않게)

## 6. 일정 확인

점검 출력의 `일정` 줄을 본다.

- `OK · …` → Secretary–1 에서 일정을 읽는다. 끝.
- `Secretary–1 이 없습니다 → 일정 없이` → 사용자에게 알린다: "일정은 Secretary–1 이 있으면 같이 들어갑니다 (`D:\OPENCODE\secretary-1\INSTALL.md`). 지금은 커밋 · 일지로만 씁니다."
- 그 밖의 실패 → [문제 해결](#문제-해결).

## 7. 시작 메뉴 바로가기 (선택)

**[질문]** "시작 메뉴에 Report–1 바로가기를 만들까요? (지울 때는 --shortcut off)"
예라면:

```text
python "D:\OPENCODE\report-1\report-1.py" --shortcut on
```

`바로가기 만듦:` 이 나오면 성공. 실패하면 출력을 그대로 보고하고 넘어간다 (바로가기 없이도 `python report-1.py` 로 켠다).

## 8. 실행하고 확인

에이전트 셸이 끝나도 꺼지지 않게 따로 띄운다:

```text
python -c "import subprocess, sys; subprocess.Popen([sys.executable, r'D:\OPENCODE\report-1\report-1.py'], creationflags=0x00000208, close_fds=True)"
python "D:\OPENCODE\report-1\report-1.py" --status
```

- `실행 중: http://127.0.0.1:…/` → **[질문]** "Report–1 창이 떴나요? 왼쪽에 이번 주 커밋 · 일정이 보이면 성공입니다."
- `꺼져 있음` → `--status` 를 한 번 더. 그래도 꺼져 있으면 사용자에게 시작 메뉴의 Report-1 (또는 `python "D:\OPENCODE\report-1\report-1.py"`)을 직접 실행해 달라고 한다.

창을 닫으면 30분 뒤 저절로 꺼진다 (`idle_exit_min`).

## 9. 완료 보고

아래 형식으로 사용자에게 보고한다. **키 값은 쓰지 않는다.**

```text
Report–1 설치 완료
- 위치     : D:\OPENCODE\report-1 (버전 · python "D:\OPENCODE\report-1\report-1.py" --version)
- 데이터   : %LOCALAPPDATA%\report-1
- 파이썬   : (1단계 결과)
- git      : (3단계 결과) · 커밋 폴더 (roots) · 작성자 (이메일)
- 일정     : Secretary–1 에서 / 없음
- LLM      : (주소) · (모델) · 키 (설정됨 / 참조 / 없음) — 또는 '없음 · 기본 초안'
- 바로가기 : 시작 메뉴 / 안 함
- 상태     : 실행 중 (주소)
- 쓰는 법  : 매일 '오늘 한 일 ›' 에 한 줄 → 금요일에 [초안 만들기] → 근거 확인 · 고치기 → [확정] (클립보드로)
```

---

## 문제 해결

`--setup` / `--check` 출력에 나온 문구로 찾는다. 고친 뒤에는 항상 `python "D:\OPENCODE\report-1\report-1.py" --check` → `결과: OK`.

| 출력에 보이는 것 | 조치 |
|---|---|
| `git : 실패 · git 을 찾지 못했습니다` | git 이 PATH 에 없다. **[질문]** git 을 설치할지, 커밋 없이 쓸지 → 커밋 없이면 `--set "sources.git.roots="` |
| `저장소를 찾지 못했습니다` | 폴더가 틀렸거나 더 깊다. **[질문]** 폴더를 다시 묻고 `--set "sources.git.roots=C:\work"` · 깊으면 `--set "sources.git.depth=3"` (최대 4) |
| `작성자 이메일을 모르는 저장소 n개는 건너뜀` | 5단계대로 `sources.git.authors` 를 넣는다 |
| `Secretary–1: …` · `Secretary–1 의 답을 읽지 못했습니다` | Secretary–1 쪽 문제. `python "D:\OPENCODE\secretary-1\secretary-1.py" --check` 결과를 보여 주고 멈춘다 (Report–1 은 일정 없이 계속 동작) |
| `Secretary–1 의 일정 형식(n)을 모릅니다` | Report–1 이 오래됐다 → [업데이트](#업데이트) |
| `LLM 서버 오류 404` · `/v1 이 필요한지 확인` | 주소 끝에 `/v1` 추가 → `--set "llm.base_url=https://…/v1"` |
| `LLM 서버 오류 401` · `403` | 키 또는 인증 헤더 문제. OpenCode 설정이 바뀌었으면 `--setup --force`. 아니면 **[질문]** |
| `CERTIFICATE_VERIFY_FAILED` · `SSL` | **[질문]** 사내 인증서 파일(PEM, 보통 `NODE_EXTRA_CA_CERTS` 의 경로)을 묻고 → `--set "llm.ca_file=<PEM 경로>"` |
| `응답 시간 초과` · `연결할 수 없습니다` · `407` | 사내 주소면 `--set "llm.proxy="` · 프록시가 필요하면 `--set "llm.proxy=http://<프록시>:<포트>"` |
| `포트 … 를 열 수 없습니다` | `--set "port=8778"` (대장의 8775–8784 안에서) |
| `설정 오류: … 형식 오류` | 사용자가 메모장으로 `%LOCALAPPDATA%\report-1\config.json` 을 고치거나, 이름을 `config.bak.json` 으로 바꾸고 4단계부터 다시 |
| `--set` 이 `API 키는 --set 으로 넣지 않습니다` | 정상 동작 (키가 명령 기록에 남지 않게 막음). 메모장 방법 또는 `{env:이름}` 참조 |
| `git pull` 이 `untracked working tree files would be overwritten` 와 함께 `AGENTS.md` · `CLAUDE.md` 를 보여 줌 | `D:\OPENCODE` 에 사용자가 만든 같은 이름 파일이 있다 (opencode `/init` 등). **[질문]** "`D:\OPENCODE\AGENTS.md` 를 `AGENTS.local.md` 로 이름을 바꿔도 될까요?" → 바꾼 뒤 pull 을 다시 한다. 그 내용을 계속 쓰려면 opencode 설정의 `instructions` 에 `AGENTS.local.md` 를 넣도록 사용자에게 안내한다 (설정 파일은 에이전트가 고치지 않는다) |

## 업데이트

사용자가 업데이트를 요청했을 때:

```text
python "D:\OPENCODE\report-1\report-1.py" --stop
git -C "D:\OPENCODE" pull --ff-only
python "D:\OPENCODE\report-1\report-1.py" --check
```

zip 으로 받았다면 `git pull` 대신 **[질문]** 새 zip 을 `D:\OPENCODE` 에 덮어 풀어 달라고 부탁한다.
설정 · 일지 · 확정한 보고서는 `%LOCALAPPDATA%\report-1\` 에 있어서 업데이트로 바뀌지 않는다.

## 제거

```text
python "D:\OPENCODE\report-1\report-1.py" --stop
python "D:\OPENCODE\report-1\report-1.py" --shortcut off
```

그다음 **[질문]** "`%LOCALAPPDATA%\report-1` 의 일지 · 확정한 보고서를 백업할까요?" → 백업이 끝났거나 필요 없다고 하면, 확인 후에만 지운다 (`config.json` 에는 API 키가 들어 있을 수 있다):

```text
python -c "import os, shutil; shutil.rmtree(os.path.join(os.environ['LOCALAPPDATA'], 'report-1'), ignore_errors=True)"
```

프로그램 폴더 `D:\OPENCODE\report-1` 은 works 저장소의 일부라서 **지우지 않는다** — 지우면 git 이 '바뀐 파일' 로 보고 다른 works 도구의 업데이트(`git pull`)가 멈춘다. 켜지 않은 코드는 남아 있어도 아무 일도 하지 않는다.
works 전체를 지울 때만 **[질문]** "다른 works 도구도 함께 지워집니다. `D:\OPENCODE` 를 지울까요?" → 확인 후 지운다.

## 참고: 명령 모음

| 명령 | 하는 일 |
|---|---|
| (없음) | 창을 연다 (이미 켜져 있으면 창만) |
| `--setup [--provider P] [--model M] [--force]` | OpenCode 설정에서 LLM 값 가져오기 + 커밋 폴더 확인 + 점검 (키는 표시 안 함) |
| `--check` | git · 일정 · 일지 · LLM 점검 (마지막 줄 `결과: …`) |
| `--set "키=값"` | config.json 값 바꾸기 (여러 번 가능, 틀리면 되돌림) |
| `--draft [--period this\|last\|2w\|month] [--basic]` | 창 없이 초안 글만 출력 (근거 없는 줄이 있으면 종료 코드 1) |
| `--shortcut on` · `--shortcut off` | 시작 메뉴 바로가기 만들기 · 지우기 |
| `--status` · `--stop` | 실행 중인지 확인 · 끄기 |
| `--version` | 버전 |
