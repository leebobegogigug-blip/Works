# -*- coding: utf-8 -*-
"""빽빽한 산점 — 겹침 보정 질량법 · 개수 범위 · 크기 불변 · 문이 닫힌 그림은 그대로 (설계서 14-9 · 14-11 · 14-13 · 14-15 의
AC3 · AC4 · AC5 · AC6 · AC9 · AC0). 식의 상수마다 경계 양쪽을 두고, 빽빽 판정의 문(상자 · 링 없음 · 색 군집 · 개수 · 큰 덩어리 몫 ·
곡선 빼기)마다 문이 닫혀 지금 경로로 가는 반례를 둔다. 그림은 전부 코드로 만든 것 (W-12)."""
import os
import sys
import unittest
from math import log

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import ascii1_render as rd  # noqa: E402
import ascii1_seg as sg  # noqa: E402
import synth  # noqa: E402

from shared import case, mh, seg_of, stats_of  # noqa: E402     # 읽기 전용 캐시

DENSE = ("H", "I", "Z")
COUNTED = tuple(n for n in synth.HARD if synth.HARD_SPECS[n].get("n", 300))       # 정답 개수가 있는 변형
MINI_BOX = (45, 30, 385, 265)


def mini(n=700, frame=True, color=synth.SERIES, r=(1.5, 2.5), hollow=False, ring=None, spread=False):
    """400 × 300 의 작은 산점 — 1 픽셀 틀(그림 상자) · 시그모이드 띠에 겹친 표식 n 개. spread 면 상자 전체에 고르게 흩는다"""
    c = synth.Canvas(400, 300)
    x0, y0, x1, y1 = MINI_BOX
    if frame:
        for x in (x0, x1):
            c.vline(x, y0, y1, 1, (40, 40, 40))
        for y in (y0, y1):
            c.hline(y, x0, x1, 1, (40, 40, 40))
    if ring:
        c.ring(ring[0], ring[1], ring[2], 1, (120, 120, 120))
    if spread:
        import random
        rng = random.Random(9)
        for _ in range(n):
            c.disc(rng.uniform(x0 + 4, x1 - 4), rng.uniform(y0 + 4, y1 - 4), rng.uniform(*r), color)
    else:
        synth.scatter(c, MINI_BOX, n, r, hollow, 4, color)
    return c.image()


def disc_picture(ring: bool):
    """HARD 크기 · 1 픽셀 틀 · 지름 160 원판 안에 채운 표식 900 개, ring 이면 둘레에 회색 1 픽셀 원 (반지름 170)"""
    import random
    from math import cos, pi, sin, sqrt
    c = synth.Canvas(*synth.HARD_SIZE)
    x0, y0, x1, y1 = synth.HARD_BOX
    for x in (x0, x1):
        c.vline(x, y0, y1, 1, (40, 40, 40))
    for y in (y0, y1):
        c.hline(y, x0, x1, 1, (40, 40, 40))
    if ring:
        c.ring(430, 295, 170, 1, (120, 120, 120))
    rng = random.Random(3)
    for _ in range(900):
        a, r = rng.uniform(0, 2 * pi), 80 * sqrt(rng.random())
        c.disc(430 + r * cos(a), 295 + r * sin(a), rng.uniform(1.5, 2.5), synth.SERIES)
    return c.image()


def fields(seg, name="파랑"):
    ks = {c.index for c in seg.clusters if c.name == name}
    return [e for e in seg.of("field") if e.cluster in ks]


def blue(seg):
    return [c.index for c in seg.clusters if c.name == "파랑"]


def hard(name):
    """HARD 변형의 (정답, 요소 찾기) — 시험 파일끼리 나눠 쓰는 읽기 전용 캐시 (shared). 군집별 통계는 shared.stats_of"""
    return case(name), seg_of(name)


# ─────────────────────────────────────────────────────────────── 식 (설계서 14-9)

class Formula(unittest.TestCase):
    def test_poisson_count(self):
        """n = -(c² / u) × ln(1 - min(0.9, m / c²)) 를 칸마다 더한다"""
        self.assertAlmostEqual(sg.poisson_count([50], 10, 5.0), -(100 / 5) * log(1 - 0.5), places=6)
        self.assertAlmostEqual(sg.poisson_count([50, 25, 0], 10, 5.0),
                               -20 * log(0.5) - 20 * log(0.75), places=6)
        self.assertAlmostEqual(sg.poisson_count([90], 10, 5.0), -20 * log(0.1), places=6)
        self.assertAlmostEqual(sg.poisson_count([100], 10, 5.0), -20 * log(0.1), places=6, msg="꽉 찬 칸은 0.9 에서 자른다")
        self.assertAlmostEqual(sg.poisson_count([89], 10, 5.0), -20 * log(1 - 0.89), places=6, msg="0.9 아래는 자르지 않는다")
        self.assertEqual(sg.poisson_count([], 10, 5.0), 0.0)
        self.assertGreater(sg.poisson_count([30], 10, 5.0), 30 / 5.0, "겹친 만큼 질량 ÷ 낱점 면적보다 많다")

    def test_quantile(self):
        v = [10, 20, 30, 40, 50]
        self.assertEqual((sg.quantile(v, 0.25), sg.quantile(v, 0.5), sg.quantile(v, 0.75)), (20, 30, 40))
        self.assertEqual(sg.quantile([7], 0.25), 7)
        self.assertEqual(sg.quantile([40, 10, 30, 20], 0.75), 30, "정렬해서 고른다")
        self.assertEqual(sg.quantile([40, 10, 30, 20], 0.25), 20, "자리 0.75 는 반올림해 1 (내리면 10)")

    def test_count_range_uses_quartiles(self):
        """아래 = 75% 분위수 면적으로 센 값, 위 = 25% 분위수 면적으로 센 값 (최소 폭보다 넓을 때)"""
        masses = [40, 60, 80, 10]
        areas = [10, 14, 20, 26, 30]
        mid, lo, hi = sg.count_range(masses, 10, areas)
        u = sg.unit_of(areas)
        self.assertEqual(u, 20)
        self.assertAlmostEqual(mid, sg.poisson_count(masses, 10, 20), places=6)
        self.assertAlmostEqual(lo, sg.poisson_count(masses, 10, 26), places=6)
        self.assertAlmostEqual(hi, sg.poisson_count(masses, 10, 14), places=6)
        self.assertLess(lo, 0.9 * mid)
        self.assertGreater(hi, 1.1 * mid)

    def test_count_range_is_at_least_10_percent_wide(self):
        """크기가 고른 표식은 분위수 범위가 0 — 가운데의 ±10% 로 넓힌다"""
        mid, lo, hi = sg.count_range([40, 60, 80], 10, [20] * 9)
        self.assertAlmostEqual(lo, 0.9 * mid, places=6)
        self.assertAlmostEqual(hi, 1.1 * mid, places=6)
        mid, lo, hi = sg.count_range([40, 60, 80], 10, [19, 20, 20, 20, 21])
        self.assertAlmostEqual(lo, 0.9 * mid, places=6, msg="분위수가 10% 안이면 최소 폭")
        self.assertAlmostEqual(hi, 1.1 * mid, places=6)

    def test_unit_of(self):
        """외톨이 면적의 중앙값 m 을 구하고 3m 이하만 다시 중앙값 (겹친 쌍이 외톨이처럼 보인 것을 뺀다)"""
        self.assertEqual(sg.unit_of([10, 10, 10, 30, 31]), 10)
        self.assertEqual(sg.unit_of([10, 10, 30, 31, 32]), 30, "3m = 90 이하는 다 남는다")
        self.assertEqual(sg.unit_of([10, 10, 10, 10, 31]), 10)
        self.assertEqual(sg.unit_of([2, 2, 2, 7, 6]), 2, "6 = 3m 은 남고 7 은 빠진다 — 2 2 2 6 의 중앙값")
        self.assertEqual(sg.unit_of([10, 10, 12, 14, 100, 100, 100]), 11, "3m = 42 를 넘는 셋을 빼면 10 10 12 14 (거르지 않으면 14)")
        self.assertEqual(sg.unit_of([2, 2, 2, 10, 10, 11, 12]), 10.5, "m/3 아래(번짐 잡티)도 뺀다 — 키운 그림에서 잡티가 4 칸을 넘어 들어온다")

    def test_count_range_drops_areas_over_3m(self):
        areas = [10, 10, 16, 20, 100, 100, 100]
        mid, lo, hi = sg.count_range([40, 60, 80], 10, areas)
        self.assertAlmostEqual(mid, sg.poisson_count([40, 60, 80], 10, 13), places=6)
        self.assertAlmostEqual(lo, sg.poisson_count([40, 60, 80], 10, 16), places=6, msg="75% 분위수는 걸러 낸 10 10 16 20 에서")

    def test_dense_thresholds(self):
        base = {"count": 500.0, "big": 0.5, "iso": 5}
        self.assertTrue(sg.is_dense(base))
        self.assertFalse(sg.is_dense(dict(base, count=499.9)), "개수 500 미만은 드물다")
        self.assertFalse(sg.is_dense(dict(base, big=0.499)), "큰 덩어리 몫 0.5 미만은 드물다")
        self.assertTrue(sg.is_dense(dict(base, count=3000.0, big=0.95, iso=30)))
        self.assertFalse(sg.is_dense(dict(base, count=3000.0, big=0.95, iso=29)),
                         "낱점 면적을 잰 외톨이가 추정 개수의 1% 미만이면 (번짐 잡티로 잰 낱점 면적) 드물다")


def blob(x0, y0, cells_w, cells_h, w):
    """x0 y0 에서 cells_w × cells_h 네모 덩어리 → (칸, 상자)"""
    pix = [(y0 + j) * w + x0 + i for j in range(cells_h) for i in range(cells_w)]
    return pix, sg.bbox_of(pix, w)


def comb(x0, y0, length, spread, w):
    """가로로 긴 사다리 — 위 · 아래 난간과 8 px 마다 가로대. 8 px 구간마다 세로로 퍼진 폭이 spread"""
    cells = {(x0 + x, y0) for x in range(length)} | {(x0 + x, y0 + spread - 1) for x in range(length)}
    cells |= {(x0 + x, y0 + y) for x in range(0, length, 8) for y in range(spread)}
    pix = sorted(y * w + x for x, y in cells)
    return pix, sg.bbox_of(pix, w)


def outline(x0, y0, bw, bh, w):
    """속 빈 네모 표식 bw × bh (획 1) → (칸, 상자)"""
    pix = sorted((y0 + j) * w + x0 + i for j in range(bh) for i in range(bw) if i in (0, bw - 1) or j in (0, bh - 1))
    return pix, sg.bbox_of(pix, w)


class Stats(unittest.TestCase):
    def test_diameter_cell_and_unit(self):
        """낱점 지름 = 외톨이 경계상자 긴 변의 중앙값, 칸 한 변 = 3 × 지름, 낱점 면적 = 외톨이 면적 (8 × 10 속 빈 네모 = 32 칸)"""
        w, h = 800, 600
        items = [outline(100 + 20 * k, 100, 8, 10, w) for k in range(6)]
        st = sg.density_stats(1, items, (90, 60, 770, 530), w, h)
        self.assertEqual(st["diameter"], 10, "짧은 변(8)이 아니라 긴 변")
        self.assertEqual(st["cell"], 30)
        self.assertEqual(st["unit"], 32)
        self.assertEqual(st["mass"], 6 * 32)
        self.assertEqual(st["cluster"], 1)
        self.assertIsNone(sg.density_stats(1, [blob(100, 100, 40, 3, w)], (90, 60, 770, 530), w, h), "외톨이가 없으면 None")


class BigShare(unittest.TestCase):
    """조건 4 — 낱점 면적 3 배를 넘는 덩어리에 든 질량의 몫. 곡선처럼 생긴 덩어리는 넣지 않는다"""

    def test_three_units_is_not_big(self):
        w, h = 800, 600
        u = 10.0
        small = [blob(10 + 10 * k, 10, 2, 5, w) for k in range(5)]          # 면적 10 다섯 개 = 50
        at = blob(100, 100, 3, 10, w)                                     # 30 = 3u
        self.assertAlmostEqual(sg.big_share(small + [at], u, w, h), 0.0)
        over = blob(100, 100, 31, 1, w)                                   # 31 > 3u
        self.assertAlmostEqual(sg.big_share(small + [over], u, w, h), 31 / 81)

    def test_curve_like_spread_floor_and_ratio(self):
        """곡선 = is_path 이면서 8 px 구간마다 퍼진 폭의 중앙값 ≤ max(8, 0.08 × 그림 짧은 변)"""
        w, h = 800, 50                                                     # 짧은 변 50 → 0.08 × 50 = 4 < 8 (바닥값)
        for spread, want in ((8, True), (9, False)):
            with self.subTest(spread=spread):
                pix, box = comb(10, 10, 400, spread, w)
                self.assertTrue(sg.is_path(pix, box, w, h))
                self.assertEqual(sg.curve_like(pix, box, w, h), want)
        w, h = 800, 600                                                    # 짧은 변 600 → 48
        for spread, want in ((48, True), (49, False)):
            with self.subTest(spread=spread):
                pix, box = comb(10, 10, 400, spread, w)
                self.assertTrue(sg.is_path(pix, box, w, h))
                self.assertEqual(sg.curve_like(pix, box, w, h), want)
        pix, box = blob(10, 10, 60, 60, w)
        self.assertFalse(sg.curve_like(pix, box, w, h), "is_path 가 아니면 곡선이 아니다")

    def test_curve_like_bins_are_8_px(self):
        """기울기 0.5 · 두께 3 의 지그재그: 8 px 구간이면 퍼짐 7–8 (곡선), 16 px 로 나누면 11 넘게 퍼진다"""
        w, h = 800, 50
        cells = set()
        for x in range(400):
            ph = x % 80
            y = ph * 0.5 if ph * 0.5 <= 20 else 40 - ph * 0.5
            cells |= {(10 + x, 10 + int(y) + k) for k in range(3)}
        pix = sorted(y * w + x for x, y in cells)
        self.assertTrue(sg.curve_like(pix, sg.bbox_of(pix, w), w, h))

    def test_curve_is_left_out_of_big_share(self):
        w, h = 800, 600
        small = [blob(10 + 10 * k, 10, 2, 5, w) for k in range(5)]
        line = comb(10, 100, 400, 20, w)
        wide = comb(10, 300, 400, 60, w)
        self.assertAlmostEqual(sg.big_share(small + [line], 10.0, w, h), 0.0, msg="곡선은 몫에서 뺀다 (분모에는 든다)")
        self.assertGreater(sg.big_share(small + [wide], 10.0, w, h), 0.8, "퍼진 띠는 곡선이 아니다")


# ─────────────────────────────────────────────────────────────── 빽빽한 변형 (AC4 · AC6)

class DenseHard(unittest.TestCase):
    def test_dense_variants_make_one_field(self):
        for name in DENSE:
            with self.subTest(name=name):
                c, seg = hard(name)
                fs = fields(seg)
                self.assertEqual(len(fs), 1)
                f = fs[0]
                self.assertEqual(f.pixels, [], "field 는 칸 목록을 들지 않는다")
                d = f.density
                self.assertEqual(d.mass.typecode, "I")
                self.assertEqual(len(d.mass), d.cols * d.rows)
                self.assertEqual(sum(d.mass), f.area)
                self.assertEqual((d.block, d.cols, d.rows), (2, 341, 236), "상자 681 px ÷ 300 열 → 블록 2 px")
                self.assertEqual((d.x0, d.y0), seg.plot_box[:2])
                self.assertEqual(f.count, d.count)
                self.assertTrue(d.count_lo <= d.count <= d.count_hi)
                k = f.cluster
                self.assertEqual(seg.unit[k], d.unit)
                inside = [e for e in seg.elements if e.cluster == k and e.kind in ("dot", "text", "curve")
                          and sg.in_plot(seg.plot_box, e.bbox)]
                self.assertEqual(inside, [], "상자 안의 칸은 모두 field 에 — 점 · 글자 · 곡선으로 가지 않는다")

    def test_ac4_range_holds_truth_and_middle_within_25_percent(self):
        for name in DENSE:
            with self.subTest(name=name):
                c, seg = hard(name)
                d = fields(seg)[0].density
                self.assertTrue(d.count_lo <= c.n <= d.count_hi, "%s 범위 %d–%d · 정답 %d" % (name, d.count_lo, d.count_hi, c.n))
                self.assertLessEqual(abs(d.count - c.n), 0.25 * c.n, "%s 가운데 %d" % (name, d.count))
                self.assertGreaterEqual(d.count_hi - d.count_lo, 0.2 * d.count - 2, "범위는 적어도 ±10%")

    def test_ac6_density_correlation(self):
        for name in DENSE:
            with self.subTest(name=name):
                c, seg = hard(name)
                ks = blue(seg)
                self.assertGreaterEqual(mh.density(seg, c, ks, 16, 8), 0.95)
                self.assertGreaterEqual(mh.density(seg, c, ks, 60, 25), 0.90)

    def test_dots_and_range_include_the_field(self):
        c, seg = hard("H")
        f = fields(seg)[0]
        self.assertEqual(seg.dots(f.cluster), f.count)
        lo, hi = seg.dots_range(f.cluster)
        self.assertEqual((lo, hi), (f.density.count_lo, f.density.count_hi))
        n = seg.dots()
        alo, ahi = seg.dots_range()
        self.assertEqual(alo, n - f.count + f.density.count_lo)
        self.assertEqual(ahi, n - f.count + f.density.count_hi)

    def test_ac4_every_counted_variant_range_holds_truth(self):
        """설계서 [실험 T2]: 겹침 보정 범위는 정답이 있는 HARD 변형 모두에서 정답을 품었다 (드문 변형도 — 판정에 쓰는 값이다)"""
        for name in COUNTED:
            with self.subTest(name=name):
                c, seg = hard(name)
                st = [s for s in stats_of(name) if s is not None]
                self.assertTrue(st, "%s: 파랑 외톨이가 있어 통계를 낸다" % name)
                first = max(st, key=lambda s: s["mass"])      # 정답 계열은 질량이 가장 큰 군집
                self.assertTrue(first["lo"] <= c.n <= first["hi"], "%s 범위 %.0f–%.0f · 정답 %d" % (name, first["lo"], first["hi"], c.n))

    def test_ac9_two_series_each(self):
        """L: 파랑 300 · 주황 150 — 둘 다 드물어 계열마다 지금 경로의 개수(±10%)와 밀도 상관을 지킨다. 파랑의 겹침 보정 범위는
        정답을 품는다. 주황의 범위는 품지 못한다 — 빨강 추세선이 주황 군집에 합쳐져(Q6 의 알려진 한계) 그 칸이 질량에 든다"""
        c, seg = hard("L")
        names = {k.index: k.name for k in seg.clusters}
        by = {names[s["cluster"]]: s for s in stats_of("L") if s is not None}
        self.assertTrue(by["파랑"]["lo"] <= c.n <= by["파랑"]["hi"])
        self.assertGreater(by["주황"]["lo"], len(c.pts2), "추세선 질량이 든 범위 (알려진 한계 — 고쳐지면 이 줄을 뒤집는다)")
        self.assertEqual(seg.of("field"), [])
        for nm, n, series in (("파랑", c.n, 0), ("주황", len(c.pts2), 1)):
            ks = [k.index for k in seg.clusters if k.name == nm]
            with self.subTest(series=nm):
                self.assertLessEqual(abs(seg.dots(ks[0]) - n), 0.10 * n, "%s 추정 %d · 정답 %d" % (nm, seg.dots(ks[0]), n))
                for gx, gy, r in ((16, 8, 0.95), (60, 25, 0.80)):
                    got = mh.pearson([float(v) for v in c.cell_counts(gx, gy, series)],
                                     mh.estimates(seg, c, ks, gx, gy))
                    self.assertGreaterEqual(got, r, "%s %d×%d" % (nm, gx, gy))


class SparseHard(unittest.TestCase):
    """드문 변형은 field 가 없고 개수는 지금 경로 (AC3 — 채운 원판 겹친 쌍도 ±10%)"""

    def test_sparse_variants_have_no_field(self):
        for name in COUNTED:
            if name in DENSE:
                continue
            with self.subTest(name=name):
                c, seg = hard(name)
                self.assertEqual(seg.of("field"), [])

    def test_ac3_sparse_counts_within_10_percent(self):
        for name in ("A0", "A3", "F0", "F1", "A1", "A_base"):
            with self.subTest(name=name):
                c, seg = hard(name)
                est = seg.dots(blue(seg)[0])
                self.assertLessEqual(abs(est - c.n), 0.10 * c.n, "%s 추정 %d · 정답 %d" % (name, est, c.n))


# ─────────────────────────────────────────────────────────────── 문 (설계서 14-13) · 크기 불변 (AC5)

class Gates(unittest.TestCase):
    def test_mini_is_dense(self):
        seg = sg.segment(mini())
        fs = fields(seg)
        self.assertEqual(len(fs), 1)
        d = fs[0].density
        self.assertTrue(d.count_lo <= 700 <= d.count_hi, (d.count_lo, d.count, d.count_hi))
        self.assertEqual(d.cell, int(round(3 * d.diameter)), "칸 한 변 = 3 × 낱점 지름")

    def test_no_plot_box_closes(self):
        seg = sg.segment(mini(frame=False))
        self.assertIsNone(seg.plot_box)
        self.assertEqual(seg.of("field"), [])

    def test_ring_closes(self):
        """원 안에 몰린 표식 — 링이 없으면 빽빽하고, 같은 그림에 링이 있으면 지금 경로 (링을 띠가 끊지 않게 원판 안에만 흩는다)"""
        for ring, want in ((False, 1), (True, 0)):
            with self.subTest(ring=ring):
                seg = sg.segment(disc_picture(ring))
                self.assertEqual(seg.ring is not None, ring)
                self.assertIsNotNone(seg.plot_box)
                self.assertEqual(len(seg.of("field")), want)

    def test_neutral_closes(self):
        seg = sg.segment(mini(color=synth.INK))
        self.assertEqual(seg.of("field"), [], "중립(검정) 군집에는 켜지 않는다")

    def test_few_points_close(self):
        seg = sg.segment(mini(n=250))
        self.assertEqual(seg.of("field"), [], "겹침 보정 개수 500 미만")

    def test_scattered_points_close(self):
        """개수는 500 을 넘어도 고르게 흩어져 큰 덩어리 몫이 작으면 드물다"""
        seen = []
        real = sg.density_stats

        def spy(*args):
            st = real(*args)
            seen.append(st)
            return st

        sg.density_stats = spy
        try:
            seg = sg.segment(mini(n=900, spread=True, r=(1.2, 1.6)))
        finally:
            sg.density_stats = real
        st = [s for s in seen if s is not None][0]
        self.assertGreaterEqual(st["count"], sg.DENSE_MIN_N)
        self.assertLess(st["big"], sg.DENSE_BIG)
        self.assertEqual(seg.of("field"), [])

    def test_curve_with_markers_stays_sparse(self):
        """상자 안의 굵은 물결 곡선 + 외톨이 표식: 곡선 질량으로 개수는 500 을 넘지만 곡선은 큰 덩어리 몫에서 빠진다"""
        c = synth.Canvas(*synth.HARD_SIZE)
        x0, y0, x1, y1 = synth.HARD_BOX
        for x in (x0, x1):
            c.vline(x, y0, y1, 1, (40, 40, 40))
        for y in (y0, y1):
            c.hline(y, x0, x1, 1, (40, 40, 40))
        from math import sin, pi
        pts = [(x, 300 + 60 * sin(2 * pi * (x - 100) / 200)) for x in range(100, 761, 4)]
        c.polyline(pts, 9, synth.SERIES)
        for k in range(12):
            c.disc(120 + 55 * k, 120, 1.6, synth.SERIES)
        seen = []
        real = sg.density_stats

        def spy(*args):
            st = real(*args)
            seen.append(st)
            return st

        sg.density_stats = spy
        try:
            seg = sg.segment(c.image())
        finally:
            sg.density_stats = real
        st = [s for s in seen if s is not None][0]
        self.assertGreaterEqual(st["count"], sg.DENSE_MIN_N)
        self.assertLess(st["big"], sg.DENSE_BIG)
        self.assertEqual(seg.of("field"), [])


    def test_line_pieces_with_specks_stay_sparse(self):
        """굵은 점선 두 줄(추세선 · 가로선으로 잡히지 않게 비스듬히 나란히) + 2 × 2 번짐 잡티 8 개: 잡티로 잰 낱점 면적 4 로
        선 조각 질량을 세면 5000 개가 넘는다 — 외톨이가 추정 개수의 1% 에 못 미쳐 빽빽하지 않다 (부드럽게 키운 실제 그림의 빨강 추세선)"""
        c = synth.Canvas(*synth.HARD_SIZE)
        x0, y0, x1, y1 = synth.HARD_BOX
        for x in (x0, x1):
            c.vline(x, y0, y1, 1, (40, 40, 40))
        for y in (y0, y1):
            c.hline(y, x0, x1, 1, (40, 40, 40))
        for off in (0, 90):
            synth.dashed(c, [(110, 440 + off), (750, 140 + off)], 40, 10, 9, synth.TREND)
        for k in range(8):
            c.rect(130 + 70 * k, 100, 131 + 70 * k, 101, synth.TREND)
        seen = []
        real = sg.density_stats

        def spy(*args):
            st = real(*args)
            seen.append(st)
            return st

        sg.density_stats = spy
        try:
            seg = sg.segment(c.image())
        finally:
            sg.density_stats = real
        st = [s for s in seen if s is not None][0]
        self.assertGreater(st["count"], 5000)
        self.assertGreater(st["big"], 0.9)
        self.assertEqual(st["iso"], 8)
        self.assertEqual(seg.of("field"), [])


class SizeInvariance(unittest.TestCase):
    """AC5: 같은 그림을 2 배로 (가장 가까운 칸 · 부드럽게) 키워도 추정 개수 변화 ≤ 15% (0.2.0 은 ×3.98)"""

    def assertSteady(self, one, two, what):
        self.assertLessEqual(abs(two - one), 0.15 * one, "%s: %d → %d" % (what, one, two))

    def test_mini_both_zooms(self):
        img = mini()
        one = fields(sg.segment(img))[0].count
        for how, zoom in (("가장 가까운 칸", synth.zoom), ("부드럽게", synth.zoom_smooth)):
            with self.subTest(zoom=how):
                fs = fields(sg.segment(zoom(img, 2)))
                self.assertEqual(len(fs), 1, "2 배여도 빽빽하다")
                self.assertSteady(one, fs[0].count, how)

    def test_hard_dense_smooth_zoom(self):
        c, seg = hard("I")
        one = fields(seg)[0].count
        big = sg.segment(synth.zoom_smooth(c.image, 2))
        fs = fields(big)
        self.assertEqual(len(fs), 1)
        self.assertSteady(one, fs[0].count, "I 부드럽게 2 배")
        self.assertTrue(fs[0].density.count_lo <= c.n <= fs[0].density.count_hi)

    def test_sparse_nearest_zoom(self):
        c, seg = hard("A3")
        one = seg.dots(blue(seg)[0])
        big = sg.segment(synth.zoom(c.image, 2))
        self.assertEqual(big.of("field"), [])
        self.assertSteady(one, big.dots(blue(big)[0]), "A3 2 배")


# ─────────────────────────────────────────────────────────────── 회귀 (AC0) · 렌더 (14-11)

class Unchanged(unittest.TestCase):
    """골든 그림은 문이 닫혀 field 가 없다. chart* · wafer* · line* 합성 그림의 요소 전부가 그대로인 것은 test_seg_equiv 의 SNAPSHOT 이 지킨다"""

    def test_golden_pictures_stay_sparse(self):
        for name, img in (("chart", synth.control_chart()[0]), ("wafer", synth.wafer_map(plus=3)[0])):
            with self.subTest(name=name):
                seg = sg.segment(img)
                self.assertEqual(seg.of("field"), [])
                self.assertEqual(seg.dots_range(), (seg.dots(), seg.dots()))


class Render(unittest.TestCase):
    def test_field_drawn_with_point_ladder(self):
        c, seg = hard("H")
        f = fields(seg)[0]
        text = rd.render(seg, 120)
        art = text.rsplit("\n\n", 1)[0]
        g = rd.assign_glyphs(seg)[f.cluster]["point"]
        self.assertGreater(sum(art.count(ch) for ch in g), 100)
        self.assertGreater(art.count(g[2]), 10, "빽빽한 곳은 사다리의 맨 위 글자")
        geo = rd.Geometry(seg, 120)
        cells = rd.allocate_dots(seg, geo)
        self.assertEqual(sum(v.get(f.cluster, 0) for v in cells.values()), f.count, "셀에 나눈 개수의 합 = 가운데 값")
        legend = text.rsplit("\n\n", 1)[1]
        self.assertIn("약", legend)
        self.assertIn("빽빽", legend)
        self.assertTrue(all(ord(ch) < 128 for ch in art), "격자는 순수 ASCII")

    def test_range_words(self):
        self.assertEqual(rd.about(2047, 2957), "약 2000–3000개")
        self.assertEqual(rd.about(1804, 2205), "약 1800–2300개")
        self.assertEqual(rd.about(63, 77), "약 63–77개")
        self.assertEqual(rd.about(99, 121), "약 99–130개")


if __name__ == "__main__":
    unittest.main()
