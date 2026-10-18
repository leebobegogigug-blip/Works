# -*- coding: utf-8 -*-
"""시험용 baseline JPEG 인코더 · 손상 코퍼스 — tests/ 에만 둔다 (W-02: 실행 경로에서 import 하지 않는다)

디코더(ascii1_jpeg)와 코드를 나누지 않고 JPEG 규격(ITU T.81 부록 K 의 표준 표)만 보고 따로 짰다:
순방향 분리형 FDCT(실수) · 2x2 평균 축소 · 허프만 부호는 길이별 개수(BITS)와 값 목록(HUFFVAL)에서 직접 만든다.
"""
import random
import struct
from math import cos, pi, sqrt
from typing import Dict, List, Sequence, Tuple

ZIGZAG = [0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5, 12, 19, 26, 33, 40, 48, 41, 34, 27, 20, 13, 6, 7, 14, 21,
          28, 35, 42, 49, 56, 57, 50, 43, 36, 29, 22, 15, 23, 30, 37, 44, 51, 58, 59, 52, 45, 38, 31, 39, 46, 53, 60, 61,
          54, 47, 55, 62, 63]

# 부록 K.1 — 자연(행) 순서
Q_LUMA = [16, 11, 10, 16, 24, 40, 51, 61, 12, 12, 14, 19, 26, 58, 60, 55, 14, 13, 16, 24, 40, 57, 69, 56, 14, 17, 22, 29,
          51, 87, 80, 62, 18, 22, 37, 56, 68, 109, 103, 77, 24, 35, 55, 64, 81, 104, 113, 92, 49, 64, 78, 87, 103, 121,
          120, 101, 72, 92, 95, 98, 112, 100, 103, 99]
Q_CHROMA = ([17, 18, 24, 47, 99, 99, 99, 99, 18, 21, 26, 66, 99, 99, 99, 99, 24, 26, 56, 99, 99, 99, 99, 99, 47, 66, 99,
             99, 99, 99, 99, 99] + [99] * 32)


def _r(hi: int, lo: int, hi2: int) -> List[int]:
    return list(range(hi * 16 + lo, hi * 16 + hi2 + 1))


def _tail(rows: Sequence[Tuple[int, int, int]]) -> List[int]:
    out: List[int] = []
    for hi, lo, last in rows:
        out += _r(hi, lo, last)
    return out


# 부록 K.3 · K.5 — (길이별 부호 수 16개, 값 목록)
DC_LUMA = ([0, 1, 5, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0], list(range(12)))
DC_CHROMA = ([0, 3, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0], list(range(12)))
AC_LUMA = ([0, 2, 1, 3, 3, 2, 4, 3, 5, 5, 4, 4, 0, 0, 1, 0x7D],
           [0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06, 0x13, 0x51, 0x61, 0x07, 0x22, 0x71,
            0x14, 0x32, 0x81, 0x91, 0xA1, 0x08, 0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72,
            0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28, 0x29, 0x2A]
           + _tail([(3, 4, 10), (4, 3, 10), (5, 3, 10), (6, 3, 10), (7, 3, 10), (8, 3, 10), (9, 2, 10), (10, 2, 10),
                    (11, 2, 10), (12, 2, 10), (13, 2, 10), (14, 1, 10), (15, 1, 10)]))
AC_CHROMA = ([0, 2, 1, 2, 4, 4, 3, 4, 7, 5, 4, 4, 0, 1, 2, 0x77],
             [0x00, 0x01, 0x02, 0x03, 0x11, 0x04, 0x05, 0x21, 0x31, 0x06, 0x12, 0x41, 0x51, 0x07, 0x61, 0x71, 0x13, 0x22,
              0x32, 0x81, 0x08, 0x14, 0x42, 0x91, 0xA1, 0xB1, 0xC1, 0x09, 0x23, 0x33, 0x52, 0xF0, 0x15, 0x62, 0x72, 0xD1,
              0x0A, 0x16, 0x24, 0x34, 0xE1, 0x25, 0xF1, 0x17, 0x18, 0x19, 0x1A, 0x26, 0x27, 0x28, 0x29, 0x2A]
             + _tail([(3, 5, 10), (4, 3, 10), (5, 3, 10), (6, 3, 10), (7, 3, 10), (8, 2, 10), (9, 2, 10), (10, 2, 10),
                      (11, 2, 10), (12, 2, 10), (13, 2, 10), (14, 2, 10), (15, 2, 10)]))
for _bits, _vals in (DC_LUMA, DC_CHROMA, AC_LUMA, AC_CHROMA):
    assert sum(_bits) == len(_vals) and len(set(_vals)) == len(_vals)
assert len(AC_LUMA[1]) == 162 and len(AC_CHROMA[1]) == 162


def code_table(spec: Tuple[Sequence[int], Sequence[int]]) -> Dict[int, Tuple[int, int]]:
    """{값: (부호, 길이)} — 부록 C 의 정규 부호 배정"""
    bits, vals = spec
    out, code, k = {}, 0, 0
    for length in range(1, 17):
        for _ in range(bits[length - 1]):
            out[vals[k]] = (code, length)
            code += 1
            k += 1
        code <<= 1
    return out


def quant_table(base: Sequence[int], quality: int) -> List[int]:
    """자연 순서의 양자화 표 — 품질 1..100 을 libjpeg 방식으로 환산"""
    quality = max(1, min(100, quality))
    scale = 5000 // quality if quality < 50 else 200 - 2 * quality
    return [max(1, min(255, (v * scale + 50) // 100)) for v in base]


_COS = [[(sqrt(0.125) if u == 0 else 0.5) * cos((2 * x + 1) * u * pi / 16) for x in range(8)] for u in range(8)]


def fdct(block: Sequence[float]) -> List[float]:
    """8x8 순방향 DCT — 행 · 열 분리형. block 은 레벨 이동(-128) 된 64 값"""
    tmp = [0.0] * 64
    for y in range(8):
        row = block[8 * y:8 * y + 8]
        for u in range(8):
            c = _COS[u]
            tmp[8 * y + u] = sum(row[x] * c[x] for x in range(8))
    out = [0.0] * 64
    for u in range(8):
        col = [tmp[8 * y + u] for y in range(8)]
        for v in range(8):
            c = _COS[v]
            out[8 * v + u] = sum(col[y] * c[y] for y in range(8))
    return out


class _Bits:
    def __init__(self) -> None:
        self.out = bytearray()
        self.acc = 0
        self.n = 0

    def put(self, code: int, length: int) -> None:
        self.acc = (self.acc << length) | code
        self.n += length
        while self.n >= 8:
            b = (self.acc >> (self.n - 8)) & 255
            self.out.append(b)
            if b == 255:
                self.out.append(0)
            self.n -= 8
        self.acc &= (1 << self.n) - 1

    def flush(self) -> None:
        if self.n:
            self.put((1 << (8 - self.n)) - 1, 8 - self.n)   # 남는 비트는 1 로 채운다


def _bitsize(v: int) -> int:
    return abs(v).bit_length()


def _amp(v: int, size: int) -> int:
    return v if v >= 0 else v + (1 << size) - 1


def _segment(marker: int, body: bytes) -> bytes:
    return struct.pack(">BBH", 255, marker, len(body) + 2) + body


def _dht(cls_id: int, spec: Tuple[Sequence[int], Sequence[int]]) -> bytes:
    return _segment(0xC4, bytes([cls_id]) + bytes(spec[0]) + bytes(spec[1]))


def encode(width: int, height: int, rgb: bytes, quality: int = 75, subsampling: str = "420", restart_interval: int = 0,
           gray: bool = False) -> bytes:
    """rgb 는 길이 3 * width * height. gray=True 면 휘도만 한 성분으로 쓴다. 가장자리 블록은 끝 화소를 되풀이해 채운다"""
    if subsampling not in ("420", "444"):
        raise ValueError("subsampling 은 '420' 또는 '444'")
    if len(rgb) != 3 * width * height or width < 1 or height < 1:
        raise ValueError("크기와 rgb 길이가 맞지 않습니다")
    sub = subsampling == "420" and not gray
    mcu = 16 if sub else 8
    mw, mh = -(-width // mcu), -(-height // mcu)
    pw, ph = mw * mcu, mh * mcu
    yp = [0.0] * (pw * ph)
    cbp = [0.0] * (pw * ph)
    crp = [0.0] * (pw * ph)
    for y in range(ph):
        sy = min(y, height - 1)
        for x in range(pw):
            i = 3 * (sy * width + min(x, width - 1))
            r, g, b = rgb[i], rgb[i + 1], rgb[i + 2]
            yp[y * pw + x] = 0.299 * r + 0.587 * g + 0.114 * b
            cbp[y * pw + x] = -0.168736 * r - 0.331264 * g + 0.5 * b + 128
            crp[y * pw + x] = 0.5 * r - 0.418688 * g - 0.081312 * b + 128
    planes = [(yp, pw, ph, 1, 1)]                          # (판, 폭, 높이, 가로 표본, 세로 표본)
    if not gray:
        if sub:
            half = pw // 2
            cb2 = [(cbp[2 * y * pw + 2 * x] + cbp[2 * y * pw + 2 * x + 1] + cbp[(2 * y + 1) * pw + 2 * x]
                    + cbp[(2 * y + 1) * pw + 2 * x + 1]) / 4 for y in range(ph // 2) for x in range(half)]
            cr2 = [(crp[2 * y * pw + 2 * x] + crp[2 * y * pw + 2 * x + 1] + crp[(2 * y + 1) * pw + 2 * x]
                    + crp[(2 * y + 1) * pw + 2 * x + 1]) / 4 for y in range(ph // 2) for x in range(half)]
            planes += [(cb2, half, ph // 2, 1, 1), (cr2, half, ph // 2, 1, 1)]
        else:
            planes += [(cbp, pw, ph, 1, 1), (crp, pw, ph, 1, 1)]
    ql, qc = quant_table(Q_LUMA, quality), quant_table(Q_CHROMA, quality)
    dc_t = [code_table(DC_LUMA), code_table(DC_CHROMA)]
    ac_t = [code_table(AC_LUMA), code_table(AC_CHROMA)]
    ncomp = len(planes)
    hv = [(2, 2)] + [(1, 1)] * 2 if sub else [(1, 1)] * 3

    head = b"\xff\xd8"
    head += _segment(0xDB, bytes([0]) + bytes(ql[ZIGZAG[i]] for i in range(64)))
    if not gray:
        head += _segment(0xDB, bytes([1]) + bytes(qc[ZIGZAG[i]] for i in range(64)))
    sof = struct.pack(">BHHB", 8, height, width, ncomp)
    for c in range(ncomp):
        sof += bytes([c + 1, hv[c][0] * 16 + hv[c][1], 0 if c == 0 else 1])
    head += _segment(0xC0, sof)
    head += _dht(0x00, DC_LUMA) + _dht(0x10, AC_LUMA)
    if not gray:
        head += _dht(0x01, DC_CHROMA) + _dht(0x11, AC_CHROMA)
    if restart_interval:
        head += _segment(0xDD, struct.pack(">H", restart_interval))
    sos = bytes([ncomp])
    for c in range(ncomp):
        sos += bytes([c + 1, 0x00 if c == 0 else 0x11])
    head += _segment(0xDA, sos + bytes([0, 63, 0]))

    bw = _Bits()
    pred = [0] * ncomp
    count, rst = 0, 0

    def block(ci: int, bx: int, by: int) -> None:
        plane, stride = planes[ci][0], planes[ci][1]
        q = ql if ci == 0 else qc
        t = 0 if ci == 0 else 1
        px = [plane[(by + j) * stride + bx + i] - 128 for j in range(8) for i in range(8)]
        co = fdct(px)
        zz = [int(round(co[ZIGZAG[k]] / q[ZIGZAG[k]])) for k in range(64)]
        d = zz[0] - pred[ci]
        pred[ci] = zz[0]
        s = _bitsize(d)
        bw.put(*dc_t[t][s])
        if s:
            bw.put(_amp(d, s), s)
        run = 0
        last = max([k for k in range(1, 64) if zz[k]] or [0])
        for k in range(1, last + 1):
            v = zz[k]
            if v == 0:
                run += 1
                continue
            while run > 15:
                bw.put(*ac_t[t][0xF0])
                run -= 16
            s = _bitsize(v)
            bw.put(*ac_t[t][run * 16 + s])
            bw.put(_amp(v, s), s)
            run = 0
        if last < 63:
            bw.put(*ac_t[t][0x00])

    for my in range(mh):
        for mx in range(mw):
            if restart_interval and count and count % restart_interval == 0:
                bw.flush()
                bw.out += bytes([255, 0xD0 + rst])
                rst = (rst + 1) & 7
                pred = [0] * ncomp
            count += 1
            if sub:
                for j in range(2):
                    for i in range(2):
                        block(0, mx * 16 + 8 * i, my * 16 + 8 * j)
                block(1, mx * 8, my * 8)
                block(2, mx * 8, my * 8)
            else:
                for ci in range(ncomp):
                    block(ci, mx * 8, my * 8)
    bw.flush()
    return head + bytes(bw.out) + b"\xff\xd9"


def jpeg_of(image, quality: int = 75, subsampling: str = "420", restart_interval: int = 0) -> bytes:
    """ascii1_png.Image 꼴(.width .height .rgb) 의 합성 그림을 JPEG 바이트로"""
    return encode(image.width, image.height, image.rgb, quality, subsampling, restart_interval)


# ───────────────────────────────────────────────────────────── 구조 읽기 · 손상 코퍼스

def split_segments(data: bytes) -> List[Tuple[int, int, int]]:
    """[(마커, 시작, 끝)] — SOI 부터 SOS 머리까지의 표지 조각. 끝은 조각 바로 뒤. SOS 조각 뒤의 자료 · EOI 는 따로 센다"""
    out, pos = [], 2
    out.append((0xD8, 0, 2))
    while pos + 4 <= len(data) and data[pos] == 255:
        marker = data[pos + 1]
        length = struct.unpack(">H", data[pos + 2:pos + 4])[0]
        out.append((marker, pos, pos + 2 + length))
        pos += 2 + length
        if marker == 0xDA:
            break
    return out


def _find(data: bytes, marker: int) -> Tuple[int, int]:
    for m, a, b in split_segments(data):
        if m == marker:
            return a, b
    raise ValueError("표지 없음")


def corrupt_corpus(valid: bytes) -> Dict[str, Tuple[bytes, str]]:
    """{이름: (손상된 바이트, 기대되는 처리)} — valid 는 encode() 가 만든 4:2:0 · 3 성분 baseline JPEG (스캔 자료가 충분히 클 것).
    기대 문구는 '거부' 로 시작하면 정해진 오류(종료 코드 1)여야 하고, '허용 또는 거부' 면 Image 든 정해진 오류든 되지만
    예외 · 무한 루프 · 메모리 폭주는 안 된다"""
    out: Dict[str, Tuple[bytes, str]] = {}
    segs = split_segments(valid)
    sos_a, sos_b = _find(valid, 0xDA)
    sof_a, sof_b = _find(valid, 0xC0)
    dqt_a, dqt_b = _find(valid, 0xDB)
    dht_a, dht_b = _find(valid, 0xC4)
    n = len(valid)

    # 잘림 — 머리 안 · 스캔 안
    for name, cut in (("trunc_0", 0), ("trunc_1", 1), ("trunc_soi", 2), ("trunc_in_dqt", dqt_a + 10),
                      ("trunc_in_sof", sof_a + 6), ("trunc_in_dht", dht_a + 20), ("trunc_in_sos", sos_a + 5),
                      ("trunc_scan_25", sos_b + (n - sos_b) // 4), ("trunc_scan_50", sos_b + (n - sos_b) // 2),
                      ("trunc_scan_90", sos_b + (n - sos_b) * 9 // 10)):
        out[name] = (valid[:cut], "거부: 파일이 끝나지 않았습니다 (잘린 파일)")

    # 비트 뒤집기 — 고정 시드. 머리 쪽 · 스캔 쪽
    rng = random.Random(20260101)
    for k in range(8):
        for zone, lo, hi in (("head", 2, sos_b), ("scan", sos_b, n - 2)):
            pos, bit = rng.randrange(lo, hi), rng.randrange(8)
            buf = bytearray(valid)
            buf[pos] ^= 1 << bit
            out["flip_%s_%d" % (zone, k)] = (bytes(buf), "허용 또는 거부: 한 비트가 뒤집힘 (Image 또는 정해진 오류)")

    # 표 · 머리
    out["dht_empty"] = (valid[:dht_a] + b"\xff\xc4\x00\x02" + valid[dht_b:], "거부: 비어 있는 허프만 표")
    out["dht_none"] = (b"".join(valid[a:b] for m, a, b in segs if m != 0xC4) + valid[sos_b:], "거부: 허프만 표 없음")
    out["dqt_none"] = (b"".join(valid[a:b] for m, a, b in segs if m != 0xDB) + valid[sos_b:], "거부: 양자화 표 없음")

    def sof_edit(w: int, h: int, prec: int = 8, marker: int = 0xC0) -> bytes:
        buf = bytearray(valid)
        buf[sof_a + 1] = marker
        buf[sof_a + 4] = prec
        struct.pack_into(">HH", buf, sof_a + 5, h, w)
        return bytes(buf)
    out["sof_huge"] = (sof_edit(65535, 65535), "거부: 크기 한도 초과 (4000×4000 넘음), 메모리를 잡기 전에")
    out["sof_wide"] = (sof_edit(60000, 8), "거부: 크기 한도 초과")
    out["sof_zero_w"] = (sof_edit(0, 16), "거부: 가로 0")
    out["sof_zero_h"] = (sof_edit(16, 0), "거부: 세로 0")
    out["sof_zero_both"] = (sof_edit(0, 0), "거부: 크기 0")
    wh = struct.unpack(">HH", valid[sof_a + 7:sof_a + 9] + valid[sof_a + 5:sof_a + 7])        # (가로, 세로)
    out["sof2_progressive"] = (sof_edit(wh[0], wh[1], marker=0xC2), "거부: 지원하지 않는 JPEG (progressive)")
    out["sof1_extended"] = (sof_edit(wh[0], wh[1], marker=0xC1), "거부: 지원하지 않는 JPEG (확장 순차)")
    out["sof9_arithmetic"] = (sof_edit(wh[0], wh[1], marker=0xC9), "거부: 지원하지 않는 JPEG (산술 부호화)")
    out["precision_12"] = (sof_edit(wh[0], wh[1], prec=12), "거부: 지원하지 않는 JPEG (12 비트)")

    # 4 성분 — SOF · SOS 모두 4 성분으로 고쳐 쓴다 (CMYK 꼴)
    comps = valid[sof_a + 10:sof_b]
    sof4 = valid[sof_a + 4:sof_a + 9] + bytes([4]) + comps + bytes([4, 0x11, 1])
    sos_body = valid[sos_a + 4:sos_b]
    sos4 = bytes([4]) + sos_body[1:7] + bytes([4, 0x11]) + sos_body[7:]
    out["four_components"] = (valid[:sof_a] + _segment(0xC0, sof4) + valid[sof_b:sos_a] + _segment(0xDA, sos4)
                              + valid[sos_b:], "거부: 지원하지 않는 JPEG (4 성분, CMYK)")
    out["sof_comp_mismatch"] = (valid[:sof_a + 9] + b"\x02" + valid[sof_a + 10:], "거부: 성분 수가 SOS 와 맞지 않음")

    # 길이 거짓
    for name, delta in (("dqt_len_long", 20), ("dqt_len_short", -30), ("dqt_len_huge", 0x7000)):
        buf = bytearray(valid)
        struct.pack_into(">H", buf, dqt_a + 2, max(0, min(65535, struct.unpack(">H", valid[dqt_a + 2:dqt_a + 4])[0] + delta)))
        out[name] = (bytes(buf), "거부: DQT 길이가 실제와 다름")
    buf = bytearray(valid)
    struct.pack_into(">H", buf, dqt_a + 2, 0)
    out["dqt_len_zero"] = (bytes(buf), "거부: DQT 길이 0 (최소 2)")
    buf = bytearray(valid)
    struct.pack_into(">H", buf, dht_a + 2, struct.unpack(">H", valid[dht_a + 2:dht_a + 4])[0] + 40)
    out["dht_len_long"] = (bytes(buf), "거부: DHT 길이가 실제와 다름")

    # 허프만 표 이상
    buf = bytearray(valid)
    buf[dht_a + 5] = 5                                      # 길이 1 부호 5 개 — 1 비트 부호는 2 개까지
    out["dht_oversubscribed"] = (bytes(buf), "거부: 허프만 부호가 길이 한도를 넘음 (과다 배정)")
    buf = bytearray(valid)
    buf[dht_a + 5 + 16] = 0xFF                              # 길이 16 부호 255 개 — 값 목록이 모자람
    out["dht_count_overrun"] = (bytes(buf), "거부: 부호 수가 DHT 길이를 넘음")
    buf = bytearray(valid)
    buf[dht_a + 4] = 0x44                                   # 표 종류 4 · 번호 4 — 범위 밖
    out["dht_bad_class"] = (bytes(buf), "거부: 허프만 표 종류 · 번호 오류")
    only_long = bytes([0x00]) + bytes([0] * 15 + [1]) + bytes([5])   # 길이 16 짜리 부호 하나뿐 — 스캔의 다른 부호가 해독 불가
    out["dht_sparse"] = (valid[:dht_a] + _segment(0xC4, only_long) + valid[dht_b:], "거부: 해독할 수 없는 허프만 부호")

    # SOS 뒤 자료 없음
    out["sos_no_data"] = (valid[:sos_b] + b"\xff\xd9", "거부: 스캔 자료 없음")
    out["sos_no_data_no_eoi"] = (valid[:sos_b], "거부: 스캔 자료 없음 (잘린 파일)")
    buf = bytearray(valid)
    buf[sos_a + 4] = 0                                      # SOS 성분 0 개
    out["sos_zero_comps"] = (bytes(buf), "거부: SOS 성분 수 오류")
    buf = bytearray(valid)
    buf[sos_a + 5] = 9                                      # 없는 성분 번호
    out["sos_bad_comp"] = (bytes(buf), "거부: SOS 가 없는 성분을 가리킴")

    # 마커 중복
    out["dup_soi"] = (b"\xff\xd8" + valid, "허용 또는 거부: SOI 중복")
    out["dup_sof"] = (valid[:sof_b] + valid[sof_a:sof_b] + valid[sof_b:], "거부: SOF 중복")
    out["dup_sos"] = (valid[:sos_b] + valid[sos_a:sos_b] + valid[sos_b:], "거부: 스캔 둘 (순차 JPEG 는 한 번)")
    out["dup_dri"] = (valid[:sos_a] + b"\xff\xdd\x00\x04\x00\x01" + b"\xff\xdd\x00\x04\x00\x02" + valid[sos_a:],
                      "허용 또는 거부: 재시작 간격이 SOS 전에 바뀜 (간격과 스캔이 맞지 않으면 오류)")
    out["no_sof"] = (valid[:sof_a] + valid[sof_b:], "거부: SOF 없음")
    out["not_jpeg_after_soi"] = (b"\xff\xd8" + bytes(range(64)), "거부: 표지가 아님")
    out["eoi_only"] = (b"\xff\xd8\xff\xd9", "거부: 이미지 없음")
    return out
