# -*- coding: utf-8 -*-
"""ascii-1.py 테스트 — 변환 · 이름 충돌 · 여러 파일 · 실패와 확인 필요 · 옵션 · 종료 코드 · 끌어놓기 대기.
그림은 전부 코드로 만든 것이고 파일은 임시 폴더(공백 · 한글 이름)에만 만든다. 이 PC 의 실제 폴더는 건드리지 않는다 (W-12)"""
import hashlib
import importlib.util
import io
import os
import random
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import ascii1_png as ap  # noqa: E402
import ascii1_render as rd  # noqa: E402
import ascii1_seg as sg  # noqa: E402
import pngenc as pe  # noqa: E402
import synth  # noqa: E402

spec = importlib.util.spec_from_file_location("ascii_1", os.path.join(ROOT, "ascii-1.py"))
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)

_CACHE = {}


def png_of(image):
    rows = [[tuple(image.rgb[3 * (y * image.width + x):3 * (y * image.width + x) + 3]) for x in range(image.width)]
            for y in range(image.height)]
    return pe.encode(image.width, image.height, 2, 8, rows, filters=(0,))


def noise():
    rng = random.Random(3)                               # 한 번만 만들어 이어서 뽑는다 (매번 새로 만들면 같은 값만 나온다)
    return ap.Image(100, 100, bytes(rng.randrange(256) for _ in range(30000)))


def sample(name):
    """합성 그림의 PNG 바이트 (한 번만 만든다)"""
    if name not in _CACHE:
        img = {"chart": lambda: synth.control_chart(frame=True)[0], "wafer": lambda: synth.wafer_map(plus=3)[0],
               "blank": lambda: synth.Canvas(60, 40).image(),
               "noise": lambda: noise()}[name]()
        _CACHE[name] = png_of(img)
    return _CACHE[name]


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


class Folder(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self._tmp.name, "한글 폴더 two words")      # 공백 · 한글 경로
        os.makedirs(self.dir)
        self.addCleanup(self._tmp.cleanup)

    def put(self, name, data):
        path = os.path.join(self.dir, name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def names(self):
        return sorted(os.listdir(self.dir))

    def read(self, name):
        with open(os.path.join(self.dir, name), encoding="utf-8", newline="") as f:
            return f.read()


class Commands(unittest.TestCase):
    def test_version(self):
        for flag in ("version", "--version"):
            code, out, _ = run(flag)
            self.assertEqual((code, out.strip()), (0, "ascii-1 " + cli.VERSION))

    def test_help_is_the_default_and_names_the_exit_codes(self):
        for argv in ((), ("help",), ("--help",), ("-h",)):
            code, out, _ = run(*argv)
            self.assertEqual(code, 0)
            self.assertIn("Ascii–1", out)
            self.assertIn("--width", out)
            self.assertIn("종료 코드", out)

    def test_check_passes_and_ends_with_the_result_line(self):
        code, out, _ = run("check")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines()[-1], "결과: OK")
        for step in ("PNG 읽기", "요소 찾기", "글자 아트"):
            self.assertIn(step, out)

    def test_check_reports_a_broken_stage(self):
        with mock.patch.object(cli.render, "render", side_effect=RuntimeError("부서짐")):
            code, out, _ = run("check")
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines()[-1], "결과: 점검 실패")
        self.assertIn("부서짐", out)

    def test_check_notices_wrong_pictures(self):
        with mock.patch.object(cli.seg_mod, "segment", return_value=sg.Segmentation(90, 60, (255, 255, 255))):
            code, out, _ = run("check")
        self.assertEqual((code, out.splitlines()[-1]), (1, "결과: 점검 실패"))


class Converting(Folder):
    def test_writes_next_to_the_input_and_leaves_the_original_alone(self):
        src = self.put("관리도 샘플.png", sample("chart"))
        before = sha(src)
        code, out, err = run(src)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(self.names(), ["관리도 샘플.png", "관리도 샘플.txt"])
        self.assertEqual(sha(src), before, "원본은 바꾸지 않는다")
        self.assertEqual(out.splitlines()[-1], "결과: OK")
        self.assertIn("OK  관리도 샘플.png → 관리도 샘플.txt", out)

    def test_output_is_what_the_modules_produce(self):
        src = self.put("a.png", sample("chart"))
        run(src)
        want = rd.render(sg.segment(ap.load(src)), rd.DEFAULT_WIDTH, eol=rd.DEFAULT_EOL)
        self.assertEqual(self.read("a.txt").replace("\r\n", "\n"), want)

    def test_output_is_utf8_with_the_legend(self):
        self.put("w.png", sample("wafer"))
        run(os.path.join(self.dir, "w.png"))
        with open(os.path.join(self.dir, "w.txt"), "rb") as f:
            raw = f.read()
        text = raw.decode("utf-8")
        self.assertIn("웨이퍼 외곽", text)
        self.assertTrue(text.endswith("\n"))

    def test_never_overwrites_an_existing_file(self):
        src = self.put("a.png", sample("chart"))
        self.put("a.txt", "내가 만든 파일".encode("utf-8"))
        code, out, _ = run(src)
        self.assertEqual(code, 0)
        self.assertEqual(self.names(), ["a (2).txt", "a.png", "a.txt"])
        self.assertEqual(self.read("a.txt"), "내가 만든 파일", "있던 파일은 그대로")
        run(src)
        run(src)
        self.assertEqual(self.names(), ["a (2).txt", "a (3).txt", "a (4).txt", "a.png", "a.txt"])

    def test_uppercase_and_other_extensions(self):
        src = self.put("그림.PNG", sample("wafer"))
        self.assertEqual(run(src)[0], 0)
        self.assertIn("그림.txt", self.names())

    def test_several_files_in_one_drop(self):
        a = self.put("chart.png", sample("chart"))
        b = self.put("wafer.png", sample("wafer"))
        code, out, _ = run(a, b)
        self.assertEqual(code, 0)
        self.assertEqual(self.names(), ["chart.png", "chart.txt", "wafer.png", "wafer.txt"])
        self.assertEqual(out.splitlines()[-1], "결과: OK")
        self.assertIn("chart.png", out)
        self.assertIn("wafer.png", out)

    def test_width_option(self):
        src = self.put("w.png", sample("wafer"))
        for args, limit in ((("--width", "40"), 40), (("--width=60",), 60)):
            run(src, *args)
        art40 = self.read("w.txt").replace("\r\n", "\n").rsplit("\n\n", 1)[0].rstrip("\n").split("\n")
        art60 = self.read("w (2).txt").replace("\r\n", "\n").rsplit("\n\n", 1)[0].rstrip("\n").split("\n")
        self.assertEqual({len(x) for x in art40}, {41})                  # 40 열 + 줄 끝 기호 한 칸
        self.assertEqual({len(x) for x in art60}, {61})
        self.assertTrue(all(x.endswith("$") for x in art40 + art60))

    def test_box_option(self):
        src = self.put("c.png", sample("chart"))
        run(src, "--box")
        self.assertTrue(set("─│┼") <= set(self.read("c.txt")))

    def test_stdout_option_writes_no_file(self):
        a = self.put("c.png", sample("chart"))
        b = self.put("w.png", sample("wafer"))
        code, out, _ = run(a, b, "--stdout")
        self.assertEqual(code, 0)
        self.assertEqual(self.names(), ["c.png", "w.png"])
        self.assertIn("== c.png ==", out)
        self.assertIn("== w.png ==", out)
        self.assertEqual(out.splitlines()[-1], "결과: OK")

    def test_kind_wafer_accepts_a_wafer(self):
        src = self.put("w.png", sample("wafer"))
        self.assertEqual(run(src, "--kind", "wafer")[0], 0)
        self.assertEqual(run(src, "--kind=auto")[0], 0)


class NeedsAHuman(Folder):
    def assert_refused(self, name, data, *args, words=()):
        before = self.names()
        src = self.put(name, data)
        code, out, _ = run(src, *args)
        self.assertEqual(code, 3, out)
        self.assertEqual(out.splitlines()[-1], "결과: 확인 필요")
        self.assertEqual(self.names(), sorted(before + [name]), "만들지 않는다")
        for w in words:
            self.assertIn(w, out)

    def test_blank_picture(self):
        self.assert_refused("blank.png", sample("blank"), words=("그릴 것",))

    def test_photo_like_picture(self):
        self.assert_refused("noise.png", sample("noise"), words=("절반",))

    def test_wrong_kind(self):
        self.assert_refused("c.png", sample("chart"), "--kind", "wafer", words=("웨이퍼 외곽",))
        self.assert_refused("w.png", sample("wafer"), "--kind", "chart", words=("웨이퍼 맵",))

    def test_one_refusal_among_good_files_makes_the_result_confirm(self):
        good = self.put("c.png", sample("chart"))
        bad = self.put("blank.png", sample("blank"))
        code, out, _ = run(good, bad)
        self.assertEqual(code, 3)
        self.assertIn("c.txt", self.names())
        self.assertEqual(out.splitlines()[-1], "결과: 확인 필요")


class Failing(Folder):
    def test_a_broken_jpeg_with_a_png_name(self):
        # 이름은 .png 여도 시그니처로 JPEG 로 읽는다 (JPEG 를 읽게 된 뒤로 — 그 전에는 'JPEG 로 보입니다' 로 거부). 깨진 JPEG 는 종료 코드 1
        src = self.put("fake.png", b"\xff\xd8\xff\xe0" + bytes(100))
        before = sha(src)
        code, out, _ = run(src)
        self.assertEqual(code, 1)
        self.assertIn("실패  fake.png: JPEG", out)
        self.assertEqual(out.splitlines()[-1], "결과: 점검 실패")
        self.assertEqual(self.names(), ["fake.png"])
        self.assertEqual(sha(src), before)

    def test_broken_and_missing_files_do_not_stop_the_others(self):
        good = self.put("c.png", sample("chart"))
        broken = self.put("cut.png", sample("chart")[:200])
        missing = os.path.join(self.dir, "없는 파일.png")
        code, out, _ = run(broken, missing, good)
        self.assertEqual(code, 1)
        self.assertIn("c.txt", self.names())
        self.assertIn("파일이 없습니다", out)
        self.assertIn("실패  cut.png", out)
        self.assertEqual(out.splitlines()[-1], "결과: 점검 실패")

    def test_failure_outranks_a_refusal(self):
        code, out, _ = run(self.put("blank.png", sample("blank")), self.put("x.png", b"not a png"))
        self.assertEqual((code, out.splitlines()[-1]), (1, "결과: 점검 실패"))

    def test_cannot_write_next_to_the_input(self):
        src = self.put("c.png", sample("chart"))
        with mock.patch.object(cli, "output_file", side_effect=PermissionError("읽기 전용")):
            code, out, _ = run(src)
        self.assertEqual(code, 1)
        self.assertIn("--stdout", out)
        self.assertEqual(out.splitlines()[-1], "결과: 점검 실패")

    def test_a_directory_is_not_a_picture(self):
        code, out, _ = run(self.dir)
        self.assertEqual(code, 1)
        self.assertIn("파일이 없습니다", out)

    def test_no_free_name_left(self):
        src = self.put("c.png", sample("chart"))
        with mock.patch.object(cli, "MAX_COLLISIONS", 3):
            self.put("c.txt", b"1")
            self.put("c (2).txt", b"2")
            self.put("c (3).txt", b"3")
            code, out, _ = run(src)
        self.assertEqual(code, 1)
        self.assertIn("실패  c.png", out)


class Usage(unittest.TestCase):
    def test_usage_errors_exit_two_with_a_message_on_stderr(self):
        for argv, word in ((("--width", "10", "a.png"), "40–300"), (("--width", "300000", "a.png"), "40–300"),
                           (("--width", "abc", "a.png"), "숫자"), (("a.png", "--width"), "값이 필요"),
                           (("--kind", "circle", "a.png"), "auto"), (("--kind",), "값이 필요"),
                           (("--nope", "a.png"), "모르는 옵션"), (("-x",), "모르는 옵션")):
            with self.subTest(argv=argv):
                code, out, err = run(*argv)
                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                self.assertIn(word, err)

    def test_nothing_is_written_on_a_usage_error(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "a.png")
            with open(path, "wb") as f:
                f.write(sample("chart"))
            run(path, "--width", "5")
            self.assertEqual(os.listdir(d), ["a.png"])

    def test_commands_must_stand_alone(self):
        # `version` 이 파일 이름으로 쓰일 수 있으니 다른 인자와 같이 오면 파일로 본다
        code, out, _ = run("version", "--width", "50")
        self.assertEqual(code, 1)
        self.assertIn("파일이 없습니다", out)


class DropWait(unittest.TestCase):
    def test_waits_only_in_front_of_a_person(self):
        with mock.patch.object(sys, "stdin") as fin, mock.patch.object(sys, "stdout", new_callable=io.StringIO) as fout, \
                mock.patch("builtins.input") as inp:
            fin.isatty.return_value = True
            fout.isatty = lambda: True
            cli.wait_for_enter()
            self.assertEqual(inp.call_count, 1)
        with mock.patch.object(sys, "stdin") as fin, mock.patch("builtins.input") as inp:
            fin.isatty.return_value = False
            cli.wait_for_enter()
            inp.assert_not_called()

    def test_when_to_wait(self):
        self.assertTrue(cli.should_wait(["그림.png"]))
        self.assertTrue(cli.should_wait(["a.png", "b.png", "--width", "80"]))
        self.assertFalse(cli.should_wait(["a.png", "--no-wait"]), "--no-wait 는 기다리지 않는다")
        self.assertFalse(cli.should_wait(["a.png", "--stdout"]), "화면에 찍을 때는 기다리지 않는다")
        self.assertFalse(cli.should_wait([]), "인자가 없으면 도움말만")
        for command in ("version", "help", "check"):
            self.assertFalse(cli.should_wait([command]))
        self.assertFalse(cli.should_wait(["--box", "a.png"]), "옵션부터 쳤으면 터미널에서 직접 연 것")

    def test_a_closed_console_does_not_raise(self):
        with mock.patch.object(sys, "stdin") as fin, mock.patch.object(sys, "stdout", new_callable=io.StringIO) as fout, \
                mock.patch("builtins.input", side_effect=EOFError):
            fin.isatty.return_value = True
            fout.isatty = lambda: True
            cli.wait_for_enter()


class AsAProgram(Folder):
    """실제로 python 으로 띄워 본다 — __main__ · 인코딩 · 대기하지 않는지"""

    def launch(self, *args):
        env = dict(os.environ, PYTHONIOENCODING="cp949")       # 콘솔 인코딩이 UTF-8 이 아니어도 깨지지 않아야
        return subprocess.run([sys.executable, os.path.join(ROOT, "ascii-1.py")] + list(args), capture_output=True,
                              stdin=subprocess.DEVNULL, timeout=120, env=env)

    def test_drop_a_file(self):
        src = self.put("그림 하나.png", sample("wafer"))
        p = self.launch(src)
        self.assertEqual(p.returncode, 0, p.stderr.decode("utf-8", "replace"))
        self.assertIn("그림 하나.txt", self.names())
        out = p.stdout.decode("utf-8")
        self.assertEqual(out.splitlines()[-1], "결과: OK")
        self.assertNotIn("Enter", out, "콘솔이 아니면 기다리지 않는다")

    def test_version_and_usage_exit_codes(self):
        self.assertEqual(self.launch("version").stdout.decode("utf-8").strip(), "ascii-1 " + cli.VERSION)
        self.assertEqual(self.launch("--width", "1", "x.png").returncode, 2)
        self.assertEqual(self.launch("check").returncode, 0)


if __name__ == "__main__":
    unittest.main()
