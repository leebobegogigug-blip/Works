# -*- coding: utf-8 -*-
"""추세선 복원 (설계서 14-10 · 14-11 · AC8) — 실선 · 점선 · 굵기, 범례 견본 · 제목 번짐 제외, 마커 곡선은 그대로,
그림 상자가 없는 차트의 굵은 선은 덩어리 자신의 두께로 마커를 가른다. 그림은 전부 코드로 만든 것 (W-12)."""
import importlib.util
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import ascii1_render as rd  # noqa: E402
import ascii1_seg as sg  # noqa: E402
import synth  # noqa: E402

spec = importlib.util.spec_from_file_location("measure_hard", os.path.join(ROOT, "tools", "measure_hard.py"))
mh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mh)

FRAME = (40, 40, 40)
TRENDED = ("J", "J0", "J1", "J2", "A_base", "C", "D", "K", "Z")      # 추세선이 있는 HARD 변형 (L 은 빨강이 주황에 합쳐진다 — Q6)
COL = 8                                                            # AC8 을 재는 열 너비 (px)

_SEGS = {}
_CASES = {}


def case(name):
    if name not in _CASES:
        _CASES[name] = synth.hard_case(name)
    return _CASES[name]


def seg_of(name):
    if name not in _SEGS:
        _SEGS[name] = sg.segment(case(name).image)
    return _SEGS[name]


def red(seg):
    return {c.index for c in seg.clusters if c.name == "빨강"}


def kinds(seg, cluster_ids, kind):
    return [e for e in seg.elements if e.kind == kind and e.cluster in cluster_ids]


def framed(draw, frame=True):
    """HARD 크기의 빈 그림에 1 px 틀(그림 상자)을 두르고 draw(canvas) 로 그린다"""
    c = synth.Canvas(*synth.HARD_SIZE)
    if frame:
        x0, y0, x1, y1 = synth.HARD_BOX
        for x in (x0, x1):
            c.vline(x, y0, y1, 1, FRAME)
        for y in (y0, y1):
            c.hline(y, x0, x1, 1, FRAME)
    draw(c)
    return c.image()


def truth_part(lo, hi):
    """정답 추세선 좌표 중 가로 위치가 상자 폭의 lo–hi 비율인 것"""
    x0, _, x1, _ = synth.HARD_BOX
    return [p for p in synth.trend_points(synth.HARD_BOX) if x0 + lo * (x1 - x0) <= p[0] <= x0 + hi * (x1 - x0)]


def y_at(pts, x):
    """꺾은선 pts (x 순) 의 x 에서의 y (선형 보간, 범위 밖은 끝값)"""
    if x <= pts[0][0]:
        return pts[0][1]
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        if ax <= x <= bx:
            return ay if bx == ax else ay + (by - ay) * (x - ax) / (bx - ax)
    return pts[-1][1]


def red_pixels_in_box(img, seg):
    """상자 안(PLOT_INSET 안쪽)의 빨강 칸 — trend_stats 에 넣는 것과 같은 칸 (선이 없는 그림이라 선으로 떼어 갈 것이 없다)"""
    cls, clusters, _ = sg.classify(img, seg.bg)
    k = [c.index for c in clusters if c.name == "빨강"][0]
    x0, y0, x1, y1 = seg.plot_box
    w = img.width
    m = sg.PLOT_INSET
    return [i for i, v in enumerate(cls) if v == k and x0 + m <= i % w <= x1 - m and y0 + m <= i // w <= y1 - m]


def stats_of(img):
    seg = sg.segment(img)
    return sg.trend_stats(red_pixels_in_box(img, seg), seg.plot_box, img.width), seg


class TrendHard(unittest.TestCase):
    """AC8 — HARD 의 실선 · 점선 추세선이 추세선 요소 하나로 묶이고, 점 · 글자로 쪼개지지 않는다"""

    def test_one_trend_no_red_dots_or_text(self):
        for name in TRENDED:
            with self.subTest(name=name):
                seg = seg_of(name)
                r = red(seg)
                self.assertEqual(len(kinds(seg, r, "trend")), 1)
                self.assertEqual(sum(e.count for e in kinds(seg, r, "dot")), 0, "추세선에서 나온 점")
                self.assertEqual(len(kinds(seg, r, "text")), 0, "추세선에서 나온 글자")
                e = kinds(seg, r, "trend")[0]
                self.assertEqual(e.count, 0, "추세선은 점이 아니다")
                self.assertEqual(seg.dots(e.cluster), 0)
                self.assertGreater(e.thickness, 0)
                self.assertEqual(e.path, sorted(e.path), "path 는 x 순")

    def test_cover_at_least_90(self):
        """measure_hard 의 추세덮음% (8 px 열 · 정답 y ± 4 px) ≥ 90"""
        for name in TRENDED:
            with self.subTest(name=name):
                self.assertGreaterEqual(mh.measure(case(name))["trend"], 90.0)

    def test_path_within_one_cell(self):
        """8 px 열마다 path 의 y 가 정답에서 ±1 셀(120 열로 그릴 때의 셀 높이) 안 — 90% 이상의 열"""
        for name in TRENDED:
            with self.subTest(name=name):
                seg = seg_of(name)
                e = kinds(seg, red(seg), "trend")[0]
                ch = rd.Geometry(seg, 120).ch
                truth = case(name).trend
                lo, hi = int(truth[0][0]) // COL + 1, int(truth[-1][0]) // COL - 1
                ok = sum(1 for col in range(lo, hi + 1) if e.path[0][0] <= col * COL + COL / 2 <= e.path[-1][0]
                         and abs(y_at(e.path, col * COL + COL / 2) - y_at(truth, col * COL + COL / 2)) <= ch)
                self.assertGreaterEqual(ok / (hi - lo + 1), 0.90)

    def test_trend_pixels_inside_plot_box(self):
        for name in ("J1", "Z"):
            with self.subTest(name=name):
                seg = seg_of(name)
                x0, y0, x1, y1 = seg.plot_box
                e = kinds(seg, red(seg), "trend")[0]
                self.assertTrue(all(x0 <= i % seg.width <= x1 and y0 <= i // seg.width <= y1 for i in e.pixels))

    def test_trend_does_not_take_other_series(self):
        """파랑 산점은 그대로 — 추세선은 빨강 군집만 묶는다"""
        for name in ("A0", "A1", "E0", "H", "I", "B0", "F0", "F1", "E"):
            with self.subTest(name=name):
                self.assertEqual(sg.segment(case(name).image).of("trend"), [], "추세선이 없는 변형")


class TrendRender(unittest.TestCase):
    """렌더: 추세선은 곡선 층(우선순위 2)에서 path 를 segment_cells 로 이어 그린다"""

    def test_cells_follow_truth(self):
        for name in ("J", "J0", "J1", "J2"):
            with self.subTest(name=name):
                seg = seg_of(name)
                geo = rd.Geometry(seg, 120)
                e = kinds(seg, red(seg), "trend")[0]
                cells = rd.trend_cells(e, geo)
                self.assertTrue(set(cells.values()) <= set("_-/\\|"))
                truth = case(name).trend
                c_lo = geo.cell_xy(truth[0][0], 0)[1] + 1
                c_hi = geo.cell_xy(truth[-1][0], 0)[1] - 1
                rows = {}
                for (r, c) in cells:
                    rows.setdefault(c, []).append(r)
                ok = 0
                for c in range(c_lo, c_hi + 1):
                    x = geo.x0 + (c + 0.5) * geo.cw
                    want = geo.cell_xy(x, y_at(truth, x))[0]
                    ok += any(abs(r - want) <= 1 for r in rows.get(c, ()))
                self.assertGreaterEqual(ok / (c_hi - c_lo + 1), 0.90)

    def test_render_has_trend_and_no_red_points(self):
        seg = seg_of("J1")
        out = rd.render(seg, 120)
        self.assertNotIn("빨강 점", out)
        art = out.split("\n\n")[0]
        n = sum(art.count(ch) for ch in "_-/\\")
        self.assertGreater(n, 0.9 * 110, "120 열 중 추세선이 지나는 열마다 곡선 글자")

    def test_no_trend_same_output(self):
        """추세선이 없는 그림은 렌더가 지금 그대로 — 골든 3 개는 test_render 가 바이트로 본다"""
        for img in (synth.control_chart()[0], synth.line_chart()[0]):
            seg = sg.segment(img)
            self.assertEqual(seg.of("trend"), [])


class LegendSwatch(unittest.TestCase):
    """그림 상자 밖의 같은 색(범례 견본 · 제목)은 추세선에도 개수에도 들어가지 않는다 — 글자로 비운다"""

    def picture(self):
        def draw(c):
            c.polyline(synth.trend_points(synth.HARD_BOX), 3, synth.TREND)
            c.disc(705, 30, 4, synth.TREND)                                            # 범례 견본: 원 + 짧은 점선
            synth.dashed(c, [(716.0, 30.0), (760.0, 30.0)], 10, 6, 2, synth.TREND)
            c.text("TEMP", 120, 20, synth.TREND)                                       # 같은 색의 제목
        return framed(draw)

    def test_swatch_is_text_not_dots(self):
        seg = sg.segment(self.picture())
        r = red(seg)
        self.assertEqual(len(kinds(seg, r, "trend")), 1)
        self.assertEqual(sum(e.count for e in kinds(seg, r, "dot")), 0)
        self.assertEqual(kinds(seg, r, "curve"), [])
        x0, y0, x1, y1 = seg.plot_box
        e = kinds(seg, r, "trend")[0]
        self.assertTrue(all(x0 <= i % seg.width <= x1 and y0 <= i // seg.width <= y1 for i in e.pixels))
        swatch = [t for t in kinds(seg, r, "text") if t.bbox[1] < y0]
        self.assertTrue(any(t.bbox[0] <= 705 <= t.bbox[2] for t in swatch), "견본 원은 글자로")
        self.assertTrue(any(t.bbox[0] >= 716 for t in swatch), "견본 점선은 글자로")

    def test_outside_pieces_untouched_without_trend(self):
        """추세선이 없는 군집은 상자 밖 조각을 지금처럼 다룬다 — 견본 원은 점이다"""
        def draw(c):
            c.polyline(truth_part(0.0, 0.25), 3, synth.TREND)      # 짧은 선: 추세선이 아니다
            c.disc(705, 30, 4, synth.TREND)
        seg = sg.segment(framed(draw))
        r = red(seg)
        self.assertEqual(kinds(seg, r, "trend"), [])
        self.assertTrue(any(e.bbox[0] <= 705 <= e.bbox[2] and e.bbox[1] < 60 for e in kinds(seg, r, "dot")))


class TrendGates(unittest.TestCase):
    """14-10 의 문턱 — 구간 폭 · 띠 높이 · 좁은 구간 · 채움 · 길이 · 구간 사이 틈. 문턱 곁의 그림으로 건다"""

    def assertTrend(self, img, want):
        seg = sg.segment(img)
        got = kinds(seg, red(seg), "trend")
        self.assertEqual(len(got), 1 if want else 0)
        return seg

    def test_span(self):
        for lo, hi, want in ((0.0, 0.25, False), (0.0, 0.33, False), (0.0, 0.50, True), (0.4, 0.9, True)):
            with self.subTest(span=(lo, hi)):
                img = framed(lambda c: c.polyline(truth_part(lo, hi), 3, synth.TREND))
                st, _ = stats_of(img)
                self.assertEqual(st["span"] >= sg.TREND_SPAN, want, st)
                self.assertTrend(img, want)

    def test_fill(self):
        """성긴 점선(빈 구간이 많다)은 추세선이 아니고, 구간 하나만큼 비는 점선은 추세선이다"""
        for on, off, want in ((6, 14, False), (6, 12, True)):
            with self.subTest(dash=(on, off)):
                img = framed(lambda c: synth.dashed(c, synth.trend_points(synth.HARD_BOX), on, off, 3, synth.TREND))
                st, _ = stats_of(img)
                if want:
                    self.assertTrue(sg.TREND_FILL <= st["fill"] < 0.99, st)
                else:
                    self.assertLess(st["fill"], sg.TREND_FILL, st)
                    self.assertGreaterEqual(st["fill"], 0.6, st)
                self.assertTrend(img, want)

    def test_thick_dash_bins_follow_thickness(self):
        """굵은 점선: 구간 폭이 두께를 따라 넓어져(B = 2t) 대시 사이 틈이 빈 구간이 되지 않는다"""
        img = framed(lambda c: synth.dashed(c, synth.trend_points(synth.HARD_BOX), 14, 12, 8, synth.TREND))
        st, _ = stats_of(img)
        self.assertGreater(st["B"], 8)
        self.assertTrend(img, True)

    def test_narrow(self):
        """같은 색 표식이 섞여 좁은 구간이 모자라면 추세선이 아니다. 조금 섞인 것은 추세선이다"""
        import random
        for n, want in ((16, False), (8, True)):
            with self.subTest(n=n):
                def draw(c):
                    c.polyline(synth.trend_points(synth.HARD_BOX), 3, synth.TREND)
                    rng = random.Random(11)
                    x0, y0, x1, y1 = synth.HARD_BOX
                    for _ in range(n):
                        x = rng.uniform(x0 + 20, x1 - 20)
                        y = y_at(synth.trend_points(synth.HARD_BOX), x) + rng.choice((-1, 1)) * rng.uniform(25, 120)
                        c.disc(x, min(y1 - 10, max(y0 + 10, y)), 4, synth.TREND)
                img = framed(draw)
                st, _ = stats_of(img)
                if want:
                    self.assertTrue(sg.TREND_NARROW <= st["narrow"] < 0.95, st)
                else:
                    self.assertTrue(0.6 <= st["narrow"] < sg.TREND_NARROW, st)
                self.assertTrend(img, want)

    def test_band_height(self):
        """띠가 하나여도 그 높이가 max(8, 3t) + B 를 넘으면 좁은 구간이 아니다 (빗살 — 비스듬한 1 px 선에 막대.
        선이 비스듬해야 find_lines 가 가로선으로 떼어 가지 않는다)"""
        def comb(tick, width):
            def draw(c):
                c.polyline([(100.0, 250.0), (760.0, 350.0)], width, synth.TREND)
                for x in range(102, 758, 8):
                    y = int(round(250 + 100 * (x - 100) / 660 - width / 2))
                    c.vline(x, y, y + tick - 1, 1, synth.TREND)
            return framed(draw)
        # 한도 max(8, 3t) + B: 1 px 선은 8 + 8 = 16, 3 px 선은 9 + 8 = 17 (3t 가 바닥 8 을 넘는다)
        for tick, width, t, want in ((24, 1, 1, False), (12, 1, 1, True), (22, 3, 3, False), (13, 3, 3, True)):
            with self.subTest(tick=tick, width=width):
                st, seg = stats_of(comb(tick, width))
                self.assertEqual(st["t"], t)
                self.assertEqual(st["narrow"] >= sg.TREND_NARROW, want, {k: v for k, v in st.items() if k != "path"})
                if width == 1 or not want:           # 3 px 선의 짧은 빗살은 선에 붙은 마커로 보여 추세선에서 빠질 수 있다 — 띠 판정만 본다
                    self.assertEqual(len(kinds(seg, red(seg), "trend")), 1 if want else 0)

    def test_two_parallel_lines_are_not_one_trend(self):
        """같은 색 선 둘(세로 틈 7 px)은 구간마다 띠가 둘이라 좁은 구간이 아니다 — 추세선은 군집마다 하나"""
        def draw(c):
            c.polyline(synth.trend_points(synth.HARD_BOX), 3, synth.TREND)
            c.polyline([(x, y + 10) for x, y in synth.trend_points(synth.HARD_BOX)], 3, synth.TREND)
        st, seg = stats_of(framed(draw))
        self.assertLess(st["narrow"], 0.5, {k: v for k, v in st.items() if k != "path"})
        self.assertEqual(kinds(seg, red(seg), "trend"), [])

    def test_piece_on_the_frame_is_outside(self):
        """틀 선 위(상자에서 PLOT_INSET 안쪽이 아닌 곳)에 걸친 같은 색 조각은 추세선에 들지 않고 글자로 간다"""
        def draw(c):
            c.polyline(synth.trend_points(synth.HARD_BOX), 3, synth.TREND)
            c.disc(400, synth.HARD_BOX[1], 3, synth.TREND)
        seg = sg.segment(framed(draw))
        x0, y0, x1, y1 = seg.plot_box
        m = 2                                       # 설계서 14-7 의 PLOT_INSET (상수를 읽으면 변이와 같이 움직인다)
        e = kinds(seg, red(seg), "trend")[0]
        self.assertTrue(all(x0 + m <= i % seg.width <= x1 - m and y0 + m <= i // seg.width <= y1 - m for i in e.pixels))
        self.assertTrue(any(t.bbox[0] <= 400 <= t.bbox[2] and t.bbox[1] <= y0 for t in kinds(seg, red(seg), "text")))

    def test_gap_joins_only_near_bins(self):
        """멀리(4 구간 넘게) 떨어진 같은 색 조각은 줄에 넣지 않는다 — 채움이 깎이지 않는다"""
        def draw(c):
            c.polyline(truth_part(0.0, 0.5), 3, synth.TREND)
            c.disc(640, 200, 4, synth.TREND)
        st, seg = stats_of(framed(draw))
        self.assertGreaterEqual(st["fill"], sg.TREND_FILL, st)
        self.assertEqual(len(kinds(seg, red(seg), "trend")), 1)
        dashed = framed(lambda c: synth.dashed(c, truth_part(0.0, 0.8), 6, 30, 3, synth.TREND))
        st, seg = stats_of(dashed)            # 틈 30 px ≤ 4 구간: 한 줄로 이어지되 빈 구간이 많아 채움이 모자란다
        self.assertGreater(st["span"], sg.TREND_SPAN, st)
        self.assertEqual(kinds(seg, red(seg), "trend"), [])

    def test_no_box_no_trend(self):
        img = framed(lambda c: c.polyline(synth.trend_points(synth.HARD_BOX), 1, synth.TREND), frame=False)
        seg = sg.segment(img)
        self.assertIsNone(seg.plot_box)
        self.assertEqual(seg.of("trend"), [])


def marker_curve(frame=True, axis_only=False):
    """마커가 붙은 거의 평평한 꺾은선 — 좁은 구간 · 채움 · 길이는 추세선 문을 통과한다 (마커 구간도 띠 하나)"""
    def draw(c):
        x0, y0, x1, y1 = synth.HARD_BOX
        if axis_only:
            c.hline(y1, x0, x1, 2, synth.BLACK)
        pts = [(x0 + 20 + k * 64.0, 300.0 + (6 if k % 2 else -6)) for k in range(11)]
        for a, b in zip(pts, pts[1:]):
            c.line(a[0], a[1], b[0], b[1], 1.2, synth.BLUE)
        for x, y in pts:
            c.disc(x, y, 5.2, synth.BLUE)
    if axis_only:
        return framed(draw, frame=False)
    return framed(draw, frame)


class MarkerCurve(unittest.TestCase):
    """마커가 선 위에 붙은 관리도형 곡선은 추세선으로 바뀌지 않는다 — 지금의 곡선 + 점 경로"""

    def test_charts_keep_markers(self):
        for name, img, markers in (("chart", synth.control_chart()[0], 12), ("chart_frame", synth.control_chart(frame=True)[0], 12),
                                   ("chart_20", synth.control_chart(20)[0], 20), ("line", synth.line_chart()[0], 12)):
            with self.subTest(name=name):
                seg = sg.segment(img)
                blue = {c.index for c in seg.clusters if c.name == "파랑"}
                self.assertEqual(seg.of("trend"), [])
                self.assertEqual(seg.dots(), markers)
                self.assertEqual(len(kinds(seg, blue, "curve")), 1)

    def test_flat_marker_curve_passes_ratios_but_is_not_trend(self):
        img = marker_curve()
        seg = sg.segment(img)
        cls, clusters, _ = sg.classify(img, seg.bg)
        k = [c.index for c in clusters if c.name == "파랑"][0]
        x0, y0, x1, y1 = seg.plot_box
        m = sg.PLOT_INSET
        pix = [i for i, v in enumerate(cls) if v == k and x0 + m <= i % 800 <= x1 - m and y0 + m <= i // 800 <= y1 - m]
        st = sg.trend_stats(pix, seg.plot_box, 800)
        self.assertTrue(st["span"] >= sg.TREND_SPAN and st["fill"] >= sg.TREND_FILL and st["narrow"] >= sg.TREND_NARROW, st)
        self.assertEqual(seg.of("trend"), [])
        self.assertEqual(seg.dots(), 11)
        self.assertEqual(len(seg.of("curve")), 1)


class OwnThickness(unittest.TestCase):
    """그림 상자가 없는 차트의 굵은 선: 선 두께(가는 축)로 잡은 rc 로 쪼갠 '마커' 가 선 조각만 하면 덩어리 자신의 두께로 다시 가른다"""

    def axis_and(self, draw):
        def full(c):
            c.hline(560, 40, 760, 1, FRAME)              # 가로축 하나 — 세로선이 없어 상자가 없다
            draw(c)
        return framed(full, frame=False)

    def test_thick_line_is_a_curve_not_dots(self):
        img = self.axis_and(lambda c: c.polyline(synth.trend_points(synth.HARD_BOX), 3, synth.TREND))
        seg = sg.segment(img)
        self.assertIsNone(seg.plot_box)
        self.assertEqual(seg.line_thickness, 1)
        r = red(seg)
        self.assertEqual(sum(e.count for e in kinds(seg, r, "dot")), 0)
        self.assertEqual(len(kinds(seg, r, "curve")), 1)

    def test_real_markers_stay(self):
        """마커 지름이 2t + 2 이상이면 다시 가르지 않는다 — 마커 11 · 곡선 하나"""
        seg = sg.segment(marker_curve(axis_only=True))
        self.assertIsNone(seg.plot_box)
        self.assertEqual(seg.dots(), 11)
        blue = {c.index for c in seg.clusters if c.name == "파랑"}
        self.assertEqual(len(kinds(seg, blue, "curve")), 1)


if __name__ == "__main__":
    unittest.main()
