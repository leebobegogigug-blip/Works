# -*- coding: utf-8 -*-
"""flow1_scan 테스트 — 파이썬 · 노트북에서 쿼리와 흐름 찾기. 예시 코드 · 테이블 · 패키지 이름은 모두 지어낸 것 (W-12)"""
import json
import os
import shutil
import sys
import tempfile
import textwrap
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import flow1_scan as sc  # noqa: E402

EX = os.path.join(HERE, "examples")
CFG = {"modules": ["demo_query"]}


def scan(code, cfg=None, name="t.py", kind="py", path=""):
    return sc.scan_text(textwrap.dedent(code), name, CFG if cfg is None else cfg, kind, path)


def sqls(res):
    return [" ".join(q["sql"].split()) for q in res["queries"]]


class Detect(unittest.TestCase):
    def test_sql_argument_is_enough_without_knowing_the_package(self):
        r = scan("""
            df = spark.sql("SELECT a FROM s.t WHERE a > 1")
            x = run_query(sql="select b from s.u")
            helper.fetch_all('''
                SELECT c FROM s.v
            ''')
        """, cfg={})
        self.assertEqual([(q["call"], q["var"]) for q in r["queries"]],
                         [("spark.sql", "df"), ("run_query", "x"), ("helper.fetch_all", "")])

    def test_handling_sql_text_is_not_running_it(self):
        r = scan("""
            import logging
            sql = "SELECT a FROM s.t"
            print(sql)
            logging.info(sql)
            log.debug("SELECT b FROM s.u")
            queries = []
            queries.append(sql)
            f.write(sql)
            st.selectbox("Select files from the list", files)
        """, cfg={})
        self.assertEqual(r["queries"], [])

    def test_package_calls_with_unknown_sql_need_the_package_name(self):
        code = """
            import demo_query as dq
            from demo_query import Client
            def go(sql):
                return dq.query(sql)
            c = Client("prod")
            with dq.connect() as conn:
                df = conn.execute(get_sql())
            other.query(get_sql())
        """
        r = scan(code)
        self.assertEqual([(q["call"], q["dynamic"]) for q in r["queries"]], [("conn.execute", True), ("dq.query", True)])
        self.assertEqual(r["queries"][1]["scope"], "def go")        # 부르지 않은 함수 안 — 매개변수가 자리로
        self.assertEqual(r["queries"][1]["sql"], "{sql}")
        self.assertEqual(scan(code, cfg={})["queries"], [])          # 패키지 이름을 모르면 SQL 모양 인자만

    def test_sql_argument_is_picked_by_keyword_name(self):
        r = scan("""
            import demo_query as dq
            dq.query(hive_sql=make_sql(), timeout=30)
            dq.query(conn, sql=build())
            dq.query(query_timeout=30, sql_text=text_of())
        """)
        self.assertEqual([q["sql"] for q in r["queries"]], ["{make_sql}", "{build}", "{text_of}"])

    def test_pandas_read_sql_is_known(self):
        r = scan("""
            import pandas as pd
            from pandas import read_sql_query
            a = pd.read_sql(make_sql(), con)
            b = read_sql_query(q, con)
        """, cfg={})
        self.assertEqual([q["call"] for q in r["queries"]], ["pd.read_sql", "read_sql_query"])


class Strings(unittest.TestCase):
    def test_fstring_constants_are_inlined_unknowns_become_placeholders(self):
        r = scan("""
            START = "2026-09-01"
            n = 10
            df = dq.query(f"SELECT a FROM s.t WHERE dt >= '{START}' AND k = {key} LIMIT {n}")
        """)
        q = r["queries"][0]
        self.assertEqual(q["sql"], "SELECT a FROM s.t WHERE dt >= '2026-09-01' AND k = {key} LIMIT 10")
        self.assertEqual([p["name"] for p in q["params"]], ["key"])

    def test_format_percent_concat_dedent_strip_replace(self):
        r = scan('''
            import textwrap
            base = "SELECT a FROM s.t"
            sql = base + " WHERE x = 1"
            sql += " AND y = '%s'" % day
            q1 = dq.query(sql)
            q2 = dq.query("SELECT {} FROM {tbl} WHERE z = {z!r}".format(col, tbl="s.u", z=zval))
            q3 = dq.query(textwrap.dedent("""
                SELECT b
                FROM s.v
            """).strip().replace("s.v", "s.w"))
            q4 = dq.query("SELECT %(c)s FROM s.x WHERE d = %(d)s" % {"c": "col1", "d": dval})
        ''')
        self.assertEqual(sqls(r), ["SELECT a FROM s.t WHERE x = 1 AND y = '{day}'", "SELECT {col} FROM s.u WHERE z = {zval}",
                                   "SELECT b FROM s.w", "SELECT col1 FROM s.x WHERE d = {dval}"])
        self.assertEqual([q["sql_src"] for q in r["queries"]], ["concat", "format", "literal", "percent"])

    def test_join_of_query_result_becomes_named_placeholder_with_dependency(self):
        r = scan("""
            vip = dq.query("SELECT cust_id FROM dw.vip")
            ids = "','".join(vip.cust_id.astype(str))
            df = dq.query(f"SELECT * FROM dw.orders WHERE cust_id IN ('{ids}')")
            n = len(df)
            top = dq.query(f"SELECT * FROM dw.orders ORDER BY amount DESC LIMIT {n}")
        """)
        self.assertEqual(r["queries"][1]["sql"], "SELECT * FROM dw.orders WHERE cust_id IN ('{ids}')")
        self.assertEqual([(e["from"], e["to"], e["kind"], e["label"]) for e in r["edges"]],
                         [("q1", "q2", "param", "ids"), ("q2", "q3", "param", "n")])

    def test_literal_list_join_and_dict_lookup(self):
        r = scan("""
            cols = ", ".join(["a", "b", "c"])
            SQL = {"t": "SELECT %s FROM s.t", "u": "SELECT x FROM s.u"}
            q1 = dq.query(SQL["t"] % cols)
            q2 = dq.query(SQL.get("u"))
        """)
        self.assertEqual(sqls(r), ["SELECT a, b, c FROM s.t", "SELECT x FROM s.u"])


class SqlFiles(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="flow1-scan-")
        os.makedirs(os.path.join(self.dir, "sql"))
        with open(os.path.join(self.dir, "sql", "a.sql"), "w", encoding="utf-8") as f:
            f.write("-- 설명\nSELECT a FROM s.from_file")
        with open(os.path.join(self.dir, "secret.env"), "w", encoding="utf-8") as f:
            f.write("SELECT nothing FROM s.never")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_sql_files_next_to_the_script(self):
        path = os.path.join(self.dir, "job.py")
        r = scan("""
            import os
            from pathlib import Path
            import demo_query as dq
            HERE = os.path.dirname(os.path.abspath(__file__))
            with open(os.path.join(HERE, "sql", "a.sql"), encoding="utf-8") as f:
                a = dq.query(f.read())
            b = dq.query(open("sql/a.sql").read())
            c = dq.query((Path(__file__).parent / "sql" / "a.sql").read_text())
            d = dq.query(open("secret.env").read())
            e = dq.query(open("sql/missing.sql").read())
        """, path=path)
        self.assertEqual([q["sql_src"] for q in r["queries"]], ["file:sql/a.sql"] * 3 + ["dynamic", "dynamic"])
        self.assertEqual(r["queries"][0]["reads"][0]["name"], "s.from_file")
        self.assertEqual(r["sql_files"], [os.path.join(self.dir, "sql", "a.sql")])     # .sql · .hql · .txt 만 읽는다
        self.assertTrue(any("missing.sql" in w for w in r["warnings"]))

    def test_package_call_that_takes_a_sql_file_path(self):
        r = scan("""
            from pathlib import Path
            import demo_query as dq
            dq.run_file("sql/a.sql")
            dq.run_file(sql_path=Path(__file__).parent / "sql" / "a.sql")
            dq.run_file("sql/missing.sql")
        """, cfg={"modules": ["demo_query"], "calls": ["run_file"]}, path=os.path.join(self.dir, "job.py"))
        self.assertEqual([q["sql_src"] for q in r["queries"]], ["file:sql/a.sql", "file:sql/a.sql", "literal"])
        self.assertEqual([x["name"] for x in r["queries"][1]["reads"]], ["s.from_file"])
        self.assertEqual(r["queries"][2]["sql"], "sql/missing.sql")          # 못 읽으면 경로를 그대로 보인다
        self.assertTrue(any("missing.sql" in w for w in r["warnings"]))


class Flow(unittest.TestCase):
    def test_merge_join_concat_inputs_and_outputs(self):
        r = scan("""
            import pandas as pd
            a = dq.query("SELECT k, x FROM s.a")
            b = dq.query("SELECT k, y FROM s.b")
            m = pd.read_csv("master.csv")
            ab = a.merge(b, on=["k"], how="left")
            abm = pd.merge(ab, m, left_on="k", right_on="code")
            j = ab.join(m.set_index("code"), on="k")
            allx = pd.concat([a, b], axis=1)
            s = ",".join(names)
            abm.to_csv("out.csv")
            allx.to_sql("daily", con, schema="mart")
        """)
        ops = [(o["id"], o["kind"], o["how"], o["on"], o["left_on"], o["right_on"], o["var"]) for o in r["ops"]]
        self.assertEqual(ops, [("j1", "merge", "left", ["k"], [], [], "ab"),
                               ("j2", "merge", "inner", [], ["k"], ["code"], "abm"),
                               ("j3", "join", "left", ["k"], [], [], "j"),
                               ("j4", "concat", "axis=1", [], [], [], "allx")])
        self.assertEqual([(i["kind"], i["target"], i["var"]) for i in r["inputs"]], [("read_csv", "master.csv", "m")])
        self.assertEqual([(o["kind"], o["target"], o.get("table")) for o in r["outputs"]],
                         [("to_csv", "out.csv", None), ("to_sql", "daily", {"key": "mart.daily", "name": "mart.daily"})])
        edges = [(e["from"], e["to"], e.get("side", "")) for e in r["edges"]]
        self.assertIn(("q1", "j1", "L"), edges)
        self.assertIn(("q2", "j1", "R"), edges)
        self.assertIn(("i1", "j2", "R"), edges)
        self.assertIn(("j2", "o1", ""), edges)
        self.assertEqual(r["stats"]["joins"], 3)

    def test_functions_are_read_at_each_call_site(self):
        r = scan("""
            def run(sql):
                print(sql)
                return dq.query(sql)
            def month(m):
                return run(f"SELECT * FROM s.orders WHERE ym = '{m}'")
            def never(x):
                return dq.query(f"SELECT * FROM s.never WHERE x = {x}")
            def loop(n):
                return loop(n)
            jan = month("2026-01")
            feb = month("2026-02")
            loop(1)
        """)
        self.assertEqual([(q["var"], q["line"], q["via"], q["scope"]) for q in r["queries"]],
                         [("jan", 11, "month() › run() L4", "def run"), ("feb", 12, "month() › run() L4", "def run"),
                          ("", 8, "", "def never")])
        self.assertEqual(sqls(r)[:2], ["SELECT * FROM s.orders WHERE ym = '2026-01'",
                                       "SELECT * FROM s.orders WHERE ym = '2026-02'"])
        self.assertEqual(r["queries"][2]["sql"], "SELECT * FROM s.never WHERE x = {x}")

    def test_loops_unroll_lists_and_dicts(self):
        r = scan("""
            for t in ["s.a", "s.b"]:
                dq.query(f"SELECT COUNT(*) FROM {t}")
            Q = {"x": "SELECT 1 FROM s.x", "y": "SELECT 2 FROM s.y"}
            out = {}
            for k, sql in Q.items():
                out[k] = dq.query(sql)
            for row in rows:
                dq.query(f"SELECT * FROM s.z WHERE id = {row}")
        """)
        self.assertEqual([q["reads"][0]["name"] for q in r["queries"]], ["s.a", "s.b", "s.x", "s.y", "s.z"])
        self.assertTrue(all(q["loop"] for q in r["queries"]))
        self.assertEqual(r["queries"][2]["var"], "out[k]")

    def test_if_branches_both_count(self):
        r = scan("""
            if full:
                sql = "SELECT * FROM s.big"
            else:
                sql = "SELECT * FROM s.small"
            df = dq.query(sql)
            if debug:
                dq.query("SELECT 1 FROM s.debug")
        """)
        self.assertEqual([q["sql"] for q in r["queries"]], ["SELECT * FROM s.big", "SELECT 1 FROM s.debug"])
        self.assertTrue(r["queries"][1]["branch"])

    def test_class_methods_through_instances(self):
        r = scan("""
            from demo_query import Client
            class Loader:
                def __init__(self):
                    self.cli = Client("dev")
                    self.base = "SELECT a FROM s.c"
                def get(self, g):
                    return self.cli.fetch(self.base + f" WHERE g = '{g}'")
            ld = Loader()
            gold = ld.get("GOLD")
        """, cfg={"modules": ["demo_query"], "calls": ["fetch"]})
        self.assertEqual([(q["var"], q["sql"], q["call"]) for q in r["queries"]],
                         [("gold", "SELECT a FROM s.c WHERE g = 'GOLD'", "self.cli.fetch")])

    def test_node_limit(self):
        code = "\n".join(f"dq.query('SELECT {i} FROM s.t')" for i in range(sc.MAX_NODES + 5))
        r = scan(code)
        self.assertEqual(len(r["queries"]), sc.MAX_NODES)
        self.assertTrue(r["warnings"])


class Files(unittest.TestCase):
    def test_syntax_error_and_cp949(self):
        r = scan("def f(:\n  pass")
        self.assertTrue(r["error"].startswith("문법 오류"))
        d = tempfile.mkdtemp(prefix="flow1-enc-")
        try:
            p = os.path.join(d, "old.py")
            with open(p, "wb") as f:
                f.write('# 한글 주석\ndf = dq.query("SELECT 이름 FROM s.고객")\n'.encode("cp949"))
            r = sc.scan_file(p, CFG)
            self.assertEqual(r["queries"][0]["reads"][0]["name"], "s.고객")
            r = sc.scan_file(os.path.join(d, "none.py"), CFG)
            self.assertIn("파일을 읽지 못했습니다", r["error"])
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_notebook_cells_magics_and_sql_cells(self):
        r = sc.scan_file(os.path.join(EX, "stock_check.ipynb"), CFG)
        self.assertEqual(r["error"], "")
        self.assertEqual([(q["var"], q["call"], q["cell"]) for q in r["queries"]],
                         [("low", "%%sql", 2), ("recent", "dq.query", 3), ("check", "dq.query", 6)])
        self.assertEqual([(e["from"], e["to"], e["label"]) for e in r["edges"] if e["kind"] == "param"], [("q1", "q2", "ids")])
        self.assertTrue(any("셀 5" in w for w in r["warnings"]))
        self.assertEqual(len(r["cells"]), 6)

    def test_notebook_json_error(self):
        r = scan("{not json", kind="ipynb", name="x.ipynb")
        self.assertIn("노트북", r["error"])

    def test_plain_sql_file(self):
        r = sc.scan_text("SELECT a FROM x.y JOIN x.z ON y.k = z.k WHERE a > 1", "붙여 넣기", {}, "sql")
        self.assertEqual((r["stats"]["queries"], r["stats"]["tables"], r["stats"]["joins"]), (1, 2, 1))


class Examples(unittest.TestCase):
    """tests/examples — 데모 · 문서 · 가이드가 같이 쓰는 지어낸 스크립트"""

    def test_daily_sales(self):
        r = sc.scan_file(os.path.join(EX, "daily_sales.py"), CFG)
        self.assertEqual(r["stats"], {"queries": 6, "tables": 6, "joins": 5, "conds": 9, "ops": 3, "inputs": 0,
                                      "outputs": 2, "params": 1})
        self.assertEqual([q["var"] for q in r["queries"]], ["df_orders", "df_vip", "df_items", "df_returns", "", "df_trend"])
        self.assertEqual(r["queries"][3]["sql_src"], "file:sql/returns.sql")
        self.assertEqual([w["name"] for w in r["queries"][4]["writes"]], ["tmp.vip_daily"])

    def test_helpers(self):
        r = sc.scan_file(os.path.join(EX, "helpers.py"), CFG)
        self.assertEqual(len(r["queries"]), 7)
        self.assertEqual(r["queries"][6]["var"], "gold")

    def test_result_is_json(self):
        for name in ("daily_sales.py", "helpers.py", "stock_check.ipynb"):
            r = sc.scan_file(os.path.join(EX, name), CFG)
            self.assertEqual(json.loads(json.dumps(r))["format"], sc.FORMAT)


if __name__ == "__main__":
    unittest.main()
