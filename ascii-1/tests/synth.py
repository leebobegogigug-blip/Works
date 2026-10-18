# -*- coding: utf-8 -*-
"""합성 그림 — 관리도 같은 선 차트와 웨이퍼 파티클 맵을 코드로 그린다 (W-12: 실제 그림을 저장소에 넣지 않는다)

실제 그림에서 잰 모양(선 두께 2–3 · 마커 지름 약 10 · 웨이퍼 점 3×3 · 1칸 외곽선 · 노치)을 따라 그렸다.
soften() 은 JPEG 처럼 가장자리가 번지고 잡티가 낀 모습을 흉내 낸다.
"""
import random
from math import cos, exp, hypot, pi, sin
from typing import Dict, List, Optional, Set, Tuple

from ascii1_png import Image

Color = Tuple[int, int, int]
BLACK, RED, YELLOW, BLUE, ORANGE, GRAY = (30, 30, 30), (225, 40, 45), (245, 235, 10), (60, 85, 165), (215, 145, 85), (190, 190, 190)

FONT = {
    "U": ["#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."],
    "C": [".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."],
    "L": ["#....", "#....", "#....", "#....", "#....", "#....", "#####"],
    "1": ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "0": [".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."],
    "5": ["#####", "#....", "####.", "....#", "....#", "#...#", ".###."],
}

# HARD 세트의 제목 · 눈금 글자 (FONT 와 나눈 까닭: test_seg 가 FONT 의 글자마다 '원판이 아니다' 를 확인하는데 점 · 공백은 그 대상이 아니다)
FONT_HARD = {
    "2": [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"],
    "3": [".###.", "#...#", "....#", "..##.", "....#", "#...#", ".###."],
    "4": ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."],
    "6": [".###.", "#....", "#....", "####.", "#...#", "#...#", ".###."],
    "7": ["#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."],
    "8": [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."],
    "9": [".###.", "#...#", "#...#", ".####", "....#", "....#", ".###."],
    ".": [".....", ".....", ".....", ".....", ".....", "..##.", "..##."],
    " ": [".....", ".....", ".....", ".....", ".....", ".....", "....."],
    "T": ["#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."],
    "E": ["#####", "#....", "#....", "####.", "#....", "#....", "#####"],
    "M": ["#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"],
    "P": ["####.", "#...#", "#...#", "####.", "#....", "#....", "#...."],
    "R": ["####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"],
    "A": [".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
}


class Canvas:
    def __init__(self, w: int, h: int, bg: Color = (255, 255, 255)):
        self.w, self.h = w, h
        self.px = [bg] * (w * h)

    def set(self, x: int, y: int, c: Color) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            self.px[y * self.w + x] = c

    def rect(self, x0: int, y0: int, x1: int, y1: int, c: Color) -> None:
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                self.set(x, y, c)

    def disc(self, cx: float, cy: float, r: float, c: Color) -> None:
        for y in range(int(cy - r) - 1, int(cy + r) + 2):
            for x in range(int(cx - r) - 1, int(cx + r) + 2):
                if hypot(x - cx, y - cy) <= r:
                    self.set(x, y, c)

    def hline(self, y: int, x0: int, x1: int, t: int, c: Color) -> None:
        self.rect(x0, y - t // 2, x1, y - t // 2 + t - 1, c)

    def vline(self, x: int, y0: int, y1: int, t: int, c: Color) -> None:
        self.rect(x - t // 2, y0, x - t // 2 + t - 1, y1, c)

    def line(self, x0: float, y0: float, x1: float, y1: float, r: float, c: Color) -> None:
        n = int(max(abs(x1 - x0), abs(y1 - y0))) * 2 + 1
        for k in range(n + 1):
            self.disc(x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n, r, c)

    def ring(self, cx: float, cy: float, r: float, width: float, c: Color) -> None:
        """속 빈 원 — 바깥 반지름 r 에서 안쪽으로 width 만큼 두른 고리 (width 1 이면 1 픽셀 테두리)"""
        for y in range(int(cy - r) - 1, int(cy + r) + 2):
            for x in range(int(cx - r) - 1, int(cx + r) + 2):
                d = hypot(x - cx, y - cy)
                if r - width < d <= r:
                    self.set(x, y, c)

    def polyline(self, pts: List[Tuple[float, float]], width: float, c: Color,
                 on: Optional[float] = None, off: float = 0.0) -> None:
        """꺾은선 (굵기 width). on 을 주면 점선 — 호의 길이를 따라 on 만큼 긋고 off 만큼 비운다"""
        r, s = width / 2.0, 0.0
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            length = hypot(x1 - x0, y1 - y0)
            n = max(1, int(length * 2))
            for k in range(n):
                t = k / n
                if on is None or (s + t * length) % (on + off) < on:
                    if width <= 1:                 # 1 픽셀 선은 가장 가까운 칸 하나씩 (8 방향으로 이어진 가는 선)
                        self.set(int(round(x0 + (x1 - x0) * t)), int(round(y0 + (y1 - y0) * t)), c)
                    else:
                        self.disc(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, r, c)
            s += length

    def text(self, s: str, x: int, y: int, c: Color) -> None:
        """5×7 글자를 한 칸 띄워 가로로 쓴다 (x · y 는 왼쪽 위)"""
        for n, ch in enumerate(s):
            for j, row in enumerate(FONT.get(ch) or FONT_HARD[ch]):
                for i, v in enumerate(row):
                    if v == "#":
                        self.set(x + n * 7 + i, y + j, c)

    def image(self) -> Image:
        return Image(self.w, self.h, bytes(v for p in self.px for v in p))


def zoom(img: Image, f: int) -> Image:
    """f 배로 키운다 (가장 가까운 칸 복사)"""
    w, h, src = img.width, img.height, img.rgb
    out = bytearray()
    for y in range(h):
        row = b"".join(src[3 * (y * w + x):3 * (y * w + x) + 3] * f for x in range(w))
        out += row * f
    return Image(w * f, h * f, bytes(out))


def soften(img: Image, a: float = 0.7, noise: int = 4, seed: int = 1) -> Image:
    """가장자리를 번지게 하고(이웃 네 칸과 섞음) 칸마다 ±noise 의 잡티를 더한다 — JPEG 흉내"""
    w, h, src = img.width, img.height, img.rgb
    rng = random.Random(seed)
    out = bytearray(len(src))
    for y in range(h):
        for x in range(w):
            for k in range(3):
                nb = [src[3 * (yy * w + xx) + k] for xx, yy in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
                      if 0 <= xx < w and 0 <= yy < h]
                v = a * src[3 * (y * w + x) + k] + (1 - a) * sum(nb) / len(nb) + rng.randint(-noise, noise)
                out[3 * (y * w + x) + k] = max(0, min(255, int(round(v))))
    return Image(w, h, bytes(out))


def control_chart(markers: int = 12, frame: bool = False) -> Tuple[Image, int]:
    """관리도: 한계선(빨강 2 · 노랑 2) · 중심선(검정) · 왼쪽 축 · 아래 축 · 파랑 꺾은선과 마커 · 글자. (그림, 마커 수)"""
    c = Canvas(420, 300)
    c.vline(45, 8, 270, 2, BLACK)
    c.hline(270, 45, 400, 2, BLACK)
    if frame:                                    # 오른쪽 · 위 틀까지 닫고, 한계선은 틀 끝에서 멈추고 라벨은 틀 밖에 둔다
        c.vline(400, 8, 270, 2, BLACK)
        c.hline(8, 45, 400, 2, BLACK)
    for y, t, col in ((70, 3, RED), (230, 3, RED), (100, 2, YELLOW), (200, 2, YELLOW), (150, 3, BLACK)):
        c.hline(y, 46, 401 if frame else 400, t, col)
    c.text("UCL", 404, 67, RED)                  # 선 끝 옆에 놓인 글자 (선 띠 안쪽 행에 걸친다)
    for label, y in (("110", 66), ("105", 106), ("100", 146)):
        c.text(label, 12, y, BLACK)
    c.text("CL", 404, 167, BLACK)                # 가까운 두 글자뿐인 라벨 — 줄 묶기로만 잡힌다
    for label, x in (("5", 140), ("1", 220), ("0", 300)):
        c.text(label, x, 278, BLACK)             # 멀리 떨어진 낱글자 눈금 — 같은 줄 맞춤으로만 잡힌다
    pts = [(70 + k * (310 // (markers - 1)), 150 + (35 if k % 3 == 0 else -30 if k % 3 == 1 else 8)) for k in range(markers)]
    for a, b in zip(pts, pts[1:]):
        c.line(a[0], a[1], b[0], b[1], 1.2, BLUE)
    for x, y in pts:
        c.disc(x, y, 5.2, BLUE)
    return c.image(), markers


def line_chart(markers: int = 12) -> Tuple[Image, int]:
    """마커와 곡선뿐인 차트 — 가로 · 세로선도 글자도 없다 (선 두께를 곡선 자체에서 재야 마커를 가른다)"""
    c = Canvas(420, 300)
    pts = [(70 + k * (310 // (markers - 1)), 150 + (35 if k % 3 == 0 else -30 if k % 3 == 1 else 8)) for k in range(markers)]
    for a, b in zip(pts, pts[1:]):
        c.line(a[0], a[1], b[0], b[1], 1.2, BLUE)
    for x, y in pts:
        c.disc(x, y, 5.2, BLUE)
    return c.image(), markers


def wafer_map(blue: int = 50, orange: int = 12, gray: int = 8, tile: int = 4, seed: int = 3, notch: bool = True,
              faint: bool = False, plus: int = 0, squash: float = 0.0, halo: int = 0, stripe: int = 0, ring: bool = True):
    """웨이퍼 맵: 회색 1칸 외곽(아래쪽에 노치) · 흩어진 3×3 점 · 빈틈없이 깐 점 덩어리. → (그림, 정보 dict)"""
    rng = random.Random(seed)
    c = Canvas(240, 240)
    cx = cy = 120
    R = 90
    cover = {}                                      # faint: 칸에 걸친 정도로 옅게 (1칸 선이 격자 중간에 걸린 모습)
    for k in range(0 if ring else 3600, 3600):
        a = k / 10
        r = R
        if notch and abs(a - 90) <= 4:
            r = R - 7 * (1 - abs(a - 90) / 4)
        fx, fy = cx + r * cos(a * pi / 180), cy + r * (1 - squash) * sin(a * pi / 180)    # squash: 세로로 살짝 눌린 원
        if not faint:
            c.set(int(round(fx)), int(round(fy)), GRAY)
            continue
        x0, y0 = int(fx), int(fy)
        for dx in (0, 1):
            for dy in (0, 1):
                wgt = (1 - abs(fx - (x0 + dx))) * (1 - abs(fy - (y0 + dy)))
                cover[(x0 + dx, y0 + dy)] = max(cover.get((x0 + dx, y0 + dy), 0.0), wgt)
    for (x, y), wgt in cover.items():
        c.set(x, y, tuple(int(round(255 - (255 - g) * min(1.0, wgt * 0.9))) for g in GRAY))
    taken: List[Tuple[int, int]] = []
    blob = (150, 105)                              # 덩어리 자리 (tile × tile 개를 3칸 간격으로 깐다)
    taken.append((blob[0] + 6, blob[1] + 6))

    def place() -> Tuple[int, int]:
        while True:
            x, y = rng.randint(40, 200), rng.randint(40, 190)
            if hypot(x - cx, y - cy) < R - 18 and hypot(x - blob[0] - 6, y - blob[1] - 6) > 20 \
                    and all(hypot(x - tx, y - ty) >= 9 for tx, ty in taken):
                taken.append((x, y))
                return x, y

    taken += [(41 + 3 * n, 41 + 3 * n) for n in range(stripe)]       # 사슬 자리는 다른 점이 겹치지 않게 비워 둔다
    colored = []
    for n, col in ((blue, BLUE), (orange, ORANGE), (gray, GRAY)):
        for _ in range(n):
            x, y = place()
            c.rect(x - 1, y - 1, x + 1, y + 1, col)
            if col != GRAY:
                colored.append((x, y))
    for x, y in colored:                            # 색 있는 점 둘레의 또렷한 회색 테두리 (JPEG 링잉 같은 번짐)
        for yy in range(y - 1 - halo, y + 2 + halo):
            for xx in range(x - 1 - halo, x + 2 + halo):
                if c.px[yy * c.w + xx] == (255, 255, 255):
                    c.set(xx, yy, GRAY)
    for n in range(plus):                           # 십자 모양 점 덩어리를 한 줄에: 글자처럼 보이지만 링 안이라 데이터
        px, py = 100 + 25 * n, 60
        taken.append((px, py))
        for dx, dy in ((0, 0), (3, 0), (-3, 0), (0, 3), (0, -3)):
            c.rect(px + dx - 1, py + dy - 1, px + dx + 1, py + dy + 1, BLUE)
    for n in range(stripe):                        # 3×3 점이 대각선으로 닿아 사슬처럼 이어진 덩어리 — 길쭉하고 속이 비어 곡선처럼 보인다
        c.rect(40 + 3 * n, 40 + 3 * n, 42 + 3 * n, 42 + 3 * n, BLUE)
    for i in range(tile):
        for j in range(tile):
            c.rect(blob[0] + 3 * i, blob[1] + 3 * j, blob[0] + 3 * i + 2, blob[1] + 3 * j + 2, BLUE)
    return c.image(), {"blue": blue, "orange": orange, "gray": gray, "tile": tile * tile, "plus": plus * 5, "stripe": stripe, "R": R, "center": (cx, cy)}


# ─────────────────────────────────────────────────────────────── HARD 세트: 격자 · 속 빈 표식 · 겹침 · 점선 추세선 · 번짐
# 산점도형 차트(800×600)를 축마다 한 가지씩 바꿔 가며 그린다. 정답(개수 · 좌표 · 격자 줄 수 · 그림 상자)을 같이 돌려준다.
# 실험 때 Pillow 로 그린 그림의 모양을 표준 라이브러리로 다시 그린 것이다 (W-02: 시험 · 개발 도구만 쓴다).

LBLUE_GRID, DGRAY_GRID = (200, 225, 240), (150, 150, 150)
SERIES, SERIES2, TREND, INK = (31, 119, 180), (255, 127, 14), (214, 39, 40), (20, 20, 20)
HARD_SIZE = (800, 600)
HARD_BOX = (90, 60, 770, 530)                      # 그림 상자 x0 y0 x1 y1 (격자의 바깥 줄이 놓이는 곳)
GRID_LINES = (21, 17)                              # 세로 · 가로 줄 수


def ring(c: Canvas, cx: float, cy: float, r: float, width: float, color: Color) -> None:
    """속 빈 원"""
    c.ring(cx, cy, r, width, color)


def dashed(c: Canvas, pts: List[Tuple[float, float]], on: float, off: float, width: float, color: Color) -> None:
    """점선 꺾은선"""
    c.polyline(pts, width, color, on, off)


def grid(c: Canvas, box: Tuple[int, int, int, int], nx: int, ny: int, color: Color, width: int) -> Set[int]:
    """연한 격자: 세로 nx 줄 · 가로 ny 줄을 상자 안에 같은 간격으로 긋는다. 그린 칸 번호(y * w + x)의 집합을 돌려준다"""
    x0, y0, x1, y1 = box
    before = list(c.px)
    for k in range(nx):
        c.vline(int(round(x0 + (x1 - x0) * k / (nx - 1))), y0, y1, width, color)
    for k in range(ny):
        c.hline(int(round(y0 + (y1 - y0) * k / (ny - 1))), x0, x1, width, color)
    return {i for i, (a, b) in enumerate(zip(before, c.px)) if a is not b and a != b}


def sigmoid_band(t: float) -> float:
    """가로 위치 t(0–1)에서 띠 중심의 높이(0–1) — 왼쪽 낮고 오른쪽 높은 S 자"""
    return 1.0 / (1.0 + exp(-(t - 0.5) * 10)) * 0.6 + 0.2


def scatter(c: Canvas, box: Tuple[int, int, int, int], n: int, r_range: Tuple[float, float], hollow: bool,
            seed: int, color: Color = SERIES, lift: float = 0.0) -> List[Tuple[float, float, float]]:
    """겹치는 산점 n 개 — 시그모이드 띠 + 가우스 잡음. 속이 비면 1 픽셀 테두리 원. 정답 (x, y, r) 목록을 돌려준다"""
    x0, y0, x1, y1 = box
    rng = random.Random(seed)
    pts = []
    for _ in range(n):
        t = rng.random()
        v = min(0.98, max(0.02, sigmoid_band(t) + rng.gauss(0, 0.08) + lift))
        x, y, r = x0 + t * (x1 - x0), y1 - v * (y1 - y0), rng.uniform(*r_range)
        pts.append((x, y, r))
        if hollow:
            ring(c, x, y, r, 1, color)
        else:
            c.disc(x, y, r, color)
    return pts


def trend_points(box: Tuple[int, int, int, int]) -> List[Tuple[float, float]]:
    """추세선 정답 좌표 (띠 중심을 따라 가로 폭의 약 95%)"""
    x0, y0, x1, y1 = box
    out = []
    for k in range(400):
        t = k / 399
        out.append((x0 + t * (x1 - x0) * 0.95 + 0.02 * (x1 - x0), y1 - sigmoid_band(t) * (y1 - y0)))
    return out


class HardCase:
    """HARD 변형 하나: 그림과 정답"""

    def __init__(self, name: str, image: Image, box, pts, pts2, trend, trend_kind, grid_lines, grid_cells, series_color):
        self.name, self.image, self.box = name, image, box
        self.pts = pts                       # 첫 계열 (x, y, r) — 개수의 정답
        self.pts2 = pts2                     # 둘째 계열 (L)
        self.trend = trend                   # 추세선 정답 좌표 (없으면 [])
        self.trend_kind = trend_kind         # None · "solid" · "dash"
        self.grid_lines = grid_lines         # 격자 줄 수 (세로 + 가로, 없으면 0)
        self.grid_cells = grid_cells         # 데이터에 덮이지 않고 남은 격자 칸 번호
        self.series_color = series_color

    @property
    def n(self) -> int:
        return len(self.pts)

    def cell_counts(self, gx: int, gy: int, series: int = 0) -> List[int]:
        """그림 상자를 gx × gy 칸으로 나눠 칸마다 센 정답 개수 (행 우선)"""
        x0, y0, x1, y1 = self.box
        out = [0] * (gx * gy)
        for x, y, _ in (self.pts if series == 0 else self.pts2):
            i = min(gx - 1, max(0, int((x - x0) / (x1 - x0) * gx)))
            j = min(gy - 1, max(0, int((y - y0) / (y1 - y0) * gy)))
            out[j * gx + i] += 1
        return out


# 이름 → 그리는 값. 기본은 채운 r4 300 개 + 실선 폭 3 + 1 픽셀 틀(검정)
_BASE = dict(grid=None, gridw=1, n=300, r=(4, 4), hollow=False, trend="solid", trendw=3, text=False, series2=False,
             blur=False, frame=True)
HARD_SPECS: Dict[str, dict] = {
    "A_base": {},
    "A0": dict(n=60, trend=None),
    "A1": dict(trend=None),
    "E0": dict(n=60, trend=None, hollow=True),
    "E": dict(trend=None, hollow=True),
    "F0": dict(n=60, trend=None, r=(2, 2)),
    "F1": dict(n=60, trend=None, r=(1.5, 1.5)),
    "H": dict(n=2000, r=(3, 3), trend=None),
    "I": dict(n=2000, r=(2, 6), hollow=True, trend=None),
    "B0": dict(n=60, trend=None, grid=LBLUE_GRID),
    "C": dict(grid=LBLUE_GRID, gridw=2),
    "D": dict(grid=DGRAY_GRID),
    "J": dict(trend="dash"),
    "J0": dict(n=0, trend="dash"),
    "J1": dict(n=0),
    "J2": dict(trendw=1),
    "K": dict(text=True),
    "L": dict(series2=True),
    "Z": dict(grid=LBLUE_GRID, gridw=2, n=2500, r=(2, 6), hollow=True, trend="dash", text=True, blur=True),
}
HARD = tuple(HARD_SPECS)


def hard_case(name: str) -> HardCase:
    """HARD 변형 name 의 그림과 정답. 같은 이름이면 늘 같은 그림이다 (씨앗 고정)"""
    cfg = dict(_BASE, **HARD_SPECS[name])
    w, h = HARD_SIZE
    box = HARD_BOX
    x0, y0, x1, y1 = box
    c = Canvas(w, h)
    gcells, glines = set(), 0
    if cfg["grid"]:
        gcells = grid(c, box, GRID_LINES[0], GRID_LINES[1], cfg["grid"], cfg["gridw"])
        glines = sum(GRID_LINES)
    elif cfg["frame"]:
        for x in (x0, x1):
            c.vline(x, y0, y1, 1, (40, 40, 40))
        for y in (y0, y1):
            c.hline(y, x0, x1, 1, (40, 40, 40))
    if cfg["text"]:
        c.text("TEMP RATE 2.5", w // 2 - 45, 25, INK)                      # 제목
        for k in range(11):
            c.text(str(k * 10), x0 + (x1 - x0) * k // 10 - 7, y1 + 10, INK)    # 가로 눈금
        for k in range(9):
            c.text("%.1f" % (k * 0.3), x0 - 33, y1 - (y1 - y0) * k // 8 - 3, INK)  # 세로 눈금
        c.text("TEMP", w // 2 - 14, h - 28, INK)
    pts = scatter(c, box, cfg["n"], cfg["r"], cfg["hollow"], 1, SERIES) if cfg["n"] else []
    pts2 = scatter(c, box, cfg["n"] // 2, cfg["r"], cfg["hollow"], 2, SERIES2, lift=0.15) if cfg["series2"] else []
    trend = []
    if cfg["trend"]:
        trend = trend_points(box)
        if cfg["trend"] == "solid":
            c.polyline(trend, cfg["trendw"], TREND)
        else:
            dashed(c, trend, 10, 6, cfg["trendw"], TREND)
    gcells = {i for i in gcells if c.px[i] == cfg["grid"]}                 # 데이터가 덮은 칸은 뺀다
    img = c.image()
    if cfg["blur"]:
        img = soften(img, 0.8, 4, 7)                       # JPEG q80 쯤의 번짐 · 잡티
    return HardCase(name, img, box, pts, pts2, trend, cfg["trend"], glines, gcells, SERIES)
