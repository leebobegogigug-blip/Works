# -*- coding: utf-8 -*-
"""브라우저 E2E: Flow–1 실제 프로세스 + Chromium (가짜 사내 쿼리 패키지로 --run 까지).

  pip install playwright && python -m playwright install chromium
  python tests/e2e_ui.py            흐름 확인 + 스크린샷 (SHOT_DIR, 기본 shots/)
  python tests/e2e_ui.py --pages    문서 사진도 다시 찍는다 (docs/page/ 의 hero · title · 부품)
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
EX = os.path.join(HERE, "examples")
FAKE = os.path.join(HERE, "fake_pkg")
from playwright.sync_api import sync_playwright  # noqa: E402

OUT = os.environ.get("SHOT_DIR", os.path.join(ROOT, "shots"))
PAGES = os.path.join(ROOT, "docs", "page")
LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))
W, H = 1480, 900
MARK = "붙여넣기표식QX7Z"

# 실행 중(live) 상태를 보려고 일부러 느린 스크립트 — 지어낸 예시
SLOW = '''"""지어낸 예시 — 느린 쿼리 (E2E 에서 실행 중 표시를 본다)"""
import demo_query as dq
fast = dq.query("SELECT a, b FROM dw.fast LIMIT 7")
slow = dq.query("SELECT c FROM dw.slow_table WHERE c > 0", delay=6)
'''


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def env_for(home):
    return dict(os.environ, FLOW_HOME=home, PYTHONUNBUFFERED="1", PYTHONPATH=FAKE, PYTHONUTF8="1")


def start_app(tmp, theme="dark"):
    home = tempfile.mkdtemp(prefix=theme + "-", dir=tmp)
    with open(os.path.join(home, "config.json"), "w", encoding="utf-8") as f:
        json.dump({"watch": [EX], "theme": theme, "idle_exit_min": 0, "query": {"modules": ["demo_query"]}}, f)
    port = free_port()
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "flow-1.py"), "--no-window", "--port", str(port)],
                            env=env_for(home), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    url = f"http://127.0.0.1:{port}/"
    for _ in range(80):
        try:
            with LOCAL.open(url + "api/ping", timeout=1) as r:
                if json.loads(r.read())["app"] == "flow-1":
                    return proc, url, home
        except Exception:
            time.sleep(0.25)
    proc.kill()
    raise SystemExit("Flow–1 이 켜지지 않았습니다:\n" + proc.stderr.read().decode("utf-8", "replace"))


def run(home, script, *args, wait=True, cwd=None):
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, "flow-1.py"), "--run", script] + list(args), env=env_for(home),
                         stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, cwd=cwd or home)
    if wait:
        p.wait(60)
    return p


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  √ {msg}")


def paste(page, text):
    """Ctrl+V 흉내 — 붙여 넣기 이벤트를 그대로 보낸다 (헤드리스 브라우저는 시스템 클립보드가 없다)"""
    page.evaluate("""(text) => { const dt = new DataTransfer(); dt.setData('text/plain', text);
        document.body.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true})); }""",
                  text)


def disk_has(folder, needle):
    for dp, _, fs in os.walk(folder):
        for f in fs:
            with open(os.path.join(dp, f), "rb") as fh:
                if needle.encode("utf-8") in fh.read():
                    return True
    return False


def pick_file(page, name):
    page.click(f"#files .file:has-text('{name}')")
    page.wait_for_function("(n) => document.querySelector('#lcd-file').textContent === n", arg=name)
    page.wait_for_selector("#svgwrap svg .n")
    page.wait_for_timeout(300)


def flow(page, home, tmp, shots):
    page.wait_for_selector("#svgwrap svg .n")
    page.wait_for_selector("#explorer .ex")
    check(page.locator("#files .file").count() == 6, "01 FILES: 00 전체 + 예시 파일 다섯")
    check("쿼리 19" in page.inner_text("#stats"), "00 전체 보기: 다섯 파일의 쿼리 19개가 한 장에")
    shots("1-all")

    pick_file(page, "daily_sales.py")
    check(page.locator(".flow .n-query").count() == 6, "파일 하나: 쿼리 카드 여섯")
    check(page.locator(".flow .e-param").count() == 1 and page.locator(".flow .e-join").count() >= 3,
          "간선: 조건(점선) 하나 · JOIN 줄 · 병합으로 들어가는 선")
    page.locator('.flow .n[data-id="q3"]').click()
    page.wait_for_selector("#detail .d-title")
    check(page.inner_text("#detail .d-title") == "df_items", "카드를 누르면 02 에 쿼리 전부")
    det = page.inner_text("#detail")
    for part in ("LEFT", "dw.products p", "{order_ids}", "Q01 df_orders", "category, product_id"):
        check(part in det, f"02 QUERY 에 '{part}'")
    check(page.locator(".flow .e.hl").count() >= 4 and "dim" in (page.get_attribute(".flow", "class") or ""),
          "선택한 카드의 간선만 켜지고 나머지는 흐려진다")
    shots("2-query")
    page.click("#detail .ref:has-text('Q01 df_orders')")
    page.wait_for_function("document.querySelector('#detail .d-title').textContent === 'df_orders'")
    check(True, "파라미터의 출처(Q01)를 누르면 그 쿼리로 간다")

    w2 = page.evaluate("document.querySelector('.flow').getAttribute('width')")
    page.click(".knob.k2")                                                  # 보통 → 전부
    page.wait_for_function("(w) => document.querySelector('.flow') && document.querySelector('.flow').getAttribute('width') !== w", arg=w2)
    check(page.inner_text("#kl2") == "전부" and page.inner_text("#v2") == "전부", "② 상세 노브 → 값 칩도 같은 값")
    check(page.locator(".flow .r-with").count() >= 1, "상세 3: WITH 줄")
    page.click(".knob.k2", modifiers=["Shift"])
    page.click(".knob.k4")
    page.wait_for_timeout(200)
    check("f-join" in page.get_attribute(".flow", "class"), "④ 강조 JOIN")
    shots("3-focus-join")
    page.click(".knob.k4", modifiers=["Shift"])

    page.fill("#find", "vip_daily")
    page.press("#find", "Enter")
    page.wait_for_timeout(200)
    check(page.locator(".flow .n.hit").count() == 4, "찾기: tmp.vip_daily 를 쓰고 · 읽는 쿼리 · 테이블 · 같은 이름의 출력 파일 (4)")
    page.press("#find", "Escape")

    # 탐색기: 폴더 펼치기 · 이번만 열기 · 감시 목록 밖의 파일
    page.click("#explorer .ex.dir:has-text('sql')")
    page.wait_for_selector("#explorer .ex:has-text('returns.sql')")
    check(True, "탐색기: 폴더를 누르면 펼친다")
    other = os.path.join(tmp, "scratch")
    os.makedirs(other, exist_ok=True)
    with open(os.path.join(other, "adhoc.py"), "w", encoding="utf-8") as f:
        f.write('import demo_query as dq\nx = dq.query("SELECT k, v FROM mart.adhoc WHERE v > 0")\n')
    page.fill("#path-in", other)
    page.press("#path-in", "Enter")
    page.wait_for_selector("#explorer .ex:has-text('adhoc.py')")
    check("●" in page.inner_text("#explorer .ex:has-text('adhoc.py')"), "탐색기: SQL 이 있어 보이는 파일에 ●")
    page.click("#explorer .ex:has-text('adhoc.py')")
    page.wait_for_function("document.querySelector('#lcd-file').textContent === 'adhoc.py'")
    page.wait_for_selector(".flow .n-query")
    check("이번만 연 파일" in page.inner_text("#files"), "파일을 누르면 이번만 열기 — 감시 목록과 따로")
    with open(os.path.join(home, "config.json"), encoding="utf-8") as f:
        check(other not in json.dumps(json.load(f)), "이번만 연 파일은 설정에 남지 않는다")
    shots("4-explorer")

    # 붙여 넣기 (메모리에만)
    paste(page, f'import demo_query as dq\n# {MARK}\nfoo = dq.query("SELECT x FROM s.pasted JOIN s.more ON pasted.k = more.k")\n')
    page.wait_for_function("document.querySelector('#lcd-file').textContent.startsWith('붙여 넣은 코드')")
    page.wait_for_selector(".flow .n-query")
    check(not disk_has(home, MARK), "붙여 넣은 코드는 디스크에 없다 (W-05)")

    # --run: 끝난 실행 겹치기 · 실행 중 표시
    run(home, os.path.join(EX, "run_demo.py"), "--fail")
    pick_file(page, "run_demo.py")
    page.wait_for_selector(".flow text.run-ok")
    check(page.locator(".flow text.run-err").count() == 1, "실행 기록: 실패한 쿼리에 ERR")
    check(not page.is_hidden("#runbar") and "ERR" in page.inner_text("#runbar"), "흐름도 아래 실행 줄")
    page.click("#runs-btn")
    page.wait_for_selector(".drawer .row")
    check(page.locator(".drawer .row").count() == 1, "04 RUNS: 실행 기록 목록")
    shots("5-runs")
    page.keyboard.press("Escape")
    slow = os.path.join(tmp, "slow_job.py")
    with open(slow, "w", encoding="utf-8") as f:
        f.write(SLOW)
    proc = run(home, slow, wait=False)
    page.wait_for_selector("#files .file:has-text('slow_job.py')", timeout=20000)
    pick_file(page, "slow_job.py")
    page.wait_for_selector(".flow text.run-busy", timeout=15000)
    check("busy" in page.get_attribute("#led-run", "class"), "실행 중: run LED 깜빡임 · 카드에 ◐")
    shots("6-live")
    proc.wait(60)
    page.wait_for_selector(".flow text.run-ok >> nth=1", timeout=15000)
    check(page.locator(".flow text.run-busy").count() == 0, "실행이 끝나면 걸린 시간으로 바뀐다")

    with page.expect_download() as dl:
        page.click("#save-svg")
    path = dl.value.path()
    with open(path, encoding="utf-8") as f:
        text = f.read()
    check(text.startswith("<svg") and "data:font/woff;base64," in text, "SVG 저장 — 폰트 · 색을 담은 파일")


def pages(browser, tmp):
    """문서 사진 — 실제 화면 (라이트 · 다크) + 제목 카드 + 부품"""
    os.makedirs(PAGES, exist_ok=True)
    for theme in ("dark", "light"):
        proc, url, home = start_app(tmp, theme)
        try:
            run(home, os.path.join(EX, "run_demo.py"), "--fail")      # 성공한 쿼리 · 실패한 쿼리(ERR · 가린 비밀번호)가 같이 보이게
            ctx = browser.new_context(viewport={"width": W, "height": H}, color_scheme=theme, accept_downloads=True)
            page = ctx.new_page()
            page.goto(url)
            page.wait_for_selector("#svgwrap svg .n")
            pick_file(page, "daily_sales.py")
            page.evaluate("document.querySelector('#canvas').scrollTo(0, 0)")
            page.locator('.flow .n[data-id="q3"]').click()
            page.wait_for_selector("#detail .d-title")
            page.evaluate("document.querySelector('#canvas').scrollTo(0, 0)")
            page.wait_for_timeout(3400)
            page.screenshot(path=os.path.join(PAGES, f"hero-{theme}.jpg"), type="jpeg", quality=86)
            if theme == "dark":
                page.keyboard.press("Escape")
                page.wait_for_timeout(300)
                page.locator('.flow .n[data-id="q2"]').screenshot(path=os.path.join(PAGES, "card.png"))
                page.locator("#p-files").screenshot(path=os.path.join(PAGES, "explorer.png"))
                # 흐름도 한 장 — 화면보다 넓으니 'SVG 저장' 과 같은 파일(색 · 폰트 내장)을 그대로 그려 찍는다
                whole_svg = page.evaluate("""async () => (await fetch(
                    `/api/svg?f=${encodeURIComponent(S.key)}&d=2&theme=dark`, { headers: { "X-Flow-Token": TOKEN } })).text()""")
                whole = ctx.new_page()
                whole.set_content('<body style="margin:0">' + whole_svg + "</body>")
                whole.evaluate("document.fonts.ready.then(() => true)")
                whole.wait_for_timeout(300)
                whole.locator("svg").screenshot(path=os.path.join(PAGES, "flow.png"))
                whole.close()
                page.set_viewport_size({"width": 1800, "height": 640})      # 병합 · 출력까지 흐름도 구역에 다 들어오게
                pick_file(page, "run_demo.py")
                page.wait_for_selector(".flow text.run-ok")
                page.wait_for_selector(".flow .run-err")
                page.locator("#p-flow").screenshot(path=os.path.join(PAGES, "run.png"))
            font = url + "font/flow-1-dos.woff"
            ink, bg, sub, acc = (("#f2f2f3", "#000", "#a5aaae", "#6aba23") if theme == "dark" else
                                 ("#0b0b0b", "#d4d6d8", "#4c5156", "#45741b"))
            page.set_content(
                f"<style>@font-face{{font-family:D;src:url({font})}}body{{margin:0;background:{bg};color:{ink};"
                f"font-family:D,monospace}}.c{{width:880px;padding:40px 0 34px;text-align:center}}"
                f".a{{font-size:16px;color:{sub};letter-spacing:2px}}.b{{font-size:64px;line-height:72px;margin:10px 0;"
                f"text-shadow:3px 0 0 currentColor}}.b i{{font-style:normal;color:{acc}}}.d{{font-size:24px;color:{sub}}}</style>"
                "<div class=c><div class=a>파이썬 데이터 쿼리 흐름도</div><div class=b>Flow–1<i>_</i></div>"
                "<div class=d>쿼리가 흐르는 길, 한 장에.</div></div>")
            page.wait_for_timeout(400)
            page.locator(".c").screenshot(path=os.path.join(PAGES, f"title-{theme}.png"))
            ctx.close()
        finally:
            proc.terminate()
            proc.wait(10)
    print(f"문서 사진: {PAGES}")


def main():
    os.makedirs(OUT, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="flow1-e2e-")
    proc, url, home = start_app(tmp)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(viewport={"width": W, "height": H}, color_scheme="dark", accept_downloads=True)
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            handled = ("status of 400", "status of 404")    # 화면이 알림으로 알려 주는 거절
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" and not any(h in m.text for h in handled) else None)
            page.goto(url)
            flow(page, home, tmp, lambda name: page.screenshot(path=os.path.join(OUT, name + ".png")))
            check(not errors, f"브라우저 오류 없음 {errors or ''}")
            page.set_viewport_size({"width": 460, "height": 800})
            page.wait_for_timeout(300)
            page.screenshot(path=os.path.join(OUT, "7-narrow.png"), full_page=True)
            check(page.evaluate("document.documentElement.scrollWidth <= 460"), "좁은 창에서 가로 스크롤 없음")
            ctx.close()
            if "--pages" in sys.argv:
                pages(browser, tmp)
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(tmp, ignore_errors=True)
    print("E2E OK")


if __name__ == "__main__":
    main()
