# -*- coding: utf-8 -*-
"""ascii1_gui.py 테스트 — 창이 그림을 읽어 그리고 · 옵션을 바꾸면 다시 그리고 · 틀리면 ERR 로 보이고 · 저장이 덮어쓰지 않는지.
창은 실제 tkinter 로 연다. tkinter 나 화면이 없는 곳(CI 의 리눅스 등)에서는 창 시험만 건너뛴다. 그림은 전부 코드로 만든 것이다"""
import gc
import hashlib
import importlib.util
import io
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import ascii1_gui as gui  # noqa: E402
import test_cli as tc  # noqa: E402

spec = importlib.util.spec_from_file_location("ascii_1_gui_test", os.path.join(ROOT, "ascii-1.py"))
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


def display_problem():
    """창을 열 수 없는 까닭 또는 None"""
    if not gui.available():
        return "tkinter 가 없다"
    try:
        root = gui.tk.Tk()
    except gui.tk.TclError as e:
        return "화면이 없다 (%s)" % e
    root.destroy()
    return None


NO_DISPLAY = display_problem()


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def settle(win, seconds=60):
    """일꾼이 끝날 때까지 창의 이벤트를 돌린다"""
    limit = time.time() + seconds
    while win.busy and time.time() < limit:
        win.root.update()
        time.sleep(0.005)
    win.root.update()
    assert not win.busy, "일꾼이 %d 초 안에 끝나지 않았다" % seconds


class Folder:
    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = os.path.join(self.tmp.name, "한글 폴더 two words")
        os.makedirs(self.folder)
        return self

    def __exit__(self, *exc):
        self.tmp.cleanup()

    def put(self, name, data):
        path = os.path.join(self.folder, name)
        with open(path, "wb") as f:
            f.write(data)
        return path


@unittest.skipIf(NO_DISPLAY, NO_DISPLAY)
class WindowTests(unittest.TestCase):
    def setUp(self):
        self.win = gui.Window(app)
        self.addCleanup(gc.collect)                          # 창의 순환 쓰레기는 주 스레드에서 치운다
        self.addCleanup(self.win.root.destroy)
        self.addCleanup(lambda: settle(self.win))           # 일꾼이 도는 채로 창을 부수지 않는다 (Tcl 이 다른 스레드에서 죽는다)

    def open(self, path):
        self.assertTrue(self.win.open_path(path))
        settle(self.win)

    def art(self):
        return self.win.view.get("1.0", "end").rstrip("\n")

    def test_starts_empty_with_nothing_to_save(self):
        self.assertIsNone(self.win.text)
        self.assertEqual(str(self.win.save_button.cget("state")), "disabled")
        self.assertEqual(str(self.win.copy_button.cget("state")), "disabled")
        self.assertIn("그림을 열어", self.win.status.cget("text"))

    def test_open_reads_draws_and_enables_save(self):
        with Folder() as f:
            self.open(f.put("그림 하나.png", tc.sample("chart")))
            art = self.art().rsplit("\n\n", 1)[0]
            for glyph in "=~":
                self.assertIn(glyph, art)
            self.assertTrue(self.win.status.cget("text").startswith("OK  그림 하나.png"))
            self.assertEqual(str(self.win.save_button.cget("state")), "normal")
            self.assertEqual(self.win.path_label.cget("text"), os.path.join(f.folder, "그림 하나.png"))

    def test_same_picture_as_the_command_line(self):
        with Folder() as f:
            src = f.put("a.png", tc.sample("wafer"))
            self.open(src)
            seg, _, _ = app.analyze(src)
            _, _, text, _ = app.make_art(seg, "a.png", self.win.read_options()[0])
            self.assertEqual(self.win.text, text)
            self.assertEqual(self.art(), text.rstrip("\n"))

    def test_width_change_redraws_without_reading_again(self):
        with Folder() as f:
            self.open(f.put("a.png", tc.sample("chart")))
            before = self.art()
            with mock.patch.object(app, "analyze", side_effect=AssertionError("다시 읽으면 안 된다")):
                self.win.width_var.set("60")
                self.win.options_changed()
                settle(self.win)
            after = self.art()
            self.assertNotEqual(before, after)
            width = max(len(x) for x in after.rsplit("\n\n", 1)[0].split("\n"))
            self.assertLessEqual(width, 60)
            self.assertRegex(self.win.status.cget("text"), r"\d+열 \d+행")

    def test_box_option_draws_box_characters(self):
        with Folder() as f:
            self.open(f.put("a.png", tc.sample("chart")))
            self.assertNotIn("─", self.art())
            self.win.box_var.set(True)
            self.win.options_changed()
            settle(self.win)
            self.assertIn("─", self.art())

    def test_bad_width_is_an_error_and_keeps_the_picture(self):
        with Folder() as f:
            self.open(f.put("a.png", tc.sample("chart")))
            kept = self.art()
            for bad in ("abc", "5", "301", ""):
                self.win.width_var.set(bad)
                self.win.options_changed()
                self.win.root.update()
                self.assertEqual(self.win.chip.cget("text"), "ERR", bad)
                self.assertFalse(self.win.busy)
                self.assertEqual(self.art(), kept, bad)
            self.win.width_var.set("120")
            self.win.options_changed()
            settle(self.win)
            self.assertNotEqual(self.win.chip.winfo_manager(), "pack")

    def test_wrong_kind_asks_for_confirmation_and_blocks_saving(self):
        with Folder() as f:
            self.open(f.put("a.png", tc.sample("chart")))
            self.win.kind_var.set("wafer")
            self.win.options_changed()
            settle(self.win)
            self.assertIsNone(self.win.text)
            self.assertEqual(self.art(), "")
            self.assertIn("웨이퍼", self.win.status.cget("text"))
            self.assertEqual(self.win.led.cget("text"), "‼")
            self.assertEqual(str(self.win.save_button.cget("state")), "disabled")
            self.win.kind_var.set("auto")
            self.win.options_changed()
            settle(self.win)
            self.assertIsNotNone(self.win.text)

    def test_unreadable_file_is_shown_as_an_error(self):
        with Folder() as f:
            self.open(f.put("not.png", b"this is not a png"))
            self.assertEqual(self.win.chip.cget("text"), "ERR")
            self.assertIsNone(self.win.text)
            self.assertEqual(str(self.win.save_button.cget("state")), "disabled")
            self.win.options_changed()                       # 읽지 못했으니 다시 그릴 것이 없다 — 조용히 아무 일도 없어야 한다
            self.assertFalse(self.win.busy)

    def test_blank_picture_asks_for_confirmation(self):
        with Folder() as f:
            self.open(f.put("blank.png", tc.sample("blank")))
            self.assertIsNone(self.win.text)
            self.assertEqual(self.win.led.cget("text"), "‼")

    def test_worker_crash_does_not_leave_the_window_reading_forever(self):
        with Folder() as f:
            with mock.patch.object(app, "analyze", side_effect=RuntimeError("부서짐")):
                self.open(f.put("a.png", tc.sample("chart")))
            self.assertFalse(self.win.busy)
            self.assertEqual(self.win.chip.cget("text"), "ERR")
            self.assertIn("부서짐", self.win.status.cget("text"))

    def test_second_open_while_busy_is_refused(self):
        with Folder() as f:
            src = f.put("a.png", tc.sample("chart"))
            self.assertTrue(self.win.open_path(src))
            self.assertFalse(self.win.open_path(src))
            self.assertEqual(str(self.win.open_button.cget("state")), "disabled")
            settle(self.win)
            self.assertEqual(str(self.win.open_button.cget("state")), "normal")

    def test_option_changed_while_busy_is_applied_after(self):
        with Folder() as f:
            self.assertTrue(self.win.open_path(f.put("a.png", tc.sample("chart"))))
            self.win.width_var.set("50")
            self.win.options_changed()
            self.assertTrue(self.win.pending)
            settle(self.win)
            settle(self.win)
            width = max(len(x) for x in self.art().rsplit("\n\n", 1)[0].split("\n"))
            self.assertLessEqual(width, 50)

    def test_save_never_overwrites_and_leaves_the_original(self):
        with Folder() as f:
            src = f.put("그림 하나.png", tc.sample("chart"))
            digest = sha(src)
            self.open(src)
            first = self.win.save()
            second = self.win.save()
            self.assertEqual(os.path.basename(first), "그림 하나.txt")
            self.assertEqual(os.path.basename(second), "그림 하나 (2).txt")
            for path in (first, second):
                with open(path, encoding="utf-8") as g:
                    self.assertEqual(g.read(), self.win.text)
            self.assertEqual(sha(src), digest)
            self.assertTrue(self.win.status.cget("text").startswith("저장했습니다"))

    def test_save_asks_where_when_the_folder_is_not_writable(self):
        with Folder() as f:
            self.open(f.put("a.png", tc.sample("chart")))
            elsewhere = os.path.join(f.folder, "다른 곳.txt")
            with mock.patch.object(app, "output_file", side_effect=PermissionError("읽기 전용")), \
                    mock.patch.object(gui.filedialog, "asksaveasfilename", return_value=elsewhere) as ask:
                self.assertEqual(self.win.save(), elsewhere)
            ask.assert_called_once()
            with open(elsewhere, encoding="utf-8") as g:
                self.assertEqual(g.read(), self.win.text)

    def test_save_cancelled_dialog_writes_nothing(self):
        with Folder() as f:
            self.open(f.put("a.png", tc.sample("chart")))
            with mock.patch.object(app, "output_file", side_effect=PermissionError()), \
                    mock.patch.object(gui.filedialog, "asksaveasfilename", return_value=""):
                self.assertIsNone(self.win.save())
            self.assertEqual(sorted(os.listdir(f.folder)), ["a.png"])

    def test_copy_puts_the_art_on_the_clipboard(self):
        with Folder() as f:
            self.open(f.put("a.png", tc.sample("wafer")))
            self.assertTrue(self.win.copy())
            self.assertEqual(self.win.root.clipboard_get(), self.win.text)

    def test_zoom_stays_in_range(self):
        for _ in range(40):
            self.win.zoom(1)
        self.assertEqual(self.win.art_font.cget("size"), 24)
        for _ in range(40):
            self.win.zoom(-1)
        self.assertEqual(self.win.art_font.cget("size"), 6)

    def test_window_uses_no_red(self):
        """DESIGN: 빨강 없음 — 오류도 가장 밝은 글자 + ERR 칩"""
        for name in ("NAVY", "NAVY1", "NAVY2", "NAVY3", "NAVY5", "LIME", "LIME0", "BLACK", "GRAY0", "GRAY1", "GRAY2", "GRAY", "GRAY4", "WHITE"):
            value = getattr(gui, name).lstrip("#")
            r, g, b = (int(value[i:i + 2], 16) for i in (0, 2, 4))
            self.assertFalse(r > g + 24 and r > b + 24, "%s=#%s 는 붉다" % (name, value))


@unittest.skipIf(NO_DISPLAY, NO_DISPLAY)
class SelfTest(unittest.TestCase):
    def test_gui_selftest_opens_and_closes_a_window(self):
        out = io.StringIO()
        self.assertEqual(gui.selftest(app, out), 0)
        self.assertTrue(out.getvalue().rstrip().endswith("결과: OK"))

    def test_gui_selftest_reports_a_broken_drawing(self):
        out = io.StringIO()
        with mock.patch.object(app, "make_art", return_value=(0, "", "x\n\n범례", "")):
            self.assertEqual(gui.selftest(app, out), 1)
        self.assertTrue(out.getvalue().rstrip().endswith("결과: 점검 실패"))


class EntryTests(unittest.TestCase):
    """창을 열지 않고 확인하는 것들 — 어디서나 돈다"""

    def test_gui_usage_errors(self):
        for argv in (["gui", "a.png", "b.png"], ["gui", "--wat"]):
            err = io.StringIO()
            with redirect_stderr(err):
                self.assertEqual(app.entry(argv), app.USAGE, argv)
            self.assertIn("사용법", err.getvalue())

    def test_no_arguments_open_the_window_and_arguments_do_not(self):
        with mock.patch.object(app.gui, "run", return_value=0) as run:
            self.assertEqual(app.entry([]), 0)
            self.assertEqual(app.entry(["gui"]), 0)
            self.assertEqual(app.entry(["gui", "x.png"]), 0)
        self.assertEqual([c.args[1] for c in run.call_args_list], [[], [], ["x.png"]])
        with mock.patch.object(app.gui, "run") as run, redirect_stdout(io.StringIO()):
            self.assertEqual(app.entry(["version"]), 0)
            self.assertEqual(app.entry(["help"]), 0)
        run.assert_not_called()

    def test_command_line_path_still_waits_only_when_dropped(self):
        with mock.patch.object(app, "wait_for_enter") as wait, redirect_stdout(io.StringIO()):
            app.entry(["version"])
            wait.assert_not_called()
            app.entry(["no-such-file.png"])
            wait.assert_called_once()

    def test_without_tkinter_the_window_says_so_and_fails(self):
        err = io.StringIO()
        with mock.patch.object(gui, "tk", None), mock.patch.object(gui, "TK_ERROR", "ImportError: 가짜"), redirect_stderr(err):
            self.assertEqual(gui.run(app), app.FAIL)
        self.assertIn("tkinter", err.getvalue())
        self.assertIn("help", err.getvalue())

    def test_without_a_screen_the_window_says_so_and_fails(self):
        if not gui.available():
            self.skipTest("tkinter 가 없다")
        err = io.StringIO()
        with mock.patch.object(gui, "Window", side_effect=gui.tk.TclError("no display")), redirect_stderr(err):
            self.assertEqual(gui.run(app), app.FAIL)
        self.assertIn("no display", err.getvalue())

    def test_check_reports_whether_the_window_is_available(self):
        for have in (True, False):
            out = io.StringIO()
            with mock.patch.object(app.gui, "available", return_value=have):
                self.assertEqual(app.check(out), 0)                  # 창이 없어도 점검은 실패가 아니다
            self.assertIn("창 (tkinter)", out.getvalue())

    def test_console_is_left_alone_off_windows(self):
        if os.name == "nt":
            self.skipTest("Windows 에서는 실제 콘솔을 건드리므로 시험하지 않는다")
        self.assertFalse(gui.hide_own_console())


if __name__ == "__main__":
    unittest.main()
