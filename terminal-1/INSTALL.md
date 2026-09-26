# Terminal–1 설치 가이드 — AI 에이전트(opencode)가 실행하는 용도

> **사람이 할 일은 한 줄입니다.** opencode를 열고 이렇게 말하세요.
>
> ```
> INSTALL.md 를 처음부터 끝까지 읽고, 거기 적힌 순서대로 Terminal–1 설치를 진행해줘.
> ```
>
> 이 파일이 아직 PC에 없으면 저장소 주소를 알려 주세요:
> `https://github.com/leebobegogigug-blip/Works` 의 `terminal-1/INSTALL.md`

---

## 0. 에이전트에게 — 작업 규칙

너(opencode)는 이 문서의 단계를 **순서대로** 실행해 Windows PC에 Terminal–1을 설치한다.

1. **셸:** 모든 명령은 Windows PowerShell 문법이다. 네 셸 도구가 PowerShell이 아니면(cmd, bash 등)
   `powershell -NoProfile -ExecutionPolicy Bypass -Command "<명령>"` 으로 감싸서 실행한다.
2. **확인:** 각 단계의 `확인`을 실제로 실행하고, 기대 결과와 다르면 `실패하면`과 [문제 해결](#문제-해결)을 따른다. 추측으로 넘어가지 않는다.
3. **관리자 권한 금지:** 관리자 권한이 필요한 명령은 쓰지 않는다. 시스템 PATH가 아니라 **사용자** PATH만 바꾼다.
4. **덮어쓰기 금지:** 이미 있는 폴더나 설정 파일을 지우거나 덮어쓰지 않는다. 설정 파일을 고치기 전에는 반드시 백업한다.
5. **멈추고 묻기:** **[질문]** 표시가 있는 곳과 아래 경우에는 멈추고 사용자에게 묻는다.
   - 설치 위치가 이미 있고 내용이 다를 때
   - 네트워크가 막혀 무언가를 내려받지 못할 때
   - 필수 프로그램(Python, Windows Terminal, opencode)이 없을 때
6. **보고:** 끝나면 11단계 형식으로 보고한다. 업데이트 · 제거는 문서 끝의 [업데이트](#업데이트) · [제거](#제거)를 따른다.

설치 위치 기본값은 아래와 같다. 사용자가 다른 경로를 말하면 그 경로를 쓴다.

```powershell
$Root  = 'D:\OPENCODE'             # 저장소 전체
$T1 = 'D:\OPENCODE\terminal-1'       # 프로그램 폴더 (PATH에 넣을 곳)
```

`$Root`, `$T1` 변수는 명령마다 다시 정의해서 쓴다. 셸 호출 사이에 변수가 남지 않을 수 있다.

---

## 1. 필수 프로그램 확인

```powershell
$PSVersionTable.PSVersion.ToString()
Get-Command wt -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
Get-Command opencode -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
Get-Command git -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
if (Get-Command py -ErrorAction SilentlyContinue) { py -3 --version } else { python --version }
```

**확인**
- PowerShell 5.1 이상
- `wt` 경로가 나온다 (Windows Terminal)
- `opencode` 경로가 나온다
- Python 3.8 이상
- `git`은 없어도 된다. 없으면 2단계에서 zip 방식을 쓴다.

**실패하면**
- **[질문]** `wt`, `opencode`, Python 중 하나라도 없으면 멈추고, 무엇이 없는지 알리고 설치를 부탁한다.
- Python이 `Microsoft Store`로 연결되는 가짜 `python.exe`라서 버전이 안 나오면, Python 설치가 필요하다고 알린다.
- 이 단계에서는 아무것도 설치하지 않는다.

---

## 2. 소스 받기

먼저 설치 위치가 이미 있는지 본다.

```powershell
$Root = 'D:\OPENCODE'
Test-Path $Root
```

- **`False`** (처음 설치). D 드라이브 자체가 없으면(`Test-Path D:\`가 `False`) **[질문]** 다른 경로를 묻는다.
  - git이 있으면 아래처럼 받는다.

    ```powershell
    $Root = 'D:\OPENCODE'
    New-Item -ItemType Directory -Force -Path $Root | Out-Null
    git clone https://github.com/leebobegogigug-blip/Works.git $Root
    ```

  - git이 없거나 clone이 실패하면(회사 네트워크 차단 등) 멈추고, **[질문]** 사용자에게 요청한다.
    "저장소 zip(`Works-repo.zip` 또는 GitHub의 *Code → Download ZIP*)을 받아 `D:\OPENCODE`에 풀어 주세요."
- **`True`인데 비어 있음** (`(Get-ChildItem $Root -Force | Measure-Object).Count`가 `0`)
  - `False`일 때와 똑같이 clone한다. git은 빈 폴더에 clone할 수 있다.
- **`True`이고 안에 다른 것이 있음** (D 드라이브의 `OPENCODE` 폴더는 이미 다른 용도로 쓰고 있을 수 있다)
  - `$Root\.git`이 없으면 **[질문]** **멈추고 묻는다.** 안에 있는 항목 목록을 보여 주고, 이 폴더에 이어서 설치할지 다른 경로를 쓸지 확인한다. 기존 파일은 절대 옮기거나 지우지 않는다.
  - `$Root\.git`이 있으면 `git -C $Root status --short`로 수정된 파일이 없는지 본다.
  - 수정된 파일이 없으면 `git -C $Root pull --ff-only`로 업데이트한다.
  - 수정된 파일이 있으면 **[질문]** 목록을 보여 주고 멈추고 묻는다. 아무것도 되돌리거나 지우지 않는다.

**확인**

```powershell
$T1 = 'D:\OPENCODE\terminal-1'
'terminal-1.ps1','terminal-1.cmd','t1_monitor.py','t1_term.py','t1_pet.py','t1_pet_data.py','t1_pet_ui.py','t1_pet_run.py' |
  ForEach-Object { '{0,-20} {1}' -f $_, (Test-Path (Join-Path $T1 $_)) }
```

8개가 모두 `True`여야 한다.

**실패하면**
- zip을 풀다가 폴더가 한 겹 더 생겼을 수 있다(예: `D:\OPENCODE\Works-main\terminal-1`).
- `Get-ChildItem D:\OPENCODE -Recurse -Filter terminal-1.ps1`로 실제 위치를 찾는다.
- 찾은 위치로 `$T1`를 바꾸고, 바꾼 사실을 보고에 적는다.

---

## 3. 인터넷에서 받은 파일 차단 풀기

zip으로 받았으면 Windows가 파일을 "인터넷에서 받음"으로 표시해 스크립트 실행을 막을 수 있다. git으로 받았어도 해도 무해하다.

```powershell
$T1 = 'D:\OPENCODE\terminal-1'
Get-ChildItem $T1 -Recurse -File | Unblock-File
```

---

## 4. 동작 점검 (설치 전 자체 테스트)

```powershell
$T1 = 'D:\OPENCODE\terminal-1'
Set-Location $T1
if (Get-Command py -ErrorAction SilentlyContinue) { $py = 'py'; $pa = @('-3') } else { $py = 'python'; $pa = @() }
& $py @pa -m unittest discover -s tests 2>&1 | Select-Object -Last 3
```

**확인:** 마지막 줄이 `OK`이다. 테스트는 123개 전후.

**실패하면**
- 실패한 테스트 이름과 에러 마지막 20줄을 보고에 넣는다.
- 설치는 계속 진행하되, 테스트가 실패했다는 사실을 보고 맨 위에 적는다.
- 코드를 고치려고 하지 않는다.

---

## 5. PATH에 추가 (사용자 PATH)

```powershell
$T1 = 'D:\OPENCODE\terminal-1'
$p = [Environment]::GetEnvironmentVariable('Path', 'User')
if (-not $p) { $p = '' }
$parts = $p.Split(';') | Where-Object { $_ -ne '' }
if ($parts -notcontains $T1) {
    [Environment]::SetEnvironmentVariable('Path', (($parts + $T1) -join ';'), 'User')
    'PATH added'
} else { 'PATH already has it' }
$env:Path = "$env:Path;$T1"   # 지금 셸에서도 바로 쓰도록
```

**확인:** `Get-Command terminal-1.cmd`가 `$T1\terminal-1.cmd`를 가리킨다.

PATH 에 `D:\OPENCODE\ocmux` 가 있거나 `%LOCALAPPDATA%\ocmux` 폴더가 있으면(예전 이름으로 설치돼 있던 PC) **[질문]** 사용자에게 알린다: "예전 이름(ocmux)에서 자동으로 옮기는 기능은 1.1.0 에서 없어졌습니다. 펫 · 채널을 그대로 쓰시려면 매뉴얼의 '예전 이름(ocmux) 설치' 대로 직접 옮겨 주세요." 에이전트가 따로 지우거나 옮기지 않는다.

주의: 이미 열려 있는 다른 터미널 창에는 새 PATH가 반영되지 않는다. 사용자에게 알릴 사항으로 적어 둔다.

---

## 6. 색 테마 설치

```powershell
$T1 = 'D:\OPENCODE\terminal-1'
& (Join-Path $T1 'terminal-1.cmd') setup
```

**확인:** 출력에 `SCHEME`과 `ready`가 보인다.

**실패하면**
- 실행 정책 오류라면 `terminal-1.cmd`(이미 Bypass로 실행함)를 썼는지 다시 본다.
- 그룹 정책으로 막혀 있다면 우회하지 말고 멈춘다. 오류 전문을 사용자에게 보여 준다.

---

## 7. 한 프레임 화면 점검

opencode 없이 펫 화면을 한 장 그려 본다. 점검용 펫 저장 파일이 생기므로 끝나면 지운다.

```powershell
$T1 = 'D:\OPENCODE\terminal-1'
Set-Location $T1
if (Get-Command py -ErrorAction SilentlyContinue) { $py = 'py'; $pa = @('-3') } else { $py = 'python'; $pa = @() }
& $py @pa t1_monitor.py rpg --name install-check --once 1 --cols 80 --rows 24 | Out-Null
"exit=$LASTEXITCODE"
Remove-Item (Join-Path $env:LOCALAPPDATA 'terminal-1\pet-install-check*') -ErrorAction SilentlyContinue
```

**확인:** `exit=0`

---

## 8. 추천 글꼴 설치 (선택 · 관리자 권한 없이)

**[질문]** 사용자에게 먼저 묻는다. "도트 글꼴 GNU Unifont 15.1.01(무료, OFL/GPL)을 터미널 글꼴로 설치할까요? (지울 때는 [제거](#제거) 4번)"
**아니요**면 9단계를 건너뛰고 10단계로 간다.

**8-1. 내려받기**

```powershell
$tmp = Join-Path $env:TEMP 'unifont'
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
$otf = Join-Path $tmp 'unifont-15.1.01.otf'
$urls = @(
  'https://unifoundry.com/pub/unifont/unifont-15.1.01/font-builds/unifont-15.1.01.otf',
  'https://ftp.gnu.org/gnu/unifont/unifont-15.1.01/unifont-15.1.01.otf'
)
foreach ($u in $urls) {
  try { Invoke-WebRequest $u -OutFile $otf -UseBasicParsing; if ((Get-Item $otf).Length -gt 1MB) { "downloaded: $u"; break } } catch { "failed: $u" }
}
Test-Path $otf
```

**확인:** `True`이고 파일 크기가 수 MB다.

**실패하면**
- 두 주소 모두 막혔으면 멈추고 **[질문]** 사용자에게 부탁한다.
  "`unifont-15.1.01.otf`를 받아서 경로를 알려 주세요 (https://unifoundry.com/unifont/)."
- 사용자가 경로를 주면 그 파일을 `$otf`로 쓴다.

**8-2. 현재 사용자용으로 설치** (Windows 10 1809 이상)

```powershell
$otf = Join-Path $env:TEMP 'unifont\unifont-15.1.01.otf'
$fontDir = Join-Path $env:LOCALAPPDATA 'Microsoft\Windows\Fonts'
New-Item -ItemType Directory -Force -Path $fontDir | Out-Null
$dest = Join-Path $fontDir 'unifont-15.1.01.otf'
if (-not (Test-Path $dest)) { Copy-Item $otf $dest }
New-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows NT\CurrentVersion\Fonts' `
  -Name 'Unifont (OpenType)' -Value $dest -PropertyType String -Force | Out-Null
'font installed'
```

**확인:** `Test-Path $dest`가 `True`다.
- Windows Terminal은 창을 모두 닫았다가 다시 열어야 새 글꼴을 인식한다.
- 일부 버전은 "현재 사용자용" 글꼴을 목록에 늦게 띄운다. 9단계 뒤에도 글꼴이 안 바뀌면 사용자에게 부탁한다.
  "`unifont-15.1.01.otf` 우클릭 → **모든 사용자용으로 설치**를 해 주세요." 이 방법은 관리자 권한이 필요할 수 있다.

---

## 9. Windows Terminal 글꼴 설정 (8단계를 했을 때만)

**9-1. 설정 파일 찾기** (앞에서부터 처음 있는 것)

```powershell
@(
  "$env:LOCALAPPDATA\Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState\settings.json",
  "$env:LOCALAPPDATA\Packages\Microsoft.WindowsTerminalPreview_8wekyb3d8bbwe\LocalState\settings.json",
  "$env:LOCALAPPDATA\Microsoft\Windows Terminal\settings.json"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
```

**9-2. 백업 후 수정**

```powershell
$s = '<9-1에서 찾은 경로>'
Copy-Item $s "$s.bak-terminal-1-$(Get-Date -Format yyyyMMdd-HHmmss)"
```

`profiles` → `defaults` 안에 아래 두 키를 넣는다. 이미 있는 `font` 객체가 있으면 `face`, `size`만 바꾼다.

```jsonc
"font": { "face": "Unifont", "size": 12 },
"antialiasingMode": "aliased"
```

**수정 규칙**
- `settings.json`에는 주석(`//`)과 끝 쉼표가 있을 수 있다.
  PowerShell 5.1의 `ConvertFrom-Json` → `ConvertTo-Json`으로 통째로 다시 쓰면 주석이 사라지고 깨질 수 있으니 **쓰지 않는다**.
- 텍스트로 해당 부분만 고친다.
- `defaults`가 `"defaults": {}` 처럼 비어 있으면 그 안에 넣는다.
- 구조가 예상과 달라 안전하게 고치기 어렵다면 수정하지 말고 사용자에게 안내만 한다.
  "설정 → 프로필 기본값 → 모양 → 글꼴에서 Unifont, 크기 12를 고르세요."

**확인:** 파일을 다시 읽어 `Unifont`가 `defaults` 안에 딱 한 번 들어갔는지 본다.

**실패하면:** 백업 파일로 되돌린다.

```powershell
Copy-Item "<백업 경로>" $s -Force
```

---

## 10. 사용자에게 남길 마무리 안내

에이전트는 `terminal-1 add`를 **직접 실행하지 않는다**. 지금 이 opencode 세션이 들어 있는 창을 새 탭 구성이 가리거나 흔들 수 있기 때문이다. 대신 사용자에게 아래를 안내한다.

1. Windows Terminal 창을 **모두** 닫았다가 새로 연다. 새 PATH, 색 테마, 글꼴이 이때 적용된다.
2. 작업할 프로젝트 폴더에서 이렇게 실행한다.

   ```powershell
   cd C:\work\<프로젝트>
   terminal-1 add                 # 막히면: terminal-1.cmd add
   ```

3. 처음 한 번은 `00 overview` 탭과 채널 탭이 함께 열린다. 어느 창에서든 `?`를 누르면 화면 설명이 나온다.

---

## 11. 보고 형식

설치가 끝나면(또는 멈추면) 이 형식으로 사용자에게 보고한다.

```
[Terminal–1 설치 결과]
위치        : D:\OPENCODE\terminal-1  (바꿨다면 이유)
Python      : 3.x.x (py -3 | python)
버전        : (terminal-1.cmd version 결과)
테스트      : OK 123 / 실패 n개 (이름)
PATH        : 추가됨 | 이미 있음
색 테마     : 설치됨
화면 점검   : exit=0
글꼴        : 설치+설정됨 | 설치만(설정은 수동 안내) | 건너뜀
설정 백업   : <경로> (9단계를 했을 때)
멈춘 곳     : 없음 | n단계 — 이유와 사용자에게 필요한 조치
다음 할 일  : Windows Terminal 모두 닫고 다시 열기 → 프로젝트 폴더에서 terminal-1 add
```

---

## 문제 해결

출력에 보이는 것으로 찾는다. 표에 없으면 멈추고 출력을 그대로 보고한다.

| 보이는 것 | 조치 |
|---|---|
| `running scripts is disabled` · 실행 정책 오류 | `terminal-1.ps1` 대신 `terminal-1.cmd` 로 실행한다 (`-ExecutionPolicy Bypass`). 그룹 정책으로 강제된 것이면 우회하지 않고 멈춘다 |
| `terminal-1` 을 찾을 수 없음 | PATH 는 새로 연 창부터 적용된다. 지금 창에서는 `D:\OPENCODE\terminal-1\terminal-1.cmd` 로 부른다 |
| 색 테마 `Terminal-1 Black` 이 안 보임 | Windows Terminal 창을 **모두** 닫았다가 연다. 그래도 없으면 `terminal-1.cmd setup` 을 다시 |
| 4단계 테스트 실패 | 설치는 계속하고, 실패한 테스트 이름과 에러 마지막 20줄을 보고 맨 위에 적는다. 코드를 고치지 않는다 |
| 글꼴이 목록에 없음 | Windows Terminal 을 모두 닫았다가 연다 → 그래도 없으면 **[질문]** "`unifont-15.1.01.otf` 우클릭 → 모든 사용자용으로 설치" 를 부탁한다 (관리자 권한이 필요할 수 있다) |
| `git pull` 이 `Your local changes … would be overwritten` | **[질문]** `git -C D:\OPENCODE status --short` 결과를 보여 주고 어떻게 할지 묻는다. 아무것도 되돌리거나 지우지 않는다 |
| `git pull` 이 `untracked working tree files would be overwritten` 와 함께 `AGENTS.md` · `CLAUDE.md` 를 보여 줌 | `D:\OPENCODE` 에 사용자가 만든 같은 이름 파일이 있다 (opencode `/init` 등). **[질문]** "`D:\OPENCODE\AGENTS.md` 를 `AGENTS.local.md` 로 이름을 바꿔도 될까요?" → 바꾼 뒤 pull 을 다시 한다. 그 내용을 계속 쓰려면 opencode 설정의 `instructions` 에 `AGENTS.local.md` 를 넣도록 사용자에게 안내한다 (설정 파일은 에이전트가 고치지 않는다) |

## 업데이트

사용자가 업데이트를 요청했을 때.

```powershell
$Root = 'D:\OPENCODE'
git -C $Root status --short
```

수정된 파일이 있으면 [문제 해결](#문제-해결)의 `Your local changes` 줄을 따른다. 없으면:

```powershell
$Root = 'D:\OPENCODE'; $T1 = 'D:\OPENCODE\terminal-1'
git -C $Root pull --ff-only
& (Join-Path $T1 'terminal-1.cmd') setup
& (Join-Path $T1 'terminal-1.cmd') version
```

**확인:** `SCHEME` · `ready` 와 `Terminal-1 x.y.z` 가 보인다.

사용자에게 안내한다: "열려 있는 Terminal–1 창은 옛 코드로 돌고 있습니다. Windows Terminal 창을 모두 닫았다가 연 뒤 프로젝트 폴더에서 `terminal-1 focus <이름>` 하세요. 펫 저장 · 채널 목록은 그대로입니다."
zip 으로 받았다면 `git pull` 대신 **[질문]** 새 zip 을 `D:\OPENCODE` 에 덮어 풀어 달라고 부탁한다 (데이터는 `%LOCALAPPDATA%\terminal-1` 에 있어서 그대로 남는다).

## 제거

사용자가 제거를 요청했을 때. 순서대로 하고, **[질문]** 에서 사용자가 원하지 않으면 그 항목은 건너뛴다.
먼저 **[질문]** "Terminal–1 창(탭)을 모두 닫아 주세요. 열려 있으면 파일을 지울 수 없습니다."

**1. 채널 풀기** — headless 서버도 꺼진다

```powershell
$T1 = 'D:\OPENCODE\terminal-1'
& (Join-Path $T1 'terminal-1.cmd') ls
```

표의 `NAME` 마다 `& (Join-Path $T1 'terminal-1.cmd') rm <이름>` 을 실행한다.

**2. 사용자 PATH 에서 빼기**

```powershell
$T1 = 'D:\OPENCODE\terminal-1'
$p = [Environment]::GetEnvironmentVariable('Path', 'User')
$parts = @(($p -split ';') | Where-Object { $_ -ne '' -and $_.TrimEnd('\') -ine $T1 })
[Environment]::SetEnvironmentVariable('Path', ($parts -join ';'), 'User')
'PATH removed'
```

**3. 색 테마 지우기** — `terminal-1 setup` 이 만든 Windows Terminal 조각 파일

```powershell
Remove-Item (Join-Path $env:LOCALAPPDATA 'Microsoft\Windows Terminal\Fragments\terminal-1') -Recurse -ErrorAction SilentlyContinue
'scheme removed'
```

**4. 글꼴 (8 · 9단계를 했을 때만)**

**[질문]** "Windows Terminal 글꼴 설정과 Unifont 글꼴도 되돌릴까요? 다른 프로그램이 Unifont 를 쓰고 있을 수 있습니다."

- 글꼴 설정: `settings.json` 을 9단계 백업으로 덮어쓰지 않는다 (백업 뒤에 바꾼 다른 설정이 사라진다). 사용자에게 안내한다: "설정 → 프로필 기본값 → 모양 → 글꼴을 원래 글꼴로 바꿔 주세요."
- 사용자가 바꾼 뒤, 글꼴 등록과 파일:

```powershell
Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows NT\CurrentVersion\Fonts' -Name 'Unifont (OpenType)' -ErrorAction SilentlyContinue
$f = Join-Path $env:LOCALAPPDATA 'Microsoft\Windows\Fonts\unifont-15.1.01.otf'
Remove-Item $f -ErrorAction SilentlyContinue
"font file still there: $(Test-Path $f)"
```

**확인:** `font file still there: False`. `True` 면 글꼴을 쓰는 창이 열려 있는 것이다 — 사용자에게 창을 모두 닫아 달라고 하고 한 번 더.

**5. 데이터**

**[질문]** "펫 저장 · 채널 목록(`%LOCALAPPDATA%\terminal-1`)을 백업할까요?" → 백업이 끝났거나 필요 없다고 하면, 확인 후에만:

```powershell
Remove-Item (Join-Path $env:LOCALAPPDATA 'terminal-1') -Recurse
```

**6. 프로그램 폴더는 지우지 않는다**

`D:\OPENCODE\terminal-1` 은 works 저장소의 일부라서 지우지 않는다 — 지우면 git 이 '바뀐 파일' 로 보고 다른 works 도구의 업데이트(`git pull`)가 멈춘다. PATH 에서 빠진 코드는 남아 있어도 아무 일도 하지 않는다.
works 전체를 지울 때만 **[질문]** "다른 works 도구도 함께 지워집니다. `D:\OPENCODE` 를 지울까요?" → 확인 후 지운다.
