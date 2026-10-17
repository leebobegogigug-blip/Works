# -*- coding: utf-8 -*-
"""ascii1_seg 테스트 — 합성한 선 차트 · 웨이퍼 맵으로 구조 불변량을 지킨다 (글자 하나가 아니라 개수 · 위치 · 닫힘).
그림은 전부 코드로 만든 것 (W-12). JPEG 흉내(soften)를 입힌 것도 같은 기대를 받는다."""
import os
import random
import sys
import unittest
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import ascii1_seg as sg  # noqa: E402
import synth  # noqa: E402
from ascii1_png import Image  # noqa: E402


def names(seg):
    return {c.index: c.name for c in seg.clusters}


def by_name(seg, kind):
    n = names(seg)
    return Counter(n[e.cluster] for e in seg.elements if e.kind == kind)


class ControlChart(unittest.TestCase):
    def check(self, img, markers):
        seg = sg.segment(img)
        n = names(seg)
        self.assertEqual(seg.guess_kind(), "chart")
        self.assertTrue({"파랑", "빨강", "노랑"} <= set(n.values()))
        self.assertEqual(len(n), 4, "검정(회색) · 파랑 · 빨강 · 노랑")
        blue = [c.index for c in seg.clusters if c.name == "파랑"][0]
        self.assertEqual(seg.dots(blue), markers, "마커 수")
        hl = by_name(seg, "hline")
        self.assertEqual((hl["빨강"], hl["노랑"]), (2, 2), "한계선")
        self.assertEqual(sum(v for k, v in hl.items() if k in ("검정", "회색")), 2, "중심선 + 아래 축")
        self.assertEqual(sum(v for k, v in by_name(seg, "vline").items() if k in ("검정", "회색")), 1, "왼쪽 축")
        self.assertGreaterEqual(len(seg.of("curve")), 1, "꺾은선")
        # 파랑이 아닌 군집에서 점이 새지 않는다 (글자 · 번짐 · 선 조각은 점이 아니다)
        self.assertEqual(sum(seg.dots(c.index) for c in seg.clusters if c.index != blue), 0)
        return seg

    def test_clean(self):
        img, markers = synth.control_chart()
        seg = self.check(img, markers)
        self.assertAlmostEqual(seg.line_thickness, 2.5, delta=0.7)
        self.assertGreaterEqual(len(seg.of("text")), 17, "UCL · 110 · 105 · 100 · CL · 5 · 1 · 0 의 글자 17 개")

    def test_blurred_and_noisy(self):
        img, markers = synth.control_chart()
        self.check(synth.soften(img), markers)

    def test_other_marker_counts(self):
        for k in (5, 20):
            with self.subTest(markers=k):
                img, markers = synth.control_chart(k)
                self.check(img, markers)

    def test_label_next_to_line_end_stays_text(self):
        # 선 끝 옆의 UCL 글자가 선 띠와 같이 지워지지 않는다: 빨강 글자 3 개가 남아야
        img, _ = synth.control_chart()
        seg = sg.segment(img)
        red_text = [e for e in seg.of("text") if names(seg)[e.cluster] == "빨강"]
        self.assertEqual(len(red_text), 3)
        self.assertTrue(all(e.bbox[0] >= 400 for e in red_text))


class LineChartOnly(unittest.TestCase):
    """가로 · 세로선이 없는 차트: 선 두께를 곡선 자체에서 재서 마커를 가른다"""

    def test_markers_without_any_straight_line(self):
        for img_fn in (lambda: synth.line_chart()[0], lambda: synth.soften(synth.line_chart()[0]),
                       lambda: synth.zoom(synth.line_chart()[0], 2)):
            seg = sg.segment(img_fn())
            self.assertEqual(seg.of("hline") + seg.of("vline"), [])
            self.assertEqual(seg.dots(), 12)
            self.assertGreaterEqual(len(seg.of("curve")), 1)

    def test_other_marker_counts(self):
        for k in (4, 9, 20):
            with self.subTest(markers=k):
                img, n = synth.line_chart(k)
                self.assertEqual(sg.segment(img).dots(), n)

    def test_wafer_dense_cluster_is_not_mistaken_for_a_curve(self):
        # 선이 없는 웨이퍼의 뭉친 점 덩어리가 곡선 두께 추정을 건드려 점으로 안 세어지면 안 된다
        img, info = synth.wafer_map()
        seg = sg.segment(img)
        self.assertEqual(seg.of("curve"), [])
        self.assertEqual(seg.dots(), info["blue"] + info["tile"] + info["orange"] + info["gray"])


class DotChains(unittest.TestCase):
    """점이 사슬처럼 닿아 이어진 길쭉한 덩어리는 곡선이 아니라 점 무리다 (실제 웨이퍼의 점 기둥이 곡선으로 오인되어 파랑 점이 165 → 13 개로 줄었던 회귀)"""

    def check(self, ring):
        img, info = synth.wafer_map(stripe=40, ring=ring)
        seg = sg.segment(img)
        self.assertEqual(seg.of("curve"), [], "점 사슬이 곡선이 되었다")
        want = info["blue"] + info["tile"] + info["orange"] + info["gray"] + info["stripe"]
        self.assertEqual(seg.dots(), want)
        return seg

    def test_with_and_without_the_ring(self):
        self.check(True)
        self.check(False)

    def test_blurred_and_zoomed(self):
        img, info = synth.wafer_map(stripe=40, ring=False)
        for variant in (synth.soften(img), synth.zoom(img, 2)):
            seg = sg.segment(variant)
            self.assertEqual(seg.of("curve"), [])
            want = info["blue"] + info["tile"] + info["orange"] + info["gray"] + info["stripe"]
            self.assertLessEqual(abs(seg.dots() - want), 0.1 * want)

    def test_path_gate(self):
        # 이어진 선처럼 그림을 가로지르면 곡선, 짧거나 끊기면 아니다
        w = 200
        straight = [y * w + x for y in range(98, 101) for x in range(10, 190)]
        self.assertTrue(sg.is_path(straight, (10, 98, 189, 100), w, 200) is False, "속이 찬 띠는 곡선이 아니다(채움률)")
        diag = [(10 + 2 * k + dy) * w + (10 + 2 * k) for k in range(80) for dy in range(3)]
        box = sg.bbox_of(diag, w)
        self.assertTrue(sg.is_path(diag, box, w, 200))
        gap = [i for i in diag if not 60 <= i % w < 120]
        self.assertFalse(sg.is_path(gap, sg.bbox_of(gap, w), w, 200), "가운데가 끊긴 무리는 한 줄이 아니다")
        short = [i for i in diag if i % w < 60]
        self.assertFalse(sg.is_path(short, sg.bbox_of(short, w), w, 200), "그림을 가로지르지 않는다")


class WaferMap(unittest.TestCase):
    def check(self, img, info, exact=True):
        seg = sg.segment(img)
        n = {v: k for k, v in names(seg).items()}
        self.assertEqual(seg.guess_kind(), "wafer")
        ring = seg.ring
        self.assertAlmostEqual(ring.r, info["R"], delta=2)
        self.assertAlmostEqual(ring.cx, info["center"][0], delta=2)
        self.assertGreaterEqual(ring.closed, 0.95, "외곽이 닫혀 있다")
        self.assertIsNotNone(ring.notch, "노치")
        self.assertLess(abs((ring.notch - 90 + 180) % 360 - 180), 12, "노치는 아래쪽(90°)")
        self.assertEqual(len(seg.of("ring")), 1)
        blue, orange = seg.dots(n["파랑"]), seg.dots(n["주황"])
        want_blue = info["blue"] + info["tile"] + info["plus"]
        if exact:
            self.assertEqual((blue, orange), (want_blue, info["orange"]))
        else:
            self.assertLessEqual(abs(blue - want_blue), 0.15 * want_blue)
            self.assertLessEqual(abs(orange - info["orange"]), 0.2 * info["orange"] + 1)
        gray = [e for e in seg.elements if e.kind == "dot" and names(seg)[e.cluster] in ("회색", "검정")]
        self.assertEqual(sum(e.count for e in gray), info["gray"], "회색 점 (외곽선은 점이 아니다)")
        self.assertEqual(len(seg.of("text")), 0, "링 안은 데이터라 글자가 없다")
        return seg

    def test_clean(self):
        img, info = synth.wafer_map()
        seg = self.check(img, info)
        # 빈틈없이 깐 덩어리는 면적 ÷ 낱점 면적으로 센다 (4×4 = 16 개)
        n = {v: k for k, v in names(seg).items()}
        big = max((e for e in seg.of("dot") if e.cluster == n["파랑"]), key=lambda e: e.count)
        self.assertEqual(big.count, info["tile"])
        self.assertAlmostEqual(seg.unit[n["파랑"]], 9, delta=1)

    def test_blurred_and_noisy(self):
        img, info = synth.wafer_map()
        self.check(synth.soften(img), info, exact=False)

    def test_faint_ring_that_straddles_pixels(self):
        # 1칸 선이 격자 중간에 걸려 반쯤 옅어진 외곽: 거리 60 만으로는 끊긴다 (옅은 칸 이어 붙이기)
        img, info = synth.wafer_map(faint=True)
        seg = sg.segment(img)
        self.assertIsNotNone(seg.ring)
        self.assertGreaterEqual(seg.ring.closed, 0.95)
        self.assertLess(abs((seg.ring.notch - 90 + 180) % 360 - 180), 12)

    def test_letter_like_clusters_inside_the_ring_are_data(self):
        img, info = synth.wafer_map(plus=3)
        seg = self.check(img, info)
        self.assertEqual(len(seg.of("text")), 0)

    def test_diamond_frame_is_not_a_ring(self):
        # 선(가로 · 세로)으로 먼저 걸러지지 않는 빈 정사각형(마름모) — 정사각 경계상자라도 원이 아니다
        c = synth.Canvas(200, 200)
        for k in range(0, 81):
            for x, y in ((100 + k, 20 + k), (180 - k, 100 + k), (100 - k, 180 - k), (20 + k, 100 - k)):
                c.set(x, y, synth.GRAY)
        for x, y in ((90, 100), (110, 95), (100, 120)):
            c.rect(x, y, x + 2, y + 2, synth.BLUE)
        seg = sg.segment(c.image())
        self.assertIsNone(seg.ring)

    def test_wafer_without_notch(self):
        img, info = synth.wafer_map(notch=False)
        seg = sg.segment(img)
        self.assertIsNotNone(seg.ring)
        self.assertIsNone(seg.ring.notch)
        self.assertGreaterEqual(seg.ring.closed, 0.95)

    def test_square_frame_is_not_a_ring(self):
        c = synth.Canvas(200, 200)
        c.rect(20, 20, 180, 21, synth.GRAY)
        c.rect(20, 178, 180, 179, synth.GRAY)
        c.rect(20, 20, 21, 180, synth.GRAY)
        c.rect(178, 20, 179, 180, synth.GRAY)
        for x, y in ((60, 60), (100, 120), (140, 90)):
            c.rect(x, y, x + 2, y + 2, synth.BLUE)
        seg = sg.segment(c.image())
        self.assertIsNone(seg.ring)
        self.assertEqual(seg.dots(), 3)


class Scale(unittest.TestCase):
    """같은 그림을 키워도 같은 구조 · 같은 개수가 나온다 (문턱이 픽셀 크기에 묶이면 여기서 깨진다)"""

    def counts(self, seg):
        return {names(seg)[c.index]: seg.dots(c.index) for c in seg.clusters}

    def test_wafer_zoomed(self):
        img, info = synth.wafer_map(plus=3)
        base = self.counts(sg.segment(img))
        for f in (2, 3):
            with self.subTest(zoom=f):
                big = synth.zoom(img, f)
                wide = synth.zoom(synth.soften(synth.soften(img, 0.8), 0.8), f)       # 번짐이 f 배로 넓어진 것
                for variant in (big, synth.soften(big), synth.zoom(synth.soften(img), f), wide):
                    seg = sg.segment(variant)
                    got = self.counts(seg)
                    self.assertEqual(got["파랑"], base["파랑"])
                    self.assertEqual(got["주황"], base["주황"])
                    self.assertEqual(got.get("회색", 0) + got.get("검정", 0), info["gray"])
                    self.assertTrue(seg.ring is not None and seg.ring.closed >= 0.95)
                    self.assertAlmostEqual(seg.ring.r, info["R"] * f, delta=2 * f)
                    self.assertLess(abs((seg.ring.notch - 90 + 180) % 360 - 180), 12)

    def test_gray_halo_around_colored_dots_is_not_dots(self):
        # 점 둘레의 두꺼운 회색 테두리 — 크기를 키우면 테두리도 같이 두꺼워진다. 반경이 낱점 크기에 비례해야 번짐으로 거른다
        img, info = synth.wafer_map(halo=2)
        for f in (1, 3):
            with self.subTest(zoom=f):
                seg = sg.segment(synth.zoom(img, f) if f > 1 else img)
                got = self.counts(seg)
                self.assertEqual((got["파랑"], got["주황"]), (info["blue"] + info["tile"], info["orange"]))
                self.assertEqual(got.get("회색", 0) + got.get("검정", 0), info["gray"], "테두리가 회색 점으로 세어졌다")

    def test_slightly_squashed_wafer_zoomed(self):
        # 완벽한 원이 아니어도(세로 4% 눌림) 외곽은 외곽이다 — 허용 오차가 반지름에 비례해야 키워도 닫힌다
        img, info = synth.wafer_map(squash=0.04)
        for f in (1, 3):
            with self.subTest(zoom=f):
                seg = sg.segment(synth.zoom(img, f) if f > 1 else img)
                self.assertIsNotNone(seg.ring)
                self.assertGreaterEqual(seg.ring.closed, 0.9)

    def test_chart_zoomed(self):
        img, markers = synth.control_chart()
        for f in (2, 3):
            with self.subTest(zoom=f):
                seg = sg.segment(synth.zoom(img, f))
                blue = [c.index for c in seg.clusters if c.name == "파랑"][0]
                self.assertEqual(seg.dots(blue), markers)
                self.assertEqual(sum(seg.dots(c.index) for c in seg.clusters if c.index != blue), 0)
                hl = by_name(seg, "hline")
                self.assertEqual((hl["빨강"], hl["노랑"]), (2, 2))


class Unsupported(unittest.TestCase):
    def test_photo_like_noise_is_refused_quickly(self):
        rng = random.Random(2)
        img = Image(200, 200, bytes(rng.randrange(256) for _ in range(3 * 200 * 200)))
        seg = sg.segment(img)
        self.assertIn("절반", seg.reason)
        self.assertEqual(seg.elements, [])

    def test_normal_pictures_have_no_reason(self):
        for img in (synth.control_chart()[0], synth.wafer_map()[0], synth.Canvas(10, 10).image()):
            self.assertEqual(sg.segment(img).reason, "")


class TextRuns(unittest.TestCase):
    """글자 줄 판정 도우미를 직접 — 다른 규칙과 겹쳐 있어서 통합 시험만으로는 빠졌는지 알 수 없다"""

    def box(self, x, y, w=5, h=8):
        return (x, y, x + w - 1, y + h - 1)

    def test_glyph_run_needs_a_non_round_member(self):
        row = [(0, self.box(10, 20), 20, False), (1, self.box(17, 20), 20, False), (2, self.box(24, 21), 20, True),
               (3, self.box(80, 60), 20, False)]
        self.assertEqual(sg.glyph_runs(row, False), {0, 1, 2})
        dots = [(0, self.box(10, 20), 40, True), (1, self.box(17, 20), 40, True), (2, self.box(24, 20), 40, True)]
        self.assertEqual(sg.glyph_runs(dots, False), set(), "모두 둥글면 글자가 아니다")

    def test_glyph_run_survives_two_interleaved_lines(self):
        a = [(n, self.box(10 + 7 * n, 20), 20, False) for n in range(3)]
        b = [(3 + n, self.box(10 + 7 * n, 60), 20, False) for n in range(3)]
        self.assertEqual(sg.glyph_runs(a + b, False), {0, 1, 2, 3, 4, 5})

    def test_vertical_run(self):
        col = [(n, self.box(30, 10 + 9 * n, 8, 5), 20, False) for n in range(3)]
        self.assertEqual(sg.glyph_runs(col, True), {0, 1, 2})

    def test_aligned_row_pulls_in_a_round_label(self):
        row = [(0, self.box(10, 100, 5, 8), 30, True), (1, self.box(70, 100), 20, False), (2, self.box(130, 101), 20, False)]
        self.assertEqual(sg.aligned_rows(row, False), {0, 1, 2})
        off = row + [(3, self.box(190, 110), 20, False)]
        self.assertEqual(sg.aligned_rows(off, False), {0, 1, 2}, "줄에서 벗어난 것은 빠진다")

    def test_alignment_tolerance_scales_with_glyph_size(self):
        big = [(n, self.box(10 + 60 * n, 100 + 4 * (n % 2), 14, 20), 80, False) for n in range(3)]
        self.assertEqual(sg.aligned_rows(big, False), {0, 1, 2}, "큰 글자는 중심이 4px 어긋나도 한 줄")
        small = [(n, self.box(10 + 60 * n, 100 + 4 * (n % 2), 5, 8), 20, False) for n in range(3)]
        self.assertEqual(sg.aligned_rows(small, False), set(), "작은 글자는 4px 어긋나면 한 줄이 아니다")

    def test_two_in_a_row_is_not_enough(self):
        self.assertEqual(sg.aligned_rows([(0, self.box(10, 100), 20, False), (1, self.box(70, 100), 20, False)], False), set())


class Discs(unittest.TestCase):
    """반지름이 정수인 원판(r 2–8, 채움률 0.52–0.68)도 둥근 점이다 — 글자 줄이 되거나 낱점 면적에서 빠지면 안 된다"""

    def test_markers_in_a_row_are_not_text(self):
        for r in (2, 3, 4, 6):          # r 8 이면 다섯 개가 한 행의 40% 를 덮어 가로선이 된다 (MANUAL › 알려진 한계)
            c = synth.Canvas(60 + 30 * 5, 80)
            for k in range(5):
                c.disc(20 + 30 * k, 40, r, synth.RED)
            seg = sg.segment(c.image())
            self.assertEqual(seg.of("text"), [], r)
            self.assertEqual(seg.dots(), 5, r)

    def test_lone_markers_count_one_each(self):
        c = synth.Canvas(160, 100)
        for k, (x, y) in enumerate(((20, 20), (60, 70), (100, 30), (140, 80))):
            c.disc(x, y, 3, synth.BLUE)
        seg = sg.segment(c.image())
        self.assertEqual(seg.dots(), 4)
        self.assertEqual(seg.unit[seg.clusters[0].index], 29)

    def test_glyphs_are_not_discs(self):
        for ch, rows in synth.FONT.items():
            pix = [y * 10 + x for y, row in enumerate(rows) for x, v in enumerate(row) if v == "#"]
            self.assertFalse(sg.is_disc(pix, sg.bbox_of(pix, 10), 10), ch)

    def test_hollow_ring_and_square_are_not_discs(self):
        ring = [y * 20 + x for y in range(11) for x in range(11) if 3.5 <= ((x - 5) ** 2 + (y - 5) ** 2) ** 0.5 <= 5]
        square = [y * 20 + x for y in range(9) for x in range(9)]
        self.assertFalse(sg.is_disc(ring, sg.bbox_of(ring, 20), 20))
        self.assertFalse(sg.is_disc(square, sg.bbox_of(square, 20), 20))


class Colors(unittest.TestCase):
    def test_dark_background(self):
        c = synth.Canvas(120, 100, bg=(10, 10, 20))
        for x, y in ((20, 20), (60, 40), (90, 70)):
            c.rect(x, y, x + 3, y + 3, (255, 255, 255))
        seg = sg.segment(c.image())
        self.assertEqual(seg.bg, (10, 10, 20))
        self.assertEqual(seg.dots(), 3)

    def test_two_colors_make_two_clusters(self):
        c = synth.Canvas(100, 100)
        for x in (10, 30, 50):
            c.rect(x, 10, x + 3, 13, synth.BLUE)
            c.rect(x, 60, x + 3, 63, synth.ORANGE)
        seg = sg.segment(c.image())
        self.assertEqual(sorted(cl.name for cl in seg.clusters), ["주황", "파랑"])
        self.assertEqual([seg.dots(cl.index) for cl in seg.clusters], [3, 3])

    def test_border_box_on_the_edge_is_not_the_background(self):
        """그림 가장자리를 두른 테두리(내보낸 차트의 틀) 색이 가장자리의 최빈색이어도 바탕은 안쪽의 흰색이다"""
        img, markers = synth.control_chart(frame=True)
        c = synth.Canvas(img.width, img.height)
        c.px = [tuple(img.rgb[3 * i:3 * i + 3]) for i in range(img.width * img.height)]
        for t in (1, 3):
            c.rect(0, 0, img.width - 1, t - 1, synth.BLACK)
            c.rect(0, img.height - t, img.width - 1, img.height - 1, synth.BLACK)
            c.rect(0, 0, t - 1, img.height - 1, synth.BLACK)
            c.rect(img.width - t, 0, img.width - 1, img.height - 1, synth.BLACK)
            seg = sg.segment(c.image())
            self.assertEqual(seg.bg, (255, 255, 255), t)
            self.assertEqual(seg.reason, "", t)
            self.assertEqual(seg.dots(), markers, t)

    def test_noisy_background_keeps_the_edge_color(self):
        """바탕이 잡음으로 여러 색에 흩어져 어느 한 색보다 큰 단색 덩어리가 있어도 바탕은 가장자리 쪽이다"""
        rng = random.Random(5)
        c = synth.Canvas(100, 100)
        c.px = [(255 - rng.randrange(6), 255 - rng.randrange(6), 255 - rng.randrange(6)) for _ in range(100 * 100)]
        c.rect(30, 30, 69, 69, synth.BLUE)                    # 1600 칸 — 바탕의 어느 한 색(약 40 칸)보다 많다
        seg = sg.segment(c.image())
        self.assertGreater(min(seg.bg), 240)

    def test_faint_gray_panel_is_background(self):
        """바탕과 거리 30–60 의 옅은 회색 판(그래프 판 채우기)은 중립 전경에 닿지 않으면 바탕이다"""
        c = synth.Canvas(200, 150)
        c.rect(20, 10, 190, 130, (235, 235, 235))
        for k in range(8):
            c.disc(30 + 20 * k, 30 + 8 * k, 4, synth.BLUE)
        seg = sg.segment(c.image())
        self.assertEqual(seg.reason, "")
        self.assertEqual([cl.name for cl in seg.clusters], ["파랑"])
        self.assertEqual(seg.dots(), 8)

    def test_faint_gray_still_joins_a_neutral_line(self):
        """옅은 칸이 진한 중립 선에 닿아 있으면 그 선의 일부다 (1칸 옅은 외곽이 격자에 걸린 것)"""
        c = synth.Canvas(200, 100)
        c.rect(10, 50, 189, 50, (0, 0, 0))
        c.rect(10, 51, 189, 51, (215, 215, 215))
        seg = sg.segment(c.image())
        self.assertEqual(len(seg.of("hline")), 1)
        self.assertEqual(seg.of("hline")[0].bbox[1:4:2], (50, 51))

    def test_clusters_are_ordered_by_area(self):
        c = synth.Canvas(100, 100)
        c.rect(10, 10, 40, 40, synth.BLUE)
        c.rect(60, 60, 64, 64, synth.ORANGE)
        seg = sg.segment(c.image())
        self.assertEqual([cl.name for cl in seg.clusters], ["파랑", "주황"])
        self.assertGreater(seg.clusters[0].pixels, seg.clusters[1].pixels)


class Robust(unittest.TestCase):
    def test_empty_and_tiny_images(self):
        for w, h in ((1, 1), (2, 2), (3, 1), (1, 7), (50, 50)):
            with self.subTest(size=(w, h)):
                seg = sg.segment(synth.Canvas(w, h).image())
                self.assertEqual(seg.elements, [])
                self.assertEqual(seg.guess_kind(), "unknown")

    def test_solid_and_all_foreground(self):
        c = synth.Canvas(30, 30, bg=synth.BLUE)
        sg.segment(c.image())
        c.rect(5, 5, 25, 25, synth.RED)
        sg.segment(c.image())

    def test_random_noise_never_raises(self):
        rng = random.Random(11)
        for _ in range(40):
            w, h = rng.randint(1, 24), rng.randint(1, 24)
            img = Image(w, h, bytes(rng.randrange(256) for _ in range(3 * w * h)))
            sg.segment(img)

    def test_few_colors_random_blocks_never_raises(self):
        rng = random.Random(5)
        palette = [(255, 255, 255), (0, 0, 0), (225, 40, 45), (60, 85, 165), (190, 190, 190), (245, 235, 10)]
        for _ in range(40):
            c = synth.Canvas(rng.randint(8, 60), rng.randint(8, 60))
            for _ in range(rng.randint(0, 12)):
                x, y = rng.randrange(c.w), rng.randrange(c.h)
                c.rect(x, y, x + rng.randint(0, 20), y + rng.randint(0, 20), rng.choice(palette))
            sg.segment(c.image())

    def test_deterministic(self):
        img, _ = synth.wafer_map()
        a, b = sg.segment(img), sg.segment(img)
        key = lambda s: [(e.kind, e.cluster, e.bbox, e.area, e.count) for e in s.elements]   # noqa: E731
        self.assertEqual(key(a), key(b))
        self.assertEqual((a.ring.cx, a.ring.notch), (b.ring.cx, b.ring.notch))

    def test_pixels_stay_inside_the_picture(self):
        img, _ = synth.control_chart()
        seg = sg.segment(img)
        for e in seg.elements:
            self.assertTrue(all(0 <= i < img.width * img.height for i in e.pixels))
            self.assertTrue(0 <= e.bbox[0] <= e.bbox[2] < img.width and 0 <= e.bbox[1] <= e.bbox[3] < img.height)


if __name__ == "__main__":
    unittest.main()
