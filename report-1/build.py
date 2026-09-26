"""ui.html 과 fonts/report-1-dos.woff 를 report-1.py 에 넣는다 (배포는 report-1.py 한 파일).

  python build.py           변경을 report-1.py 에 반영
  python build.py --check   반영 안 된 변경이 있으면 실패 (커밋 전 · CI 확인용)
"""
import base64
import io
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(ROOT, "report-1.py")
HTML = os.path.join(ROOT, "ui.html")
FONT = os.path.join(ROOT, "fonts", "report-1-dos.woff")
PARTS = (("ui.html", 'INDEX_HTML = r"""'), ("fonts/report-1-dos.woff", 'FONT_WOFF_B64 = """'))


def splice(src: str, mark: str, body: str):
    start = src.index(mark) + len(mark)
    end = src.index('"""', start)
    return src[:start] + body + src[end:], src[start:end] == body


def main() -> int:
    src = io.open(PY, encoding="utf-8").read()
    html = io.open(HTML, encoding="utf-8").read()
    if '"""' in html or html.endswith("\\"):
        print('ui.html 에 """ 가 있거나 \\ 로 끝나면 안 됩니다')
        return 2
    font = "\n" + base64.encodebytes(io.open(FONT, "rb").read()).decode("ascii")  # 76자마다 줄바꿈
    out, stale = src, []
    for (name, mark), body in zip(PARTS, (html, font)):
        out, same = splice(out, mark, body)
        if not same:
            stale.append(name)
    if not stale:
        print("report-1.py 는 ui.html · fonts/report-1-dos.woff 와 같습니다")
        return 0
    if "--check" in sys.argv:
        print(f"{' · '.join(stale)} 변경이 report-1.py 에 반영되지 않았습니다 → python build.py")
        return 1
    io.open(PY, "w", encoding="utf-8", newline="\n").write(out)
    print(f"report-1.py 에 반영: {' · '.join(stale)} (UI {len(html):,}자 · 폰트 {os.path.getsize(FONT):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
