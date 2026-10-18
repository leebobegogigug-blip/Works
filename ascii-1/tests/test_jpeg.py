# -*- coding: utf-8 -*-
"""ascii1_jpeg 테스트 — 인코드 → 디코드 왕복 · 표본 비율 · 여러 스캔 · 합성 차트의 요소 구조 · 손상 코퍼스 · 변이 퍼징 · 크기 한도.
JPEG 는 전부 tests/jpegenc.py 로 코드에서 만든다 (표준 라이브러리만 — W-02 · W-11). 기준 디코더 대조는 개발 중에만 했다"""
import faulthandler
import os
import random
import struct
import subprocess
import sys
import tempfile
import time
import tracemalloc
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import ascii1_jpeg as aj  # noqa: E402
import ascii1_png as ap  # noqa: E402
import ascii1_seg as sg  # noqa: E402
import jpegenc as je  # noqa: E402
import synth  # noqa: E402

PER_ITEM_S = 5.0                     # 손상 · 변이 입력 하나가 끝나야 하는 시간
WATCHDOG_S = 120                     # 그래도 멈추면 이 시간 뒤에 스택을 찍고 프로세스를 끝낸다 (CI 가 매달리지 않게)


def mad(a, b):
    """칸 평균 절대차"""
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def scene(w, h, seed=1):
    """매끈한 바탕 + 또렷한 도형 — 사진도 아니고 잡티도 아닌 그림 (JPEG 왕복 오차를 재기 좋다)"""
    rng = random.Random(seed)
    c = synth.Canvas(w, h)
    for y in range(h):
        for x in range(w):
            c.px[y * w + x] = (int(200 + 55 * x / max(1, w - 1)), int(180 + 60 * y / max(1, h - 1)), 230)
    for _ in range(4):
        x, y = rng.randrange(w), rng.randrange(h)
        c.rect(x, y, min(w - 1, x + rng.randrange(3, 12)), min(h - 1, y + rng.randrange(3, 12)),
               (rng.randrange(256), rng.randrange(256), rng.randrange(256)))
    c.disc(w // 2, h // 2, min(w, h) / 4, (30, 60, 160))
    return c.image()


def luma(img):
    return bytes(int(round(0.299 * img.rgb[3 * i] + 0.587 * img.rgb[3 * i + 1] + 0.114 * img.rgb[3 * i + 2]))
                 for i in range(img.width * img.height))


def ycc(img):
    """→ (Y, Cb, Cr) 판 (반올림한 바이트) — 여러 스캔 JPEG 를 손으로 짤 때 쓴다"""
    out = ([], [], [])
    for i in range(img.width * img.height):
        r, g, b = img.rgb[3 * i:3 * i + 3]
        out[0].append(0.299 * r + 0.587 * g + 0.114 * b)
        out[1].append(-0.168736 * r - 0.331264 * g + 0.5 * b + 128)
        out[2].append(0.5 * r - 0.418688 * g - 0.081312 * b + 128)
    return [bytes(max(0, min(255, int(round(v)))) for v in p) for p in out]


def shrink(plane, w, h, fx, fy):
    """판을 fx × fy 칸 평균으로 줄인다 (가장자리는 남은 칸만)"""
    nw, nh = -(-w // fx), -(-h // fy)
    out = bytearray(nw * nh)
    for y in range(nh):
        for x in range(nw):
            vals = [plane[yy * w + xx] for yy in range(y * fy, min(h, y * fy + fy)) for xx in range(x * fx, min(w, x * fx + fx))]
            out[y * nw + x] = int(round(sum(vals) / len(vals)))
    return bytes(out), nw, nh


def multi_scan(img, factors, quality=95):
    """성분마다 따로 스캔한 baseline JPEG (비인터리브 스캔 셋). factors = [(h, v)] 셋 — Y 가 가장 크다.
    각 성분 판을 회색 JPEG 로 부호화해 그 스캔 자료를 이어 붙인다 (표는 셋이 같다: 휘도 표 0 번)"""
    planes = ycc(img)
    hmax, vmax = max(f[0] for f in factors), max(f[1] for f in factors)
    head = tables = None
    scans = []
    for ci, ((h, v), plane) in enumerate(zip(factors, planes)):
        p, pw, ph = shrink(plane, img.width, img.height, hmax // h, vmax // v)
        gray = je.encode(pw, ph, bytes(b for b in p for _ in range(3)), quality, gray=True)
        segs = je.split_segments(gray)
        if tables is None:
            tables = b"".join(gray[a:b] for m, a, b in segs if m in (0xDB, 0xC4))
        sos_b = [b for m, a, b in segs if m == 0xDA][0]
        scans.append(je._segment(0xDA, bytes([1, ci + 1, 0x00, 0, 63, 0])) + gray[sos_b:-2])
    sof = struct.pack(">BHHB", 8, img.height, img.width, 3)
    for ci, (h, v) in enumerate(factors):
        sof += bytes([ci + 1, h * 16 + v, 0])
    head = b"\xff\xd8" + tables + je._segment(0xC0, sof)
    return head + b"".join(scans) + b"\xff\xd9"


class RoundTrip(unittest.TestCase):
    """우리 인코더 → 우리 디코더. 문턱은 잰 값의 1.3 배 남짓 (Linux · Python 3.13 에서 잼). 품질이 낮을수록 양자화 오차가,
    4:2:0 은 작은 원색 도형의 색차를 반으로 줄인 오차가 크다. 같은 파일을 기준 디코더(libjpeg)로 푼 것과는 칸 평균 0.1 이내였다"""

    def check(self, img, limit, **kw):
        data = je.jpeg_of(img, **kw)
        out = ap.decode(data)
        self.assertIsInstance(out, ap.Image)
        self.assertEqual((out.width, out.height, len(out.rgb)), (img.width, img.height, 3 * img.width * img.height))
        self.assertLessEqual(mad(out.rgb, img.rgb), limit)
        return out

    def test_quality_and_subsampling(self):
        img = scene(64, 48)
        for q, sub, limit in ((100, "444", 0.6), (95, "444", 1.6), (75, "444", 4.5), (50, "444", 6.5),   # 0.43 1.19 3.41 5.13
                              (95, "420", 4.0), (75, "420", 7.0), (50, "420", 9.0)):                    # 3.13 5.49 7.15
            with self.subTest(q=q, sub=sub):
                self.check(img, limit, quality=q, subsampling=sub)

    def test_odd_sizes_and_edges(self):
        for w, h in ((1, 1), (7, 3), (17, 9), (33, 31), (8, 16), (16, 8), (1, 40), (41, 1)):
            with self.subTest(size=(w, h)):
                img = scene(w, h, seed=w * 100 + h)
                self.check(img, 1.0, quality=100, subsampling="444")    # 0.28–0.70 — 가장자리 자르기 · 채움 블록이 틀리면 크게 는다
                self.check(img, 22.0, quality=90, subsampling="420")    # 0.67–18.1 — 몇 칸짜리 원색 도형의 색차

    def test_restart_intervals_give_the_same_picture(self):
        img = scene(50, 34)
        plain = ap.decode(je.jpeg_of(img, 80, "420")).rgb
        for ri in (1, 2, 3, 7, 100):
            with self.subTest(restart=ri):
                data = je.jpeg_of(img, 80, "420", ri)
                if ri < 12:
                    self.assertIn(b"\xff\xd0", data)
                self.assertEqual(ap.decode(data).rgb, plain)

    def test_gray(self):
        img = scene(30, 21)
        for q, limit in ((100, 0.4), (90, 2.8), (60, 9.5)):            # 0.23 2.08 7.34
            with self.subTest(q=q):
                out = ap.decode(je.encode(img.width, img.height, img.rgb, q, gray=True))
                self.assertEqual(out.rgb[0::3], out.rgb[1::3])
                self.assertEqual(out.rgb[0::3], out.rgb[2::3])
                self.assertLessEqual(mad(out.rgb[0::3], luma(img)), limit)

    def test_flat_and_saturated(self):
        for col in ((255, 255, 255), (0, 0, 0), (255, 0, 0), (0, 0, 255), (128, 128, 128)):
            with self.subTest(col=col):
                img = ap.Image(19, 13, bytes(col) * (19 * 13))
                out = ap.decode(je.jpeg_of(img, 90, "420"))
                self.assertLessEqual(max(abs(a - b) for a, b in zip(out.rgb, img.rgb)), 6)

    def test_separate_scans_and_other_samplings(self):
        # 성분마다 따로 스캔 (비인터리브 셋) · 표본 1×1 · 2×1 · 1×2 · 2×2 · 4×1 · 1×4 · 3×1(정수비)
        img = scene(37, 29)
        for factors, limit in ((((1, 1),) * 3, 2.0), (((2, 1), (1, 1), (1, 1)), 5.0), (((1, 2), (1, 1), (1, 1)), 5.0),   # 1.54 3.91 3.92
                               (((2, 2), (1, 1), (1, 1)), 7.5), (((4, 1), (1, 1), (1, 1)), 7.0),                  # 5.75 5.52
                               (((1, 4), (1, 1), (1, 1)), 7.0), (((3, 1), (1, 1), (1, 1)), 6.5),                  # 5.37 5.06
                               (((2, 2), (2, 1), (1, 2)), 5.5)):                                                  # 4.07
            with self.subTest(factors=factors):
                out = ap.decode(multi_scan(img, factors))
                self.assertEqual((out.width, out.height), (37, 29))
                self.assertLessEqual(mad(out.rgb, img.rgb), limit)

    def test_non_integer_ratio_is_unsupported(self):
        data = multi_scan(scene(16, 16), ((3, 1), (2, 1), (1, 1)))
        with self.assertRaises(ap.PngError) as cm:
            ap.decode(data)
        self.assertEqual(str(cm.exception), aj.UNSUPPORTED)

    def test_skips_app_and_comment_segments(self):
        img = scene(20, 12)
        data = je.jpeg_of(img, 85, "420")
        extra = (je._segment(0xE0, b"JFIF\x00\x01\x02\x00\x00\x01\x00\x01\x00\x00") + je._segment(0xE1, b"Exif\x00\x00" + bytes(40))
                 + je._segment(0xFE, "지어낸 설명".encode("utf-8")) + je._segment(0xED, bytes(10)))
        self.assertEqual(ap.decode(data[:2] + extra + data[2:]).rgb, ap.decode(data).rgb)

    def test_adobe_transform(self):
        img = scene(16, 16)
        data = je.jpeg_of(img, 90, "444")
        ycc_out = ap.decode(data[:2] + je._segment(0xEE, b"Adobe\x00\x64\x00\x00\x00\x00\x01") + data[2:])
        self.assertEqual(ycc_out.rgb, ap.decode(data).rgb)
        raw = ap.decode(data[:2] + je._segment(0xEE, b"Adobe\x00\x64\x00\x00\x00\x00\x00") + data[2:])
        self.assertNotEqual(raw.rgb, ycc_out.rgb)             # 변환 0 은 성분을 R · G · B 로 그대로 쓴다
        with self.assertRaises(ap.PngError) as cm:
            ap.decode(data[:2] + je._segment(0xEE, b"Adobe\x00\x64\x00\x00\x00\x00\x02") + data[2:])
        self.assertEqual(str(cm.exception), aj.UNSUPPORTED)

    def test_16_bit_quant_tables_and_four_tables(self):
        img = scene(24, 24)
        data = je.jpeg_of(img, 75, "444")
        a, b = [(x, y) for m, x, y in je.split_segments(data) if m == 0xDB][0]
        body = data[a + 4:b]
        wide = bytes([0x10 | body[0]]) + b"".join(struct.pack(">H", v) for v in body[1:65])
        spare = bytes([0x03]) + bytes(range(1, 65))                  # 쓰지 않는 표 3 번도 함께
        changed = data[:a] + je._segment(0xDB, wide + spare) + data[b:]
        self.assertEqual(ap.decode(changed).rgb, ap.decode(data).rgb)

    def test_oversubscribed_huffman_table(self):
        with self.assertRaises(aj.JpegError):
            aj.Huffman(bytes([3] + [0] * 15), bytes(3))               # 1 비트 부호는 둘까지
        aj.Huffman(bytes([2] + [0] * 15), bytes(2))

    def test_missing_eoi_is_accepted_when_the_scan_is_complete(self):
        img = scene(20, 20)
        data = je.jpeg_of(img, 80, "420")
        self.assertEqual(ap.decode(data[:-2]).rgb, ap.decode(data).rgb)


class Structure(unittest.TestCase):
    """합성 차트 · 웨이퍼를 JPEG 로 만들어 읽으면 PNG 판과 같은 요소 구조가 나온다"""

    def summary(self, img):
        seg = sg.segment(img)
        names = {c.index: c.name for c in seg.clusters}
        lines = sorted((e.kind, names[e.cluster]) for e in seg.elements if e.kind in ("hline", "vline"))
        dots = {names[c.index]: seg.dots(c.index) for c in seg.clusters if seg.dots(c.index)}
        return {"kind": seg.guess_kind(), "ring": seg.ring is not None, "lines": lines, "dots": dots, "reason": seg.reason}

    def test_control_chart(self):
        img, markers = synth.control_chart()
        want = self.summary(img)
        self.assertEqual(want["dots"].get("파랑"), markers)
        for q, sub in ((90, "420"), (90, "444"), (75, "444")):
            with self.subTest(q=q, sub=sub):
                self.assertEqual(self.summary(ap.decode(je.jpeg_of(img, q, sub))), want)

    def test_wafer_map(self):
        img, info = synth.wafer_map()
        want = self.summary(img)
        self.assertTrue(want["ring"])
        for q, sub in ((95, "444"), (90, "444")):
            with self.subTest(q=q, sub=sub):
                self.assertEqual(self.summary(ap.decode(je.jpeg_of(img, q, sub))), want)

    def test_whole_app_reads_jpeg_by_signature(self):
        # 앱 전체 경로: .jpg · .jpeg · 이름만 .png 인 JPEG 모두 같은 글자 아트, 종료 코드 0
        img, _ = synth.control_chart(frame=True)
        data = je.jpeg_of(img, 90, "444")
        with tempfile.TemporaryDirectory(prefix="ascii 1 jpeg ") as tmp:
            outs = []
            for name in ("관리도.jpg", "b.jpeg", "c.png"):
                src = os.path.join(tmp, name)
                with open(src, "wb") as f:
                    f.write(data)
                p = subprocess.run([sys.executable, os.path.join(ROOT, "ascii-1.py"), src, "--stdout", "--no-wait"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120,
                                   env=dict(os.environ, PYTHONIOENCODING="utf-8"))
                out = p.stdout.decode("utf-8")
                self.assertEqual(p.returncode, 0, out + p.stderr.decode("utf-8", "replace"))
                self.assertEqual(out.splitlines()[-1], "결과: OK")
                outs.append(out.replace(name, "<그림>"))
                with open(src, "rb") as f:
                    self.assertEqual(f.read(), data)          # 원본 불변
            self.assertEqual(outs[0], outs[1])
            self.assertEqual(outs[0], outs[2])

    def test_png_with_a_jpeg_name_is_read_as_png(self):
        img, _ = synth.control_chart()
        import pngenc as pe
        rows = [[tuple(img.rgb[3 * (y * img.width + x):3 * (y * img.width + x) + 3]) for x in range(img.width)]
                for y in range(img.height)]
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "사실은 PNG.jpg")
            with open(src, "wb") as f:
                f.write(pe.encode(img.width, img.height, 2, 8, rows, filters=(0,)))
            self.assertEqual(ap.load(src).rgb, img.rgb)


class Guarded(unittest.TestCase):
    """깨진 입력은 정해진 오류(PngError 갈래) 아니면 Image — 그 밖의 예외 · 끝없는 루프 · 메모리 폭주 없음"""

    @classmethod
    def setUpClass(cls):
        cls.valid = je.jpeg_of(scene(64, 48, seed=5), 85, "420")

    def setUp(self):
        faulthandler.dump_traceback_later(WATCHDOG_S, exit=True)

    def tearDown(self):
        faulthandler.cancel_dump_traceback_later()

    def attempt(self, data):
        """→ (Image 또는 None, 오류 문구 또는 None). 그 밖의 예외는 그대로 새어 시험이 실패한다"""
        t = time.monotonic()
        try:
            out, err = ap.decode(data), None
        except ap.PngError as e:
            out, err = None, str(e)
        elapsed = time.monotonic() - t
        self.assertLess(elapsed, PER_ITEM_S)
        if err is not None:
            self.assertTrue(err and "\n" not in err, "한국어 한 줄")
        else:
            self.assertEqual(len(out.rgb), 3 * out.width * out.height)
            self.assertTrue(1 <= out.width <= ap.MAX_SIDE and 1 <= out.height <= ap.MAX_SIDE)
        return out, err

    def test_corrupt_corpus(self):
        corpus = je.corrupt_corpus(self.valid)
        self.assertEqual(len(corpus), 60)
        self.assertIsInstance(self.attempt(self.valid)[0], ap.Image)
        for name, (data, expect) in sorted(corpus.items()):
            with self.subTest(name=name):
                out, err = self.attempt(data)
                if expect.startswith("거부"):
                    self.assertIsNone(out, expect)
                else:
                    self.assertTrue(expect.startswith("허용 또는 거부"))

    def test_corpus_messages(self):
        corpus = je.corrupt_corpus(self.valid)
        for name in ("sof2_progressive", "sof1_extended", "sof9_arithmetic", "precision_12", "four_components"):
            with self.subTest(name=name):
                self.assertEqual(self.attempt(corpus[name][0])[1], aj.UNSUPPORTED)
        for name in ("trunc_scan_25", "trunc_scan_50", "trunc_scan_90", "trunc_in_sof", "sos_no_data_no_eoi"):
            with self.subTest(name=name):
                self.assertIn("잘린 파일", self.attempt(corpus[name][0])[1])
        self.assertIn("너무 큽니다", self.attempt(corpus["sof_huge"][0])[1])
        self.assertIn("크기가 0", self.attempt(corpus["sof_zero_w"][0])[1])
        self.assertRegex(self.attempt(corpus["dht_oversubscribed"][0])[1], "DHT|허프만")
        self.assertIn("허프만", self.attempt(corpus["dht_sparse"][0])[1])

    def test_seeded_mutation_fuzz(self):
        # 유효한 파일 셋(4:2:0 + 재시작 · 4:4:4 · 회색)의 임의 바이트를 바꾸거나 잘라 낸 400 개 — 시드 고정
        rng = random.Random(20261018)
        img = scene(40, 24, seed=7)
        bases = [je.jpeg_of(img, 80, "420", 2), je.jpeg_of(img, 70, "444"),
                 je.encode(img.width, img.height, img.rgb, 85, gray=True)]
        results = {"image": 0, "error": 0}
        for k in range(400):
            base = bases[k % len(bases)]
            buf = bytearray(base)
            op = rng.randrange(4)
            if op == 0:
                for _ in range(rng.randint(1, 4)):
                    buf[rng.randrange(2, len(buf))] = rng.randrange(256)
            elif op == 1:
                pos = rng.randrange(2, len(buf))
                buf[pos] ^= 1 << rng.randrange(8)
            elif op == 2:
                pos = rng.randrange(2, len(buf))
                buf[pos:pos + rng.randint(1, 8)] = b""
            else:
                pos = rng.randrange(2, min(len(buf), 700))             # 머리 쪽에 몰아서 (표 · SOF · SOS)
                buf[pos] = rng.choice((0, 1, 0x7F, 0x80, 0xFE, 0xFF, buf[pos] + 1 & 255))
            with self.subTest(k=k, op=op):
                out, err = self.attempt(bytes(buf))
                results["image" if out is not None else "error"] += 1
        self.assertGreater(results["error"], 50)                      # 퍼징이 실제로 오류 길을 지난다
        self.assertGreater(results["image"], 50)                      # 스캔 쪽 변이는 대개 그림이 된다

    def test_size_limit_before_decoding(self):
        corpus = je.corrupt_corpus(self.valid)
        for name in ("sof_huge", "sof_wide"):
            with self.subTest(name=name):
                data = corpus[name][0]
                tracemalloc.start()
                try:
                    _, err = self.attempt(data)
                    _, peak = tracemalloc.get_traced_memory()
                finally:
                    tracemalloc.stop()
                self.assertIn("너무 큽니다", err)
                self.assertLess(peak, 4 * len(data) + 256 * 1024, "판을 잡기 전에 거부")

    def test_limit_edge_is_allowed_in_the_header(self):
        # 4000 은 되고 4001 은 안 된다 — 머리만 바꾼 파일이라 4000 쪽은 자료가 모자라 '잘린 파일' 로 끝난다
        sof_a = [a for m, a, b in je.split_segments(self.valid) if m == 0xC0][0]
        for side, word in ((4000, "잘린 파일"), (4001, "너무 큽니다")):
            with self.subTest(side=side):
                buf = bytearray(self.valid)
                struct.pack_into(">HH", buf, sof_a + 5, 8, side)
                self.assertIn(word, self.attempt(bytes(buf))[1])

    def test_load_checks_file_size_for_jpeg_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "big.jpg")
            with open(src, "wb") as f:
                f.write(self.valid)
                f.truncate(ap.MAX_FILE_BYTES + 1)
            with self.assertRaises(ap.PngError) as cm:
                ap.load(src)
            self.assertIn("파일이 너무 큽니다", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
