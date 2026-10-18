# -*- coding: utf-8 -*-
"""렌더 · 명령의 격자 표시(--grid hide · dots · ticks · show) · 그림 상자 틀 · 우선순위 표 · 추세선과 밀도 · 범례 문구 (설계서 14-11 · AC12).
격자가 없는 그림은 옵션과 상관없이 바이트까지 그대로다 (골든 3 개는 test_render 가 본다). 그림은 전부 코드로 만든 것 (W-12)"""
import os
import sys
import tempfile
import unittest
from math import cos, sin

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import ascii1_render as rd  # noqa: E402
import ascii1_seg as sg  # noqa: E402
import synth  # noqa: E402
import test_cli as tc  # noqa: E402

MODES = ("hide", "dots", "ticks", "show")
GRIDDED = ("B0", "C", "D", "Z")
WIDTHS = (40, 120, 300)
TREND_GLYPHS = set("_-/\\|")

_SEGS = {}


def seg_of(name):
    if name not in _SEGS:
        _SEGS[name] = sg.segment(synth.hard_case(name).image)
    return _SEGS[name]


def art(text):
    return text.rsplit("\n\n", 1)[0].split("\n") if "\n\n" in text else []


def legend(text):
    return text.rsplit("\n\n", 1)[-1]


def frame_of(seg, geo):
    """시험 쪽에서 따로 셈한 틀: 가장 바깥 격자줄 넷이 놓인 셀 (행 위 · 아래, 열 왼 · 오른)"""
    g = seg.grid
    x0, x1 = g.vertical[0].pos + 0.5, g.vertical[-1].pos + 0.5
    y0, y1 = g.horizontal[0].pos + 0.5, g.horizontal[-1].pos + 0.5
    (rt, cl), (rb, cr) = geo.cell_xy(x0, y0), geo.cell_xy(x1, y1)
    return rt, rb, cl, cr


def frame_cells(rt, rb, cl, cr):
    out = {}
    for c in range(cl, cr + 1):
        out[(rt, c)] = out[(rb, c)] = "-"
    for r in range(rt, rb + 1):
        out[(r, cl)] = out[(r, cr)] = "|"
    for corner in ((rt, cl), (rt, cr), (rb, cl), (rb, cr)):
        out[corner] = "+"
    return out


def grid_rows_cols(seg, geo):
    g = seg.grid
    rows = sorted({geo.cell_xy(0, ln.pos + 0.5)[0] for ln in g.horizontal})
    cols = sorted({geo.cell_xy(ln.pos + 0.5, 0)[1] for ln in g.vertical})
    return rows, cols


def pearson(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    sab = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    sa = sum((x - ma) ** 2 for x in a) ** 0.5
    sb = sum((y - mb) ** 2 for y in b) ** 0.5
    return sab / (sa * sb)


POINTS = set("".join("".join(s) for s in rd.POINT_SETS))


class GridModes(unittest.TestCase):
    """격자가 있는 HARD 변형 (연한 격자 B0 · C · Z, 진한 격자 D) — 가로 17 · 세로 21 줄"""

    def layout(self, name, mode, width=120):
        seg = seg_of(name)
        cells, geo = rd.layout(seg, width, grid=mode)
        return seg, cells, geo

    def test_hide_draws_only_the_frame(self):
        for name in GRIDDED:
            with self.subTest(name=name):
                seg, cells, geo = self.layout(name, "hide")
                want = frame_cells(*frame_of(seg, geo))
                for cell, ch in want.items():
                    self.assertIn(cell, cells, "틀 셀이 비었다 %s" % (cell,))
                    prio, got = cells[cell]
                    if prio == 3:
                        self.assertEqual(got, ch, cell)
                    else:
                        self.assertGreater(prio, 3, "틀은 점 · 노치에만 진다 %s %s" % (cell, cells[cell]))
                self.assertEqual({c for c, v in cells.items() if v[0] == 3}, {c for c in want if cells[c][0] == 3},
                                 "hide 에서 우선순위 3 은 틀뿐 (이 변형에는 가로 · 세로선이 없다)")
                self.assertFalse([c for c, v in cells.items() if v[0] == 0], "hide 는 격자 글자를 그리지 않는다")

    def test_hide_text_has_two_frame_rows_and_the_legend_line(self):
        for name in GRIDDED:
            with self.subTest(name=name):
                text = rd.render(seg_of(name), 120)
                lines = art(text)
                width = max(len(x) for x in lines)
                self.assertGreaterEqual(width, 0.9 * 120, "틀이 내용 상자에 들어간다")
                self.assertEqual(len([x for x in lines if x.count("-") >= 0.5 * width]), 2, "\n".join(lines))
                cols = [c for c in range(width) if sum(1 for x in lines if c < len(x) and x[c] == "|") >= 0.5 * len(lines)]
                self.assertEqual(len(cols), 2)
                self.assertLessEqual("\n".join(lines).count("+"), 4, "+ 는 틀의 네 모서리뿐 — 안쪽에 격자 교차가 없다")
                self.assertIn("- | 그림 상자 · 격자 가로 17 · 세로 21 줄 생략", legend(text))
                self.assertNotIn("격자 교차점", text)

    def test_show_draws_every_grid_line_under_the_data(self):
        for name in GRIDDED:
            with self.subTest(name=name):
                seg, cells, geo = self.layout(name, "show")
                rows, cols = grid_rows_cols(seg, geo)
                rt, rb, cl, cr = frame_of(seg, geo)
                low = {c: ch for c, (p, ch) in cells.items() if p == 0}
                self.assertTrue(low)
                for (r, c), ch in low.items():
                    on_h, on_v = r in rows and cl <= c <= cr, c in cols and rt <= r <= rb
                    self.assertTrue(on_h or on_v, "격자 글자가 격자줄 밖에 %s" % ((r, c),))
                    self.assertEqual(ch, "+" if on_h and on_v else ("-" if on_h else "|"), (r, c))
                for r in rows:
                    for c in range(cl, cr + 1):
                        self.assertIn((r, c), cells, "격자줄 셀이 비었다")
                self.assertFalse([c for c, v in cells.items() if v[0] == 3], "show 에는 따로 그리는 틀이 없다")
                text = rd.render(seg, 120, grid="show")
                self.assertIn("- | + 격자 (가로 17 · 세로 21 줄)", legend(text))
                self.assertNotIn("생략", text)
                self.assertNotIn("그림 상자", text)

    def test_show_text_has_the_grid_rows(self):
        seg = seg_of("B0")
        geo = rd.Geometry(seg, 120)
        rows, cols = grid_rows_cols(seg, geo)
        lines = art(rd.render(seg, 120, grid="show"))
        width = max(len(x) for x in lines)
        self.assertEqual(len([x for x in lines if x.count("-") >= 0.5 * width]), len(rows))
        vert = [c for c in range(width) if sum(1 for x in lines if c < len(x) and x[c] == "|") >= 0.4 * len(lines)]
        self.assertEqual(len(vert), len(cols))
        self.assertIn("+-----+", "\n".join(lines))

    def test_dots_marks_crossings_only(self):
        for name in GRIDDED:
            with self.subTest(name=name):
                seg, cells, geo = self.layout(name, "dots")
                rows, cols = grid_rows_cols(seg, geo)
                hide, _ = rd.layout(seg, 120, grid="hide")
                low = {c: ch for c, (p, ch) in cells.items() if p == 0}
                self.assertTrue(set(low.values()) <= {"."})
                self.assertTrue(all(r in rows and c in cols for r, c in low), "점은 격자 교차 셀에만")
                free = [(r, c) for r in rows for c in cols if (r, c) not in hide]
                self.assertTrue(free)
                self.assertEqual(sorted(low), sorted(free), "비어 있는 교차 셀마다 . 하나")
                self.assertEqual({c: v for c, v in cells.items() if v[0] > 0}, hide, "나머지는 hide 와 같다")
                text = rd.render(seg, 120, grid="dots")
                self.assertIn("- | 그림 상자 · . 격자 교차점 (가로 17 · 세로 21 줄)", legend(text))

    def test_ticks_marks_the_frame_at_grid_lines(self):
        for name in GRIDDED:
            with self.subTest(name=name):
                seg, cells, geo = self.layout(name, "ticks")
                rows, cols = grid_rows_cols(seg, geo)
                rt, rb, cl, cr = frame_of(seg, geo)
                frame = frame_cells(rt, rb, cl, cr)
                marks = {(rt, c) for c in cols} | {(rb, c) for c in cols} | {(r, cl) for r in rows} | {(r, cr) for r in rows}
                self.assertFalse([c for c, v in cells.items() if v[0] == 0], "ticks 는 안쪽에 아무것도 깔지 않는다")
                three = {c: ch for c, (p, ch) in cells.items() if p == 3}
                self.assertTrue(set(three) <= set(frame), "눈금은 틀 위에만")
                for c, ch in three.items():
                    self.assertEqual(ch, "+" if c in marks or frame[c] == "+" else frame[c], c)
                self.assertGreaterEqual(sum(1 for c in marks if three.get(c) == "+"), 0.8 * len(marks))
                text = rd.render(seg, 120, grid="ticks")
                self.assertIn("- | 그림 상자 · + 틀 위의 격자 자리 (가로 17 · 세로 21 줄)", legend(text))

    def test_points_and_trend_are_the_same_in_every_mode(self):
        for name in GRIDDED:
            with self.subTest(name=name):
                seg = seg_of(name)
                base, _ = rd.layout(seg, 120, grid="hide")
                top = {c: v for c, v in base.items() if v[0] >= 4}
                for mode in MODES[1:]:
                    cells, _ = rd.layout(seg, 120, grid=mode)
                    self.assertEqual({c: v for c, v in cells.items() if v[0] >= 4}, top, mode)

    def test_box_option_turns_the_frame_into_box_glyphs(self):
        text = rd.render(seg_of("B0"), 120, box=True)
        a = "\n".join(art(text))
        self.assertIn("─", a)
        self.assertIn("│", a)
        self.assertIn("┼", a)
        self.assertIn("─ │ 그림 상자 · 격자 가로 17 · 세로 21 줄 생략", legend(text))
        text = rd.render(seg_of("B0"), 120, box=True, grid="dots")
        self.assertIn(".", "\n".join(art(text)), "--box 는 - | + 만 바꾼다")

    def test_unknown_mode_is_refused(self):
        with self.assertRaises(ValueError):
            rd.render(seg_of("B0"), 120, grid="lines")


class EveryOutput(unittest.TestCase):
    """모든 변형 · 모드 · 열 수: 순수 ASCII · 열 수 ≤ --width · 같은 입력이면 같은 바이트"""

    def test_ascii_width_and_determinism(self):
        for name in GRIDDED + ("A_base", "J0"):
            seg = seg_of(name)
            for mode in MODES:
                for width in WIDTHS:
                    with self.subTest(name=name, mode=mode, width=width):
                        text = rd.render(seg, width, grid=mode)
                        lines = art(text)
                        self.assertTrue(lines)
                        self.assertLessEqual(max(len(x) for x in lines), width)
                        self.assertTrue(all(0x20 <= ord(ch) <= 0x7E for x in lines for ch in x))
                        self.assertTrue(all(x == x.rstrip() for x in lines))
                        self.assertEqual(text, rd.render(seg, width, grid=mode))
                        self.assertIn("→ %d열 %d행" % (max(len(x) for x in lines), len(lines)), legend(text))

    def test_fresh_segmentation_gives_the_same_bytes(self):
        self.assertEqual(rd.render(sg.segment(synth.hard_case("B0").image), 120), rd.render(seg_of("B0"), 120))


class WithoutGrid(unittest.TestCase):
    """격자가 없는 그림에서 --grid 는 아무것도 바꾸지 않는다"""

    def test_same_bytes_in_every_mode(self):
        segs = [sg.segment(synth.control_chart()[0]), sg.segment(synth.wafer_map(plus=3)[0]),
                sg.segment(synth.control_chart(frame=True)[0]), sg.segment(synth.line_chart()[0]),
                seg_of("A_base"), seg_of("H"), seg_of("J1")]
        for seg in segs:
            self.assertIsNone(seg.grid)
            for width in WIDTHS:
                plain = rd.render(seg, width)
                for mode in MODES:
                    with self.subTest(width=width, mode=mode):
                        self.assertEqual(rd.render(seg, width, grid=mode), plain)
                        self.assertNotIn("격자", plain)

    def test_golden_with_every_mode(self):
        for name, img, width in (("chart_100.txt", synth.control_chart()[0], 100), ("wafer_100.txt", synth.wafer_map(plus=3)[0], 100),
                                 ("wafer_40.txt", synth.wafer_map(plus=3)[0], 40)):
            with open(os.path.join(HERE, "golden", name), encoding="utf-8", newline="") as f:
                gold = f.read()
            seg = sg.segment(img)
            for mode in MODES:
                with self.subTest(name=name, mode=mode):
                    self.assertEqual(rd.render(seg, width, grid=mode), gold)


def scene(ring=False):
    """손으로 놓은 격자 그림 200×100: 상자 (10, 10)–(189, 89), 세로 5 줄 · 가로 5 줄. 열 수 100 이면 셀 1.8 × 3.6 px 이고
    틀이 셀 (0, 0) 에서 시작해 잘라 낸 뒤에도 셀 번호가 그대로다"""
    seg = sg.Segmentation(200, 100, (255, 255, 255))
    seg.clusters = [sg.Cluster(1, "파랑", (31, 119, 180), 100, False), sg.Cluster(2, "빨강", (214, 39, 40), 50, False)]
    xs, ys = (10, 55, 100, 145, 189), (10, 30, 50, 70, 89)
    seg.grid = sg.Grid([sg.GridLine(float(y), y, y, 10, 189, (200, 225, 240)) for y in ys],
                       [sg.GridLine(float(x), x, x, 10, 89, (200, 225, 240)) for x in xs], 20.0, 45.0, "light")
    seg.plot_box, seg.plot_source = (10, 10, 189, 89), "grid"
    if ring:
        seg.ring = sg.Ring(100, 50, 30, 1.0, None)
    return seg


def dot(cluster, x, y):
    return sg.Element("dot", cluster, (x, y, x, y), 1, [y * 200 + x], float(x), float(y), 1)


class Priority(unittest.TestCase):
    """격자 0 < 링 1 < 곡선 · 추세선 2 < 선 · 틀 · 눈금 3 < 점 · 밀도 4 < 노치 5 (설계서 14-11)"""

    def test_table(self):
        self.assertEqual(rd.PRIO, {"grid": 0, "ring": 1, "curve": 2, "trend": 2, "line": 3, "frame": 3, "tick": 3,
                                   "dot": 4, "field": 4, "notch": 5})

    def cell(self, x, y):
        return rd.Geometry(scene(), 100).cell_xy(x + 0.5, y + 0.5)

    def test_scene_geometry(self):
        cells, geo = rd.layout(scene(), 100)
        self.assertEqual((geo.x0, geo.y0, geo.cols), (10, 10, 100))
        self.assertEqual(cells[(0, 0)], (3, "+"))
        self.assertEqual(art(rd.render(scene(), 100))[0][:3], "+--")

    def test_a_point_beats_grid_and_frame(self):
        seg = scene()
        seg.elements = [dot(1, 100, 50), dot(1, 10, 70)]               # 안쪽 교차점 · 왼쪽 틀 위
        for mode in MODES:
            cells, _ = rd.layout(seg, 100, grid=mode)
            self.assertEqual(cells[self.cell(100, 50)], (4, "o"), mode)
            self.assertEqual(cells[self.cell(10, 70)], (4, "o"), mode)

    def test_grid_is_under_everything(self):
        seg = scene()
        cells, _ = rd.layout(seg, 100, grid="show")
        self.assertEqual(cells[self.cell(100, 50)], (0, "+"))
        self.assertEqual(cells[self.cell(77, 30)], (0, "-"))
        self.assertEqual(cells[self.cell(55, 40)], (0, "|"))
        self.assertEqual(cells[self.cell(10, 10)], (0, "+"), "show 의 바깥 줄도 격자 (틀을 따로 그리지 않는다)")
        cells, _ = rd.layout(seg, 100, grid="dots")
        self.assertEqual(cells[self.cell(100, 50)], (0, "."))
        self.assertEqual(cells[self.cell(10, 10)], (3, "+"), "dots 의 바깥 교차점은 틀이 이긴다")

    def test_ring_beats_grid_and_dots_mode_falls_back_to_hide(self):
        seg = scene(ring=True)
        pix = [int(100 + 30 * cos(a / 50.0)) + 200 * int(50 + 30 * sin(a / 50.0)) for a in range(315)]
        seg.elements = [sg.Element("ring", 2, (70, 20, 130, 80), len(pix), sorted(set(pix)), 100.0, 50.0)]
        cells, _ = rd.layout(seg, 100, grid="show")
        ringed = [c for c, v in cells.items() if v == (1, ".")]
        self.assertTrue(ringed)
        dots_cells, _ = rd.layout(seg, 100, grid="dots")
        hide_cells, _ = rd.layout(seg, 100, grid="hide")
        self.assertEqual(dots_cells, hide_cells, "링이 있으면 dots 는 hide 로 그린다")
        text = rd.render(seg, 100, grid="dots")
        self.assertIn("격자 가로 5 · 세로 5 줄 생략", text)
        self.assertNotIn("교차점", text)

    def test_trend_beats_grid_and_loses_to_the_frame(self):
        seg = scene()
        path = [(float(x), 30.5) for x in range(10, 190, 8)] + [(189.5, 30.5)]   # 가로 격자줄 y=30 위를 틀에서 틀까지
        seg.elements = [sg.Element("trend", 2, (10, 30, 189, 31), 2, [], 100.0, 30.5, 0, 2.0, path)]
        cells, _ = rd.layout(seg, 100, grid="show")
        self.assertEqual(cells[self.cell(77, 30)][0], 2, "추세선이 격자 위")
        cells, _ = rd.layout(seg, 100, grid="hide")
        self.assertEqual(cells[self.cell(10, 30)], (3, "|"), "틀이 추세선 위")

    def test_ticks_lose_to_points(self):
        seg = scene()
        seg.elements = [dot(1, 55, 10)]
        cells, _ = rd.layout(seg, 100, grid="ticks")
        self.assertEqual(cells[self.cell(55, 10)], (4, "o"))
        self.assertEqual(cells[self.cell(100, 10)], (3, "+"))
        self.assertEqual(cells[self.cell(189, 50)], (3, "+"))
        self.assertEqual(cells[self.cell(189, 40)], (3, "|"))

    def test_notch_is_on_top(self):
        seg = scene(ring=True)
        seg.ring.notch = 90.0
        x, y = 100, 80
        seg.elements = [dot(1, x, y)]
        cells, _ = rd.layout(seg, 100, grid="show")
        nc = rd.notch_cell(seg, rd.Geometry(seg, 100))
        self.assertEqual(cells[nc[0]], (5, "v"))


class GridLegend(unittest.TestCase):
    def test_line_counts_are_every_found_line(self):
        seg = scene()
        seg.grid.horizontal = seg.grid.horizontal[:3]
        self.assertIn("격자 가로 3 · 세로 5 줄 생략", rd.render(seg, 100))
        seg.grid.vertical = seg.grid.vertical[:4]
        self.assertIn("(가로 3 · 세로 4 줄)", rd.render(seg, 100, grid="show"))

    def test_one_direction_grid_uses_the_line_span(self):
        seg = scene()
        seg.grid.vertical = []
        cells, geo = rd.layout(seg, 100)
        self.assertEqual(cells[geo.cell_xy(10.5, 10.5)], (3, "+"))
        self.assertEqual(cells[geo.cell_xy(189.5, 89.5)], (3, "+"))
        self.assertIn("격자 가로 5 · 세로 0 줄 생략", rd.render(seg, 100))


class GridOnly(unittest.TestCase):
    """격자만 있는 그림 — 틀과 범례를 그린다 (설계서 14-11 · 명령은 종료 코드 0)"""

    def picture(self, color):
        c = synth.Canvas(400, 300)
        synth.grid(c, (40, 30, 370, 270), 11, 9, color, 1)
        return c.image()

    def test_frame_and_legend(self):
        for color in (synth.LBLUE_GRID, synth.DGRAY_GRID):
            with self.subTest(color=color):
                seg = sg.segment(self.picture(color))
                self.assertIsNotNone(seg.grid)
                text = rd.render(seg, 120)
                lines = art(text)
                self.assertTrue(lines[0].startswith("+-") and lines[0].endswith("-+"), lines[0])
                self.assertTrue(lines[-1].startswith("+-") and lines[-1].endswith("-+"), lines[-1])
                self.assertTrue(all(x.startswith("|") and x.endswith("|") for x in lines[1:-1]))
                self.assertIn("- | 그림 상자 · 격자 가로 9 · 세로 11 줄 생략", legend(text))
                self.assertNotIn("그릴 것을 찾지 못했습니다", text)

    def test_command_exit_code(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "격자 only.png")
            with open(src, "wb") as f:
                f.write(tc.png_of(self.picture(synth.LBLUE_GRID)))
            code, out, _ = tc.run(src, "--stdout")
            self.assertEqual(code, 0, out)
            self.assertIn("격자 가로 9 · 세로 11 줄 생략", out)
            self.assertTrue(out.rstrip().endswith("결과: OK"))


class TrendOverDensity(unittest.TestCase):
    """빽빽한 산점(field) 위의 추세선이 읽힌다: 추세선이 지나는 셀에서 밀도 글자는 추세선에 양보하고, 낱점(dot)은 그대로 이긴다"""

    def test_trend_shows_through_the_field(self):
        seg = seg_of("Z")
        dense = {e.cluster for e in seg.of("field")}
        self.assertTrue(dense and seg.of("trend"))
        for width in WIDTHS:
            with self.subTest(width=width):
                cells, geo = rd.layout(seg, width)
                drawn = rd.trend_cells(seg.of("trend")[0], geo)
                dots = rd.allocate_dots(seg, geo)
                sparse = {c for c, per in dots.items() if any(k not in dense for k in per)}
                mine = [c for c in drawn if c not in sparse and cells[c][0] != 3]                 # 틀 위는 틀이 이긴다
                shown = [c for c in mine if cells[c][1] in TREND_GLYPHS and cells[c][0] == 2]
                self.assertGreaterEqual(len(shown), 0.95 * len(mine), "추세선 셀 %d 중 %d 만 보인다" % (len(mine), len(shown)))
                under = [c for c in drawn if c in dots and c not in sparse]
                self.assertTrue(under, "이 그림에서는 추세선이 밀도 위를 지난다")
                self.assertTrue(all(cells[c][0] in (2, 3) for c in under))

    def test_field_is_still_drawn_around_the_trend(self):
        seg = seg_of("Z")
        cells, geo = rd.layout(seg, 120)
        g = rd.assign_glyphs(seg)[seg.of("field")[0].cluster]["point"]
        drawn = [ch for p, ch in cells.values() if p == 4 and ch in g]
        self.assertGreater(len(drawn), 400)
        self.assertIn(g[2], drawn)

    def test_sparse_points_still_beat_the_trend(self):
        seg = seg_of("C")
        self.assertFalse(seg.of("field"))
        cells, geo = rd.layout(seg, 120)
        drawn = rd.trend_cells(seg.of("trend")[0], geo)
        dots = rd.allocate_dots(seg, geo)
        both = [c for c in drawn if c in dots]
        self.assertTrue(both)
        self.assertTrue(all(cells[c][0] == 4 and cells[c][1] in POINTS for c in both))

    def test_ac12_column_mass_centre_follows_the_trend(self):
        """열마다 파랑(밀도) 개수의 무게중심 행과 추세선 행의 상관 ≥ 0.9"""
        seg = seg_of("Z")
        k = seg.of("field")[0].cluster
        for width in (120, 300):
            with self.subTest(width=width):
                geo = rd.Geometry(seg, width)
                dots = rd.allocate_dots(seg, geo)
                trend = {}
                for (r, c) in rd.trend_cells(seg.of("trend")[0], geo):
                    trend.setdefault(c, []).append(r)
                mass = {}
                for (r, c), per in dots.items():
                    if per.get(k):
                        m = mass.setdefault(c, [0, 0])
                        m[0] += per[k]
                        m[1] += per[k] * r
                cols = sorted(c for c in trend if mass.get(c, [0])[0] >= 3)
                self.assertGreater(len(cols), 0.5 * geo.cols)
                r = pearson([mass[c][1] / mass[c][0] for c in cols], [sum(trend[c]) / len(trend[c]) for c in cols])
                self.assertGreaterEqual(r, 0.9)


class TrendLegend(unittest.TestCase):
    def test_trend_words(self):
        for name in ("C", "J0", "J1", "A_base"):
            with self.subTest(name=name):
                lg = legend(rd.render(seg_of(name), 120))
                self.assertIn("_ - / \\ | 빨강 추세선", lg)
                self.assertNotIn("빽빽한 점 위에", lg)
        self.assertIn("_ - / \\ | 곡선", legend(rd.render(seg_of("A_base"), 120)), "곡선과 따로")
        self.assertNotIn("곡선", legend(rd.render(seg_of("J1"), 120)))

    def test_trend_over_density_is_said(self):
        lg = legend(rd.render(seg_of("Z"), 120))
        self.assertIn("_ - / \\ | 빨강 추세선 (빽빽한 점 위에 그림)", lg)
        self.assertRegex(lg, r"o O @ 파랑 점 약 \d+–\d+개 \(빽빽함 · 밀도로 그림\)")
        lo, hi = seg_of("Z").dots_range()
        self.assertIn("점은 추정 %s (빽빽한 곳은 겹침을 보정한 범위)" % rd.about(lo, hi), lg)

    def test_manual_examples(self):
        """MANUAL · README 에 적은 예 (합성 HARD 그림의 값만 적는다 — W-11)"""
        self.assertIn("o O @ 파랑 점 약 1800–2300개 (빽빽함 · 밀도로 그림)", rd.render(seg_of("H"), 120))
        self.assertIn("격자 가로 17 · 세로 21 줄 생략", rd.render(seg_of("C"), 120))

    def test_no_trend_no_words(self):
        for name in ("B0", "H"):
            self.assertNotIn("추세선", rd.render(seg_of(name), 120))


def box_density(seg, case, geo, cells, ks, gx, gy):
    """렌더 셀에 나눈 개수를 그림 상자의 gx × gy 칸에 셀과 칸이 겹친 넓이 비율로 옮긴다"""
    x0, y0, x1, y1 = case.box
    bw, bh = (x1 - x0) / gx, (y1 - y0) / gy
    est = [0.0] * (gx * gy)
    for (r, c), per in cells.items():
        n = sum(v for k, v in per.items() if k in ks)
        if not n:
            continue
        ax, ay = geo.x0 + c * geo.cw, geo.y0 + r * geo.ch
        bx, by = ax + geo.cw, ay + geo.ch
        for i in range(max(0, int((ax - x0) / bw)), min(gx - 1, int((bx - x0) / bw)) + 1):
            ox = min(bx, x0 + (i + 1) * bw) - max(ax, x0 + i * bw)
            for j in range(max(0, int((ay - y0) / bh)), min(gy - 1, int((by - y0) / bh)) + 1):
                oy = min(by, y0 + (j + 1) * bh) - max(ay, y0 + j * bh)
                if ox > 0 and oy > 0:
                    est[j * gx + i] += n * ox * oy / (geo.cw * geo.ch)
    return est


class AC6Render(unittest.TestCase):
    """렌더 값(셀에 나눈 개수)으로 잰 밀도 상관: 16×8 ≥ 0.95 · 60×25 ≥ 0.90"""

    def test_dense_variants(self):
        for name in ("H", "I", "Z"):
            case, seg = synth.hard_case(name), seg_of(name)
            ks = {c.index for c in seg.clusters if c.name == "파랑"}
            for width in (120, 200, 300):
                with self.subTest(name=name, width=width):
                    geo = rd.Geometry(seg, width)
                    cells = rd.allocate_dots(seg, geo)
                    for (gx, gy), want in (((16, 8), 0.95), ((60, 25), 0.90)):
                        r = pearson([float(v) for v in case.cell_counts(gx, gy)], box_density(seg, case, geo, cells, ks, gx, gy))
                        self.assertGreaterEqual(r, want, "%d×%d 상관 %.3f" % (gx, gy, r))


class Command(unittest.TestCase):
    """--grid 옵션 · OK 줄 · make_art 의 모양 문자열"""

    def test_parse(self):
        self.assertEqual(tc.cli.parse(["a.png"])[1]["grid"], "hide")
        for argv in (["--grid", "show", "a.png"], ["--grid=show", "a.png"]):
            self.assertEqual(tc.cli.parse(argv)[1]["grid"], "show")
        for mode in MODES:
            self.assertEqual(tc.cli.parse(["a.png", "--grid", mode])[1]["grid"], mode)

    def test_bad_values_are_usage_errors(self):
        for argv in (["--grid", "lines", "a.png"], ["--grid=", "a.png"], ["a.png", "--grid"], ["--grid=HIDE", "a.png"]):
            with self.subTest(argv=argv):
                code, out, err = tc.run(*argv)
                self.assertEqual(code, 2)
                self.assertIn("--grid", err)
                self.assertEqual(out, "")

    def test_help_names_the_option(self):
        self.assertIn("--grid", tc.cli.HELP)
        self.assertIn("hide", tc.cli.HELP)

    def test_shape_and_render_follow_the_option(self):
        seg = seg_of("B0")
        opts = tc.cli.parse(["a.png"])[1]
        _, _, text, shape = tc.cli.make_art(seg, "a.png", opts)
        self.assertEqual(text, rd.render(seg, 120))
        self.assertEqual(shape, "%d열 %d행 · 점 추정 %d개" % (max(len(x) for x in art(text)), len(art(text)), seg.dots()))
        opts = tc.cli.parse(["a.png", "--grid", "show"])[1]
        self.assertEqual(tc.cli.make_art(seg, "a.png", opts)[2], rd.render(seg, 120, grid="show"))
        no_grid = dict(opts)
        del no_grid["grid"]
        self.assertEqual(tc.cli.make_art(seg, "a.png", no_grid)[2], rd.render(seg, 120), "창이 넘기는 옵션에는 grid 가 없다 → hide")

    def test_shape_uses_the_range_with_a_field(self):
        seg = seg_of("Z")
        _, _, text, shape = tc.cli.make_art(seg, "z.png", tc.cli.parse(["z.png"])[1])
        lo, hi = seg.dots_range()
        self.assertTrue(shape.endswith(" · 점 추정 %s" % rd.about(lo, hi)), shape)
        self.assertNotIn(",", shape)
        self.assertRegex(shape, r"^\d+열 \d+행 · 점 추정 약 \d+–\d+개$")

    def test_ok_line_with_grid_option(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "b0.png")
            with open(src, "wb") as f:
                f.write(tc.png_of(synth.hard_case("B0").image))
            code, out, _ = tc.run(src, "--stdout", "--grid", "ticks")
            self.assertEqual(code, 0)
            self.assertIn("+ 틀 위의 격자 자리 (가로 17 · 세로 21 줄)", out)
            self.assertRegex(out, r"OK  b0\.png \(\d+열 \d+행 · 점 추정 \d+개\)")
            code, out2, _ = tc.run(src, "--stdout")
            self.assertIn("격자 가로 17 · 세로 21 줄 생략", out2)


if __name__ == "__main__":
    unittest.main()
