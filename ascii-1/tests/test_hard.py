# -*- coding: utf-8 -*-
"""HARD 합성 세트와 측정 도구(tools/measure_hard.py) — 이 단계는 세트의 정답이 서로 맞는지 · 결정적인지 · 도구가 도는지만 지킨다.
'지금 값'(NOW)은 기준선 기록이다: 요소 찾기를 일부러 고치면 이 값이 바뀌고, 그때 사람이 보고 고친다.
개선 기대값(AC)은 각 구현 작업이 자기 시험으로 넣는다. 그림은 전부 코드로 만든 것 (W-12)."""
import importlib.util
import os
import sys
import unittest
from math import isnan

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import synth  # noqa: E402

spec = importlib.util.spec_from_file_location("measure_hard", os.path.join(ROOT, "tools", "measure_hard.py"))
mh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mh)

_CASES = {}


def case(name):
    if name not in _CASES:
        _CASES[name] = synth.hard_case(name)
    return _CASES[name]


# 지금(0.2.0) 요소 찾기의 파랑 점 추정 — 기준선. 개수가 정답과 크게 다른 것이 문제 그 자체다 (E0 는 속 빈 원을 4 배 센다)
NOW = {"A0": 56, "E0": 229, "A_base": 102}


class HardSet(unittest.TestCase):
    def test_names(self):
        want = {"A0", "A1", "E0", "E", "F0", "F1", "H", "I", "B0", "C", "D", "J", "J1", "J2", "K", "L", "Z"}
        self.assertTrue(want <= set(synth.HARD))
        self.assertEqual(len(synth.HARD), len(set(synth.HARD)))

    def test_truth_matches_picture(self):
        for name in synth.HARD:
            with self.subTest(name=name):
                c = case(name)
                img = c.image
                self.assertLessEqual(img.width, 800)
                self.assertLessEqual(img.height, 600)
                self.assertEqual(len(img.rgb), 3 * img.width * img.height)
                x0, y0, x1, y1 = c.box
                self.assertTrue(0 < x0 < x1 < img.width and 0 < y0 < y1 < img.height)
                self.assertTrue(all(x0 <= x <= x1 and y0 <= y <= y1 for x, y, _ in c.pts + c.pts2), "점은 그림 상자 안")
                for gx, gy in ((16, 8), (60, 25)):
                    self.assertEqual(sum(c.cell_counts(gx, gy)), c.n, "셀별 개수의 합 = 개수")
                    self.assertEqual(sum(c.cell_counts(gx, gy, 1)), len(c.pts2))
                self.assertEqual(bool(c.trend), c.trend_kind is not None)
                if c.trend:
                    self.assertTrue(all(x0 <= x <= x1 and y0 <= y <= y1 for x, y in c.trend))
                self.assertEqual(c.grid_lines, 38 if c.grid_cells else 0)

    def test_counts_by_design(self):
        n = {k: case(k).n for k in synth.HARD}
        self.assertEqual((n["A0"], n["A1"], n["E0"], n["E"], n["F0"], n["F1"]), (60, 300, 60, 300, 60, 60))
        self.assertEqual((n["H"], n["I"], n["Z"], n["J0"], n["J1"]), (2000, 2000, 2500, 0, 0))
        self.assertEqual(len(case("L").pts2), 150)
        self.assertEqual((case("J").trend_kind, case("J1").trend_kind, case("A0").trend_kind), ("dash", "solid", None))
        for g in ("B0", "C", "D", "Z"):
            self.assertEqual(case(g).grid_lines, 38)
        for g in ("A0", "E", "H", "J", "K", "L"):
            self.assertEqual(case(g).grid_lines, 0, "격자가 없는 변형")

    def test_grid_cells_are_grid_colored(self):
        for name, color in (("B0", synth.LBLUE_GRID), ("D", synth.DGRAY_GRID)):
            c = case(name)
            rgb = c.image.rgb
            self.assertGreater(len(c.grid_cells), 10000)
            self.assertTrue(all(tuple(rgb[3 * i:3 * i + 3]) == color for i in c.grid_cells))

    def test_deterministic(self):
        for name in ("A0", "E0", "J1", "B0"):
            with self.subTest(name=name):
                a, b = synth.hard_case(name), case(name)
                self.assertEqual(a.image.rgb, b.image.rgb)
                self.assertEqual((a.pts, a.trend, a.grid_cells), (b.pts, b.trend, b.grid_cells))

    def test_hollow_has_holes_and_dashes_have_gaps(self):
        c = synth.Canvas(30, 30)
        synth.ring(c, 15, 15, 6, 1, (0, 0, 0))
        self.assertEqual(c.px[15 * 30 + 15], (255, 255, 255), "속은 비어 있다")
        self.assertEqual(c.px[15 * 30 + 21], (0, 0, 0), "테두리는 있다")
        d = synth.Canvas(60, 10)
        synth.dashed(d, [(2.0, 5.0), (58.0, 5.0)], 10, 6, 1, (0, 0, 0))
        row = [d.px[5 * 60 + x] == (0, 0, 0) for x in range(60)]
        self.assertTrue(row[4] and not row[13] and row[20], "10 긋고 6 비운다")


class MeasureTool(unittest.TestCase):
    def test_measure_keys_and_now_values(self):
        for name, est in NOW.items():
            with self.subTest(name=name):
                m = mh.measure(case(name))
                self.assertEqual(m["n"], case(name).n)
                self.assertEqual(m["est"], est, "기준선(NOW)이 바뀌었다 — 의도한 변경이면 값을 고친다")
                self.assertEqual(len(m["R"]), 2)
                self.assertFalse(isnan(m["R"][0]))
                self.assertEqual(len(mh.row(m)), len(mh.HEAD))

    def test_grid_leak_and_trend_measured(self):
        m = mh.measure(case("B0"))
        self.assertIsNotNone(m["leak"])
        self.assertTrue(all(0.0 <= v <= 100.0 for v in m["leak"]))
        self.assertEqual(m["lines_true"], 38)
        t = mh.measure(case("J1"))
        self.assertIsNotNone(t["trend"])
        self.assertIsNone(mh.measure(case("A0"))["trend"])

    def test_table_shape(self):
        out = mh.table([mh.row(mh.measure(case("A0")))])
        lines = out.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("이름"))

    def test_main_unknown_name(self):
        import io
        from contextlib import redirect_stderr
        with redirect_stderr(io.StringIO()):
            self.assertEqual(mh.main(["없는변형"]), 2)


if __name__ == "__main__":
    unittest.main()
