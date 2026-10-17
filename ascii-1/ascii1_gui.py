# -*- coding: utf-8 -*-
"""ascii-1 의 작은 창 — 인자 없이 열면 뜬다 (tkinter 는 표준 라이브러리). 창은 얇게: 읽기 · 찾기 · 그리기는 ascii-1.py 의 함수를 그대로 쓴다.

그림을 고르면 요소 찾기(오래 걸릴 수 있다)를 일꾼 스레드에서 돌려 창이 멎지 않게 하고, 열 수 · 종류 · 선 글자를 바꾸면
이미 찾은 요소로 다시 그리기만 한다. 저장은 CLI 와 같은 규칙 — 입력 옆 <이름>.txt, 있으면 덮어쓰지 않고 <이름> (2).txt.
화면 규격은 docs/DESIGN.md: 네이비 · 라임 · 회색, 번호 붙은 구역, 각진 모서리, 빨강 없음 (오류는 ERR 칩 + 가장 밝은 글자)
"""
import gc
import os
import queue
import sys
import tempfile
import threading

try:
    import tkinter as tk
    from tkinter import filedialog, font as tkfont
    TK_ERROR = None
except Exception as e:                      # tkinter 가 없는 파이썬 (예: 일부 리눅스 배포판) — 명령줄로만 쓴다
    tk = filedialog = tkfont = None
    TK_ERROR = "%s: %s" % (e.__class__.__name__, e)

NAVY, NAVY1, NAVY2, NAVY3 = "#002341", "#08365E", "#1F507A", "#3F77A6"
NAVY5 = "#B8CEE0"
LIME, LIME0 = "#6ABA23", "#2C4912"
BLACK, GRAY0, GRAY1, GRAY2, GRAY, GRAY4, WHITE = "#000000", "#35383B", "#5C6166", "#81888D", "#A5AAAE", "#D4D6D8", "#F2F2F3"
FONT_CANDIDATES = ("D2Coding", "NanumGothicCoding", "Consolas", "DejaVu Sans Mono", "Menlo", "Courier New")
KIND_LABELS = (("auto", "자동"), ("chart", "차트"), ("wafer", "웨이퍼"))
GAP = 8                                     # 8px 격자 (DESIGN 원칙 6)
POLL_MS = 40
SELFTEST_SECONDS = 60


def available():
    """창을 쓸 수 있는가 (tkinter 가 있는가) — 화면이 있는지는 열어 봐야 안다"""
    return tk is not None


def hide_own_console():
    """exe 를 두 번 눌러 연 검은 콘솔 창을 숨긴다. 터미널에서 친 것이면 그 창은 건드리지 않는다.
    붙어 있는 프로세스가 우리뿐일 때(한 파일 exe 는 부트로더까지 둘)만 숨기고, 어긋나면 그대로 둔다 — 숨기지 못해도 해는 없다"""
    if os.name != "nt":
        return False
    try:
        import ctypes
        kernel, user = ctypes.windll.kernel32, ctypes.windll.user32
        hwnd = kernel.GetConsoleWindow()
        if not hwnd:
            return False
        ids = (ctypes.c_uint * 8)()
        attached = kernel.GetConsoleProcessList(ids, 8)
        if 0 < attached <= (2 if getattr(sys, "frozen", False) else 1):
            user.ShowWindow(hwnd, 0)
            return True
    except Exception:
        pass
    return False


class Window:
    """창 하나. app 은 ascii-1.py 모듈(analyze · make_art · output_file · 상수)"""

    def __init__(self, app, root=None):
        self.app = app
        self.root = root or tk.Tk()
        self.root.title("%s %s" % (app.NAME, app.VERSION))
        self.root.configure(bg=NAVY)
        self.root.minsize(640, 420)
        self.path = None
        self.seg = None
        self.text = None
        self.busy = False
        self.pending = False                # 일하는 중에 옵션이 바뀌었다 → 끝나면 다시 그린다
        self.results = queue.Queue()
        self.width_var = tk.StringVar(value=str(app.render.DEFAULT_WIDTH))
        self.kind_var = tk.StringVar(value="auto")
        self.box_var = tk.BooleanVar(value=False)
        families = set(tkfont.families(self.root))
        self.art_font = tkfont.Font(root=self.root, family=next((f for f in FONT_CANDIDATES if f in families), "TkFixedFont"), size=10)
        self._build()
        self._set_status("○", "그림을 열어 주세요", muted=True)
        self._sync_buttons()

    # ---------------------------------------------------------------- 화면
    def _zone(self, parent, number, name):
        bar = tk.Frame(parent, bg=NAVY)
        tk.Label(bar, text=number, bg=NAVY2, fg=WHITE, font=("TkDefaultFont", 8, "bold"), padx=4).pack(side="left")
        tk.Label(bar, text=name, bg=NAVY, fg=NAVY5, font=("TkDefaultFont", 8, "bold"), padx=GAP // 2).pack(side="left")
        return bar

    def _button(self, parent, text, command):
        return tk.Button(parent, text=text, command=command, bg=NAVY2, fg=WHITE, activebackground=NAVY3, activeforeground=WHITE,
                         disabledforeground=GRAY1, relief="flat", bd=0, padx=GAP + 4, pady=GAP // 2, highlightthickness=0, cursor="hand2")

    def _build(self):
        r = self.root
        head = tk.Frame(r, bg=NAVY)
        head.pack(fill="x", padx=2 * GAP, pady=(2 * GAP, GAP))
        tk.Label(head, text="ASCII–1", bg=NAVY, fg=WHITE, font=("TkDefaultFont", 14, "bold")).pack(side="left")
        tk.Label(head, text="v" + self.app.VERSION, bg=NAVY2, fg=NAVY5, font=("TkDefaultFont", 8), padx=4).pack(side="left", padx=GAP)
        tk.Label(head, text="PNG 를 글자 아트로", bg=NAVY, fg=GRAY2).pack(side="left")

        top = tk.Frame(r, bg=NAVY)
        top.pack(fill="x", padx=2 * GAP)
        zone = tk.Frame(top, bg=NAVY)
        zone.pack(side="left", fill="x", expand=True)
        self._zone(zone, "01", "OPEN").pack(anchor="w")
        row = tk.Frame(zone, bg=NAVY1)
        row.pack(fill="x", pady=(GAP // 2, 0))
        self.open_button = self._button(row, "그림 열기…", self.choose)
        self.open_button.pack(side="left", padx=GAP, pady=GAP)
        self.path_label = tk.Label(row, text="PNG 파일을 고르세요 (Ctrl+O)", bg=NAVY1, fg=GRAY, anchor="w")
        self.path_label.pack(side="left", fill="x", expand=True)

        opts = tk.Frame(r, bg=NAVY)
        opts.pack(fill="x", padx=2 * GAP, pady=(GAP, 0))
        self._zone(opts, "02", "OPTIONS").pack(anchor="w")
        row = tk.Frame(opts, bg=NAVY1)
        row.pack(fill="x", pady=(GAP // 2, 0))
        tk.Label(row, text="열 수", bg=NAVY1, fg=GRAY, padx=GAP).pack(side="left", pady=GAP)
        self.width_box = tk.Spinbox(row, from_=self.app.render.MIN_WIDTH, to=self.app.render.MAX_WIDTH, increment=10, width=5,
                                    textvariable=self.width_var, command=self.options_changed, bg=BLACK, fg=GRAY4,
                                    insertbackground=GRAY4, buttonbackground=NAVY2, relief="flat", highlightthickness=1,
                                    highlightbackground=NAVY3, highlightcolor=LIME)
        self.width_box.pack(side="left")
        self.width_box.bind("<Return>", lambda _e: self.options_changed())
        self.width_box.bind("<FocusOut>", lambda _e: self.options_changed())
        tk.Label(row, text="%d–%d" % (self.app.render.MIN_WIDTH, self.app.render.MAX_WIDTH), bg=NAVY1, fg=GRAY2, padx=GAP).pack(side="left")
        tk.Label(row, text="종류", bg=NAVY1, fg=GRAY, padx=GAP).pack(side="left")
        for value, label in KIND_LABELS:
            tk.Radiobutton(row, text=label, value=value, variable=self.kind_var, command=self.options_changed, bg=NAVY1, fg=GRAY4,
                           selectcolor=NAVY, activebackground=NAVY1, activeforeground=WHITE, highlightthickness=0).pack(side="left")
        tk.Checkbutton(row, text="선을 ─ │ 로", variable=self.box_var, command=self.options_changed, bg=NAVY1, fg=GRAY4,
                       selectcolor=NAVY, activebackground=NAVY1, activeforeground=WHITE, highlightthickness=0).pack(side="left", padx=GAP)
        self._button(row, "A+", lambda: self.zoom(1)).pack(side="right", padx=(0, GAP), pady=GAP // 2)
        self._button(row, "A−", lambda: self.zoom(-1)).pack(side="right", padx=(0, GAP // 2), pady=GAP // 2)

        foot = tk.Frame(r, bg=NAVY)
        foot.pack(side="bottom", fill="x", padx=2 * GAP, pady=GAP)
        self._zone(foot, "04", "STATUS").pack(anchor="w")
        row = tk.Frame(foot, bg=NAVY1)
        row.pack(fill="x", pady=(GAP // 2, 0))
        self.led = tk.Label(row, text="○", bg=NAVY1, fg=GRAY1, padx=GAP, font=("TkDefaultFont", 11))
        self.led.pack(side="left", pady=GAP)
        self.chip = tk.Label(row, text="", bg=NAVY1, fg=WHITE, font=("TkDefaultFont", 8, "bold"), padx=4)
        self.status = tk.Label(row, text="", bg=NAVY1, fg=GRAY4, anchor="w", justify="left")
        self.status.pack(side="left", fill="x", expand=True)
        self.copy_button = self._button(row, "복사", self.copy)
        self.copy_button.pack(side="right", padx=(0, GAP), pady=GAP // 2)
        self.save_button = self._button(row, "저장 (.txt)", self.save)
        self.save_button.pack(side="right", padx=(0, GAP // 2), pady=GAP // 2)

        art = tk.Frame(r, bg=NAVY)
        art.pack(fill="both", expand=True, padx=2 * GAP, pady=(GAP, 0))
        self._zone(art, "03", "ART").pack(anchor="w")
        body = tk.Frame(art, bg=NAVY3, bd=0)
        body.pack(fill="both", expand=True, pady=(GAP // 2, 0))
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self.view = tk.Text(body, wrap="none", bg=BLACK, fg=GRAY4, insertbackground=GRAY4, font=self.art_font, relief="flat", bd=0,
                            padx=GAP, pady=GAP, highlightthickness=0, state="disabled", cursor="arrow", undo=False)
        self.view.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
        sy = tk.Scrollbar(body, orient="vertical", command=self.view.yview, troughcolor=NAVY, bg=NAVY2, relief="flat", bd=0)
        sx = tk.Scrollbar(body, orient="horizontal", command=self.view.xview, troughcolor=NAVY, bg=NAVY2, relief="flat", bd=0)
        self.view.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")

        r.bind("<Control-o>", lambda _e: self.choose())
        r.bind("<Control-s>", lambda _e: self.save())
        r.bind("<Configure>", self._wrap_status)

    def _wrap_status(self, _event=None):
        self.status.configure(wraplength=max(200, self.root.winfo_width() - 330))

    def zoom(self, step):
        self.art_font.configure(size=min(24, max(6, self.art_font.cget("size") + step)))

    # ---------------------------------------------------------------- 상태
    def _set_status(self, icon, message, muted=False, error=False):
        self.led.configure(text=icon, fg=GRAY1 if muted else (WHITE if error else LIME))
        if error:
            self.chip.configure(text="ERR")
            self.chip.pack(side="left", before=self.status)
        else:
            self.chip.pack_forget()
        self.status.configure(text=message, fg=GRAY2 if muted else (WHITE if error else GRAY4))

    def _sync_buttons(self):
        state = "disabled" if self.busy else "normal"
        self.open_button.configure(state=state)
        can = "normal" if (self.text and not self.busy) else "disabled"
        self.save_button.configure(state=can)
        self.copy_button.configure(state=can)

    def _show(self, text):
        self.view.configure(state="normal")
        self.view.delete("1.0", "end")
        if text:
            self.view.insert("1.0", text)
        self.view.configure(state="disabled")
        self.view.xview_moveto(0)
        self.view.yview_moveto(0)

    # ---------------------------------------------------------------- 옵션
    def read_options(self):
        """창의 옵션 → (opts, 틀린 까닭 또는 None)"""
        opts = {"files": [], "width": self.app.render.DEFAULT_WIDTH, "kind": self.kind_var.get(), "box": bool(self.box_var.get()),
                "stdout": False, "wait": False}
        lo, hi = self.app.render.MIN_WIDTH, self.app.render.MAX_WIDTH
        try:
            opts["width"] = int(self.width_var.get().strip())
        except ValueError:
            return opts, "열 수는 숫자여야 합니다 (%d–%d)" % (lo, hi)
        if not lo <= opts["width"] <= hi:
            return opts, "열 수는 %d–%d 사이여야 합니다 (%d)" % (lo, hi, opts["width"])
        return opts, None

    def options_changed(self):
        if self.busy:                       # 읽는 중에 바꾼 옵션은 잃지 않는다 — 끝나면 이 옵션으로 다시 그린다
            self.pending = True
            return
        if self.seg is None:                # 아직 읽은 그림이 없거나 읽지 못했다 — 다시 그릴 것이 없다
            return
        self._start(None)

    # ---------------------------------------------------------------- 일
    def choose(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(title="그림 열기", filetypes=[("PNG 그림", "*.png"), ("모든 파일", "*.*")])
        if path:
            self.open_path(path)

    def open_path(self, path):
        """그림을 연다 (요소 찾기부터)"""
        if self.busy:
            return False
        self.path = os.path.abspath(path)
        self.seg = None
        self.path_label.configure(text=self.path, fg=GRAY4)
        return self._start(self.path)

    def _start(self, path):
        opts, problem = self.read_options()
        if problem:
            self._set_status("×", problem, error=True)
            return False
        self.busy = True
        self.pending = False
        gc.disable()                        # 순환 쓰레기 치우기가 일꾼 스레드에서 돌면 tk 변수가 엉뚱한 스레드에서 지워져 Tcl 이 죽는다 — 일이 끝나면 주 스레드에서 치운다
        self._sync_buttons()
        self._set_status("◐", "읽는 중… (큰 그림은 오래 걸릴 수 있습니다)" if path else "다시 그리는 중…")
        seg, name = self.seg, os.path.basename(self.path)
        threading.Thread(target=_work, args=(self.app, self.results, path, seg, name, opts), daemon=True).start()
        self.root.after(POLL_MS, self._poll)
        return True

    def _poll(self):
        try:
            seg, code, line, text, shape = self.results.get_nowait()
        except queue.Empty:
            self.root.after(POLL_MS, self._poll)
            return
        self.busy = False
        gc.enable()
        gc.collect()
        self.seg = seg if seg is not None else self.seg
        self.text = text
        self._show(text)
        name = os.path.basename(self.path or "")
        if text is not None:
            self._set_status("●", "OK  %s (%s)" % (name, shape))
        elif code == self.app.FAIL:
            self.seg = None
            self._set_status("×", line.replace("실패  ", "", 1), error=True)
        else:
            self._set_status("‼", line.replace("확인 필요  ", "", 1))
        self._sync_buttons()
        if self.pending:
            self.options_changed()

    # ---------------------------------------------------------------- 내보내기
    def save(self):
        """입력 옆에 <이름>.txt — 있으면 덮어쓰지 않고 <이름> (2).txt. 폴더에 쓸 수 없으면 저장 위치를 묻는다"""
        if not self.text or self.busy or not self.path:
            return None
        try:
            target, f = self.app.output_file(self.path)
        except OSError:
            stem = os.path.splitext(os.path.basename(self.path))[0]
            target = filedialog.asksaveasfilename(title="저장 위치", defaultextension=".txt", initialfile=stem + ".txt",
                                                  filetypes=[("글자 아트", "*.txt")])
            if not target:
                return None
            try:
                f = open(target, "w", encoding="utf-8")
            except OSError as e:
                self._set_status("×", "저장하지 못했습니다 (%s)" % e.__class__.__name__, error=True)
                return None
        with f:
            f.write(self.text)
        self._set_status("√", "저장했습니다: %s" % target)
        return target

    def copy(self):
        if not self.text or self.busy:
            return False
        self.root.clipboard_clear()
        self.root.clipboard_append(self.text)
        self.root.update_idletasks()
        self._set_status("√", "클립보드에 복사했습니다")
        return True


def _work(app, results, path, seg, name, opts):
    """일꾼 스레드 — 창(Window)도 tk 객체도 쥐지 않는다. 창을 닫은 뒤 이 스레드가 tk 변수를 치우면 Tcl 이 죽는다"""
    try:
        code, line, text, shape = app.OK, "", None, ""
        if path is not None:
            seg, code, line = app.analyze(path)
        if seg is not None:
            code, line, text, shape = app.make_art(seg, name, opts)
        results.put((seg, code, line, text, shape))
    except Exception as e:                                    # 어떤 예외든 창에 보여 주고 끝낸다 (스레드가 조용히 죽으면 창이 영영 "읽는 중")
        results.put((None, app.FAIL, "실패  %s: %s: %s" % (name, e.__class__.__name__, e), None, ""))


def run(app, files=()):
    """창을 열고 닫을 때까지 돈다 → 종료 코드. 파일이 주어지면 첫 번째를 바로 연다"""
    if not available():
        sys.stderr.write("창을 열 수 없습니다: 이 파이썬에는 tkinter 가 없습니다 (%s)\n명령줄로 쓰세요: ascii-1.py help\n" % TK_ERROR)
        return app.FAIL
    try:
        win = Window(app)
    except tk.TclError as e:                                  # 화면이 없는 곳 (원격 · 서버)
        sys.stderr.write("창을 열 수 없습니다: %s\n명령줄로 쓰세요: ascii-1.py help\n" % e)
        return app.FAIL
    hide_own_console()
    if files:
        win.root.after(100, lambda: win.open_path(files[0]))
    win.root.mainloop()
    return app.OK


def selftest(app, out=None):
    """창을 실제로 열어 내장 그림 하나를 읽고 그려 본다 (exe 에 창 부품이 제대로 들어갔는지 — `gui --selftest`) → 종료 코드"""
    out = out or sys.stdout
    problems = []
    if not available():
        problems.append("tkinter 가 없습니다 (%s)" % TK_ERROR)
    else:
        win = None
        try:
            win = Window(app)
            w, h = 90, 60
            px = bytearray(b"\xff" * (w * h * 3))
            for y in range(29, 32):
                px[3 * (y * w + 5):3 * (y * w + 85)] = bytes((225, 40, 45)) * 80
            for x in (15, 45, 75):
                for y in range(10, 15):
                    px[3 * (y * w + x):3 * (y * w + x + 5)] = bytes((60, 85, 165)) * 5
            with tempfile.TemporaryDirectory() as tmp:
                src = os.path.join(tmp, "자가 점검.png")
                with open(src, "wb") as f:
                    f.write(app.png_bytes(w, h, bytes(px)))
                win.open_path(src)
                import time
                limit = time.time() + SELFTEST_SECONDS
                while win.busy and time.time() < limit:
                    win.root.update()
                    time.sleep(0.01)
                win.root.update()
                if win.busy:
                    problems.append("%d 초 안에 끝나지 않았습니다" % SELFTEST_SECONDS)
                elif not win.text or sum(win.text.rsplit("\n\n", 1)[0].count(g) for g in "oO@") != 3:
                    problems.append("그림 결과가 기대와 다르다 (붉은 선 하나 · 점 셋)")
                else:
                    out.write("  창 열기 · 그림 읽기 · 그리기  OK\n")
        except Exception as e:
            problems.append("%s: %s" % (e.__class__.__name__, e))
        finally:
            if win is not None:
                try:
                    win.root.destroy()
                except Exception:
                    pass
    for p in problems:
        out.write("  × %s\n" % p)
    code = app.FAIL if problems else app.OK
    out.write(app.RESULT[code] + "\n")
    return code
