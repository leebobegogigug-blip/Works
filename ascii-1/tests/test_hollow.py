# -*- coding: utf-8 -*-
"""속 빈 원 표식 · 색 있는 표식의 글자 오판 (설계서 14-8 · 14-9 › 낱점 면적 · 14-15 의 AC3 · AC7).
is_hollow 의 조건마다 한쪽만 어긋난 모양을 두고, 글자 후보 빼기의 문(상자 안 · 링 없음 · 색 군집 · 외톨이 5 개)마다
문이 닫혀 글자가 남는 반례를 둔다. 그림은 전부 코드로 만든 것 (W-12)."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import ascii1_seg as sg  # noqa: E402
import synth  # noqa: E402

W = 40           # 모양 시험용 작은 그림의 폭


def shape(cells):
    """(x, y) 목록 → is_hollow 에 넘길 (칸 번호, 상자). 칸은 W 폭 그림 위"""
    pix = sorted({y * W + x for x, y in cells})
    return pix, sg.bbox_of(pix, W)


def hollow(cells) -> bool:
    pix, box = shape(cells)
    return sg.is_hollow(pix, box, W)


def ring_cells(cx, cy, r, width=1.0, sx=1.0, sy=1.0):
    """synth.Canvas.ring 과 같은 고리를 가로 sx · 세로 sy 배로 늘린 타원 고리"""
    c = synth.Canvas(W, W)
    for y in range(W):
        for x in range(W):
            d = ((x - cx) / sx) ** 2 + ((y - cy) / sy) ** 2
            if (r - width) ** 2 < d <= r * r:
                c.set(x, y, (0, 0, 0))
    return [(i % W, i // W) for i, p in enumerate(c.px) if p == (0, 0, 0)]


def art(rows, ox=5, oy=5):
    """'#' 그림 → (x, y) 목록"""
    return [(x + ox, y + oy) for y, r in enumerate(rows) for x, v in enumerate(r) if v == "#"]


def outline(x0, y0, x1, y1, t=1):
    """속 빈 네모 (획 두께 t)"""
    return [(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)
            if x - x0 < t or x1 - x < t or y - y0 < t or y1 - y < t]


class IsHollow(unittest.TestCase):
    def test_rings_of_every_marker_size(self):
        for r in (3, 4, 5, 6, 8):
            with self.subTest(r=r):
                self.assertTrue(hollow(ring_cells(15, 15, r)))
        self.assertTrue(hollow(ring_cells(15, 15, 6, width=2)), "획 두께 2")
        self.assertTrue(hollow(outline(5, 5, 14, 14)), "속 빈 네모 표식도 속 빈 표식이다")

    def test_filled_disc_is_not_hollow(self):
        c = synth.Canvas(W, W)
        c.disc(15, 15, 6, (0, 0, 0))
        self.assertFalse(hollow([(i % W, i // W) for i, p in enumerate(c.px) if p == (0, 0, 0)]))

    def test_open_ring_has_no_hole(self):
        cells = [(x, y) for x, y in ring_cells(15, 15, 6) if not (x > 18 and 13 <= y <= 17)]     # 오른쪽이 뚫린 C
        self.assertFalse(hollow(cells))

    def test_square_within_20_percent(self):
        """가로 ÷ 세로 0.8–1.25 — 0.75 는 아니고 0.87 은 맞다 (양쪽으로)"""
        self.assertTrue(hollow(ring_cells(18, 18, 7, sx=0.87)))
        self.assertTrue(hollow(ring_cells(18, 18, 7, sy=0.87)))
        self.assertFalse(hollow(ring_cells(18, 18, 7, sx=0.74)))
        self.assertFalse(hollow(ring_cells(18, 18, 7, sy=0.74)))
        self.assertTrue(hollow(outline(2, 2, 11, 9)), "10 × 8 = 1.25 는 경계 안")
        self.assertFalse(hollow(outline(2, 2, 12, 9)), "11 × 8 = 1.375 는 밖")

    def test_fill_below_0_6(self):
        self.assertTrue(hollow(outline(3, 3, 8, 8)), "6 × 6 네모 테두리 채움 0.56")
        self.assertFalse(hollow(outline(3, 3, 12, 12, t=2)), "10 × 10 두께 2 채움 0.64")

    def test_short_side_at_least_5(self):
        self.assertTrue(hollow(art([".###.", "#...#", "#...#", "#...#", "#...#", ".###."])), "5 × 6 고리")
        self.assertFalse(hollow(art([".##.", "#..#", "#..#", "#..#", ".##."])), "4 × 5 고리 — 다른 조건은 다 맞는다")

    def test_hole_near_the_middle(self):
        """구멍이 상자 한쪽 구석에 있으면(무게중심이 25% 밖) 속 빈 표식이 아니다 — 9 · 6 · P 같은 글자"""
        cells = [(0, y) for y in range(12)] + [(x, 0) for x in range(12)] + [(11, y) for y in range(8)] \
            + outline(7, 7, 11, 11)
        self.assertFalse(hollow([(x + 3, y + 3) for x, y in cells]))
        centred = [(0, y) for y in range(12)] + [(x, 0) for x in range(12)] + [(11, y) for y in range(12)] \
            + [(x, 11) for x in range(12)]
        self.assertTrue(hollow([(x + 3, y + 3) for x, y in centred]))

    def test_stroke_goes_round(self):
        """구멍이 둘이고 무게중심은 가운데여도 획이 둘레를 다 돌지 않으면(대각선 끝에 달린 두 고리) 아니다"""
        cells = ring_cells(9, 9, 3.5) + ring_cells(21, 21, 3.5) + [(x, x) for x in range(11, 20)]
        pix, box = shape(cells)
        self.assertEqual(len(sg.components_of(pix, W)), 1, "한 덩어리")
        self.assertFalse(hollow(cells))
        five = art([".###.", "#...#", "#...#", "#...#", ".###."])
        pix, box = shape(five)
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        bins = {int(((sg.atan2(i // W - cy, i % W - cx) * 180 / sg.pi) % 360) // 30) for i in pix}
        self.assertEqual(len(bins), 8)
        self.assertFalse(hollow(five), "5 × 5 고리: 구멍 · 채움 · 크기는 맞지만 30° 칸 12 개 중 8 개만 덮는다")


def frame_picture(markers=(), text=(), ink=synth.SERIES, mark=synth.SERIES, ring=None, outside=()):
    """HARD 와 같은 800 × 600 · 1 픽셀 틀(그림 상자) 그림. markers 는 원판 중심 (상자 안), text 는 (글, x, y) · ink 색,
    outside 는 상자 밖에 둘 원판 중심, ring 은 (cx, cy, r) 회색 큰 원"""
    c = synth.Canvas(*synth.HARD_SIZE)
    x0, y0, x1, y1 = synth.HARD_BOX
    for x in (x0, x1):
        c.vline(x, y0, y1, 1, (40, 40, 40))
    for y in (y0, y1):
        c.hline(y, x0, x1, 1, (40, 40, 40))
    if ring:
        c.ring(ring[0], ring[1], ring[2], 1, (120, 120, 120))
    for x, y in list(markers) + list(outside):
        c.disc(x, y, 4, mark)
    for s, x, y in text:
        c.text(s, x, y, ink)
    return c.image()


def texts(seg, cluster_name, inside=None):
    box = synth.HARD_BOX
    names = {c.index: c.name for c in seg.clusters}
    out = [e for e in seg.of("text") if names[e.cluster] == cluster_name]
    if inside is not None:
        out = [e for e in out if (box[0] + 2 < e.cx < box[2] - 2 and box[1] + 2 < e.cy < box[3] - 2) == inside]
    return out


def blue_dots(seg):
    blue = [c.index for c in seg.clusters if c.name == "파랑"]
    return sum(e.count for e in seg.of("dot") if e.cluster in blue)


MARKS = [(150 + 60 * k, 150 + (k % 3) * 70) for k in range(10)]      # 상자 안 외톨이 원판 자리
LABEL = ("TEMP", 400, 400)                                           # 상자 안 글자 (4 덩어리)


class TextGate(unittest.TestCase):
    """글자 후보 빼기의 문 — 상자 · 링 없음 · 색 군집 · 상자 안 외톨이 ≥ MARKER_REPEAT"""

    def test_marker_repeat_threshold(self):
        n = sg.MARKER_REPEAT
        self.assertEqual(n, 5)
        few = sg.segment(frame_picture(MARKS[:n - 1], [LABEL]))
        self.assertEqual(len(texts(few, "파랑", inside=True)), 4, "외톨이 4 개: 문이 닫혀 글자로 남는다")
        many = sg.segment(frame_picture(MARKS[:n], [LABEL]))
        self.assertEqual(texts(many, "파랑", inside=True), [], "외톨이 5 개: 상자 안의 같은 색 덩어리는 글자 후보가 아니다")
        self.assertGreater(blue_dots(many), n, "상자 안 같은 색 주석은 점으로 센다 (알려진 한계)")

    def test_text_outside_box_stays_text(self):
        """관리도의 UCL 처럼 상자 밖에 놓인 같은 색 글자는 문이 열려도 글자다"""
        seg = sg.segment(frame_picture(MARKS, [("UCL 2.5", 300, 25), ("125", 20, 300)]))
        self.assertEqual(len(texts(seg, "파랑", inside=False)), 5 + 3, "U C L 2 5 · 1 2 5 (점 '.' 은 글자 후보보다 작다)")
        self.assertEqual(blue_dots(seg), len(MARKS))

    def test_markers_outside_box_do_not_open(self):
        outside = [(30, 80 + 40 * k) for k in range(10)]
        seg = sg.segment(frame_picture((), [LABEL], outside=outside))
        self.assertEqual(len(texts(seg, "파랑", inside=True)), 4)

    def test_neutral_markers_do_not_open(self):
        seg = sg.segment(frame_picture(MARKS, [LABEL], ink=synth.INK, mark=synth.INK))
        self.assertEqual(len(texts(seg, "검정", inside=True)), 4, "중립 군집에는 켜지 않는다")

    def test_ring_closes_the_gate(self):
        seg = sg.segment(frame_picture(MARKS, [("TEMP", 600, 470)], ring=(330, 300, 160)))
        self.assertIsNotNone(seg.ring)
        self.assertEqual(len(texts(seg, "파랑", inside=True)), 4)

    def test_no_plot_box_closes_the_gate(self):
        c = synth.Canvas(*synth.HARD_SIZE)
        for x, y in MARKS:
            c.disc(x, y, 4, synth.SERIES)
        c.text(LABEL[0], LABEL[1], LABEL[2], synth.SERIES)
        seg = sg.segment(c.image())
        self.assertIsNone(seg.plot_box)
        self.assertEqual(len(texts(seg, "파랑")), 4)

    def test_control_chart_colored_labels_stay(self):
        for frame in (False, True):
            with self.subTest(frame=frame):
                seg = sg.segment(synth.control_chart(frame=frame)[0])
                self.assertIsNotNone(seg.plot_box)
                self.assertEqual(len(texts(seg, "빨강")), 3, "UCL 세 글자")


_CASES = {}


def case(name):
    if name not in _CASES:
        c = synth.hard_case(name)
        _CASES[name] = (c, sg.segment(c.image))
    return _CASES[name]


class SparseCountAC3(unittest.TestCase):
    """AC3: 드문 표식(채운 · 속 빈) 개수 ±10%"""

    def test_sparse_counts_within_10_percent(self):
        for name in ("E0", "E", "G", "F0", "F1", "A0"):
            with self.subTest(name=name):
                self.assertSparse(name)

    def test_a3_overlapping_discs_within_10_percent(self):
        """A3 (채운 r 4 120 개) — 겹친 원판 쌍이 split_markers 로 가서 쌍마다 1 개로 세던 것(-14%). T7 부터 상자 안 표식 무리의
        곡선 아닌 덩어리는 마커 분리로 가지 않고 면적으로 센다"""
        self.assertSparse("A3")

    def assertSparse(self, name):
        c, seg = case(name)
        est = blue_dots(seg)
        self.assertLessEqual(abs(est - c.n), 0.10 * c.n, "%s 추정 %d · 정답 %d" % (name, est, c.n))

    def test_hollow_unit_is_ring_area(self):
        """속 빈 원도 낱점 면적 후보다 — E0 의 낱점 면적은 r 4 고리 하나의 칸 수"""
        c, seg = case("E0")
        blue = [k.index for k in seg.clusters if k.name == "파랑"][0]
        one = len(ring_cells(15.3, 15.6, 4))
        self.assertAlmostEqual(seg.unit[blue], one, delta=0.25 * one)


class MarkerTextAC7(unittest.TestCase):
    """AC7: 그림 상자 안의 색 있는 표식이 글자로 지워지는 것 ≤ 표식 수의 2%"""

    def test_markers_in_box_are_not_text(self):
        for name in synth.HARD:
            c, seg = case(name)
            if not c.n:
                continue
            with self.subTest(name=name):
                lost = len(texts(seg, "파랑", inside=True)) + len(texts(seg, "주황", inside=True))
                self.assertLessEqual(lost, 0.02 * (c.n + len(c.pts2)), "%s 상자 안 글자 %d" % (name, lost))


if __name__ == "__main__":
    unittest.main()
