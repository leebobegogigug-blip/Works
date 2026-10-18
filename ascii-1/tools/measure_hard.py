# -*- coding: utf-8 -*-
"""HARD 합성 세트를 지금 요소 찾기(ascii1_seg)에 돌려 변형마다 잰 값을 표로 찍는다 — 개발 도구다 (tools/ 는 RULES.md › W-02 의 실행 경로가 아니다).

  python tools/measure_hard.py                      HARD 변형 전부 (시험용 그림은 tests/synth.py 가 코드로 그린다)
  python tools/measure_hard.py A0 E0 Z              이름으로 고른 변형만
  python tools/measure_hard.py --real 그림.png ...  내 PC 의 그림도 잰다 — 웨이퍼 · 관리도 원본이면 AC0 의 숫자와 맞는지 판정까지 한다
                                                    (맞으면 종료 코드 0, 하나라도 어긋나면 1). 사용자 그림은 저장소에 넣지 않는다 (W-12)

열: 시간 · 정답 개수 · 파랑 점 추정과 오차% · 빽빽한 군집(field)의 개수 범위 · 파랑 글자 · 파랑 곡선 · 밀도 상관 R(16×8 / 60×25) ·
    추세선 덮음(%) · 빨강 점 · 빨강 글자 · 선 찾은 수(가로 · 세로선 + 격자 줄)/정답(격자가 없으면 틀 4) · 검정 · 회색 군집의 점 · 글자 · 격자 칸 누수%(색 있는 군집으로 간 비율) · 격자 위 요소 칸%.
마지막 줄은 결과: 측정 끝 (S-03).
"""
import os
import sys
import time
from collections import Counter
from math import isnan, sqrt
from typing import Dict, List, Optional, Tuple

TOOLS = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(TOOLS)
sys.path.insert(0, APP)
sys.path.insert(0, os.path.join(APP, "tests"))
import ascii1_png  # noqa: E402
import ascii1_seg as sg  # noqa: E402
import synth  # noqa: E402

DENSITY_GRIDS = ((16, 8), (60, 25))
TREND_COL = 8            # 추세선 덮음을 재는 열 너비(px)
TREND_TOL = 4            # 정답 y 와 이만큼(px) 이내면 맞게 놓인 것
# 설계서 08 의 사용자 그림 기준값 (로컬 확인용). 웨이퍼 · 관리도
BASE_WAFER = {"파랑": 165, "주황": 26, "회색": 17}
# 설계서 14-15 AC0 — 원본 두 장이 지켜야 하는 숫자 (허용폭은 거기 적힌 것: 노치 ±3° · 글자 ±2, 나머지는 정확히)
REAL_WAFER = {"dots": BASE_WAFER, "closed": 100.0, "notch": 87.8, "notch_tol": 3.0}
REAL_CHART = {"dots": {"파랑": 20}, "hline": 7, "vline": 2, "curve": 3, "text": 64, "text_tol": 2, "colored_text": 18}


def pearson(a: List[float], b: List[float]) -> float:
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    sa = sqrt(sum((x - ma) ** 2 for x in a))
    sb = sqrt(sum((y - mb) ** 2 for y in b))
    if not sa or not sb:
        return float("nan")
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb)


def named(seg, name: str) -> List[int]:
    return [c.index for c in seg.clusters if c.name == name]


def estimates(seg, case, series: List[int], gx: int, gy: int) -> List[float]:
    """그림 상자를 gx × gy 로 나눈 칸마다 점 추정 — 점은 중심이 놓인 칸에, field 는 블록 질량에 비례해 블록 중심이 놓인 칸에"""
    x0, y0, x1, y1 = case.box
    est = [0.0] * (gx * gy)

    def add(x: float, y: float, v: float) -> None:
        i = min(gx - 1, max(0, int((x - x0) / (x1 - x0) * gx)))
        j = min(gy - 1, max(0, int((y - y0) / (y1 - y0) * gy)))
        est[j * gx + i] += v

    for e in seg.elements:
        if e.kind == "dot" and e.cluster in series:
            add(e.cx, e.cy, e.count)
        elif e.kind == "field" and e.cluster in series:
            d = e.density
            total = sum(d.mass)
            for n, m in enumerate(d.mass):
                if m:
                    add(d.x0 + (n % d.cols + 0.5) * d.block, d.y0 + (n // d.cols + 0.5) * d.block, e.count * m / total)
    return est


def density(seg, case, series: List[int], gx: int, gy: int) -> float:
    """그림 상자를 gx × gy 로 나눠 정답 개수와 점 추정의 Pearson 상관"""
    return pearson([float(v) for v in case.cell_counts(gx, gy)], estimates(seg, case, series, gx, gy))


def trend_cover(seg, case) -> Optional[float]:
    """추세선이 있는 x 범위를 TREND_COL 폭 열로 나눠, 빨강 선(추세선 · 곡선 · 가로 · 세로선)이 정답 y 에서 TREND_TOL 이내에 있는 열의 %"""
    if not case.trend:
        return None
    red = set(named(seg, "빨강"))
    w = seg.width
    cols: Dict[int, List[int]] = {}
    for e in seg.elements:
        if e.cluster in red and e.kind in ("trend", "curve", "hline", "vline"):
            for p in e.pixels:
                cols.setdefault((p % w) // TREND_COL, []).append(p // w)
    xs = [p[0] for p in case.trend]
    first, last = int(min(xs)) // TREND_COL, int(max(xs)) // TREND_COL
    hit = total = 0
    for col in range(first + 1, last):                     # 양끝 열은 반쯤 걸쳐 있어 뺀다
        cx = col * TREND_COL + TREND_COL / 2
        y = min(case.trend, key=lambda p: abs(p[0] - cx))[1]
        total += 1
        if any(abs(v - y) <= TREND_TOL for v in cols.get(col, ())):
            hit += 1
    return 100.0 * hit / total if total else None


def grid_leak(case, img, bg, seg, cls_clusters=None) -> Optional[List[float]]:
    """격자 칸(데이터가 덮지 않고 남은 칸) 중 색 있는 군집으로 간 %, 그리고 점 · 글자 · 곡선 · 원 요소가 된 %.
    군집은 segment() 와 같은 classify 결과 (격자가 있으면 격자 칸을 뺀 뒤). cls_clusters 에 이미 구한 classify 결과를 넘기면 다시 안 구한다"""
    if not case.grid_cells:
        return None
    cls, clusters, _ = cls_clusters or sg.classify(img, bg)
    chroma = {c.index for c in clusters if not c.neutral}
    leak = sum(1 for i in case.grid_cells if cls[i] in chroma)
    covered = set()
    for e in seg.elements:
        if e.kind in ("dot", "text", "curve", "ring"):
            covered.update(e.pixels)
    on = sum(1 for i in case.grid_cells if i in covered)
    n = len(case.grid_cells)
    return [100.0 * leak / n, 100.0 * on / n]


def measure(case, seg=None, cls=None) -> dict:
    """변형 하나를 재서 값 사전으로 돌려준다 (표의 열과 같은 이름). seg · cls(classify 결과)에 이미 구한 것을 넘기면 다시 분석하지 않는다
    (시험이 같은 그림을 여러 번 분석하지 않으려고 — 이때 time 은 0 이고 부르는 쪽이 채운다)"""
    img = case.image
    dt = 0.0
    if seg is None:
        t = time.time()
        seg = sg.segment(img)
        dt = time.time() - t
    blue = named(seg, "파랑")
    red = set(named(seg, "빨강"))
    est = sum(seg.dots(k) for k in blue)
    fields = [e.density for e in seg.of("field") if e.cluster in blue]
    out = {
        "name": case.name, "time": dt, "n": case.n, "est": est,
        "range": (sum(d.count_lo for d in fields), sum(d.count_hi for d in fields)) if fields else None,
        "err": (100.0 * (est - case.n) / case.n) if case.n else None,
        "blue_text": sum(1 for e in seg.elements if e.kind == "text" and e.cluster in blue),
        "blue_curve": sum(1 for e in seg.elements if e.kind == "curve" and e.cluster in blue),
        "R": [density(seg, case, blue, gx, gy) if case.n else float("nan") for gx, gy in DENSITY_GRIDS],
        "trend": trend_cover(seg, case),
        "red_dot": sum(e.count for e in seg.elements if e.kind == "dot" and e.cluster in red),
        "red_text": sum(1 for e in seg.elements if e.kind == "text" and e.cluster in red),
        "neutral": [sum(e.count for e in seg.elements if e.kind == "dot" and seg.clusters[e.cluster - 1].neutral),
                    sum(1 for e in seg.elements if e.kind == "text" and seg.clusters[e.cluster - 1].neutral)],
        "lines": len(seg.of("hline")) + len(seg.of("vline"))
        + (len(seg.grid.horizontal) + len(seg.grid.vertical) if seg.grid else 0),   # 격자 줄은 seg.grid 에 있다
        "lines_true": case.grid_lines or 4,                     # 격자가 없는 변형은 1 픽셀 틀 네 줄
        "leak": grid_leak(case, img, seg.bg, seg, cls),
        "clusters": ",".join(c.name for c in seg.clusters),
    }
    if case.series_color and case.pts2:
        orange = named(seg, "주황")
        out["orange_est"] = sum(seg.dots(k) for k in orange)
        out["n2"] = len(case.pts2)
    return out


def fmt(v, spec: str, none: str = "-") -> str:
    if v is None or (isinstance(v, float) and isnan(v)):
        return none
    return format(v, spec)


HEAD = ("이름", "시간", "정답", "추정", "오차%", "범위", "파랑글자", "파랑곡선", "R16x8", "R60x25", "추세덮음%", "빨강점", "빨강글자",
        "선수/정답", "중립점", "중립글자", "격자누수%", "격자위요소%", "군집")


def row(m: dict) -> List[str]:
    leak = m["leak"]
    return [m["name"], fmt(m["time"], ".1f") + "s", str(m["n"]), str(m["est"]), fmt(m["err"], "+.0f"),
            "%d-%d" % m["range"] if m["range"] else "-",
            str(m["blue_text"]), str(m["blue_curve"]), fmt(m["R"][0], ".2f"), fmt(m["R"][1], ".2f"),
            fmt(m["trend"], ".0f"), str(m["red_dot"]), str(m["red_text"]),
            "%d/%d" % (m["lines"], m["lines_true"]), str(m["neutral"][0]), str(m["neutral"][1]),
            fmt(leak[0], ".0f") if leak else "-", fmt(leak[1], ".0f") if leak else "-", m["clusters"]]


def table(rows: List[List[str]]) -> str:
    cells = [list(HEAD)] + rows
    widths = [max(len(r[k]) for r in cells) for k in range(len(HEAD))]
    return "\n".join(" | ".join(v.ljust(widths[k]) if k in (0, len(HEAD) - 1) else v.rjust(widths[k]) for k, v in enumerate(r)).rstrip()
                     for r in cells)


def real_facts(seg) -> dict:
    """사용자 그림 하나의 분석 결과에서 AC0 이 보는 숫자만 뽑는다 (판정은 judge_real)"""
    names = {c.index: c.name for c in seg.clusters}
    neutral = {c.index for c in seg.clusters if c.neutral}
    dots, texts = Counter(), Counter()
    for e in seg.elements:
        if e.kind in ("dot", "field"):
            dots[names[e.cluster]] += e.count
        elif e.kind == "text":
            texts[names[e.cluster]] += 1
    return {
        "kind": seg.guess_kind(), "dots": dict(dots), "texts": dict(texts),
        "colored_text": sum(1 for e in seg.elements if e.kind == "text" and e.cluster not in neutral),
        "hline": len(seg.of("hline")), "vline": len(seg.of("vline")), "curve": len(seg.of("curve")),
        "field": len(seg.of("field")), "reason": seg.reason,
        "closed": None if seg.ring is None else 100.0 * seg.ring.closed,
        "notch": None if seg.ring is None else seg.ring.notch,
    }


def judge_real(f: dict) -> List[tuple]:
    """AC0 의 숫자와 견준다 → [(항목, 맞는가, '잰 값 (기준)')]. 웨이퍼 · 관리도가 아닌 그림은 []"""
    out: List[tuple] = []

    def check(what: str, ok: bool, got, want) -> None:
        out.append((what, bool(ok), "%s (기준 %s)" % (got, want)))

    check("분석", not f["reason"], "예" if not f["reason"] else f["reason"], "예")
    if f["kind"] == "wafer":
        for name, want in REAL_WAFER["dots"].items():
            got = f["dots"].get(name, 0)
            check("점 " + name, got == want, got, want)
        check("점 군집 수", set(f["dots"]) == set(REAL_WAFER["dots"]), len(f["dots"]), len(REAL_WAFER["dots"]))
        check("링 닫힘%", f["closed"] is not None and f["closed"] >= REAL_WAFER["closed"], fmt(f["closed"], ".0f"), "100")
        check("노치°", f["notch"] is not None and abs(f["notch"] - REAL_WAFER["notch"]) <= REAL_WAFER["notch_tol"],
              fmt(f["notch"], ".1f"), "%.1f±%.0f" % (REAL_WAFER["notch"], REAL_WAFER["notch_tol"]))
        check("빽빽한 군집", f["field"] == 0, f["field"], 0)
    elif f["kind"] == "chart":
        for name, want in REAL_CHART["dots"].items():
            got = f["dots"].get(name, 0)
            check("마커 " + name, got == want, got, want)
        for key, label in (("hline", "가로선"), ("vline", "세로선"), ("curve", "곡선")):
            check(label, f[key] == REAL_CHART[key], f[key], REAL_CHART[key])
        n = sum(f["texts"].values())
        check("글자", abs(n - REAL_CHART["text"]) <= REAL_CHART["text_tol"], n, "%d±%d" % (REAL_CHART["text"], REAL_CHART["text_tol"]))
        check("색 있는 글자", f["colored_text"] == REAL_CHART["colored_text"], f["colored_text"], REAL_CHART["colored_text"])
        check("빽빽한 군집", f["field"] == 0, f["field"], 0)
    return out


def real(path: str) -> Tuple[List[str], int]:
    """내 PC 의 그림 하나를 재서 설계서 08 · AC0 의 기준값과 견준다 → (찍을 줄, 어긋난 항목 수)"""
    img = ascii1_png.load(path)
    t = time.time()
    seg = sg.segment(img)
    dt = time.time() - t
    names = {c.index: c.name for c in seg.clusters}
    lines = ["%s: %dx%d %.2fs 분석=%s 종류=%s" % (os.path.basename(path), img.width, img.height, dt,
                                               "예" if not seg.reason else "아니오(" + seg.reason + ")", seg.guess_kind())]
    f = real_facts(seg)
    lines.append("  점 " + (" ".join("%s %d" % kv for kv in sorted(f["dots"].items())) or "-")
                 + " · 글자 %d (%s) · 가로선 %d · 세로선 %d · 곡선 %d"
                 % (sum(f["texts"].values()), " ".join("%s %d" % kv for kv in sorted(f["texts"].items())) or "-",
                    f["hline"], f["vline"], f["curve"]))
    for e in seg.of("field"):
        d = e.density
        lines.append("  빽빽함 %s: 가운데 %d · 범위 %d–%d · 낱점 면적 %.1f · 지름 %.1f · 칸 %d px"
                     % (names[e.cluster], d.count, d.count_lo, d.count_hi, d.unit, d.diameter, d.cell))
    verdict = judge_real(f)
    bad = [v for v in verdict if not v[1]]
    if verdict:
        lines.append("  AC0 판정: " + ("모두 맞음" if not bad else "어긋남 %d" % len(bad)))
        for what, ok, detail in verdict:
            lines.append("    %s %s: %s" % ("맞음  " if ok else "어긋남", what, detail))
    else:
        lines.append("  AC0 판정: 웨이퍼 · 관리도가 아니라 견줄 기준이 없다")
    return lines, len(bad)


def main(argv: List[str]) -> int:
    args = list(argv)
    paths: List[str] = []
    if "--real" in args:
        k = args.index("--real")
        paths, args = args[k + 1:], args[:k]
    unknown = [a for a in args if a not in synth.HARD_SPECS]
    if unknown:
        print("모르는 변형: %s (있는 것: %s)" % (", ".join(unknown), " ".join(synth.HARD)), file=sys.stderr)
        return 2
    names = args or ([] if paths else list(synth.HARD))
    if names:
        print(table([row(measure(synth.hard_case(n))) for n in names]))
    bad = 0
    for p in paths:
        try:
            lines, n = real(p)
            print("\n".join(lines))
            bad += n
        except (OSError, ValueError) as e:
            print("%s: 읽지 못했습니다 (%s)" % (os.path.basename(p), e))
            bad += 1
    print("결과: 측정 끝" if not bad else "결과: 기준과 어긋남 %d" % bad)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
