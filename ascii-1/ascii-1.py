#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ascii-1 - PNG 를 끌어다 놓으면 ASCII 아트로 바꿔 주는 명령형 도구 (표준 라이브러리만 · Python 3.8+)

지금은 뼈대만 있다: version · help. PNG 읽기는 ascii1_png.py, 변환은 아직 없다 (docs/plans/ascii-1-design.md).
종료 코드: 0 OK · 2 사용법 오류 (RULES.md › S-03)
"""
import sys

NAME = "Ascii-1"
APP = "ascii-1"
VERSION = "0.0.1"

HELP = """Ascii–1 — PNG 를 ASCII 아트로 (개발 중: 변환 기능은 아직 없습니다)

  ascii-1.py version     버전
  ascii-1.py help        이 도움말
"""


def main(argv):
    cmd = argv[0] if argv else "help"
    if cmd in ("version", "--version"):
        print("%s %s" % (APP, VERSION))
        return 0
    if cmd in ("help", "--help", "-h"):
        print(HELP)
        return 0
    print("아직 변환 기능이 없습니다 (개발 중). help 를 보세요.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
