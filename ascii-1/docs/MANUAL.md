# Ascii–1 매뉴얼

PNG 를 ASCII 아트로 바꾸는 명령형 도구입니다. 소개는 [README](../README.md), 설치 절차는 [INSTALL.md](../INSTALL.md)에 있습니다.

- **개발 중** — 지금 되는 것은 `version` · `help` 와 PNG 읽기 모듈뿐입니다. 변환 명령은 아직 없습니다
- **내 PC 전용** — 네트워크를 쓰지 않고, 파일은 사용자가 지정한 PNG 만 읽습니다

## 명령

| 명령 | 하는 일 |
|---|---|
| `python ascii-1.py version` | 버전 |
| `python ascii-1.py help` | 도움말 |

## 읽을 수 있는 PNG

`ascii1_png.py` 가 표준 라이브러리(`zlib` · `struct`)만으로 읽습니다. 결과는 늘 8 비트 RGB 이고, 투명한 곳은 흰 바탕으로 칩니다.

| 항목 | 지원 |
|---|---|
| 색 유형 | 회색 · RGB · 팔레트 · 회색+알파 · RGBA |
| 비트 깊이 | 1 · 2 · 4 · 8 · 16 (16 비트는 위 바이트만) |
| 줄 필터 · 인터레이스 | 0–4 · Adam7 |
| 투명 | 알파 채널 · 팔레트 투명도 · 회색/RGB 투명색 |
| 한도 | 한 변 4000 픽셀 · 파일 64 MB |
| 읽지 않는 것 | JPEG 를 비롯한 PNG 가 아닌 파일 (확장자가 `.png` 여도 안이 JPEG 이면 `JPEG 로 보입니다` 하고 거부) |

깨진 파일 · 잘린 파일 · 압축 폭탄은 `PngError` 한 줄로 끝납니다. 원본은 어떤 경우에도 바꾸지 않습니다.

## 개발

| 할 일 | 명령 |
|---|---|
| 테스트 | `python -m unittest discover -s tests` (표준 라이브러리만 — 시험용 PNG 인코더는 `tests/pngenc.py` 에만 있습니다) |
| works 규칙 검사 | 저장소 루트에서 `python tools/works_check.py` |

CI(`.github/workflows/ascii-1.yml`)는 Windows · Ubuntu × Python 3.8 · 최신에서 테스트를 돌립니다. 테스트 그림은 전부 코드로 만든 것입니다.

## 데이터

저장하는 것이 없습니다. 이 앱이 만드는 파일은 입력 PNG 옆의 결과 `.txt` 뿐입니다 (변환 기능이 생긴 뒤).

## 알려진 한계

- 이 문서의 대부분은 설계 단계입니다. 사양 · 출력 모양은 `docs/plans/ascii-1-design.md` 를 보세요
- 속도: 1000×1000 RGB 를 읽는 데 필터에 따라 0.01–1.4 초 (Linux · Python 3.13 에서 잰 값). Windows · Python 3.8 에서는 더 걸릴 수 있습니다

## 라이선스

내장한 폰트 · 자산이 없습니다.
