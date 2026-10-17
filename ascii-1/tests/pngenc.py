# -*- coding: utf-8 -*-
"""시험용 PNG 인코더 · 기대값 계산 — tests/ 에만 둔다 (W-02: 실행 경로에서 import 하지 않는다)

디코더(ascii1_png)와 코드를 나누지 않고 PNG 규격만 보고 따로 짰다: 필터는 순방향(빼기), 줄 묶기는 비트 단위.
"""
import struct
import zlib
from typing import List, Optional, Sequence, Tuple

SIGNATURE = b"\x89PNG\r\n\x1a\n"
CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
COMBOS = [(0, 1), (0, 2), (0, 4), (0, 8), (0, 16), (2, 8), (2, 16), (3, 1), (3, 2), (3, 4), (3, 8),
          (4, 8), (4, 16), (6, 8), (6, 16)]
ADAM7 = [(0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2)]


def chunk(kind: bytes, body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)


def pack_row(samples: Sequence[int], depth: int) -> bytes:
    if depth == 8:
        return bytes(samples)
    if depth == 16:
        return b"".join(struct.pack(">H", v) for v in samples)
    bits = "".join(format(v, "0%db" % depth) for v in samples)
    bits += "0" * (-len(bits) % 8)
    return bytes(int(bits[i:i + 8], 2) for i in range(0, len(bits), 8))


def paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else (b if pb <= pc else c)


def filter_row(ftype: int, cur: bytes, prev: bytes, bpp: int) -> bytes:
    out = bytearray()
    for i, x in enumerate(cur):
        left = cur[i - bpp] if i >= bpp else 0
        up = prev[i]
        ul = prev[i - bpp] if i >= bpp else 0
        pred = (0, left, up, (left + up) // 2, paeth(left, up, ul))[ftype]
        out.append((x - pred) & 255)
    return bytes(out)


def scanlines(rows: List[List[Tuple[int, ...]]], w: int, h: int, ctype: int, depth: int, interlace: int,
              filters: Sequence[int]) -> bytes:
    bpp = max(1, depth * CHANNELS[ctype] // 8)
    plan = [(0, 0, 1, 1)] if not interlace else ADAM7
    out, n = bytearray(), 0
    for xs, ys, dx, dy in plan:
        ys_list = list(range(ys, h, dy))
        xs_list = list(range(xs, w, dx))
        if not ys_list or not xs_list:
            continue
        prev = None
        for y in ys_list:
            flat = [s for x in xs_list for s in rows[y][x]]
            cur = pack_row(flat, depth)
            if prev is None:
                prev = bytes(len(cur))
            ft = filters[n % len(filters)]
            n += 1
            out.append(ft)
            out += filter_row(ft, cur, prev, bpp)
            prev = cur
    return bytes(out)


def encode(w: int, h: int, ctype: int, depth: int, rows: List[List[Tuple[int, ...]]],
           palette: Optional[Sequence[Tuple[int, int, int]]] = None, trns: Optional[bytes] = None,
           interlace: int = 0, filters: Sequence[int] = (0, 1, 2, 3, 4), idat_parts: int = 1,
           extra: Sequence[bytes] = ()) -> bytes:
    raw = scanlines(rows, w, h, ctype, depth, interlace, filters)
    comp = zlib.compress(raw)
    step = -(-len(comp) // idat_parts)
    parts = [comp[i:i + step] for i in range(0, len(comp), step)] or [b""]
    out = SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, depth, ctype, 0, 0, interlace))
    if palette is not None:
        out += chunk(b"PLTE", bytes(v for c in palette for v in c))
    if trns is not None:
        out += chunk(b"tRNS", trns)
    for e in extra:
        out += e
    for p in parts:
        out += chunk(b"IDAT", p)
    return out + chunk(b"IEND", b"")


def forge(w: int, h: int, depth: int, ctype: int, interlace: int = 0, idat: bytes = b"") -> bytes:
    """머리만 주는 대로 쓰고 IDAT 는 그대로 넣는다 — 잘못된 머리 · 압축 폭탄 시험용"""
    return (SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, depth, ctype, 0, 0, interlace))
            + chunk(b"IDAT", zlib.compress(idat)) + chunk(b"IEND", b""))


def over_white(c: int, a: int) -> int:
    return (c * a + 255 * (255 - a) + 127) // 255


def expected_rgb(px: Tuple[int, ...], ctype: int, depth: int, palette=None, trns=None) -> Tuple[int, int, int]:
    """한 칸의 기대 RGB — 흰 바탕에 합성 · 16 비트는 위 바이트. trns 는 색 유형 3 이면 알파 목록, 0 · 2 이면 키 값"""
    hi = (lambda v: v >> 8) if depth == 16 else (lambda v: v)
    if ctype == 3:
        r, g, b = palette[px[0]]
        a = trns[px[0]] if trns is not None and px[0] < len(trns) else 255
        return over_white(r, a), over_white(g, a), over_white(b, a)
    if ctype == 0:
        if trns is not None and px[0] == trns:
            return 255, 255, 255
        v = px[0] * 255 // ((1 << depth) - 1) if depth < 8 else hi(px[0])
        return v, v, v
    if ctype == 2:
        if trns is not None and tuple(px) == tuple(trns):
            return 255, 255, 255
        return hi(px[0]), hi(px[1]), hi(px[2])
    if ctype == 4:
        v = over_white(hi(px[0]), hi(px[1]))
        return v, v, v
    a = hi(px[3])
    return over_white(hi(px[0]), a), over_white(hi(px[1]), a), over_white(hi(px[2]), a)
