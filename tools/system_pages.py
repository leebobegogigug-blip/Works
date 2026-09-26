# -*- coding: utf-8 -*-
"""works 시스템 공용 사진을 앱 사진에서 다시 만든다 — docs/page/system-{dark,light}.jpg · parts-{dark,light}.jpg

  pip install playwright && python -m playwright install chromium     (개발 도구 · 앱 실행에는 필요 없다)
  python tools/system_pages.py

새 앱이 운영에 들어오면 PARTS 에 한 줄 더하고 다시 돌린다. 사진은 각 앱이 문서에 둔 것(hero 등)에서 잘라 쓴다 —
앱 사진을 다시 찍으면 이 사진도 다시 만든다. 글꼴은 이 PC 에 있는 것 중 앞의 것부터 (Windows 면 맑은 고딕).
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "page")

# (화면 이름, 라벨(system), 부품 카드 설명, 사진 경로({theme} = dark · light), 자를 곳 x · y · 너비 · 높이 (원본 픽셀))
PARTS = [
    ("Secretary–1", "SECRETARY–1", "말하면 잡아 주는 일정 비서",
     "secretary-1/docs/page/hero-{theme}.jpg", (540, 120, 680, 1200)),
    ("Terminal–1", "TERMINAL–1", "opencode 여러 개를 한 창에서",
     "terminal-1/docs/images/page/hero-{theme}.jpg", (80, 140, 1600, 840)),
    ("TQ–1 token quest", "TQ–1 · TOKEN QUEST", "토큰을 먹고 자라는 펫 · Terminal–1 안",
     "terminal-1/docs/images/page/pet-{theme}.png", (62, 12, 800, 492)),
    ("Report–1", "REPORT–1", "붙여 넣으면 근거 달린 보고서",
     "report-1/docs/page/hero-{theme}.jpg", (0, 0, 1180, 820)),
]
W = 1760
SANS = '"Pretendard", "Malgun Gothic", "Apple SD Gothic Neo", "Noto Sans KR", "Segoe UI", "Liberation Sans", ' \
       '"WenQuanYi Zen Hei", sans-serif'
THEME = {
    "dark": {"stage": "radial-gradient(ellipse at 50% 30%, #1b2025 0%, #0c0e10 55%, #060708 100%)",
             "card": "radial-gradient(ellipse at 50% 35%, #20262c 0%, #111417 70%)", "label": "#8b9094",
             "name": "#f2f2f3", "sub": "#a5aaae", "rule": "rgba(242,242,243,.2)", "link": "#75a1c7",
             "shadow": "0 18px 40px rgba(0,0,0,.55)"},
    "light": {"stage": "radial-gradient(ellipse at 50% 30%, #fbfbfc 0%, #eceef0 55%, #dfe2e4 100%)",
              "card": "radial-gradient(ellipse at 50% 35%, #f7f8f9 0%, #dcdfe2 70%)", "label": "#5c6166",
              "name": "#0b0b0b", "sub": "#4c5156", "rule": "rgba(0,35,65,.2)", "link": "#1f507a",
              "shadow": "0 18px 40px rgba(0,35,65,.22)"},
}


def img_size(path):
    """PNG · JPEG 크기 (표준 라이브러리만)"""
    import struct
    with open(path, "rb") as f:
        d = f.read(256 * 1024)
    if d[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", d[16:24])
    i = 2
    while i < len(d):
        if d[i] != 0xFF:
            i += 1
            continue
        if d[i + 1] in (0xC0, 0xC1, 0xC2):
            h, w = struct.unpack(">HH", d[i + 5:i + 9])
            return w, h
        i += 2 + struct.unpack(">H", d[i + 2:i + 4])[0]
    raise ValueError(f"크기를 읽지 못했습니다: {path}")


def shot(path, box, w, h, shadow):
    """원본의 box 부분을 w × h 칸에 (CSS 배경으로 잘라 붙이기)"""
    sw, sh = img_size(path)
    x, y, bw, bh = box
    k = w / bw
    url = "file://" + path.replace("\\", "/")
    return (f'<div class="shot" style="width:{w:.0f}px;height:{h:.0f}px;background:url(\'{url}\') '
            f'{-x * k:.1f}px {-y * k:.1f}px / {sw * k:.1f}px {sh * k:.1f}px no-repeat;box-shadow:{shadow}"></div>')


def fit(box, max_w, max_h):
    bw, bh = box[2], box[3]
    k = min(max_w / bw, max_h / bh)
    return bw * k, bh * k


def system_html(theme):
    t = THEME[theme]
    heights = {"Secretary–1": 420, "Terminal–1": 290, "TQ–1 token quest": 180, "Report–1": 290}   # 앱을 더하면 줄인다
    figs = []
    for name, label, _, src, box in PARTS:
        h = heights.get(name, 330)
        w = box[2] * h / box[3]
        figs.append(f'<figure>{shot(os.path.join(ROOT, src.format(theme=theme)), box, w, h, t["shadow"])}'
                    f'<figcaption>{label}</figcaption></figure>')
    return (f"<style>body{{margin:0}}.s{{width:{W}px;height:920px;background:{t['stage']};display:flex;"
            "justify-content:center;align-items:flex-end;gap:40px;box-sizing:border-box;padding:0 20px 96px}"
            "figure{margin:0;display:flex;flex-direction:column;align-items:center}"
            f"figcaption{{margin-top:44px;font:400 22px/28px {SANS};letter-spacing:4px;color:{t['label']};white-space:nowrap}}"
            f".shot{{border-radius:2px}}</style><div class=s id=cap>{''.join(figs)}</div>")


def parts_html(theme):
    t = THEME[theme]
    n = len(PARTS)
    gap = 40
    cw = (W - gap * (n - 1)) / n
    cards = []
    for name, _, sub, src, box in PARTS:
        w, h = fit(box, cw - 90, 300)
        cards.append(f'<div class=c style="width:{cw:.0f}px"><div class=pic>'
                     f'{shot(os.path.join(ROOT, src.format(theme=theme)), box, w, h, t["shadow"])}</div>'
                     f'<div class=row><span class=n>{name}</span><span class=e>explore</span></div>'
                     f'<div class=sub>{sub}</div></div>')
    return (f"<style>body{{margin:0}}.p{{width:{W}px;height:576px;display:flex;gap:{gap}px;background:transparent}}"
            f".c{{display:flex;flex-direction:column}}.pic{{height:420px;margin-top:16px;background:{t['card']};display:grid;"
            f"place-items:center}}.row{{display:flex;justify-content:space-between;align-items:baseline;padding:26px 4px 16px;"
            f"border-bottom:2px solid {t['rule']}}}.n{{font:400 30px/34px {SANS};color:{t['name']};white-space:nowrap}}"
            f".e{{font:400 28px/34px {SANS};color:{t['link']}}}.sub{{font:400 22px/26px {SANS};color:{t['sub']};"
            f"padding:16px 4px 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}</style>"
            f"<div class=p id=cap>{''.join(cards)}</div>")


def main():
    from playwright.sync_api import sync_playwright
    for _, _, _, src, box in PARTS:
        for theme in THEME:
            p = os.path.join(ROOT, src.format(theme=theme))
            sw, sh = img_size(p)
            if box[0] + box[2] > sw or box[1] + box[3] > sh:
                raise SystemExit(f"자를 곳이 사진 밖입니다: {p} ({sw}×{sh}) · {box}")
    bg = {"dark": "#000", "light": "#fff"}
    with sync_playwright() as pw, tempfile.TemporaryDirectory() as tmp:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": W, "height": 920})
        for theme in THEME:
            for kind, make, ext in (("system", system_html, "jpg"), ("parts", parts_html, "jpg")):
                html = os.path.join(tmp, f"{kind}-{theme}.html")
                with open(html, "w", encoding="utf-8") as f:
                    f.write(f"<!doctype html><meta charset=utf-8><body style='background:{bg[theme]}'>" + make(theme))
                page.goto("file://" + html)
                page.wait_for_timeout(300)
                out = os.path.join(OUT, f"{kind}-{theme}.{ext}")
                page.locator("#cap").screenshot(path=out, type="jpeg", quality=85)
                print(f"{out} · {os.path.getsize(out) // 1024} KB")
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
