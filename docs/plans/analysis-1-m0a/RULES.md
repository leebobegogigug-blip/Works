# Analysis–1 규칙

이 저장소 (`analysis-1`) 의 규칙 **정본**이다. 규칙은 여기에만 적는다.
다른 문서는 이 파일을 링크하고, 내용을 옮겨 적지 않는다 (옮겨 적은 규칙은 반드시 갈라진다).

- 기획 · 설정 값 (포트 · 환경 변수 · 데이터 폴더) → [docs/PLAN.md](docs/PLAN.md) (설정 표는 15 › B)
- 디자인 (데이터 팔레트) → [DESIGN.md](DESIGN.md) · 화면 틀은 works [DESIGN.md](https://github.com/leebobegogigug-blip/Works/blob/447758f4b43ebafe7b3ec89acf7eec458ea2e27e/docs/DESIGN.md)
- works 에서 옮긴 것 · 갈라짐 장부 → [docs/UPSTREAM.md](docs/UPSTREAM.md)
- 에이전트용 요약 → [AGENTS.md](AGENTS.md) (opencode) · [CLAUDE.md](CLAUDE.md) (Claude Code)
- 채택한 works 문서 (works 커밋 `447758f` 에 고정) → [RULES.md](https://github.com/leebobegogigug-blip/Works/blob/447758f4b43ebafe7b3ec89acf7eec458ea2e27e/RULES.md) (헌법 W · 규약 S) · [DESIGN.md](https://github.com/leebobegogigug-blip/Works/blob/447758f4b43ebafe7b3ec89acf7eec458ea2e27e/docs/DESIGN.md) (화면 틀) · [SPEC-llm.md](https://github.com/leebobegogigug-blip/Works/blob/447758f4b43ebafe7b3ec89acf7eec458ea2e27e/docs/SPEC-llm.md) (`llm` 키 · 명령) · [DEVELOP.md](https://github.com/leebobegogigug-blip/Works/blob/447758f4b43ebafe7b3ec89acf7eec458ea2e27e/docs/DEVELOP.md) (작업 방식 D)

## works 와의 관계

- Analysis–1 은 works 의 앱이 아니다. works 밖 별도 저장소에 앱 하나로 산다. works 규칙을 따를 의무는 없지만, 같은 사람이 같은 PC 에서 works 앱과 나란히 쓰는 도구라 works 의 헌법 · 규약 · 디자인 · LLM 규격 · 작업 방식을 스스로 채택한다.
- works 보다 느슨해지는 곳은 셋이다 — 실행 의존성 DuckDB 하나 (AN-02) · 기록은 이 PC 에 (AN-05) · 데이터 색 (AN-09). 주체는 works W-07 보다 넓혀 엄하게 한다 (AN-07). 나머지는 works 그대로이거나, 별도 저장소라는 자리에 맞게 옮겼다 (AN-01 · AN-08).
- works 문서는 옮긴 커밋에 고정한 링크로 부른다. works 가 바뀌어도 여기는 저절로 따라가지 않는다 — 대조는 [docs/UPSTREAM.md](docs/UPSTREAM.md) 가 맡는다.
- 설치 자리 `D:\OPENCODE\analysis-1` 은 works 저장소 폴더 안이지만 works 의 일부가 아니다. works 의 규칙 · 검사기 · 대장은 이 저장소에 적용되지 않는다 ([AGENTS.md](AGENTS.md) › 적용 범위).

## 등급

| 등급 | 뜻 | 어기면 |
|---|---|---|
| **AN** | 이 저장소가 지킨다 — works 헌법 W 와 같은 무게 | 머지하지 않는다. 바꾸려면 이 파일을 고치는 PR 이 먼저 들어간다 |
| **규약 S** (채택한 것) | 따른다 | 따르지 않을 때는 까닭을 `docs/MANUAL.md` 의 `알려진 한계` 나 PR 에 적는다 |

- 예외 대장은 두지 않는다. 앱이 하나라 '이미 있는 앱이 아직 못 지키는 조항' 이 생기지 않는다 — 못 지키면 AN 을 고치는 PR 로 간다 [제안].
- 검사는 works 검사기 대신 `tests/test_rules.py` 와 CI 가 맡는다 (M1-a 부터). 그 전 (M0) 과, 시험이 못 보는 뜻 판단 (`[질문]` 을 알맞은 자리에 썼는지 등) 은 리뷰가 본다.
- 요청이 AN 과 부딪히면 하기 전에 조항 번호를 말하고 기다린다 (D-02).

---

## 규칙

### AN-01 저장소 = 앱
- 저장소 루트가 곧 앱 폴더다. 앱은 하나이고, 저장소 이름이 곧 명령이다 (`analysis-1` › `analysis-1.py`).
- 필수 구성은 works W-01 목록 그대로다: `README.md` · `INSTALL.md` · `docs/MANUAL.md` · `tests/` · `.gitignore` · `.gitattributes` · `.github/workflows/analysis-1.yml`. M1-a 에서 다 갖춘다.
- works 앱과 코드를 공유하지 않는다. 필요하면 사본으로 옮기고 (LLM 클라이언트 · 줄 판정 · 원자적 저장 — docs/PLAN.md › 07 › 모듈의 '옮겨 오는 곳'), 옮겨 온 곳은 주석에 화면 이름 (en dash · S-01) 으로 적고 [docs/UPSTREAM.md](docs/UPSTREAM.md) 에 올린다.
- works 앱의 기능이 필요하면 그 앱의 공개 명령만 쓴다 — v1 에는 없다. 쓰게 되면 명령이 없거나 · 실패하거나 · 모르는 `format` 이면 그 기능만 끄고 계속 돈다.

왜: 한 앱을 고쳐도 다른 앱이 깨지지 않게 — works 를 고쳐도 Analysis–1 이, Analysis–1 을 고쳐도 works 가 깨지지 않는다.
works 와: W-01 취지 채택 — 폴더 대신 저장소. 대가는 사본 갈라짐이다 (docs/UPSTREAM.md).
지키는 곳: 리뷰 · M1-a (뼈대 · 사본 옮기기).

### AN-02 실행 의존성
- 실행에는 Python 표준 라이브러리와 DuckDB 하나를 쓴다. DuckDB 는 필수라고 README 사양 줄과 설정 표 (docs/PLAN.md › 15 › B 의 '없을 때' 칸) 에 밝힌다. 필수 의존성을 '선택 기능' 이라 부르지 않는다.
- DuckDB 는 버전 하나로 고정한다. 버전은 M0 에서 사용자 PC 의 Python 으로 고른다 (docs/PLAN.md › 07 › 엔진). 엔진은 두 벌 쓰지 않는다 (sqlite3 와 함께 쓰지 않는다).
- DuckDB 는 함수 안에서 import 한다. 없으면 `--version` · `--help` · `--check` 만 돌고, `--check` 가 설치 방법과 `결과: 점검 실패` 를 낸다. 저장한 HTML 보고서는 앱 없이 브라우저로 열린다.
- 앱 코드는 Python 3.8 문법이다. 고정 엔진의 휠 범위 (1.2.2 는 3.8–3.13 · 1.4.5 는 3.9–3.14 · 1.5.6 은 3.10–3.14 [실험]) 밖의 Python 에서도 위 세 명령은 돈다. INSTALL 1단계가 고정 엔진의 휠 범위와 64비트를 본다.
- 그 밖의 외부 패키지는 선택 기능으로만 쓴다 (없으면 그 기능만 꺼진다). 개발 도구 (`tests/` · `tools/`) 는 자유지만 실행 경로에서 import 하지 않는다.

왜: 9백만 줄 · 3.0GB 에서 표준 라이브러리는 적재 153.9s · RSS 2.6GB · 그룹 2.86s, DuckDB 는 59.5s · 1.2GB · 0.068s 였다 [실험 — docs/PLAN.md › 15 › D]. 엔진 두 벌은 같은 질문의 숫자가 엔진마다 갈린다 (sqlite 에 분위수 없음).
works 와: W-02 를 바꿈. 대가는 설치의 pip 단계와 휠 약 13MB [실험] 내려받기 — 사내 PC 에서 막힐 수 있고, 없으면 분석이 안 된다.
지키는 곳: CI 엔진 없는 job (세 명령 · `--check` 종료 1) · 엔진 job (`ANALYSIS_REQUIRE_ENGINE=1`) · `tests/test_rules.py` (최소 Python) · 버전은 M0 (KIT-1 · R2b).

### AN-03 내 PC 에서만
- 서버는 `127.0.0.1` 에만 바인딩한다. 포트는 8900–8909 [제안] 의 10개를 차례로 시도한다.
- 실행마다 새 토큰 (화면 meta `analysis-token` · 요청 머리 `X-Analysis-Token`) 을 쓰고, `Host` 헤더를 검사하고, 보안 헤더를 붙인다 (docs/PLAN.md › 07 › 서버 API).
- 밖으로 나가는 통신은 사용자가 설정한 LLM 주소뿐이다. 텔레메트리 · 자동 업데이트 확인 · 외부 CDN · 웹 폰트 금지. LLM 에 무엇을 보내는지는 `llm_share` (docs/PLAN.md › 06) 가 정한다.
- 엔진을 잠근다: 연결마다 확장 자동 설치 · 불러오기 끔 › `allowed_directories` (데이터 폴더) › `enable_external_access=false` › `lock_configuration`. 그러면 `INSTALL` · 범위 밖 읽기 · 범위 밖 `ATTACH` · `COPY TO` 가 막히고, 데이터 폴더 안의 `ATTACH` · `COPY TO` 는 된다 [실험]. SQL 은 식 컴파일러가 낸 것만 돈다.

왜: DuckDB 기본값은 확장을 받으러 밖으로 나가고, 명시적 `INSTALL` 은 자동 설치 끄기로 안 막힌다 [실험].
works 와: W-03 그대로 + 엔진 잠금. 데이터를 사내 LLM 에 보내는 것과 사내 PC 에서 돌리는 것은 사용자가 허가했다 (2026-10-03 · Q2). 이 비공개 저장소의 코드를 사내 PC 에서 돌리는 것도 그 허가에 드는 것으로 본다 [미확인 — 사용자에게 한 번 더 알린다]. 남는 것은 기술 확인이다 (R9 · KIT-1).
지키는 곳: `tests/test_rules.py` (`0.0.0.0` 바인딩 · UI 외부 리소스) · 보안 시험 (Host · 토큰 · 본문 상한) · 엔진 잠금 시험 · M1-b1.

### AN-04 비밀
- 키 · 토큰 · 비밀번호를 화면 · 로그 · 명령줄 인자 · 커밋에 남기지 않는다. 보여 줄 때는 `설정됨 (n자)` 처럼 가린다.
- 설정 파일은 값 대신 `{env:이름}` · `{file:경로}` 참조를 받는다.
- 비밀 값을 명령줄로 받는 옵션을 만들지 않는다. `--set llm.api_key=<값>` 은 거부한다 (works SPEC-llm › 04).
- [보낼 본문 보기] 와 대화 기록 (AN-05) 에서 키 · `extra_headers` 값은 가린다 — 값을 남기지 않는다.

왜: 한 번 찍힌 비밀은 로그 · 기록 · 커밋 history 에서 거둘 수 없다.
works 와: W-04 그대로.
지키는 곳: `tests/test_rules.py` (비밀처럼 보이는 문자열 · 비밀 값을 받는 명령줄 옵션) · 리뷰 · M1-a.

### AN-05 기록은 이 PC 에
- 대화 기록 (`docs\<id>.talk.jsonl`) · 조작 기록 · 판정 카드는 분석 문서 (`docs\<id>.analysis.json`) 와 함께 데이터 폴더에 저장한다.
- 기본은 켬이다. 화면에 '기록 중' 을 보이고, 분석 문서마다 끄기 · 지우기 한 번 · 보낸 본문 보기를 준다.
- 데이터 사본 (`cache\`) 은 가져오기 화면에서 크기 · 위치를 보이고 끌 수 있다.
- 끄기 · 지우기의 범위 · 보낸 본문을 그대로 남길지 · 덧붙이기 쓰기는 docs/PLAN.md › 03 › 남은 해석 문제의 기본값 [제안] 에서 시작해 M1-b1 · M1-b2 에서 정한다.

왜: 대화 · 의견을 종합한 그림 있는 보고서 (요구 5) 는 결론까지 나눈 대화 기록이 있어야 엮을 수 있다.
works 와: W-05 를 바꿈 — 원문은 메모리에만 › 이 PC 에 남김. W-05 의 '무엇이 저장되는지 화면에 미리 보인다' 는 그대로다 ('기록 중' 표시).
지키는 곳: 기록 시험 · 리뷰 · M1-b1 (조작 기록 · 판정 카드) · M1-b2 (대화 기록).

### AN-06 저장은 깨지지 않게
- 저장 파일에는 형식 버전을 적는다. 쓰기는 `.tmp` 에 쓴 뒤 바꿔치기한다. 깨져 있으면 `.broken` 으로 두고 새로 시작한다. 더 새 형식이면 덮어쓰지 않고 읽기 전용으로 연다.
- 사용자 데이터는 `%LOCALAPPDATA%\analysis-1\` (Windows 밖에서는 `~/.local/share/analysis-1/`) 에 둔다. 설치 폴더 `D:\OPENCODE\analysis-1` 안에 두지 않는다.
- 엔진이 직접 쓰는 사본에는 `.tmp` 바꿔치기를 그대로 못 쓰고, 같은 파일을 읽기 쓰기와 읽기 전용으로 함께 못 연다 [실험]. 그래서 사본 수명 주기를 따른다 (docs/PLAN.md › 07): 가져오기 연결이 다 쓰고 닫은 뒤 분석 연결이 READ_ONLY 로 연다 · 실체화는 세션 작업 파일 · 다시 만들기는 새 파일 › 바꿔치기 재시도 › 새 연결 · 단일 실행 잠금 (`analysis-1.lock`) · 파일 이름에 엔진 버전 · 깨지면 `.broken` 으로 두고 원본에서 다시.

왜: `git pull` · `git clean` · 폴더 교체가 사용자 데이터를 건드리지 않게. 설치 폴더가 works 폴더 (`D:\OPENCODE`) 안이라 거기서 돌린 `git clean` 도 데이터 폴더에는 닿지 않는다.
works 와: W-06 그대로.
지키는 곳: Windows 시험 · 형식 시험 (`ANALYSIS_HOME` 임시 폴더로) · M1-b1.

### AN-07 주체는 사용자
- 모든 조작은 손으로 된다. 손 UI 가 없는 조작은 LLM 도구로도 열지 않는다 — 도구마다 손 조작 짝 `action_id` 를 둔다 (E-1).
- LLM (조수) 은 화면 · 데이터를 직접 바꾸지 않고 제안만 한다. 보기 조작 (등급 1) · 데이터 조작 (등급 2) 모두 제안 카드다 (점선 미리보기 › Enter 적용 · Esc 버림). 적용은 사용자가 누를 때만이고, 적용 전에는 작업 영역의 실제 상태가 바뀌지 않는다 (E-2 · E-4).
- 앱 밖 상태 (파일 쓰기 등 · 등급 3) 는 사용자 단추로만 연다. 미리보기 › 확정 · 되돌릴 수 있으면 되돌리기를 준다.
- 결론 확정 · 발견 카드 · 보고서 저장은 사용자만 한다 (E-7). 조수를 꺼도 모든 기능이 된다 (E-6 · M1-b1).
- 화면 원칙 E-1–E-7 은 docs/PLAN.md › 04 › 주체에 있다.

왜: 2026-10-03 사용자 요구 — '모든 작업을 손으로 할 수 있되 LLM 의 도움을 받을 수 있게 · 주체를 확실히'.
works 와: W-07 을 넓혀 채택 — works 는 '앱 밖의 상태' 만 제안 › 확정이고, 여기서는 LLM 이 하는 바꾸기 전부 (앱 안 상태까지) 가 제안이다. 대가: LLM 도구가 손 UI 진도에 묶인다.
지키는 곳: 손 조작 짝 시험 (짝 없는 도구가 있으면 실패) · 제안 시험 (적용 전 작업 영역 불변) · M1-b1 (손 조작) · M1-b2 (도구).

### AN-08 설치는 에이전트가, 되돌릴 수 있게
- `INSTALL.md` 는 opencode 가 그대로 따라 하는 절차다. 필수 절: 규칙 · 단계마다 확인과 실패했을 때 할 일 · `[질문]` 표시 · 보고 형식 · 문제 해결 · 업데이트 · 제거.
- 관리자 권한 금지. 사용자 범위 변경은 `[질문]` 으로 동의를 받고, 백업하고, 제거 절에 되돌리는 방법이 있을 때만 한다.
- 설치 자리는 `D:\OPENCODE\analysis-1` 이다 (Q10). 저장소 · 명령 · 폴더 이름은 소문자 `analysis-1` 로 적는다 (S-01 — Windows 는 대소문자를 가리지 않아 `Analysis-1` 과 같은 폴더다).
- 받기 (가) git — `git clone https://github.com/leebobegogigug-blip/analysis-1.git "D:\OPENCODE\analysis-1"`. 저장소가 비공개라 Git Credential Manager 의 브라우저 로그인을 `[질문]` 으로 쓰고, 토큰을 주소 · 명령줄 · `.git\config` 에 넣지 않는다 (AN-04).
- 받기 (나) zip — 로그인한 브라우저의 Download ZIP 을 `D:\OPENCODE\analysis-1` 에 풀어 달라고 `[질문]`. 기본은 git 길이다. zip 사본은 `.git` 이 없어 `D:\OPENCODE` 에서 돌린 `git clean -xfd` 가 지운다 (`.git` 이 있는 사본은 `-xfd` 로는 남고 `-xffd` 면 지워진다) [실험 · git 2.43]. INSTALL 의 zip 길에 이 위험을 적는다.
- 엔진: `python -m pip install --no-cache-dir --only-binary=:all: "duckdb==<고정>" --target "%LOCALAPPDATA%\analysis-1\lib\duckdb-<고정>"`. 사내 미러는 `[질문]` 으로 사용자가 이미 가진 pip 설정을 쓰고 주소를 문서에 적지 않는다. 휠은 저장소에 넣지 않는다 — 엔진은 다시 받을 수 있는 캐시라 설치 자리와 나눈다.
- 업데이트: (가) `git -C "D:\OPENCODE\analysis-1" pull --ff-only` · (나) 새 zip 을 새 폴더에 풀고 폴더째 바꾼다 (데이터 폴더는 따로라 그대로). 어느 쪽이든 `--check` 가 '엔진 버전 다름' 이면 엔진 설치 단계를 다시 하고, 옛 `lib\duckdb-*` · 옛 버전 사본 지우기는 `[질문]`.
- 사내에서 고쳐 쓰면 works Flow–1 AGENTS › 04 의 `inhouse` 가지 · `merge origin/main` 순서를 따르되, git 은 `-C "D:\OPENCODE\analysis-1"` 로 부른다. zip 으로 받았으면 고치기 전에 git 으로 다시 받을지 `[질문]`. `inhouse` 가지는 원격에 push 하지 않는다 — Flow–1 AGENTS › 04 의 4 와 같고, 비공개 저장소여도 그렇다 (사내 고침이 GitHub 에 남지 않게 · 저장소가 나중에 공개로 바뀌어도 새지 않게). 그 대신 git 길로 받아 `.git` 을 두고, `D:\OPENCODE` 에서 `git clean -ff` 를 쓰지 않는다 (docs/PLAN.md › 리스크 37).
- 제거: `--stop` › 데이터 폴더 (분석 문서 · 기록 · 사본) 백업 · 지우기 `[질문]` › 설치 폴더 `D:\OPENCODE\analysis-1` 지우기 `[질문]` › GitHub 자격 증명 지우기 `[질문]` (다른 저장소에도 쓰면 남긴다). works 저장소의 일부가 아니라 폴더째 지울 수 있다. works `.gitignore` 의 `/analysis-1/` 줄은 남아도 무해하다. 보내기 메뉴 (P1) 는 `[질문]` + 제거 절.

왜: works 와 같은 자리라 SPEC-llm `--setup` 이 앱 폴더와 그 위 (`D:\OPENCODE`) 의 opencode 설정을 그대로 찾는다 · 사용자가 고른 자리다 (2026-10-03 · Q10).
works 와: W-08 채택 — 설치 자리도 works 꼴 (`D:\OPENCODE\<name>-<n>`) 이다. 다만 별도 저장소라 받기 · 업데이트 · 제거를 이 저장소 INSTALL 이 따로 하고, works 쪽에 `.gitignore` 의 `/analysis-1/` 한 줄과 검사기 고침 (git 이 무시하는 루트 폴더를 앱으로 세지 않게) 이 따른다 — works 작업 가지의 PR 로 따로 낸다.
지키는 곳: `tests/test_rules.py` (INSTALL 필수 절 제목) · 리뷰 · 사용자 PC 설치 · M0 (KIT-1 — R2 · R9) · M1-a (INSTALL 1단계 · 업데이트 · 제거 절).

### AN-09 디자인
- 화면 틀 (구역 · 버튼 · 글자 · 노브 · 축 · 칩) 은 works DESIGN.md 그대로다 — 네이비 · 라임 · 회색 · 화면 틀에 빨강 없음 · Unifont · 원칙 일곱.
- 차트의 데이터 표지만 별도 데이터 팔레트를 쓴다: 범주 12색까지 · 색각 이상 고려 · 연속 · 발산은 명도가 한쪽으로만 변하는 팔레트 · 규격 밖 · 불량은 고정 경고색 + 엑스 모양. 경고색은 반도체 관례대로 빨강 계열도 된다 — 데이터 표지에서만.
- 선택 · 마킹은 여전히 lime 이다 (노브 ② · 원칙 2 '색 = 조작'). 고정 경고색은 범주 · 연속 단계에 넣지 않는다.
- 직접 이름표 · 스포트라이트 (사용자가 켬) · trellis 는 색과 함께 쓰는 보조 수단으로 남는다.
- 색은 계산하지 않는다 — 단계를 토큰으로 미리 두고 서버 그리기가 그 표만 쓴다 (JS 에서 계산한 색 · `hsl()` 은 색 검사가 못 본다 [실험]).
- 데이터 팔레트의 값과 검사는 [DESIGN.md](DESIGN.md) 에서 정한다 — 연속 · 범주 · 고정 경고색은 M1-b1 앞, 발산은 처음 쓰는 판 앞.

왜: 장비별 범주 색을 쓰면 '유채색은 네이비 · 라임 두 계열만' 이 깨진다 — 범주 팔레트 · viridis · 네이비와 라임 사이 보간은 works 검사기에 걸린다 [실험]. 고정 경고색을 단계에서 빼는 것은 '가장 높은 die' 와 '불량 die' 가 같은 색이 되지 않게다.
works 와: W-10 을 데이터 색만 바꿈. 별도 저장소라 works 규칙 PR 없이 정한다 (Q7).
지키는 곳: `tests/test_rules.py` (화면 틀 색이 works 팔레트 밖인지) · 색 시험 (데이터 팔레트 · 토큰 표가 `ui.html` 과 같은지 · `hsl(` · 색 보간 코드 막기) · M1-b1.

### AN-10 약속은 CI 가
- 워크플로는 하나다 (`.github/workflows/analysis-1.yml`). Windows + Ubuntu × (최소 Python · 최신 Python). 시험은 표준 라이브러리 `unittest`. 사내 LLM 은 가짜 LLM 서버로 흉내 낸다.
- README 의 숫자와 사양 (최소 Python · 테스트 수) 은 CI 가 확인하는 것만 적는다. 성능 숫자는 README 에 쓰지 않고 MANUAL › 알려진 한계에 측정 환경과 함께 적는다.
- 엔진 job 만 고정 버전을 pip 로 받는다. 엔진 import 는 `setUpClass` 안에 둔다 — 엔진 없는 job 에서도 시험 불러오기 (README 테스트 수 세기) 가 깨지지 않게.
- 엔진 없는 job 은 `--check` 의 `결과: 점검 실패` 를 기대한다. 엔진 job 은 `ANALYSIS_REQUIRE_ENGINE=1` 로 엔진 시험 건너뛰기를 실패로 바꾼다.
- 비공개 저장소라 Actions 무료 시간에 한도가 있다 [미확인 — 요금제마다 다르다]. job 짝은 그대로 두고 무거운 job (엔진 · e2e) 은 PR 과 `main` 에서만 돌린다 [제안]. M0 의 워크플로는 손으로만 도는 빈 판이다.

왜: 혼자 유지하는 저장소에서 약속을 지키는 것은 CI 다. 엔진 job 의 건너뛰기를 실패로 바꾸는 것은 pip 단계가 조용히 실패해 엔진 시험이 모두 건너뛴 채 초록이 되는 일을 막으려고다 (D-07).
works 와: W-11 그대로 + 엔진 job.
지키는 곳: CI (docs/PLAN.md › 13) · M1-a (두 job · 가짜 LLM).

### AN-11 사내 정보 금지
- 저장소 가시성과 무관하다 (지금은 비공개 · Q9).
- 실데이터 · 회사명 · 사내 주소 · 동료 이름 · 내부 시스템 이름 · 사내 모델 응답 원문 · 실데이터나 실제 대화가 찍힌 스크린샷을 커밋하지 않는다. 사내 이름은 설정에 둔다 (D-03).
- 합성 데이터만 쓴다 — 이름 · 값은 지어낸 것 · 회사 특유 약어 대신 일반 용어 (CP · WAT · PCM) · 사내 빈 코드 · 존 정의를 옮기지 않는다.
- Spotfire 골든은 합성 데이터의 값만 커밋한다. Spotfire 는 비교 대상으로 이름만 쓰고 화면 · 문서 문장을 옮기지 않는다.
- README 끝에 영감 고지문을 둔다 (works RULES › W-12 문구 그대로). 글꼴을 넣으면 `fonts/OFL.txt` 를 함께 두고, 글리프를 `analysis1_assets.py` 에 넣으면 그 파일 머리 주석에 Unifont · OFL 을 밝히고 `fonts/OFL.txt` 를 가리킨다. 내보낸 HTML 보고서 끝에 글꼴 고지 한 줄을 둔다.

왜: 가시성은 나중에 바뀔 수 있고, 한 번 커밋한 것은 기록에 남는다.
works 와: W-12 그대로 — 비공개여도 같다.
지키는 곳: `tests/test_rules.py` (비밀처럼 보이는 문자열 · 사설 IP · 영감 고지문 · 글꼴 라이선스 파일) · 리뷰 · 첫 커밋부터.

### works W-09 는 번호를 두지 않는다
- 앱이 하나이고 이름은 정했다 (Q8). 이름을 바꿀 일이 생기면 works W-09 의 방식 (예전 데이터 · 실행기 자동 이전 · 덮어쓰지 않기 · 예전 프로그램이 켜져 있으면 미룸) 을 따른다.

---

## 규약

| 규약 | 이 저장소에서 |
|---|---|
| S-01 이름 | 채택 — 화면 Analysis–1 (en dash) · 저장소 · 명령 · 파일 · 데이터 폴더는 `analysis-1` · 코드 상수 `APP` · `NAME` · `VERSION` |
| S-02 버전 | 채택 — `VERSION = "x.y.z"` 하나 · `--version` · 올리는 법은 D-08 그대로 (고침 셋째 · 새 기능 둘째 자리 · PR 하나에 한 번) |
| S-03 명령과 종료 코드 | 채택 — `--setup` · `--check` · `--status` · `--stop` · `--version` · `--help` · 종료 0 · 1 · 2 · 3 · 점검 출력 마지막 줄 `결과: …`. 엔진이 없으면 `--check` 는 1 — INSTALL 문제 해결이 설치 단계로 보내는 경우라 사람 확인 (3) 이 아니다 |
| S-04 앱 유형 | 한 파일 배포는 해당 없음 — 모듈 10개 안팎 [추정] · Flow–1 선례 · 모듈마다 1,500줄 (docs/PLAN.md › 07 › 모듈). 웹형의 나머지는 채택: `ui.html` › `build.py` › `analysis1_assets.py` · CI 에서 `build.py --check` · 보안 헤더 (AN-03) |
| S-05 Windows 가 본 무대 | 채택 — 경로는 늘 큰따옴표 · cmd · PowerShell · Git Bash 에서 그대로 · PowerShell 5.1 호환 · `.ps1` · `.cmd` · `.bat` 은 CRLF · 콘솔 UTF-8 |
| S-06 대장 먼저 | 해당 없음 — 같은 칸 (이름 · 폴더 · 포트 · 전역 단축키 · 데이터 폴더 · 환경 변수 · 캐릭터) 은 docs/PLAN.md › 15 › B 설정 표가 맡는다 |
| S-07 문서 | 채택 — 뼈대는 works `docs/templates/` 에서 시작한다. 형제 앱 링크 · 공용 이미지 자리는 해당 없음 (형제 앱이 없다) |
| S-08 커밋 | 채택 — `analysis-1: 무엇 · 무엇` |
| S-09 LLM | 채택 — SPEC-llm 의 `llm` 키 그대로 (`tool_mode` 포함) · `--setup` (opencode 설정 공유) · `--check` · `--set` · `stream: false`. 환경 변수는 `ANALYSIS_BASE_URL` · `ANALYSIS_API_KEY` · `ANALYSIS_MODEL`. `llm_share` 와 `--exam` 은 `llm` 밖이라 앱이 정한다 |

---

## 작업 방식

- works [DEVELOP.md](https://github.com/leebobegogigug-blip/Works/blob/447758f4b43ebafe7b3ec89acf7eec458ea2e27e/docs/DEVELOP.md) 의 D-01–D-11 을 채택한다. 순서 · 기준 · 커밋 · 보고 모양 (D-10 · D-11) 은 그대로다.
- 입구도 works DEVELOP › 00 방식이다 — [AGENTS.md](AGENTS.md) 가 입구이고, 도구별 파일 ([CLAUDE.md](CLAUDE.md)) 은 `@AGENTS.md` 한 줄이다.
- 읽을 때 아래 표대로 바꿔 읽는다.

| works DEVELOP 에서 | 이 저장소에서 |
|---|---|
| 헌법 W · works RULES.md | AN · 이 파일 |
| `python tools/works_check.py` (D-08 · D-09) | `tests/test_rules.py` 와 CI — M1-a 전에는 없어 리뷰가 본다 |
| 대장 (REGISTRY.md) — 이름 · 포트 · 환경 변수 · 데이터 폴더 · PC 에 남기는 것 | docs/PLAN.md › 15 › B 설정 표 (M1-a 부터 README · MANUAL 이 정본) |
| 예외 대장 (D-02 의 셋째 길 · D-08) | 없음 — AN 을 고치는 PR 로 간다 |
| 00 순위 표의 2 (고칠 앱의 AGENTS.md · GUIDE · UI) | 이 저장소의 AGENTS.md · `docs/MANUAL.md` (M1-a 부터) |
| 시험용 데이터 폴더 `REPORT_HOME` · `FLOW_HOME` (D-07) | `ANALYSIS_HOME` |
| works 문서의 상대 링크 | works 커밋 `447758f` 에 고정한 링크 ([docs/UPSTREAM.md](docs/UPSTREAM.md)) |

---

## 규칙 바꾸기

- AN 을 바꾸는 PR 은 그 조항만 바꾼다. [AGENTS.md](AGENTS.md) 요약 · `tests/test_rules.py` 를 같은 PR 에서 맞춘다.
- 새 조항은 실제로 일어난 문제나 되풀이된 패턴이 근거일 때만 넣는다 (works RULES › 규칙 바꾸기 채택).
- works 의 W · S · D 가 바뀌어 따라갈 때도 이 파일을 고치는 PR 로 한다. [docs/UPSTREAM.md](docs/UPSTREAM.md) 의 SHA 칸을 같은 PR 에서 고친다.
- 고친 기록: 처음 만듦 — 기획서 (docs/PLAN.md › 03) 의 채택 표를 옮김 · 설치 자리는 2026-10-03 사용자 답 (Q10) 대로 `D:\OPENCODE\analysis-1`.
