# -*- coding: utf-8 -*-
"""ascii1_render 테스트 — 합성한 선 차트 · 웨이퍼 맵의 글자 아트: 줄 수 · 너비 · 순수 ASCII · 선이 한 줄 · 외곽이 닫힘 · 점 개수 보존.
골든 파일(tests/golden/*.txt)은 합성 그림의 정답 출력이다. 렌더링 규칙을 일부러 바꿨을 때만, 사람이 차이를 한 줄씩 보고 승인한 뒤
  ASCII1_GOLDEN_WRITE=1 python -m unittest tests.test_render                          (bash)
  $env:ASCII1_GOLDEN_WRITE=1; python -m unittest tests.test_render; $env:ASCII1_GOLDEN_WRITE=""   (PowerShell)
로 다시 쓴다. 그림은 전부 코드로 만든 것 (W-12)."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import ascii1_render as rd  # noqa: E402
import ascii1_seg as sg  # noqa: E402
import synth  # noqa: E402

GOLD = os.path.join(HERE, "golden")


def art(text):
    """범례 위의 격자 줄들 (격자 안에는 빈 줄이 이어질 수 있어 마지막 빈 줄을 경계로 본다)"""
    return text.rsplit("\n\n", 1)[0].split("\n") if "\n\n" in text else []


def legend(text):
    return text.rsplit("\n\n", 1)[-1]


def flood_reaches_center(lines):
    """격자를 한 칸 여백으로 감싸고 빈 칸(공백)을 4방향으로 채웠을 때 중심의 빈 칸에 닿는가 — 닿으면 외곽이 열린 것"""
    h, w = len(lines), max(len(x) for x in lines)
    grid = [[" "] + list(x.ljust(w)) + [" "] for x in [""] + lines + [""]]
    seen = {(0, 0)}
    stack = [(0, 0)]
    while stack:
        r, c = stack.pop()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            rr, cc = r + dr, c + dc
            if 0 <= rr < len(grid) and 0 <= cc < len(grid[0]) and (rr, cc) not in seen and grid[rr][cc] == " ":
                seen.add((rr, cc))
                stack.append((rr, cc))
    return (h // 2 + 1, w // 2 + 1) in seen


class Golden(unittest.TestCase):
    def check(self, name, text):
        path = os.path.join(GOLD, name)
        if os.environ.get("ASCII1_GOLDEN_WRITE"):
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
        with open(path, encoding="utf-8", newline="") as f:
            self.assertEqual(f.read(), text, "%s 이 골든과 다르다 — 의도한 변경이면 위 설명대로 다시 쓰고 git diff 를 본다" % name)

    def test_chart(self):
        self.check("chart_100.txt", rd.render(sg.segment(synth.control_chart()[0]), 100))

    def test_wafer(self):
        self.check("wafer_100.txt", rd.render(sg.segment(synth.wafer_map(plus=3)[0]), 100))

    def test_wafer_narrow(self):
        self.check("wafer_40.txt", rd.render(sg.segment(synth.wafer_map(plus=3)[0]), 40))


class ControlChart(unittest.TestCase):
    def setUp(self):
        self.img, self.markers = synth.control_chart()
        self.text = rd.render(sg.segment(self.img), 100)
        self.lines = art(self.text)

    def test_width_and_pure_ascii(self):
        self.assertTrue(self.lines)
        self.assertLessEqual(max(len(x) for x in self.lines), 100)
        self.assertTrue(all(0x20 <= ord(ch) <= 0x7E for x in self.lines for ch in x))
        self.assertTrue(all(x == x.rstrip() for x in self.lines), "줄 끝 공백이 없다")
        self.assertTrue(self.text.endswith("\n") and not self.text.endswith("\n\n"))

    def test_each_limit_line_is_one_row(self):
        for glyph, expect in (("=", 2), ("~", 2)):
            rows = [x for x in self.lines if x.count(glyph) >= 30]
            self.assertEqual(len(rows), expect, "'%s' 로 이어진 줄 수 (선이 두 줄로 그려지면 늘어난다)" % glyph)

    def test_one_glyph_per_marker(self):
        self.assertEqual(sum(x.count(g) for x in self.lines for g in "oO@"), self.markers)

    def test_curve_connects_the_markers(self):
        self.assertGreaterEqual(sum(x.count(g) for x in self.lines for g in "/\\"), 8)

    def test_legend(self):
        lg = legend(self.text)
        self.assertIn("o O @ 파랑 점 %d개" % self.markers, lg)
        self.assertIn("= 빨강 선", lg)
        self.assertIn("~ 노랑 선", lg)
        self.assertIn("글자", lg)
        self.assertIn("420×300 → 100열", lg)

    def test_deterministic(self):
        self.assertEqual(self.text, rd.render(sg.segment(self.img), 100))

    def test_blurred_gives_the_same_structure(self):
        lines = art(rd.render(sg.segment(synth.soften(self.img)), 100))
        self.assertEqual(sum(x.count(g) for x in lines for g in "oO@"), self.markers)
        self.assertEqual(len([x for x in lines if x.count("=") >= 30]), 2)
        self.assertEqual(len([x for x in lines if x.count("~") >= 30]), 2)

    def test_lines_stay_inside_the_frame(self):
        # 오른쪽 틀이 있고 라벨이 틀 밖 바로 옆에 있는 차트: 한계선은 틀에서 멈춘다 (번져서 라벨과 이어져도)
        for variant in (self.img, synth.soften(self.img)):
            img, _ = synth.control_chart(frame=True)
            lines = art(rd.render(sg.segment(synth.soften(img) if variant is not self.img else img), 100))
            self.assertTrue(lines[0].startswith("+") and lines[0].endswith("+"), lines[0])
            rows = [x for x in lines if x.count("=") >= 30 or x.count("~") >= 30]
            self.assertEqual(len(rows), 4)
            for x in rows:
                self.assertTrue(x.startswith("+") and x.endswith("+"), "선이 틀 밖으로 삐져나감: " + x)


class WaferMap(unittest.TestCase):
    def setUp(self):
        self.img, self.info = synth.wafer_map(plus=3)
        self.seg = sg.segment(self.img)
        self.text = rd.render(self.seg, 100)
        self.lines = art(self.text)

    def test_ring_is_closed_in_ascii(self):
        self.assertFalse(flood_reaches_center(self.lines), "글자로 그린 외곽에 틈이 있다")

    def test_ring_is_closed_at_other_widths(self):
        for width in (40, 60, 160, 300):
            with self.subTest(width=width):
                lines = art(rd.render(self.seg, width))
                self.assertFalse(flood_reaches_center(lines))
                self.assertLessEqual(max(len(x) for x in lines), width)

    def test_circle_looks_round(self):
        # 셀 세로 = 가로의 2 배 → 글자로 그린 원도 가로 : 세로 = 2 : 1 근처
        w = max(len(x) for x in self.lines)
        self.assertAlmostEqual(w / len(self.lines), 2.0, delta=0.25)

    def test_notch_is_at_the_bottom(self):
        last = self.lines[-1]
        self.assertIn("v", last)
        self.assertLess(abs(last.index("v") - len(max(self.lines, key=len)) / 2), 6, "노치는 아래 가운데")
        self.assertEqual(sum(x.count("v") for x in self.lines), 1)

    def test_dot_counts_are_conserved_in_cells(self):
        geo = rd.Geometry(self.seg, 100)
        cells = rd.allocate_dots(self.seg, geo)
        for c in self.seg.clusters:
            self.assertEqual(sum(per.get(c.index, 0) for per in cells.values()), self.seg.dots(c.index), c.name)

    def test_dense_cells_use_the_heavy_glyph(self):
        img, _ = synth.wafer_map(tile=6, plus=3)                 # 점 36 개를 18×18 px 에 빈틈없이
        text = rd.render(sg.segment(img), 40)                      # 셀이 커서 덩어리 한 셀에 여러 점이 들어간다
        self.assertIn("@", "".join(art(text)))
        self.assertNotIn("@", "".join(self.lines[:3]), "맨 위는 낱점뿐")

    def test_legend(self):
        lg = legend(self.text)
        blue = self.info["blue"] + self.info["tile"] + self.info["plus"]
        self.assertIn("o O @ 파랑 점 %d개" % blue, lg)
        self.assertIn("x X %% 주황 점 %d개" % self.info["orange"], lg)
        self.assertIn("웨이퍼 외곽", lg)
        self.assertIn("v 노치", lg)

    def test_art_only_uses_declared_glyphs(self):
        allowed = set(" .vo O@xX%*#&".replace(" ", "")) | {" "}
        self.assertTrue(set("".join(self.lines)) <= allowed | set("OX"), set("".join(self.lines)) - allowed)


class ContentWidth(unittest.TestCase):
    """열 수는 그림 폭이 아니라 그려질 내용의 폭에 걸린다 — 여백에 열을 쓰면 같은 열 수로도 해상도가 반토막 난다"""

    def test_wafer_and_chart_fill_the_requested_columns(self):
        for img in (synth.wafer_map()[0], synth.control_chart(frame=True)[0]):
            seg = sg.segment(img)
            for width in (60, 100, 200):
                got = max(len(x) for x in art(rd.render(seg, width)))
                self.assertGreaterEqual(got, 0.9 * width, "폭 %d 요청에 %d 열" % (width, got))
                self.assertLessEqual(got, width)

    def test_text_does_not_widen_the_content(self):
        seg = hand_built_with([line("hline", (50, 49, 149, 50), 100, 49.5)])
        self.assertEqual(rd.content_box(seg), (50, 49, 149, 50))
        seg.elements.append(sg.Element("text", 1, (0, 0, 199, 99), 5, [], 100, 50))
        self.assertEqual(rd.content_box(seg), (50, 49, 149, 50), "글자는 그리지 않으니 내용의 폭에 넣지 않는다")

    def test_empty_falls_back_to_the_whole_picture(self):
        self.assertEqual(rd.content_box(hand_built(200, 100)), (0, 0, 199, 99))

    def test_a_finer_width_means_a_finer_picture(self):
        seg = sg.segment(synth.wafer_map()[0])
        coarse = sum(len(x.replace(" ", "")) for x in art(rd.render(seg, 60)))
        fine = sum(len(x.replace(" ", "")) for x in art(rd.render(seg, 200)))
        self.assertGreater(fine, 2 * coarse)


class Helpers(unittest.TestCase):
    def test_ladder_follows_cell_capacity(self):
        self.assertEqual([rd.ladder(n, 2.0) for n in (1, 2, 3, 4)], [0, 1, 2, 2])
        self.assertEqual([rd.ladder(n, 20.0) for n in (1, 2, 3, 4, 5)], [0, 1, 1, 2, 2])

    def test_notch_glyph_follows_the_side(self):
        seg = sg.Segmentation(200, 200, (255, 255, 255))
        for deg, glyph in ((0, ">"), (90, "v"), (180, "<"), (270, "^"), (350, ">")):
            seg.ring = sg.Ring(100, 100, 80, 1.0, float(deg))
            self.assertEqual(rd.notch_cell(seg, rd.Geometry(seg, 100))[1], glyph, deg)

    def test_thin_keeps_one_cell_for_a_wide_horizontal_stroke(self):
        # 가로로 굵은 선이 셀 경계에 걸쳐도 한 줄만
        img = synth.Canvas(200, 60)
        img.hline(30, 10, 190, 6, synth.BLUE)
        seg = sg.segment(img.image())
        rows = [x for x in art(rd.render(seg, 100)) if x.strip()]
        self.assertLessEqual(len(rows), 1)

    def test_glyph_assignment_orders_by_dot_count(self):
        img, info = synth.wafer_map()
        seg = sg.segment(img)
        g = rd.assign_glyphs(seg)
        names = {c.name: c.index for c in seg.clusters}
        self.assertEqual(g[names["파랑"]]["point"][0], "o")
        self.assertEqual(g[names["주황"]]["point"][0], "x")

    def test_box_mode(self):
        text = rd.render(sg.segment(synth.control_chart()[0]), 100, box=True)
        a = "".join(art(text))
        self.assertTrue(set("─│┼") <= set(a))
        plain = "".join(art(rd.render(sg.segment(synth.control_chart()[0]), 100)))
        self.assertTrue(all(ord(ch) < 0x7F for ch in plain))


def hand_built(width=200, height=100):
    """요소를 손으로 놓은 Segmentation — 분석 단계가 이미 다듬은 것과 상관없이 렌더러 규칙만 시험한다"""
    seg = sg.Segmentation(width, height, (255, 255, 255))
    seg.clusters = [sg.Cluster(1, "검정", (0, 0, 0), 100, True)]
    return seg


def hand_built_with(elements):
    seg = hand_built()
    seg.elements = list(elements)
    return seg


def line(kind, box, cx, cy):
    return sg.Element(kind, 1, box, 10, [], cx, cy, 1, 2.0)


def curve(box, w):
    x0, y0, x1, y1 = box
    pix = [y * w + x for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]
    return sg.Element("curve", 1, box, len(pix), pix, (x0 + x1) / 2, (y0 + y1) / 2)


class Rules(unittest.TestCase):
    def test_horizontal_line_is_cut_at_the_frame(self):
        seg = hand_built()
        seg.elements = [line("vline", (20, 5, 21, 95), 20.5, 50), line("vline", (180, 5, 181, 95), 180.5, 50),
                        line("hline", (0, 49, 199, 50), 100, 49.5)]
        row = [x for x in art(rd.render(seg, 100)) if "-" in x][0]
        self.assertTrue(row.startswith("+") and row.endswith("+"), row)

    def test_tick_sized_curve_pieces_are_not_drawn(self):
        seg = hand_built()
        base = [line("hline", (0, 49, 199, 50), 100, 49.5)]            # 내용의 폭을 정하는 긴 선
        seg.elements = base + [curve((10, 10, 12, 11), 200)]
        plain = art(rd.render(hand_built_with(base), 100))
        self.assertEqual(art(rd.render(seg, 100)), plain, "셀 가로의 2 배도 안 되는 조각은 그려지지 않는다")
        seg.elements = base + [curve((10, 10, 40, 11), 200)]
        self.assertNotEqual(art(rd.render(seg, 100)), plain)

    def test_a_marker_on_a_line_wins_the_cell(self):
        c = synth.Canvas(300, 100)
        c.hline(50, 10, 290, 3, synth.BLACK)
        c.disc(150, 50, 5.2, synth.BLUE)
        c.disc(60, 20, 5.2, synth.BLUE)
        lines = art(rd.render(sg.segment(c.image()), 100))
        row = [x for x in lines if x.count("-") > 20][0]
        self.assertIn("o", row, "선이 지나는 줄에서도 마커가 보여야 한다")
        self.assertEqual(sum(x.count("o") for x in lines), 2)


class Edges(unittest.TestCase):
    def test_nothing_found(self):
        text = rd.render(sg.segment(synth.Canvas(60, 40).image()), 100)
        self.assertEqual(art(text), [])
        self.assertIn("그릴 것을 찾지 못했습니다", text)

    def test_tiny_picture_and_width_limits(self):
        seg = sg.segment(synth.Canvas(10, 10).image())
        rd.render(seg, 10)
        rd.render(seg, 10000)
        img, _ = synth.wafer_map()
        s = sg.segment(synth.zoom(img, 4))          # 960 px — 열 수를 마음껏 늘릴 수 있는 큰 그림
        narrow = max(len(x) for x in art(rd.render(s, 5)))
        self.assertTrue(0.6 * rd.MIN_WIDTH <= narrow <= rd.MIN_WIDTH, "너무 좁은 요청은 %d 열로 올린다 (%d)" % (rd.MIN_WIDTH, narrow))
        wide = max(len(x) for x in art(rd.render(s, 10000)))
        self.assertTrue(0.6 * rd.MAX_WIDTH <= wide <= rd.MAX_WIDTH, "너무 넓은 요청은 %d 열로 줄인다 (%d)" % (rd.MAX_WIDTH, wide))

    def test_width_never_exceeds_the_picture(self):
        c = synth.Canvas(30, 30)
        c.rect(5, 5, 7, 7, synth.BLUE)
        c.rect(20, 20, 22, 22, synth.BLUE)
        lines = art(rd.render(sg.segment(c.image()), 100))
        self.assertLessEqual(max(len(x) for x in lines), 30)

    def test_random_pictures_never_raise(self):
        import random
        rng = random.Random(8)
        palette = [(255, 255, 255), (0, 0, 0), (225, 40, 45), (60, 85, 165), (190, 190, 190), (245, 235, 10)]
        for _ in range(30):
            c = synth.Canvas(rng.randint(8, 80), rng.randint(8, 80))
            for _ in range(rng.randint(0, 14)):
                x, y = rng.randrange(c.w), rng.randrange(c.h)
                c.rect(x, y, x + rng.randint(0, 25), y + rng.randint(0, 25), rng.choice(palette))
            text = rd.render(sg.segment(c.image()), rng.choice((40, 100, 300)))
            self.assertTrue(text.endswith("\n"))


if __name__ == "__main__":
    unittest.main()
