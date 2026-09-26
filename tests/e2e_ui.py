# -*- coding: utf-8 -*-
"""브라우저 E2E: 가짜 LLM 서버 + Secretary–1 실제 프로세스 + Chromium. 스크린샷도 남긴다."""
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timedelta, timezone


def pick_tz():
    """시험 일정을 '지금 ±4시간'에 심으므로 현지 시각이 한낮이어야 전부 오늘 안에 들어간다.
    한국이 낮(08~17시)이면 한국 시간, 아니면 지금이 오전 11시쯤인 고정 오프셋 시간대 (Etc/GMT±N · 부호가 반대).
    비서 · 가짜 LLM · 브라우저가 모두 같은 시간대를 쓴다. Windows 는 PC 시간대를 그대로 쓴다."""
    if not hasattr(time, "tzset"):
        return None
    now = datetime.now(timezone.utc)
    if 8 <= (now + timedelta(hours=9)).hour <= 17:
        return "Asia/Seoul"
    off = int(round(11 - (now.hour + now.minute / 60))) % 24
    if off > 14:
        off -= 24
    return "Etc/UTC" if off == 0 else (f"Etc/GMT-{off}" if off > 0 else f"Etc/GMT+{-off}")


TZ = pick_tz()
if TZ:
    os.environ["TZ"] = TZ
    time.tzset()
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location("secretary", os.path.join(ROOT, "secretary-1.py"))
sec = importlib.util.module_from_spec(_spec)
sys.modules["secretary"] = sec  # dataclass 가 모듈을 찾을 수 있게
_spec.loader.exec_module(sec)
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
    cal = sec.LocalCalendar(db)
    now = datetime.now()
    base = now.replace(minute=0 if now.minute < 30 else 30, second=0, microsecond=0)
    today = sec.start_of_day(now)

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
           "wiki_file": os.path.join(tmp, f"wiki-{app_port}.json"),
           "alerts": {"poll_sec": 1 if alert_soon else 10}}
    if theme:
        cfg["theme"] = theme
    cfg_path = os.path.join(tmp, f"{mode}-{app_port}.json")
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False)
    logf = open(os.path.join(tmp, f"{mode}-{app_port}.log"), "w")
    app = subprocess.Popen([sys.executable, os.path.join(ROOT, "secretary-1.py"), "--config", cfg_path, "--no-window"],
                           env=ENV, stdout=logf, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{app_port}/"
    for _ in range(100):
        try:
            with LOCAL.open(url + "api/ping", timeout=0.5) as r:
                if json.loads(r.read())["app"] == "secretary-1":
                    break
        except Exception:
            time.sleep(0.1)
    else:
        raise SystemExit("Secretary-1 이 뜨지 않음: " + open(os.path.join(tmp, f"{mode}-{app_port}.log")).read())
    return fake, app, url, cfg_path, llm_port


def api_client(url):
    html = LOCAL.open(url, timeout=5).read().decode()
    token = re.search(r'name="secretary-token" content="([^"]+)"', html).group(1)

    def call(path, body=None):
        req = urllib.request.Request(url.rstrip("/") + path, method="POST" if body is not None else "GET",
                                     data=json.dumps(body).encode() if body is not None else None)
        req.add_header("X-Secretary-Token", token)
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
        r = api("/api/chat", {"message": "앞으로 스크럼은 항상 15분 기억해"})  # 대화로 학습 (모드별) → 카드 확정
        card = r["proposals"][0]
        assert card["kind"] == "rule" and card["rows"][0][1] == "스크럼은 항상 15분", r
        assert api(f"/api/proposals/{card['id']}/confirm", {})["rules"] == 1
        r = api("/api/chat", {"message": "주간회의 준비물은 노트북이랑 지난주 회의록, 안건은 분기 목표 점검이야 정리해줘"})
        card = r["proposals"][0]
        assert card["kind"] == "wiki" and ["준비", "노트북 · 지난주 회의록", True] in card["rows"], r
        assert api(f"/api/proposals/{card['id']}/confirm", {})["proposal"]["status"] == "done"
        r = api("/api/chat", {"message": "주간회의 준비물 뭐였지?"})
        assert [a["tool"] for a in r["activity"]] == ["list_events", "wiki_read"] and "노트북" in r["reply"], r
        api("/api/chat", {"message": "내일 일정 알려줘"})
        stats = llm_stats(llm_port)
        assert stats["rules_in_prompt"] and "스크럼은 항상 15분" in stats["last_rules"], stats
        check = subprocess.run([sys.executable, os.path.join(ROOT, "secretary-1.py"), "--config", cfg_path, "--check"],
                               env=ENV, capture_output=True, text=True, timeout=60)
        assert "학습 규칙 : 1개" in check.stdout and "일정 위키 : 1개" in check.stdout, check.stdout
        # 모델 드롭다운: 서버 목록 → 바꾸기 → 다음 요청부터 그 모델 · config.json 에 저장
        assert api("/api/models")["models"] == ["사내-LLM", "qwen3-32b"]
        assert api("/api/model", {"model": "qwen3-32b"})["saved"] is True
        api("/api/chat", {"message": "내일 일정 알려줘"})
        assert llm_stats(llm_port)["last_model"] == "qwen3-32b"
        with open(cfg_path, encoding="utf-8") as f:
            assert json.load(f)["llm"]["model"] == "qwen3-32b"
        print(f"[{mode}] ok · llm 요청 {stats['requests']}회 (tools 포함 {stats['with_tools']}회)")
        print("   --check ▸ " + "\n   --check ▸ ".join(check.stdout.strip().splitlines()[2:]))
    finally:
        app.terminate()
        fake.terminate()


NAVY, LIME, GREY = "rgb(0, 35, 65)", "rgb(106, 186, 35)", "rgb(165, 170, 174)"
PRIME, PRIME_INK = "rgb(31, 80, 122)", "rgb(242, 242, 243)"  # TE v2: 네이비 주색 · 라임 강조
ENC1 = "rgb(117, 161, 199)"  # 노브 ① = Terminal–1 인코더 ① 파랑
BLACK_PANEL, LIGHT_PANEL = "rgb(11, 11, 11)", "rgb(242, 242, 243)"


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
            assert css(p, ".send", "backgroundColor") == PRIME  # 주 버튼은 네이비
            cap = "(s) => getComputedStyle(document.querySelector(s), '::before').backgroundColor"
            assert p.evaluate(cap, ".key.k1 .dial") == ENC1 and p.evaluate(cap, ".key.k2 .dial") == LIME  # 노브 캡 = ①파랑 ②라임 ③흰색 ④회색
            assert css(p, ".lbl b", "backgroundColor") == PRIME and p.locator(".lbl").count() == 4  # 01~04 번호 라벨
            assert p.locator("#next-count svg.seg").count() == 1 and p.locator("#clock-time svg.seg").count() == 1
            assert p.locator("#mascot svg .ms").count() == 1 and p.locator("#mascot svg .mled").count() == 1  # 마스코트
            assert p.locator(".track .ev").count() >= 6 and p.locator(".track .nowline").count() == 1
            assert p.inner_text("#next-title") != "self-test"
            # 도스 픽셀 폰트: 내장 WOFF 가 실제로 로드되고 전체에 쓰인다
            assert p.evaluate("[...document.fonts].some(f => f.family.replace(/\"/g, '') === 'Secretary1DOS' && f.status === 'loaded')")
            assert css(p, "body", "fontFamily").startswith(("Secretary1DOS", '"Secretary1DOS"'))
            assert css(p, "#msg", "fontFamily") == css(p, ".key.k1", "fontFamily") == css(p, "body", "fontFamily")
            stamp_flow(p)
            p.wait_for_function("!document.querySelector('.bit')")  # 도장 파편이 다 사라진 뒤에
            wide_boxes = p.evaluate("""() => [...document.querySelectorAll('.device, .bar, .lcd, .overview, .log, .keys, .input, .foot')]
                .filter(e => e.scrollWidth > e.clientWidth + 1).map(e => e.className)""")
            assert not wide_boxes, wide_boxes  # 글자가 커져도 가로로 넘치지 않는다
            assert re.fullmatch(r"\d\d:\d\d", p.get_attribute(".msg.user", "data-ts"))  # 로그 줄: 시각 · 기호 · 내용
            # 아래 줄: 로컬 저장 · 모델 드롭다운
            assert p.inner_text("#foot-info") == "로컬 저장"
            p.wait_for_function("document.querySelectorAll('#model option').length === 2")
            p.select_option("#model", "qwen3-32b")
            p.wait_for_function("[...document.querySelectorAll('.sys')].some(e => e.textContent.includes('모델 → qwen3-32b'))")
            assert llm_stats(llm_port)["requests"] >= 1
            say(p, "내일 일정 알려줘")
            assert llm_stats(llm_port)["last_model"] == "qwen3-32b"
            assert css(p, ".card.done .seal", "borderTopColor") == LIME
            p.screenshot(path=os.path.join(OUT, "secretary-1-compact.png"))

            # 오늘 일정 서랍
            p.click("#day-count")
            p.wait_for_selector("#day-drawer:not([hidden])")
            p.wait_for_selector("#day-drawer .chip")  # 목록은 서랍이 열린 뒤 따로 받아 온다
            assert p.locator("#day-drawer .chip").count() == 1
            assert p.locator("#daylist .row").count() >= 6
            p.wait_for_timeout(500)
            p.screenshot(path=os.path.join(OUT, "secretary-1-day.png"))
            p.click("#next")
            p.wait_for_function("document.querySelector('#day-label').textContent === 'tomorrow'")
            p.keyboard.press("Escape")
            p.wait_for_selector("#day-drawer", state="hidden")

            # 학습: 명령어 → 대화 → 서랍에서 직접
            say(p, "/학습 스크럼은 항상 15분")
            assert "학습했습니다" in p.locator(".msg.bot").last.inner_text()
            assert p.inner_text("#mem-count") == "1"
            say(p, "앞으로 코드리뷰는 30분으로 잡아 기억해")
            p.wait_for_selector(".card.pending[data-kind='rule']")
            assert p.inner_text("#mem-count") == "1"  # 대화로 배운 규칙은 확정해야 저장
            p.click(".card.pending .okb")
            p.wait_for_function("document.querySelector('#mem-count').textContent === '2'")
            p.wait_for_selector(".plus1")
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
            p.screenshot(path=os.path.join(OUT, "secretary-1-learn.png"))
            p.click("#rules .rule >> nth=0 >> .x")
            p.wait_for_function("document.querySelectorAll('#rules .rule').length === 2")
            assert p.inner_text("#mem-count") == "2"
            p.keyboard.press("Escape")

            # 일정 위키: 대화로 정리 → 확정 → 다음 일정 칸 [위키] · 일정 서랍 W · Alt+W · 질문
            say(p, "주간회의 준비물은 노트북이랑 지난주 회의록, 안건은 분기 목표 점검이야 정리해줘")
            p.wait_for_selector(".card.pending[data-kind='wiki']")
            card = p.inner_text(".card.pending")
            assert "노트북 · 지난주 회의록" in card and "분기 목표 점검" in card, card
            p.click(".card.pending .okb")
            p.wait_for_selector("#next-wiki:not([hidden])")
            p.click("#next-wiki")
            p.wait_for_selector("#wiki-body dl")  # 서랍이 열린 뒤 위키를 받아 온다
            body = p.inner_text("#wiki-body")
            assert "노트북" in body and "분기 목표 점검" in body and "원문 기록 1개" in body, body
            p.wait_for_timeout(450)
            p.screenshot(path=os.path.join(OUT, "secretary-1-wiki.png"))
            p.click("#wiki-body summary")  # 원문 기록 펼치기 → 지우기 (정리된 내용은 그대로)
            p.once("dialog", lambda d: d.accept())
            p.click("#wiki-body .clr")
            p.wait_for_function("!document.querySelector('#wiki-body details')")
            assert "노트북" in p.inner_text("#wiki-body")
            p.keyboard.press("Escape")
            p.wait_for_selector("#wiki-drawer", state="hidden")
            p.keyboard.press("Alt+w")
            p.wait_for_selector("#wiki-body dl")
            p.click("#wiki-body .wacts button >> text=직접 고치기")  # 서랍에서 직접 고치기 → Ctrl+Enter 저장
            p.fill("#wiki-body textarea[name=prep]", "노트북\n회의실 예약")
            p.press("#wiki-body textarea[name=prep]", "Control+Enter")
            p.wait_for_function("document.querySelector('#wiki-body dl') && document.querySelector('#wiki-body').textContent.includes('회의실 예약')")
            assert "지난주 회의록" not in p.inner_text("#wiki-body")
            p.click("#wiki-back")
            p.wait_for_selector("#wiki-body .wrow")
            p.keyboard.press("Escape")
            p.click("#day-count")
            p.wait_for_selector("#daylist .row.haswiki .wb")
            p.click("#daylist .row.haswiki")
            p.wait_for_selector("#wiki-body dl")
            p.keyboard.press("Escape")
            say(p, "주간회의 준비물 뭐였지?")
            assert "노트북" in p.locator(".msg.bot").last.inner_text()

            # 제안 → Esc 취소(구기기) → Ctrl+Enter 확정 → 'ㅇㅇ' 확정
            say(p, "월요일 오전 기획 회의 잡아줘")
            p.wait_for_selector(".card.pending")
            assert css(p, ".card.pending .okb", "color") == PRIME_INK and css(p, ".card.pending .okb", "backgroundColor") == PRIME
            p.wait_for_timeout(750)
            p.screenshot(path=os.path.join(OUT, "secretary-1-pending.png"))
            p.keyboard.press("Escape")
            p.wait_for_selector(".card.cancelled")
            done0 = p.locator(".card.done").count()  # 앞에서 확정한 카드 (일정 · 학습 · 위키)
            say(p, "월요일 오전 기획 회의 잡아줘")
            p.wait_for_selector(".card.pending")
            p.keyboard.press("Control+Enter")
            p.wait_for_function(f"document.querySelectorAll('.card.done').length === {done0 + 1}")
            say(p, "내일 오전 회의 잡아줘")
            p.wait_for_selector(".card.pending")
            say(p, "ㅇㅇ")
            p.wait_for_function("document.querySelectorAll('.card.pending').length === 0")
            assert p.locator(".card.done").count() == done0 + 2
            p.wait_for_selector(".card.done .undo")  # 방금 확정한 것 되돌리기 (Ctrl+Z)
            p.keyboard.press("Control+z")
            p.wait_for_selector(".card.undone")
            assert p.locator(".card.done").count() == done0 + 1

            # Alt+1 빠른 키, /알림 → 앱 안 알림
            n = bots(p)
            p.keyboard.press("Alt+2")
            p.wait_for_function(f"document.querySelectorAll('.msg.bot').length > {n}")
            say(p, "/알림")
            p.wait_for_selector(".toast.show")
            assert "알림 테스트" in p.inner_text("#toast-text")
            assert p.locator(".act.alert").count() >= 1
            p.wait_for_timeout(500)
            p.screenshot(path=os.path.join(OUT, "secretary-1-alert.png"))

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
            assert s.inner_text("#next-k").lower() == "now", s.inner_text("#next-k")  # 화면엔 대문자로
            s.wait_for_timeout(400)
            s.screenshot(path=os.path.join(OUT, "secretary-1-now.png"))

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
            assert css(lt, ".send", "backgroundColor") == PRIME and css(lt, ".lbl b", "backgroundColor") == PRIME  # 라이트도 네이비 주색
            assert css(lt, "#next-count .seg .on", "fill") == PRIME_INK  # 화면(LCD) 숫자는 라이트에서도 흰색
            stamp_flow(lt)
            assert css(lt, ".card.done .seal", "borderTopColor") == PRIME  # 라이트의 확정 도장은 네이비
            lt.screenshot(path=os.path.join(OUT, "secretary-1-light.png"))
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
