# -*- coding: utf-8 -*-
"""Report–1 단위 · 통합 테스트 (표준 라이브러리 unittest). git 은 진짜로, 사내 LLM · Secretary–1 은 가짜로."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import importlib.util  # noqa: E402

TMP = tempfile.mkdtemp(prefix="report1-test-")
os.environ["REPORT_HOME"] = os.path.join(TMP, "home")
os.environ["GIT_CONFIG_GLOBAL"] = os.path.join(TMP, "gitconfig")   # 이 PC 의 전역 git 설정(이메일)에 흔들리지 않게
os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
os.environ["XDG_CONFIG_HOME"] = os.path.join(TMP, "xdg")           # 이 PC 의 OpenCode 설정을 읽지 않게
os.environ["XDG_DATA_HOME"] = os.path.join(TMP, "xdg-data")
for k in ("REPORT_BASE_URL", "REPORT_API_KEY", "REPORT_MODEL", "OPENCODE_CONFIG"):
    os.environ.pop(k, None)
open(os.environ["GIT_CONFIG_GLOBAL"], "w").close()

# report-1.py 는 이름에 '-' 가 있어 import 문으로는 못 부른다 → 파일에서 직접 읽어 'report' 모듈로 등록
_spec = importlib.util.spec_from_file_location("report", os.path.join(ROOT, "report-1.py"))
rp = importlib.util.module_from_spec(_spec)
sys.modules["report"] = rp
_spec.loader.exec_module(rp)
from fake_llm_server import FakeLLM  # noqa: E402

GIT_OK = shutil.which("git") is not None


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


def git(repo, *args, when=None, email=None):
    env = dict(os.environ)
    if when:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = when
    cmd = ["git", "-C", repo]
    if email:
        cmd += ["-c", f"user.email={email}", "-c", "user.name=someone"]
    subprocess.run(cmd + list(args), check=True, capture_output=True, env=env)


def make_repo(path, email="me@example.com"):
    os.makedirs(path)
    git(path, "init", "-q")
    if email:
        git(path, "config", "user.email", email)
    git(path, "config", "user.name", "Me")
    return path


def commit(repo, msg, when, email=None):
    with open(os.path.join(repo, "f.txt"), "a", encoding="utf-8") as f:
        f.write(msg + "\n")
    git(repo, "add", "f.txt")
    git(repo, "commit", "-q", "-m", msg, when=when, email=email)


def fake_secretary(folder, events, fmt=1, extra=None, raw=None):
    """Secretary–1 의 공개 명령(--export-events) 흉내 — 받은 기간 안의 일정만 돌려준다"""
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "secretary-1.py")
    body = raw if raw is not None else (
        "import json, sys\n"
        "a = sys.argv\n"
        "f, t = a[a.index('--from') + 1], a[a.index('--to') + 1]\n"
        f"evs = {json.dumps(events, ensure_ascii=False)!r}\n"
        "evs = [e for e in json.loads(evs) if f <= e['start'][:10] <= t]\n"
        f"out = dict({{'app': 'secretary-1', 'version': '0.6.0', 'format': {fmt}, 'backend': 'local', 'events': evs}}, **{extra or {}!r})\n"
        "sys.stdout.buffer.write((json.dumps(out, ensure_ascii=False) + '\\n').encode('utf-8'))\n")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    return path


def base_cfg(home, **over):
    cfg = rp.deep_merge(rp.DEFAULT_CONFIG, over)
    cfg["_dir"] = home
    rp.validate_config(cfg)
    return cfg


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(dir=TMP)
        self.home = os.path.join(self.dir, "home")
        os.makedirs(self.home)


# ─────────────────────────────────────────────────────────────── 기간

class Periods(unittest.TestCase):
    def test_week_kinds(self):
        sat = date(2026, 9, 26)
        this = rp.make_period("this", sat)
        self.assertEqual((this.start, this.end, this.next_start, this.next_end),
                         (date(2026, 9, 21), date(2026, 9, 27), date(2026, 9, 28), date(2026, 10, 4)))
        self.assertEqual((this.key, this.label), ("2026-W39", "2026 W39 · 9/21 – 9/27"))
        last = rp.make_period("last", sat)
        self.assertEqual((last.start, last.end, last.key), (date(2026, 9, 14), date(2026, 9, 20), "2026-W38"))
        two = rp.make_period("2w", sat)
        self.assertEqual((two.start, two.end, two.key), (date(2026, 9, 14), date(2026, 9, 27), "2026-W38+39"))

    def test_monday_and_month(self):
        self.assertEqual(rp.make_period("this", date(2026, 9, 21)).start, date(2026, 9, 21))
        dec = rp.make_period("month", date(2026, 12, 15))
        self.assertEqual((dec.start, dec.end, dec.key), (date(2026, 12, 1), date(2026, 12, 31), "2026-12"))
        with self.assertRaises(ValueError):
            rp.make_period("year")


# ─────────────────────────────────────────────────────────────── 커밋

@unittest.skipUnless(GIT_OK, "git 이 없음")
class GitSource(Base):
    def cfg(self, **git_over):
        return base_cfg(self.home, sources={"git": dict({"roots": [self.dir]}, **git_over)})

    def test_only_my_commits_in_range(self):
        api = make_repo(os.path.join(self.dir, "api-server"))
        commit(api, "로그인 토큰 만료 처리", "2026-09-22T10:00:00")
        commit(api, "남의 커밋", "2026-09-22T11:00:00", email="other@example.com")
        commit(api, "지난주 커밋", "2026-09-18T11:00:00")   # 맨 위 커밋이 더 옛날 — git --since 만 믿으면 이번 주 커밋까지 사라진다
        items, st = rp.GitCollector(self.cfg()).collect(date(2026, 9, 21), date(2026, 9, 27))
        self.assertEqual([c["title"] for c in items], ["로그인 토큰 만료 처리"])
        self.assertEqual(items[0]["repo"], "api-server")
        self.assertEqual(items[0]["when"], "2026-09-22T10:00")
        self.assertTrue(st.startswith("OK · 1건 · 저장소 1개"), st)

    def test_unknown_author_is_skipped_not_guessed(self):
        """작성자 이메일을 모르면 가져오지 않는다 — 남의 커밋이 내 실적으로 들어가지 않게"""
        web = make_repo(os.path.join(self.dir, "web"), email=None)
        commit(web, "대시보드", "2026-09-22T10:00:00", email="me@example.com")
        items, st = rp.GitCollector(self.cfg()).collect(date(2026, 9, 21), date(2026, 9, 27))
        self.assertEqual(items, [])
        self.assertIn("작성자 이메일을 모르는 저장소 1개", st)
        items, _ = rp.GitCollector(self.cfg(authors=["ME@example.com"])).collect(date(2026, 9, 21), date(2026, 9, 27))
        self.assertEqual([c["title"] for c in items], ["대시보드"])   # 설정한 이메일 · 대소문자 무시

    def test_branches_depth_and_dedupe(self):
        deep = make_repo(os.path.join(self.dir, "team", "svc"))
        commit(deep, "기본 가지", "2026-09-22T09:00:00")
        git(deep, "checkout", "-q", "-b", "feature")
        commit(deep, "기능 가지", "2026-09-23T09:00:00")
        git(deep, "stash", "list")
        items, _ = rp.GitCollector(self.cfg()).collect(date(2026, 9, 21), date(2026, 9, 27))
        self.assertEqual([c["title"] for c in items], ["기본 가지", "기능 가지"])
        items, st = rp.GitCollector(self.cfg(depth=0)).collect(date(2026, 9, 21), date(2026, 9, 27))
        self.assertEqual((items, st), ([], "저장소를 찾지 못했습니다 (sources.git.roots · depth)"))

    def test_no_roots(self):
        items, st = rp.GitCollector(base_cfg(self.home)).collect(date(2026, 9, 21), date(2026, 9, 27))
        self.assertEqual((items, st), ([], "폴더 미설정 → sources.git.roots"))


# ─────────────────────────────────────────────────────────────── 일정 (Secretary–1 공개 명령)

EVENTS = [{"id": "L1", "title": "주간회의", "start": "2026-09-21T10:00", "end": "2026-09-21T11:00", "location": "3A"},
          {"id": "L2", "title": "분기 계획 리뷰", "start": "2026-09-29T15:00", "end": "2026-09-29T16:00", "location": ""}]


class CalendarSource(Base):
    def collector(self, path):
        return rp.CalendarCollector(base_cfg(self.home, sources={"calendar": {"secretary": path}}))

    def test_reads_public_command(self):
        path = fake_secretary(self.dir, EVENTS)
        evs, st = self.collector(path).collect(date(2026, 9, 21), date(2026, 10, 4))
        self.assertEqual([e["title"] for e in evs], ["주간회의", "분기 계획 리뷰"])
        self.assertTrue(st.startswith("OK · 2건 · Secretary–1 0.6.0"), st)

    def test_missing_unknown_format_error_and_garbage(self):
        d0, d1 = date(2026, 9, 21), date(2026, 9, 27)
        self.assertEqual(self.collector(os.path.join(self.dir, "none.py")).collect(d0, d1),
                         ([], "Secretary–1 이 없습니다 → 일정 없이"))
        evs, st = self.collector(fake_secretary(os.path.join(self.dir, "v2"), EVENTS, fmt=2)).collect(d0, d1)
        self.assertEqual(evs, [])
        self.assertIn("형식(2)을 모릅니다", st)
        evs, st = self.collector(fake_secretary(os.path.join(self.dir, "err"), [], extra={"error": "캘린더 연결 실패"})).collect(d0, d1)
        self.assertEqual((evs, st), ([], "Secretary–1: 캘린더 연결 실패"))
        evs, st = self.collector(fake_secretary(os.path.join(self.dir, "junk"), [], raw="print('hello')\n")).collect(d0, d1)
        self.assertEqual(evs, [])
        self.assertIn("답을 읽지 못했습니다", st)

    def test_default_is_sibling_secretary(self):
        self.assertEqual(rp.CalendarCollector.default_path(),
                         os.path.join(os.path.dirname(ROOT), "secretary-1", "secretary-1.py"))


# ─────────────────────────────────────────────────────────────── 일지 · 저장

class JournalStore(Base):
    def test_add_between_remove(self):
        j = rp.Journal(os.path.join(self.home, "journal.json"))
        a = j.add("  온보딩 문서\n초안 작성  ", date(2026, 9, 22))
        b = j.add("회의록 정리", date(2026, 9, 29))
        self.assertEqual((a["id"], a["text"], b["id"]), ("n1", "온보딩 문서 초안 작성", "n2"))
        self.assertEqual([x["id"] for x in j.between(date(2026, 9, 21), date(2026, 9, 27))], ["n1"])
        j.remove("n1")
        self.assertEqual([x["id"] for x in j.all()], ["n2"])
        self.assertEqual(j.add("다음", date(2026, 9, 30))["id"], "n3")
        with self.assertRaises(ValueError):
            j.add("   ")
        with self.assertRaises(ValueError):
            j.add("가" * 301)
        with self.assertRaises(KeyError):
            j.remove("n99")

    def test_broken_file_is_backed_up(self):
        path = os.path.join(self.home, "journal.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{깨짐")
        j = rp.Journal(path)
        self.assertEqual(j.all(), [])
        self.assertIn("새로 시작합니다", j.doc.error)
        self.assertTrue(os.path.exists(path + ".broken"))
        j.add("다시 시작")
        with open(path, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["version"], 1)

    def test_newer_version_is_read_only(self):
        path = os.path.join(self.home, "journal.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"version": 99, "entries": [{"id": "n1", "date": "2026-09-22", "text": "미래"}]}, f)
        j = rp.Journal(path)
        self.assertEqual([x["text"] for x in j.all()], ["미래"])
        with self.assertRaises(OSError):
            j.add("덮어쓰기")
        with open(path, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["version"], 99)

    def test_report_store_save_restore(self):
        st = rp.ReportStore(os.path.join(self.home, "reports"))
        self.assertIsNone(st.save("2026-W39", {"label": "첫", "confirmed": "a"}))
        before = st.save("2026-W39", {"label": "둘", "confirmed": "b"})
        self.assertEqual(before["label"], "첫")
        st.restore("2026-W39", before)
        self.assertEqual(st.get("2026-W39")["label"], "첫")
        st.restore("2026-W39", None)
        self.assertIsNone(st.get("2026-W39"))
        with self.assertRaises(ValueError):
            st.path("../x")


# ─────────────────────────────────────────────────────────────── 근거 검사 · 초안

def known():
    S = rp.Source
    return {s.id: s for s in [S("c1", "commit", "토큰 만료 처리", "2026-09-22T10:00", "api-server", "a1b2c3d"),
                              S("c2", "commit", "로그 정리", "2026-09-23T10:00", "api-server", "b2c3d4e"),
                              S("e1", "event", "주간회의", "2026-09-21T10:00", "3A", "L1"),
                              S("n3", "note", "온보딩 문서 초안", "2026-09-22T00:00"),
                              S("f1", "plan", "분기 계획 리뷰", "2026-09-29T15:00", "", "L2")]}


class Judge(unittest.TestCase):
    def test_states(self):
        k, L = known(), rp.Line
        self.assertEqual(rp.judge(L(0, "처리", ["c1", "C2", "zz"]), k).refs, ["c1", "c2"])
        self.assertEqual(rp.judge(L(0, "지어낸 성과", []), k).state, "err")
        self.assertEqual(rp.judge(L(0, "다음 주 일을 실적으로", ["f1"]), k).state, "err")   # 실적엔 이번 기간 근거만
        self.assertEqual(rp.judge(L(1, "다음 주 계획", ["f1"]), k).state, "ok")
        self.assertEqual(rp.judge(L(1, "근거 없는 계획", []), k).state, "plan")
        self.assertEqual(rp.judge(L(2, "근거 없는 이슈", []), k).state, "err")
        self.assertEqual(rp.judge(L(0, "사람이 쓴 줄", [], "user"), k).state, "user")

    def test_basic_draft_every_line_has_refs(self):
        lines = rp.basic_draft(known(), 8)
        self.assertEqual([(x.section, x.text, x.refs) for x in lines], [
            (0, "온보딩 문서 초안", ["n3"]), (0, "api-server: 로그 정리 외 1건", ["c1", "c2"]),
            (0, "주간회의", ["e1"]), (1, "분기 계획 리뷰 (9/29)", ["f1"])])
        self.assertTrue(all(x.state == "ok" for x in lines))
        self.assertEqual(len(rp.basic_draft(known(), 1)), 2)   # 칸마다 max_lines

    def test_parse_draft_shapes(self):
        good = '{"sections": [{"lines": [{"text": "토큰 처리", "refs": ["c1"]}]}, {"lines": []}, {"lines": []}]}'
        self.assertEqual([(x.section, x.text, x.refs) for x in rp.parse_draft(good, 8)], [(0, "토큰 처리", ["c1"])])
        fenced = "정리했습니다.\n```json\n" + good + "\n```\n확인 부탁드립니다."
        self.assertEqual(len(rp.parse_draft("<think>음</think>" + fenced, 8)), 1)
        alt = '{"done": [{"text": "a", "refs": "c1, c2"}], "next": ["b"], "issues": []}'
        self.assertEqual([(x.section, x.refs) for x in rp.parse_draft(alt, 8)], [(0, ["c1", "c2"]), (1, [])])
        for bad in ("이번 주에는 많은 일을 하셨네요", '{"foo": 1}', "{깨진"):
            with self.assertRaises(ValueError):
                rp.parse_draft(bad, 8)

    def test_render_text(self):
        p = rp.make_period("this", date(2026, 9, 26))
        lines = [rp.Line(0, "토큰 처리", ["c1"], "llm", "ok"), rp.Line(1, "리뷰 준비", ["f1"], "llm", "ok")]
        text = rp.render_text(p, ["금주 실적", "차주 계획", "이슈"], lines, known())
        self.assertEqual(text, "■ 금주 실적 (9/21 – 9/27)\n - 토큰 처리\n\n■ 차주 계획 (9/28 – 10/4)\n - 리뷰 준비\n\n■ 이슈\n - 없음\n")
        with_refs = rp.render_text(p, ["금주 실적", "차주 계획", "이슈"], lines, known(), with_refs=True)
        self.assertIn(" - 토큰 처리 (api-server a1b2c3d)", with_refs)
        self.assertIn(" - 리뷰 준비 (다음 일정 9/29)", with_refs)

    def test_prompt_keeps_rules_and_only_given_sources(self):
        p = rp.make_period("this", date(2026, 9, 26))
        k = known()
        del k["c2"]
        msgs = rp.build_messages(p, k, ["금주 실적", "차주 계획", "이슈"], 1, "brief", 5, "김개발")
        self.assertIn("지어내지 않는다", msgs[0]["content"])
        self.assertIn("[c1] 2026-09-22 커밋 · api-server · 토큰 만료 처리", msgs[1]["content"])
        self.assertNotIn("로그 정리", msgs[1]["content"])


# ─────────────────────────────────────────────────────────────── 앱 (HTTP)

class Http(Base):
    def setUp(self):
        super().setUp()
        self.llm = FakeLLM()
        mon = date.today() - timedelta(days=date.today().weekday())
        evs = [{"id": "L1", "title": "주간회의", "start": f"{mon}T10:00", "end": f"{mon}T11:00", "location": "3A"},
               {"id": "L2", "title": "분기 계획 리뷰", "start": f"{mon + timedelta(days=8)}T15:00", "end": "", "location": ""}]
        sec = fake_secretary(os.path.join(self.dir, "sec"), evs)
        self.cfg = base_cfg(self.home, llm={"base_url": self.llm.url, "model": "fake-model"},
                            sources={"calendar": {"secretary": sec}}, idle_exit_min=0)
        self.app = rp.App(self.cfg, os.path.join(self.home, "config.json"))
        self.app.journal.add("온보딩 문서 초안 작성")
        self.app.httpd, self.app.port = rp.bind_server(0, rp.make_handler(self.app))
        self.app.allowed_hosts = {f"127.0.0.1:{self.app.port}", f"localhost:{self.app.port}"}
        import threading
        threading.Thread(target=self.app.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.app.httpd.shutdown()
        self.app.httpd.server_close()
        self.llm.close()

    def call(self, path, body=None, token=True, host=None, ctype="application/json"):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.app.url.rstrip("/") + path, data=data, method="POST" if data is not None else "GET")
        if token:
            req.add_header("X-Report-Token", self.app.token)
        if host:
            req.add_header("Host", host)
        if data is not None:
            req.add_header("Content-Type", ctype)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(req, timeout=30) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8"))

    def test_binds_localhost_and_guards(self):
        self.assertEqual(self.app.httpd.server_address[0], "127.0.0.1")
        self.assertEqual(self.call("/api/state", token=False)[0], 401)
        self.assertEqual(self.call("/api/state", host="evil.example:80")[0], 403)
        self.assertEqual(self.call("/api/draft", {"period": "this"}, ctype="text/plain")[0], 415)
        self.assertEqual(self.call("/api/ping", token=False), (200, {"app": "report-1", "version": rp.VERSION}))

    def test_sources_draft_confirm_undo(self):
        code, src = self.call("/api/sources?period=this")
        self.assertEqual(code, 200)
        kinds = sorted(x["kind"] for x in src["items"])
        self.assertEqual(kinds, ["event", "note", "plan"])
        code, d = self.call("/api/draft", {"period": "this"})
        self.assertEqual((code, d["mode"], d["error"]), (200, "llm", ""))
        self.assertTrue(all(x["state"] == "ok" for x in d["lines"]), d["lines"])
        self.assertIn("온보딩 문서 초안 작성 완료", d["text"])
        code, c = self.call("/api/confirm", {"period": "this", "lines": d["lines"]})
        self.assertEqual(code, 200, c)
        self.assertEqual(self.call("/api/reports")[1]["reports"][0]["key"], c["key"])
        self.assertEqual(self.call(f"/api/reports/{c['key']}")[1]["text"], c["text"])
        self.assertEqual(self.call("/api/undo", {"key": c["key"]})[0], 200)
        self.assertEqual(self.call("/api/reports")[1]["reports"], [])
        self.assertEqual(self.call("/api/undo", {"key": c["key"]})[0], 400)   # 두 번은 안 됨

    def test_invented_achievement_blocks_confirm_until_a_person_owns_it(self):
        self.llm.mode = "lie"
        code, d = self.call("/api/draft", {"period": "this"})
        bad = [x for x in d["lines"] if x["state"] == "err"]
        self.assertEqual([x["text"] for x in bad], ["성과 30% 향상"])
        code, c = self.call("/api/confirm", {"period": "this", "lines": d["lines"]})
        self.assertEqual(code, 400)
        self.assertIn("근거 없는 줄이 1개", c["error"])
        forged = [dict(x, state="ok") for x in d["lines"]]   # 화면이 상태를 바꿔 보내도 서버가 다시 판정한다
        self.assertEqual(self.call("/api/confirm", {"period": "this", "lines": forged})[0], 400)
        owned = [dict(x, origin="user") if x["state"] == "err" else x for x in d["lines"]]
        code, c = self.call("/api/confirm", {"period": "this", "lines": owned})
        self.assertEqual(code, 200, c)

    def test_excluded_sources_are_not_sent_or_citable(self):
        _, src = self.call("/api/sources?period=this")
        note = next(x for x in src["items"] if x["kind"] == "note")
        _, d = self.call("/api/draft", {"period": "this", "exclude": [note["id"]]})
        sent = json.dumps(self.llm.requests[-1], ensure_ascii=False)
        self.assertNotIn(note["title"], sent)
        self.assertNotIn(note["id"], [r for x in d["lines"] for r in x["refs"]])
        _, pv = self.call("/api/preview", {"period": "this", "exclude": [note["id"]],
                                           "lines": [{"section": 0, "text": "일지 인용", "refs": [note["id"]], "origin": "llm"}]})
        self.assertEqual(pv["lines"][0]["state"], "err")

    def test_llm_retry_and_fallback(self):
        self.llm.mode = "garbage"
        _, d = self.call("/api/draft", {"period": "this"})
        self.assertEqual((d["mode"], len(self.llm.requests)), ("llm", 2))
        self.llm.mode = "fence"
        self.assertEqual(self.call("/api/draft", {"period": "this"})[1]["mode"], "llm")
        self.llm.mode = "error"
        _, d = self.call("/api/draft", {"period": "this"})
        self.assertEqual(d["mode"], "basic")
        self.assertIn("LLM 초안 실패 → 기본 초안으로", d["error"])
        self.assertTrue(d["lines"] and all(x["state"] == "ok" for x in d["lines"]))

    def test_journal_api(self):
        code, j = self.call("/api/journal", {"text": "회의록 정리"})
        self.assertEqual((code, j["item"]["text"]), (200, "회의록 정리"))
        _, src = self.call("/api/sources?period=this")
        self.assertIn("회의록 정리", [x["title"] for x in src["items"]])
        self.assertEqual(self.call(f"/api/journal/{j['item']['id']}/delete", {})[0], 200)
        self.assertEqual(self.call("/api/journal", {"text": ""})[0], 400)


# ─────────────────────────────────────────────────────────────── 설정 · 명령

def run_cli(*args, env=None):
    e = dict(os.environ, PYTHONIOENCODING="utf-8", **(env or {}))
    r = subprocess.run([sys.executable, os.path.join(ROOT, "report-1.py"), *args], capture_output=True, timeout=120, env=e)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")


class Cli(Base):
    def env(self):
        return {"REPORT_HOME": self.home}

    def test_version_and_data_dir(self):
        code, out, _ = run_cli("--version")
        self.assertEqual((code, out.strip()), (0, f"Report-1 {rp.VERSION}"))
        self.assertEqual(rp.default_config_path(), os.path.join(os.environ["REPORT_HOME"], "config.json"))

    def test_set_refuses_raw_key_and_unknown_keys(self):
        code, out, _ = run_cli("--set", "llm.api_key=sk-plain-value-000", env=self.env())
        self.assertEqual(code, 2)
        self.assertIn("API 키는 --set 으로 넣지 않습니다", out)
        self.assertNotIn("sk-plain-value-000", out)
        code, out, _ = run_cli("--set", "llm.api_key={env:CORP_KEY}", "--set", 'sources.git.roots=["C:/work"]', env=self.env())
        self.assertEqual(code, 0, out)
        self.assertIn("{env:CORP_KEY} 참조", out)
        self.assertEqual(run_cli("--set", "nope.key=1", env=self.env())[0], 2)
        code, out, _ = run_cli("--set", "report.sections=[\"하나\"]", env=self.env())
        self.assertEqual(code, 2)
        self.assertIn("되돌렸습니다", out)
        with open(os.path.join(self.home, "config.json"), encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved["sources"]["git"]["roots"], ["C:/work"])
        code, out, _ = run_cli("--set", "sources.git.roots=C:\\work; D:\\proj", "--set", "sources.git.authors=Me@Example.com",
                               env=self.env())   # 셸마다 따옴표가 달라서 목록 칸은 ; 로 나눈 글도 받는다
        self.assertEqual(code, 0, out)
        with open(os.path.join(self.home, "config.json"), encoding="utf-8") as f:
            git = json.load(f)["sources"]["git"]
        self.assertEqual((git["roots"], git["authors"]), (["C:\\work", "D:\\proj"], ["Me@Example.com"]))
        self.assertEqual(run_cli("--set", "sources.git.roots=", env=self.env())[0], 0)
        self.assertEqual(saved["report"]["sections"], rp.DEFAULT_CONFIG["report"]["sections"])

    def test_draft_basic_to_stdout(self):
        rp.Journal(os.path.join(self.home, "journal.json")).add("주간보고 양식 정리")
        code, out, err = run_cli("--draft", "--basic", env=dict(self.env(), REPORT_HOME=self.home))
        self.assertEqual(code, 0, err)
        self.assertTrue(out.startswith("■ 금주 실적 ("), out)
        self.assertIn(" - 주간보고 양식 정리\n", out)
        self.assertNotIn("[", out.splitlines()[1])   # 로그는 표준 오류로

    def test_check_without_llm_is_ok(self):
        code, out, _ = run_cli("--check", env=self.env())
        self.assertEqual(code, 0, out)
        self.assertIn("LLM       : 미설정 → 기본 초안", out)
        self.assertEqual(out.strip().splitlines()[-1], "결과: OK")

    def test_setup_reads_opencode_and_asks_for_roots(self):
        oc = os.path.join(self.dir, "oc")
        os.makedirs(oc)
        with open(os.path.join(oc, "opencode.jsonc"), "w", encoding="utf-8") as f:
            f.write('{\n // 사내\n "provider": {"corp": {"npm": "@ai-sdk/openai-compatible", '
                    '"options": {"baseURL": "https://llm.corp.local/v1", "apiKey": "{env:CORP_KEY}"}, '
                    '"models": {"qwen3": {}}}},\n}\n')
        code, out, _ = run_cli("--setup", env=dict(self.env(), OPENCODE_CONFIG=os.path.join(oc, "opencode.jsonc")))
        self.assertEqual(code, 3, out)
        self.assertIn("provider 'corp'", out)
        self.assertIn("커밋을 찾을 작업 폴더", out.splitlines()[-1])
        with open(os.path.join(self.home, "config.json"), encoding="utf-8") as f:
            llm = json.load(f)["llm"]
        self.assertEqual((llm["base_url"], llm["model"], llm["api_key"]), ("https://llm.corp.local/v1", "qwen3", "{env:CORP_KEY}"))

    def test_setup_needs_choice(self):
        oc = os.path.join(self.dir, "oc2")
        os.makedirs(oc)
        with open(os.path.join(oc, "opencode.json"), "w", encoding="utf-8") as f:
            json.dump({"provider": {"a": {"options": {"baseURL": "https://a.local/v1"}, "models": {"m": {}}},
                                    "b": {"options": {"baseURL": "https://b.local/v1"}, "models": {"m": {}}}}}, f)
        code, out, _ = run_cli("--setup", env=dict(self.env(), OPENCODE_CONFIG=os.path.join(oc, "opencode.json")))
        self.assertEqual(code, 3)
        self.assertIn("provider 가 여러 개입니다 → --provider 로 고르세요: a, b", out)

    def test_example_config_matches_defaults(self):
        with open(os.path.join(ROOT, "config.example.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), rp.DEFAULT_CONFIG)   # 설명서의 기본값과 코드가 같게

    def test_env_overrides_and_refs(self):
        os.environ["REPORT_TEST_KEY"] = "secret-from-env"
        try:
            cfg = base_cfg(self.home, llm={"base_url": "http://x/v1", "model": "m", "api_key": "{env:REPORT_TEST_KEY}"})
            self.assertEqual(rp.LLMClient(cfg).api_key, "secret-from-env")
            self.assertEqual(rp.mask_secret("{env:REPORT_TEST_KEY}"), "{env:REPORT_TEST_KEY} 참조 · 값 있음")
            self.assertEqual(rp.mask_secret("abc"), "설정됨 (3자 · 값은 표시 안 함)")
            os.environ["REPORT_API_KEY"] = "leak-me"
            path = os.path.join(self.home, "a.json")
            self.assertEqual(rp.load_config(path)[0]["llm"]["api_key"], "leak-me")
            self.assertEqual(rp.DEFAULT_CONFIG["llm"]["api_key"], "")          # 기본값에 섞이지 않고
            rp.load_config(os.path.join(self.home, "b.json"))
            with open(os.path.join(self.home, "b.json"), encoding="utf-8") as f:
                self.assertNotIn("leak-me", f.read())                           # 새 설정 파일로 새지 않는다
        finally:
            del os.environ["REPORT_TEST_KEY"]
            os.environ.pop("REPORT_API_KEY", None)


if __name__ == "__main__":
    unittest.main(verbosity=1)
