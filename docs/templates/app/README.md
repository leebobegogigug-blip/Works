<!-- 소개 페이지 (OP–1 식). 말투 · 이미지 규칙은 docs/DESIGN.md › 06 문서와 말투. 이미지는 라이트 · 다크 한 쌍 -->
<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/page/hero-dark.jpg">
    <img src="docs/page/hero-light.jpg" width="880" alt="{{NAME}} 본체 — (화면에 무엇이 보이는지)">
  </picture>
</p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/page/title-dark.png">
    <img src="docs/page/title-light.png" width="880" alt="{{TAGLINE}} — {{NAME}} — (한 줄 약속)">
  </picture>
</p>

<p align="center">
<!-- 3–4줄. 무엇을 해 주는지 → 몇 가지만 꼽으면 → 한 줄 농담 -->
(무엇을 해 주는지 한 줄). 몇 가지만 꼽으면:<br>
(특징) · (특징) · (특징).<br>
전부는 아니고, 이 정도입니다:
</p>

<p align="center"><sub>
<!-- 대문자 사양 줄. 숫자는 CI · 검사기가 확인할 수 있는 것만 (RULES.md › W-11) -->
(기능) · (기능)<br>
파이썬 3.8+ · 표준 라이브러리만<br>
127.0.0.1 전용<br>
설치는 OPENCODE 에게 · INSTALL.MD<br>
테스트 0 · WINDOWS + UBUNTU CI
</sub></p>

<p align="center"><a href="#install">설치하기 ›</a></p>

<br>

<!-- 기능 섹션을 필요한 만큼: 마침표로 끝나는 헤드라인 · 2–3줄 · 이미지 · 대문자 캡션 -->
<h3 align="center">(마침표로 끝나는 헤드라인).</h3>

<p align="center">
(설명 두세 줄)
</p>

<p align="center"><img src="docs/page/(부품).png" width="620" alt="01 (구역) — (설명)"></p>
<p align="center"><sub>01 (구역) · (요소) · (요소)</sub></p>

<br>

<h3 align="center">works 시스템.</h3>

<p align="center">
{{NAME}} 은 works 시스템의 한 부품입니다.<br>
같은 팔레트, 같은 번호 라벨, 같은 노브 색으로 만든 사내 도구들.<br>
전부 받아서 바로 실행하고, 전부 내 PC 에서만 돕니다.
</p>

<p align="center"><a href="../README.md">explore ›</a></p>

<!-- 공용 이미지는 루트 docs/page/ 것을 쓴다. 복사하지 않는다 (RULES.md › S-07) -->
<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../docs/page/system-dark.jpg">
    <img src="../docs/page/system-light.jpg" width="880" alt="works 시스템">
  </picture>
</p>

<br>

<a name="specs"></a>
<h3 align="center">사양.</h3>

<table align="center">
<tr><td width="140">실행</td><td width="560">Windows 10 / 11 · Python 3.8+</td></tr>
<tr><td>의존성</td><td>없음</td></tr>
<tr><td>저장</td><td><code>%LOCALAPPDATA%\{{APP}}\</code> — 전부 이 PC</td></tr>
<tr><td>네트워크</td><td><code>127.0.0.1</code> 전용 · 밖으로는 (설정한 주소)</td></tr>
<tr><td>테스트</td><td>unittest 0 · CI Windows + Ubuntu</td></tr>
</table>

<br>

<a name="install"></a>
<h3 align="center">설치.</h3>

<p align="center">OpenCode 에 아래를 붙여넣으면 <a href="INSTALL.md">INSTALL.md</a> 순서대로 <code>D:\OPENCODE\{{APP}}</code> 에 설치합니다.</p>

```text
{{NAME}} 을 설치해줘. works 저장소를 D:\OPENCODE 에 받고, 프로그램 폴더는 D:\OPENCODE\{{APP}} 이야.
1. 코드 받기: D:\OPENCODE 가 없거나 비어 있으면 git clone https://github.com/leebobegogigug-blip/Works.git "D:\OPENCODE"
   (이미 works 가 받아져 있으면 받지 말고, git 이 안 되면 Works-repo.zip 을 D:\OPENCODE 에 풀어)
2. 그다음 D:\OPENCODE\{{APP}}\INSTALL.md 를 끝까지 읽고 그 순서대로만 진행해.
   API 키·토큰은 절대 출력하지 말고, [질문] 표시가 있는 곳에서는 나한테 물어봐.
```

<br>

<h3 align="center">설치비 0원 · 의존성 0개<br>반품은 (제거 한 줄)*</h3>

<p align="center"><sub>*자세한 순서는 <a href="INSTALL.md#제거">INSTALL.md › 제거</a></sub></p>

<br>

<table align="center">
<tr><td width="620"><a href="INSTALL.md">설치 가이드</a> <sub>· OpenCode 에이전트용 단계별 절차 · 문제 해결</sub></td><td align="right" width="40">›</td></tr>
<tr><td><a href="docs/MANUAL.md">매뉴얼</a> <sub>· 설정 · 쓰는 법 · 명령 · 화면</sub></td><td align="right">›</td></tr>
<tr><td><a href="../docs/DESIGN.md">디자인</a> <sub>· works 공통 원칙 일곱 가지 · 팔레트</sub></td><td align="right">›</td></tr>
<tr><td><a href="https://github.com/leebobegogigug-blip/Works/issues">문제 알리기</a> <sub>· 이슈</sub></td><td align="right">›</td></tr>
<tr><td><a href="../README.md">works</a> <sub>· 시스템 전체</sub></td><td align="right">›</td></tr>
</table>

<br>

<p align="center"><sub>
{{NAME}} · (한 줄 농담).<br>
화면 문법은 소형 하드웨어 계측기(Teenage Engineering 류)에서 영감을 받았고, 해당 회사와는 관련이 없습니다.
</sub></p>
