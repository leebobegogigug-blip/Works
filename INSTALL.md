# jaba 설치 가이드 — OpenCode 에이전트용

> **사람용 한 줄:** OpenCode 에 아래 프롬프트를 붙여넣으면 이 문서대로 설치합니다. `<저장소 주소>`만 바꾸세요.
>
> ```text
> jaba 를 설치해줘. 설치 위치는 D:\OPENCODE\jaba 야.
> 1. 코드 받기: git clone <저장소 주소> "D:\OPENCODE\jaba"
>    (git 이 안 되면 D:\OPENCODE\jaba-repo.zip 을 D:\OPENCODE 에 풀어)
> 2. 그다음 D:\OPENCODE\jaba\INSTALL.md 를 끝까지 읽고 그 순서대로만 진행해.
>    API 키·토큰은 절대 출력하지 말고, [질문] 표시가 있는 곳에서는 나한테 물어봐.
> ```

---

이 아래는 **OpenCode(에이전트)가 실행할 절차**입니다.

## 0. 목표와 규칙

**목표**: `D:\OPENCODE\jaba` 에 jaba 를 설치하고, 점검을 통과시키고, 실행 중인 상태로 끝낸다.

**규칙 — 반드시 지킬 것**

1. **명령은 이 문서에 적힌 것만** 실행한다. 모든 명령은 Git Bash · cmd · PowerShell 어디서나 그대로 동작하게 적혀 있다 (경로는 항상 큰따옴표).
2. **비밀 금지**: `opencode.json` · `opencode.jsonc` · `auth.json` · `config.json` 을 읽기 도구나 `cat`/`type`/`Get-Content` 로 열거나 출력하지 않는다. LLM 설정 옮기기는 `--setup` 이 하고, 키 값은 어디에도 표시하지 않는다. 사용자가 키를 채팅에 붙여넣으려 하면 말리고 `config.json` 에 직접 넣도록 안내한다.
3. 관리자 권한 · 레지스트리 · 시스템 설정 변경 금지. `pip install` 은 4단계(Outlook)에서 사용자가 원할 때만.
4. **[질문]** 표시가 있는 곳에서는 멈추고 사용자에게 묻는다.
5. 출력이 예상과 다르면 추측해서 우회하지 말고, 출력을 그대로 보여 주고 [문제 해결](#문제-해결) 표를 따른다. 표에 없으면 멈추고 보고한다.
6. 명령은 한 번에 하나씩 실행하고, 결과를 확인한 뒤 다음으로 간다.

## 1. 파이썬 확인

```text
python --version
```

- `Python 3.8` 이상이면 통과.
- `Python was not found` 가 나오거나, 아무것도 안 나오거나, Microsoft Store 가 열리면 → `py -3 --version` 을 실행한다.
  - 이게 되면 **이후 모든 명령의 `python` 을 `py -3` 으로 바꿔서** 실행한다.
  - 이것도 안 되면 파이썬이 없는 것이다. **[질문]** 사용자에게 파이썬 설치를 부탁한다 (회사 소프트웨어 센터나 python.org 설치 파일, 설치할 때 "Add python.exe to PATH" 체크). 설치 전까지 여기서 멈춘다.

## 2. 코드 받기

먼저 이미 받았는지 확인한다 (시작 프롬프트대로 clone 했다면 `True`):

```text
python -c "import os; print(os.path.isfile(r'D:\OPENCODE\jaba\jaba.py'))"
```

`True` 면 2단계는 끝, 3단계로 간다. `False` 면 아래 A 또는 B 로 받는다.
(사용자가 **업데이트**를 요청한 경우에만 [업데이트](#업데이트)로 간다.)

설치 폴더를 만든다:

```text
python -c "import os; os.makedirs(r'D:\OPENCODE', exist_ok=True); print('OK')"
```

**A. git (기본)** — 사용자가 준 저장소 주소로:

```text
git clone <저장소 주소> "D:\OPENCODE\jaba"
```

**B. zip** — git 이 없거나 막혔고 `D:\OPENCODE\jaba-repo.zip` 이 있을 때:

```text
python -c "import zipfile; zipfile.ZipFile(r'D:\OPENCODE\jaba-repo.zip').extractall(r'D:\OPENCODE'); print('OK')"
```

받은 뒤 위의 확인 명령을 다시 실행해서 `True` 가 나와야 한다.

> 저장소 맨 위가 아니라 하위 폴더에 jaba 가 있으면 (예: `Works/jaba`) 저장소를 `D:\OPENCODE\<저장소 이름>` 에 clone 하고,
> 이 문서의 `D:\OPENCODE\jaba` 를 **모두 그 하위 폴더 경로로 바꿔서** 진행한다.

## 3. 설정 가져오기 + 점검

```text
python "D:\OPENCODE\jaba\jaba.py" --setup
```

하는 일: `config.json` · `jaba.bat` 만들기 → OpenCode 설정에서 사내 LLM 의 주소 · 모델 · 키 · 헤더를 `config.json` 에 옮기기 (키는 표시 안 함) → LLM · 캘린더 점검.
OpenCode 설정은 `%USERPROFILE%\.config\opencode\opencode.json(c)`, `D:\OPENCODE\opencode.json(c)`, `OPENCODE_CONFIG`, 로그인 정보 `%USERPROFILE%\.local\share\opencode\auth.json` 에서 찾는다.

마지막 줄의 **결과**로 판단한다.

| 마지막 줄 | 할 일 |
|---|---|
| `결과: OK` | 4단계로 |
| `결과: 확인 필요` + `provider 가 여러 개입니다 → … : a, b` | **[질문]** 사내 LLM 이 어느 것인지 묻고 → `python "D:\OPENCODE\jaba\jaba.py" --setup --provider "a"` |
| `결과: 확인 필요` + `모델이 여러 개입니다 → … : x, y` | **[질문]** 어느 모델을 쓸지 묻고 → `python "D:\OPENCODE\jaba\jaba.py" --setup --provider "a" --model "x"` |
| `결과: 확인 필요` + `OpenCode 설정 파일…을 찾지 못했습니다` 또는 `OpenAI 호환 provider … 가 없습니다` | [LLM 을 직접 넣기](#llm-을-직접-넣기) |
| `결과: 점검 실패` | [문제 해결](#문제-해결) 표대로 고치고 `python "D:\OPENCODE\jaba\jaba.py" --check` → `결과: OK` 가 될 때까지 |

참고: `도구 호출: 텍스트로 출력함 → 자동으로 json 모드로 동작` 은 실패가 아니다 (그대로 동작함). 고정하려면 `--set "llm.tool_mode=json"`.

### LLM 을 직접 넣기

**[질문]** 사용자에게 사내 LLM 주소(보통 `…/v1` 로 끝남)와 모델 이름을 받는다 (**키는 받지 않는다**).

```text
python "D:\OPENCODE\jaba\jaba.py" --set "llm.base_url=<주소>" --set "llm.model=<모델 이름>"
```

키가 필요한 서버면 사용자에게 둘 중 하나를 안내한다.

- 메모장으로 `D:\OPENCODE\jaba\config.json` 을 열어 `"api_key": ""` 의 따옴표 안에 직접 붙여넣고 저장.
- 키가 이미 사용자 환경변수(예: `CORP_LLM_KEY`)에 있으면 → `python "D:\OPENCODE\jaba\jaba.py" --set "llm.api_key={env:CORP_LLM_KEY}"`

그다음 `python "D:\OPENCODE\jaba\jaba.py" --check` → `결과: OK`.

## 4. (선택) Outlook 일정과 연결

**[질문]** "일정을 클래식 Outlook 과 연결할까요, jaba 자체 달력(기본)을 쓸까요?"
Outlook 을 원하고 PC 에 **클래식** Outlook 이 있을 때만 (새 Outlook 은 지원 안 함):

```text
python -m pip install pywin32
python "D:\OPENCODE\jaba\jaba.py" --set "calendar.backend=outlook" --check
```

- `pip` 가 권한 오류(`Permission denied` · `Access is denied`)면 `python -m pip install --user pywin32` 로 한 번만 다시.
- `pip` 가 네트워크 오류(사내망)면 더 시도하지 말고 기본 달력으로 두고 보고한다.
- `캘린더 : 실패` 가 나오면 → `python "D:\OPENCODE\jaba\jaba.py" --set "calendar.backend=local"` 로 되돌리고 보고한다.
- 연결됐으면 사용자에게 "jaba 로 일정 하나를 만들어 Outlook 화면의 시간과 같은지 확인해 달라"고 안내한다.

## 5. 윈도우 알림 확인

```text
python "D:\OPENCODE\jaba\jaba.py" --test-notify
```

- `윈도우 알림 OK` → **[질문]** "화면 오른쪽 아래에 'jaba 알림 테스트' 알림이 떴나요?"
  - 안 보였다면 → 윈도우 설정의 알림 · 방해 금지(집중 지원)가 켜져 있는지 사용자에게 확인을 부탁한다.
- `윈도우 알림 실패` → 회사 정책으로 막힌 것. `python "D:\OPENCODE\jaba\jaba.py" --set "alerts.windows_toast=false"` 로 끄고 (jaba 창 안의 알림만 사용) 사용자에게 알린다.

알림 규칙: 장소가 있는 일정은 15 · 5 · 1분 전, 장소가 없는 일정은 5 · 1분 전. **jaba 가 켜져 있을 때만** 온다.

## 6. 자동 실행 (권장)

**[질문]** "로그인할 때 jaba 를 자동으로 켤까요? (창 없이 켜지고, 알림은 켜져 있을 때만 옵니다)"
예라면:

```text
python "D:\OPENCODE\jaba\jaba.py" --autostart on
```

`자동 실행 등록:` 이 나오면 성공. 실패하면 출력에 나온 "직접" 방법을 사용자에게 전달한다.

## 7. 실행하고 확인

```text
python -c "import os; os.startfile(r'D:\OPENCODE\jaba\jaba.bat')"
python "D:\OPENCODE\jaba\jaba.py" --status
```

- `실행 중: http://127.0.0.1:…/` → **[질문]** "jaba 창이 떴나요? 창을 닫았다가 **Ctrl+Alt+J** 로 다시 불러 보세요."
- `꺼져 있음` → `--status` 를 한 번 더 실행한다. 그래도 꺼져 있으면 에이전트 셸이 끝나면서 같이 꺼진 것일 수 있다. 사용자에게 `D:\OPENCODE\jaba\jaba.bat` 을 직접 더블클릭해 달라고 하고, 다시 `--status` 로 확인한다.

jaba 를 켜면 작업 표시줄에 최소화된 `jaba` 콘솔 창이 생긴다. **그 창을 닫으면 jaba 가 꺼진다.**

## 8. 완료 보고

아래 형식으로 사용자에게 보고한다. **키 값은 쓰지 않는다.**

```text
jaba 설치 완료
- 위치     : D:\OPENCODE\jaba (jaba 버전 · python "D:\OPENCODE\jaba\jaba.py" --version)
- 파이썬   : (1단계 결과)
- LLM      : (주소) · (모델) · 키 (설정됨 / 참조 / 없음)
- 점검     : 기본 응답 OK · 도구 호출 (OK / json 모드)
- 캘린더   : local / outlook
- 윈도우 알림 : 보임 / 앱 안 알림만
- 자동 실행 : 등록 / 안 함
- 상태     : 실행 중 (주소)
- 쓰는 법  : Ctrl+Alt+J → "내일 3시 김과장 미팅 잡아줘" → [확정] · 빠른 키 Alt+1~4 · 학습 "앞으로 스크럼은 15분으로 잡아"
```

---

## 문제 해결

`--setup` / `--check` 출력에 나온 문구로 찾는다. 고친 뒤에는 항상 `python "D:\OPENCODE\jaba\jaba.py" --check` 로 확인한다.

| 출력에 보이는 것 | 조치 |
|---|---|
| `미설정 → config.json 의 llm.base_url` | 주소나 모델이 비어 있다 → [LLM 을 직접 넣기](#llm-을-직접-넣기) |
| `API 키 : {env:이름} 참조 · 값이 비어 있음!` | OpenCode 는 환경변수에서 키를 읽는데 지금 셸에는 그 변수가 없다. **[질문]** 사용자에게 그 사용자 환경변수가 있는지 확인. 없으면 [LLM 을 직접 넣기](#llm-을-직접-넣기)의 메모장 방법 |
| `LLM 서버 오류 404` · `/v1 이 필요한지 확인` | 주소 끝에 `/v1` 추가 → `--set "llm.base_url=https://…/v1"` |
| `LLM 서버 오류 401` · `LLM 서버 오류 403` · `api_key 또는 extra_headers` | 키 또는 인증 헤더 문제. OpenCode 설정이 바뀌었으면 `--setup --force` (다시 가져오기). 아니면 **[질문]** |
| `CERTIFICATE_VERIFY_FAILED` · `SSL` | 사내 인증서. **[질문]** OpenCode 용 인증서 파일(PEM, 보통 환경변수 `NODE_EXTRA_CA_CERTS` 의 경로)이 있는지 물어보고 → `--set "llm.ca_file=<PEM 경로>"` |
| `응답 시간 초과` · `연결할 수 없습니다` · `LLM 서버 오류 407` · `Proxy` | 사내 주소면 프록시를 끈다 → `--set "llm.proxy="` · 프록시가 필요하면 → `--set "llm.proxy=http://<프록시>:<포트>"` |
| `도구 호출: 서버가 tools 를 거부` · `텍스트로 출력함` · `모델이 도구를 쓰지 않음` | `--set "llm.tool_mode=json"` |
| `윈도우 알림 실패` | `--set "alerts.windows_toast=false"` (앱 안 알림만) |
| `포트 … 를 열 수 없습니다` | `--set "port=8775"` |
| `단축키 … 등록 실패` | 다른 프로그램이 같은 키를 씀 → **[질문]** 원하는 키 → `--set "hotkey=ctrl+alt+k"` |
| `설정 오류: … 형식 오류` (config.json 이 깨짐) | 사용자가 메모장으로 고치거나, `config.json` 을 `config.bak.json` 으로 이름을 바꾸고 3단계부터 다시 |
| 파이썬을 다시 깐 뒤 `jaba.bat` 이 안 켜짐 | `--setup` 한 번 실행 (`jaba.bat` 을 새로 만든다) |
| `--set` 이 `API 키는 --set 으로 넣지 않습니다` | 정상 동작 (키가 명령 기록에 남지 않게 막음). 메모장 방법 또는 `{env:이름}` 참조 사용 |

`--set` 은 모든 셸에서 `python "D:\OPENCODE\jaba\jaba.py" --set "키=값"` 형태로 쓴다. 틀린 값은 저장되지 않고 되돌려진다.

## 업데이트

사용자가 업데이트를 요청했을 때:

```text
python "D:\OPENCODE\jaba\jaba.py" --stop
git -C "D:\OPENCODE\jaba" pull
python "D:\OPENCODE\jaba\jaba.py" --check
python -c "import os; os.startfile(r'D:\OPENCODE\jaba\jaba.bat')"
python "D:\OPENCODE\jaba\jaba.py" --status
```

zip 으로 받았다면 `git pull` 대신 새 `jaba-repo.zip` 을 `D:\OPENCODE` 에 두고 2단계 B 의 압축 해제 명령을 실행한다.
`config.json` · `jaba.db`(일정) · `jaba_rules.json`(학습 규칙) · `jaba_wiki.json`(일정 위키)은 저장소에도 zip 에도 없어서 그대로 남는다.

## 제거

```text
python "D:\OPENCODE\jaba\jaba.py" --stop
python "D:\OPENCODE\jaba\jaba.py" --autostart off
```

그다음 **[질문]** "`jaba.db`(일정) · `jaba_rules.json`(학습 규칙) · `jaba_wiki.json`(일정 위키)을 백업할까요?" → 사용자 확인 후에만 `D:\OPENCODE\jaba` 폴더를 지운다.

## 참고: 명령 모음

| 명령 | 하는 일 |
|---|---|
| `--setup [--provider P] [--model M] [--force]` | OpenCode 설정에서 LLM 값 가져오기 + 점검 (키는 표시 안 함) |
| `--check` | LLM · 캘린더 점검 |
| `--set "키=값"` | config.json 값 바꾸기 (여러 번 가능, 틀리면 되돌림) |
| `--test-notify` | 윈도우 알림 테스트 |
| `--autostart on` · `--autostart off` | 로그인할 때 자동 실행 등록 · 해제 |
| `--status` · `--stop` | 실행 중인지 확인 · 끄기 |
| `--version` | 버전 |
