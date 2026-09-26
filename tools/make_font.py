"""fonts/secretary-1-dos.woff 를 다시 만든다 — 개발용 (실행·배포엔 필요 없음).

  pip install fonttools
  python tools/make_font.py [unifont.otf 경로]    기본값: 데비안/우분투 fonts-unifont 설치 경로
  python build.py                                  secretary-1.py 에 다시 내장

원본  GNU Unifont 15.1.01 — https://unifoundry.com/unifont/
      SIL Open Font License 1.1 / GNU GPL 2+ (폰트 임베딩 예외) 이중 라이선스. Secretary–1 은 OFL 1.1 로 배포 (fonts/OFL.txt)
뽑는 글자  ASCII · 라틴-1 · 그리스/키릴 기본 · 문장부호 · 화살표 · 수학 · 박스/블록 · 도형 · 딩뱃
          · CJK 기호 · 한글 호환 자모 · 한글 11,172자 전부 · 전각.  한자·이모지는 시스템 글꼴로 대체된다.
"""
import os
import sys

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "fonts", "secretary-1-dos.woff")
SRC = "/usr/share/fonts/opentype/unifont/unifont.otf"
RANGES = [
    (0x0020, 0x007E), (0x00A0, 0x00FF),                                      # 라틴
    (0x0370, 0x03FF), (0x0400, 0x045F),                                      # 그리스 · 키릴 기본
    (0x2010, 0x2027), (0x2030, 0x205E), (0x2070, 0x209F), (0x20A0, 0x20BF),  # 문장부호 · 첨자 · 통화(₩)
    (0x2100, 0x218F), (0x2190, 0x21FF), (0x2200, 0x22FF), (0x2300, 0x23FF),  # 문자꼴 · 화살표 · 수학 · 기술 기호
    (0x2460, 0x24FF), (0x2500, 0x259F), (0x25A0, 0x25FF),                    # ① · 박스 · 블록 · 도형
    (0x2600, 0x26FF), (0x2700, 0x27BF), (0x2B00, 0x2BFF),                    # 기호 · 딩뱃(✂) · 기호/화살표
    (0x3000, 0x303F), (0x3131, 0x318E), (0x3200, 0x32FF), (0x3380, 0x33DF),  # CJK 기호 · 호환 자모 · ㈜ · ㎡
    (0xAC00, 0xD7A3),                                                        # 한글 11,172자
    (0xFF01, 0xFF5E), (0xFFE0, 0xFFE6), (0xFFFD, 0xFFFD),                    # 전각 · �
]


def main() -> int:
    src = sys.argv[1] if len(sys.argv) > 1 else SRC
    font = TTFont(src)
    cmap = font.getBestCmap()
    codes = [c for a, b in RANGES for c in range(a, b + 1) if c in cmap]
    opt = subset.Options()
    opt.flavor = "woff"
    opt.layout_features = []           # 조합형 자모 같은 OpenType 기능은 쓰지 않는다
    opt.hinting = False
    opt.name_IDs = ["*"]               # 저작권(0) · 라이선스(13, 14) 표기를 그대로 둔다
    opt.name_legacy = True
    opt.name_languages = ["*"]
    opt.prune_unicode_ranges = False   # Unifont 의 OS/2 비트 123 때문에 재계산하면 실패한다
    sub = subset.Subsetter(opt)
    sub.populate(unicodes=codes)
    sub.subset(font)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    subset.save_font(font, OUT, opt)
    print(f"{font['name'].getDebugName(5)} → {os.path.relpath(OUT, ROOT)}: {len(codes):,}자 · {os.path.getsize(OUT):,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
