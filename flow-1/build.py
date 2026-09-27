"""ui.html 과 fonts/flow-1-dos.woff 를 flow1_assets.py 로 묶는다 (flow-1.py 가 이 모듈에서 화면 · 폰트를 읽는다).

  python build.py           ui.html · 폰트의 변경을 flow1_assets.py 에 반영
  python build.py --check   반영 안 된 변경이 있으면 실패 (커밋 전 · CI 확인용)

flow1_assets.py 는 생성 파일이다. 직접 고치지 말고 ui.html 을 고친 뒤 이 스크립트를 돌린다.
"""
import base64
import io
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "flow1_assets.py")
HTML = os.path.join(ROOT, "ui.html")
FONT = os.path.join(ROOT, "fonts", "flow-1-dos.woff")


def render() -> str:
    html = io.open(HTML, encoding="utf-8").read()
    if '"""' in html or html.endswith("\\"):
        raise SystemExit('ui.html 에 """ 가 있거나 \\ 로 끝나면 안 됩니다')
    font = base64.encodebytes(io.open(FONT, "rb").read()).decode("ascii")      # 76자마다 줄바꿈
    return ('# -*- coding: utf-8 -*-\n'
            '"""flow1_assets — 생성 파일. 고치지 마세요: ui.html · fonts/flow-1-dos.woff 를 고친 뒤 python build.py\n'
            '(CI 가 python build.py --check 로 반영 여부를 확인한다 · 폰트: GNU Unifont 15.1.01 부분집합 · SIL OFL 1.1 · fonts/OFL.txt)"""\n\n'
            f'INDEX_HTML = r"""{html}"""\n\n'
            f'FONT_WOFF_B64 = """\n{font}"""\n')


def main() -> int:
    out = render()
    old = io.open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else ""
    if out == old:
        print("flow1_assets.py 는 ui.html · fonts/flow-1-dos.woff 와 같습니다")
        return 0
    if "--check" in sys.argv:
        print("ui.html · 폰트의 변경이 flow1_assets.py 에 반영되지 않았습니다 → python build.py")
        return 1
    io.open(OUT, "w", encoding="utf-8", newline="\n").write(out)
    print(f"flow1_assets.py 에 반영 (UI {os.path.getsize(HTML):,} bytes · 폰트 {os.path.getsize(FONT):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
