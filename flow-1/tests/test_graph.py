# -*- coding: utf-8 -*-
"""flow1_graph 테스트 — 카드 줄 · 배치 · 간선 · SVG · 글 요약(골든). 예시는 모두 지어낸 것 (W-12)

골든 파일(tests/golden/*.txt)은 --scan 글 요약의 정답이다. 분석 규칙을 일부러 바꿨을 때만, 사람이 차이를 보고 승인한 뒤
  FLOW_GOLDEN_WRITE=1 python -m unittest tests.test_graph                         (bash)
  $env:FLOW_GOLDEN_WRITE=1; python -m unittest tests.test_graph; $env:FLOW_GOLDEN_WRITE=""   (PowerShell)
로 다시 쓴다 (docs/GUIDE.md › 09 작업 절차).
"""
import os
import sys
import time
import unittest
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import flow1_graph as fg  # noqa: E402
import flow1_scan as sc  # noqa: E402

EX = os.path.join(HERE, "examples")
GOLD = os.path.join(HERE, "golden")
CFG = {"modules": ["demo_query"]}
EXAMPLES = ("daily_sales.py", "helpers.py", "stock_check.ipynb")


def res(name):
    return sc.scan_file(os.path.join(EX, name), CFG)


def by_id(g):
    return {n["id"]: n for n in g["nodes"]}


class Measure(unittest.TestCase):
    def test_cells_match_the_embedded_font(self):
        self.assertEqual([fg.cells(s) for s in ("abc", "가나", "①", "●○◐√×", "a가…")], [3, 4, 2, 5, 4])

    def test_clip(self):
        self.assertEqual(fg.clip("abcdef", 6), "abcdef")
        self.assertEqual(fg.clip("abcdefg", 6), "abcde…")
        self.assertEqual(fg.clip("가나다라", 5), "가나…")
        self.assertEqual(fg.cells(fg.clip("가나다라마바", 7)), 7)


class Build(unittest.TestCase):
    def setUp(self):
        self.g = fg.build([res("daily_sales.py")], 2)
        self.n = by_id(self.g)

    def test_nodes_and_edges(self):
        kinds = [n["kind"] for n in self.g["nodes"]]
        self.assertEqual((kinds.count("query"), kinds.count("op"), kinds.count("output"), kinds.count("table")), (6, 3, 2, 8))
        dups = sorted(n["id"] for n in self.g["nodes"] if n.get("dup"))     # 읽기만 하는 테이블은 쓰는 열마다 한 벌
        self.assertEqual(dups, ["t:dw.order_items~2", "t:dw.products~2"])
        self.assertEqual(self.g["stats"]["tables"], 6)
        self.assertEqual(self.n["t:tmp.vip_daily"]["role"], "temp")      # 쓰고 다시 읽는 테이블
        self.assertEqual(len(self.g["edges"]), 19)

    def test_grid_and_no_overlap(self):
        for n in self.g["nodes"]:
            self.assertEqual([v % fg.CELL for v in (n["x"], n["y"], n["w"], n["h"])], [0, 0, 0, 0], n["id"])
        nodes = self.g["nodes"]
        for i, a in enumerate(nodes):
            for b in nodes[i + 1:]:
                apart = a["x"] + a["w"] <= b["x"] or b["x"] + b["w"] <= a["x"] or \
                    a["y"] + a["h"] <= b["y"] or b["y"] + b["h"] <= a["y"]
                self.assertTrue(apart, f"{a['id']} · {b['id']} 가 겹칩니다")

    def test_edges_are_orthogonal_and_touch_node_sides(self):
        for e in self.g["edges"]:
            pts = e["pts"]
            a, b = self.n[e["from"]], self.n[e["to"]]
            self.assertEqual(pts[0][0], a["x"] + a["w"])
            self.assertEqual(pts[-1][0], b["x"])
            self.assertTrue(a["y"] <= pts[0][1] <= a["y"] + a["h"])
            self.assertTrue(b["y"] <= pts[-1][1] <= b["y"] + b["h"])
            for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                self.assertTrue(x0 == x1 or y0 == y1, f"간선 {e['id']} 가 비스듬합니다")
            self.assertLess(a["layer"], b["layer"])                    # 왼쪽 → 오른쪽만

    def test_table_edges_land_on_their_join_rows(self):
        q3 = self.n["q3"]
        rows = [r["lbl"] for r in q3["rows"]]
        e = next(e for e in self.g["edges"] if e["from"].startswith("t:dw.products") and e["to"] == "q3")
        self.assertEqual(e["ty"], fg.HEAD + rows.index("LEFT") * fg.ROW + fg.ROW // 2)
        e = next(e for e in self.g["edges"] if e["kind"] == "param")
        where = next(i for i, r in enumerate(q3["rows"]) if "order_ids" in r["ph"])
        self.assertEqual((e["from"], e["ty"]), ("q1", fg.HEAD + where * fg.ROW + fg.ROW // 2))
        e = next(e for e in self.g["edges"] if e["from"] == "t:dw.orders" and e["to"] == "q2")   # WITH 안의 테이블
        self.assertEqual(self.n["q2"]["rows"][(e["ty"] - fg.HEAD) // fg.ROW]["text"], "spend s")

    def test_detail_levels(self):
        r = res("helpers.py")
        g1, g3 = fg.build([r], 1), fg.build([r], 3)
        q1, q3 = by_id(g1)["q1"], by_id(g3)["q1"]
        self.assertEqual((q1["w"], q3["w"]), (fg.WIDTH[1], fg.WIDTH[3]))
        self.assertEqual([x["lbl"] for x in q1["rows"]], ["FROM"])
        self.assertEqual([x["lbl"] for x in q3["rows"]], ["VIA", "SELECT", "FROM", "WHERE"])
        g3 = fg.build([res("daily_sales.py")], 3)
        self.assertEqual(by_id(g3)["q2"]["rows"][0]["lbl"], "WITH")

    def test_rewrite_same_table_makes_a_new_version_not_a_cycle(self):
        r = sc.scan_text('import demo_query as dq\n'
                         'dq.execute("INSERT OVERWRITE TABLE s.t SELECT * FROM s.t WHERE a > 0")\n'
                         'x = dq.query("SELECT * FROM s.t")\n', "t.py", CFG)
        g = fg.build([r])
        n = by_id(g)
        self.assertIn("t:s.t#2", n)
        self.assertEqual(sorted((e["from"], e["to"]) for e in g["edges"]),
                         [("q1", "t:s.t#2"), ("t:s.t", "q1"), ("t:s.t#2", "q2")])
        self.assertTrue(all(not e["back"] for e in g["edges"]))

    def test_multi_file_shares_tables(self):
        g = fg.build([res("daily_sales.py"), res("stock_check.ipynb")], 1)
        n = by_id(g)
        self.assertIn("f0:q1", n)
        self.assertIn("f1:q1", n)
        readers = {e["to"] for e in g["edges"] if e["from"].split("~")[0] == "t:dw.order_items"}
        self.assertTrue({"f0:q3", "f1:q2"} <= readers)
        self.assertTrue(g["multi"])

    def test_run_footer(self):
        r = res("daily_sales.py")
        runs = {"q1": {"state": "ok", "ms": 1234.0, "rows": 12340, "n": 1, "ratio": 0.5},
                "q2": {"state": "err", "err": "Timeout: 300s"}, "q3": {"state": "busy", "since": 1.0}}
        g = fg.build([r], 2, runs)
        n = by_id(g)
        plain = by_id(fg.build([r], 2))
        self.assertGreater(n["q1"]["h"], plain["q1"]["h"])
        s = fg.svg(g)
        self.assertIn("√ 1.2s · 12,340행", s)
        self.assertIn("× Timeout: 300s", s)
        self.assertIn("◐ 실행 중", s)
        self.assertIn("○ 실행 기록 없음", s)


class Svg(unittest.TestCase):
    def test_well_formed_escaped_and_deterministic(self):
        r = sc.scan_text('import demo_query as dq\nx = dq.query("SELECT a FROM s.t WHERE a < 5 AND b = \'&x\' '
                         'AND c = \'<script>\'")\n', "t.py", CFG)
        a = fg.svg(fg.build([r]))
        root = ET.fromstring(a)
        self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
        self.assertNotIn("<script>", a)
        self.assertEqual(a, fg.svg(fg.build([r])))
        g = fg.build([res("daily_sales.py")])
        s = fg.svg(g)
        ET.fromstring(s)
        for n in g["nodes"]:
            self.assertIn(f'data-id="{n["id"]}"', s)

    def test_standalone_has_theme_and_font(self):
        g = fg.build([res("helpers.py")])
        s = fg.svg(g, standalone=True, theme="light", font_b64="AAAA")
        self.assertIn("--card-head:#002341", s)
        self.assertIn("data:font/woff;base64,AAAA", s)
        ET.fromstring(s)
        self.assertEqual(set(fg.THEMES["dark"]), set(fg.THEMES["light"]))

    def test_big_graph_is_fast(self):
        lines = ["import demo_query as dq", "x0 = dq.query('SELECT a FROM s.t0')"]
        for i in range(1, 150):
            lines.append(f"x{i} = dq.query(f\"SELECT a FROM s.t{i % 20} JOIN s.u{i % 7} ON 1 = 1 WHERE a IN ({{x{i - 1}}})\")")
        r = sc.scan_text("\n".join(lines), "big.py", CFG)
        t0 = time.time()
        g = fg.build([r], 2)
        fg.svg(g)
        self.assertEqual(sum(1 for n in g["nodes"] if n["kind"] == "query"), 150)
        self.assertLess(time.time() - t0, 10.0)


class Golden(unittest.TestCase):
    """--scan 글 요약 = tests/golden/*.txt (분석이 한 글자라도 달라지면 실패)"""

    def test_examples(self):
        os.makedirs(GOLD, exist_ok=True)
        for name in EXAMPLES:
            got = fg.summary(res(name))
            path = os.path.join(GOLD, name + ".txt")
            if os.environ.get("FLOW_GOLDEN_WRITE", "").strip() == "1":      # cmd 의 set X=1 && … 은 끝에 공백이 붙는다
                with open(path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(got)
            with open(path, encoding="utf-8") as f:
                want = f.read()
            self.assertEqual(got, want, f"{name} 의 --scan 결과가 골든과 다릅니다 (tests/golden/{name}.txt)")


if __name__ == "__main__":
    unittest.main()
