# -*- coding: utf-8 -*-
"""ascii1_png - 표준 라이브러리만으로 PNG 를 읽는다 (zlib · struct). 설계서 docs/plans/ascii-1-design.md › ①
그림을 읽는 입구(decode · load)는 시그니처를 보고 JPEG(FF D8 FF)면 ascii1_jpeg 에 넘긴다 — 확장자는 보지 않는다.

지원: 색 유형 0 · 2 · 3 · 4 · 6 · 비트 깊이 1 · 2 · 4 · 8 · 16 · 필터 0–4 · tRNS · Adam7 · 여러 IDAT
알파는 흰 바탕에 합성하고, 16 비트는 위 바이트만 쓴다. 결과는 늘 8 비트 RGB 다.
읽을 수 없으면 PngError 하나로만 실패한다 (그 밖의 예외가 새면 버그).
"""
import os
import struct
import zlib
from itertools import accumulate
from typing import Dict, Iterator, List, Optional, Tuple

SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE = b"\xff\xd8\xff"
MAX_SIDE = 4000                        # 폭 · 높이 각각의 상한
MAX_FILE_BYTES = 64 * 1024 * 1024      # 파일 크기 상한
CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
DEPTHS = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
ADAM7 = ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))


class PngError(ValueError):
    """읽을 수 없는 PNG. 메시지는 사람에게 그대로 보여 줄 한국어 한 줄"""


class Image:
    """width × height 의 RGB. rgb 는 길이 3 * width * height 의 bytes (왼쪽 위부터 행 순서)"""

    def __init__(self, width: int, height: int, rgb: bytes):
        self.width, self.height, self.rgb = width, height, rgb

    def pixel(self, x: int, y: int) -> Tuple[int, int, int]:
        i = 3 * (y * self.width + x)
        return self.rgb[i], self.rgb[i + 1], self.rgb[i + 2]


# ─────────────────────────────────────────────────────────────── 청크

def read_chunks(data: bytes) -> List[Tuple[bytes, bytes]]:
    """[(종류, 내용)] — IEND 까지. 길이 · CRC 가 틀리면 PngError"""
    if data[:8] != SIGNATURE:
        raise PngError("PNG 가 아닙니다")
    chunks, pos = [], 8
    while True:
        if pos + 8 > len(data):
            raise PngError("PNG 가 끝나지 않았습니다 (잘린 파일)")
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        end = pos + 8 + length
        if end + 4 > len(data):
            raise PngError("PNG 가 끝나지 않았습니다 (잘린 파일)")
        body = data[pos + 8:end]
        if struct.unpack(">I", data[end:end + 4])[0] != zlib.crc32(kind + body) & 0xFFFFFFFF:
            raise PngError("PNG 의 %s 청크가 깨졌습니다 (CRC 가 맞지 않습니다)" % kind.decode("latin-1", "replace"))
        chunks.append((kind, body))
        if kind == b"IEND":
            return chunks
        pos = end + 4


def parse_header(chunks: List[Tuple[bytes, bytes]]) -> Dict[str, int]:
    if not chunks or chunks[0][0] != b"IHDR" or len(chunks[0][1]) != 13:
        raise PngError("PNG 머리(IHDR)가 없습니다")
    width, height, depth, ctype, comp, filt, interlace = struct.unpack(">IIBBBBB", chunks[0][1])
    if width < 1 or height < 1:
        raise PngError("그림 크기가 0 입니다")
    if width > MAX_SIDE or height > MAX_SIDE:
        raise PngError("그림이 너무 큽니다 (%d×%d — 한 변은 %d 까지)" % (width, height, MAX_SIDE))
    if ctype not in DEPTHS or depth not in DEPTHS[ctype]:
        raise PngError("지원하지 않는 색 형식입니다 (색 유형 %d · 비트 깊이 %d)" % (ctype, depth))
    if comp != 0 or filt != 0 or interlace not in (0, 1):
        raise PngError("지원하지 않는 PNG 방식입니다")
    return {"w": width, "h": height, "depth": depth, "ctype": ctype, "interlace": interlace}


# ─────────────────────────────────────────────────────────────── 줄 풀기

def row_bytes(npix: int, depth: int, ctype: int) -> int:
    return (npix * depth * CHANNELS[ctype] + 7) // 8


def passes(h: Dict[str, int]) -> List[Tuple[int, int, int, int, int, int]]:
    """[(가로 칸 수, 줄 수, x 시작, y 시작, x 간격, y 간격)] — 비어 있는 패스는 뺀다"""
    if not h["interlace"]:
        return [(h["w"], h["h"], 0, 0, 1, 1)]
    out = []
    for xs, ys, dx, dy in ADAM7:
        pw, ph = (h["w"] - xs + dx - 1) // dx, (h["h"] - ys + dy - 1) // dy
        if pw > 0 and ph > 0:
            out.append((pw, ph, xs, ys, dx, dy))
    return out


def unfilter(raw: bytes, pos: int, nrows: int, rowlen: int, bpp: int) -> Iterator[bytearray]:
    """필터를 푼 줄을 하나씩 내준다. raw[pos:] 는 (필터 바이트 + rowlen) × nrows"""
    prev = bytearray(rowlen)
    for _ in range(nrows):
        ftype = raw[pos]
        cur = bytearray(raw[pos + 1:pos + 1 + rowlen])
        pos += rowlen + 1
        if ftype == 1:
            for c in range(min(bpp, rowlen)):
                cur[c::bpp] = bytes(accumulate(cur[c::bpp], lambda a, b: (a + b) & 255))
        elif ftype == 2:
            cur = bytearray((a + b) & 255 for a, b in zip(cur, prev))
        elif ftype == 3:
            for i in range(rowlen):
                left = cur[i - bpp] if i >= bpp else 0
                cur[i] = (cur[i] + ((left + prev[i]) >> 1)) & 255
        elif ftype == 4:
            for i in range(rowlen):
                if i >= bpp:
                    a, c = cur[i - bpp], prev[i - bpp]
                else:
                    a = c = 0
                b = prev[i]
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                cur[i] = (cur[i] + pred) & 255
        elif ftype != 0:
            raise PngError("알 수 없는 줄 필터입니다 (%d)" % ftype)
        yield cur
        prev = cur


# ─────────────────────────────────────────────────────────────── 줄 → RGB

def _unpack(row: bytearray, npix: int, depth: int) -> bytes:
    """1 · 2 · 4 비트 값을 칸마다 한 바이트로 푼다 (원래 값 그대로)"""
    per = 8 // depth
    mask = (1 << depth) - 1
    table = _UNPACK[depth]
    if table is None:
        table = _UNPACK[depth] = [bytes(((x >> (8 - depth * (k + 1))) & mask) for k in range(per)) for x in range(256)]
    return b"".join([table[x] for x in row])[:npix]


_UNPACK: Dict[int, Optional[List[bytes]]] = {1: None, 2: None, 4: None}


def _over_white(c: bytes, a: bytes) -> bytes:
    """색 c 를 투명도 a 로 흰 바탕에 올린다"""
    if a.count(255) == len(a):
        return c
    return bytes([(x * y + 255 * (255 - y) + 127) // 255 for x, y in zip(c, a)])


def _interleave(r: bytes, g: bytes, b: bytes) -> bytes:
    out = bytearray(3 * len(r))
    out[0::3], out[1::3], out[2::3] = r, g, b
    return bytes(out)


class Decoder:
    """머리 · 팔레트 · tRNS 를 들고 줄 하나를 RGB 로 바꾼다"""

    def __init__(self, h: Dict[str, int], palette: Optional[bytes], trns: Optional[bytes]):
        self.depth, self.ctype = h["depth"], h["ctype"]
        self.key = None            # 투명색 키 (색 유형 0 · 2) — 원래 비트 깊이의 값
        self.pal_r = self.pal_g = self.pal_b = self.pal_n = None
        if self.ctype == 3:
            if not palette or len(palette) % 3 or len(palette) > 3 * 256:
                raise PngError("팔레트(PLTE)가 없거나 잘못됐습니다")
            n = len(palette) // 3
            alpha = bytes(trns[:n]) + b"\xff" * (n - len(trns[:n])) if trns else b"\xff" * n
            cols = [bytes(palette[0::3]), bytes(palette[1::3]), bytes(palette[2::3])]
            cols = [_over_white(c, alpha) for c in cols]
            pad = bytes(256 - n)
            self.pal_r, self.pal_g, self.pal_b = (bytes(c) + pad for c in cols)
            self.pal_n = n
        elif trns:
            want = 2 if self.ctype == 0 else 6 if self.ctype == 2 else 0
            if want and len(trns) >= want:
                self.key = struct.unpack(">%dH" % (want // 2), trns[:want])

    def rgb(self, row: bytearray, npix: int) -> bytes:
        d, ct = self.depth, self.ctype
        if ct == 3:
            idx = bytes(row[:npix]) if d == 8 else _unpack(row, npix, d)
            if idx and max(idx) >= self.pal_n:
                raise PngError("팔레트 밖의 색 번호가 있습니다")
            return _interleave(idx.translate(self.pal_r), idx.translate(self.pal_g), idx.translate(self.pal_b))
        if ct == 0:
            raw = _unpack(row, npix, d) if d < 8 else (bytes(row[:npix]) if d == 8 else bytes(row[0:2 * npix:2]))
            g = bytes([v * 255 // ((1 << d) - 1) for v in raw]) if d < 8 else raw
            if self.key is not None:
                if d == 16:
                    wide = struct.unpack(">%dH" % npix, bytes(row[:2 * npix]))
                    a = bytes([0 if v == self.key[0] else 255 for v in wide])
                else:
                    a = bytes([0 if v == self.key[0] else 255 for v in raw])
                g = _over_white(g, a)
            return _interleave(g, g, g)
        step = 1 if d == 8 else 2        # 16 비트면 한 값이 두 바이트 — 위 바이트만
        n = {2: 3, 4: 2, 6: 4}[ct]
        ch = [bytes(row[k * step:n * step * npix:n * step]) for k in range(n)]
        if ct == 4:
            g = _over_white(ch[0], ch[1])
            return _interleave(g, g, g)
        if ct == 6:
            return _interleave(*(_over_white(c, ch[3]) for c in ch[:3]))
        rgb = _interleave(*ch)
        if self.key is not None:
            if d == 16:
                wide = struct.unpack(">%dH" % (3 * npix), bytes(row[:6 * npix]))
                hit = [wide[3 * i:3 * i + 3] == self.key for i in range(npix)]
            else:
                hit = [tuple(rgb[3 * i:3 * i + 3]) == self.key for i in range(npix)]
            if any(hit):
                out = bytearray(rgb)
                for i, t in enumerate(hit):
                    if t:
                        out[3 * i:3 * i + 3] = b"\xff\xff\xff"
                return bytes(out)
        return rgb


# ─────────────────────────────────────────────────────────────── 위

def decode(data: bytes) -> Image:
    """PNG 또는 JPEG 바이트 → Image (시그니처로 가른다). 읽을 수 없으면 PngError (JPEG 는 그 갈래인 JpegError)"""
    if data[:3] == JPEG_SIGNATURE:
        import ascii1_jpeg                   # 서로 부르는 모듈이라 쓸 때 불러온다 (ascii1_jpeg 가 Image · PngError 를 쓴다)
        return ascii1_jpeg.decode(data)
    chunks = read_chunks(data)
    h = parse_header(chunks)
    palette = trns = None
    idat = []
    seen_idat = False
    for kind, body in chunks[1:]:
        if kind == b"IDAT":
            idat.append(body)
            seen_idat = True
        elif kind == b"PLTE" and not seen_idat:
            palette = body
        elif kind == b"tRNS" and not seen_idat:
            trns = body
        elif kind[0:1].isupper() and kind not in (b"IEND", b"PLTE", b"tRNS"):
            raise PngError("알 수 없는 필수 청크가 있습니다 (%s)" % kind.decode("latin-1", "replace"))
    if not idat:
        raise PngError("그림 데이터(IDAT)가 없습니다")
    plan = passes(h)
    depth, ctype = h["depth"], h["ctype"]
    sizes = [ph * (1 + row_bytes(pw, depth, ctype)) for pw, ph, _, _, _, _ in plan]
    total = sum(sizes)
    inflater = zlib.decompressobj()
    try:                                      # 헤더로 계산한 크기만큼만 푼다 (압축 폭탄 방어)
        raw = inflater.decompress(b"".join(idat), total + 1)
    except zlib.error:
        raise PngError("그림 데이터의 압축이 깨졌습니다")
    if len(raw) > total:
        raise PngError("그림 데이터가 머리에 적힌 크기보다 큽니다")
    if len(raw) < total:
        raise PngError("그림 데이터가 모자랍니다 (잘린 파일)")
    dec = Decoder(h, palette, trns)
    w, ht = h["w"], h["h"]
    bpp = max(1, depth * CHANNELS[ctype] // 8)
    out = bytearray(3 * w * ht)
    pos = 0
    for (pw, ph, xs, ys, dx, dy), size in zip(plan, sizes):
        rowlen = row_bytes(pw, depth, ctype)
        for r, row in enumerate(unfilter(raw, pos, ph, rowlen, bpp)):
            rgb = dec.rgb(row, pw)
            y = ys + r * dy
            if dx == 1:
                out[3 * y * w:3 * (y * w + w)] = rgb
            else:
                base, stop = 3 * (y * w + xs), 3 * (y * w + w)
                for k in range(3):
                    out[base + k:stop:3 * dx] = rgb[k::3]
        pos += size
    return Image(w, ht, bytes(out))


def load(path: str) -> Image:
    """파일 → Image. 열 수 없거나 너무 크면 PngError"""
    try:
        if os.path.getsize(path) > MAX_FILE_BYTES:
            raise PngError("파일이 너무 큽니다 (%d MB 까지)" % (MAX_FILE_BYTES // (1024 * 1024)))
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        raise PngError("파일을 열 수 없습니다 (%s)" % e.__class__.__name__)
    return decode(data)
