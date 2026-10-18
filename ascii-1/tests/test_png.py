# -*- coding: utf-8 -*-
"""ascii1_png 테스트 — 모든 색 형식 · 비트 깊이 · 필터 · Adam7 왕복, 깨진 PNG 는 PngError 로만 끝나는지. 그림은 전부 코드로 만든 것 (W-12)"""
import os
import random
import struct
import sys
import tempfile
import tracemalloc
import unittest
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import ascii1_png as ap  # noqa: E402
import pngenc as pe  # noqa: E402

SIZES = [(1, 1), (2, 3), (5, 5), (9, 7), (17, 2)]      # 8 의 배수가 아닌 크기 — 비트 묶음 · Adam7 빈 패스를 건드린다


def make(w, h, ctype, depth, rng, trns_kind=None):
    """(rows, palette, trns 인자, 기대 trns) — 칸마다 임의 값. trns_kind: 'alpha' | 'key' | None"""
    top = 1 << depth
    palette = trns = expect = None
    if ctype == 3:
        palette = [tuple(rng.randrange(256) for _ in range(3)) for _ in range(min(top, 7))]
        rows = [[(rng.randrange(len(palette)),) for _ in range(w)] for _ in range(h)]
        if trns_kind == "alpha":
            expect = [rng.choice((0, 255, 77, 128)) for _ in range(max(1, len(palette) - 1))]
            trns = bytes(expect)
        return rows, palette, trns, expect
    rows = [[tuple(rng.randrange(top) for _ in range(pe.CHANNELS[ctype])) for _ in range(w)] for _ in range(h)]
    if ctype in (4, 6):                                  # 알파는 0 · 255 · 중간값이 섞이게
        a = pe.CHANNELS[ctype] - 1
        rows = [[px[:a] + (rng.choice((0, top - 1, top // 2, rng.randrange(top))),) for px in r] for r in rows]
    if trns_kind == "key" and ctype in (0, 2):
        expect = rows[0][0][0] if ctype == 0 else rows[0][0]
        trns = struct.pack(">H", expect) if ctype == 0 else struct.pack(">3H", *expect)
    return rows, palette, trns, expect


def want(rows, ctype, depth, palette, expect):
    return b"".join(bytes(pe.expected_rgb(px, ctype, depth, palette, expect)) for r in rows for px in r)


class Roundtrip(unittest.TestCase):
    def check(self, w, h, ctype, depth, seed, **kw):
        rng = random.Random(seed)
        rows, palette, trns, expect = make(w, h, ctype, depth, rng, kw.pop("trns_kind", None))
        data = pe.encode(w, h, ctype, depth, rows, palette=palette, trns=trns, **kw)
        img = ap.decode(data)
        self.assertEqual((img.width, img.height), (w, h))
        self.assertEqual(img.rgb, want(rows, ctype, depth, palette, expect),
                         "색 유형 %d · 비트 %d · %dx%d · %s" % (ctype, depth, w, h, kw))

    def test_all_formats_plain(self):
        for ctype, depth in pe.COMBOS:
            for w, h in SIZES:
                with self.subTest(ctype=ctype, depth=depth, size=(w, h)):
                    self.check(w, h, ctype, depth, 1000 * ctype + depth + w)

    def test_all_formats_adam7(self):
        for ctype, depth in pe.COMBOS:
            for w, h in SIZES + [(8, 8), (3, 1), (1, 9)]:
                with self.subTest(ctype=ctype, depth=depth, size=(w, h)):
                    self.check(w, h, ctype, depth, 7 * ctype + depth + h, interlace=1)

    def test_each_filter_alone(self):
        for ft, name in enumerate(("없음", "Sub", "Up", "Average", "Paeth")):
            for ctype, depth in ((2, 8), (6, 8), (0, 1), (3, 4), (0, 16), (2, 16), (4, 8)):
                for interlace in (0, 1):
                    with self.subTest(filter=name, ctype=ctype, depth=depth, interlace=interlace):
                        self.check(9, 7, ctype, depth, ft * 31 + depth, filters=(ft,), interlace=interlace)

    def test_palette_alpha(self):
        for depth in (1, 2, 4, 8):
            with self.subTest(depth=depth):
                self.check(9, 7, 3, depth, depth, trns_kind="alpha")

    def test_transparent_color_key(self):
        for ctype, depth in ((0, 1), (0, 2), (0, 4), (0, 8), (0, 16), (2, 8), (2, 16)):
            for interlace in (0, 1):
                with self.subTest(ctype=ctype, depth=depth, interlace=interlace):
                    self.check(9, 7, ctype, depth, 5 + depth, trns_kind="key", interlace=interlace)

    def test_several_idat_chunks(self):
        for parts in (2, 3, 9):
            with self.subTest(parts=parts):
                self.check(17, 9, 2, 8, parts, idat_parts=parts)

    def test_ancillary_chunks_are_ignored(self):
        extra = [pe.chunk(b"tEXt", b"Comment\x00" + "한글".encode("utf-8")), pe.chunk(b"gAMA", b"\x00\x01\x86\xa0")]
        self.check(5, 5, 2, 8, 3, extra=extra)

    def test_known_pixels(self):
        rows = [[(255, 0, 0, 255), (0, 0, 255, 0)]]       # 불투명 빨강 · 완전 투명 파랑(= 흰 바탕)
        img = ap.decode(pe.encode(2, 1, 6, 8, rows))
        self.assertEqual(img.pixel(0, 0), (255, 0, 0))
        self.assertEqual(img.pixel(1, 0), (255, 255, 255))


class Rejects(unittest.TestCase):
    def png(self):
        rng = random.Random(9)
        rows, _, _, _ = make(5, 5, 2, 8, rng)
        return pe.encode(5, 5, 2, 8, rows)

    def fails(self, data, *words):
        with self.assertRaises(ap.PngError) as cm:
            ap.decode(data)
        for w in words:
            self.assertIn(w, str(cm.exception))

    def test_not_png(self):
        self.fails(b"", "PNG 가 아닙니다")
        self.fails(b"hello world, not a png", "PNG 가 아닙니다")

    def test_jpeg_signature_goes_to_the_jpeg_reader(self):
        # JPEG 를 읽게 되면서 (설계서 03① 의 결정이 바뀜): 시그니처 FF D8 FF 면 PNG 로 거부하지 않고 JPEG 로 읽는다.
        # 이 바이트는 JFIF 머리 뒤가 0 뿐인 깨진 JPEG 라서, JPEG 쪽의 정해진 오류 한 줄로 끝나야 한다
        with self.assertRaises(ap.PngError) as cm:
            ap.decode(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + bytes(50))
        self.assertEqual(cm.exception.__class__.__name__, "JpegError")
        self.assertIn("JPEG", str(cm.exception))
        self.assertNotIn("PNG 가 아닙니다", str(cm.exception))

    def test_truncated_anywhere(self):
        data = self.png()
        for cut in list(range(0, 40)) + [len(data) // 2, len(data) - 13, len(data) - 12, len(data) - 1]:
            with self.subTest(cut=cut):
                self.fails(data[:cut])

    def test_crc_mismatch(self):
        data = bytearray(self.png())
        pos = data.index(b"IDAT") + 6
        data[pos] ^= 0xFF
        self.fails(bytes(data), "CRC")

    def test_header_problems(self):
        self.fails(pe.forge(0, 5, 8, 2), "크기가 0")
        self.fails(pe.forge(5, 0, 8, 2), "크기가 0")
        self.fails(pe.forge(ap.MAX_SIDE + 1, 5, 8, 2), "너무 큽니다")
        self.fails(pe.forge(5, 5, 4, 2), "색 형식")           # RGB 는 4 비트가 없다
        self.fails(pe.forge(5, 5, 8, 1), "색 형식")           # 색 유형 1 은 없다
        self.fails(pe.forge(5, 5, 8, 2, interlace=2), "방식")

    def test_decompression_bomb_is_not_inflated(self):
        # 10×10 RGB 는 310 바이트만 필요한데 1 MB 로 풀리는 데이터
        self.fails(pe.forge(10, 10, 8, 2, idat=b"\x00" * 1_000_000), "큽니다")

    def test_decompression_bomb_memory_stays_small(self):
        # 100 MB 의 0 은 약 100 KB 로 줄어든다. 방어가 없으면 풀다가 100 MB 를 잡는다 — 거부만이 아니라 메모리도 본다
        comp = zlib.compressobj()
        packed = b"".join(comp.compress(b"\x00" * (1 << 20)) for _ in range(100)) + comp.flush()
        data = (pe.SIGNATURE + pe.chunk(b"IHDR", struct.pack(">IIBBBBB", 10, 10, 8, 2, 0, 0, 0))
                + pe.chunk(b"IDAT", packed) + pe.chunk(b"IEND", b""))
        tracemalloc.start()
        try:
            self.fails(data, "큽니다")
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        self.assertLess(peak, 5 * 1024 * 1024, "압축을 푸는 동안 메모리 %d 바이트" % peak)

    def test_huge_claim_with_tiny_data(self):
        self.fails(pe.forge(4000, 4000, 8, 2, idat=b"\x00" * 10), "모자랍니다")

    def test_short_data(self):
        self.fails(pe.forge(10, 10, 8, 2, idat=b"\x00" * 100), "모자랍니다")

    def test_broken_deflate(self):
        data = pe.SIGNATURE + pe.chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)) \
            + pe.chunk(b"IDAT", b"not zlib at all") + pe.chunk(b"IEND", b"")
        self.fails(data, "압축")

    def test_no_idat(self):
        data = pe.SIGNATURE + pe.chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)) + pe.chunk(b"IEND", b"")
        self.fails(data, "IDAT")

    def test_unknown_critical_chunk(self):
        rows, _, _, _ = make(5, 5, 2, 8, random.Random(2))
        self.fails(pe.encode(5, 5, 2, 8, rows, extra=[pe.chunk(b"ZZZZ", b"x")]), "필수 청크")

    def test_missing_palette(self):
        rows, _, _, _ = make(5, 5, 3, 8, random.Random(2))
        self.fails(pe.encode(5, 5, 3, 8, rows, palette=None), "팔레트")

    def test_palette_index_out_of_range(self):
        rows = [[(3,)] * 4] * 2                           # 팔레트는 2 색뿐
        self.fails(pe.encode(4, 2, 3, 8, rows, palette=[(0, 0, 0), (9, 9, 9)]), "팔레트 밖")

    def test_bad_filter_type(self):
        rows = [[(1, 2, 3)] * 3] * 3
        data = pe.encode(3, 3, 2, 8, rows)
        raw = bytearray(zlib.decompress(b"".join(c[1] for c in ap.read_chunks(data) if c[0] == b"IDAT")))
        raw[0] = 9
        self.fails(pe.forge(3, 3, 8, 2, idat=bytes(raw)), "필터")

    def test_load_missing_and_oversized_file(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ap.PngError):
                ap.load(os.path.join(d, "없는 파일.png"))
            path = os.path.join(d, "그림 하나.png")
            with open(path, "wb") as f:
                f.write(self.png())
            self.assertEqual(ap.load(path).width, 5)       # 공백 · 한글 경로
            old, ap.MAX_FILE_BYTES = ap.MAX_FILE_BYTES, 10
            try:
                with self.assertRaises(ap.PngError):
                    ap.load(path)
            finally:
                ap.MAX_FILE_BYTES = old


class Fuzz(unittest.TestCase):
    """무엇을 먹여도 Image 아니면 PngError — 그 밖의 예외가 새면 버그"""

    def run_ok(self, data):
        try:
            ap.decode(data)
        except ap.PngError:
            pass

    def test_flipped_bytes(self):
        rng = random.Random(42)
        rows, palette, trns, _ = make(9, 7, 3, 4, rng, "alpha")
        for interlace in (0, 1):
            base = pe.encode(9, 7, 3, 4, rows, palette=palette, trns=trns, interlace=interlace)
            for _ in range(300):
                data = bytearray(base)
                for _ in range(rng.randrange(1, 4)):
                    data[rng.randrange(len(data))] = rng.randrange(256)
                self.run_ok(bytes(data))

    def test_random_scanlines_with_valid_crc(self):
        rng = random.Random(7)
        for _ in range(300):
            ctype, depth = rng.choice(pe.COMBOS)
            w, h, interlace = rng.randrange(1, 12), rng.randrange(1, 12), rng.randrange(2)
            n = len(pe.scanlines([[(0,) * pe.CHANNELS[ctype]] * w] * h, w, h, ctype, depth, interlace, (0,)))
            raw = bytes(rng.randrange(256) if rng.random() < 0.7 else rng.randrange(5) for _ in range(n))
            data = pe.SIGNATURE + pe.chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, depth, ctype, 0, 0, interlace))
            if ctype == 3:
                data += pe.chunk(b"PLTE", bytes(rng.randrange(256) for _ in range(3 * rng.randrange(1, 5))))
            if rng.random() < 0.3:
                data += pe.chunk(b"tRNS", bytes(rng.randrange(256) for _ in range(rng.randrange(0, 9))))
            data += pe.chunk(b"IDAT", zlib.compress(raw)) + pe.chunk(b"IEND", b"")
            self.run_ok(data)


if __name__ == "__main__":
    unittest.main()
