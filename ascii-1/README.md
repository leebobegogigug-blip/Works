# Ascii–1

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/images/page/hero-dark.png">
    <img src="docs/images/page/hero-light.png" width="880" alt="Ascii–1 창 — 01 SOURCE · 02 STAT 7세그 · 03 DECK 노브 네 개 · 04 ART 웨이퍼 맵의 글자 아트">
  </picture>
</p>
<p align="center"><sub>01 SOURCE · 02 STAT · 03 DECK · 04 ART · 05 STATUS — 합성 웨이퍼 그림(점 101개)을 연 모습</sub></p>

PNG 를 ASCII 아트로 바꿔 주는 도구입니다. 실행하면 작은 창이 열려 그림을 골라 보고, 저장하거나 복사합니다. 사진이 아니라 **바탕 · 선 · 점이 또렷한 그림** — 관리도 같은 선 차트와 웨이퍼 파티클 맵 — 을 위한 것입니다.

```text
python ascii-1.py                 → 창이 열린다 (그림 열기 · 열 수 · 종류 · 저장 · 복사). ascii-1.exe 는 두 번 누르면 된다
python ascii-1.py 그림.png        → 창 없이 그림 옆에 그림.txt (이미 있으면 덮어쓰지 않고 그림 (2).txt)
```

PNG 를 `ascii-1.py` 나 exe 위로 끌어다 놓으면 창 없이 바로 `.txt` 를 만듭니다. 열 수(`--width 40–300`, 기본 120)가 클수록 촘촘합니다. 선 · 점 · 웨이퍼의 원 외곽을 찾아 글자로 옮기고, 그림 속 글자(`UCL` · 눈금 숫자)는 읽지 않고 비웁니다. 점은 뭉친 곳을 면적으로 센 **추정 개수**입니다. `.exe` 한 파일로도 묶습니다 — 저장소 Releases 의 `ascii-1-v…` 릴리스에 `ascii-1.exe` 와 `.sha256` 이 올라갑니다(창이 있는 exe 는 0.2.0 부터입니다 — 0.1.0 은 창 없이 명령줄만 있습니다). 서명하지 않아 SmartScreen · 사내 백신이 막을 수 있습니다 — [매뉴얼](docs/MANUAL.md) 참고. 방법과 한계는 저장소의 `docs/plans/ascii-1-design.md` 에 있습니다.

<table>
<tr><td width="140">실행</td><td width="560">Windows 10 / 11 · Python 3.8+ (소스로 실행) 또는 <code>ascii-1.exe</code></td></tr>
<tr><td>의존성</td><td>없음 — 표준 라이브러리만</td></tr>
<tr><td>저장</td><td>없음 — 결과 <code>.txt</code>(UTF-8)는 입력 PNG 옆에 만들고, 원본은 건드리지 않습니다</td></tr>
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
