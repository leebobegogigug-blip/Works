# -*- coding: utf-8 -*-
"""브라우저 E2E: 가짜 LLM + Report–1 실제 프로세스 + Chromium.

  pip install playwright && python -m playwright install chromium
  python tests/e2e_ui.py            흐름 확인 + 스크린샷 (SHOT_DIR, 기본 shots/)
  python tests/e2e_ui.py --pages    문서 사진도 다시 찍는다 (docs/page/hero-*.jpg · title-*.png · err.png)
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from fake_llm_server import FakeLLM  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

OUT = os.environ.get("SHOT_DIR", os.path.join(ROOT, "shots"))
PAGES = os.path.join(ROOT, "docs", "page")
LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))
W, H = 1180, 820

# 지어낸 예시 자료 (사내 정보 아님 · RULES.md › W-12)
MAIL = """보낸 사람: 김대리 <kim@example.com>
받는 사람: 운영팀
제목: 결제 서버 응답 지연 보고

안녕하세요. 공유드립니다.

9월 12일 14:05부터 14:47까지 결제 서버 응답이 느려졌습니다. 영향 받은 주문은 1,240건입니다.
원인은 DB 연결 풀 고갈로 보입니다. 연결 풀 크기를 40에서 80으로 늘린 뒤 정상화됐습니다.

> 지난 메일 인용
"""
CHAT = ("[김대리] [오후 2:10] 결제 느린 거 저만 그런가요\n[박과장] [오후 2:11] 저도요 DB 쪽 확인 중\n"
        "[김대리] [오후 2:15] 풀 크기 늘렸습니다\n[박과장] [오후 2:47] 정상화 확인, 재발 방지책은 내일 회의에서\n")
TABLE = "시각\t응답 시간(ms)\t실패 주문\n14:00\t180\t0\n14:20\t2,400\t610\n14:40\t1,900\t630\n15:00\t190\t0\n"
MEMO = "내일 10시 재발 방지 회의 · 모니터링 알림 기준 다시 정할 것"


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def start_app(tmp, llm, theme="dark"):
    run = tempfile.mkdtemp(prefix=theme + "-", dir=tmp)   # 켤 때마다 새 데이터 폴더
    home = os.path.join(run, "home")
    os.makedirs(home)
    with open(os.path.join(home, "config.json"), "w", encoding="utf-8") as f:
        json.dump({"llm": {"base_url": llm.url, "model": "fake-model"}, "theme": theme, "idle_exit_min": 0}, f)
    port = free_port()
    env = dict(os.environ, REPORT_HOME=home, PYTHONUNBUFFERED="1")
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "report-1.py"), "--no-window", "--port", str(port)],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    url = f"http://127.0.0.1:{port}/"
    for _ in range(80):
        try:
            with LOCAL.open(url + "api/ping", timeout=1) as r:
                if json.loads(r.read())["app"] == "report-1":
                    return proc, url, home
        except Exception:
            time.sleep(0.25)
    proc.kill()
    raise SystemExit("Report–1 이 켜지지 않았습니다:\n" + proc.stderr.read().decode("utf-8", "replace"))


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  √ {msg}")


def paste(page, text, target="body"):
    """Ctrl+V 흉내 — 붙여 넣기 이벤트를 그대로 보낸다 (헤드리스 브라우저는 시스템 클립보드가 없다)"""
    page.evaluate("""([sel, text]) => { const dt = new DataTransfer(); dt.setData('text/plain', text);
        document.querySelector(sel).dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true})); }""",
                  [target, text])


def disk_has(folder, needle):
    for dp, _, fs in os.walk(folder):
        for f in fs:
            with open(os.path.join(dp, f), "rb") as fh:
                if needle.encode("utf-8") in fh.read():
                    return True
    return False


def fill(page):
    page.fill("#topic", "9월 결제 서버 응답 지연")
    page.press("#topic", "Enter")
    paste(page, MAIL)
    page.wait_for_selector(".card >> nth=0")
    paste(page, CHAT, "#drop")
    page.wait_for_selector(".card >> nth=1")
    paste(page, TABLE)
    page.wait_for_selector(".card >> nth=2")
    page.fill("#drop", MEMO)
    page.press("#drop", "Control+Enter")
    page.wait_for_selector(".card >> nth=3")


def flow(page, llm, home, shots):
    page.wait_for_selector("#pastes .hello")
    fill(page)
    check(page.locator(".card").count() == 4, "붙여 넣기 → 자료 넷 (화면 어디서든 · 붙여 넣는 칸 · 메모 Ctrl+Enter)")
    kinds = page.locator(".card .chip.navy").all_inner_texts()
    check([k.split(" · ")[1] for k in kinds] == ["메일", "대화", "표", "메모"], f"자료 종류를 알아본다 {kinds}")
    check("메일 인용 1줄" in page.inner_text(".card >> nth=0"), "메일 인용(>) 줄은 건너뛴다")
    paste(page, MAIL)
    page.wait_for_selector(".toast:has-text('이미 붙여 넣은 조각뿐')")
    check(page.locator(".card").count() == 4, "같은 메일을 또 붙이면 새 자료를 만들지 않는다")
    check("err" in page.get_attribute("#led-save", "class"), "보관 LED: 보관 안 한 자료 있음")
    check(not os.path.isdir(os.path.join(home, "topics")) and not disk_has(home, "DB 연결 풀"),
          "보관 전에는 원문이 디스크에 없다 (W-05)")
    check("/ 20,000자" in page.inner_text("#meter-t"), "자료 계기판")
    shots("1-sources")

    llm.mode = "good"
    page.click("#draft")
    page.wait_for_selector(".ln .ref")
    check(page.locator(".sec-h").first.inner_text() == "□ 요약", "초안: 맨 위는 요약")
    for chip in ("추론", "확인", "빈칸"):
        check(page.locator(f".ln .chip:has-text('{chip}')").count() >= 1, f"'{chip}' 줄")
    check(page.locator(".ln.err").count() == 0 and not page.is_disabled("#ok"), "근거 없는 줄 없음 · 확정 가능")
    ref = page.locator(".ln .ref").first
    rid = ref.inner_text()
    ref.hover()
    check(page.locator(f".fr.hl[data-id='{rid}']").count() == 1, "근거 칩에 올리면 조각이 켜진다")
    shots("2-draft")

    page.click("#ok")
    page.wait_for_selector(".seal")
    clip = page.evaluate("navigator.clipboard.readText()")
    check(clip.startswith("9월 결제 서버 응답 지연\n\n□ 요약\n  ○ "), "확정 → 보고서 글이 클립보드로")
    page.click("#undo")
    page.wait_for_selector(".seal", state="detached")
    check(page.locator(".toast:has-text('되돌렸습니다')").count() == 1, "20초 안에 되돌리기")

    first = page.locator(".card >> nth=0").locator(".fr").first
    fid = first.get_attribute("data-id")
    llm.requests.clear()
    first.locator("input").uncheck()
    page.wait_for_selector(f".fr.off[data-id='{fid}']")
    page.wait_for_timeout(300)
    check(fid not in page.locator(".ln .ref").all_inner_texts(), "체크를 푼 조각은 근거에서 빠진다")
    page.click("#draft")
    page.wait_for_selector(".ln .ref")
    sent = json.dumps(llm.requests, ensure_ascii=False)
    check(f"[{fid}]" not in sent and "[p2]" in sent, "체크를 푼 조각은 사내 LLM 에 보내지 않는다")
    first.locator("input").check()
    page.wait_for_selector(f".fr:not(.off)[data-id='{fid}']")

    llm.mode = "lie"
    page.click("#draft")
    page.wait_for_selector(".chip.err:has-text('ERR 근거 없음')")
    check(page.is_disabled("#ok"), "지어낸 사실(ERR)이 있으면 확정 못 함")
    shots("3-err")
    bad = page.locator(".ln.err .txt").first
    bad.click()
    page.keyboard.press("End")
    page.keyboard.type(" (다음 주 측정 예정)")
    page.keyboard.press("Enter")
    page.wait_for_selector(".ln .chip.navy:has-text('직접')")
    page.wait_for_timeout(300)
    check(not page.is_disabled("#ok"), "사람이 고치면 '직접' — 책임을 지고 확정할 수 있다")

    llm.mode = "number"
    page.click("#draft")
    page.wait_for_selector(".chip.warn:has-text('숫자?')")
    check(page.locator(".ln .txt .n").all_inner_texts() == ["97"], "근거 조각에 없는 숫자에 물결 밑줄")
    llm.mode = "good"

    page.keyboard.press("Control+s")
    page.wait_for_selector(".toast:has-text('보관했습니다')")
    check("ok" in page.get_attribute("#led-save", "class"), "Ctrl+S 보관 → LED 라임")
    check(disk_has(os.path.join(home, "topics"), "DB 연결 풀"), "보관한 뒤에만 원문이 topics 에")

    page.click("#shelf")
    page.wait_for_selector(".drawer .row")
    check(page.locator(".drawer .row").count() == 1 and "9월 결제 서버" in page.inner_text(".drawer"), "보관함에 토픽")
    page.keyboard.press("Escape")

    paste(page, "새로 붙인 자료 하나 — 보관 안 함")
    page.wait_for_selector(".card >> nth=4")
    page.once("dialog", lambda d: d.accept())
    page.click("#new")
    page.wait_for_selector("#pastes .hello")
    check(page.input_value("#topic") == "", "새 토픽: 보관 안 한 자료가 있으면 묻고 비운다")
    page.click("#shelf")
    page.click(".drawer .row >> text=열기")
    page.wait_for_selector(".card >> nth=3")
    check(page.locator(".card").count() == 4 and page.input_value("#topic") == "9월 결제 서버 응답 지연",
          "보관함에서 다시 열기 (보관한 때의 자료)")

    before = page.inner_text("#lcd-form")
    page.click(".knob.k1")
    page.wait_for_timeout(300)
    check(page.inner_text("#lcd-form") != before and page.inner_text("#kl1") == page.inner_text("#lcd-form"),
          "① 양식 노브 → LCD 도 같은 값")


def pages(browser, tmp, llm):
    """문서 사진 — 실제 화면 (라이트 · 다크) + 제목 카드"""
    os.makedirs(PAGES, exist_ok=True)
    for theme in ("dark", "light"):
        proc, url, _ = start_app(tmp, llm, theme)
        try:
            ctx = browser.new_context(viewport={"width": W, "height": H}, color_scheme=theme,
                                      permissions=["clipboard-read", "clipboard-write"])
            page = ctx.new_page()
            page.goto(url)
            page.wait_for_selector("#pastes .hello")
            fill(page)
            page.click(".knob.k1")                                      # ① 양식 → 이슈 보고
            page.wait_for_function("document.querySelector('#kl1').textContent === '이슈 보고'")
            llm.mode = "good"
            page.click("#draft")
            page.wait_for_selector(".ln .ref")
            page.click("#ok")
            page.wait_for_selector(".seal")
            page.locator(".ln .ref").nth(2).hover()
            page.evaluate("document.querySelector('#p-src .pane-b').scrollTop = 0")   # 토픽 · 붙여 넣는 칸이 보이게
            page.wait_for_timeout(3200)   # 알림이 사라진 뒤
            page.screenshot(path=os.path.join(PAGES, f"hero-{theme}.jpg"), type="jpeg", quality=86)
            if theme == "dark":
                llm.mode = "lie number"
                page.click("#draft")
                page.wait_for_selector(".chip.err:has-text('ERR 근거 없음')")
                page.mouse.move(0, 0)
                page.wait_for_timeout(3200)
                page.locator("#p-draft").screenshot(path=os.path.join(PAGES, "err.png"))
                llm.mode = "good"
            font = url + "font/report-1-dos.woff"
            ink, bg, sub, acc = (("#f2f2f3", "#000", "#a5aaae", "#6aba23") if theme == "dark" else
                                 ("#0b0b0b", "#d4d6d8", "#4c5156", "#45741b"))
            page.set_content(
                f"<style>@font-face{{font-family:D;src:url({font})}}body{{margin:0;background:{bg};color:{ink};"
                f"font-family:D,monospace}}.c{{width:880px;padding:40px 0 34px;text-align:center}}"
                f".a{{font-size:16px;color:{sub};letter-spacing:2px}}.b{{font-size:64px;line-height:72px;margin:10px 0;"
                f"text-shadow:3px 0 0 currentColor}}.b i{{font-style:normal;color:{acc}}}.d{{font-size:24px;color:{sub}}}</style>"
                "<div class=c><div class=a>근거 달린 보고서</div><div class=b>Report–1<i>_</i></div>"
                "<div class=d>붙여 넣으면, 근거와 함께.</div></div>")
            page.wait_for_timeout(400)
            page.locator(".c").screenshot(path=os.path.join(PAGES, f"title-{theme}.png"))
            ctx.close()
        finally:
            proc.terminate()
            proc.wait(10)
    print(f"문서 사진: {PAGES}")


def main():
    os.makedirs(OUT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="report1-e2e-")
    llm = FakeLLM()
    proc, url, home = start_app(tmp, llm)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(viewport={"width": W, "height": H}, color_scheme="dark",
                                      permissions=["clipboard-read", "clipboard-write"])
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            handled = ("status of 400", "status of 409")   # 화면이 알림으로 알려 주는 거절 (같은 자료 · 보관 안 한 자료)
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" and not any(h in m.text for h in handled) else None)
            page.goto(url)
            flow(page, llm, home, lambda name: page.screenshot(path=os.path.join(OUT, name + ".png")))
            check(not errors, f"브라우저 오류 없음 {errors or ''}")
            page.set_viewport_size({"width": 460, "height": 800})
            page.wait_for_timeout(300)
            page.screenshot(path=os.path.join(OUT, "4-narrow.png"), full_page=True)
            check(page.evaluate("document.documentElement.scrollWidth <= 460"), "좁은 창에서 가로 스크롤 없음")
            spill = page.evaluate("""() => { const d = document.querySelector('.device').getBoundingClientRect();
                return [...document.querySelectorAll('.device *')].filter(e => { const r = e.getBoundingClientRect();
                  return r.width && e.offsetParent !== null && !e.closest('.toast') && (r.right > d.right + 1 || r.left < d.left - 1); })
                  .map(e => e.className || e.tagName).slice(0, 5); }""")
            check(not spill, f"좁은 창에서 본체 밖으로 넘치는 것 없음 {spill or ''}")
            ctx.close()
            if "--pages" in sys.argv:
                pages(browser, tmp, llm)
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
        llm.close()
        shutil.rmtree(tmp, ignore_errors=True)
    print("E2E OK")


if __name__ == "__main__":
    main()
