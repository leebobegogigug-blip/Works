# -*- coding: utf-8 -*-
"""ascii1_seg - 색 분류 · 연결요소 · 요소 분류. 설계서 docs/plans/ascii-1-design.md › ②③④

Image(RGB) → Segmentation: 바탕을 빼고, 색(군집)마다 따로 연결요소를 세어
가로선 · 세로선 · 원 외곽(웨이퍼) · 글자 · 점(개수 추정) · 곡선 으로 가른다. 모든 문턱은 [제안] 이라 모듈 위 상수로 둔다.
어떤 Image 를 줘도 예외 없이 끝난다 (전경이 없으면 요소가 빈 목록).
"""
import colorsys
from array import array
from collections import Counter
from dataclasses import dataclass, field
from math import atan2, cos, hypot, log, pi, sin, sqrt
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
PATH_SPAN = 0.4            # 선이 없을 때 곡선으로 보려면 그림의 긴 변의 이만큼은 가로질러야 (웨이퍼의 점 기둥은 0.2 안팎)
PATH_CONTINUOUS = 0.9     # …그리고 긴 축의 칸(열)들 중 이 비율 이상에 칸이 있어야 (끊긴 점 무리가 아니라 이어진 선)
PATH_QUANTILE = 0.2       # 선이 없을 때 곡선 두께 = 길쭉한 덩어리 칸들의 min(가로런, 세로런) 하위 20%
DISC_INSIDE = 0.9         # 원판: 상자에 내접한 타원 안의 칸 중 이 비율 이상이 차 있고
DISC_OUTSIDE = 0.3        # …타원 밖으로 나간 칸이 면적의 이 비율 이하
FRAME_SLACK = 1          # 틀(가장 바깥 세로선 둘) 밖으로 이만큼 넘어간 선 끝은 선이 아니라 라벨
# 격자 층 · 그림 상자 (설계서 14-5 · 14-7). 길이는 px
GRID_LIGHT = (25, 140)    # 바탕과의 RGB 거리가 이 사이(끝 제외)인 칸이 "연한 칸"
GRID_SAT = 0.35           # …그리고 채도가 이 아래
GRID_FRAC = 0.30          # 한 행(열)의 연한 칸이 폭(높이)의 이 비율 이상이면 격자 줄 후보
GRID_MAX_THICK = 4        # 이어진 후보 행(2 칸 틈까지 한 띠)이 이보다 두꺼우면 줄이 아니다
GRID_MIN_PITCH = 6        # 간격 중앙값이 이보다 작으면 격자가 아니다 (선의 번짐 띠)
GRID_GAP_TOL = 0.15       # 간격마다 k × 중앙값 ± 15% (k = 1 · 2 · 3 — 데이터에 가려 빠진 줄은 둘까지)
GRID_THICK_TOL = 1        # 띠 두께가 중앙값 ± 1 px 안이어야 같은 격자의 줄
GRID_MIN_LINES = (3, 6)   # 가로 · 세로 둘 다 3 줄 이상 등간격, 또는 한 방향만 6 줄 이상 등간격
GRID_SAME = 2             # 연한 격자와 같은 자리(± px)의 중립 선은 격자 줄이다
PLOT_MIN = 0.30           # 그림 상자가 그림 폭 · 높이의 이 비율보다 작으면 상자가 없는 것
PLOT_JOIN = 3             # L 자 축: 세로선 아래 끝 · 가로선 왼쪽 끝이 서로 이만큼(+ 가로선 두께) 안에서 만나야
PLOT_INSET = 2            # "상자 안" = 중심이 그림 상자에서 이만큼(px) 안쪽 — 틀 선 위의 조각은 안이 아니다
# 속 빈 원 표식 · 글자 제외 (설계서 14-8)
HOLLOW_MIN = 5            # 속 빈 표식: 경계상자 짧은 변 ≥ (px)
HOLLOW_ASPECT = 0.8       # …가로 ÷ 세로가 이 값 – 1 / 이 값 (정사각 ±20%)
HOLLOW_FILL = 0.6         # …채움률(면적 ÷ 상자) <
HOLLOW_CENTER = 0.25      # …둘러싸인 바탕(구멍)의 무게중심이 상자 중심에서 가로 · 세로 이 비율 안
HOLLOW_BINS = 12          # …중심 둘레를 이만큼(30°)으로 나눠
HOLLOW_COVER = 10         # …그중 이만큼 이상에 획이 있다
MARKER_REPEAT = 5         # 상자 안에 표식 외톨이가 이만큼 이상인 색 군집은 상자 안 덩어리를 글자 후보에서 뺀다
# 추세선 (설계서 14-10). 길이는 px, t = 군집 칸의 세로 연속 길이의 중앙값
TREND_BIN = (8, 2.0)      # 구간 폭 B = max(8, 2 × t)
TREND_GAP = 4             # 칸이 있는 이웃 구간의 번호 차가 이 이하면 한 줄로 잇는다 — 가장 긴 줄만 쓴다
TREND_BAND = (8, 3.0)     # 좁은 구간 = 띠(TREND_SPLIT 넘는 틈으로 나눔) 중 칸 2 개 이상인 것이 하나이고 높이 ≤ max(8, 3t) + B
TREND_SPLIT = 2           # 한 구간 안에서 이 행 수보다 넓게 빈 곳이 띠를 나눈다
TREND_SPAN = 0.40         # 줄의 가로 길이 ≥ 상자 폭의 이 비율
TREND_FILL = 0.90         # 줄 안의 구간 중 칸이 있는 것 ≥ 이 비율
TREND_NARROW = 0.80       # 줄 안의 구간 중 좁은 것 ≥ 이 비율
MARKER_MIN = (2.0, 2.0)   # 쪼갠 마커의 몸통 지름 중앙값이 선 두께의 2 배 + 2 px 보다 작으면 마커가 아니라 선 조각
# 빽빽한 산점 · 개수 범위 (설계서 14-9). 문턱은 개수 · 비율 · 낱점 지름의 배수 · 그림 짧은 변의 비율 — px 고정은 바닥값뿐 (크기 불변)
POISSON_CELL = 3          # 겹침 보정 칸 한 변 = 낱점 지름의 이 배수
POISSON_CAP = 0.9         # 칸의 덮음 비율을 이 값에서 자른다 (꽉 찬 칸이 무한대가 되지 않게)
DENSE_MIN_N = 500         # 빽빽: 겹침 보정 개수 ≥
DENSE_BIG_UNIT = 3        # …낱점 면적의 이 배수보다 큰 덩어리에 든 질량의 몫이
DENSE_BIG = 0.5           # …이 값 이상
DENSE_ISO_SHARE = 0.01    # …그리고 낱점 면적을 잰 외톨이(typical_areas)가 추정 개수의 이 비율 이상 — 번짐 잡티 몇 개로 잰 낱점 면적이
                          #    선 조각 질량을 수천 개로 부풀리지 않게 (실제 빽빽한 산점 3.6% 이상 · 부드럽게 키운 그림의 빨강 추세선 0.2%)
DENSE_PATH_BIN = 8        # 곡선 빼기: 긴 축을 이 폭(px) 구간으로 나눠 짧은 축으로 퍼진 폭을 잰다
DENSE_PATH_SPREAD = (8, 0.08)   # …퍼짐 중앙값 ≤ max(8 px, 0.08 × 그림 짧은 변) 이면 곡선 (큰 덩어리 몫에서 뺀다)
RANGE_Q = (0.25, 0.75)    # 개수 범위: 외톨이 면적의 이 분위수로 다시 센 값 (큰 면적 → 아래)
RANGE_MIN = 0.10          # …범위는 적어도 가운데의 ±이 비율
FIELD_COLS = 300          # 밀도 지도 블록 한 변 = max(1, 상자 폭 // 이 값) — 렌더의 가장 넓은 열 수 (MAX_WIDTH)

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
class DensityMap:                  # kind "field" 의 본체. 칸 목록을 들지 않는다 (메모리)
    x0: int                        # 지도의 왼쪽 위 (px) — 그림 상자의 왼쪽 위
    y0: int
    block: int                     # 블록 한 변 (px) = max(1, 상자 폭 // FIELD_COLS)
    cols: int
    rows: int
    mass: "array"                  # typecode "I", 길이 cols * rows, 행 우선. 블록마다 그 군집의 칸 수 (px²)
    unit: float                    # 낱점 면적 (px²)
    diameter: float                # 낱점 지름 = 외톨이 경계상자 긴 변의 중앙값 (px)
    count: int                     # 추정 개수의 가운데 값 (개) — Element.count 와 같다
    count_lo: int                  # 범위 아래 (개)
    count_hi: int                  # 범위 위 (개)
    cell: int = 0                  # 겹침 보정 칸 한 변 (px) = round(POISSON_CELL × diameter)


@dataclass
class Element:
    kind: str                      # hline vline ring text dot curve trend field
    cluster: int
    bbox: Tuple[int, int, int, int]  # x0 y0 x1 y1 (끝 포함)
    area: int                      # field 는 질량 합 (px²)
    pixels: List[int]              # 그림 위 칸 번호 y * width + x. field 는 빈 목록 (칸은 density.mass 에)
    cx: float = 0.0
    cy: float = 0.0
    count: int = 1                 # dot · field 의 추정 개수 (추정치다). trend 는 0
    thickness: float = 0.0         # hline · vline · trend 의 두께 (px)
    path: Optional[List[Tuple[float, float]]] = None   # trend: x 순 구간 중심점 (px, 칸 중심은 +0.5)
    density: Optional[DensityMap] = None               # field: 블록별 질량 지도 · 낱점 면적 · 개수 범위


@dataclass
class Ring:
    cx: float
    cy: float
    r: float
    closed: float                  # 둘레 5° 칸 중 외곽이 있는 비율 (1.0 = 닫힘)
    notch: Optional[float]         # 노치 방향(도, 3시=0 · 아래쪽이 90). 없으면 None


@dataclass
class GridLine:
    pos: float                     # 줄의 중심 (px). 가로줄이면 y, 세로줄이면 x
    lo: int                        # 띠의 첫 행(가로줄) 또는 첫 열(세로줄) (px, 끝 포함)
    hi: int                        # 띠의 끝 행 · 열 (px, 끝 포함). 두께 = hi - lo + 1
    start: int                     # 줄이 놓인 구간의 시작 — 가로줄이면 x, 세로줄이면 y (px)
    end: int                       # …끝 (px, 끝 포함)
    rgb: Tuple[int, int, int]      # 띠 칸의 평균색


@dataclass
class Grid:
    horizontal: List[GridLine]     # y 순
    vertical: List[GridLine]       # x 순
    pitch_h: float                 # 가로줄 간격의 중앙값 (px). 가로줄이 없으면 0.0
    pitch_v: float                 # 세로줄 간격의 중앙값 (px). 없으면 0.0
    source: str                    # "light" (연한 칸 투영) · "lines" (진한 회색 — find_lines 결과)
    removed: int = 0               # 데이터 군집에서 뺀 격자 칸 수 (측정 도구 · 시험용)


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
    grid: Optional[Grid] = None    # 격자 (줄은 elements 에 넣지 않는다 — hline · vline 으로 세지 않게). 없으면 None
    plot_box: Optional[Tuple[int, int, int, int]] = None   # 그림 상자 x0 y0 x1 y1 (px, 끝 포함). 정할 수 없으면 None
    plot_source: str = ""          # "grid" · "frame" · "axes" · ""

    def of(self, kind: str) -> List[Element]:
        return [e for e in self.elements if e.kind == kind]

    def dots(self, cluster: Optional[int] = None) -> int:
        """점의 추정 개수 — dot 과 field(가운데 값)의 count 를 더한다"""
        return sum(e.count for e in self.elements if e.kind in ("dot", "field") and cluster in (None, e.cluster))

    def dots_range(self, cluster: Optional[int] = None) -> Tuple[int, int]:
        """점의 추정 범위 — dot 합에 field 의 범위 아래 · 위를 더한다 (field 가 없으면 (n, n))"""
        n = sum(e.count for e in self.elements if e.kind == "dot" and cluster in (None, e.cluster))
        fs = [e.density for e in self.elements if e.kind == "field" and cluster in (None, e.cluster)]
        return n + sum(d.count_lo for d in fs), n + sum(d.count_hi for d in fs)

    def guess_kind(self) -> str:
        if self.ring is not None:
            return "wafer"
        if self.of("hline") or self.of("vline") or self.grid is not None or self.plot_box is not None:
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
    """네 가장자리의 최빈색. 다만 그림 전체의 최빈색을 바탕으로 칠 때 전경(바탕과 먼 칸)이 더 적으면 그쪽 —
    가장자리를 두른 테두리(내보낸 차트의 틀)가 바탕으로 뽑히면 그림 전체가 전경이 된다"""
    w, h, rgb = img.width, img.height, img.rgb
    cells = list(range(w)) + list(range((h - 1) * w, h * w)) + list(range(0, h * w, w)) + list(range(w - 1, h * w, w))
    edge = Counter(tuple(rgb[3 * i:3 * i + 3]) for i in cells).most_common(1)[0][0]
    cols = Counter(zip(rgb[0::3], rgb[1::3], rgb[2::3]))
    common = cols.most_common(1)[0][0]
    if common == edge:
        return edge

    def far(bg) -> int:
        return sum(n for c, n in cols.items()
                   if (c[0] - bg[0]) ** 2 + (c[1] - bg[1]) ** 2 + (c[2] - bg[2]) ** 2 > FG_DIST * FG_DIST)
    return common if far(common) < far(edge) else edge


def light_colors(cols, bg) -> Set[Tuple[int, int, int]]:
    """연한 칸의 색: 바탕과의 거리가 GRID_LIGHT 사이이고 채도가 GRID_SAT 아래 (격자 후보)"""
    lo2, hi2 = GRID_LIGHT[0] ** 2, GRID_LIGHT[1] ** 2
    out = set()
    for c in cols:
        d2 = (c[0] - bg[0]) ** 2 + (c[1] - bg[1]) ** 2 + (c[2] - bg[2]) ** 2
        if lo2 < d2 < hi2 and colorsys.rgb_to_hsv(c[0] / 255, c[1] / 255, c[2] / 255)[1] < GRID_SAT:
            out.add(c)
    return out


def classify(img, bg) -> Tuple[bytearray, List[Cluster], Optional[Grid]]:
    """칸마다 군집 번호(0 = 바탕)를 붙인다. 군집은 면적이 큰 순서.
    같은 칸 루프에서 연한 칸도 표시해 격자를 판정한다 (find_grid). 격자가 있으면 격자 칸을 가장자리 흡수 전에 바탕으로 두고,
    흡수는 패스마다 스냅숏을 보고 한다 — 표식에 닿은 칸에서 스캔 순서로 번지지 않게 (설계서 14-6). 격자가 없으면 지금 그대로"""
    w, h, rgb = img.width, img.height, img.rgb
    cols = Counter(zip(rgb[0::3], rgb[1::3], rgb[2::3]))
    pale = light_colors(cols, bg)
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
    # 색 → 짝 번호 (임시 번호 + 1, 연한 칸인가). 칸 루프 한 번으로 두 표시를 만들고 translate 로 나눈다
    pairs: Dict[Tuple[int, bool], int] = {}
    key = {c: pairs.setdefault((v + 1 if v >= 0 else 0, c in pale), len(pairs)) for c, v in lut.items()}
    to_raw, to_light = bytearray(256), bytearray(256)
    for (v, lt), b in pairs.items():
        to_raw[b], to_light[b] = v, lt
    codes = bytes(map(key.__getitem__, zip(rgb[0::3], rgb[1::3], rgb[2::3])))
    raw = bytearray(codes.translate(to_raw))     # 중립 1 · 유채색 군집 2.. · 가장자리 100 + (닿을 군집 번호) · 옅은 중립 250
    light = codes.translate(to_light)
    grid = find_grid(img, bg, light)
    if grid is not None:
        grid.removed = clear_grid(raw, light, grid, w, h)
    # 가장자리(옅은 번짐)는 같은 군집의 진한 칸과 닿아 있으면 그 군집으로, 아니면 중립으로
    fringe = [i for i, v in enumerate(raw) if 100 < v < 250]     # 250(옅은 중립)은 아래에서 따로
    for _ in range(2):
        left = []
        snap = raw if grid is None else bytes(raw)
        for i in fringe:
            want = raw[i] - 100
            x = i % w
            hit = False
            for j in _neighbors(i, x, w, h):
                if snap[j] == want:
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
    return bytearray(remap[v] for v in raw), clusters, grid


def _neighbors(i: int, x: int, w: int, h: int):
    out = []
    n = w * h
    for dy in (-w, 0, w):
        for dx in (-1, 0, 1):
            if (dy or dx) and 0 <= i + dy + dx < n and 0 <= x + dx < w:
                out.append(i + dy + dx)
    return out


# ─────────────────────────────────────────────────────────────── 격자 층 · 그림 상자 (설계서 14-5 · 14-7)

def regular_lines(lines: Sequence[Tuple[float, float]]) -> Tuple[List[int], float]:
    """(중심, 두께) 목록(중심 순) → 등간격 격자줄로 볼 것들의 번호와 간격 중앙값. 격자가 아니면 ([], 0.0).
    두꺼운 띠와 두께가 중앙값에서 먼 띠는 먼저 빼고, 남은 줄의 간격이 모두 중앙값의 1 · 2 · 3 배 ± GRID_GAP_TOL 이어야 한다"""
    keep = [n for n, (_, t) in enumerate(lines) if t <= GRID_MAX_THICK]
    if not keep:
        return [], 0.0
    tm = median([lines[n][1] for n in keep])
    keep = [n for n in keep if abs(lines[n][1] - tm) <= GRID_THICK_TOL]
    if len(keep) < GRID_MIN_LINES[0]:
        return [], 0.0
    cs = [lines[n][0] for n in keep]
    gaps = [b - a for a, b in zip(cs, cs[1:])]
    g = sorted(gaps)[len(gaps) // 2]
    if g < GRID_MIN_PITCH:
        return [], 0.0
    if not all(any(abs(d - k * g) <= GRID_GAP_TOL * k * g for k in (1, 2, 3)) for d in gaps):
        return [], 0.0
    return keep, float(g)


def pick_grid(nh: int, nv: int) -> Tuple[bool, bool]:
    """등간격 가로 nh · 세로 nv 줄 → (가로를 격자로, 세로를 격자로). 둘 다 3 줄 이상이거나 한 방향만 6 줄 이상"""
    if nh >= GRID_MIN_LINES[0] and nv >= GRID_MIN_LINES[0]:
        return True, True
    return nh >= GRID_MIN_LINES[1], nv >= GRID_MIN_LINES[1]


def light_mask(img, bg) -> bytes:
    """칸마다 연한 칸이면 1 (classify 가 같은 루프에서 만드는 표시를 따로 만들 때)"""
    rgb = img.rgb
    pale = light_colors(set(zip(rgb[0::3], rgb[1::3], rgb[2::3])), bg)
    return bytes(map(lambda c: c in pale, zip(rgb[0::3], rgb[1::3], rgb[2::3])))


def find_grid(img, bg, light: Optional[bytes] = None) -> Optional[Grid]:
    """연한 격자: 연한 칸(light, 칸마다 0 · 1)을 행 · 열로 투영해 GRID_FRAC 이상인 행(열)을 띠로 묶고, 등간격이면 격자 (source "light").
    light 를 주지 않으면 그림에서 만든다. 투영은 bytes.count 로 C 속도"""
    w, h = img.width, img.height
    if light is None:
        light = light_mask(img, bg)
    if not w or not h:
        return None
    rows = [y for y in range(h) if light.count(1, y * w, (y + 1) * w) >= GRID_FRAC * w]
    cols = [x for x in range(w) if light[x::w].count(1) >= GRID_FRAC * h]
    axes = []
    for vals in (rows, cols):
        bands: List[List[int]] = []
        for v in vals:
            if bands and v - bands[-1][1] <= 2:
                bands[-1][1] = v
            else:
                bands.append([v, v])
        keep, pitch = regular_lines([((lo + hi) / 2, hi - lo + 1) for lo, hi in bands])
        axes.append(([bands[n] for n in keep], pitch))
    use_h, use_v = pick_grid(len(axes[0][0]), len(axes[1][0]))
    if not (use_h or use_v):
        return None
    rgb = img.rgb
    out: List[List[GridLine]] = [[], []]
    for horizontal, use, (bands, _) in ((True, use_h, axes[0]), (False, use_v, axes[1])):
        if not use:
            continue
        for lo, hi in bands:
            cells = []
            for r in range(lo, hi + 1):
                if horizontal:
                    cells += [r * w + x for x in range(w) if light[r * w + x]]
                else:
                    cells += [y * w + r for y in range(h) if light[y * w + r]]
            along = [(i % w) if horizontal else (i // w) for i in cells]
            mean = tuple(int(sum(rgb[3 * i + k] for i in cells) / len(cells)) for k in range(3))
            out[0 if horizontal else 1].append(GridLine((lo + hi) / 2, lo, hi, min(along), max(along), mean))
    return Grid(out[0], out[1], axes[0][1] if use_h else 0.0, axes[1][1] if use_v else 0.0, "light")


def clear_grid(raw: bytearray, light: bytes, grid: Grid, w: int, h: int) -> int:
    """격자 띠 ±1 줄 안(줄이 놓인 구간 ±1)의 연한 칸을 바탕(0)으로 → 데이터 군집에서 뺀 칸 수.
    연한 칸이 아닌 칸(표식과 격자가 만나는 진한 칸)은 띠 위에 있어도 그대로 둔다"""
    removed = 0
    for horizontal, lines in ((True, grid.horizontal), (False, grid.vertical)):
        for ln in lines:
            for r in range(max(0, ln.lo - 1), min(h if horizontal else w, ln.hi + 2)):
                for a in range(max(0, ln.start - 1), min(w if horizontal else h, ln.end + 2)):
                    i = r * w + a if horizontal else a * w + r
                    if light[i] and raw[i]:
                        raw[i] = 0
                        removed += 1
    return removed


def grid_from_lines(hl: List[Element], vl: List[Element], clusters: List[Cluster], grid: Optional[Grid]):
    """진한 격자 (source "lines"): 중립 군집마다 그 군집의 가로선 · 세로선 중심에 연한 격자와 같은 등간격 판정을 하고,
    맞으면 그 선들을 hl · vl 에서 떼어 격자로 옮긴다. 연한 격자가 이미 있으면 그 줄과 같은 자리(± GRID_SAME)의 중립 선과,
    바깥 줄에서 한 간격 밖(연한 바깥 줄을 진한 틀이 덮은 자리)의 중립 선만 떼고, 뒤의 것은 격자 줄로 더한다.
    → (hl, vl, grid, 뗀 선 목록)"""
    neutral = {c.index for c in clusters if c.neutral}
    taken: List[Element] = []
    if grid is not None:
        for e in hl + vl:
            horizontal = e.kind == "hline"
            lines, pitch = (grid.horizontal, grid.pitch_h) if horizontal else (grid.vertical, grid.pitch_v)
            if e.cluster not in neutral or not lines:
                continue
            pos = e.cy if horizontal else e.cx
            spots = [ln.pos for ln in lines] + [lines[0].pos - pitch, lines[-1].pos + pitch]   # 바깥 줄을 덮은 진한 틀 자리까지
            if any(abs(p - pos) <= GRID_SAME for p in spots):
                taken.append(e)
                grid.removed += e.area
                if not any(abs(ln.pos - pos) <= GRID_SAME for ln in lines):
                    b = e.bbox
                    ln = GridLine(pos, b[1], b[3], b[0], b[2], clusters[e.cluster - 1].rgb) if horizontal else \
                        GridLine(pos, b[0], b[2], b[1], b[3], clusters[e.cluster - 1].rgb)
                    lines.append(ln)
                    lines.sort(key=lambda g: g.pos)
    else:
        for k in sorted(neutral):
            hs = sorted((e for e in hl if e.cluster == k), key=lambda e: e.cy)
            vs = sorted((e for e in vl if e.cluster == k), key=lambda e: e.cx)
            hk, ph = regular_lines([(e.cy, e.thickness) for e in hs])
            vk, pv = regular_lines([(e.cx, e.thickness) for e in vs])
            use_h, use_v = pick_grid(len(hk), len(vk))
            if not (use_h or use_v):
                continue
            rgb = clusters[k - 1].rgb
            gh = [hs[n] for n in hk] if use_h else []
            gv = [vs[n] for n in vk] if use_v else []
            grid = Grid([GridLine(e.cy, e.bbox[1], e.bbox[3], e.bbox[0], e.bbox[2], rgb) for e in gh],
                        [GridLine(e.cx, e.bbox[0], e.bbox[2], e.bbox[1], e.bbox[3], rgb) for e in gv],
                        ph if use_h else 0.0, pv if use_v else 0.0, "lines", sum(e.area for e in gh + gv))
            taken = gh + gv
            break
    if not taken:
        return hl, vl, grid, []
    gone = {id(e) for e in taken}
    return [e for e in hl if id(e) not in gone], [e for e in vl if id(e) not in gone], grid, taken


def find_plot_box(seg: "Segmentation") -> Tuple[Optional[Tuple[int, int, int, int]], str]:
    """그림 상자 → (x0 y0 x1 y1, 근거). 격자 바깥 줄 → 가장 바깥 세로선 둘 · 가로선 둘 (틀) → L 자로 만나는 세로선 · 가로선 (축).
    그림 폭 · 높이의 PLOT_MIN 보다 작으면 없음"""
    g, hl, vl = seg.grid, seg.of("hline"), seg.of("vline")
    box, source = None, ""
    if g is not None:
        span_h = (min(ln.start for ln in g.horizontal), max(ln.end for ln in g.horizontal)) if g.horizontal else None
        span_v = (min(ln.start for ln in g.vertical), max(ln.end for ln in g.vertical)) if g.vertical else None
        xs = (g.vertical[0].pos, g.vertical[-1].pos) if g.vertical else span_h
        ys = (g.horizontal[0].pos, g.horizontal[-1].pos) if g.horizontal else span_v
        box, source = (xs[0], ys[0], xs[1], ys[1]), "grid"
    elif len(vl) >= 2 and len(hl) >= 2:
        xs = sorted(e.cx for e in vl)
        ys = sorted(e.cy for e in hl)
        box, source = (xs[0], ys[0], xs[-1], ys[-1]), "frame"
    elif vl and hl:
        v = min(vl, key=lambda e: e.cx)
        joins = [e for e in hl if abs(v.bbox[3] - e.cy) <= PLOT_JOIN + e.thickness
                 and abs(e.bbox[0] - v.cx) <= PLOT_JOIN + v.thickness]
        if joins:
            a = max(joins, key=lambda e: e.cy)
            box, source = (v.cx, v.bbox[1], a.bbox[2], a.cy), "axes"
    if box is None:
        return None, ""
    x0, y0, x1, y1 = (int(b + 0.5) for b in box)
    if x1 - x0 + 1 < PLOT_MIN * seg.width or y1 - y0 + 1 < PLOT_MIN * seg.height:
        return None, ""
    return (x0, y0, x1, y1), source


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


def is_disc(pix: Sequence[int], box: Tuple[int, int, int, int], w: int) -> bool:
    """칸으로 그린 원판(마커)인가 — 반지름이 정수인 원판은 채움률이 0.52–0.68 이라 is_round 의 0.70 에 못 미친다.
    상자에 내접한 타원 안이 거의 다 차 있고 타원 밖으로 나간 칸이 적으면 원판이다 (속이 빈 글자 · 네모와 가른다)"""
    bw, bh = box[2] - box[0] + 1, box[3] - box[1] + 1
    if min(bw, bh) < 3 or not 0.7 <= bw / bh <= 1.43:
        return False
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    ax, ay = (bw - 1) / 2, (bh - 1) / 2
    cells = set(pix)
    inside = hit = 0
    for y in range(box[1], box[3] + 1):
        for x in range(box[0], box[2] + 1):
            if ((x - cx) / ax) ** 2 + ((y - cy) / ay) ** 2 <= 1.0:
                inside += 1
                hit += y * w + x in cells
    return hit >= DISC_INSIDE * inside and len(pix) - hit <= DISC_OUTSIDE * len(pix)


def is_hollow(pix: Sequence[int], box: Tuple[int, int, int, int], w: int) -> bool:
    """속 빈 원(고리) 표식인가 — 정사각에 가깝고(±20%) · 채움률이 낮고 · 가운데에 둘러싸인 바탕(구멍)이 있고 ·
    획이 중심 둘레를 거의 다 돈다. 구멍은 상자를 한 칸 넓혀 바깥에서 4방향으로 바탕을 채웠을 때 닿지 않은 바탕 칸이다"""
    x0, y0, x1, y1 = box
    bw, bh = x1 - x0 + 1, y1 - y0 + 1
    if min(bw, bh) < HOLLOW_MIN or not HOLLOW_ASPECT <= bw / bh <= 1 / HOLLOW_ASPECT \
            or len(pix) >= HOLLOW_FILL * bw * bh:
        return False
    sw, sh = bw + 2, bh + 2
    seen = bytearray(sw * sh)                     # 1 = 획 또는 바깥에서 닿은 바탕
    for i in pix:
        seen[(i // w - y0 + 1) * sw + (i % w - x0 + 1)] = 1
    seen[0] = 1
    stack = [0]
    while stack:
        k = stack.pop()
        x = k % sw
        for j in (k - 1 if x else -1, k + 1 if x < sw - 1 else -1, k - sw, k + sw):
            if 0 <= j < sw * sh and not seen[j]:
                seen[j] = 1
                stack.append(j)
    hole = [k for k in range(sw * sh) if not seen[k]]
    if not hole:
        return False
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    hx = sum(k % sw for k in hole) / len(hole) - 1 + x0
    hy = sum(k // sw for k in hole) / len(hole) - 1 + y0
    if abs(hx - cx) > HOLLOW_CENTER * bw or abs(hy - cy) > HOLLOW_CENTER * bh:
        return False
    step = 360 / HOLLOW_BINS
    bins = {int(((atan2(i // w - cy, i % w - cx) * 180 / pi) % 360) // step) for i in pix}
    return len(bins) >= HOLLOW_COVER


def marker_clusters(comps, clusters: List[Cluster], plot_box, ring, w: int, h: int) -> Set[int]:
    """그림 상자 안에서 표식이 되풀이되는 색 군집 — 상자 안 외톨이(원판 · 둥근 덩어리 · 속 빈 원, 면적 ≥ 4,
    긴 변 ≤ 그림 긴 변의 10%)가 MARKER_REPEAT 개 이상. 상자가 없거나 링이 있으면 없음 (설계서 14-8)"""
    if plot_box is None or ring is not None:
        return set()
    seen: Counter = Counter()
    for k, pix, box in comps:
        if clusters[k - 1].neutral or seen[k] >= MARKER_REPEAT or not in_plot(plot_box, box):
            continue
        bw, bh = box[2] - box[0] + 1, box[3] - box[1] + 1
        if len(pix) >= 4 and max(bw, bh) <= 0.1 * max(w, h) \
                and (is_round(bw, bh, len(pix)) or is_disc(pix, box, w) or is_hollow(pix, box, w)):
            seen[k] += 1
    return {k for k, n in seen.items() if n >= MARKER_REPEAT}


def in_plot(plot_box, box) -> bool:
    """덩어리 상자의 중심이 그림 상자에서 PLOT_INSET 안쪽에 있는가"""
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return plot_box[0] + PLOT_INSET < cx < plot_box[2] - PLOT_INSET and plot_box[1] + PLOT_INSET < cy < plot_box[3] - PLOT_INSET


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
    pixels = list(stroke)
    if notch is not None:        # 안쪽 칸은 노치 둘레(±15°)만 외곽의 일부다 — 나머지는 JPEG 가 남긴 잔상
        pixels += [i for b in dent for i in dent[b] if abs((polar(i)[1] - notch + 180) % 360 - 180) <= 15]
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
    """굵은 곡선에 붙은 마커를 거리 변환으로 떼어 낸다 → ([(중심 x, 중심 y, 몸통 칸, 코어 면적)], 곡선 칸) 또는 None.
    몸통은 코어 중심에서 reach 안의 칸이다 — 덩어리 전체가 아니라 중심 둘레 상자 안의 칸만 보고(같은 hypot 판정),
    덩어리 안의 순서(pix 순서)대로 늘어놓는다"""
    box = bbox_of(pix, w)
    dist = distance_map(pix, w, box)
    cut = int(round(rc * CHAMFER))
    core = [i for i, d in dist.items() if d >= cut]
    if not core:
        return None
    order = {i: n for n, i in enumerate(pix)}       # 칸 → 덩어리 안의 순서
    marks = []
    body: Set[int] = set()
    for cp in components_of(core, w):
        cx, cy = sum(i % w for i in cp) / len(cp), sum(i // w for i in cp) / len(cp)
        reach = max(dist[i] for i in cp) / CHAMFER + 0.5
        # hypot ≥ |dx| · |dy| 이므로 상자 밖 칸은 판정을 통과할 수 없다 (상자는 1칸씩 넉넉히)
        xa, xb = max(box[0], int(cx - reach) - 1), min(box[2], int(cx + reach) + 1)
        ya, yb = max(box[1], int(cy - reach) - 1), min(box[3], int(cy + reach) + 1)
        hits = []
        for y in range(ya, yb + 1):
            for x in range(xa, xb + 1):
                n = order.get(y * w + x)
                if n is not None and hypot(x - cx, y - cy) <= reach:
                    hits.append(n)
        hits.sort()
        mb = [pix[n] for n in hits]
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


def is_path(pix: Sequence[int], box: Tuple[int, int, int, int], w: int, h: int) -> bool:
    """그림을 가로지르는 이어진 선(곡선)처럼 보이는 덩어리인가 — 점이 사슬처럼 이어진 무리와 가른다"""
    bw, bh = box[2] - box[0] + 1, box[3] - box[1] + 1
    long_side = max(bw, bh)
    if long_side < PATH_SPAN * max(w, h) or len(pix) / (bw * bh) > 0.45:
        return False
    along = (lambda i: i % w) if bw >= bh else (lambda i: i // w)
    lo = box[0] if bw >= bh else box[1]
    return len({along(i) - lo for i in pix}) >= PATH_CONTINUOUS * long_side


def path_thickness(pix: Sequence[int], w: int) -> float:
    """곡선 덩어리의 두께 — 칸마다 min(가로로 이어진 길이, 세로로 이어진 길이) 를 재서 하위 20% 값.
    곡선 칸이 마커 칸(둘레가 굵다)보다 적어도 5분의 1은 되어야 맞는다"""
    cells = set(pix)
    hrun: Dict[int, int] = {}
    vrun: Dict[int, int] = {}
    for i in pix:
        if i in hrun:
            continue
        a = i
        while a - 1 in cells and (a - 1) % w != w - 1:
            a -= 1
        b = i
        while b + 1 in cells and (b + 1) % w != 0:
            b += 1
        for j in range(a, b + 1):
            hrun[j] = b - a + 1
    for i in pix:
        if i in vrun:
            continue
        a = i
        while a - w in cells:
            a -= w
        b = i
        while b + w in cells:
            b += w
        for j in range(a, b + 1, w):
            vrun[j] = (b - a) // w + 1
    vals = sorted(min(hrun[i], vrun[i]) for i in pix)
    return float(vals[int(PATH_QUANTILE * (len(vals) - 1))])


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


# ─────────────────────────────────────────────────────────────── 추세선 (설계서 14-10)

def trend_bin(t: float) -> int:
    """두께 t 의 추세선을 나누는 구간 폭 B (px)"""
    return int(max(TREND_BIN[0], TREND_BIN[1] * t))


def trend_stats(pix: Sequence[int], box: Tuple[int, int, int, int], w: int) -> dict:
    """상자 안 한 군집의 칸 → 추세선 판정 값: 두께 t · 구간 폭 B · 줄의 길이 비율 span · 채움 fill · 좁은 구간 비율 narrow ·
    path (좁은 구간마다 구간 중심 x · 띠 중심 y, 칸 중심은 +0.5). 칸을 x 구간으로 나눠 구간마다 세로 띠가 하나로 좁게 몰렸는지 본다"""
    cells = set(pix)
    runs = []
    for i in pix:
        if i - w in cells:
            continue
        j = i
        while j + w in cells:
            j += w
        runs.append((j - i) // w + 1)
    t = median(runs)
    b = trend_bin(t)
    lim = max(TREND_BAND[0], TREND_BAND[1] * t) + b         # 기울기 몫으로 B 를 더한다
    bins: Dict[int, List[int]] = {}
    for i in pix:
        bins.setdefault((i % w - box[0]) // b, []).append(i // w)
    keys = sorted(bins)
    lines = [[keys[0]]]
    for q in keys[1:]:
        if q - lines[-1][-1] <= TREND_GAP:
            lines[-1].append(q)
        else:
            lines.append([q])
    line = max(lines, key=len)
    path = []
    for q in line:
        ys = sorted(bins[q])
        bands = [[ys[0], ys[0], 1]]
        for y in ys[1:]:
            if y - bands[-1][1] <= TREND_SPLIT:
                bands[-1][1] = y
                bands[-1][2] += 1
            else:
                bands.append([y, y, 1])
        main = [bd for bd in bands if bd[2] >= 2]
        if len(main) == 1 and main[0][1] - main[0][0] + 1 <= lim:
            path.append((box[0] + q * b + b / 2, (main[0][0] + main[0][1] + 1) / 2))
    reach = line[-1] - line[0] + 1
    return {"t": t, "B": b, "span": reach * b / (box[2] - box[0] + 1), "fill": len(line) / reach,
            "narrow": len(path) / len(line), "path": path}


def find_trend(pix: Sequence[int], box: Tuple[int, int, int, int], w: int) -> Optional[Tuple[List[Tuple[float, float]], float]]:
    """상자 안 한 군집의 칸이 추세선 하나면 (path, 두께 t), 아니면 None — 길이 · 채움 · 좁은 구간 세 비율이 모두 문턱 이상"""
    if not pix:
        return None
    st = trend_stats(pix, box, w)
    if st["span"] >= TREND_SPAN and st["fill"] >= TREND_FILL and st["narrow"] >= TREND_NARROW:
        return st["path"], float(st["t"])
    return None


def marker_diameter(marks) -> float:
    """split_markers 가 쪼갠 마커들의 몸통 지름(같은 면적의 원) 중앙값 (px)"""
    return median([2 * sqrt(len(m[2]) / pi) for m in marks])


def split_own(pix: List[int], box: Tuple[int, int, int, int], w: int, h: int, rc: float):
    """split_markers(pix, w, rc). 곡선 덩어리인데 쪼갠 "마커" 의 지름이 선 조각만 하면(2 × 덩어리 두께 + 2 px 미만)
    덩어리 자신의 두께로 다시 가른다 — 대개 None (마커 없음 → 곡선). 늘 다시 가르면 골든 관리도가 한 글자 달라진다"""
    res = split_markers(pix, w, rc)
    if res is not None and is_path(pix, box, w, h):
        t_own = path_thickness(pix, w)
        if marker_diameter(res[0]) < MARKER_MIN[0] * t_own + MARKER_MIN[1]:
            res = split_markers(pix, w, max(rc, t_own + 1.0))
    return res


def marker_curve(pix: Sequence[int], w: int, h: int, line_thickness: Optional[float]) -> bool:
    """마커가 붙은 곡선인가 — 가장 큰 덩어리를 지금의 rc 로(요소 분류와 같이 split_own) 갈랐을 때 마커가 2 개 이상이고
    몸통 지름 중앙값이 그 덩어리 두께의 2 배 + 2 px 이상이면 (추세선 후보에서 뺀다)"""
    big = max(components_of(pix, w), key=len)
    box = bbox_of(big, w)
    t_own = path_thickness(big, w)
    rc = line_thickness + 1.0 if line_thickness else t_own + 1.0
    if max(box[2] - box[0] + 1, box[3] - box[1] + 1) < 4 * rc:
        return False
    res = split_own(big, box, w, h, rc)
    return res is not None and len(res[0]) >= 2 and marker_diameter(res[0]) >= MARKER_MIN[0] * t_own + MARKER_MIN[1]


# ─────────────────────────────────────────────────────────────── 빽빽한 산점 · 개수 범위 (설계서 14-9)

def typical_areas(areas: Sequence[float]) -> List[float]:
    """외톨이 면적 중 중앙값 m 의 1/3 – 3 배 안의 것. 위는 겹친 쌍이 외톨이처럼 보인 것, 아래는 번짐 잡티 —
    잡티는 1 · 2 칸이라 '면적 ≥ 4' 에 걸리지만 그림을 키우면 4 칸을 넘어 들어온다 (크기 불변)"""
    m = median(areas)
    return [a for a in areas if m / 3 <= a <= 3 * m]


def unit_of(areas: Sequence[float]) -> float:
    """외톨이 면적들 → 낱점 면적: typical_areas 의 중앙값"""
    return median(typical_areas(areas))


def quantile(vals: Sequence[float], p: float) -> float:
    """정렬한 값에서 p 분위 자리(가장 가까운 순위)의 값"""
    s = sorted(vals)
    return s[min(len(s) - 1, int(p * (len(s) - 1) + 0.5))]


def poisson_count(masses: Sequence[int], cell: int, unit: float) -> float:
    """겹침 보정 개수 — 칸(한 변 cell)마다 n = -(c² / unit) × ln(1 - min(POISSON_CAP, m / c²)) 를 더한다.
    무작위로 놓인 표식이 덮는 비율 1 - exp(-밀도 × 표식 면적) 을 거꾸로 풀어 겹친 만큼을 되돌린다 (표식 모양과 상관없다)"""
    a = cell * cell
    return sum(-(a / unit) * log(1 - min(POISSON_CAP, m / a)) for m in masses if m)


def count_range(masses: Sequence[int], cell: int, areas: Sequence[float]) -> Tuple[float, float, float]:
    """(가운데, 아래, 위). 가운데는 낱점 면적으로, 아래 · 위는 외톨이 면적(typical_areas)의 75% · 25% 분위수로 다시 센 값.
    크기가 고른 표식은 분위수 범위가 거의 0 이라 적어도 가운데의 ±RANGE_MIN 으로 넓힌다"""
    keep = typical_areas(areas)
    mid = poisson_count(masses, cell, median(keep))
    lo = min(poisson_count(masses, cell, quantile(keep, RANGE_Q[1])), mid * (1 - RANGE_MIN))
    hi = max(poisson_count(masses, cell, quantile(keep, RANGE_Q[0])), mid * (1 + RANGE_MIN))
    return mid, lo, hi


def curve_like(pix: Sequence[int], box: Tuple[int, int, int, int], w: int, h: int) -> bool:
    """곡선처럼 생긴 덩어리 — is_path 이면서 긴 축 DENSE_PATH_BIN px 구간마다 짧은 축으로 퍼진 폭의 중앙값이
    max(8 px, 0.08 × 그림 짧은 변) 이하. 마커가 붙은 곡선은 16–17 px, 한 덩어리로 이어진 빽빽한 산점은 100 px 넘게 퍼진다"""
    if not is_path(pix, box, w, h):
        return False
    along_x = box[2] - box[0] >= box[3] - box[1]
    span: Dict[int, List[int]] = {}
    for i in pix:
        a, o = (i % w, i // w) if along_x else (i // w, i % w)
        b = span.get(a // DENSE_PATH_BIN)
        if b is None:
            span[a // DENSE_PATH_BIN] = [o, o]
        elif o < b[0]:
            b[0] = o
        elif o > b[1]:
            b[1] = o
    return median([hi - lo + 1 for lo, hi in span.values()]) <= max(DENSE_PATH_SPREAD[0], DENSE_PATH_SPREAD[1] * min(w, h))


def big_share(items, unit: float, w: int, h: int) -> float:
    """덩어리들(칸, 상자)의 질량 중 낱점 면적의 DENSE_BIG_UNIT 배보다 큰 덩어리에 든 몫. 곡선처럼 생긴 덩어리는 몫에서 뺀다 (분모에는 든다)"""
    total = sum(len(p) for p, _ in items)
    big = sum(len(p) for p, b in items if len(p) > DENSE_BIG_UNIT * unit and not curve_like(p, b, w, h))
    return big / total if total else 0.0


def density_stats(k: int, items, plot_box: Tuple[int, int, int, int], w: int, h: int) -> Optional[dict]:
    """상자 안 군집 k 의 덩어리들(칸, 상자) → 빽빽 판정 값. 외톨이(원판 · 둥근 덩어리 · 속 빈 원, 면적 ≥ 4, 긴 변 ≤ 그림 긴 변의 10%)가
    없으면 None (지금 경로). 낱점 지름 = 외톨이 긴 변의 중앙값, 칸 한 변 = round(POISSON_CELL × 지름) 을 상자 왼쪽 위에서 깐다"""
    areas, sides = [], []
    for pix, box in items:
        bw, bh = box[2] - box[0] + 1, box[3] - box[1] + 1
        if len(pix) >= 4 and max(bw, bh) <= 0.1 * max(w, h) \
                and (is_round(bw, bh, len(pix)) or is_disc(pix, box, w) or is_hollow(pix, box, w)):
            areas.append(len(pix))
            sides.append(max(bw, bh))
    if not areas:
        return None
    diameter = median(sides)
    cell = max(1, int(round(POISSON_CELL * diameter)))
    x0, y0 = plot_box[0], plot_box[1]
    masses = Counter(((i // w - y0) // cell, (i % w - x0) // cell) for pix, _ in items for i in pix)
    mid, lo, hi = count_range(list(masses.values()), cell, areas)
    unit = unit_of(areas)
    return {"cluster": k, "unit": unit, "diameter": diameter, "cell": cell, "count": mid, "lo": lo, "hi": hi,
            "big": big_share(items, unit, w, h), "mass": sum(masses.values()), "iso": len(typical_areas(areas))}


def is_dense(st: dict) -> bool:
    """빽빽함: 겹침 보정 개수 ≥ DENSE_MIN_N 이고 큰 덩어리 몫 ≥ DENSE_BIG 이고 외톨이 ≥ DENSE_ISO_SHARE × 개수
    (상자 · 링 없음 · 색 군집 · 외톨이가 있는지는 부르는 쪽이 본다)"""
    return st["count"] >= DENSE_MIN_N and st["big"] >= DENSE_BIG and st["iso"] >= DENSE_ISO_SHARE * st["count"]


def density_field(k: int, items, plot_box: Tuple[int, int, int, int], st: dict, w: int) -> Element:
    """빽빽한 군집 k 의 상자 안 덩어리들 → Element("field"). 칸 목록 대신 블록(한 변 max(1, 상자 폭 // FIELD_COLS))마다 칸 수를
    array("I") 에 센다. 상자 밖으로 삐져나온 칸은 가장자리 블록에. bbox 는 덩어리 상자들의 합, cx · cy 는 질량 중심"""
    x0, y0, x1, y1 = plot_box
    block = max(1, (x1 - x0 + 1) // FIELD_COLS)
    cols, rows = (x1 - x0) // block + 1, (y1 - y0) // block + 1
    mass = array("I", [0]) * (cols * rows)
    sx = sy = 0
    for pix, _ in items:
        for i in pix:
            x, y = i % w, i // w
            sx += x
            sy += y
            mass[min(rows - 1, max(0, (y - y0) // block)) * cols + min(cols - 1, max(0, (x - x0) // block))] += 1
    total = sum(len(p) for p, _ in items)
    box = (min(b[0] for _, b in items), min(b[1] for _, b in items), max(b[2] for _, b in items), max(b[3] for _, b in items))
    n = int(round(st["count"]))
    dm = DensityMap(x0, y0, block, cols, rows, mass, float(st["unit"]), float(st["diameter"]), n,
                    min(n, int(st["lo"])), max(n, int(-(-st["hi"] // 1))), st["cell"])
    return Element("field", k, box, total, [], sx / total, sy / total, n, density=dm)


def segment(img) -> Segmentation:
    w, h = img.width, img.height
    bg = find_bg(img)
    cls, clusters, grid = classify(img, bg)
    seg = Segmentation(w, h, bg, clusters)
    per: Dict[int, List[int]] = {}
    for i, v in enumerate(cls):
        if v:
            per.setdefault(v, []).append(i)
    seg.grid = grid
    if not per:
        seg.plot_box, seg.plot_source = find_plot_box(seg)      # 격자만 있는 그림
        return seg
    if sum(len(v) for v in per.values()) > MAX_FG_RATIO * w * h:
        seg.reason = "바탕이 아닌 곳이 절반이 넘습니다 (사진이나 채워진 그림은 대상이 아닙니다)"
        return seg
    chrom = {i for k, idx in per.items() if not clusters[k - 1].neutral for i in idx}    # 색 있는 칸
    # ── 선: 가로 · 세로. 격자로 판정된 선은 선이 아니라 seg.grid 로
    hl, per = find_lines(per, w, h, True)
    vl, per = find_lines(per, w, h, False)
    hl, vl, seg.grid, grid_lines = grid_from_lines(hl, vl, clusters, seg.grid)
    hl, vl = clamp_to_frame(hl, vl, per, w)
    seg.elements += hl + vl
    seg.plot_box, seg.plot_source = find_plot_box(seg)
    thick = [e.thickness for e in hl + vl + grid_lines]      # 진한 격자 줄은 지금처럼 선 두께에 든다 (연한 격자는 들지 않는다)
    if thick:
        seg.line_thickness = median(thick)
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

    # ── 추세선: 상자 안 색 있는 군집마다 하나. 묶인 칸은 글자 · 점 · 마커 분리로 가지 않는다 (링이 있거나 상자가 없으면 묶지 않는다)
    trend_k: Set[int] = set()
    pb = seg.plot_box

    def xy_in_plot(x: float, y: float) -> bool:
        return pb[0] + PLOT_INSET <= x <= pb[2] - PLOT_INSET and pb[1] + PLOT_INSET <= y <= pb[3] - PLOT_INSET

    if pb is not None and ring is None:
        for k in sorted(per):
            if clusters[k - 1].neutral:
                continue
            inside = [i for i in per[k] if xy_in_plot(i % w, i // w)]
            found = find_trend(inside, pb, w)
            if found is None or marker_curve(inside, w, h, seg.line_thickness):
                continue
            path, t = found
            seg.elements.append(Element("trend", k, bbox_of(inside, w), len(inside), inside, sum(i % w for i in inside) / len(inside),
                                        sum(i // w for i in inside) / len(inside), 0, t, path))
            gone = set(inside)
            per[k] = [i for i in per[k] if i not in gone]
            trend_k.add(k)

    # ── 연결요소
    comps = []                                   # (군집, 칸 목록, 상자)
    for k, idx in per.items():
        for pix in components_of(idx, w):
            comps.append((k, pix, bbox_of(pix, w)))
    # ── 빽빽한 산점: 상자 안 색 군집마다 겹침 보정 개수 · 큰 덩어리 몫을 재서, 빽빽하면 상자 안 덩어리를 모두 field 하나로
    #    (글자 · 마커 분리 · 점으로 가지 않는다). 링이 있거나 상자가 없거나 외톨이가 없으면 지금 경로 (설계서 14-9 · 14-13)
    field_k: Set[int] = set()
    if pb is not None and ring is None:
        mine: Dict[int, list] = {}
        for k, pix, box in comps:
            if not clusters[k - 1].neutral and in_plot(pb, box):
                mine.setdefault(k, []).append((pix, box))
        for k in sorted(mine):
            st = density_stats(k, mine[k], pb, w, h)
            if st is None or not is_dense(st):
                continue
            seg.elements.append(density_field(k, mine[k], pb, st, w))
            seg.unit[k] = float(st["unit"])
            field_k.add(k)
        if field_k:
            comps = [c for c in comps if not (c[0] in field_k and in_plot(pb, c[2]))]
    # ── 글자: 높이가 글자만 한 덩어리 중 줄을 이루는 것 (링 안은 데이터).
    #    상자 안에서 표식이 되풀이되는 색 군집의 상자 안 덩어리는 후보가 아니다 — 겹친 표식 쌍이 줄 묶기를 켜지 않게
    marked = marker_clusters(comps, clusters, seg.plot_box, ring, w, h)
    max_h = max(GLYPH_MAX_H[0], GLYPH_MAX_H[1] * h)
    cands = []
    for n, (k, pix, box) in enumerate(comps):
        bw, bh = box[2] - box[0] + 1, box[3] - box[1] + 1
        if GLYPH_MIN_H <= max(bw, bh) <= max_h * 6 and min(bw, bh) <= max_h and not in_ring(box) \
                and not (k in marked and in_plot(seg.plot_box, box)):
            cands.append((n, box, len(pix), is_round(bw, bh, len(pix)) or is_disc(pix, box, w)))
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
    for n, (k, pix, box) in enumerate(comps):        # 추세선 · field 가 생긴 군집의 상자 밖 조각 = 범례 견본 · 제목 번짐 → 글자 (잡티는 지금처럼 버린다)
        if len(pix) >= MIN_DOT_AREA and (k in field_k or k in trend_k and not xy_in_plot(sum(i % w for i in pix) / len(pix),
                                                                                         sum(i // w for i in pix) / len(pix))):
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

    line_boxes = [(e.cluster, e.bbox) for e in seg.elements + grid_lines if e.kind in ("hline", "vline")]

    def on_line(k: int, box, area: int) -> bool:   # 다른 색 선 위의 색 번짐
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        return area <= LINE_BLUR_MAX and any(lk != k and b[0] - 1 <= cx <= b[2] + 1 and b[1] - 1 <= cy <= b[3] + 1
                                        for lk, b in line_boxes)

    keep = [c for c in keep if not (max(c[2][2] - c[2][0], c[2][3] - c[2][1]) + 1 <= max_h
                                    and (on_text(c[2]) or on_line(c[0], c[2], len(c[1]))))]
    # ── 낱점 면적: 군집마다 외톨이 둥근 덩어리(원판 · 속 빈 원 포함)의 중앙값
    unit: Dict[int, float] = {k: seg.unit[k] for k in field_k}

    def estimate(k: int, comps_) -> None:
        areas = []
        for kk, pix, box in comps_:
            bw, bh = box[2] - box[0] + 1, box[3] - box[1] + 1
            if kk == k and len(pix) >= 4 and max(bw, bh) <= 0.1 * max(w, h) \
                    and (is_round(bw, bh, len(pix)) or is_disc(pix, box, w) or is_hollow(pix, box, w)):
                areas.append(len(pix))
        if areas:
            m = median(areas)
            unit[k] = median([a for a in areas if a <= 3 * m])

    for k in {c[0] for c in keep if not clusters[c[0] - 1].neutral}:
        estimate(k, keep)            # 중립은 번짐 조각에 속지 않게 뒤에서
    rc = seg.line_thickness + 1.0 if seg.line_thickness else None
    if rc is None and ring is None:      # 가로 · 세로선도 웨이퍼 링도 없는 차트: 곡선 자체의 두께로 문턱을 정한다
        paths = [pix for _, pix, box in keep if is_path(pix, box, w, h)]
        if paths:
            rc = path_thickness(max(paths, key=len), w) + 1.0
    small = []
    for k, pix, box in keep:
        bw, bh = box[2] - box[0] + 1, box[3] - box[1] + 1
        cx, cy = sum(i % w for i in pix) / len(pix), sum(i // w for i in pix) / len(pix)
        # 선에 붙은 마커가 있을 수 있는 큰 덩어리. 상자 안에서 표식이 되풀이되는 군집의 곡선 아닌 덩어리는 겹친 표식 무리라
        # 마커 분리(쌍을 코어 하나로 세고 나머지를 곡선으로 낸다)로 보내지 않고 면적으로 센다
        if rc is not None and max(bw, bh) >= 4 * rc \
                and not (k in marked and in_plot(seg.plot_box, box) and not is_path(pix, box, w, h)):
            res = split_own(pix, box, w, h, rc)
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
