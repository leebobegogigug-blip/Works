# Ascii–1 설치 가이드 — OpenCode 에이전트용

> **사람용 한 줄:** OpenCode 에 아래 프롬프트를 붙여넣으면 이 문서대로 설치합니다.
> Ascii–1 은 works 저장소(`https://github.com/leebobegogigug-blip/Works`)의 `ascii-1` 폴더입니다.
> 지금은 개발 중이라 설치해도 `version` · `help` 만 됩니다.
>
> ```text
> Ascii–1 을 설치해줘. works 저장소를 D:\OPENCODE 에 받고, 프로그램 폴더는 D:\OPENCODE\ascii-1 이야.
> 1. 코드 받기: D:\OPENCODE 가 없거나 비어 있으면 git clone https://github.com/leebobegogigug-blip/Works.git "D:\OPENCODE"
>    (이미 works 가 받아져 있으면 받지 말고, git 이 안 되면 Works-repo.zip 을 D:\OPENCODE 에 풀어)
> 2. 그다음 D:\OPENCODE\ascii-1\INSTALL.md 를 끝까지 읽고 그 순서대로만 진행해.
>    API 키·토큰은 절대 출력하지 말고, [질문] 표시가 있는 곳에서는 나한테 물어봐.
> ```

---

이 아래는 **OpenCode(에이전트)가 실행할 절차**입니다.

## 0. 목표와 규칙

**목표**: `D:\OPENCODE\ascii-1` 에서 Ascii–1 이 실행되는지 확인한다. 설치할 것은 없다 — 받은 파일이 곧 프로그램이다.

**규칙 — 반드시 지킬 것**

1. **명령은 이 문서에 적힌 것만** 실행한다. 모든 명령은 Git Bash · cmd · PowerShell 어디서나 그대로 동작하게 적혀 있다 (경로는 항상 큰따옴표).
2. **관리자 권한 금지.** PATH · 시작 프로그램 · 레지스트리는 건드리지 않는다.
3. **[질문]** 표시가 있는 곳에서는 멈추고 사용자에게 묻는다.
4. 출력이 예상과 다르면 추측해서 우회하지 말고, 출력을 그대로 보여 주고 [문제 해결](#문제-해결) 표를 따른다. 표에 없으면 멈추고 보고한다.
5. 명령은 한 번에 하나씩 실행하고, 결과를 확인한 뒤 다음으로 간다.

## 1. 파이썬 확인

```text
python --version
```

- **확인**: `Python 3.8` 이상이면 통과.
- **실패하면**: `py -3 --version` 을 실행한다. 이게 되면 이후 모든 명령의 `python` 을 `py -3` 으로 바꾼다. 이것도 안 되면 **[질문]** 사용자에게 파이썬 설치를 부탁하고 멈춘다.

## 2. 코드 받기

```text
python -c "import os; print(os.path.isfile(r'D:\OPENCODE\ascii-1\ascii-1.py'))"
```

- **확인**: `True` 면 3단계로.
- **실패하면**: `D:\OPENCODE` 가 비어 있으면 `git clone https://github.com/leebobegogigug-blip/Works.git "D:\OPENCODE"`. 이미 works 가 있으면 `git -C "D:\OPENCODE" pull --ff-only`. 다른 파일이 있는 폴더면 **[질문]** 목록을 보여 주고 묻는다. 아무것도 지우거나 옮기지 않는다.

## 3. 실행 확인

```text
python "D:\OPENCODE\ascii-1\ascii-1.py" version
```

- **확인**: `ascii-1 ` 다음에 버전 숫자가 한 줄 나온다.
- **실패하면**: [문제 해결](#문제-해결).

## 9. 완료 보고

아래 형식으로 사용자에게 보고한다.

```text
Ascii–1 설치 완료
- 위치     : D:\OPENCODE\ascii-1
- 파이썬   : (1단계 결과)
- 실행     : (3단계 결과)
- 멈춘 곳  : 없음 | n단계 — 이유와 사용자에게 필요한 조치
- 쓰는 법  : 아직 변환 기능이 없다 (개발 중). 지금은 version · help 만 된다
```

---

## 문제 해결

| 출력에 보이는 것 | 조치 |
|---|---|
| `git pull` 이 `untracked working tree files would be overwritten` 와 함께 `AGENTS.md` · `CLAUDE.md` 를 보여 줌 | `D:\OPENCODE` 에 사용자가 만든 같은 이름 파일이 있다 (opencode `/init` 등). **[질문]** "`D:\OPENCODE\AGENTS.md` 를 `AGENTS.local.md` 로 이름을 바꿔도 될까요?" → 바꾼 뒤 pull 을 다시 한다. 그 내용을 계속 쓰려면 opencode 설정의 `instructions` 에 `AGENTS.local.md` 를 넣도록 사용자에게 안내한다 (설정 파일은 에이전트가 고치지 않는다) |
| `python` 을 찾을 수 없음 | 1단계의 `py -3` 안내를 따른다 |

## 업데이트

```text
git -C "D:\OPENCODE" pull --ff-only
python "D:\OPENCODE\ascii-1\ascii-1.py" version
```

## 제거

Ascii–1 은 PC 에 남기는 것이 없다 (사용자 PATH · 바로가기 · 레지스트리 · 데이터 폴더 모두 없음). 되돌릴 것이 없다.

프로그램 폴더 `D:\OPENCODE\ascii-1` 은 works 저장소의 일부라서 **지우지 않는다** — 지우면 git 이 '바뀐 파일' 로 보고 다른 앱의 업데이트(`git pull`)가 멈춘다.
이 앱으로 만든 결과 `.txt` 파일은 입력 PNG 옆에 있으니 사용자가 직접 지운다.
works 전체를 지울 때만 **[질문]** "다른 works 도구도 함께 지워집니다. `D:\OPENCODE` 를 지울까요?" → 확인 후 지운다.

## 참고: 명령 모음

| 명령 | 하는 일 |
|---|---|
| `version` | 버전 |
| `help` | 도움말 |
