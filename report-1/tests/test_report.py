# -*- coding: utf-8 -*-
"""Report–1 단위 · 통합 테스트 (표준 라이브러리 unittest). 사내 LLM 은 가짜로 (tests/fake_llm_server.py)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import importlib.util  # noqa: E402

TMP = tempfile.mkdtemp(prefix="report1-test-")
os.environ["REPORT_HOME"] = os.path.join(TMP, "home")
os.environ["XDG_CONFIG_HOME"] = os.path.join(TMP, "xdg")           # 이 PC 의 OpenCode 설정을 읽지 않게
os.environ["XDG_DATA_HOME"] = os.path.join(TMP, "xdg-data")
for k in ("REPORT_BASE_URL", "REPORT_API_KEY", "REPORT_MODEL", "OPENCODE_CONFIG"):
    os.environ.pop(k, None)

# report-1.py 는 이름에 '-' 가 있어 import 문으로는 못 부른다 → 파일에서 직접 읽어 'report' 모듈로 등록
_spec = importlib.util.spec_from_file_location("report", os.path.join(ROOT, "report-1.py"))
rp = importlib.util.module_from_spec(_spec)
sys.modules["report"] = rp
_spec.loader.exec_module(rp)
from fake_llm_server import FakeLLM  # noqa: E402

# 지어낸 예시 자료 (사내 정보 아님 · RULES.md › W-12)
MAIL = """보낸 사람: 김대리 <kim@example.com>
받는 사람: 운영팀
제목: 결제 서버 응답 지연 보고

안녕하세요.

9월 12일 14:05부터 14:47까지 결제 서버 응답이 느려졌습니다. 영향 받은 주문은 1,240건입니다.
원인은 DB 연결 풀 고갈로 보입니다.

> 지난 메일 인용 한 줄
> 지난 메일 인용 두 줄
"""
CHAT = ("[김대리] [오후 2:10] 결제 느린 거 저만 그런가요\n[박과장] [오후 2:11] 저도요 DB 쪽 확인 중\n"
        "[김대리] [오후 2:15] 풀 크기 늘렸습니다\n[박과장] [오후 2:47] 정상화 확인\n")
TABLE = "항목\t9월\t10월\n매출\t1,200\t1,350\n지연 건수\t3\t1\n"
MARK = "비밀표식-QX7Z"   # 디스크에 원문이 남는지 찾는 표식


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


def base_cfg(home, **over):
    cfg = rp.deep_merge(rp.DEFAULT_CONFIG, over)
    cfg["_dir"] = home
    rp.validate_config(cfg)
    return cfg


def files_under(folder):
    out = []
    for dp, _, fs in os.walk(folder):
        out += [os.path.join(dp, f) for f in fs]
    return out


def disk_has(folder, needle):
    for p in files_under(folder):
        with open(p, "rb") as f:
            if needle.encode("utf-8") in f.read():
                return True
    return False


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(dir=TMP)
        self.home = os.path.join(self.dir, "home")
        os.makedirs(self.home)


# ─────────────────────────────────────────────────────────────── 자료 → 조각

class Split(unittest.TestCase):
    def test_mail_subject_quotes_and_short_greeting(self):
        sp = rp.split_paste(MAIL)
        self.assertEqual((sp["kind"], sp["title"], sp["quotes"]), ("mail", "결제 서버 응답 지연 보고", 2))
        self.assertFalse(any("인용" in f for f in sp["frags"]))                       # > 인용 줄은 건너뛴다
        self.assertNotIn("안녕하세요.", sp["frags"])                               # 인사 한 줄은 이웃 조각과 묶는다
        self.assertTrue(any("1,240건" in f for f in sp["frags"]))

    def test_table_rows_keep_their_header(self):
        sp = rp.split_paste(TABLE)
        self.assertEqual(sp["kind"], "table")
        self.assertEqual(sp["frags"], ["항목: 매출 · 9월: 1,200 · 10월: 1,350", "항목: 지연 건수 · 9월: 3 · 10월: 1"])
        self.assertEqual(rp.split_paste("1\t2\n3\t4\n")["frags"], ["1 · 2", "3 · 4"])   # 숫자뿐인 첫 줄은 머리글이 아니다

    def test_chat_is_detected_and_title_has_no_header(self):
        sp = rp.split_paste(CHAT)
        self.assertEqual((sp["kind"], sp["title"]), ("chat", "결제 느린 거 저만 그런가요"))

    def test_long_text_is_cut_without_losing_words(self):
        long = "첫 문장입니다. " + ("가나다라마바사 아자차카타파하 " * 80) + "끝."
        for text in (long, "가" * 1500):
            frags = rp.split_paste(text)["frags"]
            self.assertTrue(all(len(f) <= rp.FRAG_MAX for f in frags), [len(f) for f in frags])
            self.assertEqual("".join("".join(frags).split()), "".join(text.split()))

    def test_rules_and_blank_lines_split_blocks(self):
        first = "첫째 문단은 이만큼 길게 써서 다음 문단과 묶이지 않게 합니다. 짧은 조각만 이웃과 묶이니 충분히 길어야 합니다."
        self.assertGreaterEqual(len(first), rp.FRAG_MIN)
        self.assertEqual(rp.split_paste(first + "\n-----\n둘째 문단\n\n\n")["frags"], [first, "둘째 문단"])
        self.assertEqual(rp.split_paste("짧은 머리\n\n" + first)["frags"], ["짧은 머리\n" + first])


class DeskTest(unittest.TestCase):
    def test_ids_dedupe_delete_and_restore(self):
        d = rp.Desk("이슈 보고")
        a1 = d.add(MAIL)
        self.assertEqual((a1.id, a1.frags[0]), ("a1", "p1"))
        with self.assertRaisesRegex(ValueError, "이미 붙여 넣은 조각뿐"):
            d.add(MAIL)                                               # 같은 메일을 두 번 붙이면
        a2 = d.add(MAIL + "\n새로 붙은 답장 한 줄입니다.")
        self.assertEqual((a2.id, a2.dups, len(a2.frags)), ("a2", len(a1.frags), 1))   # 같은 조각은 건너뛴다
        d.exclude.add(a2.frags[0])
        snap = d.remove("a1")
        self.assertNotIn("p1", d.frags)
        d.restore(snap)
        self.assertEqual([p.id for p in d.pastes], ["a1", "a2"])
        self.assertEqual(list(d.frags)[0], "p1")
        self.assertIn(a2.frags[0], d.exclude)
        d.remove("a2")
        a3 = d.add("완전히 다른 새 자료입니다. 지운 자료의 번호를 다시 쓰지 않습니다.")
        self.assertEqual(a3.id, "a3")                                            # 지운 자료 · 조각의 id 는 다시 쓰지 않는다
        self.assertNotIn(a3.frags[0], a2.frags)
        with self.assertRaises(KeyError):
            d.remove("a9")

    def test_limits_and_empty(self):
        d = rp.Desk("이슈 보고")
        with self.assertRaisesRegex(ValueError, "비어 있습니다"):
            d.add("  \n ")
        with self.assertRaisesRegex(ValueError, "나눠서"):
            d.add("가" * (rp.MAX_PASTE + 1))
        with self.assertRaisesRegex(ValueError, "쓸 수 있는 글이 없습니다"):
            d.add("-----\n=====\n")

    def test_known_chars_unsaved_and_doc_roundtrip(self):
        d = rp.Desk("회의 결과")
        self.assertFalse(d.unsaved())
        d.topic = "결제 지연"
        d.add(MAIL)
        d.add(TABLE)
        d.exclude = {"p1"}
        self.assertTrue(d.unsaved())
        self.assertNotIn("p1", d.known())
        self.assertEqual(d.chars(), d.chars(False) - len(d.frags["p1"].text))
        back = rp.Desk.from_doc(json.loads(json.dumps(d.to_doc())), rp.DEFAULT_CONFIG["report"]["forms"], "현황 보고")
        self.assertEqual((back.topic, back.form, back.exclude), ("결제 지연", "회의 결과", {"p1"}))
        self.assertEqual({k: f.text for k, f in back.frags.items()}, {k: f.text for k, f in d.frags.items()})
        self.assertEqual((back.next_a, back.next_p), (d.next_a, d.next_p))
        self.assertEqual(rp.Desk.from_doc({"form": "없는 양식", "pastes": [{"id": "x"}, 3]}, {"A": []}, "A").form, "A")


# ─────────────────────────────────────────────────────────────── 근거 판정 · 초안 · 글

def frags(*texts):
    return {f"p{i + 1}": rp.Frag(f"p{i + 1}", "a1", t) for i, t in enumerate(texts)}


class Judge(unittest.TestCase):
    def test_states(self):
        known = frags("주문 1,240건 영향", "14:05부터 14:47까지")
        j = lambda **kw: rp.judge(rp.Line(**dict({"section": 1, "text": "x"}, **kw)), known)  # noqa: E731
        self.assertEqual(j(refs=[]).state, "err")
        self.assertEqual(j(refs=["p9", "P1", "[p1]"]).refs, ["p1"])            # 모르는 id 는 버리고, 모양은 고친다
        self.assertEqual(j(refs=["p9"]).state, "err")
        self.assertEqual(j(refs=["p2"], kind="infer").state, "infer")
        self.assertEqual(j(refs=["p1", "p2"], kind="check").state, "check")
        self.assertEqual(j(refs=[], kind="check").state, "err")
        self.assertEqual((j(refs=["p1"], kind="gap").state, j(refs=["p1"], kind="gap").refs), ("gap", []))
        self.assertEqual(j(refs=[], origin="user").state, "user")
        self.assertEqual(j(refs=["p1"], kind="이상한값").state, "ok")
        self.assertEqual(rp.judge(rp.Line(1, "x", ["p1"]), {}).state, "err")    # 체크를 푼 조각은 근거가 아니다

    def test_numbers_must_come_from_cited_fragments(self):
        known = frags("영향 주문 1240건, 14:05부터 14:47까지", "매출 3.50억")
        line = lambda t, r: rp.judge(rp.Line(1, t, r), known).nums  # noqa: E731
        self.assertEqual(line("영향 주문 1,240건 · 14시 05분", ["p1"]), [])
        self.assertEqual(line("복구 97분 · 3건 · 30% 감소", ["p1"]), ["97", "30"])   # 한 자리 정수(센 숫자)는 세지 않는다
        self.assertEqual(line("매출 3.5억", ["p2"]), [])
        self.assertEqual(line("매출 3.5억", ["p1"]), ["3.5"])                       # 다른 조각에 있어도 근거로 단 조각에 없으면
        self.assertEqual(rp.judge(rp.Line(1, "복구 97분", ["p1"], origin="user"), known).nums, [])
        self.assertEqual(rp.numbers("1,240 · 09 · 3.50 · 10.0 · 2026-09-12 · 0.5"),
                         ["1240", "9", "3.5", "10", "2026", "9", "12", "0.5"])

    def test_parse_shapes(self):
        secs = ["요약", "현상", "원인"]
        good = json.dumps({"title": "T", "sections": [
            {"name": "요약", "lines": [{"text": "a", "refs": ["p1"], "kind": "추론"}] * 5},
            {"name": "원인", "lines": [{"text": "원인 글 [p2, p3]", "kind": "fact", "level": 2}]},
            {"name": "현상", "lines": ["그냥 글", {"text": "", "kind": "gap"}, 3]}]}, ensure_ascii=False)
        for wrapped in (good, f"<think>음</think>설명\n```json\n{good}\n```\n끝"):
            title, names, lines = rp.parse_draft(wrapped, secs, False, 6)
            self.assertEqual((title, names), ("T", secs))
            self.assertEqual(len([x for x in lines if x.section == 0]), rp.SUMMARY_MAX)
            self.assertEqual(lines[0].kind, "infer")
            cause = next(x for x in lines if x.section == 2)
            self.assertEqual((cause.text, cause.refs, cause.level), ("원인 글", ["p2", "p3"], 2))   # 글 속 [p2] 는 근거로
            self.assertEqual([(x.text, x.kind) for x in lines if x.section == 1], [("그냥 글", "fact"), ("", "gap")])
        _, _, pos = rp.parse_draft('{"sections": [{"lines": ["x"]}, {"lines": ["y"]}, {"lines": ["z"]}, {"lines": ["w"]}]}',
                                   secs, False, 6)
        self.assertEqual([x.section for x in pos], [0, 1, 2, 2])                  # 이름이 없으면 순서대로
        _, names, _ = rp.parse_draft('{"sections": [{"name": "요약", "lines": []}, {"name": "배경", "lines": ["b"]},'
                                     ' {"name": "할 일", "lines": ["c"]}]}', ["요약"], True, 6)
        self.assertEqual(names, ["요약", "배경", "할 일"])                          # 자유 구성은 LLM 이 칸 이름을 정한다
        for bad in ("그냥 말", "[1, 2]", '{"title": "x"}'):
            with self.assertRaises(ValueError):
                rp.parse_draft(bad, secs, False, 6)

    def test_render_brief_prose_and_refs(self):
        known = frags("영향 주문 1,240건", "원인은 DB 연결 풀 고갈")
        pastes = {"a1": rp.Paste("a1", "mail", "지연 보고", "")}
        lines = [rp.judge(x, known) for x in (
            rp.Line(0, "조치 완료로 보임", ["p1", "p2"], "infer"), rp.Line(1, "주문 1,240건 영향", ["p1"]),
            rp.Line(1, "세부", ["p2"], level=2), rp.Line(1, "시각 표기 다름", ["p1", "p2"], "check"),
            rp.Line(2, "담당자", [], "gap"))]
        text = rp.render_text("결제 지연", ["요약", "현상", "원인", "조치"], lines, known, pastes)
        self.assertEqual(text, "결제 지연\n\n□ 요약\n  ○ 조치 완료로 보임\n\n□ 현상\n  ○ 주문 1,240건 영향\n    - 세부\n"
                               "  ○ 시각 표기 다름 (확인 필요)\n\n□ 원인\n  ○ 담당자 — 자료 없음 (확인 필요)\n\n□ 조치\n  ○ 자료 없음\n")
        refd = rp.render_text("결제 지연", ["요약", "현상", "원인"], lines, known, pastes, "prose", True)
        self.assertIn("  조치 완료로 보임[1][2]\n", refd)
        self.assertIn("    세부[2]\n", refd)
        self.assertTrue(refd.endswith("※ 근거\n[1] 메일 「지연 보고」: 영향 주문 1,240건\n[2] 메일 「지연 보고」: 원인은 DB 연결 풀 고갈\n"))

    def test_prompt_sends_only_checked_fragments(self):
        d = rp.Desk("이슈 보고")
        d.add(MAIL)
        d.add("다른 자료 " + MARK)
        mark_id = next(k for k, f in d.frags.items() if MARK in f.text)
        d.exclude = {mark_id}
        secs, free = rp.sections_of(base_cfg(TMP), "이슈 보고")
        msgs = rp.build_messages("결제 지연", "이슈 보고", secs, free, d.known(), d.paste_of(), 2, "brief", "exec")
        allm = json.dumps(msgs, ensure_ascii=False)
        self.assertNotIn(MARK, allm)
        self.assertIn("자료 밖의 지식", msgs[0]["content"])
        self.assertIn("'요약' · '현상' · '원인' · '영향' · '조치' · '요청 사항' — 이 순서", msgs[0]["content"])
        self.assertIn("임원", msgs[0]["content"])
        self.assertIn("[p1] (자료 1 · 메일) ", msgs[1]["content"])
        self.assertEqual(rp.sections_of(base_cfg(TMP), "자유 구성"), (["요약"], True))
        self.assertEqual(rp.sections_of(base_cfg(TMP, report={"summary": False}), "회의 결과")[0][0], "회의 개요")

    def test_basic_draft_cites_every_fact(self):
        d = rp.Desk("이슈 보고")
        d.add(MAIL)
        d.add(CHAT)
        secs, _ = rp.sections_of(base_cfg(TMP), "이슈 보고")
        lines = rp.basic_draft(d.known(), d.paste_of(), secs, 6, True)
        self.assertTrue(all(x.refs for x in lines if x.kind == "fact"))
        self.assertTrue(all(x.state in ("ok", "gap") for x in lines))
        self.assertEqual({x.section for x in lines if x.kind == "gap"}, {0, 2, 3, 4, 5})


# ─────────────────────────────────────────────────────────────── 저장 (W-05 · W-06)

class Storage(Base):
    def test_folder_broken_newer_and_bad_names(self):
        f = rp.Folder(os.path.join(self.home, "topics"), "토픽")
        k = f.new_key("t")
        f.save(k, {"topic": "a"})
        self.assertEqual(f.get(k)["version"], 1)
        self.assertNotEqual(f.new_key("t"), k)
        with open(f.path(k), "w", encoding="utf-8") as fh:
            fh.write("{broken")
        self.assertIsNone(f.get(k))
        self.assertTrue(os.path.exists(f.path(k) + ".broken"))
        with open(f.path(k), "w", encoding="utf-8") as fh:
            json.dump({"version": 99, "topic": "future"}, fh)
        self.assertTrue(f.get(k)["readonly"])
        with self.assertRaises(OSError):
            f.save(k, {"topic": "overwrite"})                  # 더 새 버전이 쓴 파일은 덮어쓰지 않는다
        for bad in ("../x", "a/b", "..", ""):
            with self.assertRaises(ValueError):
                f.path(bad)


# ─────────────────────────────────────────────────────────────── 로컬 서버

class HttpBase(Base):
    MODE = "good"

    def setUp(self):
        super().setUp()
        self.llm = FakeLLM(mode=self.MODE)
        self.cfg = base_cfg(self.home, llm={"base_url": self.llm.url, "model": "fake-model"}, idle_exit_min=0)
        self.app = rp.App(self.cfg, os.path.join(self.home, "config.json"))
        self.app.httpd, self.app.port = rp.bind_server(0, rp.make_handler(self.app))
        self.app.allowed_hosts = {f"127.0.0.1:{self.app.port}", f"localhost:{self.app.port}"}
        threading.Thread(target=self.app.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.app.httpd.shutdown()
        self.app.httpd.server_close()
        self.llm.close()

    def call(self, path, body=None, token=True, host=None, ctype="application/json", raw=None):
        data = raw if raw is not None else (json.dumps(body).encode("utf-8") if body is not None else None)
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

    def fill(self, *texts, topic="결제 지연", form="이슈 보고"):
        self.assertEqual(self.call("/api/desk", {"topic": topic, "form": form})[0], 200)
        for t in texts:
            code, d = self.call("/api/paste", {"text": t})
            self.assertEqual(code, 200, d)
        return d["desk"]

    def body(self, draft, **over):
        return dict({"form": draft["form"], "sections": draft["sections"], "title": draft["title"],
                     "lines": draft["lines"]}, **over)


class Http(HttpBase):
    def test_binds_localhost_and_guards(self):
        self.assertEqual(self.app.httpd.server_address[0], "127.0.0.1")
        self.assertEqual(self.call("/api/state", token=False)[0], 401)
        self.assertEqual(self.call("/api/state", host="evil.example:80")[0], 403)
        self.assertEqual(self.call("/api/paste", {"text": "x"}, ctype="text/plain")[0], 415)
        self.assertEqual(self.call("/api/ping", token=False), (200, {"app": "report-1", "version": rp.VERSION}))
        self.assertEqual(self.call("/api/topics/..%2Fx/open", {})[0], 404)
        keep = rp.MAX_PASTE
        rp.MAX_PASTE = 100          # 요청 크기 한도 = MAX_PASTE × 8 바이트
        try:
            code, d = self.call("/api/paste", {"text": "가" * 400})
        finally:
            rp.MAX_PASTE = keep
        self.assertEqual(code, 413, d)

    def test_paste_draft_confirm_undo(self):
        desk = self.fill(MAIL, CHAT, TABLE)
        self.assertEqual([p["kind"] for p in desk["pastes"]], ["mail", "chat", "table"])
        code, d = self.call("/api/draft", {"detail": 2, "tone": "brief", "audience": "boss"})
        self.assertEqual((code, d["mode"], d["title"]), (200, "llm", "결제 지연"), d)
        self.assertEqual(d["sections"][:2], ["요약", "현상"])
        states = {x["state"] for x in d["lines"]}
        self.assertTrue({"ok", "infer", "check", "gap"} <= states, states)
        self.assertNotIn("err", states)
        code, c = self.call("/api/confirm", self.body(d, with_refs=True))
        self.assertEqual(code, 200, c)
        self.assertIn("※ 근거\n[1] 메일 「결제 서버 응답 지연 보고」", c["text"])
        path = os.path.join(self.home, "reports", c["key"] + ".json")
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual((saved["text"], saved["title"]), (c["text"], "결제 지연"))
        self.assertNotIn("frags", saved)
        self.assertEqual(self.call("/api/reports")[1]["reports"][0]["key"], c["key"])
        self.assertEqual(self.call(f"/api/reports/{c['key']}")[1]["text"], c["text"])
        code, u = self.call("/api/undo", {})
        self.assertEqual((code, u["undone"]), (200, "confirm"))
        self.assertFalse(os.path.exists(path))
        self.assertEqual(self.call("/api/undo", {})[0], 400)                      # 두 번은 안 된다

    def test_raw_text_reaches_disk_only_when_saved(self):
        """W-05 — 붙여 넣은 원문은 '보관' 을 누르기 전에는 디스크 어디에도 없다"""
        self.fill(MAIL, "기록 " + MARK + " 끝")
        code, d = self.call("/api/draft", {})
        self.assertEqual(code, 200)
        self.assertEqual(self.call("/api/preview", self.body(d))[0], 200)
        self.assertFalse(disk_has(self.home, MARK))
        self.assertFalse(os.path.isdir(os.path.join(self.home, "topics")))
        code, s = self.call("/api/save", {})
        self.assertEqual((code, s["desk"]["unsaved"]), (200, False))
        self.assertTrue(disk_has(os.path.join(self.home, "topics"), MARK))
        self.assertEqual(self.call("/api/topics")[1]["topics"][0]["id"], s["saved"])
        self.assertEqual(self.call("/api/save", {})[1]["saved"], s["saved"])        # 다시 보관하면 같은 파일에

    def test_unsaved_desk_is_guarded(self):
        self.fill(MAIL)
        code, d = self.call("/api/desk/new", {})
        self.assertEqual(code, 409, d)
        self.assertIn("보관 안 한 자료 1개", d["error"])
        key = self.call("/api/save", {})[1]["saved"]
        self.call("/api/paste", {"text": CHAT})
        self.assertEqual(self.call("/api/desk/new", {})[0], 409)                   # 보관 뒤에 더 붙인 것도
        code, d = self.call("/api/desk/new", {"discard": True})
        self.assertEqual((code, d["desk"]["pastes"]), (200, []))
        code, d = self.call(f"/api/topics/{key}/open", {})
        self.assertEqual((code, d["desk"]["topic"], d["desk"]["saved_id"], d["desk"]["unsaved"]), (200, "결제 지연", key, False))
        self.assertEqual(len(d["desk"]["pastes"]), 1)                             # 보관한 때의 자료만
        code, d = self.call(f"/api/topics/{key}/delete", {})
        self.assertEqual((code, d["topics"], d["desk"]["unsaved"]), (200, [], True))
        self.assertEqual(self.call("/api/undo", {})[0], 200)
        self.assertEqual(self.call("/api/topics")[1]["topics"][0]["id"], key)
        self.assertEqual(self.call("/api/desk")[1]["desk"]["saved_id"], key)

    def test_idle_exit_waits_for_unsaved(self):
        self.app.cfg["idle_exit_min"] = 1
        later = time.time() + 3600
        self.assertTrue(self.app.idle_should_exit(later))
        self.fill(MAIL)
        self.assertFalse(self.app.idle_should_exit(later))                         # 원문이 사라지지 않게 기다린다
        self.call("/api/save", {})
        self.assertTrue(self.app.idle_should_exit(later))
        self.assertFalse(self.app.idle_should_exit(time.time()))

    def test_excluded_fragments_are_not_sent_or_citable(self):
        desk = self.fill(MAIL, "기록 " + MARK + " 끝")
        mark_id = desk["pastes"][1]["frags"][0]["id"]
        code, d = self.call("/api/draft", {})
        self.assertTrue(any(mark_id in x["refs"] for x in d["lines"]))
        self.call("/api/desk", {"exclude": [mark_id, "p999"]})
        self.assertEqual(self.call("/api/desk")[1]["desk"]["exclude"], [mark_id])
        code, pv = self.call("/api/preview", self.body(d))
        self.assertTrue(all(mark_id not in x["refs"] for x in pv["lines"]))
        self.llm.requests.clear()
        self.call("/api/draft", {})
        self.assertNotIn(MARK, json.dumps(self.llm.requests, ensure_ascii=False))

    def test_budget_blocks_llm_but_not_basic(self):
        self.app.budget = 1000
        self.fill(" ".join(f"{i}번째 문장은 서로 다른 내용입니다." for i in range(120)))
        code, d = self.call("/api/draft", {})
        self.assertEqual(code, 400)
        self.assertIn("한도보다 깁니다", d["error"])
        self.assertEqual(self.llm.requests, [])
        code, d = self.call("/api/draft", {"basic": True})
        self.assertEqual((code, d["mode"]), (200, "basic"))

    def test_paste_delete_and_undo(self):
        self.fill(MAIL, CHAT)
        code, d = self.call("/api/paste/a1/delete", {})
        self.assertEqual(([p["id"] for p in d["desk"]["pastes"]], d["undo_sec"]), (["a2"], rp.App.UNDO_SEC))
        code, u = self.call("/api/undo", {})
        self.assertEqual(([p["id"] for p in u["desk"]["pastes"]], u["undone"]), (["a1", "a2"], "paste"))
        self.assertEqual(self.call("/api/paste/a9/delete", {})[0], 404)
        self.assertEqual(self.call("/api/paste", {"text": "   "})[0], 400)

    def test_forged_client_state_is_rejudged(self):
        self.fill(MAIL, CHAT, TABLE)
        code, d = self.call("/api/draft", {})
        forged = [dict(x, state="ok", refs=["p77"]) for x in d["lines"] if x["kind"] == "fact"]
        self.assertGreaterEqual(len(forged), 3)
        forged[0]["kind"] = "gap"
        code, pv = self.call("/api/preview", self.body(d, lines=forged))
        self.assertEqual(pv["lines"][0]["state"], "gap")
        self.assertTrue(all(x["state"] == "err" for x in pv["lines"][1:]))
        code, c = self.call("/api/confirm", self.body(d, lines=forged))
        self.assertEqual(code, 400)
        self.assertIn("근거 없는 줄이", c["error"])
        self.assertEqual(self.call("/api/confirm", self.body(d, form="없는 양식"))[0], 400)


class HttpLie(HttpBase):
    MODE = "lie"

    def test_invented_fact_blocks_confirm_until_a_person_owns_it(self):
        self.fill(MAIL)
        code, d = self.call("/api/draft", {})
        bad = [x for x in d["lines"] if x["state"] == "err"]
        self.assertEqual([x["text"] for x in bad], ["성과 30% 향상"])
        code, c = self.call("/api/confirm", self.body(d))
        self.assertEqual(code, 400)
        owned = [dict(x, origin="user", text="성과 측정은 다음 주") if x["state"] == "err" else x for x in d["lines"]]
        code, c = self.call("/api/confirm", self.body(d, lines=owned))
        self.assertEqual(code, 200, c)
        self.assertIn("성과 측정은 다음 주", c["text"])


class HttpModes(Base):
    def run_mode(self, mode):
        llm = FakeLLM(mode=mode)
        try:
            app = rp.App(base_cfg(self.home, llm={"base_url": llm.url, "model": "m"}), os.path.join(self.home, "c.json"))
            app.desk_update({"form": "자유 구성"})
            app.paste({"text": MAIL})
            app.paste({"text": CHAT})
            return app.draft({}), llm
        finally:
            llm.close()

    def test_numbers_inline_fence_retry_length_error(self):
        d, _ = self.run_mode("number")
        self.assertEqual([x["nums"] for x in d["lines"] if x["nums"]], [["97"]])
        d, _ = self.run_mode("inline")
        self.assertTrue(all(x["refs"] and "[p" not in x["text"] for x in d["lines"] if x["kind"] == "fact"))
        d, _ = self.run_mode("fence")
        self.assertEqual((d["mode"], d["sections"]), ("llm", ["요약", "내용"]))
        d, llm = self.run_mode("garbage")
        self.assertEqual((d["mode"], len(llm.requests)), ("llm", 2))              # 한 번 다시 묻는다
        d, llm = self.run_mode("length")
        self.assertEqual((d["mode"], len(llm.requests)), ("basic", 1))            # 잘린 답은 다시 묻지 않는다
        self.assertIn("llm.max_tokens", d["error"])
        d, _ = self.run_mode("error")
        self.assertEqual(d["mode"], "basic")
        self.assertIn("500", d["error"])


# ─────────────────────────────────────────────────────────────── 명령줄

def run_cli(*args, env=None, stdin=None):
    e = dict(os.environ, PYTHONIOENCODING="utf-8", **(env or {}))
    r = subprocess.run([sys.executable, os.path.join(ROOT, "report-1.py"), *args], capture_output=True, timeout=120,
                       env=e, input=stdin)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")


class Cli(Base):
    def env(self):
        return {"REPORT_HOME": self.home}

    def saved(self):
        with open(os.path.join(self.home, "config.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_version_and_data_dir(self):
        code, out, _ = run_cli("--version")
        self.assertEqual((code, out.strip()), (0, f"Report-1 {rp.VERSION}"))
        self.assertEqual(rp.default_config_path(), os.path.join(os.environ["REPORT_HOME"], "config.json"))

    def test_set_refuses_raw_key_and_unknown_keys(self):
        code, out, _ = run_cli("--set", "llm.api_key=sk-plain-value-000", env=self.env())
        self.assertEqual(code, 2)
        self.assertIn("API 키는 --set 으로 넣지 않습니다", out)
        self.assertNotIn("sk-plain-value-000", out)
        code, out, _ = run_cli("--set", "llm.api_key={env:CORP_KEY}", "--set", "report.budget_chars=12000", env=self.env())
        self.assertEqual(code, 0, out)
        self.assertIn("{env:CORP_KEY} 참조", out)
        self.assertEqual(run_cli("--set", "nope.key=1", env=self.env())[0], 2)
        code, out, _ = run_cli("--set", "theme=purple", env=self.env())
        self.assertEqual(code, 2)
        self.assertIn("되돌렸습니다", out)
        self.assertEqual((self.saved()["report"]["budget_chars"], self.saved()["theme"]), (12000, "dark"))
        self.assertEqual(run_cli("--set", "llm.models=a; b", env=self.env())[0], 0)   # 목록 칸은 ; 로 나눈 글도
        self.assertEqual(self.saved()["llm"]["models"], ["a", "b"])

    def test_set_forms_add_change_remove(self):
        code, out, _ = run_cli("--set", "report.forms.주간 점검=현황; 이슈 ;계획", env=self.env())
        self.assertEqual(code, 0, out)
        forms = self.saved()["report"]["forms"]
        self.assertEqual(forms["주간 점검"], ["현황", "이슈", "계획"])
        self.assertEqual(list(forms)[:5], list(rp.DEFAULT_CONFIG["report"]["forms"]))   # 기본 양식은 그대로 남는다
        self.assertEqual(run_cli("--set", "report.forms.현황 보고=", env=self.env())[0], 0)
        cfg, _ = rp.load_config(os.path.join(self.home, "config.json"))
        self.assertNotIn("현황 보고", cfg["report"]["forms"])                     # 지운 양식이 기본값에서 되살아나지 않는다
        self.assertEqual(run_cli("--set", "report.forms.없는 양식=", env=self.env())[0], 2)
        code, out, _ = run_cli("--set", "report.forms.중복=가;가", env=self.env())
        self.assertEqual(code, 2)
        self.assertIn("같은 칸 이름", out)
        self.assertEqual(run_cli("--set", "report.forms.자유2=[]", env=self.env())[0], 0)
        self.assertEqual(self.saved()["report"]["forms"]["자유2"], [])

    def test_draft_files_and_stdin_to_stdout(self):
        a, b = os.path.join(self.dir, "a.txt"), os.path.join(self.dir, "b.txt")
        with open(a, "w", encoding="utf-8") as f:
            f.write(MAIL)
        with open(b, "wb") as f:
            f.write(CHAT.encode("cp949"))                                         # 한글 Windows 메모장 파일
        code, out, err = run_cli("--draft", a, b, "--basic", "--topic", "결제 지연", "--form", "회의 결과", env=self.env())
        self.assertEqual(code, 0, err)
        self.assertTrue(out.startswith("결제 지연\n\n□ 요약\n"), out)
        self.assertIn("□ 논의 내용\n", out)
        self.assertIn("결제 느린 거 저만 그런가요", out)
        self.assertIn("자료 a2", err)                                             # 로그는 표준 오류로
        code, out, err = run_cli("--draft", "-", "--basic", env=self.env(), stdin=TABLE.encode("utf-8"))
        self.assertEqual(code, 0, err)
        self.assertIn("항목: 매출", out)
        self.assertEqual(run_cli("--draft", a, "--form", "없는 양식", env=self.env())[0], 2)
        self.assertFalse(os.path.isdir(os.path.join(self.home, "topics")))        # 명령줄은 아무것도 보관하지 않는다

    def test_check_without_llm_is_ok(self):
        code, out, _ = run_cli("--check", env=self.env())
        self.assertEqual(code, 0, out)
        self.assertIn("LLM       : 미설정 → 기본 초안", out)
        self.assertIn("양식      : 현황 보고 · 이슈 보고", out)
        self.assertEqual(out.strip().splitlines()[-1], "결과: OK")

    def test_setup_reads_opencode_and_checks(self):
        llm = FakeLLM()
        try:
            oc = os.path.join(self.dir, "oc")
            os.makedirs(oc)
            with open(os.path.join(oc, "opencode.jsonc"), "w", encoding="utf-8") as f:
                f.write('{\n // 사내\n "provider": {"corp": {"npm": "@ai-sdk/openai-compatible", '
                        '"options": {"baseURL": "' + llm.url + '", "apiKey": "{env:CORP_KEY}"}, '
                        '"models": {"qwen3": {}}}},\n}\n')
            code, out, _ = run_cli("--setup", env=dict(self.env(), OPENCODE_CONFIG=os.path.join(oc, "opencode.jsonc"),
                                                       CORP_KEY="k-value-never-printed"))
        finally:
            llm.close()
        self.assertEqual(code, 0, out)
        self.assertIn("provider 'corp'", out)
        self.assertIn("기본 응답 OK", out)
        self.assertTrue(out.strip().splitlines()[-1].startswith("결과: OK"))
        self.assertNotIn("k-value-never-printed", out)
        llm_cfg = self.saved()["llm"]
        self.assertEqual((llm_cfg["base_url"], llm_cfg["model"], llm_cfg["api_key"]), (llm.url, "qwen3", "{env:CORP_KEY}"))

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

    def test_bad_forms_config_is_refused(self):
        for bad in ({}, {"": ["a"]}, {"A": "a;b"}, {"A": [f"칸{i}" for i in range(9)]}, {"A": ["가" * 21]}, [["a"]]):
            cfg = rp.deep_merge(rp.DEFAULT_CONFIG, {})
            cfg["report"]["forms"] = bad
            with self.assertRaises(rp.ConfigError, msg=repr(bad)):
                rp.validate_config(cfg)


if __name__ == "__main__":
    unittest.main(verbosity=1)
