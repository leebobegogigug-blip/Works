# -*- coding: utf-8 -*-
"""브라우저 E2E: 가짜 LLM 서버 + jaba 실제 프로세스 + Chromium. 스크린샷도 남긴다."""
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timedelta

TZ = "Asia/Seoul" if hasattr(time, "tzset") else None  # Windows 는 PC 시간대를 그대로 쓴다
if TZ:
    os.environ["TZ"] = TZ
    time.tzset()
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import jaba  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

OUT = os.environ.get("SHOT_DIR", os.path.join(ROOT, "shots"))
os.makedirs(OUT, exist_ok=True)
ENV = dict(os.environ, PYTHONUNBUFFERED="1")
LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))
W, H = 460, 800  # 기본 창 크기 (컴팩트)
TZ_ARG = {"timezone_id": TZ} if TZ else {}


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def seed(db, ongoing=False, alert_soon=False):
    cal = jaba.LocalCalendar(db)
    now = datetime.now()
    base = now.replace(minute=0 if now.minute < 30 else 30, second=0, microsecond=0)
    today = jaba.start_of_day(now)

    def add(title, start, minutes, loc=""):
        cal.create_event(title, start, start + timedelta(minutes=minutes), loc)

    add("데일리 스크럼", base - timedelta(hours=4), 30, "온라인")
    add("디자인 리뷰", base - timedelta(hours=2), 60, "2B")
    add("주간회의", base + timedelta(hours=1), 60, "3A")
    add("1:1 김과장", base + timedelta(hours=2, minutes=30), 30, "포커스룸")
    add("고객사 콜", base + timedelta(hours=2, minutes=45), 45, "온라인")
    add("코드리뷰", base + timedelta(hours=3, minutes=30), 60, "온라인")
    cal.create_event("보안 점검 주간", today, today + timedelta(days=1), all_day=True)
    mon = today + timedelta(days=1)
    while mon.weekday() != 0:
        mon += timedelta(days=1)
    add("분기 계획", mon.replace(hour=14, minute=30), 60, "대회의실")
    if ongoing:
        add("집중 작업", now.replace(second=0, microsecond=0) - timedelta(minutes=20), 45, "자리")
    if alert_soon:  # 장소 없는 일정 → 5분 전 알림이 몇 초 뒤에 울리도록
        s = datetime.now().replace(microsecond=0) + timedelta(minutes=5, seconds=4)
        cal.create_event("보고서 마감", s, s + timedelta(minutes=30), "")
    cal.db.close()


def start_stack(mode, tmp, theme=None, ongoing=False, alert_soon=False):
    llm_port, app_port = free_port(), free_port()
    fake = subprocess.Popen([sys.executable, os.path.join(HERE, "fake_llm_server.py"), str(llm_port), mode], env=ENV)
    db = os.path.join(tmp, f"{mode}-{app_port}.db")
    seed(db, ongoing, alert_soon)
    cfg = {"llm": {"base_url": f"http://127.0.0.1:{llm_port}/v1", "model": "사내-LLM", "proxy": ""},
           "calendar": {"backend": "local", "local_db": db}, "open_window": False, "hotkey": "",
           "port": app_port, "user_name": "Bob", "learn_file": os.path.join(tmp, f"rules-{app_port}.json"),
           "alerts": {"poll_sec": 1 if alert_soon else 10}}
    if theme:
        cfg["theme"] = theme
    cfg_path = os.path.join(tmp, f"{mode}-{app_port}.json")
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False)
    logf = open(os.path.join(tmp, f"{mode}-{app_port}.log"), "w")
    app = subprocess.Popen([sys.executable, os.path.join(ROOT, "jaba.py"), "--config", cfg_path, "--no-window"],
                           env=ENV, stdout=logf, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{app_port}/"
    for _ in range(100):
        try:
            with LOCAL.open(url + "api/ping", timeout=0.5) as r:
                if json.loads(r.read())["app"] == "jaba":
                    break
        except Exception:
            time.sleep(0.1)
    else:
        raise SystemExit("jaba 가 뜨지 않음: " + open(os.path.join(tmp, f"{mode}-{app_port}.log")).read())
    return fake, app, url, cfg_path, llm_port


def api_client(url):
    html = LOCAL.open(url, timeout=5).read().decode()
    token = re.search(r'name="jaba-token" content="([^"]+)"', html).group(1)

    def call(path, body=None):
        req = urllib.request.Request(url.rstrip("/") + path, method="POST" if body is not None else "GET",
                                     data=json.dumps(body).encode() if body is not None else None)
        req.add_header("X-Jaba-Token", token)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        with LOCAL.open(req, timeout=20) as r:
            return json.loads(r.read())
    return call


def llm_stats(port):
    return json.loads(LOCAL.open(f"http://127.0.0.1:{port}/", timeout=5).read())


def check_mode(mode, tmp):
    fake, app, url, cfg_path, llm_port = start_stack(mode, tmp)
    try:
        api = api_client(url)
        r = api("/api/chat", {"message": "월요일 3시 김과장 미팅 잡아줘 3A에서"})
        assert r["proposals"] and r["proposals"][0]["kind"] == "create", r
        assert r["mode"] == ("native" if mode == "native" else "json"), r["mode"]
        assert "겹치는" in r["reply"] and r["proposals"][0]["conflicts"], r
        assert api("/api/proposals/p1/confirm", {})["proposal"]["status"] == "done"
        r = api("/api/chat", {"message": "주간회의 옮겨줘"})
        assert r["proposals"] and r["proposals"][0]["kind"] == "update", r
        assert [a["tool"] for a in r["activity"]] == ["list_events", "propose_update"], r["activity"]
        r = api("/api/chat", {"message": "이번 주에 1시간 비는 시간 찾아줘"})
        assert r["reply"].startswith("1시간 비는 시간"), r
        assert "<think>" not in r["reply"]
        r = api("/api/chat", {"message": "앞으로 스크럼은 항상 15분 기억해"})  # 대화로 학습 (모드별)
        assert r["learned"] and r["learned"][0]["text"] == "스크럼은 항상 15분", r
        api("/api/chat", {"message": "내일 일정 알려줘"})
        stats = llm_stats(llm_port)
        assert stats["rules_in_prompt"] and "스크럼은 항상 15분" in stats["last_rules"], stats
        check = subprocess.run([sys.executable, os.path.join(ROOT, "jaba.py"), "--config", cfg_path, "--check"],
                               env=ENV, capture_output=True, text=True, timeout=60)
        assert "학습 규칙 : 1개" in check.stdout, check.stdout
        print(f"[{mode}] ok · llm 요청 {stats['requests']}회 (tools 포함 {stats['with_tools']}회)")
        print("   --check ▸ " + "\n   --check ▸ ".join(check.stdout.strip().splitlines()[2:]))
    finally:
        app.terminate()
        fake.terminate()


NAVY, LIME, GREY = "rgb(0, 35, 65)", "rgb(106, 186, 35)", "rgb(165, 170, 174)"
BLACK_PANEL, INK_BLACK, LIGHT_PANEL = "rgb(11, 11, 11)", "rgb(11, 11, 11)", "rgb(239, 238, 233)"


def css(page, sel, prop):
    return page.eval_on_selector(sel, f"e => getComputedStyle(e).{prop}")


def ui_run(tmp):
    errors = []
    stacks = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()

            def new_page(url, scheme="dark", w=W, h=H):
                ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=2,
                                          locale="ko-KR", color_scheme=scheme, **TZ_ARG)
                page = ctx.new_page()
                page.on("pageerror", lambda e: errors.append(f"{scheme}: {e}"))
                page.on("console", lambda m: m.type == "error" and errors.append(f"{scheme}: {m.text}"))
                page.goto(url)
                page.wait_for_selector(".msg.bot")
                page.wait_for_function("!document.body.classList.contains('booting')")
                return page

            def bots(page):
                return page.locator(".msg.bot").count()

            def say(page, text, wait_bot=True):
                n = bots(page)
                page.fill("#msg", text)
                page.press("#msg", "Enter")
                if wait_bot:
                    page.wait_for_function(f"document.querySelectorAll('.msg.bot').length > {n}")
                page.wait_for_timeout(450)  # 타자 애니메이션

            def stamp_flow(page):
                n = bots(page)
                page.click(".key >> nth=0")
                page.wait_for_function(f"document.querySelectorAll('.msg.bot').length > {n}")
                page.fill("#msg", "월요일 3시 김과장 미팅 잡아줘. 3A에서")
                page.press("#msg", "Enter")
                page.wait_for_selector(".card.pending")
                card = page.inner_text(".card.pending")
                assert "겹침" in card and "분기 계획" in card, card
                page.click(".card.pending .okb")
                page.wait_for_selector(".card.done")
                page.wait_for_selector("#mascot.happy")
                page.wait_for_timeout(1000)

            # ── A. 기본 = 검정 다크 · 컴팩트 (OS가 라이트여도 다크)
            fake, app, url, _, llm_port = start_stack("native", tmp)
            stacks += [fake, app]
            p = new_page(url, "light")
            assert "남은 일정" in p.inner_text(".msg.bot"), p.inner_text(".msg.bot")
            assert css(p, ".device", "backgroundColor") == BLACK_PANEL
            assert css(p, ".send", "backgroundColor") == LIME
            assert css(p, ".key.k3", "backgroundColor") == NAVY and css(p, ".key.k1", "backgroundColor") == LIME
            assert p.locator("#next-count svg.seg").count() == 1 and p.locator("#clock-time svg.seg").count() == 1
            assert p.locator("#mascot svg rect").count() > 80
            assert p.locator(".track .ev").count() >= 6 and p.locator(".track .nowline").count() == 1
            assert p.inner_text("#next-title") != "self-test"
            # 도스 픽셀 폰트: 내장 WOFF 가 실제로 로드되고 전체에 쓰인다
            assert p.evaluate("[...document.fonts].some(f => f.family.replace(/\"/g, '') === 'JabaDOS' && f.status === 'loaded')")
            assert css(p, "body", "fontFamily").startswith(("JabaDOS", '"JabaDOS"'))
            assert css(p, "#msg", "fontFamily") == css(p, ".key.k1", "fontFamily") == css(p, "body", "fontFamily")
            stamp_flow(p)
            p.wait_for_function("!document.querySelector('.bit')")  # 도장 파편이 다 사라진 뒤에
            wide_boxes = p.evaluate("""() => [...document.querySelectorAll('.device, .bar, .lcd, .overview, .log, .keys, .input, .foot')]
                .filter(e => e.scrollWidth > e.clientWidth + 1).map(e => e.className)""")
            assert not wide_boxes, wide_boxes  # 글자가 커져도 가로로 넘치지 않는다
            assert css(p, ".msg.user", "backgroundColor") == GREY
            assert css(p, ".card.done .seal", "borderTopColor") == LIME
            p.screenshot(path=os.path.join(OUT, "jaba-compact.png"))

            # 오늘 일정 서랍
            p.click("#day-count")
            p.wait_for_selector("#day-drawer:not([hidden])")
            assert p.locator("#day-drawer .chip").count() == 1
            assert p.locator("#daylist .row").count() >= 6
            p.wait_for_timeout(500)
            p.screenshot(path=os.path.join(OUT, "jaba-day.png"))
            p.click("#next")
            p.wait_for_function("document.querySelector('#day-label').textContent === 'tomorrow'")
            p.keyboard.press("Escape")
            p.wait_for_selector("#day-drawer", state="hidden")

            # 학습: 명령어 → 대화 → 서랍에서 직접
            say(p, "/학습 스크럼은 항상 15분")
            assert "학습했습니다" in p.locator(".msg.bot").last.inner_text()
            assert p.inner_text("#mem-count") == "1"
            say(p, "앞으로 코드리뷰는 30분으로 잡아 기억해")
            p.wait_for_function("document.querySelector('#mem-count').textContent === '2'")
            assert p.locator(".act.learn").count() == 2
            st = llm_stats(llm_port)
            assert st["rules_in_prompt"] and "스크럼은 항상 15분" in st["last_rules"], st
            p.keyboard.press("Alt+m")
            p.wait_for_selector("#mem-drawer:not([hidden])")
            p.wait_for_function("document.querySelectorAll('#rules .rule').length === 2")
            p.fill("#rule-input", "금요일 오후엔 회의 잡지 마")
            p.press("#rule-input", "Enter")
            p.wait_for_function("document.querySelectorAll('#rules .rule').length === 3")
            p.wait_for_selector(".plus1")
            p.wait_for_timeout(250)
            p.screenshot(path=os.path.join(OUT, "jaba-learn.png"))
            p.click("#rules .rule >> nth=0 >> .x")
            p.wait_for_function("document.querySelectorAll('#rules .rule').length === 2")
            assert p.inner_text("#mem-count") == "2"
            p.keyboard.press("Escape")

            # 제안 → Esc 취소(구기기) → Ctrl+Enter 확정 → 'ㅇㅇ' 확정
            say(p, "월요일 오전 기획 회의 잡아줘")
            p.wait_for_selector(".card.pending")
            assert css(p, ".card.pending .okb", "color") == INK_BLACK
            p.wait_for_timeout(750)
            p.screenshot(path=os.path.join(OUT, "jaba-pending.png"))
            p.keyboard.press("Escape")
            p.wait_for_selector(".card.cancelled")
            say(p, "월요일 오전 기획 회의 잡아줘")
            p.wait_for_selector(".card.pending")
            p.keyboard.press("Control+Enter")
            p.wait_for_function("document.querySelectorAll('.card.done').length === 2")
            say(p, "내일 오전 회의 잡아줘")
            p.wait_for_selector(".card.pending")
            say(p, "ㅇㅇ")
            p.wait_for_function("document.querySelectorAll('.card.pending').length === 0")
            assert p.locator(".card.done").count() == 3

            # Alt+1 빠른 키, /알림 → 앱 안 알림
            n = bots(p)
            p.keyboard.press("Alt+2")
            p.wait_for_function(f"document.querySelectorAll('.msg.bot').length > {n}")
            say(p, "/알림")
            p.wait_for_selector(".toast.show")
            assert "알림 테스트" in p.inner_text("#toast-text")
            assert p.locator(".act.alert").count() >= 1
            p.wait_for_timeout(500)
            p.screenshot(path=os.path.join(OUT, "jaba-alert.png"))

            # 넓은 창에서도 본체는 컴팩트하게 가운데
            wide = new_page(url, "dark", 1100, 760)
            assert wide.eval_on_selector(".device", "e => e.getBoundingClientRect().width") <= 560

            # ── D. 진행 중인 회의: 라임 블록 + now
            fake4, app4, url4, _, _ = start_stack("native", tmp, ongoing=True)
            stacks += [fake4, app4]
            s = new_page(url4)
            s.wait_for_selector(".track .ev.now")
            assert css(s, ".track .ev.now", "backgroundColor") == LIME
            assert css(s, ".track .ev.past", "opacity") == "1"
            assert s.inner_text("#next-k") == "now", s.inner_text("#next-k")
            s.wait_for_timeout(400)
            s.screenshot(path=os.path.join(OUT, "jaba-now.png"))

            # ── E. 실제 알림 타이밍: 장소 없는 일정 5분 전
            fake5, app5, url5, _, _ = start_stack("native", tmp, alert_soon=True)
            stacks += [fake5, app5]
            e = new_page(url5)
            e.wait_for_selector(".toast.show", timeout=20000)
            txt = e.inner_text("#toast-text")
            assert "5분 뒤 · 보고서 마감" in txt, txt
            assert e.locator("#mascot.alert").count() == 1

            # ── B/C. 테마: system 은 OS 따라, light 는 항상 라이트
            fake2, app2, url2, _, _ = start_stack("native", tmp, theme="system")
            stacks += [fake2, app2]
            lt = new_page(url2, "light")
            assert css(lt, ".device", "backgroundColor") == LIGHT_PANEL
            stamp_flow(lt)
            lt.screenshot(path=os.path.join(OUT, "jaba-light.png"))
            assert css(new_page(url2, "dark"), ".device", "backgroundColor") == BLACK_PANEL
            fake3, app3, url3, _, _ = start_stack("native", tmp, theme="light")
            stacks += [fake3, app3]
            assert css(new_page(url3, "dark"), ".device", "backgroundColor") == LIGHT_PANEL
            browser.close()
    finally:
        for proc in stacks:
            proc.terminate()
    assert not errors, errors
    print("[ui] ok · 컴팩트·학습·알림·테마 확인 · 스크린샷 →", OUT)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        for mode in ("native", "json", "qwen"):
            check_mode(mode, tmp)
        ui_run(tmp)
