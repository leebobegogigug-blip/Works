# -*- coding: utf-8 -*-
"""기본 40 열 · 줄 끝 기호 — 글자 아트의 모든 줄이 정확히 열 수만큼이고 그다음 칸(열 수 + 1 번째)에 줄 끝 기호가 찍히는지.
render() 는 eol 을 주지 않으면 지금까지와 바이트까지 같고(골든 3 개), 명령 · 창의 기본이 40 열 + `$` 이다. 그림은 전부 코드로 만든 것 (W-12)"""
import io
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import ascii1_render as rd  # noqa: E402
import ascii1_png as ap  # noqa: E402
import ascii1_seg as sg  # noqa: E402
import test_cli as tc  # noqa: E402
from shared import seg_of  # noqa: E402

PICTURES = ("B0", "C", "A0", "Z")
WIDTHS = (40, 60, 120, 300)


def art(text):
    return text.rsplit("\n\n", 1)[0].rstrip("\n").split("\n")


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = tc.cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class Defaults(unittest.TestCase):
    def test_default_is_forty_columns_and_a_dollar_sign(self):
        self.assertEqual(rd.DEFAULT_WIDTH, 40)
        self.assertEqual(rd.DEFAULT_EOL, "$")
        opts = tc.cli.parse(["a.png"])[1]
        self.assertEqual((opts["width"], opts["eol"]), (40, "$"))
        self.assertEqual(rd.MIN_WIDTH, 40, "40 열이 가장 좁은 폭이다")

    def test_help_names_the_option_and_the_default(self):
        self.assertIn("--eol", tc.cli.HELP)
        self.assertIn("기본 %d" % 40, tc.cli.HELP)


class Render(unittest.TestCase):
    def test_every_art_line_is_exactly_width_plus_the_mark(self):
        for name in PICTURES:
            for width in WIDTHS:
                with self.subTest(name=name, width=width):
                    lines = art(rd.render(seg_of(name), width, eol="$"))
                    self.assertEqual({len(x) for x in lines}, {width + 1})
                    self.assertTrue(all(x.endswith("$") for x in lines))
                    self.assertFalse(any("$" in x[:-1] for x in lines), "기호는 41 번째 칸에만")

    def test_short_lines_are_padded_with_spaces_before_the_mark(self):
        seg = sg.segment(ap.decode(tc.sample("wafer")))                        # 틀이 없는 그림 — 줄 끝 공백이 잘린 짧은 줄이 있다
        text = rd.render(seg, 40)
        lines = art(rd.render(seg, 40, eol="$"))
        self.assertTrue(any(len(x) < 40 for x in art(text)), "틀이 없는 그림에는 짧은 줄이 있어야 시험이 된다")
        self.assertEqual(len(art(text)), len(lines))
        for plain, marked in zip(art(text), lines):
            self.assertEqual(marked, plain.ljust(40) + "$")

    def test_without_eol_nothing_changes(self):
        for name in PICTURES:
            with self.subTest(name=name):
                self.assertEqual(rd.render(seg_of(name), 120), rd.render(seg_of(name), 120, eol=None))
                self.assertNotIn("$", "".join(art(rd.render(seg_of(name), 120))))

    def test_legend_is_not_padded_or_marked(self):
        marked = rd.render(seg_of("B0"), 40, eol="$")
        plain = rd.render(seg_of("B0"), 40)
        self.assertEqual(marked.rsplit("\n\n", 1)[1], plain.rsplit("\n\n", 1)[1])

    def test_any_single_character_works_and_box_glyphs_count_as_one_column(self):
        lines = art(rd.render(seg_of("B0"), 60, box=True, eol="#"))
        self.assertEqual({len(x) for x in lines}, {61})
        self.assertTrue(all(x.endswith("#") for x in lines))

    def test_the_legend_reports_the_padded_width(self):
        text = rd.render(seg_of("B0"), 40, eol="$")
        self.assertIn("→ 40열 ", text)

    def test_pure_ascii_with_the_default_mark(self):
        for name in PICTURES:
            text = rd.render(seg_of(name), 120, eol="$")
            self.assertTrue(all(ord(ch) < 128 for ch in "".join(art(text))), name)


class Command(unittest.TestCase):
    def setUp(self):
        self.dir = tc.tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.src = os.path.join(self.dir.name, "a.png")
        with open(self.src, "wb") as f:
            f.write(tc.sample("chart"))

    def lines(self, *args):
        code, out, _ = run(self.src, "--stdout", "--no-wait", *args)
        self.assertEqual(code, 0)
        body = out.split("\n", 1)[1]                                # "== 이름 ==" 머리를 뺀다
        return body.split("\n\n", 1)[0].split("\n"), out              # 글자 아트는 첫 빈 줄 앞까지

    def test_default_output_is_forty_columns_and_a_mark(self):
        lines, out = self.lines()
        self.assertEqual({len(x) for x in lines}, {41})
        self.assertTrue(all(x.endswith("$") for x in lines))
        self.assertIn("(40열 ", out, "OK 줄의 열 수는 줄 끝 기호를 뺀 40")

    def test_width_option_moves_the_mark(self):
        lines, out = self.lines("--width", "70")
        self.assertEqual({len(x) for x in lines}, {71})
        self.assertIn("(70열 ", out)

    def test_custom_mark_and_none(self):
        lines, _ = self.lines("--eol", "|")
        self.assertTrue(all(x.endswith("|") and len(x) == 41 for x in lines))
        lines, out = self.lines("--eol=none")
        self.assertFalse(all(len(x) == 41 for x in lines), "none 이면 채우지 않는다")
        self.assertNotIn("$", "".join(lines))
        self.assertNotIn("none", "".join(lines), "none 은 기호가 아니라 끄는 말이다")
        self.assertIn("(40열 ", out, "열 수 보고는 그대로")

    def test_bad_marks_are_usage_errors(self):
        for bad in ("ab", "", " ", "\t", "none2"):
            with self.subTest(bad=bad):
                code, out, err = run(self.src, "--stdout", "--eol", bad)
                self.assertEqual((code, out), (2, ""))
                self.assertIn("--eol", err)
        code, _, err = run(self.src, "--eol")
        self.assertEqual(code, 2)

    def test_the_file_has_the_marks_too(self):
        code, _, _ = run(self.src, "--no-wait")
        self.assertEqual(code, 0)
        with open(os.path.join(self.dir.name, "a.txt"), encoding="utf-8", newline="") as f:
            text = f.read().replace("\r\n", "\n")
        lines = art(text)
        self.assertEqual({len(x) for x in lines}, {41})


class Window(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("DISPLAY") or sys.platform == "win32", "화면이 없다")
    def test_window_starts_at_forty_and_shows_the_mark(self):
        import test_gui as tg
        if tg.NO_DISPLAY:
            self.skipTest(tg.NO_DISPLAY)
        win = tg.gui.Window(tg.app)
        try:
            self.assertEqual(win.params["cols"].value, 40)
            with tg.Folder() as f:
                win.open_path(f.put("a.png", tc.sample("chart")))
                tg.settle(win)
                lines = art(win.text)
                self.assertEqual({len(x) for x in lines}, {41})
                self.assertEqual(win.stats["cols"].text(), "0040", "STAT 의 COLS 는 줄 끝 기호를 뺀 열 수")
        finally:
            win.root.destroy()


if __name__ == "__main__":
    unittest.main()
