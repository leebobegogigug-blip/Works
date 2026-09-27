# Flow–1 설치 가이드 — OpenCode 에이전트용

> **사람용 한 줄:** OpenCode 에 아래 프롬프트를 붙여넣으면 이 문서대로 설치합니다.
> Flow–1 은 works 저장소(`https://github.com/leebobegogigug-blip/Works`)의 `flow-1` 폴더입니다.
>
> ```text
> Flow–1 을 설치해줘. works 저장소를 D:\OPENCODE 에 받고, 프로그램 폴더는 D:\OPENCODE\flow-1 이야.
> 1. 코드 받기: D:\OPENCODE 가 없거나 비어 있으면 git clone https://github.com/leebobegogigug-blip/Works.git "D:\OPENCODE"
>    (이미 works 가 받아져 있으면 받지 말고, git 이 안 되면 Works-repo.zip 을 D:\OPENCODE 에 풀어)
> 2. 그다음 D:\OPENCODE\flow-1\INSTALL.md 를 끝까지 읽고 그 순서대로만 진행해.
>    API 키·토큰은 절대 출력하지 말고, [질문] 표시가 있는 곳에서는 나한테 물어봐.
> ```

---

이 아래는 **OpenCode(에이전트)가 실행할 절차**입니다.

## 0. 목표와 규칙

**목표**: `D:\OPENCODE\flow-1` 의 Flow–1 이 점검을 통과하고, 사용자의 분석 코드 폴더를 감시하며, 창이 뜨는 상태로 끝낸다.
설정과 실행 기록은 `%LOCALAPPDATA%\flow-1\` 에 생긴다 (프로그램 폴더에는 아무것도 만들지 않는다).

**규칙 — 반드시 지킬 것**

1. **명령은 이 문서에 적힌 것만** 실행한다. 모든 명령은 Git Bash · cmd · PowerShell 어디서나 그대로 동작하게 적혀 있다 (경로는 항상 큰따옴표).
2. **사용자의 분석 스크립트를 실행하지 않는다.** Flow–1 은 코드를 읽기만 한다. `--run` 은 스크립트를 **진짜로** 돌린다 (DB 에 INSERT · CREATE 도 한다) — 이 문서는 쓰는 법만 알려 주고, 사용자가 직접 고른 스크립트를 사용자가 원할 때만 돌린다.
3. **사내 정보를 저장소에 쓰지 않는다**: 사내 패키지 이름 · 폴더 경로 · 테이블 이름은 `--set` 으로 이 PC 설정(`%LOCALAPPDATA%\flow-1\config.json`)에만 넣는다. `D:\OPENCODE` 안의 파일을 고치거나 커밋하지 않는다 ([RULES.md › W-12](../RULES.md#w-12-공개-저장소다)).
4. **비밀 금지**: 분석 코드 · 설정 파일 안의 비밀번호 · 키를 출력하지 않는다. 사용자가 비밀을 채팅에 붙여넣으려 하면 말린다.
5. **관리자 권한 · 레지스트리 · 시스템 설정 변경 금지.** 시작 메뉴 바로가기는 6단계에서 사용자가 원할 때만.
6. **[질문]** 표시가 있는 곳에서는 멈추고 사용자에게 묻는다.
7. 출력이 예상과 다르면 추측해서 우회하지 말고, 출력을 그대로 보여 주고 [문제 해결](#문제-해결) 표를 따른다. 표에 없으면 멈추고 보고한다.
8. 명령은 한 번에 하나씩 실행하고, 결과를 확인한 뒤 다음으로 간다.

## 1. 파이썬 확인

```text
python --version
```

- **확인**: `Python 3.8` 이상이면 통과.
- **실패하면**: `py -3 --version` 을 실행한다. 이게 되면 **이후 모든 명령의 `python` 을 `py -3` 으로 바꿔서** 실행한다. 이것도 안 되면 **[질문]** 사용자에게 파이썬 설치를 부탁하고 (회사 소프트웨어 센터나 python.org, 설치할 때 "Add python.exe to PATH" 체크) 멈춘다.
- 분석 코드를 돌리는 파이썬(사내 패키지 · 판다스가 깔린 것)이 따로 있으면 **그 파이썬**을 쓰는 것이 좋다 — `--run` 이 그 파이썬으로 스크립트를 돌리기 때문이다. **[질문]** "분석할 때 쓰는 파이썬이 따로 있나요? (예: 아나콘다)" → 있으면 이후 `python` 을 그 경로(큰따옴표)로 바꾼다.

## 2. 코드 받기

```text
python -c "import os; print(os.path.isfile(r'D:\OPENCODE\flow-1\flow-1.py'))"
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
python "D:\OPENCODE\flow-1\flow-1.py" --setup
```

하는 일: `%LOCALAPPDATA%\flow-1\config.json` 만들기 → 데이터 폴더에 쓸 수 있는지 · 내장 예시를 제대로 읽는지(자체 시험) 점검. 마지막 줄의 **결과**로 판단한다.

| 마지막 줄 | 할 일 |
|---|---|
| `결과: OK` | 4단계로 |
| `결과: 확인 필요` | 출력의 `!` 줄 · `쿼리 패키지` 줄을 사용자에게 보여 주고 4 · 5단계에서 고친다 |
| `결과: 점검 실패` | [문제 해결](#문제-해결) 표대로 고치고 `python "D:\OPENCODE\flow-1\flow-1.py" --check` → `결과: OK` 가 될 때까지 |

출력의 `- 자체 시험 : 내장 예시 쿼리 6 · 테이블 6 · 조인 5 · 정상` 줄이 Flow–1 의 분석기가 제대로 도는지의 증거다. `정상` 이 아니면 멈추고 보고한다.

## 4. 사내 쿼리 패키지 알려 주기

Flow–1 은 패키지 이름을 몰라도 **인자에 SQL 이 들어간 호출**을 쿼리로 찾는다. 이름을 알려 주면 SQL 이 변수라 코드만으로 못 읽는 호출까지 잡는다.

- **사내 스킬이 있으면**(데이터를 뽑는 사내 패키지의 사용법을 담은 opencode 스킬 · 문서) 먼저 그것을 읽고, 거기 적힌 **import 이름**과 **SQL 을 받는 함수 · 메서드 이름**을 쓴다. 사용자에게는 확인만 받는다.
- 스킬이 없으면 **[질문]** "분석 코드에서 데이터를 뽑을 때 `import` 하는 사내 패키지 이름이 무엇인가요? SQL 을 넘기는 함수 이름도 알려 주세요 (예: `query`, `execute`)."

```text
python "D:\OPENCODE\flow-1\flow-1.py" --set "query.modules=<패키지 import 이름>"
python "D:\OPENCODE\flow-1\flow-1.py" --set "query.calls=<함수1>;<함수2>" --check
```

- `query.calls` 는 스킬 · 사용자가 알려 준 함수 이름 **전부**를 `;` 로 잇는다 (SQL 파일 경로를 받는 함수 — 예: `run_file("a.sql")` — 도 넣으면 그 파일을 읽는다) (기본값 `query;execute;read_sql;sql;run;fetch` 를 바꾼다 — 알려 준 이름이 기본값에 있던 것과 같아도 모두 적는다). 모르면 이 줄은 건너뛴다.
- **확인**: 점검 출력의 `- 쿼리 패키지: <이름> · 이 파이썬에서 import 할 수 있음`.
- `이 파이썬에 없음` (결과: 확인 필요) 이면: 분석(흐름도)은 그대로 된다. `--run` 만 그 패키지가 깔린 파이썬이 필요하다. **[질문]** "분석할 때 쓰는 파이썬 경로를 알려 주시겠어요?" → 알려 주면 이후 명령의 `python` 을 그 경로로 바꾸고 `--check` 를 다시.

## 5. 감시할 폴더

**[질문]** "쿼리 흐름을 볼 분석 코드 폴더가 어디인가요? (여러 개면 모두 · 나중에 창의 탐색기에서 더해도 됩니다)"

```text
python "D:\OPENCODE\flow-1\flow-1.py" --set "watch=<폴더1>;<폴더2>" --check
```

- **확인**: 점검 출력의 `- 감시 : n곳 · 파일 n개 · 쿼리 n개`. 쿼리가 0개면 **[질문]** "이 폴더의 코드가 SQL 을 어떻게 넘기는지 한 줄 보여 주시겠어요?" → 4단계의 `query.calls` 를 다시 본다. 그래도 0 이면 멈추고 보고한다 (사내 LLM 이 고칠 차례 — [docs/GUIDE.md](docs/GUIDE.md) › 05).
- `! 없는 경로` 줄이 나오면 경로를 사용자와 다시 확인한다 (드라이브 문자 · 오타).

## 6. 시작 메뉴 바로가기 (선택)

**[질문]** "시작 메뉴에 Flow–1 바로가기를 만들까요? (지울 때는 --shortcut off)"
예라면:

```text
python "D:\OPENCODE\flow-1\flow-1.py" --shortcut on
```

`바로가기 만듦:` 이 나오면 성공. 실패하면 출력을 그대로 보고하고 넘어간다 (바로가기 없이도 `python flow-1.py` 로 켠다).

## 7. 실행하고 확인

에이전트 셸이 끝나도 꺼지지 않게 따로 띄운다:

```text
python -c "import subprocess, sys; subprocess.Popen([sys.executable, r'D:\OPENCODE\flow-1\flow-1.py'], creationflags=0x00000208, close_fds=True)"
python "D:\OPENCODE\flow-1\flow-1.py" --status
```

- `실행 중: http://127.0.0.1:…/` → **[질문]** "Flow–1 창이 떴나요? 왼쪽 아래 탐색기에서 파이썬 파일 하나를 눌러 보세요. 가운데에 쿼리 카드가 나오면 성공입니다."
- `꺼져 있음` → `--status` 를 한 번 더. 그래도 꺼져 있으면 사용자에게 시작 메뉴의 Flow-1 (또는 `python "D:\OPENCODE\flow-1\flow-1.py"`)을 직접 실행해 달라고 한다.

창을 닫으면 30분 뒤 저절로 꺼진다 (`idle_exit_min`). 감시 목록은 설정에 남아 있어서 다시 켜면 그대로다.

쿼리마다 걸린 시간을 재는 법은 **알려 주기만 한다** (규칙 2 — 에이전트가 돌리지 않는다):

```text
python "D:\OPENCODE\flow-1\flow-1.py" --run "<사용자의 스크립트.py>" [그 스크립트의 인자…]
```

그 스크립트를 진짜로 끝까지 실행한다 (DB 에 쓰는 쿼리도 실행된다). 창이 켜져 있으면 실행하는 동안 카드가 바뀐다.

## 8. 완료 보고

아래 형식으로 사용자에게 보고한다. **비밀 값은 쓰지 않는다.**

```text
Flow–1 설치 완료
- 위치     : D:\OPENCODE\flow-1 (버전 · python "D:\OPENCODE\flow-1\flow-1.py" --version)
- 데이터   : %LOCALAPPDATA%\flow-1 (감시 목록 · 실행 기록 — 코드 · SQL · 데이터는 남기지 않음)
- 파이썬   : (1단계 결과 · 분석용 파이썬을 따로 쓰면 그 경로)
- 쿼리 패키지: (이름 · import 되는지) — 또는 '설정 안 함 · SQL 모양 인자로 찾음'
- 감시     : (n곳 · 파일 n개 · 쿼리 n개)
- 바로가기 : 시작 메뉴 / 안 함
- 상태     : 실행 중 (주소)
- 쓰는 법  : 왼쪽 탐색기에서 .py 를 누르면 흐름도 · + 는 감시 고정 · 카드를 누르면 오른쪽에 SQL 전부
             코드를 그냥 붙여 넣어도(Ctrl+V) 됨 · 걸린 시간은 --run "<스크립트>"
```

---

## 문제 해결

`--setup` / `--check` 출력이나 창의 알림에 나온 문구로 찾는다. 고친 뒤에는 항상 `python "D:\OPENCODE\flow-1\flow-1.py" --check` → `결과: OK`.

| 보이는 것 | 조치 |
|---|---|
| `자체 시험 : … 예상과 다름` | 프로그램 파일이 바뀌었다. `git -C "D:\OPENCODE" status` 를 사용자에게 보여 주고 **[질문]** 되돌릴지 묻는다 (에이전트가 임의로 `checkout` 하지 않는다) |
| `데이터 : … 에 쓸 수 없습니다` | `%LOCALAPPDATA%` 권한 문제. **[질문]** 다른 폴더를 쓸지 묻고 → 환경 변수 `FLOW_HOME=<폴더>` 를 사용자 범위로 두는 법을 안내한다 (에이전트가 레지스트리를 고치지 않는다) |
| `쿼리 패키지: … 이 파이썬에 없음` | 4단계 끝의 안내대로 — 흐름도는 되고 `--run` 만 그 패키지가 있는 파이썬이 필요하다 |
| `! 없는 경로: …` | `python "D:\OPENCODE\flow-1\flow-1.py" --remove "<그 경로>"` 뒤 5단계를 다시 |
| 감시 폴더의 쿼리가 0 · 창에서 카드가 안 나옴 | 4단계의 `query.calls` 를 사용자 · 사내 스킬과 다시 확인. 그래도 안 되면 그 파일로 `python "D:\OPENCODE\flow-1\flow-1.py" --scan "<파일>"` 을 실행해 출력을 사용자에게 보여 주고 멈춘다 (고치는 일은 [docs/GUIDE.md](docs/GUIDE.md) › 05) |
| `파일이 많아 scan.max_files 에서 멈췄습니다` | 감시 폴더를 좁히거나 `--set "scan.max_files=1000"` |
| `포트 … 를 열 수 없습니다` | `--set "port=8788"` (대장의 8785–8794 안에서) |
| `설정 오류: … 형식 오류` | 사용자가 메모장으로 `%LOCALAPPDATA%\flow-1\config.json` 을 고치거나, 이름을 `config.bak.json` 으로 바꾸고 3단계부터 다시 |
| `git pull` 이 `untracked working tree files would be overwritten` 와 함께 `AGENTS.md` · `CLAUDE.md` 를 보여 줌 | `D:\OPENCODE` 에 사용자가 만든 같은 이름 파일이 있다 (opencode `/init` 등). **[질문]** "`D:\OPENCODE\AGENTS.md` 를 `AGENTS.local.md` 로 이름을 바꿔도 될까요?" → 바꾼 뒤 pull 을 다시 한다. 그 내용을 계속 쓰려면 opencode 설정의 `instructions` 에 `AGENTS.local.md` 를 넣도록 사용자에게 안내한다 (설정 파일은 에이전트가 고치지 않는다) |

## 업데이트

사용자가 업데이트를 요청했을 때. 끄면 창에 붙여 넣은 코드 · 이번만 연 파일은 사라진다 (감시 목록 · 실행 기록은 그대로). **[질문]** "Flow–1 을 잠깐 끕니다. 괜찮을까요?" → 된 뒤에:

```text
python "D:\OPENCODE\flow-1\flow-1.py" --stop
git -C "D:\OPENCODE" pull --ff-only
python "D:\OPENCODE\flow-1\flow-1.py" --check
```

zip 으로 받았다면 `git pull` 대신 **[질문]** 새 zip 을 `D:\OPENCODE` 에 덮어 풀어 달라고 부탁한다.
**사내에서 Flow–1 코드를 고쳐 쓰고 있다면** 위의 `pull --ff-only` 는 멈추고, zip 덮어 풀기는 고친 것을 지운다 → 이 순서 대신 [AGENTS.md › 04](AGENTS.md#04-사내-사본에서-고칠-때--업데이트와-부딪히지-않게) 의 순서로 한다 (`git status` 에 바뀐 파일이 보이거나 `inhouse` 가지에 있으면 고쳐 쓰는 중이다).
설정 · 실행 기록은 `%LOCALAPPDATA%\flow-1\` 에 있어서 업데이트로 바뀌지 않는다.

## 제거

```text
python "D:\OPENCODE\flow-1\flow-1.py" --stop
python "D:\OPENCODE\flow-1\flow-1.py" --shortcut off
```

그다음 **[질문]** "`%LOCALAPPDATA%\flow-1` 의 설정(감시 목록 · 사내 패키지 이름)과 실행 기록을 지울까요?" → 확인 후에만 지운다:

```text
python -c "import os, shutil; shutil.rmtree(os.path.join(os.environ['LOCALAPPDATA'], 'flow-1'), ignore_errors=True)"
```

프로그램 폴더 `D:\OPENCODE\flow-1` 은 works 저장소의 일부라서 **지우지 않는다** — 지우면 git 이 '바뀐 파일' 로 보고 다른 works 도구의 업데이트(`git pull`)가 멈춘다. 켜지 않은 코드는 남아 있어도 아무 일도 하지 않는다.
works 전체를 지울 때만 **[질문]** "다른 works 도구도 함께 지워집니다. `D:\OPENCODE` 를 지울까요?" → 확인 후 지운다.

## 참고: 명령 모음

| 명령 | 하는 일 |
|---|---|
| (없음) · `경로…` | 창을 연다 (경로를 주면 감시 목록에 더하고) · 이미 켜져 있으면 창만 |
| `--setup` | 설정 파일 만들기 + 점검 |
| `--check` | 데이터 · 쿼리 패키지 · 감시 · 자체 시험 점검 (마지막 줄 `결과: …` · 종료 코드 0 · 1 · 3) |
| `--set "키=값"` | config.json 값 바꾸기 (여러 번 가능 · 목록은 `;` 로 · 틀리면 되돌림) |
| `--remove "경로"` | 감시 목록에서 빼기 |
| `--scan 경로…` | 창 없이 — 쿼리 · 조인 · 조건 · 흐름을 글로 (파일을 읽기만) |
| `--json 경로…` | 창 없이 — 분석 결과 JSON (format 1) |
| `--svg 파일.svg 경로… [--detail 1-3] [--theme light]` | 흐름도를 SVG 파일로 |
| `--run 스크립트.py [인자…]` | 스크립트를 **실행**하며 쿼리 호출마다 시간 · 행 수 기록 (사용자가 원할 때만) |
| `--shortcut on` · `--shortcut off` | 시작 메뉴 바로가기 만들기 · 지우기 |
| `--status` · `--stop` | 실행 중인지 확인 · 끄기 |
| `--version` | 버전 |
