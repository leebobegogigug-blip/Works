# -*- coding: utf-8 -*-
"""ascii1_jpeg - 표준 라이브러리만으로 baseline JPEG 를 읽는다 (ITU T.81 · 부록 F 의 순차 허프만)

지원: SOF0 (8 비트) · 성분 1 또는 3 · 표본 비율은 정수비 (1×1 · 2×1 · 1×2 · 2×2 · 4×1 …) · DQT 8/16 비트 ·
DHT · DRI/RSTn · 인터리브 스캔과 성분마다 나눈 여러 스캔 · APPn/COM 은 건너뛴다 · Adobe 변환 0(RGB) · 1(YCbCr)
해독: 허프만(9 비트 룩업 표 + 긴 부호는 표준 순서 찾기) → 역양자화 → 분리형 실수 IDCT(0 인 계수 · 줄 건너뛰기)
→ 색차는 2×1 · 1×2 · 2×2 면 libjpeg 와 같은 삼각 보간, 그 밖의 정수비는 최근접으로 늘린다 → YCbCr → RGB → 가장자리를 자른다. 결과는 ascii1_png.Image 와 같다.
progressive · 확장 순차 · 무손실 · 산술 부호화 · 12 비트 · 성분 2 · 4(CMYK) 는 UNSUPPORTED 한 줄로 거부한다.
크기 한도는 SOF 에서 해독 전에 본다. 비트가 모자라거나 부호가 틀리거나 표가 비면 JpegError 하나로만 실패한다
(그 밖의 예외가 새면 버그). 블록마다 쓴 비트를 자료 길이와 맞춰 보므로 깨진 자료로 끝없이 돌지 않는다.
"""
from typing import Dict, List, Optional, Tuple
from math import cos, pi, sqrt

from ascii1_png import MAX_SIDE, Image, PngError

SIGNATURE = b"\xff\xd8\xff"
UNSUPPORTED = "JPEG 이지만 지원하지 않는 형식입니다 (PNG 로 저장해 주세요)"
TRUNCATED = "JPEG 가 끝나지 않았습니다 (잘린 파일)"
BAD_CODE = "JPEG 의 스캔 자료가 깨졌습니다 (허프만 부호가 맞지 않습니다)"
LOOK = 9                                # 룩업 표로 한 번에 푸는 부호 길이
PAD = 1024                              # 스캔 자료 뒤에 붙이는 0 바이트 — 한 블록이 아무리 길어도 이 안에서 끝난다
CLIP_OFF = 1024                         # IDCT 결과를 표로 자를 때의 여유 (이 밖이면 느린 길로 자른다)

ZIGZAG = (0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5, 12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13, 6, 7, 14,
          21, 28, 35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51, 58, 59, 52, 45, 38, 31, 39, 46, 53, 60,
          61, 54, 47, 55, 62, 63)
UNSUPPORTED_SOF = {0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}

# IDCT 기저: K[u][x] = C(u)/2 · cos((2x+1)uπ/16) — f[y][x] = Σv Σu K[v][y] K[u][x] F[v][u]
K = [[(sqrt(0.125) if u == 0 else 0.5) * cos((2 * x + 1) * u * pi / 16) for x in range(8)] for u in range(8)]
CLIP = bytes([max(0, min(255, i - CLIP_OFF)) for i in range(2 * CLIP_OFF + 256)])
BIAS = 128.5 + CLIP_OFF                 # 레벨 이동 + 반올림 + 표 여유
FLAT = [bytes([v]) * 8 for v in range(256)]
MASK = [(1 << s) - 1 for s in range(17)]
HALF = [1 << (s - 1) if s else 0 for s in range(17)]


class JpegError(PngError):
    """읽을 수 없는 JPEG. 앱은 PngError 와 같이 종료 코드 1 로 알린다. 메시지는 한국어 한 줄"""


def _ceil(a: int, b: int) -> int:
    return -(-a // b)


# ─────────────────────────────────────────────────────────────── 표

class Huffman:
    """DHT 의 표 하나. look[9 비트 앞머리] = (길이 << 8) | 값, 0 이면 9 비트보다 긴 부호(또는 없는 부호)"""

    def __init__(self, counts: bytes, values: bytes):
        self.look = [0] * (1 << LOOK)
        self.maxcode = [-1] * 17
        self.mincode = [0] * 17
        self.valptr = [0] * 17
        self.values = values
        code = k = 0
        for length in range(1, 17):
            n = counts[length - 1]
            if n:
                if code + n > (1 << length):
                    raise JpegError("JPEG 의 허프만 표가 잘못됐습니다 (부호가 길이 한도를 넘습니다)")
                self.valptr[length], self.mincode[length] = k, code
                for _ in range(n):
                    if length <= LOOK:
                        shift = LOOK - length
                        entry = (length << 8) | values[k]
                        base = code << shift
                        self.look[base:base + (1 << shift)] = [entry] * (1 << shift)
                    code += 1
                    k += 1
                self.maxcode[length] = code - 1
            code <<= 1

    def slow(self, bits16: int) -> Tuple[int, int]:
        """16 비트 앞머리 → (길이, 값). 맞는 부호가 없으면 JpegError (부록 F.16 의 순서 찾기)"""
        for length in range(1, 17):
            code = bits16 >> (16 - length)
            if code <= self.maxcode[length] and code >= self.mincode[length]:
                return length, self.values[self.valptr[length] + code - self.mincode[length]]
        raise JpegError(BAD_CODE)


class Component:
    def __init__(self, cid: int, h: int, v: int, tq: int):
        self.cid, self.h, self.v, self.tq = cid, h, v, tq
        self.plane: Optional[bytearray] = None
        self.stride = 0
        self.scanned = False


class Frame:
    def __init__(self, width: int, height: int, comps: List[Component]):
        self.width, self.height, self.comps = width, height, comps
        self.hmax = max(c.h for c in comps)
        self.vmax = max(c.v for c in comps)
        self.mcux = _ceil(width, 8 * self.hmax)
        self.mcuy = _ceil(height, 8 * self.vmax)


# ─────────────────────────────────────────────────────────────── 표지 조각

def _dqt(body: bytes, tables: Dict[int, List[int]]) -> None:
    i = 0
    if not body:
        raise JpegError("JPEG 의 양자화 표(DQT)가 비어 있습니다")
    while i < len(body):
        pq, tq = body[i] >> 4, body[i] & 15
        if pq > 1 or tq > 3:
            raise JpegError("JPEG 의 양자화 표(DQT)가 잘못됐습니다")
        size = 64 * (pq + 1)
        if i + 1 + size > len(body):
            raise JpegError("JPEG 의 DQT 길이가 맞지 않습니다")
        raw = body[i + 1:i + 1 + size]
        tables[tq] = list(raw) if pq == 0 else [(raw[2 * k] << 8) | raw[2 * k + 1] for k in range(64)]   # 지그재그 순서
        i += 1 + size


def _dht(body: bytes, dc: Dict[int, Huffman], ac: Dict[int, Huffman]) -> None:
    i = 0
    if not body:
        raise JpegError("JPEG 의 허프만 표(DHT)가 비어 있습니다")
    while i < len(body):
        tc, th = body[i] >> 4, body[i] & 15
        if tc > 1 or th > 3:
            raise JpegError("JPEG 의 허프만 표(DHT)가 잘못됐습니다 (표 종류 · 번호)")
        if i + 17 > len(body):
            raise JpegError("JPEG 의 DHT 길이가 맞지 않습니다")
        counts = body[i + 1:i + 17]
        total = sum(counts)
        if i + 17 + total > len(body):
            raise JpegError("JPEG 의 DHT 길이가 맞지 않습니다")
        if total == 0:
            raise JpegError("JPEG 의 허프만 표(DHT)가 비어 있습니다")
        (ac if tc else dc)[th] = Huffman(counts, body[i + 17:i + 17 + total])
        i += 17 + total


def _sof(marker: int, body: bytes) -> Frame:
    if marker in UNSUPPORTED_SOF:
        raise JpegError(UNSUPPORTED)
    if len(body) < 6:
        raise JpegError("JPEG 머리(SOF)의 길이가 맞지 않습니다")
    prec, height, width, nf = body[0], (body[1] << 8) | body[2], (body[3] << 8) | body[4], body[5]
    if prec != 8 or nf in (2, 4) or nf > 4:
        raise JpegError(UNSUPPORTED)
    if nf == 0 or len(body) != 6 + 3 * nf:
        raise JpegError("JPEG 머리(SOF)의 길이가 맞지 않습니다")
    if width < 1 or height < 1:
        raise JpegError("그림 크기가 0 입니다")
    if width > MAX_SIDE or height > MAX_SIDE:
        raise JpegError("그림이 너무 큽니다 (%d×%d — 한 변은 %d 까지)" % (width, height, MAX_SIDE))
    comps = []
    for k in range(nf):
        cid, hv, tq = body[6 + 3 * k], body[7 + 3 * k], body[8 + 3 * k]
        h, v = hv >> 4, hv & 15
        if not (1 <= h <= 4 and 1 <= v <= 4) or tq > 3 or any(c.cid == cid for c in comps):
            raise JpegError("JPEG 머리(SOF)의 성분이 잘못됐습니다")
        comps.append(Component(cid, h, v, tq))
    if nf == 1:                                  # 성분 하나면 표본 비율과 상관없이 블록 하나가 MCU 다
        comps[0].h = comps[0].v = 1
    frame = Frame(width, height, comps)
    if any(frame.hmax % c.h or frame.vmax % c.v for c in comps):
        raise JpegError(UNSUPPORTED)             # 정수비가 아닌 표본 (예: 3×1 과 2×1)
    return frame


# ─────────────────────────────────────────────────────────────── 스캔

def _scan_extent(data: bytes, pos: int) -> Tuple[int, List[int]]:
    """엔트로피 자료의 끝(다음 표지의 FF 자리, 없으면 파일 끝)과 그 안의 RSTn 자리 목록"""
    n, cuts, i = len(data), [], pos
    while True:
        j = data.find(b"\xff", i)
        if j < 0 or j + 1 >= n:
            return n, cuts
        k = j
        while k + 1 < n and data[k + 1] == 0xFF:  # 표지 앞의 채움 FF
            k += 1
        if k + 1 >= n:
            return j, cuts
        b = data[k + 1]
        if b == 0 and k == j:
            i = j + 2
        elif 0xD0 <= b <= 0xD7:
            cuts.append(j)
            i = k + 2
        elif b == 0:
            i = k + 2
        else:
            return j, cuts


def _store(plane: bytearray, off: int, stride: int, out: List[float]) -> None:
    """IDCT 결과 64 값 → 판의 8×8 자리 (0–255 로 자른다)"""
    lo, hi = min(out), max(out)
    if lo > -CLIP_OFF and hi < CLIP_OFF:
        pix = bytes([CLIP[int(o + BIAS)] for o in out])
    else:
        pix = bytes([0 if o < -128.0 else 255 if o >= 127.0 else int(o + 128.5) for o in out])
    for y in range(8):
        plane[off:off + 8] = pix[8 * y:8 * y + 8]
        off += stride


def _idct(coefs: List[Tuple[int, float]]) -> List[float]:
    """0 이 아닌 (자연 순서 번호, 값) 목록 → 64 값 (레벨 이동 전). 줄마다 가로로 풀고, 줄의 세로 기저와 곱해 더한다"""
    rows: Dict[int, List[float]] = {}
    for i, val in coefs:
        v, u = i >> 3, i & 7
        r = rows.get(v)
        ku = K[u]
        if r is None:
            rows[v] = [val * b for b in ku]
        else:
            rows[v] = [a + val * b for a, b in zip(r, ku)]
    out: Optional[List[float]] = None
    for v, r in rows.items():
        part = [a * b for b in K[v] for a in r]
        out = part if out is None else [a + b for a, b in zip(out, part)]
    return out  # type: ignore[return-value]


def _decode_scan(frame: Frame, scomps: List[Tuple[Component, Huffman, Huffman, List[int]]], data: bytes, pos: int,
                 interval: int) -> int:
    """SOS 머리 뒤의 엔트로피 자료를 풀어 성분 판에 쓴다 → 다음 표지의 자리"""
    end, cuts = _scan_extent(data, pos)
    if len(scomps) == 1:                         # 비인터리브: 그 성분의 블록 격자 그대로
        c = scomps[0][0]
        mcux = _ceil(_ceil(frame.width * c.h, frame.hmax), 8)
        mcuy = _ceil(_ceil(frame.height * c.v, frame.vmax), 8)
        units = [(scomps[0], 1, 1)]
    else:
        mcux, mcuy = frame.mcux, frame.mcuy
        units = [(s, s[0].h, s[0].v) for s in scomps]
    total = mcux * mcuy
    every = interval or total
    starts = [pos] + [c + 2 for c in cuts]
    stops = cuts + [end]
    if not interval:
        starts, stops = starts[:1], stops[:1]
    zz = ZIGZAG
    for part in range(_ceil(total, every)):
        if part >= len(starts):
            raise JpegError(TRUNCATED if end >= len(data) else "JPEG 의 재시작 표지(RST)가 모자랍니다")
        if part and data[cuts[part - 1] + 1] != 0xD0 + ((part - 1) & 7):
            raise JpegError("JPEG 의 재시작 표지(RST) 순서가 맞지 않습니다")
        raw = data[starts[part]:stops[part]].replace(b"\xff\x00", b"\xff")
        limit = 8 * len(raw)
        buf = raw + bytes(PAD)
        acc = nb = p = 0
        preds = [0] * len(units)
        for mcu in range(part * every, min(total, (part + 1) * every)):
            my, mx = divmod(mcu, mcux)
            for si, ((comp, dct, act, qz), uh, uv) in enumerate(units):
                plane, stride = comp.plane, comp.stride
                dlook, alook = dct.look, act.look
                for by in range(uv):
                    for bx in range(uh):
                        # DC
                        while nb < 32:
                            acc = ((acc & 0xFFFFFFFF) << 8) | buf[p]
                            p += 1
                            nb += 8
                        e = dlook[(acc >> (nb - LOOK)) & 511]
                        if e:
                            nb -= e >> 8
                            s = e & 255
                        else:
                            length, s = dct.slow((acc >> (nb - 16)) & 0xFFFF)
                            nb -= length
                        if s:
                            if s > 11:
                                raise JpegError(BAD_CODE)
                            r = (acc >> (nb - s)) & MASK[s]
                            nb -= s
                            if r < HALF[s]:
                                r -= MASK[s]
                            preds[si] += r
                        dc = preds[si] * qz[0]
                        # AC
                        coefs = None
                        k = 1
                        while k < 64:
                            while nb < 32:
                                acc = ((acc & 0xFFFFFFFF) << 8) | buf[p]
                                p += 1
                                nb += 8
                            e = alook[(acc >> (nb - LOOK)) & 511]
                            if e:
                                nb -= e >> 8
                                rs = e & 255
                            else:
                                length, rs = act.slow((acc >> (nb - 16)) & 0xFFFF)
                                nb -= length
                            s = rs & 15
                            if not s:
                                if rs == 0xF0:
                                    k += 16
                                    continue
                                break
                            k += rs >> 4
                            if k > 63 or s > 10:
                                raise JpegError(BAD_CODE)
                            r = (acc >> (nb - s)) & MASK[s]
                            nb -= s
                            if r < HALF[s]:
                                r -= MASK[s]
                            if coefs is None:
                                coefs = [(0, float(dc))] if dc else []
                            coefs.append((zz[k], float(r * qz[k])))
                            k += 1
                        if 8 * p - nb > limit:
                            raise JpegError(TRUNCATED)
                        off = ((my * uv + by) * 8) * stride + (mx * uh + bx) * 8
                        if off >= len(plane) or (mx * uh + bx) * 8 >= stride:
                            continue                 # 비인터리브 스캔의 블록이 판 밖 (있을 수 없지만 지킨다)
                        if coefs:
                            _store(plane, off, stride, _idct(coefs))
                        else:
                            v = int(dc / 8.0 + 128.5) if -1024 < dc < 2048 else (0 if dc < 0 else 255)
                            row = FLAT[0 if v < 0 else 255 if v > 255 else v]
                            for _ in range(8):
                                plane[off:off + 8] = row
                                off += stride
    return end


def _sos(body: bytes, frame: Optional[Frame], dc: Dict[int, Huffman], ac: Dict[int, Huffman],
         quant: Dict[int, List[int]]) -> List[Tuple[Component, Huffman, Huffman, List[int]]]:
    if frame is None:
        raise JpegError("JPEG 머리(SOF)가 없습니다")
    if not body or not 1 <= body[0] <= 4 or len(body) != 4 + 2 * body[0]:
        raise JpegError("JPEG 의 스캔 머리(SOS)가 잘못됐습니다")
    ns = body[0]
    ss, se, a = body[1 + 2 * ns], body[2 + 2 * ns], body[3 + 2 * ns]
    if ss != 0 or se != 63 or a != 0:
        raise JpegError("JPEG 의 스캔 머리(SOS)가 잘못됐습니다")
    out = []
    for k in range(ns):
        cid, t = body[1 + 2 * k], body[2 + 2 * k]
        comp = next((c for c in frame.comps if c.cid == cid), None)
        if comp is None or any(o[0] is comp for o in out):
            raise JpegError("JPEG 의 스캔 머리(SOS)가 없는 성분을 가리킵니다")
        if comp.scanned:
            raise JpegError("JPEG 의 스캔이 같은 성분을 두 번 담았습니다")
        if (t >> 4) not in dc or (t & 15) not in ac:
            raise JpegError("JPEG 에 허프만 표(DHT)가 없습니다")
        if comp.tq not in quant:
            raise JpegError("JPEG 에 양자화 표(DQT)가 없습니다")
        out.append((comp, dc[t >> 4], ac[t & 15], list(quant[comp.tq])))
    return out


# ─────────────────────────────────────────────────────────────── 색

def _wide2(c: List[int], n: int, w: int, b_even: int, b_odd: int, shift: int, edge: int) -> bytes:
    """가로 2 배 삼각 보간 (libjpeg 의 fancy upsampling 과 같은 셈). c 는 n 개의 (세로 합친) 값"""
    even = [(edge * c[0] + b_even) >> shift] + [(3 * a + b + b_even) >> shift for a, b in zip(c[1:], c[:-1])]
    odd = [(3 * a + b + b_odd) >> shift for a, b in zip(c[:-1], c[1:])] + [(edge * c[n - 1] + b_odd) >> shift]
    out = bytearray(2 * n)
    out[0::2], out[1::2] = bytes(even), bytes(odd)
    return bytes(out[:w])


def _full_rows(frame: Frame, comp: Component) -> List[bytes]:
    """성분 판 → 그림 크기의 줄 목록 (가장자리를 자른다). 2×1 · 1×2 · 2×2 는 libjpeg 와 같은 삼각 보간,
    그 밖의 정수비는 최근접으로 늘린다. 보간의 가장자리는 판의 채움 블록이 아니라 실제 표본의 끝 줄 · 끝 칸을 되풀이한다"""
    fx, fy = frame.hmax // comp.h, frame.vmax // comp.v
    w, plane, stride = frame.width, comp.plane, comp.stride
    n = _ceil(w, fx)
    if fx <= 2 and fy <= 2 and (fx, fy) != (1, 1) and (fx == 1 or n > 2):    # libjpeg 도 표본 폭 2 이하면 되풀이만 한다
        last = _ceil(frame.height, fy) - 1
        src = [bytes(plane[r * stride:r * stride + n]) for r in range(last + 1)]
        out = []
        for y in range(frame.height):
            if fy == 1:
                out.append(_wide2(list(src[y]), n, w, 1, 2, 2, 4))
                continue
            r = y >> 1
            cur, near = src[r], src[max(0, r - 1) if y % 2 == 0 else min(last, r + 1)]
            col = [3 * a + b for a, b in zip(cur, near)]
            if fx == 1:
                bias = 1 if y % 2 == 0 else 2
                out.append(bytes([(v + bias) >> 2 for v in col]))
            else:
                out.append(_wide2(col, n, w, 8, 7, 4, 4))
        return out
    rows, cache = [], {}
    for y in range(frame.height):
        sy = y // fy
        row = cache.get(sy)
        if row is None:
            src = plane[sy * stride:sy * stride + _ceil(w, fx)]
            if fx == 1:
                row = bytes(src)
            else:
                wide = bytearray(len(src) * fx)
                for k in range(fx):
                    wide[k::fx] = src
                row = bytes(wide[:w])
            cache = {sy: row}
        rows.append(row)
    return rows


def _tables():
    """YCbCr → RGB 정수 표 (libjpeg 의 16 비트 고정 소수점과 같은 반올림)"""
    one = 1 << 16
    cr_r = [256 + ((int(1.40200 * one + 0.5) * (c - 128) + one // 2) >> 16) for c in range(256)]
    cb_b = [256 + ((int(1.77200 * one + 0.5) * (c - 128) + one // 2) >> 16) for c in range(256)]
    cb_g = [-int(0.34414 * one + 0.5) * (c - 128) + one // 2 + (256 << 16) for c in range(256)]
    cr_g = [-int(0.71414 * one + 0.5) * (c - 128) for c in range(256)]
    clamp = bytes([max(0, min(255, i - 256)) for i in range(256 * 3 + 256)])
    return cr_r, cb_b, cb_g, cr_g, clamp


_COLOR = None


def _to_rgb(frame: Frame, rgb_planes: bool) -> bytes:
    global _COLOR
    w, h = frame.width, frame.height
    out = bytearray(3 * w * h)
    if len(frame.comps) == 1:
        for y, g in enumerate(_full_rows(frame, frame.comps[0])):
            base = 3 * w * y
            out[base:base + 3 * w:3] = g
            out[base + 1:base + 3 * w:3] = g
            out[base + 2:base + 3 * w:3] = g
        return bytes(out)
    if _COLOR is None:
        _COLOR = _tables()
    cr_r, cb_b, cb_g, cr_g, cl = _COLOR
    ys, cbs, crs = (_full_rows(frame, c) for c in frame.comps)
    for y in range(h):
        yr, cb, cr = ys[y], cbs[y], crs[y]
        base = 3 * w * y
        if rgb_planes:
            r, g, b = yr, cb, cr
        else:
            r = bytes([cl[a + cr_r[c]] for a, c in zip(yr, cr)])
            g = bytes([cl[a + ((cb_g[c] + cr_g[d]) >> 16)] for a, c, d in zip(yr, cb, cr)])
            b = bytes([cl[a + cb_b[c]] for a, c in zip(yr, cb)])
        out[base:base + 3 * w:3] = r
        out[base + 1:base + 3 * w:3] = g
        out[base + 2:base + 3 * w:3] = b
    return bytes(out)


# ─────────────────────────────────────────────────────────────── 위

def decode(data: bytes) -> Image:
    """JPEG 바이트 → Image. 읽을 수 없으면 JpegError (PngError 의 한 갈래)"""
    if data[:3] != SIGNATURE:
        raise JpegError("JPEG 가 아닙니다")
    n = len(data)
    pos = 2
    frame: Optional[Frame] = None
    quant: Dict[int, List[int]] = {}
    dc: Dict[int, Huffman] = {}
    ac: Dict[int, Huffman] = {}
    interval = 0
    adobe: Optional[int] = None
    jfif = False
    scans = 0
    while True:
        if pos >= n:
            if frame is not None and scans and all(c.scanned for c in frame.comps):
                break                            # EOI 없이 끝난 파일 — 자료는 다 있다
            raise JpegError(TRUNCATED)
        if data[pos] != 0xFF:
            raise JpegError("JPEG 의 표지 자리에 다른 값이 있습니다 (깨진 파일)")
        while pos < n and data[pos] == 0xFF:
            pos += 1
        if pos >= n:
            raise JpegError(TRUNCATED)
        marker = data[pos]
        pos += 1
        if marker == 0xD9:
            break
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            continue                             # 길이 없는 표지 (SOI 중복 · TEM · 스캔 밖의 RST) 는 건너뛴다
        if marker == 0x00:
            raise JpegError("JPEG 의 표지 자리에 다른 값이 있습니다 (깨진 파일)")
        if pos + 2 > n:
            raise JpegError(TRUNCATED)
        length = (data[pos] << 8) | data[pos + 1]
        if length < 2:
            raise JpegError("JPEG 의 표지 길이가 잘못됐습니다 (FF%02X)" % marker)
        if pos + length > n:
            raise JpegError(TRUNCATED)
        body = data[pos + 2:pos + length]
        pos += length
        if marker == 0xDB:
            _dqt(body, quant)
        elif marker == 0xC4:
            _dht(body, dc, ac)
        elif marker == 0xDD:
            if len(body) != 2:
                raise JpegError("JPEG 의 재시작 간격(DRI)이 잘못됐습니다")
            interval = (body[0] << 8) | body[1]
        elif 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            if frame is not None:
                raise JpegError("JPEG 머리(SOF)가 둘 있습니다")
            frame = _sof(marker, body)
        elif marker in (0xCC, 0xDE, 0xDF, 0xDC):
            raise JpegError(UNSUPPORTED)         # 산술 부호화 표 · 계층 · DNL
        elif marker == 0xE0:
            jfif = jfif or body[:5] == b"JFIF\x00"
        elif marker == 0xEE:
            if body[:5] == b"Adobe" and len(body) >= 12:
                adobe = body[11]
        elif marker == 0xDA:
            scomps = _sos(body, frame, dc, ac, quant)
            assert frame is not None
            if len(frame.comps) == 3 and adobe not in (None, 0, 1):
                raise JpegError(UNSUPPORTED)
            for c, _, _, _ in scomps:
                if c.plane is None:
                    c.stride = frame.mcux * c.h * 8
                    c.plane = bytearray(c.stride * frame.mcuy * c.v * 8)
            pos = _decode_scan(frame, scomps, data, pos, interval)
            for c, _, _, _ in scomps:
                c.scanned = True
            scans += 1
        # 그 밖의 APPn · COM · 예약 표지는 길이만큼 건너뛴다
    if frame is None:
        raise JpegError("JPEG 머리(SOF)가 없습니다")
    if not scans:
        raise JpegError("JPEG 에 스캔 자료가 없습니다")
    if not all(c.scanned for c in frame.comps):
        raise JpegError("JPEG 의 스캔 자료가 모자랍니다 (잘린 파일)")
    rgb_planes = len(frame.comps) == 3 and (adobe == 0 or (adobe is None and not jfif
                                                           and [c.cid for c in frame.comps] == [82, 71, 66]))
    return Image(frame.width, frame.height, _to_rgb(frame, rgb_planes))
