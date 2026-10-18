# -*- coding: utf-8 -*-
"""합격 기준 AC0–AC12 (설계서 docs/plans/ascii-1-design.md › 14-15) 를 CI 가 어느 시험으로 지키는지의 장부(MAP)와, 장부를 만들며 찾은
빈자리를 메우는 시험. 숫자는 설계서 그대로다 — 시험을 통과시키려고 느슨하게 하지 않는다 (D-07).

  MAP 시험이 장부의 시험 이름이 실제로 있는지 지킨다 (이름을 바꾸거나 지우면 여기서 실패한다).
  CI 가 못 지키는 것(사용자 원본 두 장의 숫자 · 4000×4000 최악 시간 · 부드럽게 키운 실제 그림)은 로컬에서 본다:
    python tools/measure_hard.py --real <웨이퍼.png> <관리도.png>     # AC0 숫자를 판정하고 어긋나면 종료 코드 1 (그림은 저장소에 없다 — W-12)
  JPEG 기준 디코더 대조(AC11)의 기준값 다시 뜨기:  python tests/test_ac.py --write-jpeg-ref   (Pillow 가 있을 때만 · 개발 중에만)
"""
import importlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
import zlib
from contextlib import redirect_stdout
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import ascii1_png as ap  # noqa: E402
import ascii1_render as rd  # noqa: E402
import ascii1_seg as sg  # noqa: E402
import jpegenc as je  # noqa: E402
import shared  # noqa: E402     # 시험 파일끼리 나눠 쓰는 읽기 전용 캐시
import synth  # noqa: E402
from shared import case, mh, seg_of  # noqa: E402
from test_jpeg import mad, scene  # noqa: E402
from test_seg import found, grid_canvas  # noqa: E402
from test_trend import COL, kinds, red, y_at  # noqa: E402

GOLD = os.path.join(HERE, "golden", "jpeg_ref")

# AC → 지키는 시험 (파일 › 클래스.시험). 설계서 14-15 의 표를 시험 이름으로 옮긴 것이다
MAP = {
    "AC0": [("test_render", "Golden.test_chart"), ("test_render", "Golden.test_wafer"), ("test_render", "Golden.test_wafer_narrow"),
            ("test_seg_equiv", "SameAsBefore.test_segment_unchanged"), ("test_grid_render", "WithoutGrid.test_golden_with_every_mode"),
            ("test_density", "Unchanged.test_golden_pictures_stay_sparse"), ("test_hollow", "TextGate.test_control_chart_colored_labels_stay"),
            ("test_ac", "RealJudge.test_original_numbers_pass"), ("test_ac", "RealJudge.test_each_number_is_checked"),
            ("test_ac", "ThresholdGaps.test_rounded_square_frame_is_not_a_ring")],
    "AC1": [("test_hard", "GridAC.test_ac1_every_grid_line_found"), ("test_hard", "GridAC.test_ac1_grid_lines_are_not_lines"),
            ("test_hard", "GridAC.test_ac1_no_grid_where_there_is_none"), ("test_seg", "GridLayer.test_control_and_wafer_pictures_have_no_grid"),
            ("test_ac", "ThresholdGaps.test_grid_gap_tolerance"), ("test_ac", "ThresholdGaps.test_thickness_tolerance_of_a_grid_line")],
    "AC2": [("test_hard", "GridAC.test_ac2_grid_cells_do_not_go_to_data"), ("test_hard", "GridAC.test_ac2_no_data_element_on_the_grid"),
            ("test_seg", "GridLayer.test_crossing_marker_cells_stay_data")],
    "AC3": [("test_hollow", "SparseCountAC3.test_sparse_counts_within_10_percent"), ("test_density", "SparseHard.test_ac3_sparse_counts_within_10_percent"),
            ("test_ac", "SparseOnGrid.test_ac3_b0_within_10_percent")],
    "AC4": [("test_density", "DenseHard.test_ac4_range_holds_truth_and_middle_within_25_percent"),
            ("test_density", "DenseHard.test_ac4_every_counted_variant_range_holds_truth"), ("test_ac", "DenseThroughJpeg.test_ac4_range_and_middle")],
    "AC5": [("test_density", "SizeInvariance.test_mini_both_zooms"), ("test_density", "SizeInvariance.test_hard_dense_smooth_zoom"),
            ("test_density", "SizeInvariance.test_sparse_nearest_zoom"), ("test_ac", "SizeInvarianceZ.test_nearest_zoom_within_15_percent"),
            ("test_ac", "SizeInvarianceZ.test_smooth_zoom_within_15_percent")],
    "AC6": [("test_density", "DenseHard.test_ac6_density_correlation"), ("test_grid_render", "AC6Render.test_dense_variants")],
    "AC7": [("test_hollow", "MarkerTextAC7.test_markers_in_box_are_not_text"), ("test_hollow", "TextGate.test_control_chart_colored_labels_stay")],
    "AC8": [("test_trend", "TrendHard.test_one_trend_no_red_dots_or_text"), ("test_trend", "TrendHard.test_cover_at_least_90"),
            ("test_trend", "TrendHard.test_path_within_one_cell"), ("test_trend", "LegendSwatch.test_swatch_is_text_not_dots"),
            ("test_ac", "TrendWidths.test_widths_and_dashes")],
    "AC9": [("test_density", "DenseHard.test_ac9_two_series_each")],
    "AC10": [("test_seg_equiv", "Speed.test_dense_rings_within_budget"), ("test_ac", "Budget.test_real_size_time"),
             ("test_ac", "Budget.test_double_size_time"), ("test_ac", "Budget.test_memory")],
    "AC11": [("test_jpeg", "Guarded.test_corrupt_corpus"), ("test_jpeg", "Guarded.test_corpus_messages"),
             ("test_jpeg", "Guarded.test_size_limit_before_decoding"), ("test_jpeg", "Guarded.test_limit_edge_is_allowed_in_the_header"),
             ("test_ac", "JpegAC11.test_matches_reference_decoder"), ("test_ac", "JpegAC11.test_real_size_decode_time"),
             ("test_ac", "JpegAC11.test_command_refuses_with_exit_code_1")],
    "AC12": [("test_grid_render", "EveryOutput.test_ascii_width_and_determinism"), ("test_grid_render", "EveryOutput.test_fresh_segmentation_gives_the_same_bytes"),
             ("test_grid_render", "TrendOverDensity.test_ac12_column_mass_centre_follows_the_trend"),
             ("test_density", "Render.test_field_drawn_with_point_ladder"), ("test_ac", "EveryVariant.test_ascii_width_and_same_bytes")],
}


class Map(unittest.TestCase):
    def test_every_ac_has_tests_and_they_exist(self):
        self.assertEqual(sorted(MAP, key=lambda k: int(k[2:])), ["AC%d" % n for n in range(13)])
        for ac, items in MAP.items():
            self.assertTrue(items, ac + " 을 지키는 시험이 없다")
            for mod, dotted in items:
                with self.subTest(ac=ac, test=mod + "." + dotted):
                    cls_name, meth = dotted.split(".")
                    obj = getattr(importlib.import_module(mod), cls_name, None)
                    self.assertIsNotNone(obj, "%s 에 %s 가 없다" % (mod, cls_name))
                    self.assertTrue(callable(getattr(obj, meth, None)), "%s.%s 에 %s 가 없다" % (mod, cls_name, meth))


# ─────────────────────────────────────────────────────────────── AC0: 사용자 원본 두 장의 판정 (로컬 확인 도구의 판정식)

WAFER = dict(kind="wafer", dots={"파랑": 165, "주황": 26, "회색": 17}, texts={}, colored_text=0, hline=0, vline=0, curve=0, field=0,
             reason="", closed=100.0, notch=87.8)
CHART = dict(kind="chart", dots={"파랑": 20}, texts={"노랑": 6, "빨강": 5, "파랑": 7, "회색": 46}, colored_text=18, hline=7, vline=2,
             curve=3, field=0, reason="", closed=None, notch=None)


class RealJudge(unittest.TestCase):
    """tools/measure_hard.py --real 의 판정식: 사용자 원본의 숫자(설계서 AC0)에서 하나라도 벗어나면 어긋남. 그림이 없는 CI 는 식만 지킨다"""

    def bad(self, facts):
        return [what for what, ok, _ in mh.judge_real(facts) if not ok]

    def test_original_numbers_pass(self):
        for facts in (WAFER, CHART):
            with self.subTest(kind=facts["kind"]):
                verdict = mh.judge_real(facts)
                self.assertGreaterEqual(len(verdict), 7)
                self.assertEqual(self.bad(facts), [])

    def test_each_number_is_checked(self):
        wafer = [({"dots": dict(WAFER["dots"], 파랑=164)}, "점 파랑"), ({"dots": dict(WAFER["dots"], 파랑=166)}, "점 파랑"),
                 ({"dots": dict(WAFER["dots"], 주황=25)}, "점 주황"), ({"dots": dict(WAFER["dots"], 회색=18)}, "점 회색"),
                 ({"dots": dict(WAFER["dots"], 노랑=1)}, "점 군집 수"), ({"closed": 99.0}, "링 닫힘%"), ({"closed": None}, "링 닫힘%"),
                 ({"notch": 91.5}, "노치°"), ({"notch": 84.0}, "노치°"), ({"notch": None}, "노치°"), ({"field": 1}, "빽빽한 군집"),
                 ({"reason": "사진 같은 그림"}, "분석")]
        chart = [({"dots": {"파랑": 19}}, "마커 파랑"), ({"dots": {"파랑": 21}}, "마커 파랑"), ({"dots": {}}, "마커 파랑"), ({"hline": 6}, "가로선"),
                 ({"hline": 8}, "가로선"), ({"vline": 3}, "세로선"), ({"curve": 2}, "곡선"), ({"curve": 4}, "곡선"),
                 ({"texts": {"회색": 61}}, "글자"), ({"texts": {"회색": 67}}, "글자"), ({"colored_text": 17}, "색 있는 글자"),
                 ({"colored_text": 19}, "색 있는 글자"), ({"field": 2}, "빽빽한 군집")]
        for base, changes in ((WAFER, wafer), (CHART, chart)):
            for change, what in changes:
                with self.subTest(kind=base["kind"], change=str(change)):
                    self.assertEqual(self.bad(dict(base, **change)), [what])
        # 허용폭 안쪽은 맞음: 노치 ±3° · 글자 ±2
        self.assertEqual(self.bad(dict(WAFER, notch=90.0)), [])
        self.assertEqual(self.bad(dict(WAFER, notch=85.0)), [])
        for n in (62, 63, 65, 66):
            self.assertEqual(self.bad(dict(CHART, texts={"회색": n})), [], n)

    def test_other_pictures_have_nothing_to_compare(self):
        self.assertEqual([w for w, ok, _ in mh.judge_real(dict(WAFER, kind="other")) if w != "분석"], [])

    def test_main_exit_code_follows_the_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "합성 웨이퍼.png")
            img, _ = synth.wafer_map(plus=3)
            import pngenc as pe
            rows = [[tuple(img.rgb[3 * (y * img.width + x):3 * (y * img.width + x) + 3]) for x in range(img.width)] for y in range(img.height)]
            with open(path, "wb") as f:
                f.write(pe.encode(img.width, img.height, 2, 8, rows, filters=(0,)))
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(mh.main(["--real", path]), 1, "합성 웨이퍼는 사용자 원본의 숫자와 다르다")
            self.assertIn("어긋남", out.getvalue())
            self.assertTrue(out.getvalue().splitlines()[-1].startswith("결과: 기준과 어긋남"))
            f = mh.real_facts(sg.segment(img))
            same = {"dots": f["dots"], "closed": f["closed"], "notch": f["notch"], "notch_tol": 3.0}
            out = io.StringIO()
            with mock.patch.dict(mh.REAL_WAFER, same), redirect_stdout(out):
                self.assertEqual(mh.main(["--real", path]), 0, out.getvalue())
            self.assertTrue(out.getvalue().rstrip().endswith("결과: 측정 끝"))
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(mh.main(["--real", os.path.join(tmp, "없는 그림.png")]), 1)


# ─────────────────────────────────────────────────────────────── AC3: 격자 위의 드문 표식

class SparseOnGrid(unittest.TestCase):
    def test_ac3_b0_within_10_percent(self):
        """AC3 의 B0 (설계서: T4 가 건다) — 격자가 있어도 드문 표식 60 개는 ±10%"""
        c, seg = case("B0"), seg_of("B0")
        est = seg.dots([k.index for k in seg.clusters if k.name == "파랑"][0])
        self.assertLessEqual(abs(est - c.n), 0.10 * c.n, "추정 %d · 정답 %d" % (est, c.n))
        self.assertEqual(seg.of("field"), [])


# ─────────────────────────────────────────────────────────────── 문턱 변이로 드러난 빈자리 (T11 변이 시험)

def rounded_square(side, corner, t=3, n_dots=30):
    """한 변 side · 모서리 반지름 corner 의 회색 둥근 정사각 틀과 안쪽의 파랑 점 n_dots 개 (300×300). corner = side/2 면 원"""
    import random
    from math import hypot
    size = 300
    c = synth.Canvas(size, size)
    x0 = y0 = (size - side) // 2
    x1 = y1 = x0 + side
    for y in range(y0 - 1, y1 + 2):
        for x in range(x0 - 1, x1 + 2):
            cx, cy = min(max(x, x0 + corner), x1 - corner), min(max(y, y0 + corner), y1 - corner)
            if abs(hypot(x - cx, y - cy) - corner) <= t / 2 and (x <= x0 + corner or x >= x1 - corner or y <= y0 + corner or y >= y1 - corner):
                c.set(x, y, (60, 60, 60))
    rng = random.Random(1)
    for _ in range(n_dots):
        x, y = rng.randint(x0 + 30, x1 - 30), rng.randint(y0 + 30, y1 - 30)
        c.rect(x, y, x + 2, y + 2, synth.SERIES)
    return c.image()


class ThresholdGaps(unittest.TestCase):
    """문턱을 일부러 옮겨 보니(변이 시험) 기존 시험이 놓친 것들 — 양쪽 반례를 둔다"""

    def test_grid_gap_tolerance(self):
        """GRID_GAP_TOL 0.15: 간격의 중앙값이 30 일 때 한 간격이 34 (+13%) 면 줄이 흔들려도 격자, 37 (+23%) 이면 격자가 아니다.
        (test_seg 의 반례는 1.33 배라서 문턱을 0.30 으로 늦춰도 그대로 걸러졌다)"""
        self.assertEqual(found(grid_canvas((), (20, 50, 80, 114, 144, 174), h=260)), (6, 0))
        self.assertIsNone(found(grid_canvas((), (20, 50, 80, 117, 147, 177), h=260)))
        self.assertIsNone(found(grid_canvas((), (20, 50, 80, 117, 147, 177, 207), h=260)))

    def test_thickness_tolerance_of_a_grid_line(self):
        """GRID_THICK_TOL 1: 1 px 격자 사이의 두께 3 (차 2) 연한 띠는 줄이 아니라 빠지고 격자는 그대로(7 × 9). test_seg 의 반례는 두께 4 (차 3) 라 문턱을 2 로 늦춰도 걸러졌다"""
        for y in (35, 64, 95):
            with self.subTest(y=y):
                c = grid_canvas(tuple(range(20, 290, 30)), tuple(range(20, 210, 30)))
                c.rect(0, y, 299, y + 2, (200, 225, 240))
                self.assertEqual(found(c), (7, 9))

    def test_rounded_square_frame_is_not_a_ring(self):
        """RING_COVER 0.6: 둘레 5° 칸 가운데 획이 있는 것이 모자라면(둥근 정사각 틀: 한 변 200 · 모서리 반지름 60 → 56%) 링이 아니고,
        원에 가까우면(모서리 반지름 90 → 100%) 링이다"""
        self.assertIsNone(sg.segment(rounded_square(200, 60)).ring)
        self.assertIsNone(sg.segment(rounded_square(200, 70)).ring)
        ring = sg.segment(rounded_square(200, 90)).ring
        self.assertIsNotNone(ring)
        self.assertGreaterEqual(ring.closed, 0.95)


# ─────────────────────────────────────────────────────────────── AC5: 가장 빽빽한 Z 를 2 배로

def blue_field(seg):
    ks = {k.index for k in seg.clusters if k.name == "파랑"}
    return [e for e in seg.of("field") if e.cluster in ks]


class SizeInvarianceZ(unittest.TestCase):
    """AC5: 같은 그림을 2 배로 키웠을 때 추정 개수 변화 ≤ 15%. test_density 는 I 를 부드럽게만 보므로, 가장 빽빽한 Z (2500 개 · 속 빈 원 · 번짐) 를 둘 다 본다"""

    def check(self, how):
        one = blue_field(seg_of("Z"))[0]
        seg, _, _ = shared.zoomed_seg("Z", how)
        fs = blue_field(seg)
        self.assertEqual(len(fs), 1, "2 배여도 빽빽하다")
        self.assertLessEqual(abs(fs[0].count - one.count), 0.15 * one.count, "Z %s 2 배: %d → %d" % (how, one.count, fs[0].count))
        self.assertTrue(fs[0].density.count_lo <= case("Z").n <= fs[0].density.count_hi, "2 배 그림의 범위가 정답을 품는다")

    def test_nearest_zoom_within_15_percent(self):
        self.check("near")

    # 알려진 미달: Z 를 부드럽게 2 배로 키우면 2110 → 2536 (+20.2%) 으로 AC5 의 15% 를 넘는다 (범위 1718–3238 은 정답 2500 을 품는다).
    # 시험을 느슨하게 하지 않고 미달로 남긴다 — 고치면 '예상 밖 성공' 으로 알려 주니 그때 이 표시를 지운다 (T13 보고 대상)
    @unittest.expectedFailure
    def test_smooth_zoom_within_15_percent(self):
        self.check("smooth")


# ─────────────────────────────────────────────────────────────── AC4: 빽빽한 산점 + JPEG

class DenseThroughJpeg(unittest.TestCase):
    """AC4 는 'JPEG' 도 말한다: 가장 빽빽한 Z 를 1015×901 로 키워 JPEG(q90 4:2:0) 로 부호화 → 우리 디코더 → 요소 찾기. 범위가 정답 2500 을 품고
    가운데는 ±25%, 격자 38 줄과 추세선 하나를 그대로 찾는다"""

    def test_ac4_range_and_middle(self):
        seg, _ = shared.big_seg(jpeg=True)
        fs = blue_field(seg)
        self.assertEqual(len(fs), 1)
        d = fs[0].density
        n = case("Z").n
        self.assertTrue(d.count_lo <= n <= d.count_hi, "범위 %d–%d · 정답 %d" % (d.count_lo, d.count_hi, n))
        self.assertLessEqual(abs(d.count - n), 0.25 * n, "가운데 %d" % d.count)
        self.assertIsNotNone(seg.grid)
        self.assertEqual(len(seg.grid.horizontal) + len(seg.grid.vertical), 38)
        self.assertEqual(len(seg.of("trend")), 1)


# ─────────────────────────────────────────────────────────────── AC10: 시간 · 메모리

class Budget(unittest.TestCase):
    """AC10 (Linux · Python 3.13 기준, 설계서 14-14). 그림은 가장 빽빽한 Z 를 1015×901 로 키운 것 (실제 어려운 차트와 같은 크기).
    4000×4000 · 전경 45% 최악(≤ 157 s · ≤ 778 MB)은 CI 에 넣기엔 너무 오래 걸려 로컬에서 본다 (T13)"""

    def test_real_size_time(self):
        _, took = shared.big_seg()
        self.assertLessEqual(took, 8.0, "1015×901 요소 찾기 %.1f s" % took)

    def test_double_size_time(self):
        """2 배 그림 ≤ 30 s — 2030×1802 가 아니라 Z 를 2 배로 키운 1600×1200 으로 재서 칸 수에 비례해 줄인 한도(15.7 s)를 쓴다"""
        _, took, px = shared.zoomed_seg("Z", "near")
        limit = 30.0 * px / (2 * shared.BIG_SIZE[0] * 2 * shared.BIG_SIZE[1])
        self.assertLessEqual(took, limit, "Z 2 배(%d 칸) %.1f s · 한도 %.1f s" % (px, took, limit))

    @unittest.skipUnless(sys.platform.startswith("linux"), "AC10 은 Linux 기준 (resource.ru_maxrss 는 KB) — Windows · macOS 는 CI 가 따로 본다")
    def test_memory(self):
        """1× 메모리 ≤ 100 MB — 새 프로세스가 그림을 읽어 요소 찾기를 하고 끝낸 뒤의 최대 상주 메모리(해석기와 그림 포함, 시험 쪽 그림은 안 든다)"""
        img = shared.big_picture()
        with tempfile.TemporaryDirectory() as tmp:
            raw = os.path.join(tmp, "big.rgb")
            with open(raw, "wb") as f:
                f.write(img.rgb)
            code = ("import sys, resource; sys.path.insert(0, %r)\n"
                    "import ascii1_png, ascii1_seg\n"
                    "w, h = %d, %d\n"
                    "img = ascii1_png.Image(w, h, open(%r, 'rb').read())\n"
                    "ascii1_seg.segment(img)\n"
                    "print(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)\n") % (ROOT, img.width, img.height, raw)
            p = subprocess.run([sys.executable, "-c", code], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
            self.assertEqual(p.returncode, 0, p.stderr.decode("utf-8", "replace"))
            kb = int(p.stdout.split()[-1])
        peak_mb = kb / 1024
        self.assertLessEqual(peak_mb, 100.0, "최대 상주 메모리 %.0f MB" % peak_mb)


# ─────────────────────────────────────────────────────────────── AC11: JPEG

REF_CASES = {      # 이름 → (그림 만드는 법, 품질, 표본)  — 기준 디코더(libjpeg)로 푼 값이 golden/jpeg_ref/<이름>.rgb.z
    "scene_q75_420": (lambda: scene(64, 48), 75, "420"),
    "scene_q95_444": (lambda: scene(64, 48), 95, "444"),
    "chart_q90_420": (lambda: synth.control_chart(frame=True)[0], 90, "420"),
    "wafer_q90_444": (lambda: synth.wafer_map(plus=3)[0], 90, "444"),
}


class JpegAC11(unittest.TestCase):
    def test_matches_reference_decoder(self):
        """AC11: 기준 디코더(Pillow/libjpeg — 값은 개발 중에 한 번 떠서 저장소에 둔 파일이다. CI 는 Pillow 를 쓰지 않는다)와 칸 평균 절대차 ≤ 2"""
        for name, (make, q, sub) in REF_CASES.items():
            with self.subTest(name=name):
                with open(os.path.join(GOLD, name + ".jpg"), "rb") as f:
                    data = f.read()
                with open(os.path.join(GOLD, name + ".rgb.z"), "rb") as f:
                    ref = zlib.decompress(f.read())
                self.assertEqual(data, je.jpeg_of(make(), q, sub), "저장한 JPEG 가 인코더의 지금 출력과 같아야 기준값이 유효하다")
                out = ap.decode(data)
                self.assertEqual(len(out.rgb), len(ref))
                self.assertLessEqual(mad(out.rgb, ref), 2.0)

    def test_real_size_decode_time(self):
        """1015×901 해독 ≤ 5 s"""
        img, took = shared.big_decoded()
        self.assertEqual((img.width, img.height), shared.BIG_SIZE)
        self.assertLessEqual(took, 5.0, "해독 %.1f s" % took)

    def test_command_refuses_with_exit_code_1(self):
        """지원하지 않는 JPEG(progressive · 산술 · 12 비트 · 성분 4) → '지원하지 않는' 한 줄과 종료 코드 1. 잘린 파일 · 망가진 표 · 4000 을 넘는 크기도 예외 없이 종료 코드 1"""
        corpus = je.corrupt_corpus(je.jpeg_of(scene(64, 48, seed=5), 85, "420"))
        want = {"sof2_progressive": "지원하지 않는", "sof9_arithmetic": "지원하지 않는", "precision_12": "지원하지 않는", "four_components": "지원하지 않는",
                "trunc_scan_50": "잘린 파일", "trunc_in_sof": "잘린 파일", "dht_oversubscribed": "JPEG", "sof_huge": "너무 큽니다", "sof_wide": "너무 큽니다"}
        with tempfile.TemporaryDirectory() as tmp:
            for name, word in want.items():
                with self.subTest(name=name):
                    src = os.path.join(tmp, name + ".jpg")
                    with open(src, "wb") as f:
                        f.write(corpus[name][0])
                    p = subprocess.run([sys.executable, os.path.join(ROOT, "ascii-1.py"), src, "--stdout", "--no-wait"],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
                    out = p.stdout.decode("utf-8")
                    self.assertEqual(p.returncode, 1, out)
                    self.assertEqual(p.stderr, b"", "예외 추적이 새면 안 된다")
                    fails = [l for l in out.splitlines() if l.startswith("실패")]
                    self.assertEqual(len(fails), 1, out)
                    self.assertIn(word, fails[0])
                    self.assertEqual(out.splitlines()[-1], "결과: 점검 실패")


# ─────────────────────────────────────────────────────────────── AC8: 굵기 · 점선 마디

class TrendWidths(unittest.TestCase):
    """AC8: 실선(폭 1–4) · 점선(대시 4–12 px)에서 추세선이 있는 x 범위의 열 90% 이상에 선이 있고 실제 y ±1 셀, 추세선에서 나온 점 · 글자 0.
    HARD 세트에는 폭 1·3 의 실선과 대시 10 의 점선뿐이라, 마커 300 개가 있는 A_base 에 폭과 대시를 바꿔 그린다"""

    SETTINGS = (dict(trend="solid", trendw=2), dict(trend="solid", trendw=4), dict(trend="dash", dash=(4, 3), trendw=2),
                dict(trend="dash", dash=(8, 5), trendw=1), dict(trend="dash", dash=(12, 6), trendw=4), dict(trend="dash", dash=(4, 4), trendw=4))

    def test_widths_and_dashes(self):
        for over in self.SETTINGS:
            with self.subTest(**{k: str(v) for k, v in over.items()}):
                c = synth.hard_case("A_base", **over)
                seg = sg.segment(c.image)
                r = red(seg)
                self.assertEqual(len(kinds(seg, r, "trend")), 1)
                self.assertEqual(sum(e.count for e in kinds(seg, r, "dot")), 0, "추세선에서 나온 점")
                self.assertEqual(len(kinds(seg, r, "text")), 0, "추세선에서 나온 글자")
                self.assertGreaterEqual(mh.trend_cover(seg, c), 90.0)
                e = kinds(seg, r, "trend")[0]
                ch = rd.Geometry(seg, 120).ch
                lo, hi = int(c.trend[0][0]) // COL + 1, int(c.trend[-1][0]) // COL - 1
                ok = sum(1 for col in range(lo, hi + 1) if e.path[0][0] <= col * COL + COL / 2 <= e.path[-1][0]
                         and abs(y_at(e.path, col * COL + COL / 2) - y_at(c.trend, col * COL + COL / 2)) <= ch)
                self.assertGreaterEqual(ok / (hi - lo + 1), 0.90)


# ─────────────────────────────────────────────────────────────── AC12: 모든 변형의 출력

class EveryVariant(unittest.TestCase):
    """AC12: 모든 출력은 순수 ASCII · 열 수 ≤ --width · 같은 입력이면 같은 바이트. test_grid_render 는 격자 변형만 모드 × 열 수로 보므로,
    격자 없는 HARD 변형 전부(빽빽 · 추세선 · 두 계열 · 속 빈 표식 …)를 기본 모드로 세 가지 열 수에서 본다"""

    def test_ascii_width_and_same_bytes(self):
        for name in synth.HARD:
            if name in ("B0", "C", "D", "Z"):
                continue                       # 격자 변형은 test_grid_render.EveryOutput 이 모드 × 열 수로 본다
            seg = seg_of(name)
            for width in (40, 120, 300):
                with self.subTest(name=name, width=width):
                    text = rd.render(seg, width)
                    art = text.rsplit("\n\n", 1)[0].split("\n")
                    self.assertTrue(art)
                    self.assertLessEqual(max(len(x) for x in art), width)
                    self.assertTrue(all(0x20 <= ord(ch) <= 0x7E for x in art for ch in x), "그림 부분은 순수 ASCII")
                    self.assertTrue(all(ord(ch) < 0x80 or ch == "\n" for ch in text.rsplit("\n\n", 1)[0]))
                    if width == 120:
                        self.assertEqual(text, rd.render(seg, width))

    def test_fresh_analysis_gives_the_same_bytes(self):
        """다시 분석해도 같은 바이트 — 빽빽(H) · 추세선과 두 계열(L)"""
        for name in ("H", "L"):
            with self.subTest(name=name):
                self.assertEqual(rd.render(sg.segment(case(name).image), 120), rd.render(seg_of(name), 120))


def write_jpeg_ref():
    from PIL import Image as PI
    os.makedirs(GOLD, exist_ok=True)
    for name, (make, q, sub) in REF_CASES.items():
        data = je.jpeg_of(make(), q, sub)
        ref = PI.open(io.BytesIO(data)).convert("RGB")
        got = ap.decode(data)
        print(name, ref.size, "mad(우리 디코더, libjpeg) = %.3f" % mad(got.rgb, ref.tobytes()))
        with open(os.path.join(GOLD, name + ".jpg"), "wb") as f:
            f.write(data)
        with open(os.path.join(GOLD, name + ".rgb.z"), "wb") as f:
            f.write(zlib.compress(ref.tobytes(), 9))


if __name__ == "__main__":
    if "--write-jpeg-ref" in sys.argv:
        write_jpeg_ref()
    else:
        unittest.main()
