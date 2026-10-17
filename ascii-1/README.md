# Ascii–1

PNG 를 끌어다 놓으면 ASCII 아트로 바꿔 주는 도구입니다. 사진이 아니라 **바탕 · 선 · 점이 또렷한 그림** — 관리도 같은 선 차트와 웨이퍼 파티클 맵 — 을 위한 것입니다.

> **지금은 개발 중입니다.** PNG 를 읽는 부분(`ascii1_png.py`)만 있고, ASCII 로 바꾸는 기능은 아직 없습니다. 설계는 저장소의 `docs/plans/ascii-1-design.md` 에 있습니다.

<table>
<tr><td width="140">실행</td><td width="560">Windows 10 / 11 · Python 3.8+ (소스로 실행)</td></tr>
<tr><td>의존성</td><td>없음 — 표준 라이브러리만</td></tr>
<tr><td>저장</td><td>없음 — 결과 <code>.txt</code> 는 입력 PNG 옆에 만들고, 원본은 건드리지 않습니다</td></tr>
<tr><td>네트워크</td><td>쓰지 않습니다</td></tr>
<tr><td>테스트</td><td>unittest · CI Windows + Ubuntu</td></tr>
</table>

## 문서

- [설치 가이드](INSTALL.md) — OpenCode 에이전트용 단계별 절차 · 문제 해결
- [매뉴얼](docs/MANUAL.md) — 지원하는 PNG · 개발
- [디자인](../docs/DESIGN.md) — works 공통 원칙
- [works](../README.md) — explore ›

<sub>
Ascii–1 · 점이 열 개면 글자도 열 개. 그 이상은 추정입니다.<br>
화면 문법은 소형 하드웨어 계측기(Teenage Engineering 류)에서 영감을 받았고, 해당 회사와는 관련이 없습니다.
</sub>
