# -*- coding: utf-8 -*-
"""합성 그림 — 관리도 같은 선 차트와 웨이퍼 파티클 맵을 코드로 그린다 (W-12: 실제 그림을 저장소에 넣지 않는다)

실제 그림에서 잰 모양(선 두께 2–3 · 마커 지름 약 10 · 웨이퍼 점 3×3 · 1칸 외곽선 · 노치)을 따라 그렸다.
soften() 은 JPEG 처럼 가장자리가 번지고 잡티가 낀 모습을 흉내 낸다.
"""
import random
from math import cos, hypot, pi, sin
from typing import List, Tuple

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

    def text(self, s: str, x: int, y: int, c: Color) -> None:
        """5×7 글자를 한 칸 띄워 가로로 쓴다 (x · y 는 왼쪽 위)"""
        for n, ch in enumerate(s):
            for j, row in enumerate(FONT[ch]):
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


def control_chart(markers: int = 12) -> Tuple[Image, int]:
    """관리도: 한계선(빨강 2 · 노랑 2) · 중심선(검정) · 왼쪽 축 · 아래 축 · 파랑 꺾은선과 마커 · 글자. (그림, 마커 수)"""
    c = Canvas(420, 300)
    c.vline(45, 8, 270, 2, BLACK)
    c.hline(270, 45, 400, 2, BLACK)
    for y, t, col in ((70, 3, RED), (230, 3, RED), (100, 2, YELLOW), (200, 2, YELLOW), (150, 3, BLACK)):
        c.hline(y, 46, 400, t, col)
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


def wafer_map(blue: int = 50, orange: int = 12, gray: int = 8, tile: int = 4, seed: int = 3, notch: bool = True,
              faint: bool = False, plus: int = 0, squash: float = 0.0, halo: int = 0):
    """웨이퍼 맵: 회색 1칸 외곽(아래쪽에 노치) · 흩어진 3×3 점 · 빈틈없이 깐 점 덩어리. → (그림, 정보 dict)"""
    rng = random.Random(seed)
    c = Canvas(240, 240)
    cx = cy = 120
    R = 90
    cover = {}                                      # faint: 칸에 걸친 정도로 옅게 (1칸 선이 격자 중간에 걸린 모습)
    for k in range(0, 3600):
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
    for i in range(tile):
        for j in range(tile):
            c.rect(blob[0] + 3 * i, blob[1] + 3 * j, blob[0] + 3 * i + 2, blob[1] + 3 * j + 2, BLUE)
    return c.image(), {"blue": blue, "orange": orange, "gray": gray, "tile": tile * tile, "plus": plus * 5, "R": R, "center": (cx, cy)}
