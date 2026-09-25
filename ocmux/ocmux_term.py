"""
ocmux_term.py - ocmux 공용 터미널 유틸 + 디자인 시스템 (Python stdlib only)

  - Windows 콘솔 VT(ANSI) 활성화 / UTF-8 출력
  - 팔레트(네이비·라임·그레이)와 디자인 규칙 (하드웨어 계측기 화면처럼)
      1. 한 화면 = 한 모드, 핵심 값 4개를 크게
      2. 색 = 조작: ①파랑 ②초록 ③흰색 ④회색. 화면 요소의 색 = 그 값을 바꾸는 키의 색
      3. 모든 구역에 번호, `?` 를 누르면 번호표 + 범례 (매뉴얼처럼)
      4. 엔지니어링을 숨기지 않음: 지연 ms · 주기 · 이벤트 수 같은 실제 상태를 작게
      5. 즉각 반응: 누른 키는 불이 들어오고, 활동이 있으면 구역 LED 가 깜빡인다
      6. 각진 격자: 네모 모서리, 칸 사이 1칸 틈, 앞자리 0, 작은 단위
      7. 아이콘 맵(ICON) 에 있는 기호만 상태 표시에 쓴다
  - 위젯: chip / keycap / module / sect / navbar / meter / segbar / knob / seg_lines / cells / readouts / Canvas / guide
  - 한글(동아시아 wide) 폭 계산: vlen / clip / pad / wrap
  - 키 입력: Windows(msvcrt) / POSIX(termios) 공통 토큰화, 한글 자판 → 영문 키 정규화
"""
import os
import re
import shutil
import sys
import time
import unicodedata

# ---------------------------------------------------------------- console
def _enable_vt():
    """Windows 콘솔 VT(ANSI) 처리 켜기. SetConsoleMode 가 안 되면 예전 os.system('') 트릭으로."""
    try:
        import ctypes
        k = ctypes.windll.kernel32
        k.GetStdHandle.restype = ctypes.c_void_p
        h = ctypes.c_void_p(k.GetStdHandle(-11))  # STD_OUTPUT_HANDLE
        m = ctypes.c_uint32()
        if k.GetConsoleMode(h, ctypes.byref(m)):
            k.SetConsoleMode(h, m.value | 0x0004)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
            return
    except Exception:
        pass
    os.system("")


if os.name == "nt":
    _enable_vt()
    try:
        # 짝 없는 서로게이트(이모지 반쪽) 같은 게 섞여도 출력이 죽지 않게 errors=replace
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

RST, DIM, B, REV, NOREV = "\x1b[0m", "\x1b[2m", "\x1b[1m", "\x1b[7m", "\x1b[27m"
HOME, CLR_EOL, CLR_EOS = "\x1b[H", "\x1b[K", "\x1b[J"
HIDE, SHOW = "\x1b[?25l", "\x1b[?25h"


def _tc(h):
    return "\x1b[38;2;%d;%d;%dm" % (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16))


def rgb(hexcolor):
    h = (hexcolor or "#888888").lstrip("#")
    return "\x1b[38;2;%d;%d;%dm" % (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def bg(hexcolor):
    h = (hexcolor or "#000000").lstrip("#")
    return "\x1b[48;2;%d;%d;%dm" % (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


# ---------------------------------------------------------------- palette: NAVY / LIME / GRAY
# 세 가지 기준색(네이비 #002341 · 라임 #6ABA23 · 그레이 #A5AAAE)과 같은 색상(hue)의 밝기 단계만 쓴다.
#   navy  : 블록/패널 바탕, 선택 막대, 트랙      lime : 단 하나의 강조색 (켜짐·진행·값·커서)
#   gray  : 본문 글자, 라벨, 선                   black: 화면 바탕 (Windows Terminal 스킴과 같음)
P3 = {
    "navy": "#002341", "navy1": "#08365E", "navy2": "#1F507A", "navy3": "#3F77A6", "navy4": "#75A1C7", "navy5": "#B8CEE0",
    "lime": "#6ABA23", "lime0": "#2C4912", "lime1": "#45741B", "lime3": "#95D85A", "lime4": "#C0E79D",
    "gray": "#A5AAAE", "gray0": "#35383B", "gray1": "#5C6166", "gray2": "#81888D", "gray4": "#D4D6D8",
    "white": "#F2F2F3", "black": "#000000",
}

# 모니터(status/overview/logs)의 의미색
#   GRN: ok/online   YEL: busy(진행)   RED: 오류/오프라인(가장 밝은 흰색 + 칩으로 강조)
#   BLU: 도구         MAG: 서브에이전트/재시도   CYN: agent
THEME = {"GRN": P3["lime"], "YEL": P3["lime3"], "RED": P3["white"], "BLU": P3["navy4"], "MAG": P3["navy3"], "CYN": P3["navy5"]}
RED, GRN, YEL, BLU, MAG, CYN = (_tc(THEME[k]) for k in ("RED", "GRN", "YEL", "BLU", "MAG", "CYN"))
# 인스턴스(탭) 태그 색: 3색 계열 안에서 서로 구분되게
PALETTE = ["#3F77A6", "#A5AAAE", "#75A1C7", "#6ABA23", "#B8CEE0", "#81888D", "#95D85A", "#45741B"]  # 네이비가 주색 · 라임은 강조라 1번 자리에서 뺌
# 예전(파랑/분홍) 탭 색 → 새 팔레트 (instances.json 에 남아 있는 옛 색을 읽을 때 바꿔 준다)
LEGACY_COLORS = dict(zip(["#3B82F6", "#EC4899", "#6366F1", "#F472B6", "#0EA5E9", "#DB2777", "#818CF8", "#D946EF"], PALETTE))


def fix_color(c):
    """옛 팔레트 색이면 새 색으로, 아니면 그대로"""
    return LEGACY_COLORS.get((c or "").upper(), c)

# 게임/UI용 이름 있는 색 (예전 이름은 새 팔레트로 연결해 둔다)
C = {
    "pink": P3["lime"], "hot": P3["lime"], "rose": P3["white"], "orchid": P3["navy4"], "lpink": P3["gray4"],
    "blue": P3["navy3"], "sky": P3["lime3"], "lblue": P3["navy4"], "indigo": P3["navy2"], "deep": P3["navy1"],
    "white": P3["gray4"], "gray": P3["gray1"], "dark": P3["gray0"], "night": P3["navy"], "black": P3["black"],
    **P3,
}


# ---------------------------------------------------------------- 위젯 (격자 · 번호 모듈 · 키캡 · 페이더 · 세그먼트 숫자)
def chip(text, fgc="black", bgc="lime", bold=True):
    """색 블록 위의 짧은 라벨: ' BUSY ' 같은 상태 표시"""
    return f"{bg(C.get(bgc, bgc))}{rgb(C.get(fgc, fgc))}{B if bold else ''} {text} {RST}"


def keycap(key, label="", on=False, color=None):
    """하드웨어 버튼: 기본은 어두운 캡 + 밝은 글자. color(인코더 색)를 주면 그 색 캡,
    on 이면 방금 눌린 키처럼 라임으로 켜진다. 옆에 작은 라벨"""
    if on:
        cap = f"{bg(P3['lime'])}{rgb(P3['black'])}{B}{key}{RST}"
    elif color:
        cap = f"{bg(color)}{rgb(P3['black'])}{B}{key}{RST}"
    else:
        cap = f"{bg(P3['gray0'])}{rgb(P3['gray4'])}{B}{key}{RST}"
    return cap + (f" {rgb(P3['gray'])}{label}{RST}" if label else "")


def keys_row(pairs):
    """[('F','밥'), ('C','청소')] → 키캡 줄"""
    return "  ".join(keycap(k, v) for k, v in pairs)


def module(num, title, on=True, led=None):
    """번호가 붙은 모듈 제목: 01 SESSIONS (●)
    led: None=표시 없음, True=활동 중(라임), False=조용함(어두운 점)"""
    n = f"{num:02d}" if isinstance(num, int) else str(num)
    s = (f"{bg(P3['navy2'] if on else P3['navy'])}{rgb(P3['white'] if on else P3['gray1'])}{B}{n}{RST}"
         f" {rgb(P3['gray4'])}{B}{title}{RST}")
    if led is not None:
        s += f" {rgb(P3['lime'] if led else P3['gray0'])}●{RST}"
    return s


def rule(width, label="", color=None):
    """얇은 구분선. 라벨이 있으면 선 가운데가 아니라 왼쪽에 붙인다"""
    col = rgb(color or P3["navy2"])
    if not label:
        return f"{col}{'─' * max(0, width)}{RST}"
    lab = f" {label} "
    return f"{col}──{RST}{rgb(P3['gray1'])}{lab}{RST}{col}{'─' * max(0, width - 2 - vlen(lab))}{RST}"


def sect(num, title, width, right="", led=None):
    """── 01 TITLE ● ─────────── right  (번호 붙은 구획 제목줄, led=활동 표시)"""
    col = rgb(P3["navy2"])
    head = f"{col}──{RST} {module(num, title, led=led)} "
    if right:
        fill = max(1, width - vlen(head) - vlen(right) - 1)
        return head + f"{col}{'─' * fill}{RST} " + right
    return head + f"{col}{'─' * max(0, width - vlen(head))}{RST}"


def navbar(left, right, width, color=None):
    """전체 폭 네이비 바 (맨 윗줄 표시줄). 안쪽 RST 뒤에도 바탕색을 다시 깐다"""
    b = bg(color or P3["navy"])
    if right and vlen(left) + vlen(right) + 2 > width:
        right = ""
    room = width - (vlen(right) + 1 if right else 0)
    left = clip(left, room, False)
    gap = max(0, width - vlen(left) - vlen(right))
    return b + left.replace(RST, RST + b) + b + " " * gap + right.replace(RST, RST + b) + RST


def on_bg(text, width, color):
    """글자를 색 블록 위에 올리고 폭을 맞춘다 (안쪽 RST 뒤에도 바탕색 유지)"""
    b = bg(color)
    t = clip(text, width, False)
    return b + t.replace(RST, RST + b) + b + " " * max(0, width - vlen(t)) + RST


# ---------------------------------------------------------------- 색 = 조작 (4색 인코더) · 아이콘 맵
# 화면에서 ①파랑으로 칠한 값은 ①파랑 키가 바꾼다. 같은 화면 안에서 네 가지 값에만 쓴다.
ENC = [P3["navy4"], P3["lime"], P3["white"], P3["gray"]]
ENC_NAME = ["파랑", "초록", "흰색", "회색"]


def enc(i):
    return rgb(ENC[i % 4])


def enc_dot(i):
    return f"{rgb(ENC[i % 4])}●{RST}"


# 상태 표시 기호는 이 표에 있는 것만 쓴다 (README 의 아이콘 맵과 같다)
ICON = {
    "online": "●", "offline": "○", "busy": "◐", "run": "▶", "done": "√", "error": "×", "wait": "‼",
    "todo": "⊠", "compact": "⇣", "call": "!", "new": "+", "agent": "›", "step": "▮", "boss": "◆",
}
ICON_DESC = [
    ("●", "켜짐 · 온라인 · 활동"), ("○", "꺼짐 · 오프라인"), ("◐", "진행 중 (돌아감)"), ("▶", "도구 시작 · 선택"),
    ("√", "끝남"), ("×", "오류 · 실패"), ("‼", "사용자 응답 대기 (허락/질문)"), ("⊠", "할 일"),
    ("⇣", "컨텍스트 압축"), ("!", "펫 호출"), ("▮", "LED 칸 한 개 = 한 단계"), ("◆", "보스 층"),
]


def cells(items, width, gap=1, color=None):
    """스펙 표 한 줄: [(라벨, 값ANSI, 인코더번호|None)] 을 같은 폭 칸으로. 칸 사이는 검은 1칸 틈"""
    n = max(1, len(items))
    w = max(6, (width - gap * (n - 1)) // n)
    out = []
    for it in items:
        lab, val = it[0], it[1]
        e = it[2] if len(it) > 2 else None
        dot = f"{enc_dot(e)} " if e is not None else ""
        out.append(on_bg(f" {dot}{rgb(P3['gray1'])}{lab}{RST} {val}", w, color or P3["navy1"]))
    return (" " * gap).join(out)


def readouts(items, width, ghost=None):
    """큰 숫자 칸 (세그먼트 3줄 + 라벨 1줄). items: [(라벨, 숫자글자, 인코더번호)].
    칸이 좁으면 None → 호출한 쪽이 cells() 한 줄로 대신 그린다"""
    n = max(1, len(items))
    w = (width - (n - 1)) // n
    if any(seg_width(v) + 2 > w for _, v, _ in items):
        return None
    rows = ["", "", "", ""]
    for k, (lab, val, e) in enumerate(items):
        seg = seg_lines(val, ENC[e % 4], ghost=ghost or P3["navy1"])
        sw = seg_width(val)
        for i in range(3):
            rows[i] += " " + seg[i] + " " * max(0, w - sw - 1)
        rows[3] += pad(f" {enc_dot(e)} {rgb(P3['gray1'])}{lab}{RST}", w)
        if k < n - 1:
            for i in range(4):
                rows[i] += " "
    return rows


def page_dots(i, n):
    """페이지 표시 ○●○○"""
    return "".join((rgb(P3["lime"]) + "●") if k == i else (rgb(P3["navy2"]) + "●") for k in range(n)) + RST


def sysline(parts):
    """정직한 엔지니어링: 실제 시스템 상태를 작게. parts = [(라벨, 값)]"""
    return f" {rgb(P3['gray0'])}·{RST} ".join(f"{rgb(P3['gray1'])}{k}{RST} {rgb(P3['gray2'])}{v}{RST}" for k, v in parts)


def meter(v, mx, w, on=None, off=None, knob=True):
    """페이더: ━━━━━●──── (채움은 라임, 트랙은 네이비, 끝에 손잡이)"""
    w = max(2, w)
    mx = mx or 1
    fill = int(round(max(0.0, min(1.0, float(v) / mx)) * w))
    on, off = on or P3["lime"], off or P3["navy2"]
    if not knob:
        return f"{rgb(on)}{'━' * fill}{RST}{rgb(off)}{'━' * (w - fill)}{RST}"
    if fill <= 0:
        return f"{rgb(P3['gray1'])}○{RST}{rgb(off)}{'─' * (w - 1)}{RST}"
    return f"{rgb(on)}{'━' * (fill - 1)}●{RST}{rgb(off)}{'─' * (w - fill)}{RST}"


def segbar(v, mx, n, on=None, off=None):
    """LED 막대: ▮▮▮▮▯▯ (칸 단위)"""
    n = max(1, n)
    k = int(round(max(0.0, min(1.0, float(v) / (mx or 1))) * n))
    return f"{rgb(on or P3['lime'])}{'▮' * k}{RST}{rgb(off or P3['navy2'])}{'▮' * (n - k)}{RST}"


def knob(v, mx=100):
    """노브 위치 한 글자: ○ ◔ ◑ ◕ ●"""
    r = max(0.0, min(1.0, float(v) / (mx or 1)))
    return "○◔◑◕●"[min(4, int(r * 4 + 0.5))]


def led(on=True, color=None):
    return f"{rgb(color or (P3['lime'] if on else P3['gray1']))}{'●' if on else '○'}{RST}"


def spinner(t, speed=4.0, frames="◐◓◑◒"):
    """테이프 릴처럼 도는 원"""
    return frames[int(t * speed) % len(frames)]


# 3줄짜리 세그먼트 숫자 (얇은 선으로 그린 7-세그먼트 느낌). 단위 글자는 밑줄에 작게.
SEG = {
    "0": ["┌─┐", "│ │", "└─┘"], "1": ["  ╷", "  │", "  ╵"], "2": ["╶─┐", "┌─┘", "└─╴"], "3": ["╶─┐", " ─┤", "╶─┘"],
    "4": ["╷ ╷", "└─┤", "  ╵"], "5": ["┌─╴", "└─┐", "╶─┘"], "6": ["┌─╴", "├─┐", "└─┘"], "7": ["╶─┐", "  │", "  ╵"],
    "8": ["┌─┐", "├─┤", "└─┘"], "9": ["┌─┐", "└─┤", "╶─┘"], "-": ["   ", "╶─╴", "   "], " ": [" ", " ", " "],
    ".": [" ", " ", "."], ",": [" ", " ", ","], ":": [" ", "·", "·"], "/": ["  ╱", " ╱ ", "╱  "],
    # 워드마크용 글자 (TOKEN QUEST 등)
    "T": ["╶┬╴", " │ ", " ╵ "], "O": ["┌─┐", "│ │", "└─┘"], "K": ["╷ ╷", "├┬┘", "╵└╴"], "E": ["┌─╴", "├─ ", "└─╴"],
    "N": ["┌┐╷", "│││", "╵└┘"], "Q": ["┌─┐", "│ │", "└─┼"], "U": ["╷ ╷", "│ │", "└─┘"], "S": ["┌─╴", "└─┐", "╶─┘"],
    "L": ["╷  ", "│  ", "└─╴"], "V": ["╷ ╷", "│ │", "└┬┘"], "P": ["┌─┐", "├─┘", "╵  "], "R": ["┌─┐", "├┬┘", "╵└╴"],
    "A": ["┌─┐", "├─┤", "╵ ╵"], "I": ["╶┬╴", " │ ", "╶┴╴"], "D": ["┌─┐", "│ │", "└─┘"], "G": ["┌─╴", "│ ┐", "└─┘"],
    "M": ["┌┬┐", "│││", "╵╵╵"], "W": ["╷ ╷", "│││", "└┴┘"], "X": ["╷ ╷", " ╳ ", "╵ ╵"], "Y": ["╷ ╷", "└┬┘", " ╵ "],
    "C": ["┌─╴", "│  ", "└─╴"], "H": ["╷ ╷", "├─┤", "╵ ╵"], "F": ["┌─╴", "├─ ", "╵  "], "B": ["┌─┐", "├─┤", "└─┘"],
    "+": ["   ", "╶┼╴", "   "],
    "_": ["   ", "   ", "   "],     # 꺼진 자리 (유령 세그먼트만 보인다)
}
GHOST = SEG["8"]


def _seg_glyph(ch):
    """큰 글자로 그릴 수 있으면 3줄 글리프, 아니면 None (소문자·한글·기호는 밑줄에 작게)"""
    if ch.islower():
        return None
    return SEG.get(ch)


def seg_lines(text, color=None, unit_color=None, gap=1, ghost=None):
    """문자열 → 세그먼트 3줄 (ANSI). 숫자·대문자는 크게, 소문자 단위(k/min 등)는 밑줄에 작게.
    ghost 색을 주면 숫자 자리 뒤에 꺼진 세그먼트('8')를 어둡게 깐다 (LCD 느낌). '_' 는 빈 숫자 자리."""
    col = rgb(color or P3["lime"])
    ucol = rgb(unit_color or P3["gray"])
    gcol = rgb(ghost) if ghost else ""
    rows = ["", "", ""]
    for ch in str(text):
        glyph = _seg_glyph(ch)
        if glyph and ghost and (ch.isdigit() or ch in "-_"):
            for i in range(3):
                cells = [f"{col}{a}" if a != " " else (f"{gcol}{b}" if b != " " else " ")
                         for a, b in zip(glyph[i], GHOST[i])]
                rows[i] += "".join(cells) + RST + " " * gap
        elif glyph:
            for i in range(3):
                rows[i] += f"{col}{glyph[i]}{RST}" + " " * gap
        else:
            w = cw(ch)
            rows[0] += " " * w
            rows[1] += " " * w
            rows[2] += f"{ucol}{ch}{RST}"
    return rows


def seg_width(text, gap=1):
    return sum((len(_seg_glyph(ch)[0]) + gap) if _seg_glyph(ch) else cw(ch) for ch in str(text))


def term_size():
    s = shutil.get_terminal_size((110, 32))
    return s.columns, s.lines


# ---------------------------------------------------------------- width
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def cw(ch):
    o = ord(ch)
    if o < 0x1100:
        return 1
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def strip_ansi(s):
    return _ANSI_RE.sub("", s)


def vlen(s):
    out, esc = 0, False
    for ch in s:
        if ch == "\x1b":
            esc = True
            continue
        if esc:
            if ch.isalpha():
                esc = False
            continue
        out += cw(ch)
    return out


def clip(s, n, ellipsis=True):
    out, w, esc = [], 0, False
    for ch in s:
        if ch == "\x1b":
            esc = True
        if esc:
            out.append(ch)
            if ch.isalpha():
                esc = False
            continue
        c = cw(ch)
        if w + c > n:
            if ellipsis and n - w >= 1:
                out.append("…")
            break
        out.append(ch)
        w += c
    return "".join(out) + RST


def pad(s, n):
    s = clip(s, n)
    return s + " " * max(0, n - vlen(s))


def center(s, n):
    s = clip(s, n)
    gap = max(0, n - vlen(s))
    return " " * (gap // 2) + s + " " * (gap - gap // 2)


def wrap(text, width):
    """ANSI 색을 유지하며 표시폭 기준 줄바꿈. 반환: 줄 리스트 (각 줄은 색 상태를 이어받음)"""
    width = max(1, width)
    lines, cur, w, state = [], [], 0, ""
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "\x1b":
            m = _ANSI_RE.match(text, i)
            if m:
                seq = m.group(0)
                cur.append(seq)
                state = "" if seq in ("\x1b[0m", "\x1b[m") else state + seq
                i = m.end()
                continue
        if ch == "\n":
            lines.append("".join(cur) + RST)
            cur, w = [state], 0
            i += 1
            continue
        c = cw(ch)
        if w + c > width:
            lines.append("".join(cur) + RST)
            cur, w = [state], 0
            if ch == " ":
                i += 1
                continue
        cur.append(ch)
        w += c
        i += 1
    lines.append("".join(cur) + RST)
    return lines


# ---------------------------------------------------------------- 캔버스 (겹쳐 그리기) · 가이드 · 부팅
_SGR = re.compile(r"\x1b\[[0-9;]*m")


class Canvas:
    """wide(한글) 문자를 안전하게 겹쳐 그릴 수 있는 셀 버퍼"""

    def __init__(self, w, h):
        self.w, self.h = max(1, w), max(1, h)
        self.ch = [[" "] * self.w for _ in range(self.h)]
        self.st = [[""] * self.w for _ in range(self.h)]

    def _clear(self, x, y):
        row = self.ch[y]
        c = row[x]
        if c is None:
            if x > 0:
                row[x - 1] = " "
        elif x + 1 < self.w and row[x + 1] is None:
            row[x + 1] = " "
        row[x] = " "

    def text(self, x, y, s, style=""):
        if not (0 <= y < self.h):
            return x
        for c in s:
            if c < " " or "\x7f" <= c < "\xa0":      # 제어 문자(C0/DEL/C1)는 터미널로 내보내지 않는다
                continue
            w = cw(c)
            if x >= self.w:
                break
            if x < 0:
                x += w
                continue
            if w == 2 and x + 1 >= self.w:
                break
            self._clear(x, y)
            if w == 2:
                self._clear(x + 1, y)
            self.ch[y][x] = c
            self.st[y][x] = style
            if w == 2:
                self.ch[y][x + 1] = None
                self.st[y][x + 1] = style
            x += w
        return x

    def ansi(self, x, y, s, base=""):
        cur, pos = base, 0
        for m in _SGR.finditer(s):
            if m.start() > pos:
                x = self.text(x, y, s[pos:m.start()], cur)
            seq = m.group(0)
            cur = base if seq in ("\x1b[0m", "\x1b[m") else cur + seq
            pos = m.end()
        if pos < len(s):
            x = self.text(x, y, s[pos:], cur)
        return x

    def ansi_clip(self, x, y, s, width, base=""):
        return self.ansi(x, y, clip(s, width), base)

    def fill(self, x, y, w, h, c=" ", style=""):
        for yy in range(max(0, y), min(self.h, y + h)):
            self.text(x, yy, c * max(0, w), style)

    def panel(self, x, y, w, h, color="navy"):
        """색 블록 패널. 위에 그리는 글자는 base=bg(...) 로 바탕을 유지한다"""
        x0, x1 = max(0, x), min(self.w, x + w)
        self.fill(x0, y, x1 - x0, h, " ", bg(P3.get(color, color)))

    def hline(self, x, y, w, style, ch="─"):
        self.text(x, y, ch * max(0, w), style)

    def box(self, x, y, w, h, style, title=None, tstyle=None):
        if w < 2 or h < 2:
            return
        self.text(x, y, "┌" + "─" * (w - 2) + "┐", style)
        for yy in range(y + 1, y + h - 1):
            self.text(x, yy, "│", style)
            self.text(x + w - 1, yy, "│", style)
        self.text(x, y + h - 1, "└" + "─" * (w - 2) + "┘", style)
        if title:
            self.ansi(x + 2, y, clip(f" {title} ", w - 4, False), tstyle or style)

    def lines(self):
        out = []
        for y in range(self.h):
            parts, prev = [], None
            for x in range(self.w):
                c = self.ch[y][x]
                if c is None:
                    continue
                st = self.st[y][x]
                if st != prev:
                    parts.append(RST + st)
                    prev = st
                parts.append(c)
            parts.append(RST)
            out.append("".join(parts))
        return out


def canvas_from_lines(lines, W, H):
    """줄 단위로 그린 화면(모니터 칸)을 캔버스로 옮긴다 (위에 가이드를 겹쳐 그리려고)"""
    cv = Canvas(W, H)
    for y, ln in enumerate(lines[:H]):
        cv.ansi(0, y, clip(ln, W, False))
    return cv


def title_end(num, title, boxed=False, led=False):
    """번호 모듈 제목 뒤 가이드 번호표 자리 (제목과 한 칸 띄움).
    sect(): '── 01 TITLE ● N' / 상자 모듈: '┌ 01 TITLE N'"""
    n = f"{num:02d}" if isinstance(num, int) else str(num)
    return (4 if boxed else 5) + len(n) + vlen(title) + (2 if led else 0)      # 제목과 번호표 사이 한 칸


def guide_draw(cv, W, H, items, sel=0, strip_y=None, title="GUIDE"):
    """매뉴얼식 안내: 화면 위 1칸 번호표 + 아래 두 줄 범례 띠.
    items = [(x, y, 이름, 설명)]  — 번호 1~9 순서. 선택된 번호는 라임으로 깜빡이고 설명이 띠에 뜬다.
    범례 띠는 strip_y, strip_y+1 두 줄을 덮는다 (기본: 맨 아래 두 줄)."""
    sy = H - 2 if strip_y is None else strip_y
    items = [it for it in items if 0 <= it[1] < H and it[1] not in (sy, sy + 1)][:9]
    if not items:
        return
    sel = max(0, min(sel, len(items) - 1))
    blink = int(time.time() * 3) % 2
    white, lime, black = bg(P3["white"]), bg(P3["lime"]), rgb(P3["black"])
    for i, (x, y, name, desc) in enumerate(items):
        st = (lime if (i != sel or blink) else bg(P3["navy2"])) if i == sel else white
        cv.ansi(max(0, min(W - 1, x)), y, f"{st}{black}{B}{i + 1}{RST}")
    b = bg(P3["navy"])
    cv.panel(0, sy, W, 2, "navy")
    head = f" {white}{black}{B} {title} {RST} "
    parts = []
    for i, (x, y, name, desc) in enumerate(items):
        if i == sel:
            parts.append(f"{lime}{black}{B} {i + 1} {name} {RST}")
        else:
            parts.append(f"{rgb(P3['gray4'])}{B}{i + 1}{RST} {rgb(P3['gray'])}{name}{RST}")
    cv.ansi(0, sy, clip(head + "  ".join(parts), W), b)
    keys = f"{rgb(P3['gray1'])}1-{len(items)} · ←→ 고르기 · 다른 키 닫기{RST} "
    name, desc = items[sel][2], items[sel][3]
    line = f" {rgb(P3['lime'])}{B}{sel + 1} {name}{RST} {rgb(P3['gray4'])}{desc}{RST}"
    if vlen(line) + vlen(keys) + 2 <= W:
        cv.ansi(W - vlen(keys), sy + 1, keys, b)
        cv.ansi(0, sy + 1, clip(line, W - vlen(keys) - 1), b)
    else:
        cv.ansi(0, sy + 1, clip(line, W), b)


def boot_draw(cv, W, H, t, word, sub="", total=1.6, tag="BOOT"):
    """켜질 때 연출: 점 격자가 깔리고 → 세그먼트 워드마크 → 라임 줄이 지나간다 (total 초)"""
    k = total / 1.6
    cols = int(W * min(1.0, t / (0.45 * k)))
    for yy in range(1, H - 1, 2):
        cv.text(1, yy, " ".join("·" for _ in range(max(0, cols - 2) // 2)), rgb(P3["navy2"]))
    cy = max(1, H // 2 - 3)
    if t > 0.35 * k:
        if seg_width(word) <= W - 2:
            sx = (W - seg_width(word)) // 2
            for i, ln in enumerate(seg_lines(word, P3["lime"] if t > 0.6 * k else P3["navy3"])):
                cv.fill(sx - 1, cy + i, seg_width(word) + 2, 1)
                cv.ansi(sx, cy + i, ln)
        else:
            cv.fill((W - len(word) - 2) // 2, cy + 1, len(word) + 2, 1)
            cv.ansi((W - len(word)) // 2, cy + 1, f"{rgb(P3['lime'])}{B}{word}{RST}")
    if t > 0.7 * k:
        n = int(min(1.0, (t - 0.7 * k) / (0.5 * k)) * (W - 4))
        cv.fill(2, cy + 4, W - 4, 1)
        cv.text(2, cy + 4, "━" * n, rgb(P3["lime"]))
        if sub and t > 0.9 * k:
            cv.fill((W - vlen(sub)) // 2 - 1, cy + 5, vlen(sub) + 2, 1)
            cv.ansi(max(0, (W - vlen(sub)) // 2), cy + 5, f"{rgb(P3['gray'])}{sub}{RST}")
    blink = int(t * 6) % 2
    cv.ansi(1, 0, f"{rgb(P3['lime'] if blink else P3['navy2'])}●{RST} {rgb(P3['gray1'])}{tag}{RST}")
    pct = f"{min(100, int(t / total * 100)):3d}%"
    cv.ansi(W - len(pct) - 1, 0, f"{rgb(P3['gray1'])}{pct}{RST}")


# ---------------------------------------------------------------- keys
# 2벌식 한글 자판 → 영문 키 (한/영 전환을 깜빡해도 단축키가 먹도록)
HANGUL_TO_QWERTY = {
    "ㅂ": "q", "ㅈ": "w", "ㄷ": "e", "ㄱ": "r", "ㅅ": "t", "ㅛ": "y", "ㅕ": "u", "ㅑ": "i", "ㅐ": "o", "ㅔ": "p",
    "ㅁ": "a", "ㄴ": "s", "ㅇ": "d", "ㄹ": "f", "ㅎ": "g", "ㅗ": "h", "ㅓ": "j", "ㅏ": "k", "ㅣ": "l",
    "ㅋ": "z", "ㅌ": "x", "ㅊ": "c", "ㅍ": "v", "ㅠ": "b", "ㅜ": "n", "ㅡ": "m",
    "ㅃ": "q", "ㅉ": "w", "ㄸ": "e", "ㄲ": "r", "ㅆ": "t", "ㅒ": "o", "ㅖ": "p",
}


_CHOSEONG = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"


def is_hangul(k):
    """한글 자모/음절 한 글자인가 (한글 입력 모드로 단축키를 누른 경우 안내용)"""
    return len(k) == 1 and ("가" <= k <= "힣" or "ㄱ" <= k <= "ㆎ")


def norm_key(k):
    """단축키 판정용: 한글 자모 → 영문 소문자, 영문 → 소문자. 특수키 토큰은 그대로.
    한글 입력기는 자음+모음을 한 음절로 합쳐 보내기도 하므로('ㄹ'+'ㅓ' → '러') 음절은 첫소리로 판정한다."""
    if len(k) != 1:
        return k
    o = ord(k) - 0xAC00
    if 0 <= o < 11172:
        k = _CHOSEONG[o // 588]
    return HANGUL_TO_QWERTY.get(k, k.lower())


_WIN_EXT = {"H": "UP", "P": "DOWN", "K": "LEFT", "M": "RIGHT", "G": "HOME", "O": "END", "S": "DEL",
            "I": "PGUP", "Q": "PGDN", "\x0f": "BTAB", ";": "F1", "<": "F2", "=": "F3", ">": "F4", "?": "F5",
            "R": "PASTE"}   # Insert 키 = 클립보드 붙여넣기 (Windows Terminal 이 Ctrl+V 를 가로채도 동작)
_CTRL = {"\r": "ENTER", "\x08": "BS", "\x7f": "BS", "\t": "TAB", "\x1b": "ESC", "\x13": "SEND", "\x10": "PUT",
         "\x16": "PASTE", "\x0c": "CLEAR", "\x12": "RESTORE"}


def _shift_down():
    try:
        import ctypes
        return bool(ctypes.windll.user32.GetAsyncKeyState(0x10) & 0x8000)  # VK_SHIFT
    except Exception:
        return False


def read_keys_windows():
    """msvcrt 입력 → 토큰 리스트 (붙여넣기 등 몰려 들어온 입력은 한 번에)"""
    import msvcrt
    toks = []
    while True:
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            # 확장 키(화살표 등)는 두 번에 나눠 온다. 두 번째 글자는 CRT 내부 버퍼에 있어서
            # kbhit() 로는 안 보일 수 있으니 무조건 한 번 더 읽는다.
            code = msvcrt.getwch()
            tok = _WIN_EXT.get(code, "")
            if tok:
                toks.append(tok)
        elif "\ud800" <= ch <= "\udbff":
            # 이모지 등 BMP 밖 문자는 서로게이트 두 개로 나뉘어 온다 → 하나로 합치기
            lo = msvcrt.getwch()
            toks.append((ch + lo).encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace"))
        elif "\udc00" <= ch <= "\udfff":
            toks.append("�")
        elif ch == "\x03":
            raise KeyboardInterrupt
        elif ch == "\t":
            toks.append("BTAB" if _shift_down() else "TAB")
        elif ch in _CTRL:
            toks.append(_CTRL[ch])
        elif ch >= " ":
            toks.append(ch)
        if not msvcrt.kbhit():
            return toks


_POSIX_SEQ = [
    ("\x1b[200~", ""), ("\x1b[201~", ""),
    ("\x1b[A", "UP"), ("\x1b[B", "DOWN"), ("\x1b[D", "LEFT"), ("\x1b[C", "RIGHT"),
    ("\x1bOA", "UP"), ("\x1bOB", "DOWN"), ("\x1bOD", "LEFT"), ("\x1bOC", "RIGHT"),
    ("\x1b[H", "HOME"), ("\x1b[F", "END"), ("\x1b[1~", "HOME"), ("\x1b[4~", "END"),
    ("\x1b[3~", "DEL"), ("\x1b[5~", "PGUP"), ("\x1b[6~", "PGDN"), ("\x1b[Z", "BTAB"),
    ("\x1bOP", "F1"), ("\x1bOQ", "F2"), ("\x1bOR", "F3"), ("\x1bOS", "F4"),
]


def read_keys_posix(fd):
    import select
    data = os.read(fd, 65536).decode("utf-8", "replace")
    while select.select([fd], [], [], 0.01)[0]:
        chunk = os.read(fd, 65536)
        if not chunk:
            break
        data += chunk.decode("utf-8", "replace")
    toks, i = [], 0
    while i < len(data):
        for s, t in _POSIX_SEQ:
            if data.startswith(s, i):
                if t:
                    toks.append(t)
                i += len(s)
                break
        else:
            ch = data[i]
            if ch == "\x03":
                raise KeyboardInterrupt
            if ch == "\n":
                toks.append("ENTER")
            elif ch in _CTRL:
                toks.append(_CTRL[ch])
            elif ch >= " ":
                toks.append(ch)
            i += 1
    return toks


def poll_keys(timeout, fd=None):
    """timeout 초 동안 기다리며 들어온 키 토큰 반환 (없으면 [])"""
    if os.name == "nt":
        import msvcrt
        end = time.time() + timeout
        while True:
            if msvcrt.kbhit():
                return read_keys_windows()
            if time.time() >= end:
                return []
            time.sleep(0.015)
    import select
    if select.select([fd], [], [], timeout)[0]:
        return read_keys_posix(fd)
    return []


class RawInput:
    """with RawInput() as fd: ...  (POSIX 에서만 raw 모드, Windows 는 no-op)"""

    def __enter__(self):
        self.fd, self.old = None, None
        if os.name != "nt":
            import termios
            import tty
            self.fd = sys.stdin.fileno()
            self.old = termios.tcgetattr(self.fd)
            tty.setraw(self.fd)
        return self.fd

    def __exit__(self, *exc):
        if self.old is not None:
            import termios
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old)
        return False
