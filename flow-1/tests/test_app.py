# -*- coding: utf-8 -*-
"""Flow–1 앱 테스트 — 설정 · 명령 · 로컬 서버 · 감시 · 탐색기 · 붙여 넣기 · --run (표준 라이브러리 unittest)

사내 쿼리 패키지는 가짜(tests/fake_pkg/demo_query)로 흉내 낸다. 예시 코드 · 테이블 이름은 모두 지어낸 것 (W-12).
"""
import importlib.util
import json
import os
import re
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
sys.path.insert(0, ROOT)
EX = os.path.join(HERE, "examples")
FAKE = os.path.join(HERE, "fake_pkg")

TMP = tempfile.mkdtemp(prefix="flow1-test-")
os.environ["FLOW_HOME"] = os.path.join(TMP, "home")

# flow-1.py 는 이름에 '-' 가 있어 import 문으로는 못 부른다 → 파일에서 직접 읽어 'flowapp' 모듈로
_spec = importlib.util.spec_from_file_location("flowapp", os.path.join(ROOT, "flow-1.py"))
fa = importlib.util.module_from_spec(_spec)
sys.modules["flowapp"] = fa
_spec.loader.exec_module(fa)
import flow1_graph  # noqa: E402
import flow1_trace  # noqa: E402

LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))
MARK = "비밀표식QX7Z"          # 붙여 넣은 코드가 디스크에 남는지 찾는 표식


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


def run_cli(*args, env=None, cwd=None, timeout=120):
    e = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", **(env or {}))
    p = subprocess.run([sys.executable, os.path.join(ROOT, "flow-1.py")] + list(args), capture_output=True, env=e,
                       cwd=cwd or ROOT, timeout=timeout)
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def disk_has(folder, needle):
    for dp, _, fs in os.walk(folder):
        for f in fs:
            with open(os.path.join(dp, f), "rb") as fh:
                if needle.encode("utf-8") in fh.read():
                    return True
    return False


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(dir=TMP)
        self.home = os.path.join(self.dir, "home")
        os.makedirs(self.home)
        self.cfg_path = os.path.join(self.home, "config.json")

    def cfg(self, **over):
        with open(self.cfg_path, "w", encoding="utf-8") as f:
            json.dump(over, f, ensure_ascii=False)
        cfg, _ = fa.load_config(self.cfg_path)
        return cfg


# ─────────────────────────────────────────────────────────────── 설정

class Config(Base):
    def test_defaults_and_example_file_match(self):
        with open(os.path.join(ROOT, "config.example.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), fa.DEFAULT_CONFIG)
        cfg, created = fa.load_config(os.path.join(self.dir, "new", "config.json"))
        self.assertTrue(created)
        self.assertEqual((cfg["port"], cfg["query"]["modules"], cfg["theme"]), (8785, [], "dark"))

    def test_bad_values_are_refused(self):
        for bad in ({"theme": "red"}, {"query": {"modules": ["bad name!"]}}, {"watch": "D:\\x"}, {"company": "x" * 30},
                    {"scan": {"poll_sec": "fast"}}):
            with self.assertRaises(fa.ConfigError, msg=bad):
                self.cfg(**bad)

    def test_user_lists_replace_defaults(self):
        cfg = self.cfg(query={"calls": ["get_df"]})
        self.assertEqual(cfg["query"]["calls"], ["get_df"])
        self.assertEqual(cfg["query"]["sinks"], fa.DEFAULT_CONFIG["query"]["sinks"])

    def test_set_lists_unknown_keys_and_revert(self):
        self.cfg()
        self.assertEqual(fa.set_config_values(self.cfg_path, ["query.modules=demo_query;other.pkg"]), 0)
        self.assertEqual(fa.load_config(self.cfg_path)[0]["query"]["modules"], ["demo_query", "other.pkg"])
        self.assertEqual(fa.set_config_values(self.cfg_path, ["nope.key=1"]), 2)
        self.assertEqual(fa.set_config_values(self.cfg_path, ["theme=purple"]), 2)       # 검증에서 걸리면 되돌린다
        self.assertEqual(fa.load_config(self.cfg_path)[0]["theme"], "dark")
        self.assertEqual(fa.set_config_values(self.cfg_path, ["company=작은 작업실"]), 0)
        self.assertEqual(fa.load_config(self.cfg_path)[0]["company"], "작은 작업실")

    def test_watch_edit(self):
        self.cfg()
        notes = fa.watch_edit(self.cfg_path, [EX], [])
        self.assertIn("더함", notes[0])
        self.assertIn("이미", fa.watch_edit(self.cfg_path, [os.path.join(EX, "helpers.py")], [])[0])   # 폴더가 덮는다
        with self.assertRaises(fa.ConfigError):
            fa.watch_edit(self.cfg_path, [os.path.join(self.dir, "없는곳")], [])
        fa.watch_edit(self.cfg_path, [], [EX])
        self.assertEqual(fa.load_config(self.cfg_path)[0]["watch"], [])


# ─────────────────────────────────────────────────────────────── 감시 · 탐색기

class WatchTest(Base):
    def make_tree(self):
        proj = os.path.join(self.dir, "proj")
        for d in ("", "sub", "venv", ".hidden", "__pycache__"):
            os.makedirs(os.path.join(proj, d), exist_ok=True)
        files = {"a.py": 'import demo_query as dq\nx = dq.query("SELECT a FROM s.t")\n', "sub/b.py": "print(1)\n",
                 "venv/c.py": 'q("SELECT z FROM s.z")\n', ".hidden/d.py": "", "__pycache__/e.py": "", "notes.txt": "x"}
        for name, text in files.items():
            with open(os.path.join(proj, name), "w", encoding="utf-8") as f:
                f.write(text)
        return proj

    def test_listing_skips_envs_and_rescans_changed_files(self):
        proj = self.make_tree()
        cfg = self.cfg(watch=[proj])
        w = fa.Watch(cfg)
        self.assertTrue(w.refresh(force=True))
        names = [e["name"] for e in w.entries()]
        self.assertEqual(names, ["a.py", "b.py"])
        gen = w.gen
        self.assertFalse(w.refresh())                         # 바뀐 것이 없으면 gen 그대로
        self.assertEqual(w.gen, gen)
        time.sleep(0.05)
        with open(os.path.join(proj, "a.py"), "a", encoding="utf-8") as f:
            f.write('y = dq.query("SELECT b FROM s.u")\n')
        os.utime(os.path.join(proj, "a.py"), (time.time() + 5, time.time() + 5))
        self.assertTrue(w.refresh())
        self.assertEqual(w.entries()[0]["result"]["stats"]["queries"], 2)

    def test_max_files(self):
        proj = self.make_tree()
        w = fa.Watch(self.cfg(watch=[proj], scan={"max_files": 1}))
        w.refresh(force=True)
        self.assertTrue(w.truncated)
        self.assertEqual(len(w.entries()), 1)

    def test_open_and_close_a_file_for_this_session_only(self):
        proj = self.make_tree()
        cfg = self.cfg(watch=[os.path.join(proj, "sub")])
        w = fa.Watch(cfg)
        w.refresh(force=True)
        key = w.open(os.path.join(proj, "a.py"))
        self.assertIn(key, [e["key"] for e in w.entries()])
        self.assertEqual(fa.load_config(self.cfg_path)[0]["watch"], [os.path.join(proj, "sub")])   # 설정에는 안 남는다
        self.assertEqual(w.open(os.path.join(proj, "sub", "b.py")), fa.file_key(os.path.join(proj, "sub", "b.py")))
        self.assertEqual(len(w.opened), 1)                   # 감시 목록에 있는 파일은 따로 열지 않는다
        w.close(key)
        self.assertNotIn(key, [e["key"] for e in w.entries()])
        with self.assertRaises(ValueError):
            w.open(os.path.join(proj, "notes.txt"))

    def test_explorer_lists_one_level(self):
        proj = self.make_tree()
        w = fa.Watch(self.cfg(watch=[os.path.join(proj, "sub")]))
        d = fa.list_dir(proj, w)
        self.assertEqual([(i["name"], i["dir"]) for i in d["items"]], [("sub", True), ("a.py", False)])
        self.assertTrue(d["items"][0]["watched"])
        self.assertTrue(d["items"][1]["sql"])
        self.assertEqual(d["parent"], os.path.dirname(proj))
        self.assertTrue(fa.list_dir("")["items"])            # 드라이브 · 홈
        with self.assertRaises(ValueError):
            fa.list_dir(os.path.join(proj, "a.py"))

    def test_paste_is_memory_only(self):
        w = fa.Watch(self.cfg())
        e = w.paste(f'import demo_query as dq\n# {MARK}\nx = dq.query("SELECT a FROM s.t")\n')
        self.assertEqual(e["result"]["stats"]["queries"], 1)
        self.assertEqual(w.paste("SELECT a FROM s.t JOIN s.u ON t.k = u.k")["kind"], "sql")
        self.assertFalse(disk_has(self.home, MARK))
        w.unpaste(e["key"])
        with self.assertRaises(ValueError):
            w.paste("   ")


# ─────────────────────────────────────────────────────────────── 명령

class Cli(Base):
    def env(self):
        return {"FLOW_HOME": self.home}

    def test_version_scan_json_svg(self):
        rc, out, _ = run_cli("--version", env=self.env())
        self.assertEqual((rc, out.strip()), (0, f"Flow-1 {fa.VERSION}"))
        rc, out, err = run_cli("--scan", os.path.join(EX, "daily_sales.py"), env=self.env())
        self.assertEqual(rc, 0, err)
        with open(os.path.join(HERE, "golden", "daily_sales.py.txt"), encoding="utf-8") as f:
            gold = f.read()
        self.assertEqual(out.replace("\r\n", "\n"), gold.replace("dq.query", "dq.query"))   # 설정 없이도 SQL 인자로 같은 결과
        rc, out, _ = run_cli("--json", EX, env=self.env())
        doc = json.loads(out)
        self.assertEqual((doc["format"], len(doc["files"])), (1, 5))
        svg = os.path.join(self.dir, "out", "flow.svg")
        rc, out, _ = run_cli("--svg", svg, "--detail", "3", "--theme", "light", os.path.join(EX, "daily_sales.py"),
                             env=self.env())
        self.assertEqual(rc, 0)
        with open(svg, encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(text.startswith("<svg") and "data:font/woff;base64," in text and "--fbg:#d4d6d8" in text)
        rc, _, err = run_cli("--scan", os.path.join(self.dir, "없음.py"), env=self.env())
        self.assertEqual(rc, 2)

    def test_check_setup_and_missing_paths(self):
        rc, out, _ = run_cli("--setup", env=self.env())
        self.assertEqual(rc, 0, out)
        self.assertEqual(out.strip().splitlines()[-1], "결과: OK")
        self.assertIn("자체 시험 : 내장 예시 쿼리 6 · 테이블 6", out)
        gone = os.path.join(self.dir, "gone")
        os.makedirs(gone)
        run_cli("--set", f"watch={gone}", env=self.env())
        with open(os.path.join(self.home, "config.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["watch"], [gone])
        shutil.rmtree(gone)
        rc, out, _ = run_cli("--check", env=self.env())
        self.assertEqual(rc, 3)
        self.assertTrue(out.strip().splitlines()[-1].startswith("결과: 확인 필요"))
        rc, out, _ = run_cli("--remove", gone, env=self.env())
        self.assertIn("뺌", out)
        rc, out, _ = run_cli("--set", "query.modules=no_such_pkg_xyz", "--check", env=self.env())
        self.assertEqual(rc, 3)
        self.assertIn("no_such_pkg_xyz · 이 파이썬에 없음", out)

    def test_status_when_stopped(self):
        rc, out, _ = run_cli("--status", "--port", "8799", env=self.env())
        self.assertEqual((rc, out.strip()), (1, "꺼져 있음"))


# ─────────────────────────────────────────────────────────────── --run (실행 기록)

class Run(Base):
    def run_demo(self, *extra):
        env = {"FLOW_HOME": self.home, "PYTHONPATH": FAKE}
        return run_cli("--run", os.path.join(EX, "run_demo.py"), *extra, env=env, cwd=self.dir)

    def test_run_records_timing_rows_and_errors_but_no_sql_or_data(self):
        rc, out, err = self.run_demo("--fail")
        self.assertEqual(rc, 1, err)
        self.assertIn("쿼리 호출 자리 2곳", err)
        self.assertNotIn("flow1_trace.py", err.split("Traceback")[-1])       # 감싸기 줄은 트레이스백에서 뺀다
        runs = flow1_trace.list_runs(os.path.join(self.home, "runs"), os.path.join(EX, "run_demo.py"))
        self.assertEqual(len(runs), 1)
        r = runs[0]
        self.assertEqual((r["exit"], r["ok"], len(r["calls"])), (1, False, 3))
        self.assertEqual([c["ok"] for c in r["calls"]], [True, True, False])
        self.assertEqual([c["rows"] for c in r["calls"]], [5, 10, None])
        self.assertIn("run_helper.py", r["calls"][1]["tag"])                 # import 한 도우미 모듈의 쿼리도 잰다
        self.assertIn("pwd=***", r["calls"][2]["err"])                        # 오류 글의 비밀번호 꼴은 가린다
        d = os.path.join(self.home, "runs", flow1_trace.script_key(os.path.join(EX, "run_demo.py")))
        self.assertFalse(os.path.exists(os.path.join(d, "live.json")))
        for needle in ("SELECT", "dw.orders", "fake-not-real"):             # SQL 원문 · 비밀 값은 기록에 없다
            self.assertFalse(disk_has(d, needle), needle)
        with open(os.path.join(self.home, "config.json"), encoding="utf-8") as f:
            self.assertIn(os.path.join(EX, "run_demo.py"), json.load(f)["watch"])    # 실행한 스크립트는 감시 목록에

    def test_runs_overlay_on_the_graph_and_detail_history(self):
        self.run_demo()
        self.run_demo("--fail")
        cfg, _ = fa.load_config(self.cfg_path)
        app = fa.App(cfg, self.cfg_path)
        app.watch.refresh(force=True)
        key = fa.file_key(os.path.join(EX, "run_demo.py"))
        g = app.graph(key, 2)
        states = {n["id"]: n["run"] for n in g["nodes"] if n["kind"] == "query"}
        self.assertEqual(states, {"q1": "ok", "q2": "err"})
        self.assertIn("√ ", g["svg"])
        self.assertIn("RuntimeError: pwd=***", g["svg"])
        runs = app.run_list(key)["runs"]
        self.assertEqual([r["ok"] for r in runs], [False, True])
        older = app.graph(key, 2, runs[1]["id"])                     # 지난 실행을 골라 겹치기
        self.assertEqual({n["id"]: n["run"] for n in older["nodes"] if n["kind"] == "query" and n["run"]}, {"q1": "ok"})
        hist = app.detail(key, "q1")["history"]
        self.assertEqual([h["state"] for h in hist], ["ok", "ok"])

    def test_script_sees_itself_as_main_for_pickle(self):
        script = os.path.join(self.dir, "pick.py")
        with open(script, "w", encoding="utf-8") as f:
            f.write("import pickle, sys\nclass Box:\n    def __init__(self, v):\n        self.v = v\n"
                    "b = pickle.loads(pickle.dumps(Box(3)))\nassert b.v == 3 and __name__ == '__main__'\n"
                    "assert sys.argv[1:] == ['--x', '1']\nprint('pickle ok')\n")
        rc, out, err = run_cli("--run", script, "--x", "1", env={"FLOW_HOME": self.home}, cwd=self.dir)
        self.assertEqual((rc, out.strip()), (0, "pickle ok"), err)

    def test_keep_prunes_old_runs(self):
        self.cfg(run={"keep": 1})
        self.run_demo()
        self.run_demo()
        runs = flow1_trace.list_runs(os.path.join(self.home, "runs"), os.path.join(EX, "run_demo.py"))
        self.assertEqual(len(runs), 1)

    def test_redact(self):
        self.assertEqual(flow1_trace.redact("login failed password=abc123 user=x"), "login failed password=*** user=x")
        self.assertEqual(flow1_trace.redact("jdbc://kim:s3cr3t@db.example.com/x"), "jdbc://kim:***@db.example.com/x")
        self.assertEqual(flow1_trace.shape_of([[1, 2], [3, 4]]), (2, 2))
        self.assertEqual(flow1_trace.shape_of(iter([1])), (None, None))


# ─────────────────────────────────────────────────────────────── 로컬 서버

class HttpBase(Base):
    def setUp(self):
        super().setUp()
        self.cfg(watch=[EX], idle_exit_min=0)
        cfg, _ = fa.load_config(self.cfg_path)
        self.app = fa.App(cfg, self.cfg_path)
        self.app.watch.refresh(force=True)
        self.app.httpd, self.app.port = fa.bind_server(0, fa.make_handler(self.app))
        self.app.allowed_hosts = {f"127.0.0.1:{self.app.port}", f"localhost:{self.app.port}"}
        self.th = threading.Thread(target=self.app.httpd.serve_forever, daemon=True)
        self.th.start()
        self.base = f"http://127.0.0.1:{self.app.port}"

    def tearDown(self):
        self.app.httpd.shutdown()
        self.app.httpd.server_close()

    def req(self, path, body=None, token=True, host=None, ctype="application/json", raw=False):
        headers = {}
        if token:
            headers["X-Flow-Token"] = self.app.token
        if host:
            headers["Host"] = host
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = ctype
        r = urllib.request.Request(self.base + path, data=data, headers=headers, method="POST" if data is not None else "GET")
        try:
            with LOCAL.open(r, timeout=20) as resp:
                payload = resp.read()
                return resp.status, (payload if raw else json.loads(payload.decode("utf-8"))), dict(resp.headers)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8") or "{}"), dict(e.headers)


class Http(HttpBase):
    def test_binds_localhost_and_guards(self):
        self.assertEqual(self.app.httpd.server_address[0], "127.0.0.1")
        self.assertEqual(self.req("/api/state", token=False)[0], 401)
        self.assertEqual(self.req("/api/state", host="evil.example.com")[0], 403)
        code, page, headers = self.req("/", token=False, raw=True)
        self.assertEqual(code, 200)
        html = page.decode("utf-8")
        self.assertIn(self.app.token, html)
        self.assertNotRegex(html, r"__[A-Z]+__")                # 자리표시자가 모두 채워졌다
        self.assertIn(".flow .n-box{", html)                    # SVG 규칙은 flow1_graph.SVG_CSS 한 곳에서
        for h, v in (("X-Content-Type-Options", "nosniff"), ("X-Frame-Options", "DENY"), ("Referrer-Policy", "no-referrer")):
            self.assertEqual(headers.get(h), v)
        self.assertEqual(self.req("/api/paste", {"text": "x"}, ctype="text/plain")[0], 415)
        self.assertEqual(self.req("/api/nothing")[0], 404)

    def test_state_graph_detail(self):
        code, st, _ = self.req("/api/state")
        self.assertEqual(code, 200)
        self.assertEqual(sorted(f["name"] for f in st["files"]),
                         ["daily_sales.py", "helpers.py", "run_demo.py", "run_helper.py", "stock_check.ipynb"])
        key = next(f["key"] for f in st["files"] if f["name"] == "daily_sales.py")
        code, g, _ = self.req(f"/api/graph?f={key}&d=2")
        self.assertEqual((code, g["stats"]["queries"]), (200, 6))
        self.assertTrue(g["svg"].startswith("<svg"))
        code, all_g, _ = self.req("/api/graph?f=all&d=1")
        self.assertEqual(all_g["stats"]["queries"], 19)
        code, d, _ = self.req(f"/api/detail?f={key}&id=q3")
        self.assertEqual((code, d["kind"], d["item"]["var"]), (200, "query", "df_items"))
        self.assertEqual(d["columns"]["dw.products"], ["category", "product_id"])
        self.assertIn(["dw.order_items", "tbl"], d["spans"])
        code, t, _ = self.req(f"/api/detail?f={key}&id=t:dw.orders")
        self.assertEqual([r["n"] for r in t["readers"]], [1, 2])
        code, j, _ = self.req(f"/api/detail?f={key}&id=j1")
        self.assertEqual((j["kind"], j["item"]["how"]), ("op", "inner"))
        self.assertEqual(self.req(f"/api/detail?f={key}&id=zz")[0], 404)
        self.assertEqual(self.req("/api/graph?f=nokey")[0], 404)
        code, svg, headers = self.req(f"/api/svg?f={key}&d=3&theme=light", raw=True)
        self.assertEqual(code, 200)
        self.assertIn("image/svg+xml", headers.get("Content-Type"))
        self.assertIn(b"--fbg:#d4d6d8", svg)

    def test_explorer_open_close_watch(self):
        code, d, _ = self.req("/api/browse?path=" + urllib.request.quote(EX))
        self.assertEqual(code, 200)
        self.assertTrue(all(i["watched"] for i in d["items"]))
        other = os.path.join(self.dir, "other.py")
        with open(other, "w", encoding="utf-8") as f:
            f.write('import demo_query as dq\nq = dq.query("SELECT a FROM s.other")\n')
        code, st, _ = self.req("/api/open", {"path": other})
        self.assertEqual(code, 200)
        f = next(f for f in st["files"] if f["key"] == st["opened"])
        self.assertTrue(f["opened"])
        self.assertEqual(self.req("/api/close", {"key": st["opened"]})[1]["files"][-1]["name"], "stock_check.ipynb")
        self.assertEqual(self.req("/api/open", {"path": os.path.join(self.dir, "none.py")})[0], 400)
        code, st, _ = self.req("/api/watch", {"add": self.dir})
        self.assertIn("other.py", [f["name"] for f in st["files"]])
        code, st, _ = self.req("/api/watch", {"remove": self.dir})
        self.assertNotIn("other.py", [f["name"] for f in st["files"]])

    def test_paste_over_http_stays_in_memory(self):
        code, st, _ = self.req("/api/paste", {"text": f'import demo_query as dq\n# {MARK}\nx = dq.query("SELECT 1 FROM s.t")\n'})
        self.assertEqual(code, 200)
        self.assertTrue(st["added"].startswith("p"))
        self.assertFalse(disk_has(self.home, MARK))
        self.assertEqual(self.req("/api/paste/delete", {"key": st["added"]})[0], 200)
        self.assertEqual(self.req("/api/paste/delete", {"key": st["added"]})[0], 404)

    def test_config_changes_from_other_windows_are_picked_up(self):
        other = os.path.join(self.dir, "later.py")
        with open(other, "w", encoding="utf-8") as f:
            f.write('import demo_query as dq\nq = dq.query("SELECT a FROM s.later")\n')
        time.sleep(0.05)
        fa.watch_edit(self.cfg_path, [other], [])             # --run · 다른 창의 경로 더하기가 하는 일
        self.assertTrue(self.app.reload_config())
        self.assertIn("later.py", [f["name"] for f in self.app.state()["files"]])
        self.assertFalse(self.app.reload_config())            # 바뀐 것이 없으면 다시 읽지 않는다
        fa.set_config_values(self.cfg_path, ["query.calls=fetch_only"])
        self.assertTrue(self.app.reload_config())
        self.assertEqual(self.app.cfg["query"]["calls"], ["fetch_only"])

    def test_idle_exit(self):
        self.app.cfg["idle_exit_min"] = 1
        self.assertFalse(self.app.idle_should_exit(self.app.last_seen + 30))
        self.assertTrue(self.app.idle_should_exit(self.app.last_seen + 61))
        self.app.cfg["idle_exit_min"] = 0
        self.assertFalse(self.app.idle_should_exit(self.app.last_seen + 10 ** 6))


class Assets(unittest.TestCase):
    def test_theme_values_match_ui(self):
        with open(os.path.join(ROOT, "ui.html"), encoding="utf-8") as f:
            html = f.read()
        dark = html[html.index(":root{"):html.index('}', html.index(":root{"))]
        light = html[html.index(':root[data-theme="light"]{'):]
        light = light[:light.index("}")]

        def var(block, name):
            m = re.search(re.escape(name) + r":(#[0-9a-fA-F]{3,6})", block)
            return m.group(1).lower() if m else None

        for name, value in flow1_graph.THEMES["dark"].items():
            self.assertEqual(var(dark, name), value, name)
        for name, value in flow1_graph.THEMES["light"].items():
            self.assertEqual(var(light, name) or var(dark, name), value, name)

    def test_build_is_in_sync(self):
        p = subprocess.run([sys.executable, os.path.join(ROOT, "build.py"), "--check"], capture_output=True)
        self.assertEqual(p.returncode, 0, p.stdout.decode("utf-8", "replace"))


if __name__ == "__main__":
    unittest.main()
