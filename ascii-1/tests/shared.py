# -*- coding: utf-8 -*-
"""시험 파일끼리 나눠 쓰는 HARD 변형 · 요소 찾기 결과 — 같은 그림을 시험마다 다시 그리고 다시 분석하지 않으려는 캐시.

규칙: 여기서 받은 것(HardCase · Image · Segmentation · 측정 사전)은 **읽기만 한다** — 고치면 다른 시험이 틀어진다.
결과를 바꿔 보는 시험(일부러 깨기 · 다른 문턱 · 다른 크기)은 sg.segment() 를 직접 불러 새로 만든다.
unittest discover 는 한 프로세스에서 모든 파일을 돌리므로 캐시는 파일 사이에서 이어진다. 파일 하나만 돌려도 맞게 동작한다.
"""
import importlib.util
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import ascii1_seg as sg  # noqa: E402
import synth  # noqa: E402

_spec = importlib.util.spec_from_file_location("measure_hard", os.path.join(ROOT, "tools", "measure_hard.py"))
mh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mh)

_CASES = {}
_SEGS = {}
_STATS = {}
_CLS = {}
_MEASURED = {}
SEG_SECONDS = {}          # 변형 → 처음 segment() 에 걸린 시간 (AC10 시간 시험이 같은 값을 쓴다)


def case(name):
    """HARD 변형의 정답 (synth.HardCase) — 읽기 전용"""
    if name not in _CASES:
        _CASES[name] = synth.hard_case(name)
    return _CASES[name]


def seg_of(name):
    """변형 그림의 segment() 결과 — 읽기 전용. 처음 부를 때 density_stats 를 엿들어 군집별 통계도 모은다 (stats_of)"""
    if name not in _SEGS:
        img = case(name).image
        seen = []
        real = sg.density_stats

        def spy(*args):
            st = real(*args)
            seen.append(st)
            return st

        sg.density_stats = spy
        try:
            t = time.perf_counter()
            seg = sg.segment(img)
            SEG_SECONDS[name] = time.perf_counter() - t
        finally:
            sg.density_stats = real
        _SEGS[name], _STATS[name] = seg, seen
    return _SEGS[name]


def stats_of(name):
    seg_of(name)
    return _STATS[name]


def classified(name):
    """sg.classify(그림, 바탕) — 읽기 전용"""
    if name not in _CLS:
        seg = seg_of(name)
        _CLS[name] = sg.classify(case(name).image, seg.bg)
    return _CLS[name]


def measured(name):
    """tools/measure_hard.measure() 의 결과 사전 — 읽기 전용 (시간 열은 처음 segment() 의 시간)"""
    if name not in _MEASURED:
        seg = seg_of(name)
        m = mh.measure(case(name), seg=seg, cls=classified(name))
        m["time"] = SEG_SECONDS[name]
        _MEASURED[name] = m
    return _MEASURED[name]


# ── AC10 · AC11 의 '실제 크기' 그림: 1015×901 (사용자의 어려운 차트와 같은 크기) ───────────────────────────
BIG_SIZE = (1015, 901)
_BIG = {}


def resample(img, w, h):
    """가장 가까운 칸으로 w×h 로 다시 뽑는다 (크기만 바꾸는 시험용 — 번짐 없음)"""
    xs = [min(img.width - 1, x * img.width // w) for x in range(w)]
    rows = []
    for y in range(h):
        base = min(img.height - 1, y * img.height // h) * img.width * 3
        rows.append(b"".join(img.rgb[base + 3 * sx:base + 3 * sx + 3] for sx in xs))
    return synth.Image(w, h, b"".join(rows))


def big_picture():
    """가장 빽빽한 변형 Z(2500 개 · 속 빈 원 · 격자 · 점선 추세선 · JPEG 번짐)를 1015×901 로 키운 그림 — 읽기 전용"""
    if "img" not in _BIG:
        _BIG["img"] = resample(case("Z").image, *BIG_SIZE)
    return _BIG["img"]


def big_jpeg():
    """big_picture() 를 우리 인코더로 JPEG(q90 · 4:2:0) 로 만든 바이트 — 인코드 4–5 s 라 한 번만"""
    if "jpeg" not in _BIG:
        import jpegenc
        _BIG["jpeg"] = jpegenc.jpeg_of(big_picture(), 90, "420")
    return _BIG["jpeg"]


_ZOOM = {}


def zoomed_seg(name, how):
    """HARD 변형 name 을 2 배로(how = 'near' 가장 가까운 칸 · 'smooth' 부드럽게) 키운 그림의 (분석 결과, 걸린 초) — 읽기 전용"""
    if (name, how) not in _ZOOM:
        img = (synth.zoom if how == "near" else synth.zoom_smooth)(case(name).image, 2)
        t = time.perf_counter()
        seg = sg.segment(img)
        _ZOOM[(name, how)] = (seg, time.perf_counter() - t, img.width * img.height)
    return _ZOOM[(name, how)]


def big_decoded():
    """big_jpeg() 를 우리 디코더로 푼 (그림, 걸린 초) — 읽기 전용"""
    if "dec" not in _BIG:
        import ascii1_png
        data = big_jpeg()
        t = time.perf_counter()
        img = ascii1_png.decode(data)
        _BIG["dec"] = (img, time.perf_counter() - t)
    return _BIG["dec"]


def big_seg(jpeg=False):
    """1015×901 그림(jpeg=True 면 JPEG 를 풀어 낸 것)의 (분석 결과, 걸린 초) — 읽기 전용"""
    key = "seg_jpeg" if jpeg else "seg"
    if key not in _BIG:
        img = big_decoded()[0] if jpeg else big_picture()
        t = time.perf_counter()
        seg = sg.segment(img)
        _BIG[key] = (seg, time.perf_counter() - t)
    return _BIG[key]
