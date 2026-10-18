# -*- coding: utf-8 -*-
"""ascii-1 의 작은 창 — 인자 없이 열면 뜬다 (tkinter 는 표준 라이브러리). 창은 얇게: 읽기 · 찾기 · 그리기는 ascii-1.py 의 함수를 그대로 쓴다.

화면은 docs/DESIGN.md 를 따른다 (원칙 일곱 가지):
  1 한 화면 = 한 모드      핵심 값 네 개(COLS · ROWS · DOTS · LINES)를 7세그로 크게
  2 색 = 조작              DECK 의 노브 ①파랑 열 수 · ②라임 종류 · ③흰색 선 글자 · ④회색 글자 크기 — 값은 그 노브의 색으로 보이고 그 노브가 바꾼다
  3 번호 붙은 구역         01 SOURCE · 02 STAT · 03 DECK · 04 ART, `00` 은 전체 보기
  4 엔지니어링을 숨기지 않기  그림 크기 · 읽기 · 그리기 시간 · 감지한 종류 · LED
  5 즉각 반응              활동 LED · 라임 스윕 · 저장하면 도장 + 되돌리기 초읽기
  6 사각 격자              각진 모서리 · 8px 간격 · 점 격자 · 앞자리 0
  7 캐릭터                 점 찍는 활자 — 네모 화면 얼굴이 상태를 보여 준다
글꼴은 GNU Unifont (8×16) 를 권한다 — 없으면 고정폭 글꼴로 대신한다. 테마는 dark(기본) · light · system.
저장은 CLI 와 같은 규칙 — 입력 옆 <이름>.txt, 있으면 덮어쓰지 않고 <이름> (2).txt.
"""
import gc
import math
import os
import queue
import sys
import tempfile
import threading
import time

try:
    import tkinter as tk
    from tkinter import filedialog, font as tkfont
    TK_ERROR = None
except Exception as e:                      # tkinter 가 없는 파이썬 (예: 일부 리눅스 배포판) — 명령줄로만 쓴다
    tk = filedialog = tkfont = None
    TK_ERROR = "%s: %s" % (e.__class__.__name__, e)

# ── 팔레트 (docs/DESIGN.md 02 색) ─────────────────────────────────────────────
NAVY, NAVY1, NAVY2, NAVY3, NAVY4, NAVY5 = "#002341", "#08365E", "#1F507A", "#3F77A6", "#75A1C7", "#B8CEE0"
LIME0, LIME1, LIME, LIME3 = "#2C4912", "#45741B", "#6ABA23", "#95D85A"
BLACK, GRAY0, GRAY1, GRAY2, GRAY, GRAY4, WHITE = "#000000", "#35383B", "#5C6166", "#81888D", "#A5AAAE", "#D4D6D8", "#F2F2F3"
BODY_DARK = "#0B0B0B"                       # 면(surface) 무채색 — 표에 없어도 된다
BODY_LIGHT, SURFACE_LIGHT, FAINT_LIGHT = "#D4D6D8", "#E4E6E8", "#BFC2C5"
ENCODER = (NAVY4, LIME, WHITE, GRAY)        # 인코더 네 색 — ① 파랑 ② 라임 ③ 흰색 ④ 회색, 순서 고정

THEMES = {
    "dark": dict(body=BODY_DARK, block=NAVY, cell=NAVY1, line=NAVY3, chip=NAVY2, chip_fg=WHITE, label=NAVY5, text=GRAY4, dim=GRAY2,
                 faint=GRAY0, accent=LIME, accent_text=LIME, art_bg=BLACK, art_fg=GRAY4, btn=NAVY2, btn_hover=NAVY3, btn_fg=WHITE,
                 btn_off=GRAY1, big=WHITE, dots=GRAY0, knob=GRAY0, led_off=GRAY0, err=WHITE, knob_value=None),
    "light": dict(body=BODY_LIGHT, block=SURFACE_LIGHT, cell=WHITE, line=GRAY, chip=NAVY2, chip_fg=WHITE, label=NAVY1, text=NAVY,
                  dim=GRAY1, faint=FAINT_LIGHT, accent=LIME, accent_text=LIME1, art_bg=WHITE, art_fg=BLACK, btn=NAVY2, btn_hover=NAVY3,
                  btn_fg=WHITE, btn_off=GRAY2, big=NAVY, dots=GRAY, knob=GRAY0, led_off=FAINT_LIGHT, err=NAVY, knob_value=NAVY),
}
THEME_CYCLE = ("dark", "light", "system")

UI_FONTS = ("Unifont", "D2Coding", "NanumGothicCoding", "Consolas", "DejaVu Sans Mono", "Menlo", "Courier New")      # 전부 고정폭 (맑은 고딕은 비례폭이라 뺀다)
ART_SIZES = (8, 10, 12, 14, 16, 20, 24, 32)          # 16 의 정수배(16 · 32)에서 Unifont 가 가장 또렷하다
GAP = 8                                               # 8px 격자 (원칙 6)
LEFT_WIDTH = 304
POLL_MS = 40
ALT_MASK = 0x20000 if os.name == "nt" else 0x8        # Windows 의 Tk 에서 0x8 은 NumLock 이다
SELFTEST_SECONDS = 60
UNDO_SECONDS = 8
STAMP_MS = 2400
BOOT_MS = 900
KIND_VALUES = ("auto", "chart", "wafer")
KIND_SHOW = {"auto": "AUTO", "chart": "CHART", "wafer": "WAFER"}
MOODS = {"idle": ("o o", "_"), "busy": ("- -", "~"), "ok": ("@ @", "v"), "confirm": ("O O", "-"), "error": ("x x", "_"), "saved": ("^ ^", "v")}
DIGITS = {"0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd", "6": "afgedc", "7": "abc", "8": "abcdefg",
          "9": "abcdfg", "-": "g", " ": ""}


def available():
    """창을 쓸 수 있는가 (tkinter 가 있는가) — 화면이 있는지는 열어 봐야 안다"""
    return tk is not None


def detect_system_theme():
    """Windows 의 앱 테마(밝게 · 어둡게). 알 수 없으면 dark (DESIGN: 기본 dark)"""
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
                return "light" if winreg.QueryValueEx(key, "AppsUseLightTheme")[0] else "dark"
        except Exception:
            pass
    return "dark"


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


def pick_family(candidates, installed, is_fixed):
    """후보 중 설치돼 있고 고정폭인 첫 글꼴. 없으면 None (글자 아트 줄이 어긋나지 않게 비례폭은 쓰지 않는다)"""
    for name in candidates:
        if name in installed and is_fixed(name):
            return name
    return None


def shorten(text, width):
    """긴 경로는 가운데를 줄인다"""
    if len(text) <= width:
        return text
    keep = max(4, (width - 1) // 2)
    return text[:keep] + "…" + text[-(width - 1 - keep):]


def _kb(n):
    return "%d B" % n if n < 1024 else ("%.1f KB" % (n / 1024.0) if n < 1 << 20 else "%.1f MB" % (n / float(1 << 20)))


# ── 노브 값 ──────────────────────────────────────────────────────────────────
class Numeric:
    """범위가 있는 수 — nudge 는 step 씩(fine 이면 1씩), 범위 밖으로 나가지 않는다"""

    def __init__(self, lo, hi, value, step, unit=""):
        self.lo, self.hi, self.step, self.unit = lo, hi, step, unit
        self.value = self.clamp(value)

    def clamp(self, v):
        return max(self.lo, min(self.hi, int(v)))

    def set(self, v):
        v = self.clamp(v)
        changed, self.value = v != self.value, v
        return changed

    def nudge(self, direction, fine=False):
        return self.set(self.value + direction * (1 if fine else self.step))

    def fraction(self):
        return (self.value - self.lo) / float(self.hi - self.lo)

    def text(self):
        return "%d%s" % (self.value, self.unit)


class Choice:
    """고르는 값 — wrap 이면 끝에서 처음으로 돈다"""

    def __init__(self, values, value, shows=None, wrap=True):
        self.values, self.wrap = list(values), wrap
        self.shows = shows or {}
        self.value = value if value in self.values else self.values[0]

    def set(self, v):
        if v not in self.values:
            return False
        changed, self.value = v != self.value, v
        return changed

    def nudge(self, direction, fine=False):
        i = self.values.index(self.value) + direction
        i = i % len(self.values) if self.wrap else max(0, min(len(self.values) - 1, i))
        return self.set(self.values[i])

    def fraction(self):
        return self.values.index(self.value) / float(max(1, len(self.values) - 1))

    def text(self):
        return self.shows.get(self.value, str(self.value))


# ── 그림 부품 (Canvas) ───────────────────────────────────────────────────────
class SevenSeg:
    """7세그 큰 숫자 — 자리 수가 고정이고 앞자리는 0 으로 채운다 (카운터: 0145). 값이 없으면 ----"""

    def __init__(self, parent, digits=4, w=18, h=32, gap=6, t=4):
        self.digits = digits
        self.canvas = tk.Canvas(parent, width=digits * w + (digits - 1) * gap, height=h, highlightthickness=0, bd=0)
        self.cells = []
        self.value = None
        self.theme = THEMES["dark"]
        for i in range(digits):
            x = i * (w + gap)
            hw, mid = w - 2 * t, h // 2
            geo = {"a": (x + t, 0, x + t + hw, t), "g": (x + t, mid - t // 2, x + t + hw, mid - t // 2 + t), "d": (x + t, h - t, x + t + hw, h),
                   "f": (x, t + 1, x + t, mid - 1), "b": (x + w - t, t + 1, x + w, mid - 1),
                   "e": (x, mid + 1, x + t, h - t - 1), "c": (x + w - t, mid + 1, x + w, h - t - 1)}
            self.cells.append({k: self.canvas.create_rectangle(*v, width=0) for k, v in geo.items()})

    def set(self, value):
        """value: 수, 또는 None(아직 없음 → ----)"""
        self.value = value
        self.draw()

    def text(self):
        if self.value is None:
            return "-" * self.digits
        return str(min(self.value, 10 ** self.digits - 1)).rjust(self.digits, "0")

    def draw(self):
        for ch, cell in zip(self.text(), self.cells):
            for seg, item in cell.items():
                self.canvas.itemconfigure(item, fill=self.theme["big"] if seg in DIGITS[ch] else self.theme["faint"])

    def restyle(self, theme, bg):
        self.theme = theme
        self.canvas.configure(bg=bg)
        self.draw()


class Face:
    """캐릭터 — 점 찍는 활자. 네모 화면에 눈 · 입을 앱의 글자(o O @ x - ~ _ v)로 찍는다"""

    def __init__(self, parent, font, size=48):
        self.canvas = tk.Canvas(parent, width=size, height=size, highlightthickness=0, bd=0)
        self.mood, self.theme = "idle", THEMES["dark"]
        self.frame = self.canvas.create_rectangle(1, 1, size - 2, size - 2, width=1)
        self.eyes = self.canvas.create_text(size // 2, size // 3 + 1, font=font)
        self.mouth = self.canvas.create_text(size // 2, 2 * size // 3 + 1, font=font)
        self.set("idle")

    def set(self, mood):
        self.mood = mood
        eyes, mouth = MOODS[mood]
        self.canvas.itemconfigure(self.eyes, text=eyes)
        self.canvas.itemconfigure(self.mouth, text=mouth)
        self.restyle(self.theme)

    def restyle(self, theme, bg=None):
        self.theme = theme
        color = theme["accent_text"] if self.mood in ("ok", "saved") else (theme["big"] if self.mood in ("error", "confirm") else theme["text"])
        self.canvas.configure(bg=theme["cell"])
        self.canvas.itemconfigure(self.frame, outline=theme["line"])
        self.canvas.itemconfigure(self.eyes, fill=color)
        self.canvas.itemconfigure(self.mouth, fill=color)


class Knob:
    """노브 — 번호표 · 돌림(−/+ 버튼 · 휠 · 끌기 · 키) · 값은 노브의 색. 값 자체는 Param(Numeric · Choice) 이 갖는다"""
    R = 20

    def __init__(self, win, parent, index, name, param, key, font):
        self.win, self.index, self.name, self.param, self.key = win, index, name, param, key
        self.color = ENCODER[index]
        self.theme = THEMES["dark"]
        self.drag = None
        self.frame = tk.Frame(parent, highlightthickness=1, bd=0)
        size = 2 * self.R + 8
        self.canvas = tk.Canvas(self.frame, width=size, height=size, highlightthickness=0, bd=0, cursor="sb_v_double_arrow")
        self.minus = tk.Button(self.frame, text="−", font=font, relief="flat", bd=0, padx=6, pady=0, highlightthickness=0, cursor="hand2",
                               command=lambda: win.nudge(key, -1))
        self.plus = tk.Button(self.frame, text="+", font=font, relief="flat", bd=0, padx=6, pady=0, highlightthickness=0, cursor="hand2",
                              command=lambda: win.nudge(key, +1))
        self.badge = tk.Label(self.frame, text=str(index + 1), font=font, padx=3, pady=0, highlightthickness=1)
        self.name_label = tk.Label(self.frame, text=name, font=font, anchor="w", padx=0, pady=0)
        self.value_label = tk.Label(self.frame, text="", font=font, anchor="w", pady=0)
        self.badge.grid(row=0, column=0, sticky="nw", padx=(4, 0), pady=(4, 0))
        self.name_label.grid(row=0, column=1, columnspan=2, sticky="w", padx=4, pady=(4, 0))
        self.minus.grid(row=1, column=0, sticky="e", padx=(4, 0))
        self.canvas.grid(row=1, column=1)
        self.plus.grid(row=1, column=2, sticky="w", padx=(0, 4))
        self.value_label.grid(row=2, column=0, columnspan=3, sticky="ew", padx=4, pady=(0, 4))
        self.ring = self.canvas.create_oval(4, 4, 2 * self.R + 4, 2 * self.R + 4, width=2)
        self.hub = self.canvas.create_oval(self.R, self.R, self.R + 8, self.R + 8, width=0)
        self.pointer = self.canvas.create_line(0, 0, 0, 0, width=3, capstyle="round")
        for widget in (self.canvas, self.frame):
            widget.bind("<MouseWheel>", self._wheel)
            widget.bind("<Button-4>", lambda e: self._wheel(e, +1))
            widget.bind("<Button-5>", lambda e: self._wheel(e, -1))
        self.canvas.bind("<Button-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._motion)
        self.canvas.bind("<ButtonRelease-1>", lambda _e: setattr(self, "drag", None))
        self.canvas.bind("<Button-3>", lambda e: win.nudge(key, -1, fine=bool(e.state & 0x1)))

    def _wheel(self, event, direction=None):
        if direction is None:
            direction = 1 if event.delta > 0 else -1
        self.win.nudge(self.key, direction, fine=bool(event.state & 0x1))

    def _press(self, event):
        self.win.select_knob(self.index)
        self.drag = event.y_root

    def _motion(self, event):
        if self.drag is None:
            return
        steps = int((self.drag - event.y_root) / 8)                  # 위로 8px 끌면 한 칸 올린다
        if steps:
            self.drag = event.y_root
            for _ in range(abs(steps)):
                self.win.nudge(self.key, 1 if steps > 0 else -1, fine=bool(event.state & 0x1))

    def refresh(self, selected):
        ang = math.radians(225 - 270 * self.param.fraction())
        c = self.R + 4
        self.canvas.coords(self.pointer, c, c, c + (self.R - 3) * math.cos(ang), c - (self.R - 3) * math.sin(ang))
        self.value_label.configure(text=self.param.text())
        self.frame.configure(highlightbackground=self.theme["accent"] if selected else self.theme["line"])

    def restyle(self, theme, selected):
        self.theme = theme
        self.frame.configure(bg=theme["cell"], highlightcolor=theme["accent"])
        self.canvas.configure(bg=theme["cell"])
        self.canvas.itemconfigure(self.ring, outline=self.color, fill=theme["knob"])
        self.canvas.itemconfigure(self.hub, fill=self.color)
        self.canvas.itemconfigure(self.pointer, fill=self.color)
        for button in (self.minus, self.plus):
            button.configure(bg=theme["btn"], fg=theme["btn_fg"], activebackground=theme["btn_hover"], activeforeground=theme["btn_fg"])
        self.badge.configure(bg=self.color, fg=BLACK, highlightbackground=theme["line"])          # 흰 번호표가 밝은 칸에서 사라지지 않게 가는 테두리
        self.name_label.configure(bg=theme["cell"], fg=theme["label"])
        self.value_label.configure(bg=theme["cell"], fg=(theme["knob_value"] if self.color == WHITE and theme["knob_value"] else self.color))      # 값은 노브의 색 (밝은 테마의 흰 노브만 글자색으로)
        self.refresh(selected)


# ── 창 ──────────────────────────────────────────────────────────────────────
class Window:
    """창 하나. app 은 ascii-1.py 모듈(analyze · make_art · output_file · 상수). boot=True 면 켤 때 부팅 연출(아무 키나 눌러 건너뛴다)"""

    def __init__(self, app, root=None, boot=False):
        self.app = app
        self.root = root or tk.Tk()
        self.root.title("Ascii–1 %s" % app.VERSION)
        self.root.minsize(880, 680)
        self.root.geometry("1056x736")
        self.path = None
        self.seg = None
        self.text = None
        self.info = {}
        self.busy = False
        self.pending = False                # 일하는 중에 옵션이 바뀌었다 → 끝나면 다시 그린다
        self.results = queue.Queue()
        self.saved = None                   # (경로, 쓴 글) — 되돌리기가 지울 수 있는 것은 우리가 방금 만든 이 파일뿐
        self.undo_left = 0
        self.stamp_job = None
        self.theme_name = "dark"
        self.theme = THEMES["dark"]
        self.selected = 0
        self.overview = False
        self.tick = 0
        self.sweep_x = 0
        self.sweep_dir = 1
        self.boot_canvas = None
        self.styled = []
        self.jobs = set()                   # 걸어 둔 after — 창을 닫을 때 모두 취소한다 (안 하면 지워진 명령을 부르다 Tcl 이 오류를 찍는다)
        self.status_icon, self.status_error = "○", False
        self.params = {
            "cols": Numeric(app.render.MIN_WIDTH, app.render.MAX_WIDTH, app.render.DEFAULT_WIDTH, 10),
            "kind": Choice(KIND_VALUES, "auto", KIND_SHOW),
            "box": Choice((False, True), False, {False: "OFF  - |", True: "ON  ─ │"}),
            "size": Choice(("fit",) + ART_SIZES, "fit", dict([("fit", "FIT")] + [(s, "%dpx" % s) for s in ART_SIZES]), wrap=False),
        }
        installed = set(tkfont.families(self.root))
        self.family = pick_family(UI_FONTS, installed, lambda n: bool(tkfont.Font(root=self.root, family=n, size=-16).metrics("fixed"))) \
            or tkfont.nametofont("TkFixedFont").actual("family")
        self.font = tkfont.Font(root=self.root, family=self.family, size=-16)
        self.font_big = tkfont.Font(root=self.root, family=self.family, size=-32)
        self.art_font = tkfont.Font(root=self.root, family=self.family, size=-16)
        self._measure_fonts = {}
        self._build()
        self.set_theme("dark")
        self._set_status("○", "그림을 열어 주세요", muted=True)
        self._sync_buttons()
        self.root.bind("<Destroy>", self._on_destroy, add="+")
        self._after(POLL_MS, self._tick)
        if boot:
            self.start_boot()

    # ---------------------------------------------------------------- 만들기
    def _after(self, ms, fn, *args):
        job = None

        def run():
            self.jobs.discard(job)
            fn(*args)

        job = self.root.after(ms, run)
        self.jobs.add(job)
        return job

    def _on_destroy(self, event):
        if event.widget is self.root:
            gc.enable()                     # 일하는 중에 닫아도 gc 를 켜 둔 채로 돌려준다
            for job in list(self.jobs):
                try:
                    self.root.after_cancel(job)
                except Exception:
                    pass
            self.jobs.clear()

    def paint(self, widget, **roles):
        """위젯의 옵션을 테마 토큰에 묶는다 — 테마를 바꾸면 다시 칠한다"""
        self.styled.append((widget, roles))
        widget.configure(**{opt: self.theme[tok] for opt, tok in roles.items()})
        return widget

    def restyle_role(self, widget, **roles):
        """이미 칠한 위젯의 토큰을 바꾼다 — 테마를 바꿔도 새 토큰이 따라간다"""
        for i, (w, old) in enumerate(self.styled):
            if w is widget:
                self.styled[i] = (w, dict(old, **roles))
        widget.configure(**{opt: self.theme[tok] for opt, tok in roles.items()})

    def _zone(self, parent, number, name, note=""):
        """번호 붙은 구역 → (블록, 몸통, 오른쪽 메모 라벨)"""
        block = self.paint(tk.Frame(parent, highlightthickness=1, bd=0), bg="block", highlightbackground="line")
        head = self.paint(tk.Frame(block), bg="block")
        head.pack(fill="x", padx=GAP, pady=(GAP, GAP // 2))
        self.paint(tk.Label(head, text=number, font=self.font, padx=3, pady=0), bg="chip", fg="chip_fg").pack(side="left")
        self.paint(tk.Label(head, text=name, font=self.font, padx=GAP // 2, pady=0), bg="block", fg="label").pack(side="left")
        memo = self.paint(tk.Label(head, text=note, font=self.font, anchor="e", pady=0), bg="block", fg="dim")
        memo.pack(side="right")
        body = self.paint(tk.Frame(block), bg="block")
        body.pack(fill="both", expand=True, padx=GAP, pady=(0, GAP))
        return block, body, memo

    def _button(self, parent, text, command):
        return self.paint(tk.Button(parent, text=text, command=command, font=self.font, relief="flat", bd=0, padx=GAP, pady=2,
                                    highlightthickness=0, cursor="hand2"),
                          bg="btn", fg="btn_fg", activebackground="btn_hover", activeforeground="btn_fg", disabledforeground="btn_off")

    def _build(self):
        r = self.root
        self.grid_canvas = tk.Canvas(r, highlightthickness=0, bd=0)           # 8px 점 격자 — 구역 사이의 틈에 비친다
        self.grid_canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.grid_canvas.bind("<Configure>", lambda _e: self._draw_grid())
        r.columnconfigure(1, weight=1)
        r.rowconfigure(1, weight=1)

        # 머리: 캐릭터 · 이름 · LED · 버전 · 00 · 테마
        head = self.paint(tk.Frame(r, highlightthickness=1, bd=0), bg="block", highlightbackground="line")
        head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=GAP, pady=(GAP, 0))
        self.face = Face(head, self.font, 48)
        self.face.canvas.pack(side="left", padx=GAP, pady=GAP)
        titles = self.paint(tk.Frame(head), bg="block")
        titles.pack(side="left")
        self.paint(tk.Label(titles, text="Ascii–1", font=self.font_big, anchor="w", pady=0), bg="block", fg="big").pack(anchor="w")
        self.paint(tk.Label(titles, text="PNG → 글자 아트 · 점 찍는 활자", font=self.font, anchor="w", pady=0), bg="block", fg="dim").pack(anchor="w")
        right = self.paint(tk.Frame(head), bg="block")
        right.pack(side="right", padx=GAP)
        row = self.paint(tk.Frame(right), bg="block")
        row.pack(anchor="e")
        self.led_img = self.paint(tk.Label(row, text="● img", font=self.font, padx=GAP // 2, pady=0), bg="block", fg="dim")
        self.led_img.pack(side="left")
        self.led_art = self.paint(tk.Label(row, text="● art", font=self.font, padx=GAP // 2, pady=0), bg="block", fg="dim")
        self.led_art.pack(side="left")
        self.led_busy = self.paint(tk.Label(row, text="● busy", font=self.font, padx=GAP // 2, pady=0), bg="block", fg="dim")
        self.led_busy.pack(side="left")
        self.paint(tk.Label(row, text="v" + self.app.VERSION, font=self.font, padx=3, pady=0), bg="chip", fg="chip_fg").pack(side="left", padx=(GAP, 0))
        row = self.paint(tk.Frame(right), bg="block")
        row.pack(anchor="e", pady=(GAP // 2, 0))
        self.overview_button = self._button(row, "ART 크게  F", self.toggle_overview)
        self.overview_button.pack(side="left", padx=(0, GAP // 2))
        self.theme_button = self._button(row, "THEME", self.cycle_theme)
        self.theme_button.pack(side="left")

        # 왼쪽 열: 01 SOURCE · 02 STAT · 03 DECK
        self.left = self.paint(tk.Frame(r, width=LEFT_WIDTH), bg="body")
        self.left.grid(row=1, column=0, sticky="ns", padx=(GAP, 0), pady=GAP)
        self.left.pack_propagate(False)

        block, body, self.source_memo = self._zone(self.left, "01", "SOURCE", "PNG")
        block.pack(fill="x")
        self.open_button = self._button(body, "▶ 그림 열기  Ctrl+O", self.choose)
        self.open_button.pack(fill="x")
        self.path_label = self.paint(tk.Label(body, text="PNG · JPEG 파일을 고르세요", font=self.font, anchor="w", pady=0), bg="block", fg="dim")
        self.path_label.pack(fill="x", pady=(GAP // 2, 0))
        self.info_png = self.paint(tk.Label(body, text="SIZE  —", font=self.font, anchor="w", pady=0), bg="block", fg="text")
        self.info_png.pack(fill="x")
        self.info_time = self.paint(tk.Label(body, text="READ  —   DRAW  —", font=self.font, anchor="w", pady=0), bg="block", fg="text")
        self.info_time.pack(fill="x")
        self.info_kind = self.paint(tk.Label(body, text="KIND  —", font=self.font, anchor="w", pady=0), bg="block", fg="text")
        self.info_kind.pack(fill="x")

        block, body, self.stat_memo = self._zone(self.left, "02", "STAT", "")
        block.pack(fill="x", pady=(GAP, 0))
        self.stats = {}
        for i, (key, label) in enumerate((("cols", "COLS"), ("rows", "ROWS"), ("dots", "DOTS"), ("lines", "LINES"))):
            cell = self.paint(tk.Frame(body, highlightthickness=0), bg="cell")
            cell.grid(row=i // 2, column=i % 2, sticky="ew", padx=(0, GAP // 2) if i % 2 == 0 else (GAP // 2, 0), pady=(0, GAP // 2))
            body.columnconfigure(i % 2, weight=1)
            self.paint(tk.Label(cell, text=label, font=self.font, anchor="w", pady=0), bg="cell", fg="label").pack(anchor="w", padx=GAP // 2)
            seg = SevenSeg(cell, digits=4, w=14, h=28, gap=5, t=3)
            seg.canvas.pack(anchor="w", padx=GAP // 2, pady=(0, GAP // 2))
            self.stats[key] = seg

        block, body, self.deck_memo = self._zone(self.left, "03", "DECK", "1–4 · +/−")
        block.pack(fill="x", pady=(GAP, 0))
        self.knobs = []
        for i, (key, name) in enumerate((("cols", "열 수"), ("kind", "종류"), ("box", "선 글자"), ("size", "글자 크기"))):
            knob = Knob(self, body, i, name, self.params[key], key, self.font)
            knob.frame.grid(row=i // 2, column=i % 2, sticky="nsew", padx=(0, GAP // 2) if i % 2 == 0 else (GAP // 2, 0), pady=(0, GAP // 2))
            body.columnconfigure(i % 2, weight=1)
            self.knobs.append(knob)

        # 오른쪽: 04 ART
        block, body, self.art_memo = self._zone(r, "04", "ART", "")
        block.grid(row=1, column=1, sticky="nsew", padx=GAP, pady=GAP)
        self.sweep = tk.Canvas(body, height=3, highlightthickness=0, bd=0)
        self.paint(self.sweep, bg="faint")
        self.sweep.pack(fill="x")
        self.sweep_bar = self.sweep.create_rectangle(0, 0, 0, 3, width=0)
        frame = self.paint(tk.Frame(body, highlightthickness=1, bd=0), bg="art_bg", highlightbackground="line")
        frame.pack(fill="both", expand=True, pady=(GAP // 2, 0))
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.view = self.paint(tk.Text(frame, wrap="none", font=self.art_font, relief="flat", bd=0, padx=GAP, pady=GAP, highlightthickness=0,
                                       state="disabled", cursor="arrow", undo=False, takefocus=0, width=1, height=1),
                               bg="art_bg", fg="art_fg", insertbackground="art_fg", selectbackground="chip")
        self.view.grid(row=0, column=0, sticky="nsew")
        self.scroll_y = self.paint(tk.Scrollbar(frame, orient="vertical", command=self.view.yview, relief="flat", bd=0),
                                   troughcolor="block", bg="chip")
        self.scroll_x = self.paint(tk.Scrollbar(frame, orient="horizontal", command=self.view.xview, relief="flat", bd=0),
                                   troughcolor="block", bg="chip")
        self.view.configure(yscrollcommand=self.scroll_y.set, xscrollcommand=self.scroll_x.set)
        self.scroll_y.grid(row=0, column=1, sticky="ns")
        self.scroll_x.grid(row=1, column=0, sticky="ew")
        self.view.bind("<Configure>", lambda _e: self._apply_size())

        # 발: 상태 줄
        foot = self.paint(tk.Frame(r, highlightthickness=1, bd=0), bg="block", highlightbackground="line")
        foot.grid(row=2, column=0, columnspan=2, sticky="ew", padx=GAP, pady=(0, GAP))
        self.paint(tk.Label(foot, text="05", font=self.font, padx=3, pady=0), bg="chip", fg="chip_fg").pack(side="left", padx=(GAP, 0))
        self.paint(tk.Label(foot, text="STATUS", font=self.font, padx=GAP // 2, pady=0), bg="block", fg="label").pack(side="left")
        self.led = self.paint(tk.Label(foot, text="○", font=self.font, padx=GAP, pady=GAP // 2), bg="block", fg="dim")
        self.led.pack(side="left")
        self.chip = self.paint(tk.Label(foot, text="", font=self.font, padx=3, pady=0), bg="chip", fg="chip_fg")
        self.status = self.paint(tk.Label(foot, text="", font=self.font, anchor="w", justify="left", pady=0), bg="block", fg="text")
        self.status.pack(side="left", fill="x", expand=True)
        self.copy_button = self._button(foot, "복사", self.copy)
        self.copy_button.pack(side="right", padx=(0, GAP), pady=GAP // 2)
        self.save_button = self._button(foot, "저장 .txt  Ctrl+S", self.save)
        self.save_button.pack(side="right", padx=(0, GAP // 2), pady=GAP // 2)
        self.undo_button = self._button(foot, "", self.undo_save)
        self.stamp = self.paint(tk.Canvas(foot, width=56, height=40, highlightthickness=0, bd=0), bg="block")
        self.face.set("idle")

        r.bind("<Control-o>", lambda _e: self.choose())
        r.bind("<Control-s>", lambda _e: self.save())
        r.bind("<Control-Shift-C>", lambda _e: self.copy())
        r.bind("<Control-t>", lambda _e: self.cycle_theme())
        r.bind("<Key>", self._on_key)
        r.bind("<Button-1>", lambda _e: self.skip_boot(), add="+")
        r.bind("<Configure>", self._wrap_status, add="+")

    def _draw_grid(self):
        c = self.grid_canvas
        c.delete("all")
        w, h = max(1, c.winfo_width()), max(1, c.winfo_height())
        for y in range(GAP // 2, h, GAP):
            c.create_line(0, y, w, y, fill=self.theme["dots"], dash=(1, GAP - 1))

    def _wrap_status(self, _event=None):
        self.status.configure(wraplength=max(200, self.root.winfo_width() - 460))

    # ---------------------------------------------------------------- 테마
    def resolved_theme(self):
        return detect_system_theme() if self.theme_name == "system" else self.theme_name

    def set_theme(self, name):
        if name not in THEME_CYCLE:
            return False
        self.theme_name = name
        self.theme = t = THEMES[self.resolved_theme()]
        self.root.configure(bg=t["body"])
        self.grid_canvas.configure(bg=t["body"])
        for widget, roles in self.styled:
            widget.configure(**{opt: t[tok] for opt, tok in roles.items()})
        for seg in self.stats.values():
            seg.restyle(t, t["cell"])
        self.face.restyle(t)
        for knob in self.knobs:
            knob.restyle(t, knob.index == self.selected)
        self.theme_button.configure(text="THEME %s" % name.upper())
        self.stamp.itemconfigure("stamp_ring", outline=t["accent_text"])
        self.stamp.itemconfigure("stamp_text", fill=t["accent_text"])
        self._set_status(self.status_icon, self.status.cget("text"), muted=not self.text and self.path is None, error=self.status_error)
        self._draw_grid()
        self._paint_leds()
        self._draw_sweep()
        if self.boot_canvas is not None:
            self.boot_canvas.configure(bg=t["body"])
        return True

    def cycle_theme(self):
        return self.set_theme(THEME_CYCLE[(THEME_CYCLE.index(self.theme_name) + 1) % len(THEME_CYCLE)])

    # ---------------------------------------------------------------- 상태
    def _paint_leds(self):
        t = self.theme
        self.led_img.configure(fg=t["accent_text"] if self.seg is not None else t["led_off"])
        self.led_art.configure(fg=t["accent_text"] if self.text else t["led_off"])
        self.led_busy.configure(fg=t["accent_text"] if (self.busy and (self.tick // 6) % 2 == 0) else t["led_off"])

    def _set_status(self, icon, message, muted=False, error=False):
        t = self.theme
        self.led.configure(text=icon, fg=t["dim"] if muted else (t["err"] if error else t["accent_text"]))
        if error:
            self.chip.configure(text="ERR")
            self.chip.pack(side="left", before=self.status)
        else:
            self.chip.pack_forget()
        self.status.configure(text=message, fg=t["dim"] if muted else (t["err"] if error else t["text"]))
        self.status_icon, self.status_error = icon, error

    def _sync_buttons(self):
        self.open_button.configure(state="disabled" if self.busy else "normal")
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
        self._apply_size()

    def _show_info(self, info):
        if not info or "w" not in info:
            self.info_png.configure(text="SIZE  —")
            self.info_time.configure(text="READ  —   DRAW  —")
            self.info_kind.configure(text="KIND  —")
            return
        self.info_png.configure(text="SIZE  %d×%d · %s" % (info["w"], info["h"], _kb(info["bytes"])))
        read = "%.2fs" % info["read"] if info.get("read") is not None else "—"
        draw = "%.2fs" % info["draw"] if info.get("draw") is not None else "—"
        self.info_time.configure(text="READ  %s   DRAW  %s" % (read, draw))
        self.info_kind.configure(text="KIND  %s" % info["kind"])

    def _show_stats(self, info):
        info = info or {}
        values = tuple(info.get(k) for k in ("cols", "rows", "dots", "lines"))
        self.art_memo.configure(text="%d열 %d행" % (info["cols"], info["rows"]) if info.get("cols") is not None else "")
        for seg, v in zip(self.stats.values(), values):
            seg.set(v)
        over = [k for k, v in zip(self.stats, values) if v is not None and v > 10 ** self.stats[k].digits - 1]
        self.stat_memo.configure(text=("%s 넘침" % "·".join(k.upper() for k in over)) if over else "")

    # ---------------------------------------------------------------- 글자 크기
    def _px_width(self, px):
        if px not in self._measure_fonts:
            self._measure_fonts[px] = tkfont.Font(root=self.root, family=self.family, size=-px)
        return self._measure_fonts[px].measure("0")

    def fit_size(self):
        """ART 폭에 그림이 들어가는 가장 큰 글자 크기(px) — 안 들어가면 가장 작은 것"""
        cols = self.info.get("cols") or self.params["cols"].value
        avail = self.view.winfo_width() - 2 * GAP - 4
        if avail < 100:
            avail = 640
        fits = [px for px in ART_SIZES if self._px_width(px) * cols <= avail]
        return max(fits) if fits else min(ART_SIZES)

    def _apply_size(self):
        want = self.params["size"].value
        px = self.fit_size() if want == "fit" else want
        if self.art_font.cget("size") != -px:
            self.art_font.configure(size=-px)
        self.deck_memo.configure(text=("1–4 · +/− · %dpx" % px) if want == "fit" else "1–4 · +/−")

    # ---------------------------------------------------------------- 노브 · 키
    def select_knob(self, index):
        self.selected = index % len(self.knobs)
        for knob in self.knobs:
            knob.refresh(knob.index == self.selected)

    def nudge(self, key, direction, fine=False):
        """노브를 돌린다 → 값이 바뀌었는가"""
        changed = self.params[key].nudge(direction, fine)
        if changed:
            self._param_changed(key)
        return changed

    def set_param(self, key, value):
        changed = self.params[key].set(value)
        if changed:
            self._param_changed(key)
        return changed

    def _param_changed(self, key):
        for knob in self.knobs:
            if knob.key == key:
                knob.refresh(knob.index == self.selected)
        if key == "size":
            self._apply_size()
        else:
            self.options_changed()

    def _on_key(self, event):
        if self.skip_boot():
            return
        if event.state & 0x4 or event.state & ALT_MASK:      # Ctrl · Alt 조합은 단축키가 따로 받는다
            return
        k, shift = event.keysym, bool(event.state & 0x1)
        key = self.knobs[self.selected].key
        if k in ("1", "2", "3", "4"):
            self.select_knob(int(k) - 1)
        elif k == "f":
            self.toggle_overview()
        elif k in ("plus", "equal", "KP_Add"):               # 자판에서 + 는 Shift+= 이므로 Shift 를 한 칸 조정으로 읽지 않는다
            self.nudge(key, +1)
        elif k in ("minus", "underscore", "KP_Subtract"):
            self.nudge(key, -1)
        elif k in ("Up", "Down", "Left", "Right") and self.root.focus_get() is not self.view:
            self.nudge(key, +1 if k in ("Up", "Right") else -1, shift)           # Shift+방향키 = 한 칸씩

    def toggle_overview(self):
        """ART 크게 — 왼쪽 열을 접고 ART 를 넓게 (키 F). DESIGN 의 `00` 은 전체 보기라 이 동작에는 쓰지 않는다"""
        self.overview = not self.overview
        if self.overview:
            self.left.grid_remove()
            self.overview_button.configure(text="되돌림  F")
        else:
            self.left.grid()
            self.overview_button.configure(text="ART 크게  F")
        self.root.update_idletasks()
        self._apply_size()
        return self.overview

    # ---------------------------------------------------------------- 옵션 · 일
    def read_options(self):
        """창의 옵션 → (opts, 틀린 까닭 또는 None). 노브는 범위 밖으로 가지 못하므로 틀릴 일이 없다"""
        p = self.params
        return {"files": [], "width": p["cols"].value, "kind": p["kind"].value, "box": bool(p["box"].value), "stdout": False, "wait": False}, None

    def options_changed(self):
        if self.busy:                       # 읽는 중에 바꾼 옵션은 잃지 않는다 — 끝나면 이 옵션으로 다시 그린다
            self.pending = True
            return
        if self.seg is None:                # 아직 읽은 그림이 없거나 읽지 못했다 — 다시 그릴 것이 없다
            return
        self._start(None)

    def choose(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(title="그림 열기", filetypes=[("그림 (PNG · JPEG)", "*.png *.jpg *.jpeg"), ("모든 파일", "*.*")])
        if path:
            self.open_path(path)

    def open_path(self, path):
        """그림을 연다 (요소 찾기부터)"""
        if self.busy:
            return False
        self.path = os.path.abspath(path)
        self.seg = None
        self.text = None
        self.info = {}
        self.saved = None
        self.end_undo()
        self.hide_stamp()
        self._show(None)                                     # 새 그림을 읽는 동안 옛 그림의 값이 남아 있지 않게
        self._show_info({})
        self._show_stats({})
        self.restyle_role(self.path_label, fg="text")
        self.path_label.configure(text=shorten(self.path, 34))
        started = self._start(self.path)
        self._paint_leds()
        return started

    def _start(self, path):
        self.busy = True
        self.pending = False
        gc.disable()                        # 순환 쓰레기 치우기가 일꾼 스레드에서 돌면 tk 변수가 엉뚱한 스레드에서 지워져 Tcl 이 죽는다 — 일이 끝나면 주 스레드에서 치운다
        self._sync_buttons()
        self.face.set("busy")
        self._set_status("◐", "읽는 중… (큰 그림은 오래 걸릴 수 있습니다)" if path else "다시 그리는 중…")
        opts, _ = self.read_options()
        seg, name = self.seg, os.path.basename(self.path)
        threading.Thread(target=_work, args=(self.app, self.results, path, seg, name, opts), daemon=True).start()
        return True

    def _tick(self):
        """40ms 마다 — 일꾼의 결과를 받고, 활동 표시(LED 깜빡임 · 라임 스윕)를 돌린다"""
        try:
            self.tick += 1
            try:
                result = self.results.get_nowait()
            except queue.Empty:
                result = None
            if result is not None:
                self._finish(*result)
            if self.busy:
                self._advance_sweep()
            if self.tick % 6 == 0:
                self._paint_leds()
            self._after(POLL_MS, self._tick)
        except tk.TclError:                 # 창이 닫혔다
            pass

    def _finish(self, seg, code, line, text, shape, info):
        self.busy = False
        gc.enable()
        gc.collect()
        self.seg = seg if seg is not None else self.seg
        self.text = text
        self.info = dict(self.info, **info) if seg is not None else {}
        self._show(text)
        self._show_info(self.info)
        self._show_stats(self.info if text is not None else {})
        name = os.path.basename(self.path or "")
        if text is not None:
            self.face.set("ok")
            self._set_status("●", "OK  %s (%s)" % (name, shape))
        elif code == self.app.FAIL:
            self.seg = None
            self.pending = False
            self.face.set("error")
            self._set_status("×", line.replace("실패  ", "", 1), error=True)
        else:
            self.face.set("confirm")
            self._set_status("‼", line.replace("확인 필요  ", "", 1))
        self._sync_buttons()
        self._paint_leds()
        self._draw_sweep()
        if self.pending:
            self.options_changed()

    def _advance_sweep(self):
        width = max(1, self.sweep.winfo_width())
        self.sweep_x += self.sweep_dir * 24
        if self.sweep_x <= 0 or self.sweep_x >= width - 48:
            self.sweep_dir = -self.sweep_dir
        self._draw_sweep()

    def _draw_sweep(self):
        """라임 스윕 — 일하는 동안 오가고, 끝나면 비운다"""
        width = max(1, self.sweep.winfo_width())
        if self.busy:
            x = max(0, min(width - 48, self.sweep_x))
            self.sweep.coords(self.sweep_bar, x, 0, x + 48, 3)
        else:
            self.sweep.coords(self.sweep_bar, 0, 0, 0, 3)
        self.sweep.itemconfigure(self.sweep_bar, fill=self.theme["accent"])

    # ---------------------------------------------------------------- 내보내기 · 도장 · 되돌리기
    def save(self):
        """입력 옆에 <이름>.txt — 있으면 덮어쓰지 않고 <이름> (2).txt. 폴더에 쓸 수 없으면 저장 위치를 묻는다"""
        if not self.text or self.busy or not self.path:
            return None
        try:
            target, f = self.app.output_file(self.path)
        except OSError:
            stem = os.path.splitext(os.path.basename(self.path))[0]
            target = filedialog.asksaveasfilename(title="저장 위치", defaultextension=".txt", initialfile=stem + ".txt",
                                                  filetypes=[("글자 아트", "*.txt")], confirmoverwrite=False)
            if not target:
                return None
            try:
                f = open(target, "x", encoding="utf-8")                   # 결과 파일은 덮어쓰지 않는다 (S-04) — 고른 곳에 이미 있으면 멈춘다
            except FileExistsError:
                self._set_status("×", "이미 있는 파일은 덮어쓰지 않습니다: %s — 다른 이름을 고르세요" % target, error=True)
                return None
            except OSError as e:
                self._set_status("×", "저장하지 못했습니다 (%s)" % e.__class__.__name__, error=True)
                return None
        with f:
            f.write(self.text)
        self.saved = (target, self.text)
        self.face.set("saved")
        self._set_status("√", "저장했습니다: %s" % target)
        self.show_stamp()
        self.start_undo()
        return target

    def show_stamp(self):
        """확정 도장 — 라임 동그라미에 저장"""
        c = self.stamp
        c.delete("all")
        c.create_oval(4, 4, 36, 36, width=2, outline=self.theme["accent_text"], tags="stamp_ring")
        c.create_text(20, 20, text="저장", font=self.font, fill=self.theme["accent_text"], tags="stamp_text")
        c.pack(side="right", padx=(0, GAP // 2), before=self.save_button)
        if self.stamp_job is not None:                       # 앞 저장의 도장 시계가 새 도장을 일찍 지우지 않게
            try:
                self.root.after_cancel(self.stamp_job)
            except Exception:
                pass
            self.jobs.discard(self.stamp_job)
        self.stamp_job = self._after(STAMP_MS, self.hide_stamp)

    def hide_stamp(self):
        self.stamp_job = None
        try:
            self.stamp.delete("all")
            self.stamp.pack_forget()
        except tk.TclError:
            pass

    def start_undo(self):
        self.undo_left = UNDO_SECONDS
        self.undo_button.configure(text="되돌리기 %d" % self.undo_left, state="normal")
        self.undo_button.pack(side="right", padx=(0, GAP // 2), pady=GAP // 2, before=self.save_button)
        self._after(1000, self._undo_tick, self.saved)

    def _undo_tick(self, saved):
        if saved is not self.saved or self.undo_left <= 0:
            return
        self.undo_left -= 1
        if self.undo_left <= 0:
            self.end_undo()                  # 초읽기가 끝나면 확정
            return
        try:
            self.undo_button.configure(text="되돌리기 %d" % self.undo_left)
            self._after(1000, self._undo_tick, saved)
        except tk.TclError:
            pass

    def end_undo(self):
        self.undo_left = 0
        try:
            self.undo_button.pack_forget()
        except tk.TclError:
            pass

    def undo_save(self):
        """방금 저장한 파일을 지운다 — 우리가 만든 그 파일이고 내용이 그대로일 때만 (사용자가 고친 것은 지우지 않는다)"""
        if not self.saved or self.undo_left <= 0 or self.busy:      # 일하는 중에는 얼굴 · 상태줄을 건드리지 않는다
            return False
        path, text = self.saved
        self.saved = None
        self.end_undo()
        self.hide_stamp()
        try:
            with open(path, encoding="utf-8") as f:
                same = f.read() == text
            if not same:
                self._set_status("○", "되돌리지 않았습니다 — 저장한 뒤 내용이 바뀌었습니다: %s" % path)
                return False
            os.remove(path)
        except OSError as e:
            self._set_status("×", "되돌리지 못했습니다 (%s)" % e.__class__.__name__, error=True)
            return False
        self.face.set("ok")
        self._set_status("√", "되돌렸습니다: %s 를 지웠습니다" % os.path.basename(path))
        return True

    def copy(self):
        if not self.text or self.busy:
            return False
        self.root.clipboard_clear()
        self.root.clipboard_append(self.text)
        self.root.update_idletasks()
        self._set_status("√", "클립보드에 복사했습니다")
        return True

    # ---------------------------------------------------------------- 부팅
    def start_boot(self):
        """점 격자 → 워드마크 → 라임 스윕 (0.9 초). 아무 키나 클릭으로 건너뛴다"""
        c = tk.Canvas(self.root, bg=self.theme["body"], highlightthickness=0, bd=0)
        c.place(x=0, y=0, relwidth=1, relheight=1)
        tk.Misc.lift(c)
        c.bind("<Button-1>", lambda _e: self.skip_boot())
        self.boot_canvas = c
        self.boot_started = time.time()
        self._boot_frame()

    def _boot_frame(self):
        c = self.boot_canvas
        if c is None:
            return
        try:
            t = self.theme
            elapsed = (time.time() - self.boot_started) * 1000
            if elapsed >= BOOT_MS:
                self.skip_boot()
                return
            w, h = max(1, c.winfo_width()), max(1, c.winfo_height())
            c.delete("all")
            for y in range(GAP // 2, h, GAP):
                c.create_line(0, y, w, y, fill=t["dots"], dash=(1, GAP - 1))
            if elapsed > 250:
                shown = "ASCII–1"[:int((elapsed - 250) / 300 * 7) + 1]
                c.create_text(w // 2, h // 2 - 16, text=shown, font=self.font_big, fill=t["big"])
            if elapsed > 550:
                frac = min(1.0, (elapsed - 550) / 300)
                c.create_rectangle(w // 4, h // 2 + 8, w // 4 + int(w / 2 * frac), h // 2 + 12, width=0, fill=t["accent"])
            self._after(30, self._boot_frame)
        except tk.TclError:
            self.boot_canvas = None

    def skip_boot(self):
        """부팅 연출이 떠 있으면 걷어 낸다 → 걷어 냈는가"""
        if self.boot_canvas is None:
            return False
        c, self.boot_canvas = self.boot_canvas, None
        try:
            c.destroy()
        except tk.TclError:
            pass
        return True


def _work(app, results, path, seg, name, opts):
    """일꾼 스레드 — 창(Window)도 tk 객체도 쥐지 않는다. 창을 닫은 뒤 이 스레드가 tk 변수를 치우면 Tcl 이 죽는다"""
    info = {}
    try:
        code, line, text, shape = app.OK, "", None, ""
        if path is not None:
            t0 = time.perf_counter()
            seg, code, line = app.analyze(path)
            info["read"] = time.perf_counter() - t0
            info["bytes"] = os.path.getsize(path)
        if seg is not None:
            t0 = time.perf_counter()
            code, line, text, shape = app.make_art(seg, name, opts)
            info["draw"] = time.perf_counter() - t0
            info.update(w=seg.width, h=seg.height, dots=seg.dots(), lines=len(seg.of("hline")) + len(seg.of("vline")), kind=seg.guess_kind())
            if text is not None:
                rows = text.rsplit("\n\n", 1)[0].split("\n")
                info.update(cols=max(len(x) for x in rows), rows=len(rows))
        results.put((seg, code, line, text, shape, info))
    except Exception as e:                                    # 어떤 예외든 창에 보여 주고 끝낸다 (스레드가 조용히 죽으면 창이 영영 "읽는 중")
        results.put((None, app.FAIL, "실패  %s: %s: %s" % (name, e.__class__.__name__, e), None, "", {}))


def run(app, files=()):
    """창을 열고 닫을 때까지 돈다 → 종료 코드. 파일이 주어지면 첫 번째를 바로 연다"""
    if not available():
        sys.stderr.write("창을 열 수 없습니다: 이 파이썬에는 tkinter 가 없습니다 (%s)\n명령줄로 쓰세요: ascii-1.py help\n" % TK_ERROR)
        return app.FAIL
    try:
        win = Window(app, boot=True)
    except tk.TclError as e:                                  # 화면이 없는 곳 (원격 · 서버)
        sys.stderr.write("창을 열 수 없습니다: %s\n명령줄로 쓰세요: ascii-1.py help\n" % e)
        return app.FAIL
    hide_own_console()
    if files:
        win._after(100, lambda: win.open_path(files[0]))
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
                limit = time.time() + SELFTEST_SECONDS
                while (win.busy or not win.results.empty()) and time.time() < limit:
                    win.root.update()
                    time.sleep(0.01)
                win.root.update()
                if win.busy:
                    problems.append("%d 초 안에 끝나지 않았습니다" % SELFTEST_SECONDS)
                elif not win.text or sum(win.text.rsplit("\n\n", 1)[0].count(g) for g in "oO@") != 3:
                    problems.append("그림 결과가 기대와 다르다 (붉은 선 하나 · 점 셋)")
                elif win.stats["dots"].text() != "0003":
                    problems.append("STAT 의 DOTS 가 %s (0003 이어야 함)" % win.stats["dots"].text())
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
