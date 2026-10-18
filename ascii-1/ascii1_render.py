# -*- coding: utf-8 -*-
"""ascii1_render - 요소 목록(ascii1_seg.Segmentation)을 글자 격자로 옮긴다. 설계서 docs/plans/ascii-1-design.md › ⑤⑥⑦

격자: 열 수 width(그림 폭보다 넓지 않게) · 셀 세로 = 가로의 2 배 (터미널 글자 종횡비). 한 셀에는 글자 하나.
우선순위: 점 > 가로 · 세로 선 > 곡선 > 원 외곽. 같은 입력은 같은 글자를 낸다.
글자(텍스트)는 읽지 않고 비운다. 범례는 맨 아래에 군집마다 어떤 글자를 줬는지 적는다.
"""
from math import atan2, ceil, cos, hypot, pi, sin
from typing import Dict, List, Optional, Sequence, Tuple

from ascii1_seg import TREND_GAP, Element, Segmentation, components_of, trend_bin

DEFAULT_WIDTH = 120
MIN_WIDTH, MAX_WIDTH = 40, 300
CELL_ASPECT = 2.0                  # 셀 세로 ÷ 셀 가로 (터미널 글자 종횡비 1:2)
PATH_MIN_PIXELS = {"curve": 2, "ring": 1}   # 셀 안에 이만큼은 있어야 그린다 (1칸 외곽선은 셀당 1–2 칸뿐)
HORIZONTAL_SLOPE = 1.4             # 픽셀 기울기 |dy/dx| 가 이보다 작으면 가로(글자가 세로로 2 배라 셀 기울기는 0.7), VERTICAL 보다 크면 세로
VERTICAL_SLOPE = 6.0
RING_BRIDGE_MAX = 8                # 링 셀 사이가 이 칸 수 이하로 벌어졌으면 직선으로 잇는다
DOT_REACH = 4.0                    # 곡선 조각의 끝이 점 몸통에서 이만큼(px) 안이면 그 점의 중심까지 잇는다
CURVE_SPREAD = (3.0, 8.0)           # 한 구간(빈) 안에서 곡선이 max(3 셀, 8 px) 보다 넓게 퍼지면 한 줄이 아니라 모양이 복잡한 것
MIN_CURVE_CELLS = 2.0              # 곡선 조각의 긴 변이 셀 가로의 이만큼 안 되면(눈금 막대) 그리지 않는다

POINT_SETS = (("o", "O", "@"), ("x", "X", "%"), ("*", "#", "&"), ("s", "S", "$"), ("a", "A", "8"), ("z", "Z", "0"))
HLINE_SETS = ("=", "~", "_", "^", ",", "`")          # 색 있는 가로선 (중립은 `-`)
VLINE_SETS = ("!", ":", ";", "'", ".", "i")          # 색 있는 세로선 (중립은 `|`)
RING_GLYPH = "."
NOTCH_GLYPHS = ((45, ">"), (135, "v"), (225, "<"), (315, "^"), (361, ">"))   # 3시 방향이 0° · 아래쪽이 90°
BOX = {"-": "─", "|": "│", "+": "┼"}

Cell = Tuple[int, int]             # (행, 열)


def content_box(seg: Segmentation) -> Tuple[int, int, int, int]:
    """그려질 요소(글자 제외)가 차지하는 영역 x0 y0 x1 y1. 아무것도 없으면 그림 전체"""
    boxes = [e.bbox for e in seg.elements if e.kind != "text"]
    if not boxes:
        return 0, 0, seg.width - 1, seg.height - 1
    return min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)


class Geometry:
    """열 수는 그림 전체가 아니라 그려질 내용의 폭에 걸린다 — 여백에 열을 쓰지 않는다"""

    def __init__(self, seg: Segmentation, width: int):
        self.x0, self.y0, x1, y1 = content_box(seg)
        content_w, content_h = x1 - self.x0 + 1, y1 - self.y0 + 1
        self.cols = max(1, min(width, content_w))             # 셀이 한 칸(1 px)보다 좁아지지는 않게
        self.cw = content_w / self.cols
        self.ch = self.cw * CELL_ASPECT
        self.rows = max(1, int(ceil(content_h / self.ch)))
        self.w = seg.width

    def cell_xy(self, x: float, y: float) -> Cell:
        return (min(self.rows - 1, max(0, int((y - self.y0) / self.ch))),
                min(self.cols - 1, max(0, int((x - self.x0) / self.cw))))

    def cell(self, i: int) -> Cell:
        return self.cell_xy(i % self.w + 0.5, i // self.w + 0.5)


def allocate_dots(seg: Segmentation, geo: Geometry) -> Dict[Cell, Dict[int, int]]:
    """점의 추정 개수를 셀에 나눠 담는다 → {셀: {군집: 개수}}. 합은 seg 의 개수와 같다 (가장 큰 나머지 순으로 올림).
    낱점은 중심이 놓인 셀 하나에, 뭉친 덩어리는 칸 수에 비례해 걸친 셀들에, 빽빽한 군집(field)은 블록 질량을 블록 중심이 놓인
    셀에 모아 질량에 비례해 — 겹침 보정을 군집 전체 비율로 고르게 나눈다 (설계서 14-11)"""
    out: Dict[Cell, Dict[int, int]] = {}

    def add(cell: Cell, k: int, n: int) -> None:
        if n:
            out.setdefault(cell, {})[k] = out.get(cell, {}).get(k, 0) + n

    for e in seg.elements:
        share: Dict[Cell, int] = {}
        if e.kind == "field":
            d = e.density
            for n, m in enumerate(d.mass):
                if m:
                    c = geo.cell_xy(d.x0 + (n % d.cols + 0.5) * d.block, d.y0 + (n // d.cols + 0.5) * d.block)
                    share[c] = share.get(c, 0) + m
        elif e.kind != "dot":
            continue
        elif e.count == 1:
            add(geo.cell_xy(e.cx + 0.5, e.cy + 0.5), e.cluster, 1)
            continue
        else:
            for i in e.pixels:
                c = geo.cell(i)
                share[c] = share.get(c, 0) + 1
        total = sum(share.values())
        if not total:
            continue
        exact = {c: e.count * n / total for c, n in share.items()}
        got = {c: int(v) for c, v in exact.items()}
        left = e.count - sum(got.values())
        for c in sorted(exact, key=lambda c: (-(exact[c] - got[c]), c))[:left]:
            got[c] += 1
        for c, n in got.items():
            add(c, e.cluster, n)
    return out


def ladder(n: int, capacity: float) -> int:
    """한 셀의 점 수 → 0(낱점) · 1(둘 이상) · 2(빽빽함). 셀에 낱점이 capacity 개쯤 들어가므로 빽빽함의 문턱은 거기에 맞춘다"""
    if n <= 1:
        return 0
    return 2 if n >= max(3, min(4, int(ceil(0.75 * capacity)))) else 1


class Moments:
    """셀 안의 칸들의 합 · 제곱합 — 이웃 셀을 합쳐 주축 방향을 구한다"""
    __slots__ = ("n", "sx", "sy", "sxx", "syy", "sxy")

    def __init__(self) -> None:
        self.n = 0
        self.sx = self.sy = self.sxx = self.syy = self.sxy = 0.0

    def add(self, x: float, y: float) -> None:
        self.n += 1
        self.sx += x
        self.sy += y
        self.sxx += x * x
        self.syy += y * y
        self.sxy += x * y

    def merge(self, o: "Moments") -> None:
        self.n += o.n
        self.sx += o.sx
        self.sy += o.sy
        self.sxx += o.sxx
        self.syy += o.syy
        self.sxy += o.sxy

    def slope(self) -> Optional[float]:
        """주축의 |dy/dx| (세로면 inf). 칸이 둘 미만이면 None"""
        if self.n < 2:
            return None
        mx, my = self.sx / self.n, self.sy / self.n
        vxx, vyy, vxy = self.sxx / self.n - mx * mx, self.syy / self.n - my * my, self.sxy / self.n - mx * my
        if abs(vxx - vyy) < 1e-9 and abs(vxy) < 1e-9:
            return None
        theta = 0.5 * atan2(2 * vxy, vxx - vyy)
        c, s = cos(theta), sin(theta)
        return float("inf") if abs(c) < 1e-9 else abs(s / c)


def path_cells(pixels: Sequence[int], geo: Geometry) -> Dict[Cell, Moments]:
    out: Dict[Cell, Moments] = {}
    for i in pixels:
        x, y = i % geo.w + 0.5, i // geo.w + 0.5
        out.setdefault(geo.cell_xy(x, y), Moments()).add(x, y)
    return out


def thin(cells: Dict[Cell, Moments], min_pixels: int = 2) -> Dict[Cell, str]:
    """곡선 · 외곽을 한 셀 두께로 솎고 셀마다 방향('h' 가로 · 'v' 세로 · '\\' · '/')을 붙인다"""
    keep: Dict[Cell, str] = {}
    for (r, c), m in cells.items():
        if m.n < min_pixels:
            continue
        win = Moments()
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                o = cells.get((r + dr, c + dc))
                if o is not None:
                    win.merge(o)
        s = win.slope()
        if s is None or s < HORIZONTAL_SLOPE:
            kind = "h"
        elif s > VERTICAL_SLOPE:
            kind = "v"
        else:
            mx, my = win.sx / win.n, win.sy / win.n
            kind = "\\" if win.sxy / win.n - mx * my > 0 else "/"
        # 가로로 가는 선은 한 열에 한 행만, 세로 · 대각선은 한 행에 한 열만 남긴다
        side = [cells.get((r - 1, c)), cells.get((r + 1, c))] if kind == "h" else [cells.get((r, c - 1)), cells.get((r, c + 1))]
        before = side[0].n if side[0] is not None else 0
        after = side[1].n if side[1] is not None else 0
        if m.n > before and m.n >= after:
            keep[(r, c)] = kind
    return keep


def close_ring(cells: Sequence[Cell], geo: Geometry, ring) -> List[Cell]:
    """링 셀을 중심 둘레 각도 순으로 이어 보고, 이웃한 두 셀이 붙어 있지 않으면 사이를 직선으로 채운다
    (JPEG 로 끊긴 곳 · 뾰족한 노치 옆). 너무 멀리 떨어진 곳(RING_BRIDGE_MAX 셀 초과)은 열린 채 둔다"""
    if len(cells) < 3:
        return []
    cx, cy = ring.cx, ring.cy
    order = sorted(cells, key=lambda rc: atan2((rc[0] + 0.5) * geo.ch - cy, (rc[1] + 0.5) * geo.cw - cx))
    extra: List[Cell] = []
    for a, b in zip(order, order[1:] + order[:1]):
        gap = max(abs(a[0] - b[0]), abs(a[1] - b[1]))
        if 1 < gap <= RING_BRIDGE_MAX:
            (r0, c0), (r1, c1) = a, b
            for k in range(1, gap):
                extra.append((int(round(r0 + (r1 - r0) * k / gap)), int(round(c0 + (c1 - c0) * k / gap))))
    return extra


def centerline(piece: Sequence[int], geo: Geometry) -> Optional[List[Tuple[float, float]]]:
    """곡선 조각의 중심선 — 긴 쪽 축을 따라 셀 크기 구간으로 나눠 구간마다 중심을 잡는다. 한 줄로 안 풀리는 모양(퍼짐이
    CURVE_SPREAD 초과)이면 None"""
    xs = [i % geo.w for i in piece]
    ys = [i // geo.w for i in piece]
    along_x = (max(xs) - min(xs)) >= (max(ys) - min(ys))
    key, other = (xs, ys) if along_x else (ys, xs)
    binw = geo.cw if along_x else geo.ch
    spread_max = max(CURVE_SPREAD[0] * (geo.ch if along_x else geo.cw), CURVE_SPREAD[1])     # 세밀한 격자에서도 선 두께는 남는다
    bins: Dict[int, List[float]] = {}
    lo = min(key)
    for k, o, x, y in zip(key, other, xs, ys):
        b = bins.setdefault(int((k - lo) / binw), [0.0, 0.0, 0, o, o])
        b[0] += x + 0.5
        b[1] += y + 0.5
        b[2] += 1
        b[3], b[4] = min(b[3], o), max(b[4], o)
    if any(b[4] - b[3] + 1 > spread_max for b in bins.values()):
        return None
    line = [(b[0] / b[2], b[1] / b[2]) for _, b in sorted(bins.items())]
    # 양 끝은 구간 중심이 아니라 조각의 실제 끝 — 가파른 조각은 구간이 커서 중심이 끝에서 한참 안쪽이다
    for pick, at in ((min, 0), (max, -1)):
        edge = pick(key)
        pts = [(x + 0.5, y + 0.5) for k, x, y in zip(key, xs, ys) if k == edge]
        end = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        if at == 0:
            line.insert(0, end)
        else:
            line.append(end)
    return line


def segment_cells(a: Tuple[float, float], b: Tuple[float, float], geo: Geometry) -> List[Tuple[Cell, str]]:
    """두 점 사이를 셀로 잇고 셀마다 기울기 글자를 붙인다 (기울기는 두 점이 정한다)"""
    (r0, c0), (r1, c1) = geo.cell_xy(a[0], a[1]), geo.cell_xy(b[0], b[1])
    dx, dy = abs(b[0] - a[0]), abs(b[1] - a[1])
    slope = float("inf") if dx < 1e-9 else dy / dx
    if slope < HORIZONTAL_SLOPE:
        ch = None                                               # 가로: `-` 나 `_` 는 셀마다
    elif slope > VERTICAL_SLOPE:
        ch = "|"
    else:
        ch = "\\" if (b[0] - a[0]) * (b[1] - a[1]) > 0 else "/"
    n = max(abs(r1 - r0), abs(c1 - c0))
    out = []
    for k in range(n + 1):
        t = k / n if n else 0.0
        r, c = int(round(r0 + (r1 - r0) * t)), int(round(c0 + (c1 - c0) * t))
        if ch is None:
            y = a[1] + (b[1] - a[1]) * t
            out.append(((r, c), "_" if (y - geo.y0) / geo.ch - r > 0.62 else "-"))
        else:
            out.append(((r, c), ch))
    return out


def curve_cells(e: Element, seg: Segmentation, geo: Geometry) -> Optional[Dict[Cell, str]]:
    """곡선 요소 → {셀: 글자}. 조각마다 중심선을 긋고, 조각 끝이 점 몸통 곁이면 그 점의 중심까지 잇는다.
    한 조각이라도 중심선으로 못 풀면 None (호출한 쪽이 솎기 방식으로 돌아간다)"""
    dots = [(d.cx + 0.5, d.cy + 0.5, (d.area / pi) ** 0.5) for d in seg.of("dot")]
    out: Dict[Cell, str] = {}
    for piece in components_of(e.pixels, geo.w):
        if len(piece) < 3:
            continue
        box = (min(i % geo.w for i in piece), min(i // geo.w for i in piece),
               max(i % geo.w for i in piece), max(i // geo.w for i in piece))
        short = max(box[2] - box[0] + 1, box[3] - box[1] + 1) < MIN_CURVE_CELLS * geo.cw
        line = centerline(piece, geo)
        if line is None:
            return None
        joined = attach_to_dots(line, dots)
        if short and not joined:
            continue                                  # 점에 닿지 않는 짧은 조각 = 눈금 막대
        if len(line) == 1:
            line = line * 2
        for a, b in zip(line, line[1:]):
            for cell, ch in segment_cells(a, b, geo):
                out[cell] = ch
    return out


def trend_cells(e: Element, geo: Geometry) -> Dict[Cell, str]:
    """추세선 요소 → {셀: 글자}. path 의 이웃한 점을 segment_cells 로 잇는다. 사이가 TREND_GAP 구간보다 멀면 잇지 않는다"""
    pts = e.path or []
    if len(pts) == 1:
        pts = pts * 2
    far = TREND_GAP * trend_bin(e.thickness)
    out: Dict[Cell, str] = {}
    for a, b in zip(pts, pts[1:]):
        if b[0] - a[0] > far:
            continue
        for cell, ch in segment_cells(a, b, geo):
            out[cell] = ch
    return out


def attach_to_dots(line: List[Tuple[float, float]], dots: Sequence[Tuple[float, float, float]]) -> int:
    """조각의 양 끝이 점 몸통 곁(DOT_REACH 안)이면 그 점의 중심을 끝에 덧붙인다. 붙인 끝의 수.
    한 점으로 짧은 조각의 두 끝이 다 붙지 않게, 두 끝은 서로 다른 점을 고른다"""
    def near(pt):
        return sorted((hypot(pt[0] - dx, pt[1] - dy) - r, dx, dy) for dx, dy, r in dots
                      if hypot(pt[0] - dx, pt[1] - dy) <= r + DOT_REACH)

    first, last = near(line[0]), near(line[-1])
    ends = []
    if first:
        ends.append((0, first[0]))
    if last:
        pick = next((c for c in last if not ends or c[1:] != ends[0][1][1:]), None)
        if pick is not None:
            ends.append((-1, pick))
    for where, (_, dx, dy) in sorted(ends, key=lambda t: t[0] != -1):      # 뒤쪽부터 붙여 인덱스가 밀리지 않게
        if where == 0:
            line.insert(0, (dx, dy))
        else:
            line.append((dx, dy))
    return len(ends)


def curve_glyph(kind: str, m: Moments, geo: Geometry, cell: Cell) -> str:
    if kind == "h":
        # 셀 안에서 칸의 평균 높이가 윗반이면 `-`, 아랫반이면 `_` — 낮게 깔린 선이 떠 보이지 않게
        cy = m.sy / m.n
        return "_" if (cy / geo.ch - cell[0]) > 0.62 else "-"
    return "|" if kind == "v" else kind


def assign_glyphs(seg: Segmentation) -> Dict[int, dict]:
    """군집마다 글자: 점은 개수가 많은 군집부터 POINT_SETS, 색 있는 선은 HLINE · VLINE_SETS, 중립 선은 `-` `|`"""
    dots = {c.index: seg.dots(c.index) for c in seg.clusters}
    having = sorted((k for k, n in dots.items() if n), key=lambda k: (-dots[k], k))
    glyphs: Dict[int, dict] = {c.index: {} for c in seg.clusters}
    for rank, k in enumerate(having):
        glyphs[k]["point"] = POINT_SETS[min(rank, len(POINT_SETS) - 1)]
    chroma = 0
    for c in seg.clusters:
        has_line = any(e.cluster == c.index and e.kind in ("hline", "vline") for e in seg.elements)
        if c.neutral:
            glyphs[c.index]["h"], glyphs[c.index]["v"] = "-", "|"
        elif has_line:
            glyphs[c.index]["h"] = HLINE_SETS[min(chroma, len(HLINE_SETS) - 1)]
            glyphs[c.index]["v"] = VLINE_SETS[min(chroma, len(VLINE_SETS) - 1)]
            chroma += 1
        else:
            glyphs[c.index]["h"], glyphs[c.index]["v"] = "-", "|"
    return glyphs


def line_cells(e: Element, geo: Geometry) -> List[Cell]:
    """가로선은 중심 한 줄, 세로선은 중심 한 열에만 (띠가 셀 경계에 걸쳐도 두 줄로 그리지 않는다)"""
    x0, y0, x1, y1 = e.bbox
    if e.kind == "hline":
        r = geo.cell_xy(0, e.cy + 0.5)[0]
        return [(r, c) for c in range(geo.cell_xy(x0, 0)[1], geo.cell_xy(x1 + 1, 0)[1] + 1)]
    c = geo.cell_xy(e.cx + 0.5, 0)[1]
    return [(r, c) for r in range(geo.cell_xy(0, y0)[0], geo.cell_xy(0, y1 + 1)[0] + 1)]


def snap_to_crossings(cells: List[Cell], hlines: Sequence[Element], geo: Geometry) -> List[Cell]:
    """세로선 끝이 가로선 바로 곁(한 셀 안)에서 멈췄으면 가로선까지 잇는다 — 깨끗한 그림에서는 가로선 띠가 세로선 끝을
    가져가 틀의 모서리가 한 칸씩 떨어진다"""
    if not cells:
        return cells
    col = cells[0][1]
    top, bottom = cells[0][0], cells[-1][0]
    out = list(cells)
    for h in hlines:
        row = geo.cell_xy(0, h.cy + 0.5)[0]
        c0, c1 = geo.cell_xy(h.bbox[0], 0)[1], geo.cell_xy(h.bbox[2] + 1, 0)[1]
        if not c0 - 1 <= col <= c1 + 1:
            continue
        if 1 <= top - row <= 1:
            out += [(r, col) for r in range(row, top)]
        elif 1 <= row - bottom <= 1:
            out += [(r, col) for r in range(bottom + 1, row + 1)]
    return out


def notch_cell(seg: Segmentation, geo: Geometry) -> Optional[Tuple[Cell, str]]:
    ring = seg.ring
    if ring is None or ring.notch is None:
        return None
    x, y = ring.cx + ring.r * cos(ring.notch * pi / 180), ring.cy + ring.r * sin(ring.notch * pi / 180)
    glyph = next(g for lim, g in NOTCH_GLYPHS if ring.notch % 360 < lim)
    return geo.cell_xy(x, y), glyph


def render(seg: Segmentation, width: int = DEFAULT_WIDTH, box: bool = False) -> str:
    """그림 → 글자 아트 + 범례. 격자 줄은 순수 ASCII (box 면 선 글자만 ─ │ ┼), 범례는 한국어"""
    width = max(MIN_WIDTH, min(MAX_WIDTH, width))
    geo = Geometry(seg, width)
    glyphs = assign_glyphs(seg)
    names = {c.index: c.name for c in seg.clusters}
    cells: Dict[Cell, Tuple[int, str]] = {}          # 셀 → (우선순위, 글자)

    def put(cell: Cell, prio: int, ch: str) -> None:
        if cell not in cells or cells[cell][0] < prio:
            cells[cell] = (prio, ch)

    # 외곽 · 곡선 (가장 낮음)
    for kind, prio in (("ring", 1), ("curve", 2)):
        for e in seg.of(kind):
            if kind == "curve":
                drawn = curve_cells(e, seg, geo)
                if drawn is not None:
                    for cell, ch in drawn.items():
                        put(cell, prio, ch)
                    continue
                if max(e.bbox[2] - e.bbox[0] + 1, e.bbox[3] - e.bbox[1] + 1) < MIN_CURVE_CELLS * geo.cw:
                    continue
            mom = path_cells(e.pixels, geo)
            kept = thin(mom, PATH_MIN_PIXELS[kind])
            for cell, d in kept.items():
                put(cell, prio, RING_GLYPH if kind == "ring" else curve_glyph(d, mom[cell], geo, cell))
            if kind == "ring" and seg.ring is not None:
                for cell in close_ring(list(kept), geo, seg.ring):
                    put(cell, prio, RING_GLYPH)
    for e in seg.of("trend"):                        # 추세선은 곡선과 같은 층
        for cell, ch in trend_cells(e, geo).items():
            put(cell, 2, ch)
    # 가로 · 세로 선 — 한 셀에 둘이 겹치면 `+`
    hv: Dict[Cell, set] = {}
    verticals = seg.of("vline")
    frame = None
    if len(verticals) >= 2:                          # 가장 바깥 세로선 둘이 틀 — 가로선은 틀 칸 안에서만
        cols = sorted(geo.cell_xy(e.cx + 0.5, 0)[1] for e in verticals)
        frame = (cols[0], cols[-1])
    hlines = seg.of("hline")
    for e in seg.elements:
        if e.kind in ("hline", "vline"):
            cells_ = line_cells(e, geo)
            if e.kind == "vline":
                cells_ = snap_to_crossings(cells_, hlines, geo)
            for cell in cells_:
                if frame is not None and e.kind == "hline" and not frame[0] <= cell[1] <= frame[1]:
                    continue
                hv.setdefault(cell, set()).add((e.kind, e.cluster))
    for cell, ks in hv.items():
        kinds = {k for k, _ in ks}
        if kinds == {"hline", "vline"}:
            put(cell, 3, "+")
        else:
            kind, cl = sorted(ks)[0]
            put(cell, 3, glyphs[cl]["h" if kind == "hline" else "v"])
    # 점 (가장 높음): 셀 안에서 개수가 많은 색이 이긴다
    dots = allocate_dots(seg, geo)
    for cell, per in dots.items():
        k = max(sorted(per), key=lambda k: per[k])
        cap = geo.cw * geo.ch / max(1.0, seg.unit.get(k, 4.0))
        put(cell, 4, glyphs[k]["point"][ladder(per[k], cap)])
    nc = notch_cell(seg, geo)
    if nc is not None:
        put(nc[0], 5, nc[1])
    # 자르기: 비어 있는 가장자리를 걷어 낸다
    if cells:
        r0, r1 = min(r for r, _ in cells), max(r for r, _ in cells)
        c0, c1 = min(c for _, c in cells), max(c for _, c in cells)
        rows = []
        for r in range(r0, r1 + 1):
            line = "".join((BOX.get(cells[(r, c)][1], cells[(r, c)][1]) if box else cells[(r, c)][1]) if (r, c) in cells else " "
                           for c in range(c0, c1 + 1))
            rows.append(line.rstrip())
        art = "\n".join(rows) + "\n"
        size = (max(len(x) for x in rows), len(rows))     # 범례에는 실제로 그린 격자의 크기 (잘라 낸 뒤)
    else:
        art = ""
        size = (geo.cols, geo.rows)
    return art + "\n" + "\n".join(legend(seg, size, glyphs, names, nc is not None, box)) + "\n"


def about(lo: int, hi: int) -> str:
    """개수 범위의 글: 100 이상이면 아래는 내림 · 위는 올림으로 유효 숫자 두 자리 (2047–2957 → 약 2000–3000개)"""
    def two(v: int, up: bool) -> int:
        if v < 100:
            return v
        p = 10 ** (len(str(v)) - 2)
        return -(-v // p) * p if up else v // p * p
    return "약 %d–%d개" % (two(lo, False), two(hi, True))


def legend(seg: Segmentation, size: Tuple[int, int], glyphs: Dict[int, dict], names: Dict[int, str], has_notch: bool,
           box: bool) -> List[str]:
    parts = []
    dense = {e.cluster for e in seg.of("field")}
    for c in seg.clusters:
        g = glyphs[c.index]
        n = seg.dots(c.index)
        if c.index in dense:
            parts.append("%s %s 점 %s (빽빽함 · 밀도로 그림)" % (" ".join(g["point"]), names[c.index], about(*seg.dots_range(c.index))))
        elif n:
            parts.append("%s %s 점 %d개" % (" ".join(g["point"]), names[c.index], n))
    for c in seg.clusters:
        kinds = {e.kind for e in seg.elements if e.cluster == c.index}
        shown = [glyphs[c.index][key] for key, kind in (("h", "hline"), ("v", "vline")) if kind in kinds]
        if shown:
            parts.append("%s %s 선" % (" ".join(BOX.get(g, g) if box else g for g in shown), names[c.index]))
    if seg.of("curve"):
        parts.append("_ - / \\ | 곡선")
    if seg.ring is not None:
        parts.append("%s 웨이퍼 외곽" % RING_GLYPH)
    if has_notch:
        parts.append("%s 노치" % next(g for lim, g in NOTCH_GLYPHS if seg.ring.notch % 360 < lim))
    lines = [" · ".join(parts) if parts else "그릴 것을 찾지 못했습니다"]
    foot = []
    if dense:
        foot.append("점은 추정 %s (빽빽한 곳은 겹침을 보정한 범위)" % about(*seg.dots_range()))
    elif seg.dots():
        foot.append("점은 추정 %d개 (뭉친 곳은 면적으로 센 값)" % seg.dots())
    texts = len(seg.of("text"))
    if texts:
        foot.append("글자 %d곳은 읽지 않고 비움" % texts)
    foot.append("그림 %d×%d → %d열 %d행" % (seg.width, seg.height, size[0], size[1]))
    lines.append(" · ".join(foot))
    return lines
