# -*- coding: utf-8 -*-
"""ascii1_seg 를 빠르게 고쳐도 결과는 그대로인가 — segment() 가 내는 모든 것(군집 · 요소의 종류 · 칸 목록과 그 순서 ·
중심 · 개수 · 낱점 면적 · 링)을 해시로 줄여, 마커 분리를 빠르게 고치기 전의 코드에서 뜬 스냅숏(SNAPSHOT)과 비교한다.
스냅숏을 다시 뜨는 것은 결과를 일부러 바꿀 때뿐이다: python tests/test_seg_equiv.py --write (나온 줄을 SNAPSHOT 에 붙인다).
그림은 전부 코드로 만든 것 (W-12)."""
import hashlib
import os
import random
import sys
import time
import unittest
from math import hypot

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import ascii1_seg as sg  # noqa: E402
import synth  # noqa: E402


def _f(v):
    return None if v is None else "%.6f" % v


def fingerprint(seg) -> str:
    """segment() 결과 전부를 sha256 앞 16자로. 칸 목록은 순서까지 넣는다 (렌더가 그 순서로 칸을 칠한다)"""
    h = hashlib.sha256()

    def put(*vals) -> None:
        h.update(repr(vals).encode("utf-8"))

    put(seg.width, seg.height, seg.bg, seg.reason, _f(seg.line_thickness))
    for c in seg.clusters:
        put(c.index, c.name, c.rgb, c.pixels, c.neutral)
    for k in sorted(seg.unit):
        put(k, _f(seg.unit[k]))
    r = seg.ring
    put(None if r is None else (_f(r.cx), _f(r.cy), _f(r.r), _f(r.closed), _f(r.notch)))
    for e in seg.elements:
        put(e.kind, e.cluster, e.bbox, e.area, _f(e.cx), _f(e.cy), e.count, _f(e.thickness))
        h.update(",".join(map(str, e.pixels)).encode("ascii"))
    return h.hexdigest()[:16]


def summary(seg):
    return fingerprint(seg), len(seg.elements), seg.dots()


# 이름 → 그림. 마커 분리를 타는 것(선 차트 · 큰 덩어리)과 타지 않는 것(웨이퍼)을 고루
CASES = {
    "chart": lambda: synth.control_chart()[0],
    "chart_frame": lambda: synth.control_chart(frame=True)[0],
    "chart_20": lambda: synth.control_chart(20)[0],
    "chart_soft": lambda: synth.soften(synth.control_chart()[0]),
    "chart_x2": lambda: synth.zoom(synth.control_chart()[0], 2),
    "line": lambda: synth.line_chart()[0],
    "line_soft": lambda: synth.soften(synth.line_chart()[0]),
    "line_x2": lambda: synth.zoom(synth.line_chart()[0], 2),
    "wafer": lambda: synth.wafer_map()[0],
    "wafer_soft": lambda: synth.soften(synth.wafer_map()[0]),
    "wafer_faint": lambda: synth.wafer_map(faint=True)[0],
    "wafer_plus": lambda: synth.wafer_map(plus=3)[0],
    "wafer_halo": lambda: synth.wafer_map(halo=2)[0],
    "wafer_squash": lambda: synth.wafer_map(squash=0.04)[0],
    "wafer_stripe": lambda: synth.wafer_map(stripe=40, ring=False)[0],
    "wafer_tile6_x2": lambda: synth.zoom(synth.wafer_map(tile=6)[0], 2),
}
CASES.update({"hard_" + n: (lambda n=n: synth.hard_case(n).image) for n in synth.HARD})


def dense_rings():
    """속 빈 원(r 2–6) 4000 개를 HARD 상자에 — 큰 덩어리 하나에 코어가 많아 마커 분리가 무거운 그림"""
    c = synth.Canvas(*synth.HARD_SIZE)
    synth.scatter(c, synth.HARD_BOX, 4000, (2, 6), True, 1)
    return c.image()


CASES["dense_rings"] = dense_rings

# 마커 분리를 빠르게 고치기 전(0.2.0)의 코드에서 뜬 값 — (해시, 요소 수, 점 개수 합)
SNAPSHOT = {
    'chart': ('8c9e995238601789', 37, 12),
    'chart_frame': ('abef5157091ac1e7', 40, 12),
    'chart_20': ('8dc06ae6d0ca12fd', 45, 20),
    'chart_soft': ('4db7428e9f7478a1', 34, 12),
    'chart_x2': ('feba08dca8a70d6b', 37, 12),
    'line': ('cc7ed2c4f51489a7', 13, 12),
    'line_soft': ('aac9c51ff7c60b26', 13, 12),
    'line_x2': ('74ba62b4b2087de4', 13, 12),
    'wafer': ('3d66d846974600f0', 72, 86),
    'wafer_soft': ('b659ea16e2bcb415', 72, 86),
    'wafer_faint': ('f9137362ab064a65', 72, 86),
    'wafer_plus': ('f65cfea2adf5fb40', 74, 101),
    'wafer_halo': ('a754d2d459ec1852', 72, 86),
    'wafer_squash': ('0588d87e9a73b0bb', 72, 86),
    'wafer_stripe': ('769b603b631ec5e0', 72, 126),
    'wafer_tile6_x2': ('08b2bf01b7a36b93', 72, 106),
    'hard_A_base': ('f70a07fe94d43c7b', 284, 217),    # 상자 안 표식이 되풀이되는 변형은 T5(속 빈 원 · 글자 제외)가 일부러 바꾼 값
    'hard_A0': ('c54e8cd836b57f03', 64, 56),
    'hard_A1': ('27ae320eeee2762d', 263, 213),
    'hard_E0': ('8c7bdeeed66cab55', 59, 60),
    'hard_E': ('54b0bd940cc857f3', 197, 297),
    'hard_F0': ('1cdbbcee64afe60e', 61, 59),
    'hard_F1': ('839f64de1e6ea754', 63, 60),
    'hard_H': ('5839448b50e0f6c2', 754, 1091),
    'hard_I': ('b980b9a56f96b86a', 449, 891),
    'hard_B0': ('b413fa453ad72af1', 55, 59),          # B0 · C · D · Z 는 격자 층(T4)이 일부러 바꾼 값
    'hard_C': ('4c6ed1336fdc0bdd', 198, 275),
    'hard_D': ('b031f9244b9bb1bc', 273, 214),
    'hard_J': ('14a61c1f9d550d3d', 281, 220),
    'hard_J0': ('8ac089024a41e4d8', 5, 0),
    'hard_J1': ('069f3a3dfe1c244f', 5, 0),
    'hard_J2': ('8e232b56c37ca28e', 284, 220),
    'hard_K': ('ab5ddcc9b5618eca', 348, 248),
    'hard_L': ('e4ce411963b1fa0a', 437, 348),
    'hard_Z': ('aabb18dd132eacac', 623, 1260),
    'hard_G': ('88e6ae749694b1aa', 237, 298),
    'hard_A3': ('735bcbe3a0282cdd', 119, 103),
    'dense_rings': ('cf2a806f20758882', 934, 3579),
}
# 시간 예산 (Linux · Python 3.13 에서 dense_rings 의 segment: 고치기 전 10.9 s → 1.1 s). 느린 CI 를 위해 3 배 넘게 두되 고치기 전보다는 한참 아래
SEGMENT_BUDGET = 4.0

_IMAGES = {}


def image(name):
    if name not in _IMAGES:
        _IMAGES[name] = CASES[name]()
    return _IMAGES[name]


def split_markers_ref(pix, w, rc):
    """고치기 전의 split_markers 그대로 — 코어마다 덩어리의 모든 칸에 hypot (O(코어 × 칸)). 결과를 맞춰 볼 기준"""
    box = sg.bbox_of(pix, w)
    dist = sg.distance_map(pix, w, box)
    cut = int(round(rc * sg.CHAMFER))
    core = [i for i, d in dist.items() if d >= cut]
    if not core:
        return None
    marks = []
    body = set()
    for cp in sg.components_of(core, w):
        cx, cy = sum(i % w for i in cp) / len(cp), sum(i // w for i in cp) / len(cp)
        reach = max(dist[i] for i in cp) / sg.CHAMFER + 0.5
        mb = [i for i in pix if hypot(i % w - cx, i // w - cy) <= reach]
        body.update(mb)
        marks.append((cx, cy, mb, len(cp)))
    return marks, [i for i in pix if i not in body]


class SplitMarkers(unittest.TestCase):
    def assertSame(self, pix, w, rc):
        self.assertEqual(sg.split_markers(pix, w, rc), split_markers_ref(pix, w, rc))

    def test_same_as_reference_on_segment_inputs(self):
        seen = []
        real = sg.split_markers

        def spy(pix, w, rc):
            seen.append((list(pix), w, rc))
            return real(pix, w, rc)

        sg.split_markers = spy
        try:
            for name in ("chart_soft", "line_x2", "hard_A_base", "hard_H", "hard_J1"):
                sg.segment(image(name))
        finally:
            sg.split_markers = real
        self.assertGreater(len(seen), 100)
        for n, (pix, w, rc) in enumerate(seen):
            with self.subTest(call=n):
                self.assertSame(pix, w, rc)

    def test_same_as_reference_on_random_blobs(self):
        """그림 가장자리에 닿은 덩어리 · 넓은 코어 · 가는 선에 붙은 원판 — 칸 목록의 순서까지 같다"""
        rng = random.Random(5)
        for trial in range(40):
            w, h = rng.randint(20, 90), rng.randint(20, 90)
            c = synth.Canvas(w, h)
            for _ in range(rng.randint(1, 6)):
                c.disc(rng.uniform(-3, w + 3), rng.uniform(-3, h + 3), rng.uniform(1.5, 9), (0, 0, 0))
            c.line(rng.uniform(0, w), rng.uniform(0, h), rng.uniform(0, w), rng.uniform(0, h), rng.uniform(0.5, 2), (0, 0, 0))
            cells = [i for i, p in enumerate(c.px) if p == (0, 0, 0)]
            for pix in sg.components_of(cells, w):
                rng.shuffle(pix)                       # 덩어리 안의 순서가 무엇이든 같은 순서로 돌려준다
                for rc in (1.0, 1.5, 2.0, 3.3):
                    with self.subTest(trial=trial, rc=rc):
                        self.assertSame(pix, w, rc)


class SameAsBefore(unittest.TestCase):
    def test_snapshot_covers_every_case(self):
        self.assertEqual(set(SNAPSHOT), set(CASES))

    def test_segment_unchanged(self):
        for name in CASES:
            with self.subTest(name=name):
                self.assertEqual(summary(sg.segment(image(name))), SNAPSHOT[name])


class Speed(unittest.TestCase):
    def test_dense_rings_within_budget(self):
        img = image("dense_rings")
        t = time.perf_counter()
        sg.segment(img)
        took = time.perf_counter() - t
        self.assertLess(took, SEGMENT_BUDGET, "마커 분리가 다시 O(코어 × 칸) 으로 느려졌다 (%.1f s)" % took)


if __name__ == "__main__":
    if "--write" in sys.argv:
        for name in CASES:
            print("    %r: %r," % (name, summary(sg.segment(image(name)))), flush=True)
    else:
        unittest.main()
