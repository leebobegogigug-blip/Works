# -*- coding: utf-8 -*-
"""브라우저 E2E: 가짜 LLM + 가짜 Secretary–1(공개 명령) + 진짜 git + Report–1 실제 프로세스 + Chromium.

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
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from fake_llm_server import FakeLLM  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

OUT = os.environ.get("SHOT_DIR", os.path.join(ROOT, "shots"))
PAGES = os.path.join(ROOT, "docs", "page")
LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))
W, H = 1100, 820


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def git(repo, *args, when=None):
    env = dict(os.environ)
    if when:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = when
    subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, env=env)


def seed(tmp):
    """이번 주 월요일 기준의 커밋 · 일정 — 언제 돌려도 '이번 주' 안에 들어간다"""
    mon = date.today() - timedelta(days=date.today().weekday())
    work = os.path.join(tmp, "work")
    for repo, commits in (("api-server", [("로그인 토큰 만료 처리", 0), ("토큰 갱신 실패 로그 정리", 1), ("만료 시각 테스트 추가", 2)]),
                          ("web-front", [("대시보드 차트 색 정리", 1), ("차트 범례 겹침 수정", 3)])):
        path = os.path.join(work, repo)
        os.makedirs(path)
        git(path, "init", "-q")
        git(path, "config", "user.email", "me@example.com")
        git(path, "config", "user.name", "Me")
        for msg, d in commits:
            with open(os.path.join(path, "f.txt"), "a", encoding="utf-8") as f:
                f.write(msg + "\n")
            git(path, "add", "f.txt")
            git(path, "commit", "-q", "-m", msg, when=f"{mon + timedelta(days=d)}T{10 + d}:00:00")
    evs = [("주간회의", 0, "10:00", "3A"), ("고객사 미팅 · 견적 검토", 2, "14:00", "본사 5층"),
           ("주간회의", 7, "10:00", "3A"), ("분기 계획 리뷰", 9, "15:00", "")]
    events = [{"id": f"L{i}", "title": t, "start": f"{mon + timedelta(days=d)}T{h}", "end": f"{mon + timedelta(days=d)}T{h}",
               "all_day": False, "location": loc, "recurring": t == "주간회의"} for i, (t, d, h, loc) in enumerate(evs, 1)]
    sec = os.path.join(tmp, "sec", "secretary-1.py")
    os.makedirs(os.path.dirname(sec))
    with open(sec, "w", encoding="utf-8") as f:
        f.write("import json, sys\na = sys.argv\nf, t = a[a.index('--from') + 1], a[a.index('--to') + 1]\n"
                f"evs = [e for e in json.loads({json.dumps(events, ensure_ascii=False)!r}) if f <= e['start'][:10] <= t]\n"
                "sys.stdout.buffer.write((json.dumps({'app': 'secretary-1', 'version': '0.6.0', 'format': 1, "
                "'backend': 'local', 'events': evs}, ensure_ascii=False) + '\\n').encode('utf-8'))\n")
    return work, sec


def start_app(tmp, llm, theme="dark"):
    run = tempfile.mkdtemp(prefix=theme + "-", dir=tmp)   # 켤 때마다 새 폴더 (저장소 · 설정 · 일지)
    home = os.path.join(run, "home")
    os.makedirs(home)
    work, sec = seed(run)
    with open(os.path.join(home, "config.json"), "w", encoding="utf-8") as f:
        json.dump({"llm": {"base_url": llm.url, "model": "fake-model"}, "theme": theme, "idle_exit_min": 0,
                   "user_name": "김개발", "sources": {"git": {"roots": [work]}, "calendar": {"secretary": sec}}}, f)
    port = free_port()
    env = dict(os.environ, REPORT_HOME=home, PYTHONUNBUFFERED="1", GIT_CONFIG_NOSYSTEM="1",
               GIT_CONFIG_GLOBAL=os.path.join(run, "gitconfig"))
    open(env["GIT_CONFIG_GLOBAL"], "a").close()
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "report-1.py"), "--no-window", "--port", str(port)],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    url = f"http://127.0.0.1:{port}/"
    for _ in range(80):
        try:
            with LOCAL.open(url + "api/ping", timeout=1) as r:
                if json.loads(r.read())["app"] == "report-1":
                    return proc, url
        except Exception:
            time.sleep(0.25)
    proc.kill()
    raise SystemExit("Report–1 이 켜지지 않았습니다:\n" + proc.stderr.read().decode("utf-8", "replace"))


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  √ {msg}")


def flow(page, llm, shots):
    page.wait_for_selector(".src")
    check(page.locator(".src").count() >= 7, "근거: 커밋 · 일정 · 다음 일정이 모인다")
    check("W" in page.inner_text("#wk"), "LCD 에 주차")
    page.fill("#jin", "신입 온보딩 문서 초안 작성")
    page.press("#jin", "Enter")
    page.wait_for_selector(".src:has-text('신입 온보딩 문서 초안 작성')")
    check(True, "오늘 한 일 → 일지 근거")
    page.click("#draft")
    page.wait_for_selector(".ln .txt")
    check(page.inner_text("#mode") == "LLM", "초안: 사내 LLM (가짜)")
    check(page.locator("#errs").is_hidden(), "근거 없는 줄 없음")
    check(page.locator(".ln .ref").count() >= 5, "줄마다 근거 칩")
    first = page.locator(".ln .ref").first
    first.hover()
    check(page.locator(".src.hl").count() == 1, "근거 칩에 올리면 근거 줄이 켜진다")
    page.mouse.move(5, 5)
    shots("1-draft")
    page.keyboard.press("Control+s")
    page.wait_for_selector(".seal")
    check(page.is_visible("#undo"), "확정 → 도장 · 되돌리기")
    copied = page.evaluate("navigator.clipboard.readText()")
    check(copied.startswith("■ 금주 실적"), "확정하면 보고서 글이 클립보드로")
    shots("2-confirmed")
    page.click("#undo")
    page.wait_for_selector(".seal", state="detached")
    check(page.locator("#undo").is_hidden(), "20초 안에 되돌리기")

    llm.mode = "lie"
    page.click("#draft")
    page.wait_for_selector(".chip.err:has-text('ERR 근거 없음')")
    check(page.is_disabled("#ok"), "지어낸 실적(ERR)이 있으면 확정 못 함")
    shots("3-err")
    bad = page.locator(".ln.err .txt").first
    bad.click()
    page.keyboard.press("End")
    page.keyboard.type(" (고객 설문 기준)")
    page.keyboard.press("Enter")
    page.wait_for_selector(".chip.navy:has-text('직접')")
    page.wait_for_function("!document.querySelector('#ok').disabled")
    check(True, "사람이 고치면 '직접' — 책임을 지고 확정할 수 있다")
    page.click("#ok")
    page.wait_for_selector(".seal")
    llm.mode = "good"
    page.click("#reports")
    page.wait_for_selector(".drawer .rep")
    check(page.locator(".drawer .rep").count() == 1, "지난 보고서에 하나")
    page.keyboard.press("Escape")
    page.click(".knob.k1")
    page.wait_for_selector(".hello")
    check(page.inner_text("#kl1") == "지난 주", "① 기간 노브 → 지난 주 · 초안 비움")


def pages(browser, tmp, llm):
    """문서 사진 — 실제 화면 (라이트 · 다크) + 제목 카드"""
    os.makedirs(PAGES, exist_ok=True)
    for theme in ("dark", "light"):
        proc, url = start_app(tmp, llm, theme)
        try:
            ctx = browser.new_context(viewport={"width": W, "height": H}, color_scheme=theme,
                                      permissions=["clipboard-read", "clipboard-write"])
            page = ctx.new_page()
            page.goto(url)
            page.wait_for_selector(".src")
            page.fill("#jin", "신입 온보딩 문서 초안 작성")
            page.press("#jin", "Enter")
            page.wait_for_selector(".src:has-text('신입 온보딩')")
            llm.mode = "good"
            page.click("#draft")
            page.wait_for_selector(".ln .txt")
            page.click("#ok")
            page.wait_for_selector(".seal")
            page.wait_for_timeout(2900)   # 알림이 사라진 뒤
            page.screenshot(path=os.path.join(PAGES, f"hero-{theme}.jpg"), type="jpeg", quality=86)
            if theme == "dark":
                llm.mode = "lie"
                page.click("#draft")
                page.wait_for_selector(".chip.err:has-text('ERR 근거 없음')")
                page.wait_for_timeout(300)
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
                "<div class=c><div class=a>근거 달린 주간보고</div><div class=b>Report–1<i>_</i></div>"
                "<div class=d>한 주를 모아, 근거와 함께.</div></div>")
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
    proc, url = start_app(tmp, llm)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context(viewport={"width": W, "height": H}, color_scheme="dark",
                                      permissions=["clipboard-read", "clipboard-write"])
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.goto(url)
            flow(page, llm, lambda name: page.screenshot(path=os.path.join(OUT, name + ".png")))
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
