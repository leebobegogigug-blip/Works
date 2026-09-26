<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/page/hero-dark.jpg">
    <img src="docs/page/hero-light.jpg" width="880" alt="Report–1 본체 — 왼쪽 01 근거(커밋 · 일정 · 일지 · 다음 일정), 오른쪽 02 초안(줄마다 근거 칩, 확정 도장), 아래 노브 네 개">
  </picture>
</p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/page/title-dark.png">
    <img src="docs/page/title-light.png" width="880" alt="근거 달린 주간보고 — Report–1 — 한 주를 모아, 근거와 함께.">
  </picture>
</p>

<p align="center">
금요일 오후 다섯 시 반, 이번 주에 뭘 했는지 기억나지 않을 때를 위해 만들었습니다. 몇 가지만 꼽으면:<br>
내 커밋과 일정과 한 줄 일지를 모으고, 사내 LLM 이 주간보고 초안을 쓰고, 줄마다 근거가 붙습니다.<br>
근거 없는 실적은 확정할 수 없습니다. 실적을 부풀리는 노브는 없습니다.<br>
전부는 아니고, 이 정도입니다:
</p>

<p align="center"><sub>
파일 하나 · REPORT-1.PY · 표준 라이브러리만 · 파이썬 3.8+<br>
근거 세 가지 · 내 커밋 · 일정 · 오늘 한 일<br>
내 커밋만 · 작성자 이메일로 거름 · 모르면 가져오지 않음<br>
일정은 SECRETARY–1 공개 명령으로 · 없으면 일정 없이<br>
오늘 한 일 한 줄 · ENTER 로 일지에<br>
초안 세 칸 · 금주 실적 · 차주 계획 · 이슈<br>
줄마다 근거 칩 · 올리면 근거 줄이 켜짐<br>
근거 없는 실적은 ERR · 확정 안 됨<br>
고친 줄은 '직접' · 책임은 사람에게<br>
서버가 다시 판정 · 화면을 믿지 않음<br>
체크한 근거만 사내 LLM 으로<br>
LLM 이 없으면 기본 초안 · 규칙으로 묶기<br>
노브 네 개 · ①기간 ②상세도 ③어조 ④분량 · ALT+1–4<br>
확정 CTRL+S · 도장 · 클립보드로<br>
확정 뒤 20초 되돌리기 · CTRL+Z<br>
지난 보고서 서랍<br>
--DRAFT · 창 없이 글만<br>
127.0.0.1 전용 · 실행마다 새 토큰<br>
창을 닫으면 저절로 꺼짐<br>
결재판 얼굴<br>
다크 · 라이트 · 시스템 테마 · 빨강 없음<br>
설치는 OPENCODE 에게 · INSTALL.MD<br>
단위 · 통합 테스트 32 · 브라우저 E2E · WINDOWS + UBUNTU CI
</sub></p>

<p align="center"><a href="#install">설치하기 ›</a></p>

<br>

<h3 align="center">근거 없는 실적은, 없습니다.</h3>

<p align="center">
초안의 실적 · 이슈 줄에는 근거 id 가 꼭 붙습니다. 커밋은 <code>c</code>, 일정은 <code>e</code>, 일지는 <code>n</code>.<br>
LLM 이 근거 없는 성과를 적으면 그 줄은 <code>ERR</code> — 확정 버튼이 꺼집니다.<br>
사람이 고치면 <code>직접</code> 이 붙고 확정할 수 있습니다. 그 줄의 책임은 사람에게 있으니까요.
</p>

<p align="center"><img src="docs/page/err.png" width="620" alt="02 DRAFT — '성과 30% 향상' 줄에 ERR 근거 없음 칩, 확정 버튼 꺼짐"></p>
<p align="center"><sub>02 DRAFT · 근거 칩 · ERR 근거 없음 · 직접 · 계획</sub></p>

<br>

<h3 align="center">모으는 건 흔적뿐입니다.</h3>

<p align="center">
커밋은 설정한 폴더의 저장소에서 <b>내</b> 이메일로 쓴 것만. 모르면 가져오지 않습니다. 남의 커밋이 내 실적이 되는 것보다 비어 있는 편이 낫습니다.<br>
일정은 <a href="../README.md">Secretary–1</a> 의 공개 명령으로 읽습니다. 메모는 받지 않고 제목 · 시각 · 장소만.<br>
나머지는 <code>오늘 한 일 ›</code> 에 한 줄씩. 매일 한 줄이면 금요일이 짧아집니다.
</p>

<br>

<h3 align="center">노브 네 개, 한 번 더.</h3>

<p align="center">
① 기간(이번 주 · 지난 주 · 2주 · 이번 달) ② 상세도 ③ 어조(개조식 · 서술식) ④ 분량.<br>
노브 색은 works 인코더 색 그대로입니다. 초안 칸 위의 칩도 같은 색 — 색이 곧 조작입니다.<br>
사내 LLM 에는 <b>체크한 근거 줄만</b> 보냅니다. 보내기 전에 화면에 다 보입니다.
</p>

<br>

<h3 align="center">works 시스템.</h3>

<p align="center">
Report–1 은 works 시스템의 한 부품입니다.<br>
같은 팔레트, 같은 번호 라벨, 같은 노브 색으로 만든 사내 도구들.<br>
전부 받아서 바로 실행하고, 전부 내 PC 에서만 돕니다.
</p>

<p align="center"><a href="../README.md">explore ›</a></p>

<br>

<a name="specs"></a>
<h3 align="center">사양.</h3>

<table align="center">
<tr><td width="140">실행</td><td width="560">Windows 10 / 11 · Python 3.8+ · git (커밋을 모을 때)</td></tr>
<tr><td>의존성</td><td>없음 — 표준 라이브러리만</td></tr>
<tr><td>배포</td><td><code>report-1.py</code> 한 파일 · UI 와 폰트 내장</td></tr>
<tr><td>근거</td><td>git 커밋 (내 이메일) · Secretary–1 공개 명령 <code>--export-events</code> · 오늘 한 일 일지</td></tr>
<tr><td>LLM</td><td>OpenAI 호환 <code>/v1/chat/completions</code> · <a href="../docs/SPEC-llm.md">works LLM 규격</a> · 없으면 기본 초안</td></tr>
<tr><td>저장</td><td><code>%LOCALAPPDATA%\report-1\</code> — <code>config.json</code> · <code>journal.json</code> · <code>reports\</code> — 초안은 메모리에만</td></tr>
<tr><td>네트워크</td><td><code>127.0.0.1</code> 전용 · 실행마다 새 토큰 · 밖으로는 설정한 LLM 주소 하나</td></tr>
<tr><td>키</td><td><code>Ctrl+Enter</code> 초안 · <code>Ctrl+S</code> 확정 · <code>Ctrl+Z</code> 되돌리기 · <code>Alt+1–4</code> 노브</td></tr>
<tr><td>글꼴</td><td>GNU Unifont 15.1.01 부분집합 · SIL OFL 1.1 (<a href="fonts/OFL.txt">fonts/OFL.txt</a>)</td></tr>
<tr><td>테스트</td><td>단위 · 통합 32 · 브라우저 E2E · CI Windows + Ubuntu × Python 3.8 · 3.13</td></tr>
</table>

<br>

<a name="install"></a>
<h3 align="center">설치.</h3>

<p align="center">OpenCode 에 아래를 붙여넣으면 <a href="INSTALL.md">INSTALL.md</a> 순서대로 설치합니다. LLM 설정은 OpenCode 설정에서 가져오고, 키는 어디에도 찍히지 않습니다.</p>

```text
Report–1 을 설치해줘. works 저장소를 D:\OPENCODE 에 받고, 프로그램 폴더는 D:\OPENCODE\report-1 이야.
1. 코드 받기: D:\OPENCODE 가 없거나 비어 있으면 git clone https://github.com/leebobegogigug-blip/Works.git "D:\OPENCODE"
   (이미 works 가 받아져 있으면 받지 말고, git 이 안 되면 Works-repo.zip 을 D:\OPENCODE 에 풀어)
2. 그다음 D:\OPENCODE\report-1\INSTALL.md 를 끝까지 읽고 그 순서대로만 진행해.
   API 키·토큰은 절대 출력하지 말고, [질문] 표시가 있는 곳에서는 나한테 물어봐.
```

<br>

<h3 align="center">설치비 0원 · 의존성 0개<br>반품은 한 줄이면 끝*</h3>

<p align="center"><sub>*<code>--shortcut off</code> 로 시작 메뉴 바로가기를 지우면 PC 에 남는 건 <code>%LOCALAPPDATA%\report-1</code> 뿐 — 자세한 순서는 <a href="INSTALL.md#제거">INSTALL.md › 제거</a></sub></p>

<br>

<table align="center">
<tr><td width="620"><a href="INSTALL.md">설치 가이드</a> <sub>· OpenCode 에이전트용 단계별 절차 · 업데이트 · 제거</sub></td><td align="right" width="40">›</td></tr>
<tr><td><a href="docs/MANUAL.md">매뉴얼</a> <sub>· 설정 · 쓰는 법 · 근거 규칙 · 화면</sub></td><td align="right">›</td></tr>
<tr><td><a href="../docs/DESIGN.md">디자인</a> <sub>· works 공통 원칙 일곱 가지 · 팔레트</sub></td><td align="right">›</td></tr>
<tr><td><a href="https://github.com/leebobegogigug-blip/Works/issues">문제 알리기</a> <sub>· 이슈</sub></td><td align="right">›</td></tr>
<tr><td><a href="../README.md">works</a> <sub>· 시스템 전체 · 다른 부품</sub></td><td align="right">›</td></tr>
</table>

<br>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../docs/page/colophon-dark.png">
    <img src="../docs/page/colophon-light.png" width="880" alt="works — 매일 쓰는 사내 도구를 만드는 작은 작업실. D:\OPENCODE\ · 127.0.0.1 · 내 PC">
  </picture>
</p>

<p align="center"><sub>
Report–1 · 주간보고는 써 드립니다. 한 일은 직접 하셔야 합니다.<br>
내장 폰트 GNU Unifont 15.1.01 부분집합 · SIL OFL 1.1 (<a href="fonts/OFL.txt">fonts/OFL.txt</a>)<br>
화면 문법은 소형 하드웨어 계측기(Teenage Engineering 류)에서 영감을 받았고, 해당 회사와는 관련이 없습니다.
</sub></p>
