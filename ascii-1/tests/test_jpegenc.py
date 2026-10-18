# -*- coding: utf-8 -*-
"""tests/jpegenc.py 자체 시험 — 헤더 구조 · 결정성 · 크기 · 재시작 표지 · 손상 코퍼스의 모양. 디코더는 부르지 않는다 (표준 라이브러리만)"""
import os
import random
import struct
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import jpegenc as je  # noqa: E402


def noise(w, h, seed=1):
    r = random.Random(seed)
    return bytes(r.randrange(256) for _ in range(3 * w * h))


def walk(data):
    """SOI 부터 SOS 까지 (마커, 본문) 목록과 스캔 자료의 시작 위치. 길이가 틀리면 AssertionError"""
    assert data[:2] == b"\xff\xd8"
    pos, segs = 2, []
    while True:
        assert data[pos] == 255, "표지가 아님 @%d" % pos
        marker = data[pos + 1]
        length = struct.unpack(">H", data[pos + 2:pos + 4])[0]
        body = data[pos + 4:pos + 2 + length]
        assert len(body) == length - 2
        segs.append((marker, body))
        pos += 2 + length
        if marker == 0xDA:
            return segs, pos


class EncoderTest(unittest.TestCase):
    def test_header_order_420(self):
        d = je.encode(20, 10, noise(20, 10), 75, "420")
        segs, scan = walk(d)
        self.assertEqual([m for m, _ in segs], [0xDB, 0xDB, 0xC0, 0xC4, 0xC4, 0xC4, 0xC4, 0xDA])
        self.assertTrue(d.endswith(b"\xff\xd9"))
        self.assertTrue(scan < len(d) - 2)
        sof = dict(segs[2:3])[0xC0]
        self.assertEqual(struct.unpack(">BHHB", sof[:6]), (8, 10, 20, 3))
        self.assertEqual([c[1] for c in (sof[6:9], sof[9:12], sof[12:15])], [0x22, 0x11, 0x11])
        sos = segs[-1][1]
        self.assertEqual(sos[0], 3)
        self.assertEqual(sos[-3:], bytes([0, 63, 0]))

    def test_dqt_dht_bodies(self):
        segs, _ = walk(je.encode(8, 8, noise(8, 8), 50, "444"))
        dqt = [b for m, b in segs if m == 0xDB]
        self.assertEqual([len(b) for b in dqt], [65, 65])
        self.assertEqual(dqt[0][1], 16)                       # 품질 50 은 표준 표 그대로, 지그재그 첫 값 16
        self.assertEqual([dqt[0][0], dqt[1][0]], [0, 1])
        dht = [b for m, b in segs if m == 0xC4]
        self.assertEqual([b[0] for b in dht], [0x00, 0x10, 0x01, 0x11])
        for b in dht:
            self.assertEqual(len(b), 17 + sum(b[1:17]))
        self.assertEqual([len(b) for b in dht], [29, 179, 29, 179])

    def test_444_sampling_and_gray(self):
        segs, _ = walk(je.encode(9, 9, noise(9, 9), 75, "444"))
        sof = [b for m, b in segs if m == 0xC0][0]
        self.assertEqual([sof[7], sof[10], sof[13]], [0x11, 0x11, 0x11])
        segs, _ = walk(je.encode(9, 9, noise(9, 9), 75, gray=True))
        self.assertEqual([m for m, _ in segs], [0xDB, 0xC0, 0xC4, 0xC4, 0xDA])
        sof = [b for m, b in segs if m == 0xC0][0]
        self.assertEqual(sof[5], 1)

    def test_quality_scale(self):
        self.assertEqual(je.quant_table(je.Q_LUMA, 50), je.Q_LUMA)
        self.assertTrue(all(v == 1 for v in je.quant_table(je.Q_LUMA, 100)))
        self.assertEqual(je.quant_table(je.Q_LUMA, 10)[0], 80)

    def test_deterministic(self):
        rgb = noise(33, 17)
        self.assertEqual(je.encode(33, 17, rgb, 80, "420", 2), je.encode(33, 17, rgb, 80, "420", 2))

    def test_size_monotone_in_quality(self):
        rgb = noise(32, 32)
        sizes = [len(je.encode(32, 32, rgb, q, "444")) for q in (20, 50, 90)]
        self.assertTrue(sizes[0] < sizes[1] < sizes[2], sizes)
        self.assertTrue(len(je.encode(32, 32, rgb, 75, "420")) < len(je.encode(32, 32, rgb, 75, "444")))
        flat = je.encode(64, 64, bytes([200, 100, 50]) * 4096, 75, "420")
        self.assertTrue(len(flat) < 700, len(flat))

    def test_restart_markers(self):
        w, h = 40, 24                                          # 4:2:0 은 MCU 3 x 2 = 6, 4:4:4 는 5 x 3 = 15
        rgb = noise(w, h)
        d = je.encode(w, h, rgb, 75, "420", 2)
        segs, scan = walk(d)
        self.assertEqual(dict(segs)[0xDD], b"\x00\x02")
        self.assertEqual([m for m, _ in segs].index(0xDD) < len(segs) - 1, True)
        body = d[scan:-2]
        marks = [body[i + 1] for i in range(len(body) - 1) if body[i] == 255 and 0xD0 <= body[i + 1] <= 0xD7]
        self.assertEqual(marks, [0xD0, 0xD1])                  # 6 개 MCU 를 2 개씩 끊으면 표지 2 개
        d = je.encode(w, h, rgb, 75, "444", 4)
        body = d[walk(d)[1]:-2]
        marks = [body[i + 1] for i in range(len(body) - 1) if body[i] == 255 and 0xD0 <= body[i + 1] <= 0xD7]
        self.assertEqual(marks, [0xD0, 0xD1, 0xD2])            # 15 개를 4 개씩: 3 개, 번호는 0 부터
        self.assertEqual(marks, [0xD0 + i for i in range(3)])
        self.assertNotIn(0xDD, [m for m, _ in walk(je.encode(w, h, rgb))[0]])

    def test_restart_marker_numbering_wraps(self):
        d = je.encode(8 * 20, 8, noise(160, 8), 75, "444", 1)  # MCU 20 개, 간격 1 → 표지 19 개, 번호는 7 다음 0
        body = d[walk(d)[1]:-2]
        marks = [body[i + 1] for i in range(len(body) - 1) if body[i] == 255 and 0xD0 <= body[i + 1] <= 0xD7]
        self.assertEqual(marks, [0xD0 + i % 8 for i in range(19)])

    def test_byte_stuffing(self):
        d = je.encode(64, 64, noise(64, 64, 7), 95, "444")
        body = d[walk(d)[1]:-2]
        for i, b in enumerate(body[:-1]):
            if b == 255:
                self.assertIn(body[i + 1], [0] + list(range(0xD0, 0xD8)))

    def test_bad_arguments(self):
        with self.assertRaises(ValueError):
            je.encode(2, 2, b"\0" * 5)
        with self.assertRaises(ValueError):
            je.encode(2, 2, b"\0" * 12, subsampling="422")

    def test_huffman_tables_complete(self):
        for spec in (je.AC_LUMA, je.AC_CHROMA):
            self.assertEqual(len(spec[1]), 162)
            self.assertEqual(sorted(spec[1]), sorted([r * 16 + s for r in range(16) for s in range(1, 11)] + [0, 0xF0]))
            codes = je.code_table(spec)
            self.assertEqual(len(codes), 162)
        for spec in (je.DC_LUMA, je.DC_CHROMA):
            self.assertEqual(sorted(spec[1]), list(range(12)))
        # 접두 부호 성질: 어떤 부호도 다른 부호의 앞부분이 아니다
        codes = sorted(format(c, "0%db" % n) for c, n in je.code_table(je.AC_LUMA).values())
        for a, b in zip(codes, codes[1:]):
            self.assertFalse(b.startswith(a))


class CorpusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.valid = je.encode(96, 64, noise(96, 64, 3), 75, "420")
        cls.corpus = je.corrupt_corpus(cls.valid)

    def test_shape(self):
        self.assertGreaterEqual(len(self.corpus), 40)
        for name, (data, expect) in self.corpus.items():
            self.assertIsInstance(data, bytes, name)
            self.assertTrue(expect.startswith(("거부", "허용 또는 거부")), name)
            self.assertNotEqual(data, self.valid, name)

    def test_required_cases(self):
        need = ["trunc_0", "trunc_scan_50", "flip_head_0", "flip_scan_0", "dht_empty", "sof_huge", "sof_zero_both",
                "sof2_progressive", "precision_12", "four_components", "dqt_len_long", "dht_oversubscribed",
                "sos_no_data", "dup_sof"]
        for n in need:
            self.assertIn(n, self.corpus)

    def test_deterministic(self):
        again = je.corrupt_corpus(self.valid)
        self.assertEqual(sorted(again), sorted(self.corpus))
        for n in again:
            self.assertEqual(again[n], self.corpus[n], n)

    def test_cases_do_what_they_say(self):
        c = {n: d for n, (d, _) in self.corpus.items()}
        self.assertEqual(struct.unpack(">HH", c["sof_huge"][je._find(c["sof_huge"], 0xC0)[0] + 5:][:4]), (65535, 65535))
        a, _ = je._find(c["sof2_progressive"], 0xC2)
        self.assertEqual(c["sof2_progressive"][a:a + 2], b"\xff\xc2")
        a, _ = je._find(c["precision_12"], 0xC0)
        self.assertEqual(c["precision_12"][a + 4], 12)
        segs, _ = walk(c["four_components"])
        self.assertEqual(dict(segs)[0xC0][5], 4)
        self.assertEqual(dict(segs)[0xDA][0], 4)
        self.assertEqual(len(c["trunc_scan_50"]) < len(self.valid), True)
        self.assertEqual(c["trunc_0"], b"")
        a, b = je._find(c["dht_empty"], 0xC4)
        self.assertEqual(c["dht_empty"][a:b], b"\xff\xc4\x00\x02")
        self.assertEqual(c["sos_no_data"][-2:], b"\xff\xd9")
        self.assertEqual(sum(1 for m, _ in walk(c["dup_sof"][:je._find(c["dup_sof"], 0xDA)[1]])[0] if m == 0xC0), 2)

    def test_flips_are_single_bits(self):
        for n, (d, _) in self.corpus.items():
            if n.startswith("flip_"):
                diff = [x ^ y for x, y in zip(d, self.valid) if x != y]
                self.assertEqual(len(d), len(self.valid))
                self.assertEqual(len(diff), 1, n)
                self.assertIn(diff[0], [1 << i for i in range(8)])


if __name__ == "__main__":
    unittest.main()
