# -*- coding: utf-8 -*-
"""ascii1_seg - 색 분류 · 연결요소 · 요소 분류. 설계서 docs/plans/ascii-1-design.md › ②③④

Image(RGB) → Segmentation: 바탕을 빼고, 색(군집)마다 따로 연결요소를 세어
가로선 · 세로선 · 원 외곽(웨이퍼) · 글자 · 점(개수 추정) · 곡선 으로 가른다. 모든 문턱은 [제안] 이라 모듈 위 상수로 둔다.
어떤 Image 를 줘도 예외 없이 끝난다 (전경이 없으면 요소가 빈 목록).
"""
import colorsys
from collections import Counter
from dataclasses import dataclass, field
from math import atan2, cos, hypot, pi, sin, sqrt
from typing import Dict, List, Optional, Sequence, Set, Tuple

FG_DIST = 60              # 바탕과 RGB 거리가 이보다 커야 전경
FG_LOW = 30               # 중립 칸은 이 이상이면서 이웃한 중립 전경 칸에 닿으면 전경 (1칸 옅은 선이 격자에 걸려 끊기는 것)
SAT_MIN = 0.25            # 채도가 이 아래면 중립(검정 · 회색)
FRINGE_SAT = 0.06         # 채도가 이 위인 옅은 가장자리는 이웃한 같은 색상의 군집으로 흡수
HUE_SPAN = 30             # 색상각이 이 안이면 같은 군집
HUE_MIN_SHARE = 0.02      # 색상 군집이 되려면 유채색 질량의 이만큼은 있어야
MAX_CLUSTERS = 6
LINE_FRAC = 0.40          # 선: 한 행 · 열에 이 비율 이상 걸쳐야
LINE_MAX_THICK = (8, 0.05)   # 선 띠의 최대 두께 = max(8, 0.05 × 그림 높이)
RING_MIN = 0.30           # 원 외곽 지름 ≥ 짧은 변의 이 비율
RING_SQUARE = 0.12        # 경계상자 가로세로 차이 ≤ 큰 쪽의 이 비율
RING_FILL = 0.25          # 채움률 ≤
GLYPH_MIN_H = 5           # 글자 높이 하한(px)
GLYPH_MAX_H = (14, 0.06)  # 글자 높이 상한 = max(14, 0.06 × 그림 높이)
NOISE_FRAC = 0.3          # 낱점 면적의 이 비율보다 작은 조각은 잡티
DEFAULT_UNIT = 4.0        # 낱점 면적을 알 길이 없을 때
MIN_DOT_AREA = 3          # 이보다 작은 조각은 점이 아니라 잡티 (JPEG 색 번짐)
CHAMFER = 3               # 거리 변환 가중치 (가로세로 3 · 대각 4)
RING_BRIDGE = 2           # 원 외곽 조각을 이만큼 떨어진 것까지 한 덩어리로 본다
RING_ROUND = 0.80         # 원 외곽 칸 중 중심에서 반지름 ±8% 안에 있는 비율 ≥ (정사각 틀과 구분)
LINE_MIN_RUN = 8          # 선 띠 안에서 이보다 긴 연속 구간이 선의 몸통
RING_STROKE = (3.0, 0.05)  # 외곽선 획 = 반지름 ±max(3, 5%) 안
RING_COVER = 0.60         # 둘레 5° 칸 중 획이 있는 비율 ≥ (정사각 틀 · 흩어진 점을 거른다)
NOTCH_MIN = 4             # 노치: 획 안쪽(반지름 80% 이상)에서 점에 닿지 않은 칸이 이만큼 모인 곳
HALO_NEAR = 0.5           # 중립 조각의 칸 중 이 비율 이상이 색 있는 점 가까이에 붙어 있으면 번짐 (크기와 상관없이)
HALO_REACH = (2, 0.6)     # 가까이 = max(2, 0.6 × √낱점 면적) 칸 — 그림을 키우면 번짐도 같이 커진다
LINE_BLUR_MAX = 40        # 다른 색 선 위의 이 면적 이하 조각은 색 번짐
ALIGN_TOL = (2.5, 0.25)   # 같은 줄로 보는 중심 차이 = max(2.5px, 글자 크기의 25%)
MAX_FG_RATIO = 0.5        # 배경이 아닌 칸이 이 비율을 넘으면 사진 · 채워진 그림으로 보고 분석하지 않는다
TICK_RATIO = 2.0          # 선 두께가 있을 때, 두께의 1.5 배 이하로 가늘고 이 배수 이상 긴 작은 조각은 눈금 막대
FRAME_SLACK = 1           # 틀(가장 바깥 세로선 둘) 밖으로 이만큼 넘어간 선 끝은 선이 아니라 라벨

HUE_NAMES = ((15, "빨강"), (40, "주황"), (70, "노랑"), (165, "초록"), (190, "청록"), (260, "파랑"), (290, "보라"),
             (340, "자홍"), (361, "빨강"))


@dataclass
class Cluster:
    index: int                     # 1 부터. 면적(픽셀 수)이 큰 순서
    name: str                      # 빨강 · 파랑 · 검정 · 회색 …
    rgb: Tuple[int, int, int]
    pixels: int
    neutral: bool


@dataclass
class Element:
    kind: str                      # hline vline ring text dot curve
    cluster: int
    bbox: Tuple[int, int, int, int]  # x0 y0 x1 y1 (끝 포함)
    area: int
    pixels: List[int]              # 그림 위 칸 번호 y * width + x
    cx: float = 0.0
    cy: float = 0.0
    count: int = 1                 # dot 의 추정 개수 (추정치다)
    thickness: float = 0.0         # hline · vline 의 두께


@dataclass
class Ring:
    cx: float
    cy: float
    r: float
    closed: float                  # 둘레 5° 칸 중 외곽이 있는 비율 (1.0 = 닫힘)
    notch: Optional[float]         # 노치 방향(도, 3시=0 · 아래쪽이 90). 없으면 None


@dataclass
class Segmentation:
    width: int
    height: int
    bg: Tuple[int, int, int]
    clusters: List[Cluster] = field(default_factory=list)
    elements: List[Element] = field(default_factory=list)
    unit: Dict[int, float] = field(default_factory=dict)   # 군집 → 낱점 면적
    line_thickness: Optional[float] = None
    ring: Optional[Ring] = None
    reason: str = ""               # 분석하지 않은 까닭 (한국어 한 줄). 비어 있으면 분석함

    def of(self, kind: str) -> List[Element]:
        return [e for e in self.elements if e.kind == kind]

    def dots(self, cluster: Optional[int] = None) -> int:
        return sum(e.count for e in self.elements if e.kind == "dot" and cluster in (None, e.cluster))

    def guess_kind(self) -> str:
        if self.ring is not None:
            return "wafer"
        if self.of("hline") or self.of("vline"):
            return "chart"
        return "unknown"


# ─────────────────────────────────────────────────────────────── 색 분류

def hue_name(rgb: Tuple[int, int, int], neutral: bool) -> str:
    h, s, v = colorsys.rgb_to_hsv(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
    if neutral:
        return "검정" if v < 0.35 else "회색"
    deg = h * 360
    return next(n for lim, n in HUE_NAMES if deg < lim)


def hue_gap(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def find_bg(img) -> Tuple[int, int, int]:
    w, h, rgb = img.width, img.height, img.rgb
    cells = list(range(w)) + list(range((h - 1) * w, h * w)) + list(range(0, h * w, w)) + list(range(w - 1, h * w, w))
    return Counter(tuple(rgb[3 * i:3 * i + 3]) for i in cells).most_common(1)[0][0]


def classify(img, bg) -> Tuple[bytearray, List[Cluster]]:
    """칸마다 군집 번호(0 = 바탕)를 붙인다. 군집은 면적이 큰 순서"""
    w, h, rgb = img.width, img.height, img.rgb
    cols = Counter(zip(rgb[0::3], rgb[1::3], rgb[2::3]))
    info = {}
    faint = set()
    for c, n in cols.items():
        d2 = (c[0] - bg[0]) ** 2 + (c[1] - bg[1]) ** 2 + (c[2] - bg[2]) ** 2
        if FG_LOW * FG_LOW < d2 <= FG_DIST * FG_DIST and colorsys.rgb_to_hsv(c[0] / 255, c[1] / 255, c[2] / 255)[1] < SAT_MIN:
            faint.add(c)
        if d2 > FG_DIST * FG_DIST:
            hh, s, v = colorsys.rgb_to_hsv(c[0] / 255, c[1] / 255, c[2] / 255)
            info[c] = (n, hh * 360, s)
    # 유채색의 색상 히스토그램 (5° 칸 · 채도로 가중) → 봉우리마다 군집
    hist = [0.0] * 72
    for n, hue, s in info.values():
        if s >= SAT_MIN:
            hist[int(hue // 5) % 72] += n * s
    total = sum(hist)
    centers: List[float] = []
    while total > 0 and len(centers) < MAX_CLUSTERS - 1:
        peak = max(range(72), key=lambda k: hist[k])
        if hist[peak] <= 0 or sum(hist[k] for k in range(72) if hue_gap(k * 5 + 2.5, peak * 5 + 2.5) <= HUE_SPAN) \
                < HUE_MIN_SHARE * total:
            break
        near = [k for k in range(72) if hue_gap(k * 5 + 2.5, peak * 5 + 2.5) <= HUE_SPAN]
        x = sum(hist[k] * cos((k * 5 + 2.5) * pi / 180) for k in near)
        y = sum(hist[k] * sin((k * 5 + 2.5) * pi / 180) for k in near)
        centers.append((atan2(y, x) * 180 / pi) % 360)
        for k in near:
            hist[k] = 0.0
        if sum(hist) <= 0:
            break
    # 색 → 임시 번호: 0 중립 · 1.. 유채색 군집 · 100+k 가장자리(군집 k 에 닿으면 k)
    code: Dict[Tuple[int, int, int], int] = {}
    for c, (n, hue, s) in info.items():
        if s >= SAT_MIN and centers:
            code[c] = 1 + min(range(len(centers)), key=lambda k: hue_gap(hue, centers[k]))
        elif s >= FRINGE_SAT and centers:
            k = min(range(len(centers)), key=lambda k: hue_gap(hue, centers[k]))
            code[c] = 100 + 1 + k if hue_gap(hue, centers[k]) <= HUE_SPAN else 0
        else:
            code[c] = 0
    lut = {c: code.get(c, 249 if c in faint else -1) for c in cols}
    raw = bytearray(len(rgb) // 3)
    for i, c in enumerate(zip(rgb[0::3], rgb[1::3], rgb[2::3])):
        v = lut[c]
        if v >= 0:
            raw[i] = v + 1       # 중립 1 · 유채색 군집 2.. · 가장자리 100 + (닿을 군집 번호) · 옅은 중립 250
    # 가장자리(옅은 번짐)는 같은 군집의 진한 칸과 닿아 있으면 그 군집으로, 아니면 중립으로
    fringe = [i for i, v in enumerate(raw) if v > 100]
    for _ in range(2):
        left = []
        for i in fringe:
            want = raw[i] - 100
            x = i % w
            hit = False
            for j in _neighbors(i, x, w, h):
                if raw[j] == want:
                    hit = True
                    break
            if hit:
                raw[i] = want
            else:
                left.append(i)
        fringe = left
    for i in fringe:
        raw[i] = 1
    pending = [i for i, v in enumerate(raw) if v == 250]
    for _ in range(4):                           # 옅은 중립 칸은 중립 전경에 닿아 있을 때만 (몇 칸씩 이어 붙인다)
        left = [i for i in pending if not any(raw[j] == 1 for j in _neighbors(i, i % w, w, h))]
        if len(left) == len(pending):
            break
        for i in pending:
            if raw[i] == 250 and any(raw[j] == 1 for j in _neighbors(i, i % w, w, h)):
                raw[i] = 1
        pending = [i for i in pending if raw[i] == 250]
    for i in pending:
        raw[i] = 0
    # 쓰이는 번호만 남기고 면적 순으로 다시 매긴다
    used = Counter(raw)
    used.pop(0, None)
    order = sorted(used, key=lambda k: -used[k])
    remap = bytearray(256)
    clusters = []
    for new, old in enumerate(order, 1):
        remap[old] = new
        members = [(c, n) for c, n in cols.items() if c in info and lut[c] + 1 == old]
        neutral = old == 1
        pool = [(c, n) for c, n in members if info[c][2] >= 0.5] or members
        tot = sum(n for _, n in pool) or 1
        rgb_mean = tuple(int(sum(c[k] * n for c, n in pool) / tot) for k in range(3)) if pool else (0, 0, 0)
        clusters.append(Cluster(new, hue_name(rgb_mean, neutral), rgb_mean, used[old], neutral))
    return bytearray(remap[v] for v in raw), clusters


def _neighbors(i: int, x: int, w: int, h: int):
    out = []
    n = w * h
    for dy in (-w, 0, w):
        for dx in (-1, 0, 1):
            if (dy or dx) and 0 <= i + dy + dx < n and 0 <= x + dx < w:
                out.append(i + dy + dx)
    return out


# ─────────────────────────────────────────────────────────────── 연결요소 · 거리 변환

def components_of(idx: Sequence[int], w: int, reach: int = 1) -> List[List[int]]:
    """칸 번호 목록 → 이어진 덩어리들 (반복형). reach 1 = 8방향 · 2 = 한 칸 끊긴 것까지"""
    todo: Set[int] = set(idx)
    offs = [(dx, dy) for dy in range(-reach, reach + 1) for dx in range(-reach, reach + 1) if dx or dy]
    out = []
    while todo:
        s = todo.pop()
        comp, stack = [s], [s]
        while stack:
            i = stack.pop()
            x = i % w
            for dx, dy in offs:
                if 0 <= x + dx < w:
                    j = i + dy * w + dx
                    if j in todo:
                        todo.discard(j)
                        comp.append(j)
                        stack.append(j)
        out.append(comp)
    return out


def bbox_of(pix: Sequence[int], w: int) -> Tuple[int, int, int, int]:
    xs = [i % w for i in pix]
    ys = [i // w for i in pix]
    return min(xs), min(ys), max(xs), max(ys)


def distance_map(pix: Sequence[int], w: int, box: Tuple[int, int, int, int]) -> Dict[int, int]:
    """칸 → 가장 가까운 바탕 칸까지의 거리 × 3 (가중 3-4 거리 변환). 상자 밖은 바탕"""
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0 + 3, y1 - y0 + 3
    inf = 1 << 20
    d = [0] * (bw * bh)
    for i in pix:
        d[(i // w - y0 + 1) * bw + (i % w - x0 + 1)] = inf
    for y in range(1, bh - 1):
        for x in range(1, bw - 1):
            k = y * bw + x
            if d[k]:
                d[k] = min(d[k - 1] + 3, d[k - bw] + 3, d[k - bw - 1] + 4, d[k - bw + 1] + 4)
    for y in range(bh - 2, 0, -1):
        for x in range(bw - 2, 0, -1):
            k = y * bw + x
            if d[k]:
                d[k] = min(d[k], d[k + 1] + 3, d[k + bw] + 3, d[k + bw + 1] + 4, d[k + bw - 1] + 4)
    return {i: d[(i // w - y0 + 1) * bw + (i % w - x0 + 1)] for i in pix}


def median(vals: Sequence[float]) -> float:
    s = sorted(vals)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


# ─────────────────────────────────────────────────────────────── 요소 분류

def body_extent(pix: Sequence[int], w: int, horizontal: bool) -> Optional[Tuple[int, int]]:
    """띠 안에서 LINE_MIN_RUN 보다 긴 연속 구간들이 걸친 범위. 그런 구간이 없으면(점선) None"""
    rows: Dict[int, List[int]] = {}
    for i in pix:
        rows.setdefault(i // w if horizontal else i % w, []).append(i % w if horizontal else i // w)
    lo = hi = None
    for xs in rows.values():
        xs.sort()
        start = prev = xs[0]
        for x in xs[1:] + [None]:
            if x is None or x - prev > 1:
                if prev - start + 1 >= LINE_MIN_RUN:
                    lo = start if lo is None else min(lo, start)
                    hi = prev if hi is None else max(hi, prev)
                if x is not None:
                    start = x
            if x is not None:
                prev = x
    return None if lo is None else (lo, hi)


def find_lines(per: Dict[int, List[int]], w: int, h: int, horizontal: bool) -> Tuple[List[Element], Dict[int, List[int]]]:
    """색마다 한 행(열)에 LINE_FRAC 이상 걸친 띠를 선으로 떼어 낸다. 같은 행의 토막은 한 줄로 본다"""
    span, other = (w, h) if horizontal else (h, w)
    limit = max(LINE_MAX_THICK[0], int(LINE_MAX_THICK[1] * other))
    lines: List[Element] = []
    rest: Dict[int, List[int]] = {}
    for k, idx in per.items():
        key = (lambda i: i // w) if horizontal else (lambda i: i % w)
        counts = Counter(key(i) for i in idx)
        rows = sorted(r for r, n in counts.items() if n >= max(8, LINE_FRAC * span))
        bands: List[List[int]] = []
        for r in rows:
            if bands and r - bands[-1][-1] <= 2:
                bands[-1].append(r)
            else:
                bands.append([r])
        taken: Set[int] = set()
        for band in bands:
            lo, hi = band[0], band[-1]
            if hi - lo + 1 > limit:
                continue
            pix = [i for i in idx if lo - 1 <= key(i) <= hi + 1]       # 가장자리의 옅은 줄까지
            ext = body_extent([i for i in pix if lo <= key(i) <= hi], w, horizontal)
            if ext is not None:                  # 선 끝 옆에 놓인 글자가 같이 지워지지 않게
                pix = [i for i in pix if ext[0] <= ((i % w) if horizontal else (i // w)) <= ext[1]]
            box = bbox_of(pix, w)
            length = (box[2] - box[0] + 1) if horizontal else (box[3] - box[1] + 1)
            lines.append(Element("hline" if horizontal else "vline", k, box, len(pix), pix,
                                 sum(i % w for i in pix) / len(pix), sum(i // w for i in pix) / len(pix),
                                 1, len(pix) / max(1, length)))
            taken.update(pix)
        rest[k] = [i for i in idx if i not in taken] if taken else idx
    return lines, rest


def is_round(bw: int, bh: int, area: int) -> bool:
    fill = area / (bw * bh)
    aspect = bw / bh
    return fill >= 0.70 and (0.7 <= aspect <= 1.43 or max(bw, bh) <= 4)


def find_ring(wide, per: Dict[int, List[int]], cls: bytearray, w: int, h: int):
    """원 외곽: 정사각에 가깝고 크고 속이 빈 덩어리 중 가장 큰 것 → (Ring, 군집, 외곽 칸, 지울 칸) 또는 None.
    획(반지름 ± 몇 칸)만 외곽이고, 점에 닿은 안쪽의 옅은 번짐은 버린다. 노치는 점에 닿지 않은 안쪽 칸의 쏠림"""
    best = None
    for n, (k, pix, box) in enumerate(wide):
        bw, bh = box[2] - box[0] + 1, box[3] - box[1] + 1
        if min(bw, bh) >= RING_MIN * min(w, h) and abs(bw - bh) <= RING_SQUARE * max(bw, bh) \
                and len(pix) / (bw * bh) <= RING_FILL and (best is None or bw * bh > best[0]):
            best = (bw * bh, n)
    if best is None:
        return None
    k, group, box = wide[best[1]]
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    r = ((box[2] - box[0] + 1) + (box[3] - box[1] + 1)) / 4
    tol = max(RING_STROKE[0], RING_STROKE[1] * r)

    def polar(i: int) -> Tuple[float, float]:
        dx, dy = i % w - cx, i // w - cy
        return hypot(dx, dy), (atan2(dy, dx) * 180 / pi) % 360

    group_set = set(group)
    extra = [i for i in per[k] if i not in group_set and abs(polar(i)[0] - r) <= tol]   # 떨어져 나간 획 조각
    stroke = [i for i in group if abs(polar(i)[0] - r) <= tol] + extra
    bins = {int(polar(i)[1] // 5) for i in stroke}
    if len(bins) / 72 < RING_COVER:
        return None
    dent: Dict[int, List[int]] = {}
    for i in group:
        d, ang = polar(i)
        if 0.8 * r <= d < r - tol and not _touches_other(i, w, h, cls, k):
            dent.setdefault(int(ang // 5), []).append(i)
    notch = None
    if dent:
        scores = {b: sum(len(dent.get((b + o) % 72, ())) for o in (-1, 0, 1)) for b in dent}
        top = max(scores, key=lambda b: scores[b])
        if scores[top] >= NOTCH_MIN:
            near = [polar(i)[1] for o in (-1, 0, 1) for i in dent.get((top + o) % 72, ())]
            x = sum(cos(a * pi / 180) for a in near)
            y = sum(sin(a * pi / 180) for a in near)
            notch = (atan2(y, x) * 180 / pi) % 360
    pixels = stroke + [i for b in dent for i in dent[b]]
    return Ring(cx, cy, r, len(bins) / 72, notch), k, pixels, group_set | set(extra)


def _near_share(pix: Sequence[int], w: int, h: int, cells: Set[int], reach: int) -> float:
    """pix 의 칸 중 둘레(reach 칸)에 cells 의 칸이 있는 것의 비율"""
    hit = 0
    for i in pix:
        x, y = i % w, i // w
        found = False
        for yy in range(max(0, y - reach), min(h, y + reach + 1)):
            base = yy * w
            for xx in range(max(0, x - reach), min(w, x + reach + 1)):
                if base + xx in cells:
                    found = True
                    break
            if found:
                break
        hit += found
    return hit / len(pix)


def _touches_other(i: int, w: int, h: int, cls: bytearray, k: int, reach: int = 2) -> bool:
    """i 의 둘레(reach 칸)에 군집 k 가 아닌 전경이 있는가"""
    x, y = i % w, i // w
    for yy in range(max(0, y - reach), min(h, y + reach + 1)):
        for xx in range(max(0, x - reach), min(w, x + reach + 1)):
            v = cls[yy * w + xx]
            if v and v != k:
                return True
    return False


def glyph_runs(cands, vertical: bool) -> Set[int]:
    """높이가 비슷하고 나란히 놓인 덩어리들 = 글자 줄. 둥글지 않은 것이 하나라도 있어야 글자로 본다"""
    pos = (lambda b: (b[1], b[3], b[0], b[2])) if vertical else (lambda b: (b[0], b[2], b[1], b[3]))
    order = sorted(range(len(cands)), key=lambda n: pos(cands[n][1])[0])
    runs: List[List[int]] = []
    for n in order:
        a0, a1, b0, b1 = pos(cands[n][1])
        size = b1 - b0 + 1
        for run in reversed(runs[-60:]):        # 위아래 줄이 섞여도 맞는 줄을 찾는다
            p0, p1, q0, q1 = pos(cands[run[-1]][1])
            psize = q1 - q0 + 1
            if a0 - p1 <= 1.3 * max(size, psize) and abs((b0 + b1) / 2 - (q0 + q1) / 2) <= 0.4 * max(size, psize) \
                    and 0.6 <= size / psize <= 1.67:
                run.append(n)
                break
        else:
            runs.append([n])
    out: Set[int] = set()
    for run in runs:
        if len(run) >= 2 and any(not cands[n][3] for n in run):
            out.update(run)
    return out


def split_markers(pix: List[int], w: int, rc: float):
    """굵은 곡선에 붙은 마커를 거리 변환으로 떼어 낸다 → ([(중심 x, 중심 y, 몸통 칸, 코어 면적)], 곡선 칸) 또는 None"""
    box = bbox_of(pix, w)
    dist = distance_map(pix, w, box)
    cut = int(round(rc * CHAMFER))
    core = [i for i, d in dist.items() if d >= cut]
    if not core:
        return None
    marks = []
    body: Set[int] = set()
    for cp in components_of(core, w):
        cx, cy = sum(i % w for i in cp) / len(cp), sum(i // w for i in cp) / len(cp)
        reach = max(dist[i] for i in cp) / CHAMFER + 0.5
        mb = [i for i in pix if hypot(i % w - cx, i // w - cy) <= reach]
        body.update(mb)
        marks.append((cx, cy, mb, len(cp)))
    return marks, [i for i in pix if i not in body]


def clamp_to_frame(hl: List[Element], vl: List[Element], per: Dict[int, List[int]], w: int):
    """세로선이 둘 이상이면 가장 바깥 둘이 틀이다. 가로선이 틀 밖으로 나간 끝(선 끝 옆에 놓인 라벨의 칸)은
    선에서 떼어 군집의 일반 칸으로 돌려 글자가 되게 한다"""
    if len(vl) < 2 or not hl:
        return hl, vl
    xs = sorted(e.cx for e in vl)
    lo, hi = xs[0] - FRAME_SLACK, xs[-1] + FRAME_SLACK
    out = []
    for e in hl:
        inside = [i for i in e.pixels if lo <= i % w <= hi]
        if len(inside) == len(e.pixels) or not inside:
            out.append(e)
            continue
        gone = [i for i in e.pixels if not lo <= i % w <= hi]
        per[e.cluster] = per.get(e.cluster, []) + gone
        box = bbox_of(inside, w)
        out.append(Element("hline", e.cluster, box, len(inside), inside, sum(i % w for i in inside) / len(inside),
                           sum(i // w for i in inside) / len(inside), 1, len(inside) / max(1, box[2] - box[0] + 1)))
    return out, vl


def aligned_rows(cands, vertical: bool) -> Set[int]:
    """눈금 글자처럼 간격은 넓어도 같은 줄(중심 높이가 같은)에 놓인 비슷한 크기의 덩어리 ≥ 3 — 둥글지 않은 것이 하나라도 있어야"""
    key = (lambda b: (b[0] + b[2]) / 2) if vertical else (lambda b: (b[1] + b[3]) / 2)
    size = (lambda b: b[2] - b[0] + 1) if vertical else (lambda b: b[3] - b[1] + 1)
    order = sorted(range(len(cands)), key=lambda n: key(cands[n][1]))
    out: Set[int] = set()
    group: List[int] = []

    def flush() -> None:
        if len(group) >= 3 and any(not cands[n][3] for n in group):
            out.update(group)

    for n in order:
        if group and key(cands[n][1]) - key(cands[group[-1]][1]) <= max(ALIGN_TOL[0], ALIGN_TOL[1] * size(cands[group[0]][1])) \
                and 0.7 <= size(cands[n][1]) / size(cands[group[0]][1]) <= 1.43:
            group.append(n)
        else:
            flush()
            group = [n]
    flush()
    return out


def segment(img) -> Segmentation:
    w, h = img.width, img.height
    bg = find_bg(img)
    cls, clusters = classify(img, bg)
    seg = Segmentation(w, h, bg, clusters)
    per: Dict[int, List[int]] = {}
    for i, v in enumerate(cls):
        if v:
            per.setdefault(v, []).append(i)
    if not per:
        return seg
    if sum(len(v) for v in per.values()) > MAX_FG_RATIO * w * h:
        seg.reason = "바탕이 아닌 곳이 절반이 넘습니다 (사진이나 채워진 그림은 대상이 아닙니다)"
        return seg
    chrom = {i for k, idx in per.items() if not clusters[k - 1].neutral for i in idx}    # 색 있는 칸
    # ── 선: 가로 · 세로
    hl, per = find_lines(per, w, h, True)
    vl, per = find_lines(per, w, h, False)
    hl, vl = clamp_to_frame(hl, vl, per, w)
    seg.elements += hl + vl
    if hl + vl:
        seg.line_thickness = median([e.thickness for e in hl + vl])
    # ── 원 외곽: 끊긴 조각을 이어서 찾는다 (JPEG 로 옅은 1칸 선이 끊긴다)
    wide = [(k, pix, bbox_of(pix, w)) for k, idx in per.items() for pix in components_of(idx, w, RING_BRIDGE)
            if len(pix) >= 8]
    found = find_ring(wide, per, cls, w, h)
    ring = None
    if found is not None:
        ring, k, pixels, gone = found
        seg.ring = ring
        seg.elements.append(Element("ring", k, bbox_of(pixels, w), len(pixels), pixels, ring.cx, ring.cy))
        per[k] = [i for i in per[k] if i not in gone]

    def in_ring(box) -> bool:
        return ring is not None and hypot((box[0] + box[2]) / 2 - ring.cx, (box[1] + box[3]) / 2 - ring.cy) < 1.05 * ring.r + 1          # 외곽선 위의 점도 데이터

    # ── 연결요소
    comps = []                                   # (군집, 칸 목록, 상자)
    for k, idx in per.items():
        for pix in components_of(idx, w):
            comps.append((k, pix, bbox_of(pix, w)))
    # ── 글자: 높이가 글자만 한 덩어리 중 줄을 이루는 것 (링 안은 데이터)
    max_h = max(GLYPH_MAX_H[0], GLYPH_MAX_H[1] * h)
    cands = []
    for n, (k, pix, box) in enumerate(comps):
        bw, bh = box[2] - box[0] + 1, box[3] - box[1] + 1
        if GLYPH_MIN_H <= max(bw, bh) <= max_h * 6 and min(bw, bh) <= max_h and not in_ring(box):
            cands.append((n, box, len(pix), is_round(bw, bh, len(pix))))
    text: Set[int] = set()
    for vertical in (False, True):
        sub = list(cands)
        sub = [c for c in sub if c[0] not in text]
        for m in glyph_runs(sub, vertical):
            text.add(sub[m][0])
    for vertical in (False, True):          # 눈금 글자: 이미 글자로 본 덩어리와 같은 줄에 놓인 둥근 것(0)도 함께
        for m in aligned_rows(cands, vertical):
            text.add(cands[m][0])
    for n, box, area, rnd in cands:             # 낱글자처럼 보이는 가로로 긴 단어 덩어리
        bw, bh = box[2] - box[0] + 1, box[3] - box[1] + 1
        if n not in text and not rnd and bw >= 1.3 * bh and GLYPH_MIN_H <= bh <= max_h \
                and 0.3 <= area / (bw * bh) <= 0.85:
            text.add(n)
    text_boxes = []
    keep = []
    for n, (k, pix, box) in enumerate(comps):
        if n in text:
            text_boxes.append(box)
            seg.elements.append(Element("text", k, box, len(pix), pix, sum(i % w for i in pix) / len(pix),
                                        sum(i // w for i in pix) / len(pix)))
        else:
            keep.append((k, pix, box))

    def on_text(box) -> bool:                    # 글자 둘레의 JPEG 번짐 조각 (상자가 글자 상자와 2칸 안에서 겹침)
        return any(box[0] <= t[2] + 2 and box[2] >= t[0] - 2 and box[1] <= t[3] + 2 and box[3] >= t[1] - 2
                   for t in text_boxes)

    line_boxes = [(e.cluster, e.bbox) for e in seg.elements if e.kind in ("hline", "vline")]

    def on_line(k: int, box, area: int) -> bool:   # 다른 색 선 위의 색 번짐
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        return area <= LINE_BLUR_MAX and any(lk != k and b[0] - 1 <= cx <= b[2] + 1 and b[1] - 1 <= cy <= b[3] + 1
                                        for lk, b in line_boxes)

    keep = [c for c in keep if not (max(c[2][2] - c[2][0], c[2][3] - c[2][1]) + 1 <= max_h
                                    and (on_text(c[2]) or on_line(c[0], c[2], len(c[1]))))]
    # ── 낱점 면적: 군집마다 외톨이 둥근 덩어리의 중앙값
    unit: Dict[int, float] = {}

    def estimate(k: int, comps_) -> None:
        areas = []
        for kk, pix, box in comps_:
            bw, bh = box[2] - box[0] + 1, box[3] - box[1] + 1
            if kk == k and len(pix) >= 4 and max(bw, bh) <= 0.1 * max(w, h) and is_round(bw, bh, len(pix)):
                areas.append(len(pix))
        if areas:
            m = median(areas)
            unit[k] = median([a for a in areas if a <= 3 * m])

    for k in {c[0] for c in keep if not clusters[c[0] - 1].neutral}:
        estimate(k, keep)            # 중립은 번짐 조각에 속지 않게 뒤에서
    rc = seg.line_thickness + 1.0 if seg.line_thickness else None
    small = []
    for k, pix, box in keep:
        bw, bh = box[2] - box[0] + 1, box[3] - box[1] + 1
        cx, cy = sum(i % w for i in pix) / len(pix), sum(i // w for i in pix) / len(pix)
        if rc is not None and max(bw, bh) >= 4 * rc:          # 선에 붙은 마커가 있을 수 있는 큰 덩어리
            res = split_markers(pix, w, rc)
            if res is not None:
                marks, rest = res
                base = median([m[3] for m in marks])
                for mx, my, mb, ca in marks:
                    seg.elements.append(Element("dot", k, bbox_of(mb, w), len(mb), mb, mx, my,
                                                max(1, int(round(ca / base)))))
                unit[k] = float(median([len(m[2]) for m in marks]))      # 마커가 있으면 마커가 낱점이다
                if rest:
                    seg.elements.append(Element("curve", k, bbox_of(rest, w), len(rest), rest, cx, cy))
                continue
        small.append((k, pix, box, bw, bh, cx, cy))
    chroma_units = [v for k, v in unit.items() if not clusters[k - 1].neutral]
    if chroma_units:                                                         # 색 있는 점에 붙은 중립 조각은 번짐
        reach = max(HALO_REACH[0], int(round(HALO_REACH[1] * sqrt(median(chroma_units)))))
        small = [t for t in small if not (clusters[t[0] - 1].neutral and _near_share(t[1], w, h, chrom, reach) >= HALO_NEAR)]
    for k in {t[0] for t in small if clusters[t[0] - 1].neutral}:
        estimate(k, [(t[0], t[1], t[2]) for t in small])
    for k, pix, box, bw, bh, cx, cy in small:
        u = unit.get(k)
        if u is None and (max(bw, bh) >= 0.12 * max(w, h) and len(pix) / (bw * bh) <= 0.5):
            seg.elements.append(Element("curve", k, box, len(pix), pix, cx, cy))
            continue
        if seg.line_thickness and min(bw, bh) <= 1.5 * seg.line_thickness and max(bw, bh) >= TICK_RATIO * min(bw, bh) \
                and len(pix) <= 12 * seg.line_thickness ** 2:
            seg.elements.append(Element("curve", k, box, len(pix), pix, cx, cy))     # 눈금 · 선 조각
            continue
        u = u or DEFAULT_UNIT
        if len(pix) < max(MIN_DOT_AREA, NOISE_FRAC * u):
            continue
        seg.elements.append(Element("dot", k, box, len(pix), pix, cx, cy, max(1, int(round(len(pix) / u)))))
    seg.unit.update(unit)
    return seg
