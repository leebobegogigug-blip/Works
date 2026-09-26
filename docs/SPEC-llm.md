# LLM 설정 규격

사내 LLM(OpenAI 호환 API)을 쓰는 works 앱이 따르는 설정 · 명령 규격이다 ([RULES.md › S-09](../RULES.md#규약)).
앱끼리 코드는 공유하지 않으므로(W-01) 같은 기능을 앱마다 따로 짠다. 그래서 **바깥에서 보이는 모양**은 여기 하나로 맞춘다 —
사용자와 설치 에이전트가 어느 앱에서나 같은 키 · 같은 명령 · 같은 출력을 보게.

기준 구현은 Secretary–1 이다. 새 앱은 거기서 옮겨 오고, 이 문서와 다르게 만들었다면 이 문서부터 고친다.

## 01 설정 키 (`config.json` 의 `llm`)

| 키 | 기본값 | 뜻 |
|---|---|---|
| `base_url` | `""` | OpenAI 호환 주소. 보통 `…/v1` 로 끝난다. `…/chat/completions` 를 붙여 부른다 |
| `api_key` | `""` | 키. 값 대신 `{env:이름}` · `{file:경로}` 참조를 쓸 수 있다 |
| `model` | `""` | 모델 이름 |
| `models` | `[]` | 화면에서 고를 모델 목록 (선택). 서버의 `/v1/models` 와 합쳐 보여 준다 |
| `temperature` | `0.2` | |
| `max_tokens` | `2048` | |
| `timeout_sec` | `90` | 요청 하나의 제한 시간 |
| `extra_headers` | `{}` | 추가 인증 헤더 `{"이름": "값"}`. 값에 참조를 쓸 수 있다 |
| `proxy` | `null` | `null` = 시스템 설정 · `""` = 프록시 안 씀 · `"http://host:port"` = 지정 |
| `ca_file` | `""` | 사내 인증서(PEM) 경로. SSL 오류가 날 때만 |
| `tool_mode` | `"auto"` | *도구 호출을 쓰는 앱만* — `auto` · `native` · `json` |

- 앱은 `config.example.json` 에 `llm` 을 이 키 그대로 싣는다. 검사기가 빠진 키 · 모르는 키를 알려 준다.
- `llm` 밖의 키는 앱마다 자유다.

## 02 참조와 환경 변수

- `{env:이름}` → 환경 변수 값, `{file:경로}` → 파일 내용(앞뒤 공백 제거). OpenCode 설정과 같은 문법이다.
- `<접두어>_BASE_URL` · `<접두어>_API_KEY` · `<접두어>_MODEL` 환경 변수가 있으면 설정 파일보다 먼저 쓴다. 접두어는 [대장](REGISTRY.md)의 환경 변수 칸 (`SECRETARY` · `REPORT` …).

## 03 명령

| 명령 | 하는 일 | 종료 코드 |
|---|---|---|
| `--setup [--provider P] [--model M] [--force]` | OpenCode 설정에서 LLM 값을 가져와 저장하고 점검한다. 이미 있으면 `--force` 때만 다시 | `0` OK · `1` 점검 실패 · `3` 사람이 골라야 함 |
| `--check` | LLM 에 짧은 요청 하나를 보내 본다 (+ 앱의 다른 연결) | `0` · `1` |
| `--set "키=값"` | 설정 한 칸 바꾸기. 값은 JSON 으로 읽히면 JSON. 저장 뒤 검증해서 틀리면 되돌린다 | `0` · `2` |

- `--setup` 이 읽는 곳: `%USERPROFILE%\.config\opencode\opencode.json(c)` · `OPENCODE_CONFIG` · 앱 폴더와 그 위(`D:\OPENCODE`)의 `opencode.json(c)` · 키가 없으면 `~/.local/share/opencode/auth.json`.
- OpenAI 호환 provider(`options.baseURL`)가 여럿이면 코드 3 과 함께 후보를 보여 준다 → `--provider` · `--model` 로 다시.
- 점검 출력의 마지막 줄은 `결과: OK` · `결과: 확인 필요` · `결과: 점검 실패` ([RULES.md › S-03](../RULES.md#규약)).

## 04 비밀 ([RULES.md › W-04](../RULES.md#w-04-비밀은-어디에도-찍지-않는다))

- 키 값은 어떤 출력에도 찍지 않는다. 보여 줄 때는 `설정됨 (n자 · 값은 표시 안 함)` · `{env:이름} 참조 · 값 있음`.
- `--set llm.api_key=<값>` 은 거부한다 (명령 기록에 남는다). 참조(`{env:…}`)만 받는다. 값은 사용자가 설정 파일을 직접 열어 넣는다.
- `extra_headers` 의 값도 키와 같이 다룬다.

## 05 요청

- `POST {base_url}/chat/completions` · `stream: false` · 헤더 `Authorization: Bearer <키>` (키가 있을 때) + `extra_headers`.
- 응답의 `<think>…</think>` 는 버린다.
- 오류 문구는 사람이 고칠 수 있게: `404` → `/v1` 이 필요한지 · `401`/`403` → 키 · 인증 헤더 · 시간 초과 · 연결 실패 → 프록시 · `CERTIFICATE_VERIFY_FAILED` → `ca_file`.
