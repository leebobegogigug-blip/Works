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
import threading
import time
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
import ascii1_gui as gui  # noqa: E402
import synth  # noqa: E402
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

    def art_width(self):
        return max(len(x) for x in self.art().rsplit("\n\n", 1)[0].split("\n"))

    def press(self, keysym, state=0):
        self.win._on_key(types.SimpleNamespace(keysym=keysym, state=state))

    # ---- 시작 상태
    def test_starts_empty_with_nothing_to_save(self):
        w = self.win
        self.assertIsNone(w.text)
        self.assertEqual(str(w.save_button.cget("state")), "disabled")
        self.assertEqual(str(w.copy_button.cget("state")), "disabled")
        self.assertIn("그림을 열어", w.status.cget("text"))
        self.assertEqual([s.text() for s in w.stats.values()], ["----", "----", "----", "----"])
        self.assertEqual([k.value_label.cget("text") for k in w.knobs], ["120", "AUTO", "OFF  - |", "FIT"])

    # ---- 01 SOURCE · 02 STAT · 엔지니어링 값
    def test_open_reads_draws_and_fills_every_zone(self):
        with Folder() as f:
            src = f.put("그림 하나.png", tc.sample("chart"))
            self.open(src)
            w = self.win
            art = self.art().rsplit("\n\n", 1)[0]
            for glyph in "=~":
                self.assertIn(glyph, art)
            self.assertTrue(w.status.cget("text").startswith("OK  그림 하나.png"))
            self.assertEqual(str(w.save_button.cget("state")), "normal")
            seg, _, _ = app.analyze(src)
            self.assertEqual(w.info_png.cget("text"), "SIZE  %d×%d · %s" % (seg.width, seg.height, gui._kb(os.path.getsize(src))))
            self.assertRegex(w.info_time.cget("text"), r"READ  \d+\.\d\ds   DRAW  \d+\.\d\ds")
            self.assertEqual(w.info_kind.cget("text"), "KIND  chart")
            self.assertEqual(w.stats["dots"].text(), str(seg.dots()).rjust(4, "0"))
            self.assertEqual(w.stats["lines"].text(), str(len(seg.of("hline")) + len(seg.of("vline"))).rjust(4, "0"))
            self.assertEqual(w.stats["cols"].text(), str(self.art_width()).rjust(4, "0"))
            self.assertEqual(w.stats["rows"].text(), str(len(art.split("\n"))).rjust(4, "0"))
            self.assertEqual(w.art_memo.cget("text"), "%d열 %d행" % (self.art_width(), len(art.split("\n"))))
            self.assertEqual(w.face.mood, "ok")

    def test_same_picture_as_the_command_line(self):
        with Folder() as f:
            src = f.put("a.png", tc.sample("wafer"))
            self.open(src)
            seg, _, _ = app.analyze(src)
            _, _, text, _ = app.make_art(seg, "a.png", self.win.read_options()[0])
            self.assertEqual(self.win.text, text)
            self.assertEqual(self.art(), text.rstrip("\n"))
            self.assertEqual(self.win.info_kind.cget("text"), "KIND  wafer")

    def test_grid_picture_is_drawn_as_a_frame_like_the_command_line(self):
        """창은 --grid 노브가 없다 — 늘 hide: 격자줄 없이 그림 상자 틀과 범례 한 줄 (설계서 14-11 · DESIGN.md 의 노브 네 개)"""
        with Folder() as f:
            src = f.put("격자.png", tc.png_of(synth.hard_case("B0").image))
            self.open(src)
            text = self.win.text
            seg, _, _ = app.analyze(src)
            self.assertEqual(text, app.make_art(seg, "격자.png", self.win.read_options()[0])[2])
            self.assertEqual(text, app.render.render(seg, 120, grid="hide"))
            lines = text.rsplit("\n\n", 1)[0].split("\n")
            width = max(len(x) for x in lines)
            self.assertEqual(len([x for x in lines if x.count("-") >= 0.5 * width]), 2, "틀의 위 · 아래뿐 — 가로 격자줄이 없다")
            self.assertLessEqual(text.count("+"), 4)
            self.assertIn("격자 가로 17 · 세로 21 줄 생략", self.art())
            self.assertEqual(len(self.win.knobs), 4)

    def test_leds_follow_the_state(self):
        w, t = self.win, self.win.theme
        self.assertEqual((w.led_img.cget("fg"), w.led_art.cget("fg")), (t["led_off"], t["led_off"]))
        with Folder() as f:
            self.open(f.put("a.png", tc.sample("chart")))
            self.assertEqual((w.led_img.cget("fg"), w.led_art.cget("fg")), (t["accent_text"], t["accent_text"]))
            self.open(f.put("not.png", b"nope"))
            self.assertEqual(w.led_art.cget("fg"), t["led_off"])

    # ---- 03 DECK — 노브마다 값이 바뀌고 그림에 연결되는가
    def test_cols_knob_redraws_without_reading_again(self):
        with Folder() as f:
            self.open(f.put("a.png", tc.sample("chart")))
            before = self.art()
            with mock.patch.object(app, "analyze", side_effect=AssertionError("다시 읽으면 안 된다")):
                self.assertTrue(self.win.nudge("cols", -1))                 # 120 → 110
                settle(self.win)
                self.assertEqual(self.win.params["cols"].value, 110)
                self.assertNotEqual(before, self.art())
                self.assertLessEqual(self.art_width(), 110)
                self.assertEqual(self.win.knobs[0].value_label.cget("text"), "110")
                self.win.nudge("cols", +1, fine=True)                       # Shift 는 1 칸
                settle(self.win)
                self.assertEqual(self.win.params["cols"].value, 111)

    def test_cols_knob_stops_at_both_ends(self):
        w = self.win
        self.assertTrue(w.set_param("cols", 5))
        self.assertEqual(w.params["cols"].value, w.app.render.MIN_WIDTH)
        self.assertFalse(w.nudge("cols", -1))
        self.assertTrue(w.set_param("cols", 999))
        self.assertEqual(w.params["cols"].value, w.app.render.MAX_WIDTH)
        self.assertFalse(w.nudge("cols", +1))
        self.assertEqual(w.knobs[0].value_label.cget("text"), str(w.app.render.MAX_WIDTH))

    def test_kind_knob_cycles_and_asks_for_confirmation_when_it_does_not_fit(self):
        with Folder() as f:
            self.open(f.put("a.png", tc.sample("chart")))
            w = self.win
            self.assertTrue(w.nudge("kind", +1))                            # auto → chart
            settle(w)
            self.assertEqual(w.knobs[1].value_label.cget("text"), "CHART")
            self.assertIsNotNone(w.text)
            self.assertTrue(w.nudge("kind", +1))                            # chart → wafer (이 그림은 웨이퍼가 아니다)
            settle(w)
            self.assertIsNone(w.text)
            self.assertEqual(self.art(), "")
            self.assertIn("웨이퍼", w.status.cget("text"))
            self.assertEqual((w.led.cget("text"), w.face.mood), ("‼", "confirm"))
            self.assertEqual(str(w.save_button.cget("state")), "disabled")
            self.assertEqual(w.stats["cols"].text(), "----")
            self.assertTrue(w.nudge("kind", +1))                            # wafer → auto
            settle(w)
            self.assertIsNotNone(w.text)

    def test_box_knob_draws_box_characters(self):
        with Folder() as f:
            self.open(f.put("a.png", tc.sample("chart")))
            self.assertNotIn("─", self.art())
            self.assertTrue(self.win.nudge("box", +1))
            settle(self.win)
            self.assertIn("─", self.art())
            self.assertEqual(self.win.knobs[2].value_label.cget("text"), "ON  ─ │")
            self.win.nudge("box", +1)
            settle(self.win)
            self.assertNotIn("─", self.art())

    def test_size_knob_changes_the_art_font_and_fit_follows_the_columns(self):
        with Folder() as f:
            self.open(f.put("a.png", tc.sample("chart")))
            w = self.win
            self.assertEqual(w.params["size"].value, "fit")
            fit = -int(w.art_font.cget("size"))
            self.assertIn(fit, gui.ART_SIZES)
            w.set_param("size", 32)
            self.assertEqual(int(w.art_font.cget("size")), -32)
            self.assertEqual(w.knobs[3].value_label.cget("text"), "32px")
            w.set_param("size", "fit")
            self.assertEqual(-int(w.art_font.cget("size")), fit)
            w.set_param("cols", 300)                                        # 열이 많아지면 맞춤은 더 작은 글자를 고른다
            settle(w)
            self.assertLessEqual(-int(w.art_font.cget("size")), fit)
            self.assertFalse(w.nudge("size", -10) and w.params["size"].value == "fit")   # 끝에서는 돌지 않고 멈춘다

    def test_every_knob_is_reachable_by_mouse_wheel_button_drag_and_keys(self):
        w = self.win
        w.root.update()
        wheel = w.knobs[0]
        wheel.canvas.event_generate("<Button-4>", state=0)                  # 휠 위
        self.assertEqual(w.params["cols"].value, 130)
        wheel.canvas.event_generate("<Button-5>", state=0)                  # 휠 아래
        self.assertEqual(w.params["cols"].value, 120)
        wheel.canvas.event_generate("<Button-3>", state=0)                  # 오른쪽 클릭 = 내림
        self.assertEqual(w.params["cols"].value, 110)
        wheel.plus.invoke()
        self.assertEqual(w.params["cols"].value, 120)
        wheel.minus.invoke()
        self.assertEqual(w.params["cols"].value, 110)
        wheel.canvas.event_generate("<Button-1>", x=10, y=40, rootx=300, rooty=300)     # 끌기: 위로 16px = 두 칸
        wheel.canvas.event_generate("<B1-Motion>", x=10, y=24, rootx=300, rooty=284)
        wheel.canvas.event_generate("<ButtonRelease-1>")
        self.assertEqual(w.params["cols"].value, 130)
        self.assertEqual(w.selected, 0)
        for i, knob in enumerate(w.knobs):                                  # 번호 키로 고르고 +/− 키로 돌린다
            self.press(str(i + 1))
            self.assertEqual(w.selected, i)
            before = knob.param.value
            self.press("plus")
            self.assertNotEqual(knob.param.value, before, knob.name)
            self.press("minus")
            self.assertEqual(knob.param.value, before, knob.name)
        self.press("2")
        self.press("Up")
        self.assertEqual(w.params["kind"].value, "chart")
        self.press("Down")
        self.assertEqual(w.params["kind"].value, "auto")
        self.press("1")
        self.press("Right", state=0x1)                                      # Shift+방향키 = 한 칸씩
        self.assertEqual(w.params["cols"].value, 131)

    def test_selected_knob_is_marked_with_lime(self):
        w = self.win
        w.select_knob(2)
        self.assertEqual(w.knobs[2].frame.cget("highlightbackground"), w.theme["accent"])
        self.assertEqual(w.knobs[0].frame.cget("highlightbackground"), w.theme["line"])

    def test_knob_colours_are_the_four_encoder_colours_in_order(self):
        self.assertEqual([k.color for k in self.win.knobs], ["#75A1C7", "#6ABA23", "#F2F2F3", "#A5AAAE"])
        self.assertEqual([k.badge.cget("text") for k in self.win.knobs], ["1", "2", "3", "4"])
        dark = self.win
        self.assertEqual([k.value_label.cget("fg") for k in dark.knobs], ["#75A1C7", "#6ABA23", "#F2F2F3", "#A5AAAE"])

    # ---- 00 전체 · 테마
    def test_overview_hides_and_restores_the_left_column(self):
        self.assertIn("ART 크게", self.win.overview_button.cget("text"))
        w = self.win
        w.root.update()
        self.assertTrue(w.left.winfo_ismapped())
        self.assertTrue(w.toggle_overview())
        w.root.update()
        self.assertFalse(w.left.winfo_ismapped())
        self.press("f")
        w.root.update()
        self.assertTrue(w.left.winfo_ismapped())

    def test_theme_cycles_dark_light_system_and_repaints_everything(self):
        w = self.win
        dark, light = gui.THEMES["dark"], gui.THEMES["light"]
        self.assertEqual((w.theme_name, w.view.cget("bg"), w.root.cget("bg")), ("dark", dark["art_bg"], dark["body"]))
        self.assertTrue(w.cycle_theme())
        self.assertEqual((w.theme_name, w.view.cget("bg"), w.root.cget("bg")), ("light", light["art_bg"], light["body"]))
        self.assertEqual(w.stats["dots"].canvas.cget("bg"), light["cell"])
        self.assertEqual(w.theme_button.cget("text"), "THEME LIGHT")
        with mock.patch.object(gui, "detect_system_theme", return_value="light"):
            w.cycle_theme()
            self.assertEqual((w.theme_name, w.view.cget("bg")), ("system", light["art_bg"]))
        with mock.patch.object(gui, "detect_system_theme", return_value="dark"):
            w.set_theme("system")
            self.assertEqual(w.view.cget("bg"), dark["art_bg"])
        w.cycle_theme()
        self.assertEqual(w.theme_name, "dark")
        self.assertFalse(w.set_theme("nope"))

    def test_light_theme_keeps_the_encoder_colour_of_each_knob_value_except_the_white_one(self):
        w = self.win
        w.set_theme("light")
        light = gui.THEMES["light"]
        self.assertEqual([k.value_label.cget("fg") for k in w.knobs], ["#75A1C7", "#6ABA23", light["knob_value"], "#A5AAAE"])
        w.set_theme("dark")
        self.assertEqual([k.value_label.cget("fg") for k in w.knobs], ["#75A1C7", "#6ABA23", "#F2F2F3", "#A5AAAE"])

    def test_dark_is_the_default_and_system_without_windows_is_dark(self):
        self.assertEqual(self.win.theme_name, "dark")
        if os.name != "nt":
            self.assertEqual(gui.detect_system_theme(), "dark")

    # ---- 오류 · 확인 · 일꾼
    def test_unreadable_file_is_shown_as_an_error(self):
        with Folder() as f:
            self.open(f.put("not.png", b"this is not a png"))
            w = self.win
            self.assertEqual(w.chip.cget("text"), "ERR")
            self.assertIsNone(w.text)
            self.assertEqual(w.face.mood, "error")
            self.assertEqual(str(w.save_button.cget("state")), "disabled")
            self.assertEqual(w.stats["dots"].text(), "----")
            w.options_changed()                              # 읽지 못했으니 다시 그릴 것이 없다 — 조용히 아무 일도 없어야 한다
            self.assertFalse(w.busy)
            w.nudge("cols", +1)
            self.assertFalse(w.busy)

    def test_blank_picture_asks_for_confirmation(self):
        with Folder() as f:
            self.open(f.put("blank.png", tc.sample("blank")))
            self.assertIsNone(self.win.text)
            self.assertEqual((self.win.led.cget("text"), self.win.face.mood), ("‼", "confirm"))

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
            self.assertEqual(self.win.face.mood, "busy")
            settle(self.win)
            self.assertEqual(str(self.win.open_button.cget("state")), "normal")

    def test_knob_turned_while_busy_is_applied_after(self):
        with Folder() as f:
            self.assertTrue(self.win.open_path(f.put("a.png", tc.sample("chart"))))
            self.win.set_param("cols", 50)
            self.assertTrue(self.win.pending)
            settle(self.win)
            settle(self.win)
            self.assertLessEqual(self.art_width(), 50)

    def test_activity_is_shown_while_working(self):
        gate = threading.Event()
        real = app.analyze

        def slow(path):
            gate.wait(10)
            return real(path)

        with Folder() as f:
            w = self.win
            src = f.put("a.png", tc.sample("chart"))
            with mock.patch.object(app, "analyze", slow):
                w.open_path(src)
                for _ in range(8):                               # 일꾼이 붙잡혀 있는 동안 창은 살아서 활동을 보여 준다
                    w.root.update()
                    time.sleep(0.05)
                self.assertTrue(w.busy)
                self.assertEqual((w.led.cget("text"), w.face.mood), ("◐", "busy"))
                w.tick = 0
                w._paint_leds()
                self.assertEqual(w.led_busy.cget("fg"), w.theme["accent_text"])
                self.assertGreater(w.sweep.coords(w.sweep_bar)[2], w.sweep.coords(w.sweep_bar)[0])      # 라임 스윕이 오간다
                gate.set()
                settle(w)
            self.assertEqual(w.led_busy.cget("fg"), w.theme["led_off"])
            self.assertEqual(w.sweep.coords(w.sweep_bar)[2], w.sweep.coords(w.sweep_bar)[0])

    # ---- 내보내기 · 도장 · 되돌리기
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

    def test_save_shows_the_stamp_and_a_countdown_then_confirms(self):
        with Folder() as f:
            self.open(f.put("a.png", tc.sample("chart")))
            w = self.win
            w.save()
            w.root.update()
            self.assertTrue(w.stamp.winfo_ismapped())
            self.assertEqual(w.face.mood, "saved")
            self.assertEqual(w.undo_button.cget("text"), "되돌리기 %d" % gui.UNDO_SECONDS)
            self.assertTrue(w.undo_button.winfo_ismapped())
            w.undo_left = 1
            w._undo_tick(w.saved)                            # 초읽기가 끝나면 확정
            w.root.update()
            self.assertFalse(w.undo_button.winfo_ismapped())
            self.assertFalse(w.undo_save())
            self.assertTrue(os.path.exists(os.path.join(f.folder, "a.txt")))
            w.hide_stamp()
            w.root.update()
            self.assertFalse(w.stamp.winfo_ismapped())

    def test_undo_removes_only_the_file_it_just_wrote(self):
        with Folder() as f:
            self.open(f.put("a.png", tc.sample("chart")))
            w = self.win
            first = w.save()
            self.assertTrue(w.undo_save())
            self.assertFalse(os.path.exists(first))
            self.assertIn("되돌렸습니다", w.status.cget("text"))
            self.assertFalse(w.undo_save())                  # 두 번 지우지 않는다
            self.assertEqual(sorted(os.listdir(f.folder)), ["a.png"])

    def test_undo_refuses_to_delete_a_file_that_changed_since(self):
        with Folder() as f:
            self.open(f.put("a.png", tc.sample("chart")))
            w = self.win
            path = w.save()
            with open(path, "a", encoding="utf-8") as g:
                g.write("사용자가 고친 글")
            self.assertFalse(w.undo_save())
            self.assertTrue(os.path.exists(path))
            self.assertIn("바뀌었습니다", w.status.cget("text"))

    def test_undo_leaves_an_earlier_result_alone(self):
        with Folder() as f:
            self.open(f.put("a.png", tc.sample("chart")))
            w = self.win
            first = w.save()
            second = w.save()
            self.assertTrue(w.undo_save())
            self.assertTrue(os.path.exists(first))
            self.assertFalse(os.path.exists(second))

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

    # ---- 검토에서 나온 결함의 재발 방지
    def test_theme_can_change_while_the_stamp_is_up(self):
        with Folder() as f:
            self.open(f.put("a.png", tc.sample("chart")))
            w = self.win
            w.save()
            w.root.update()
            self.assertTrue(w.cycle_theme())                                # TclError 로 중간에 멈추지 않는다
            light = gui.THEMES["light"]
            self.assertEqual(w.stamp.itemcget("stamp_ring", "outline"), light["accent_text"])
            self.assertEqual(w.stamp.itemcget("stamp_text", "fill"), light["accent_text"])
            self.assertEqual(w.stamp.itemcget("stamp_ring", "fill"), "", "동그라미를 라임으로 채워 글자를 묻지 않는다")
            self.assertEqual(w.grid_canvas.cget("bg"), light["body"], "도장 뒤의 다시 칠하기도 끝까지 간다")

    def test_theme_repaints_status_face_leds_and_the_path_line(self):
        with Folder() as f:
            self.open(f.put("a.png", tc.sample("chart")))
            w = self.win
            dark, light = gui.THEMES["dark"], gui.THEMES["light"]
            self.assertEqual(w.path_label.cget("fg"), dark["text"])
            w.set_theme("light")
            self.assertEqual(w.path_label.cget("fg"), light["text"], "경로 줄이 흐린 색으로 돌아가면 안 된다")
            self.assertEqual(w.status.cget("fg"), light["text"])
            self.assertEqual(w.led.cget("fg"), light["accent_text"])
            self.assertEqual(w.face.canvas.itemcget(w.face.eyes, "fill"), light["accent_text"])
            self.assertEqual(w.face.canvas.cget("bg"), light["cell"])
            self.assertEqual(w.led_img.cget("fg"), light["accent_text"])
            self.assertEqual(w.status.cget("bg"), light["block"])
            self.open(f.put("bad.png", b"nope"))
            w.set_theme("dark")
            self.assertEqual(w.status.cget("fg"), dark["err"])
            self.assertEqual(w.chip.cget("text"), "ERR")

    def test_a_second_save_keeps_its_own_stamp(self):
        with Folder() as f:
            self.open(f.put("a.png", tc.sample("chart")))
            w = self.win
            w.save()
            first_job = w.stamp_job
            w.save()
            self.assertNotEqual(w.stamp_job, first_job)
            self.assertNotIn(first_job, w.jobs, "앞 저장의 도장 시계는 취소된다")
            w.root.update()
            self.assertTrue(w.stamp.winfo_ismapped())

    def test_undo_clock_and_stamp_end_when_a_new_picture_is_opened(self):
        with Folder() as f:
            self.open(f.put("a.png", tc.sample("chart")))
            w = self.win
            first = w.save()
            self.open(f.put("bad.png", b"nope"))                           # ERR · 얼굴 error
            self.assertEqual((w.face.mood, w.chip.cget("text")), ("error", "ERR"))
            w.root.update()
            self.assertFalse(w.undo_button.winfo_ismapped())
            self.assertFalse(w.stamp.winfo_ismapped())
            self.assertFalse(w.undo_save(), "새 그림을 연 뒤에는 앞 저장을 되돌리는 버튼이 없다")
            self.assertTrue(os.path.exists(first))
            self.assertEqual((w.face.mood, w.chip.cget("text")), ("error", "ERR"), "얼굴 · 상태줄을 덮어쓰지 않는다")

    def test_undo_is_refused_while_working(self):
        gate = threading.Event()
        real = app.analyze

        def slow(path):
            gate.wait(10)
            return real(path)

        with Folder() as f:
            self.open(f.put("a.png", tc.sample("chart")))
            w = self.win
            path = w.save()
            with mock.patch.object(app, "analyze", slow):
                w.options_changed()                                         # 같은 그림을 다시 그리는 중에는 analyze 를 안 부른다 — 새 그림은 열 수 없으니 busy 만 확인
                w.busy = True
                self.assertFalse(w.undo_save())
                w.busy = False
                gate.set()
            self.assertTrue(os.path.exists(path))
            settle(w)

    def test_save_dialog_never_overwrites_an_existing_file(self):
        with Folder() as f:
            self.open(f.put("a.png", tc.sample("chart")))
            mine = f.put("내 메모.txt", "사용자의 글".encode("utf-8"))
            with mock.patch.object(app, "output_file", side_effect=PermissionError()), \
                    mock.patch.object(gui.filedialog, "asksaveasfilename", return_value=mine) as ask:
                self.assertIsNone(self.win.save())
            self.assertEqual(ask.call_args.kwargs.get("confirmoverwrite"), False)
            with open(mine, encoding="utf-8") as g:
                self.assertEqual(g.read(), "사용자의 글")
            self.assertEqual(self.win.chip.cget("text"), "ERR")
            self.assertIn("덮어쓰지 않습니다", self.win.status.cget("text"))
            self.assertFalse(self.win.undo_save(), "만들지 않은 파일은 되돌리기가 지울 수 없다")
            self.assertTrue(os.path.exists(mine))

    def test_keys_follow_a_real_keyboard(self):
        w = self.win
        self.press("1")
        self.press("plus", state=0x1)                                       # 자판의 + 는 Shift+= — 한 칸이 아니라 10 열
        self.assertEqual(w.params["cols"].value, 130)
        self.press("underscore", state=0x1)                                 # Shift+− 도 −
        self.assertEqual(w.params["cols"].value, 120)
        self.press("equal")
        self.assertEqual(w.params["cols"].value, 130)
        self.press("minus")
        self.assertEqual(w.params["cols"].value, 120)
        self.press("Left", state=0x1)                                       # Shift+방향키만 한 칸
        self.assertEqual(w.params["cols"].value, 119)

    def test_ctrl_and_alt_do_not_turn_knobs_and_numlock_does_not_block_keys(self):
        w = self.win
        self.press("plus", state=0x4)
        self.assertEqual(w.params["cols"].value, 120)
        self.press("plus", state=gui.ALT_MASK)
        self.assertEqual(w.params["cols"].value, 120)
        numlock = 0x10 if os.name != "nt" else 0x8                          # NumLock 이 켜져 있어도 키가 먹는다
        self.press("plus", state=numlock)
        self.assertEqual(w.params["cols"].value, 130)
        self.assertEqual(gui.ALT_MASK, 0x20000 if os.name == "nt" else 0x8)

    def test_dragging_with_shift_turns_one_step_at_a_time(self):
        w = self.win
        w.root.update()
        c = w.knobs[0].canvas
        c.event_generate("<Button-1>", x=10, y=40, rootx=300, rooty=300)
        c.event_generate("<B1-Motion>", x=10, y=24, rootx=300, rooty=284, state=0x101)      # Shift + 왼쪽 단추
        c.event_generate("<ButtonRelease-1>")
        self.assertEqual(w.params["cols"].value, 122)

    def test_size_knob_stops_at_the_ends_and_fit_follows_the_columns(self):
        w = self.win
        size = w.params["size"]
        self.assertEqual(size.values[0], "fit")
        w.set_param("size", 32)
        self.assertFalse(w.nudge("size", +1), "맨 끝에서 처음으로 돌지 않는다")
        self.assertEqual(size.value, 32)
        w.set_param("size", "fit")
        self.assertFalse(w.nudge("size", -1), "FIT 앞은 없다")
        self.assertEqual(size.value, "fit")
        w.root.update()
        w.set_param("cols", 40)
        few = w.fit_size()
        w.set_param("cols", 300)
        many = w.fit_size()
        self.assertGreater(few, many, "열이 많아지면 맞춤은 더 작은 글자를 고른다")

    def test_busy_led_blinks(self):
        w = self.win
        w.busy = True
        seen = set()
        for tick in range(0, 24):
            w.tick = tick
            w._paint_leds()
            seen.add(w.led_busy.cget("fg"))
        w.busy = False
        self.assertEqual(seen, {w.theme["accent_text"], w.theme["led_off"]})

    def test_a_new_picture_clears_the_old_values_at_once(self):
        gate = threading.Event()
        real = app.analyze

        def slow(path):
            gate.wait(10)
            return real(path)

        with Folder() as f:
            first = f.put("a.png", tc.sample("chart"))
            second = f.put("b.png", tc.sample("wafer"))
            self.open(first)
            w = self.win
            with mock.patch.object(app, "analyze", slow):
                w.open_path(second)
                w.root.update()
                self.assertEqual(self.art(), "")
                self.assertEqual([s.text() for s in w.stats.values()], ["----"] * 4)
                self.assertEqual(w.info_png.cget("text"), "SIZE  —")
                self.assertEqual(w.led_art.cget("fg"), w.theme["led_off"])
                self.assertEqual(w.led_img.cget("fg"), w.theme["led_off"])
                gate.set()
                settle(w)
            self.assertIn("b.png", w.path_label.cget("text"))
            self.assertEqual(w.info_kind.cget("text"), "KIND  wafer")

    def test_closing_while_working_leaves_gc_enabled(self):
        import gc as gcmod
        win = gui.Window(app)
        gate = threading.Event()
        real = app.analyze

        def slow(path):
            gate.wait(10)
            return real(path)

        try:
            with Folder() as f, mock.patch.object(app, "analyze", slow):
                win.open_path(f.put("a.png", tc.sample("chart")))
                self.assertFalse(gcmod.isenabled())
                win.root.destroy()
                self.assertTrue(gcmod.isenabled())
                gate.set()
                time.sleep(0.3)
        finally:
            gcmod.enable()
            gc.collect()

    def test_failed_read_clears_a_pending_option(self):
        with Folder() as f:
            w = self.win
            self.assertTrue(w.open_path(f.put("bad.png", b"nope")))
            w.set_param("cols", 50)                                         # 읽는 중에 바꿈 → pending
            settle(w)
            settle(w)
            self.assertFalse(w.pending)

    def test_family_choice_is_fixed_width_only_and_never_proportional(self):
        fixed = {"Unifont": 1, "Consolas": 1, "Malgun Gothic": 0, "D2Coding": 1}
        pick = lambda installed: gui.pick_family(gui.UI_FONTS, set(installed), lambda n: bool(fixed.get(n)))      # noqa: E731
        self.assertEqual(pick(["Malgun Gothic", "Consolas", "Arial"]), "Consolas")
        self.assertEqual(pick(["Unifont", "Consolas"]), "Unifont")
        self.assertIsNone(pick(["Malgun Gothic", "Arial"]), "비례폭만 있으면 고르지 않는다 — 마지막에 Tk 의 고정폭 글꼴")
        self.assertNotIn("Malgun Gothic", gui.UI_FONTS)
        self.assertTrue(self.win.font.metrics("fixed"), "실제로 고른 글꼴은 고정폭이다")

    def test_window_title_uses_the_en_dash_name(self):
        self.assertEqual(self.win.root.title(), "Ascii–1 " + app.VERSION)

    def test_footer_is_a_numbered_zone(self):
        texts = []

        def walk(widget):
            for child in widget.winfo_children():
                if isinstance(child, gui.tk.Label):
                    texts.append(child.cget("text"))
                walk(child)
        walk(self.win.root)
        for want in ("01", "02", "03", "04", "05", "SOURCE", "STAT", "DECK", "ART", "STATUS"):
            self.assertIn(want, texts)

    # ---- 부팅
    def test_boot_can_be_skipped_by_key_and_by_click_and_ends_by_itself(self):
        for how in ("key", "click", "call", "wait"):
            win = gui.Window(app, boot=True)
            try:
                win.root.update()
                self.assertIsNotNone(win.boot_canvas, how)
                if how == "key":
                    win._on_key(types.SimpleNamespace(keysym="a", state=0))
                elif how == "click":
                    win.boot_canvas.event_generate("<Button-1>")
                elif how == "call":
                    self.assertTrue(win.skip_boot())
                else:
                    limit = time.time() + 5
                    while win.boot_canvas is not None and time.time() < limit:
                        win.root.update()
                        time.sleep(0.01)
                win.root.update()
                self.assertIsNone(win.boot_canvas, how)
                self.assertFalse(win.skip_boot(), how)
            finally:
                win.root.destroy()
                gc.collect()

    def test_no_boot_by_default(self):
        self.assertIsNone(self.win.boot_canvas)


class SevenSegTests(unittest.TestCase):
    @unittest.skipIf(NO_DISPLAY, NO_DISPLAY)
    def test_digits_are_padded_with_zeros_and_empty_is_dashes(self):
        root = gui.tk.Tk()
        try:
            seg = gui.SevenSeg(root, digits=4)
            self.assertEqual(seg.text(), "----")
            seg.set(145)
            self.assertEqual(seg.text(), "0145")
            seg.set(123456)
            self.assertEqual(seg.text(), "9999")
            seg.set(0)
            self.assertEqual(seg.text(), "0000")
            lit = lambda i: {k for k, item in seg.cells[i].items() if seg.canvas.itemcget(item, "fill") == seg.theme["big"]}  # noqa: E731
            seg.set(8)
            self.assertEqual(lit(3), set("abcdefg"))
            seg.set(1)
            self.assertEqual(lit(3), set("bc"))
            self.assertEqual(lit(0), set("abcdef"))                      # 앞자리 0
        finally:
            root.destroy()


class DesignRules(unittest.TestCase):
    """DESIGN.md 와 코드가 갈라지지 않는지 — 정본은 docs/DESIGN.md"""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(os.path.dirname(ROOT), "docs", "DESIGN.md"), encoding="utf-8") as f:
            cls.design = f.read()
        with open(os.path.join(ROOT, "ascii1_gui.py"), encoding="utf-8") as f:
            cls.source = f.read()

    def test_every_colour_is_in_the_palette_or_a_neutral_surface(self):
        import re
        allowed = {c.upper() for c in re.findall(r"`(#[0-9A-Fa-f]{6})`", self.design)}
        allowed |= {gui.BODY_DARK.upper(), gui.BODY_LIGHT.upper(), gui.SURFACE_LIGHT.upper(), gui.FAINT_LIGHT.upper()}     # 면 무채색은 표에 없어도 된다
        used = {c.upper() for c in re.findall(r"#[0-9A-Fa-f]{6}", self.source)}
        self.assertEqual(sorted(used - allowed), [], "DESIGN.md 팔레트에도 면 무채색에도 없는 색")
        for c in used:
            r, g, b = (int(c[i:i + 2], 16) for i in (1, 3, 5))
            if c in {x.upper() for x in (gui.BODY_DARK, gui.BODY_LIGHT, gui.SURFACE_LIGHT, gui.FAINT_LIGHT)}:
                self.assertLessEqual(max(r, g, b) - min(r, g, b), 8, "면 무채색은 채도가 거의 없어야 한다 " + c)      # DESIGN 의 #E4E6E8 은 파랑 쪽으로 4 만큼 기운다
            self.assertFalse(r > g + 24 and r > b + 24, c + " 는 붉다 (빨강 없음)")

    def test_encoder_colours_and_order_match_the_design_table(self):
        self.assertIn("① 파랑 `#75A1C7` · ② 라임 `#6ABA23` · ③ 흰색 `#F2F2F3` · ④ 회색 `#A5AAAE`", self.design)
        self.assertEqual(gui.ENCODER, ("#75A1C7", "#6ABA23", "#F2F2F3", "#A5AAAE"))

    def test_status_icons_come_from_the_design_icon_table(self):
        import re
        table = set(re.findall(r"`(.)`", self.design.split("## 03 아이콘")[1].split("## 04")[0]))
        used = set(re.findall(r'_set_status\("(.)"', self.source)) | {"●", "○", "◐"}
        used |= set(re.findall(r'(?:"|\s)(▶)\s', self.source))
        self.assertEqual(sorted(used - table), [], "아이콘 표에 없는 기호")
        for banned in "✓⚠★":
            self.assertNotIn(banned, self.source, "폭 2칸 기호 · 이모지는 쓰지 않는다")

    def test_zones_are_numbered_with_two_digits_and_uppercase_names(self):
        import re
        zones = re.findall(r'_zone\([^,]+, "(\d\d)", "([A-Z]+)"', self.source)
        self.assertEqual(zones, [("01", "SOURCE"), ("02", "STAT"), ("03", "DECK"), ("04", "ART")])
        self.assertNotIn("00 전체", self.source, "DESIGN 의 00 은 전체 보기 — ART 를 키우는 이 동작에 쓰지 않는다")
        self.assertIn('"05"', self.source)

    def test_grid_and_font_sizes_follow_the_eight_pixel_rule(self):
        self.assertEqual(gui.GAP, 8)
        self.assertEqual(gui.LEFT_WIDTH % gui.GAP, 0)
        self.assertEqual(gui.UI_FONTS[0], "Unifont", "글꼴은 GNU Unifont 가 먼저")
        self.assertIn(16, gui.ART_SIZES)
        self.assertIn(32, gui.ART_SIZES)

    def test_only_dark_light_system_themes_exist_and_dark_is_first(self):
        self.assertEqual(gui.THEME_CYCLE, ("dark", "light", "system"))
        self.assertEqual(sorted(gui.THEMES), ["dark", "light"])


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
