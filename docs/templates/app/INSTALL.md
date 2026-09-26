# {{NAME}} 설치 가이드 — OpenCode 에이전트용

> **사람용 한 줄:** OpenCode 에 아래 프롬프트를 붙여넣으면 이 문서대로 설치합니다.
> {{NAME}} 은 works 저장소(`https://github.com/leebobegogigug-blip/Works`)의 `{{APP}}` 폴더입니다.
>
> ```text
> {{NAME}} 을 설치해줘. works 저장소를 D:\OPENCODE 에 받고, 프로그램 폴더는 D:\OPENCODE\{{APP}} 이야.
> 1. 코드 받기: D:\OPENCODE 가 없거나 비어 있으면 git clone https://github.com/leebobegogigug-blip/Works.git "D:\OPENCODE"
>    (이미 works 가 받아져 있으면 받지 말고, git 이 안 되면 Works-repo.zip 을 D:\OPENCODE 에 풀어)
> 2. 그다음 D:\OPENCODE\{{APP}}\INSTALL.md 를 끝까지 읽고 그 순서대로만 진행해.
>    API 키·토큰은 절대 출력하지 말고, [질문] 표시가 있는 곳에서는 나한테 물어봐.
> ```

---

이 아래는 **OpenCode(에이전트)가 실행할 절차**입니다.
<!-- 필수 절: 목표와 규칙 · 단계(확인 · 실패하면) · [질문] · 완료 보고 · 문제 해결 · 업데이트 · 제거 (RULES.md › W-08) -->

## 0. 목표와 규칙

**목표**: `D:\OPENCODE\{{APP}}` 에 {{NAME}} 을 설치하고, 점검을 통과시키고, (실행 중인 상태로) 끝낸다.

**규칙 — 반드시 지킬 것**

1. **명령은 이 문서에 적힌 것만** 실행한다. 모든 명령은 Git Bash · cmd · PowerShell 어디서나 그대로 동작하게 적혀 있다 (경로는 항상 큰따옴표).
2. **비밀 금지**: 설정 파일의 키 · 토큰을 읽기 도구나 `cat`/`type`/`Get-Content` 로 열거나 출력하지 않는다. 사용자가 키를 채팅에 붙여넣으려 하면 말린다.
3. **관리자 권한 금지.** 사용자 범위 변경(사용자 PATH · 시작 프로그램 등)은 **[질문]** 으로 동의를 받은 뒤에만.
4. **[질문]** 표시가 있는 곳에서는 멈추고 사용자에게 묻는다.
5. 출력이 예상과 다르면 추측해서 우회하지 말고, 출력을 그대로 보여 주고 [문제 해결](#문제-해결) 표를 따른다. 표에 없으면 멈추고 보고한다.
6. 명령은 한 번에 하나씩 실행하고, 결과를 확인한 뒤 다음으로 간다.

## 1. 파이썬 확인

```text
python --version
```

- **확인**: `Python 3.8` 이상이면 통과.
- **실패하면**: `py -3 --version` 을 실행한다. 이게 되면 이후 모든 명령의 `python` 을 `py -3` 으로 바꾼다. 이것도 안 되면 **[질문]** 사용자에게 파이썬 설치를 부탁하고 멈춘다.

## 2. 코드 받기

```text
python -c "import os; print(os.path.isfile(r'D:\OPENCODE\{{APP}}\{{APP}}.py'))"
```

- **확인**: `True` 면 3단계로.
- **실패하면**: `D:\OPENCODE` 가 비어 있으면 `git clone https://github.com/leebobegogigug-blip/Works.git "D:\OPENCODE"`. 이미 works 가 있으면 `git -C "D:\OPENCODE" pull --ff-only`. 다른 파일이 있는 폴더면 **[질문]** 목록을 보여 주고 묻는다. 아무것도 지우거나 옮기지 않는다.

## 3. 설정 + 점검

```text
python "D:\OPENCODE\{{APP}}\{{APP}}.py" --setup
```

- **확인**: 마지막 줄이 `결과: OK`.
- **실패하면**: `결과: 확인 필요` → 출력에 나온 선택지로 **[질문]**. `결과: 점검 실패` → [문제 해결](#문제-해결).

<!-- 앱마다 필요한 단계를 이어서. 단계마다 확인 · 실패하면 -->

## 9. 완료 보고

아래 형식으로 사용자에게 보고한다. **키 값은 쓰지 않는다.**

```text
{{NAME}} 설치 완료
- 위치     : D:\OPENCODE\{{APP}} (버전 · python "D:\OPENCODE\{{APP}}\{{APP}}.py" --version)
- 파이썬   : (1단계 결과)
- 점검     : (3단계 결과)
- 멈춘 곳  : 없음 | n단계 — 이유와 사용자에게 필요한 조치
- 쓰는 법  : (한 줄)
```

---

## 문제 해결

`--setup` / `--check` 출력에 나온 문구로 찾는다. 고친 뒤에는 항상 `--check` → `결과: OK`.

| 출력에 보이는 것 | 조치 |
|---|---|
| `포트 … 를 열 수 없습니다` | `--set "port=<대장에 등록한 대역 안의 다른 번호>"` |

## 업데이트

```text
python "D:\OPENCODE\{{APP}}\{{APP}}.py" --stop
git -C "D:\OPENCODE" pull --ff-only
python "D:\OPENCODE\{{APP}}\{{APP}}.py" --check
```

데이터(`%LOCALAPPDATA%\{{APP}}\`)는 저장소 밖에 있어서 업데이트로 바뀌지 않는다.

## 제거

```text
python "D:\OPENCODE\{{APP}}\{{APP}}.py" --stop
```

<!-- 설치 때 PC 에 남긴 것을 모두 되돌린다 (docs/REGISTRY.md › PC 에 남기는 것) -->
그다음 **[질문]** "`%LOCALAPPDATA%\{{APP}}\` 의 데이터를 백업할까요?" → 사용자 확인 후에만 데이터 폴더와 `D:\OPENCODE\{{APP}}` 를 지운다.

## 참고: 명령 모음

| 명령 | 하는 일 |
|---|---|
| `--setup` | 설정 만들기 + 점검 |
| `--check` | 점검 (마지막 줄 `결과: …`) |
| `--status` · `--stop` | 실행 중인지 확인 · 끄기 |
| `--version` | 버전 |
