<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/page/system-dark.jpg">
    <img src="docs/page/system-light.jpg" width="880" alt="works 시스템: Secretary–1, Terminal–1, TOKEN QUEST, Report–1 을 나란히">
  </picture>
</p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/page/title-dark.png">
    <img src="docs/page/title-light.png" width="880" alt="매일 쓰는 사내 도구 — works system — 받아서 바로, 내 PC 에서만.">
  </picture>
</p>

<p align="center">
works 는 매일 쓰는 사내 도구 모음입니다. 같은 팔레트, 같은 번호 라벨, 같은 노브 색으로 만들었습니다.<br>
전부 파이썬 표준 라이브러리만 쓰고, 받아서 바로 실행되고, 내 PC 에서만 돕니다.<br>
하나는 일정을 잡고, 하나는 opencode 를 지켜보고(그 안에서 펫이 자랍니다), 하나는 붙여 넣은 잡동사니를 근거 달린 보고서로 정리합니다.
</p>

<p align="center"><sub>
SECRETARY–1 · 말하면 잡아 주는 일정 비서<br>
TERMINAL–1 · opencode 여러 개를 한 창에서<br>
TQ–1 · 토큰을 먹고 자라는 펫 · TERMINAL–1 안<br>
REPORT–1 · 붙여 넣으면 근거 달린 보고서<br>
저장소 하나 · D:\OPENCODE · 폴더 이름 = 명령 이름<br>
네이비 · 라임 · 회색 · 빨강 없음
</sub></p>

<br>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/page/parts-dark.jpg">
    <img src="docs/page/parts-light.jpg" width="880" alt="works 시스템 부품: Secretary–1 일정 비서 · Terminal–1 opencode 멀티플렉서 · TQ–1 token quest 토큰 펫 · Report–1 근거 달린 보고서">
  </picture>
</p>

<p align="center">
<a href="secretary-1/README.md">Secretary–1 ›</a> &nbsp;·&nbsp;
<a href="terminal-1/README.md">Terminal–1 ›</a> &nbsp;·&nbsp;
<a href="terminal-1/docs/MANUAL.md#06-token-quest">TQ–1 token quest ›</a> &nbsp;·&nbsp;
<a href="report-1/README.md">Report–1 ›</a>
</p>

<br>

<h3 align="center">폴더.</h3>

<table align="center">
<tr><td width="150"><a href="secretary-1/README.md"><code>secretary-1/</code></a></td><td width="550">일정 비서 · <code>secretary-1.py</code> 한 파일 · Windows · Python 3.8+</td></tr>
<tr><td><a href="terminal-1/README.md"><code>terminal-1/</code></a></td><td>opencode 멀티플렉서 + TOKEN QUEST · <code>terminal-1</code> 명령 · Windows Terminal</td></tr>
<tr><td><a href="report-1/README.md"><code>report-1/</code></a></td><td>근거 달린 보고서 · <code>report-1.py</code> 한 파일 · 메일 · 메신저 · 메모 · 표를 붙여 넣기 · Python 3.8+</td></tr>
</table>

<p align="center"><sub>세 폴더는 모양이 같습니다: <code>README.md</code> 소개 · <code>INSTALL.md</code> 에이전트용 설치 절차 · <code>docs/MANUAL.md</code> 매뉴얼 · <code>tests/</code><br>
새 도구는 <a href="RULES.md">RULES.md</a> 부터 · 디자인 <a href="docs/DESIGN.md">DESIGN.md</a> · 대장 <a href="docs/REGISTRY.md">REGISTRY.md</a></sub></p>

<br>

<a name="install"></a>
<h3 align="center">설치.</h3>

<p align="center">저장소를 <code>D:\OPENCODE</code> 에 한 번 받고, 쓰고 싶은 도구의 <code>INSTALL.md</code> 를 opencode 에게 맡기면 됩니다.</p>

```text
works 저장소를 D:\OPENCODE 에 받아줘: git clone https://github.com/leebobegogigug-blip/Works.git "D:\OPENCODE"
(이미 받아져 있으면 git -C "D:\OPENCODE" pull --ff-only)
그다음 D:\OPENCODE\secretary-1\INSTALL.md · D:\OPENCODE\terminal-1\INSTALL.md · D:\OPENCODE\report-1\INSTALL.md 를 차례로 끝까지 읽고 그 순서대로만 진행해 (안 쓸 도구는 빼고).
API 키·토큰은 절대 출력하지 말고, [질문] 표시가 있는 곳에서는 나한테 물어봐.
```

<br>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/page/certified-dark.png">
    <img src="docs/page/certified-light.png" width="880" alt="works system — 둘 다 켜 두면, 월요일이 짧아집니다.">
  </picture>
</p>

<br>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/page/colophon-dark.png">
    <img src="docs/page/colophon-light.png" width="880" alt="works — 매일 쓰는 사내 도구를 만드는 작은 작업실. D:\OPENCODE\ · 127.0.0.1 · 내 PC">
  </picture>
</p>

<p align="center"><sub>
works · 도구는 셋, 폴더도 셋, <a href="RULES.md">규칙은 하나</a>.<br>
화면 문법은 소형 하드웨어 계측기(Teenage Engineering 류)에서 영감을 받았고, 해당 회사와는 관련이 없습니다.
</sub></p>
