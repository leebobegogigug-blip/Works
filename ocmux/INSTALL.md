# ocmux 설치 가이드 — AI 에이전트(opencode)가 실행하는 용도

> **사람이 할 일은 한 줄입니다.** opencode를 열고 이렇게 말하세요.
>
> ```
> INSTALL.md 를 처음부터 끝까지 읽고, 거기 적힌 순서대로 ocmux 설치를 진행해줘.
> ```
>
> 이 파일이 아직 PC에 없으면 저장소 주소를 알려 주세요:
> `https://github.com/leebobegogigug-blip/Works` 의 `ocmux/INSTALL.md`

---

## 0. 에이전트에게 — 작업 규칙

너(opencode)는 이 문서의 단계를 **순서대로** 실행해 Windows PC에 ocmux를 설치한다.

1. **셸:** 모든 명령은 Windows PowerShell 문법이다. 네 셸 도구가 PowerShell이 아니면(cmd, bash 등)
   `powershell -NoProfile -ExecutionPolicy Bypass -Command "<명령>"` 으로 감싸서 실행한다.
2. **확인:** 각 단계의 `확인`을 실제로 실행하고, 기대 결과와 다르면 `실패하면`을 따른다. 추측으로 넘어가지 않는다.
3. **관리자 권한 금지:** 관리자 권한이 필요한 명령은 쓰지 않는다. 시스템 PATH가 아니라 **사용자** PATH만 바꾼다.
4. **덮어쓰기 금지:** 이미 있는 폴더나 설정 파일을 지우거나 덮어쓰지 않는다. 설정 파일을 고치기 전에는 반드시 백업한다.
5. **멈추고 묻기:** 아래 경우에는 멈추고 사용자에게 묻는다.
   - 설치 위치가 이미 있고 내용이 다를 때
   - 네트워크가 막혀 무언가를 내려받지 못할 때
   - 필수 프로그램(Python, Windows Terminal, opencode)이 없을 때
6. **보고:** 끝나면 11단계 형식으로 보고한다.

설치 위치 기본값은 아래와 같다. 사용자가 다른 경로를 말하면 그 경로를 쓴다.

```powershell
$Root  = 'D:\OPENCODE'             # 저장소 전체
$Ocmux = 'D:\OPENCODE\ocmux'       # 프로그램 폴더 (PATH에 넣을 곳)
```

`$Root`, `$Ocmux` 변수는 명령마다 다시 정의해서 쓴다. 셸 호출 사이에 변수가 남지 않을 수 있다.

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
- `wt`, `opencode`, Python 중 하나라도 없으면 멈추고, 무엇이 없는지 사용자에게 알린다.
- Python이 `Microsoft Store`로 연결되는 가짜 `python.exe`라서 버전이 안 나오면, Python 설치가 필요하다고 알린다.
- 이 단계에서는 아무것도 설치하지 않는다.

---

## 2. 소스 받기

먼저 설치 위치가 이미 있는지 본다.

```powershell
$Root = 'D:\OPENCODE'
Test-Path $Root
```

- **`False`** (처음 설치). D 드라이브 자체가 없으면(`Test-Path D:\`가 `False`) 멈추고 묻는다.
  - git이 있으면 아래처럼 받는다.

    ```powershell
    $Root = 'D:\OPENCODE'
    New-Item -ItemType Directory -Force -Path $Root | Out-Null
    git clone https://github.com/leebobegogigug-blip/Works.git $Root
    ```

  - git이 없거나 clone이 실패하면(회사 네트워크 차단 등) 멈추고, 사용자에게 요청한다.
    "저장소 zip(`Works-repo.zip` 또는 GitHub의 *Code → Download ZIP*)을 받아 `D:\OPENCODE`에 풀어 주세요."
- **`True`인데 비어 있음** (`(Get-ChildItem $Root -Force | Measure-Object).Count`가 `0`)
  - `False`일 때와 똑같이 clone한다. git은 빈 폴더에 clone할 수 있다.
- **`True`이고 안에 다른 것이 있음** (D 드라이브의 `OPENCODE` 폴더는 이미 다른 용도로 쓰고 있을 수 있다)
  - `$Root\.git`이 없으면 **멈추고 묻는다.** 안에 있는 항목 목록을 보여 주고, 이 폴더에 이어서 설치할지 다른 경로를 쓸지 확인한다. 기존 파일은 절대 옮기거나 지우지 않는다.
  - `$Root\.git`이 있으면 `git -C $Root status --short`로 수정된 파일이 없는지 본다.
  - 수정된 파일이 없으면 `git -C $Root pull --ff-only`로 업데이트한다.
  - 수정된 파일이 있으면 멈추고 묻는다.

**확인**

```powershell
$Ocmux = 'D:\OPENCODE\ocmux'
'ocmux.ps1','ocmux.cmd','oc_monitor.py','ocmux_term.py','ocmux_pet.py','ocmux_pet_data.py','ocmux_pet_ui.py','ocmux_pet_run.py' |
  ForEach-Object { '{0,-20} {1}' -f $_, (Test-Path (Join-Path $Ocmux $_)) }
```

8개가 모두 `True`여야 한다.

**실패하면**
- zip을 풀다가 폴더가 한 겹 더 생겼을 수 있다(예: `D:\OPENCODE\Works-main\ocmux`).
- `Get-ChildItem D:\OPENCODE -Recurse -Filter ocmux.ps1`로 실제 위치를 찾는다.
- 찾은 위치로 `$Ocmux`를 바꾸고, 바꾼 사실을 보고에 적는다.

---

## 3. 인터넷에서 받은 파일 차단 풀기

zip으로 받았으면 Windows가 파일을 "인터넷에서 받음"으로 표시해 스크립트 실행을 막을 수 있다. git으로 받았어도 해도 무해하다.

```powershell
$Ocmux = 'D:\OPENCODE\ocmux'
Get-ChildItem $Ocmux -Recurse -File | Unblock-File
```

---

## 4. 동작 점검 (설치 전 자체 테스트)

```powershell
$Ocmux = 'D:\OPENCODE\ocmux'
Set-Location $Ocmux
if (Get-Command py -ErrorAction SilentlyContinue) { $py = 'py'; $pa = @('-3') } else { $py = 'python'; $pa = @() }
& $py @pa -m unittest discover -s tests 2>&1 | Select-Object -Last 3
```

**확인:** 마지막 줄이 `OK`이다. 테스트는 101개 전후.

**실패하면**
- 실패한 테스트 이름과 에러 마지막 20줄을 보고에 넣는다.
- 설치는 계속 진행하되, 테스트가 실패했다는 사실을 보고 맨 위에 적는다.
- 코드를 고치려고 하지 않는다.

---

## 5. PATH에 추가 (사용자 PATH)

```powershell
$Ocmux = 'D:\OPENCODE\ocmux'
$p = [Environment]::GetEnvironmentVariable('Path', 'User')
if (-not $p) { $p = '' }
$parts = $p.Split(';') | Where-Object { $_ -ne '' }
if ($parts -notcontains $Ocmux) {
    [Environment]::SetEnvironmentVariable('Path', (($parts + $Ocmux) -join ';'), 'User')
    'PATH added'
} else { 'PATH already has it' }
$env:Path = "$env:Path;$Ocmux"   # 지금 셸에서도 바로 쓰도록
```

**확인:** `Get-Command ocmux.cmd`가 `$Ocmux\ocmux.cmd`를 가리킨다.

주의: 이미 열려 있는 다른 터미널 창에는 새 PATH가 반영되지 않는다. 사용자에게 알릴 사항으로 적어 둔다.

---

## 6. 색 테마 설치

```powershell
$Ocmux = 'D:\OPENCODE\ocmux'
& (Join-Path $Ocmux 'ocmux.cmd') setup
```

**확인:** 출력에 `SCHEME`과 `ready`가 보인다.

**실패하면**
- 실행 정책 오류라면 `ocmux.cmd`(이미 Bypass로 실행함)를 썼는지 다시 본다.
- 그룹 정책으로 막혀 있다면 우회하지 말고 멈춘다. 오류 전문을 사용자에게 보여 준다.

---

## 7. 한 프레임 화면 점검

opencode 없이 펫 화면을 한 장 그려 본다. 점검용 펫 저장 파일이 생기므로 끝나면 지운다.

```powershell
$Ocmux = 'D:\OPENCODE\ocmux'
Set-Location $Ocmux
if (Get-Command py -ErrorAction SilentlyContinue) { $py = 'py'; $pa = @('-3') } else { $py = 'python'; $pa = @() }
& $py @pa oc_monitor.py rpg --name install-check --once 1 --cols 80 --rows 24 | Out-Null
"exit=$LASTEXITCODE"
Remove-Item (Join-Path $env:LOCALAPPDATA 'ocmux\pet-install-check*') -ErrorAction SilentlyContinue
```

**확인:** `exit=0`

---

## 8. 추천 글꼴 설치 (선택 · 관리자 권한 없이)

사용자에게 먼저 묻는다. "도트 한글 글꼴 갈무리모노(GalmuriMono11, 무료 OFL)를 터미널 글꼴로 설치할까요?"
**아니요**면 9단계로 넘어간다.

**8-1. 내려받기** (GitHub 최신 릴리스에서 zip 자산을 찾는다)

```powershell
$tmp = Join-Path $env:TEMP 'galmuri'
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
$rel = Invoke-RestMethod 'https://api.github.com/repos/quiple/galmuri/releases/latest' -Headers @{ 'User-Agent' = 'ocmux-install' }
$asset = $rel.assets | Where-Object { $_.name -like '*.zip' } | Select-Object -First 1
$asset.name
Invoke-WebRequest $asset.browser_download_url -OutFile (Join-Path $tmp 'galmuri.zip') -UseBasicParsing
Expand-Archive (Join-Path $tmp 'galmuri.zip') -DestinationPath $tmp -Force
$ttf = Get-ChildItem $tmp -Recurse -Filter 'GalmuriMono11.ttf' | Select-Object -First 1
$ttf.FullName
```

**실패하면**
- 네트워크 차단 등으로 받지 못하면 멈추고 사용자에게 부탁한다.
  "https://github.com/quiple/galmuri/releases 에서 zip을 받아 `GalmuriMono11.ttf` 경로를 알려 주세요."
- 자산 이름이 바뀌어 `GalmuriMono11.ttf`가 없으면, `Get-ChildItem $tmp -Recurse -Filter *.ttf`로 목록을 보여 주고 묻는다.

**8-2. 현재 사용자용으로 설치** (Windows 10 1809 이상)

```powershell
$ttf = Get-ChildItem (Join-Path $env:TEMP 'galmuri') -Recurse -Filter 'GalmuriMono11.ttf' | Select-Object -First 1
$fontDir = Join-Path $env:LOCALAPPDATA 'Microsoft\Windows\Fonts'
New-Item -ItemType Directory -Force -Path $fontDir | Out-Null
$dest = Join-Path $fontDir $ttf.Name
if (-not (Test-Path $dest)) { Copy-Item $ttf.FullName $dest }
New-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows NT\CurrentVersion\Fonts' `
  -Name 'GalmuriMono11 (TrueType)' -Value $dest -PropertyType String -Force | Out-Null
'font installed'
```

**확인:** `Test-Path $dest`가 `True`다.
- Windows Terminal은 창을 모두 닫았다가 다시 열어야 새 글꼴을 인식한다.
- 일부 버전은 "현재 사용자용" 글꼴을 목록에 늦게 띄운다. 9단계 뒤에도 글꼴이 안 바뀌면 사용자에게 부탁한다.
  "`GalmuriMono11.ttf` 우클릭 → **모든 사용자용으로 설치**를 해 주세요." 이 방법은 관리자 권한이 필요할 수 있다.

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
Copy-Item $s "$s.bak-ocmux-$(Get-Date -Format yyyyMMdd-HHmmss)"
```

`profiles` → `defaults` 안에 아래 두 키를 넣는다. 이미 있는 `font` 객체가 있으면 `face`, `size`만 바꾼다.

```jsonc
"font": { "face": "GalmuriMono11", "size": 9 },
"antialiasingMode": "aliased"
```

**수정 규칙**
- `settings.json`에는 주석(`//`)과 끝 쉼표가 있을 수 있다.
  PowerShell 5.1의 `ConvertFrom-Json` → `ConvertTo-Json`으로 통째로 다시 쓰면 주석이 사라지고 깨질 수 있으니 **쓰지 않는다**.
- 텍스트로 해당 부분만 고친다.
- `defaults`가 `"defaults": {}` 처럼 비어 있으면 그 안에 넣는다.
- 구조가 예상과 달라 안전하게 고치기 어렵다면 수정하지 말고 사용자에게 안내만 한다.
  "설정 → 프로필 기본값 → 모양 → 글꼴에서 GalmuriMono11, 크기 9를 고르세요."

**확인:** 파일을 다시 읽어 `GalmuriMono11`이 `defaults` 안에 딱 한 번 들어갔는지 본다.

**실패하면:** 백업 파일로 되돌린다.

```powershell
Copy-Item "<백업 경로>" $s -Force
```

---

## 10. 사용자에게 남길 마무리 안내

에이전트는 `ocmux add`를 **직접 실행하지 않는다**. 지금 이 opencode 세션이 들어 있는 창을 새 탭 구성이 가리거나 흔들 수 있기 때문이다. 대신 사용자에게 아래를 안내한다.

1. Windows Terminal 창을 **모두** 닫았다가 새로 연다. 새 PATH, 색 테마, 글꼴이 이때 적용된다.
2. 작업할 프로젝트 폴더에서 이렇게 실행한다.

   ```powershell
   cd C:\work\<프로젝트>
   ocmux add                 # 막히면: ocmux.cmd add
   ```

3. 처음 한 번은 `00 overview` 탭과 채널 탭이 함께 열린다. 어느 창에서든 `?`를 누르면 화면 설명이 나온다.

---

## 11. 보고 형식

설치가 끝나면(또는 멈추면) 이 형식으로 사용자에게 보고한다.

```
[ocmux 설치 결과]
위치        : D:\OPENCODE\ocmux  (바꿨다면 이유)
Python      : 3.x.x (py -3 | python)
테스트      : OK 101 / 실패 n개 (이름)
PATH        : 추가됨 | 이미 있음
색 테마     : 설치됨
화면 점검   : exit=0
글꼴        : 설치+설정됨 | 설치만(설정은 수동 안내) | 건너뜀
설정 백업   : <경로> (9단계를 했을 때)
멈춘 곳     : 없음 | n단계 — 이유와 사용자에게 필요한 조치
다음 할 일  : Windows Terminal 모두 닫고 다시 열기 → 프로젝트 폴더에서 ocmux add
```
