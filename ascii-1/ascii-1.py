#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ascii-1 - PNG · JPEG 를 끌어다 놓으면 ASCII 아트로 바꿔 주는 명령형 도구 (표준 라이브러리만 · Python 3.8+)

  ascii-1.py                               작은 창을 연다 (그림을 골라 보고 저장 · 복사) — exe 를 두 번 눌러도 같다
  ascii-1.py <그림.png> [<그림.png> ...]   입력 옆에 <이름>.txt 를 만든다 (있으면 덮어쓰지 않고 <이름> (2).txt)
  ascii-1.py version | help | check | gui [<그림.png>]

종료 코드: 0 OK · 1 점검 실패 · 2 사용법 오류 · 3 사람 확인 필요 (RULES.md › S-03)
출력의 마지막 줄은 결과: OK · 결과: 확인 필요 · 결과: 점검 실패 중 하나 (에이전트가 이 줄로 판단한다)
방법과 한계는 docs/plans/ascii-1-design.md · 사용법은 docs/MANUAL.md
"""
import os
import struct
import sys
import zlib
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ascii1_gui as gui          # noqa: E402
import ascii1_png as png          # noqa: E402
import ascii1_render as render    # noqa: E402
import ascii1_seg as seg_mod      # noqa: E402

NAME = "Ascii-1"
APP = "ascii-1"
VERSION = "0.2.0"

OK, FAIL, USAGE, CONFIRM = 0, 1, 2, 3
RESULT = {OK: "결과: OK", CONFIRM: "결과: 확인 필요", FAIL: "결과: 점검 실패"}
KINDS = ("auto", "chart", "wafer")
MAX_COLLISIONS = 999               # <이름> (2).txt … (999).txt 까지 비어 있는 이름을 찾는다

HELP = """Ascii–1 — PNG · JPEG 를 ASCII 아트로

  ascii-1.py                                작은 창을 엽니다. 그림을 골라 보고, 열 수 · 종류를 바꾸고, 저장하거나 복사합니다
  ascii-1.py <그림.png> [<그림.png> ...]    그림 옆에 <이름>.txt 를 만듭니다. 이미 있으면 덮어쓰지 않고 <이름> (2).txt
  ascii-1.py version                        버전
  ascii-1.py check                          자가 점검 (마지막 줄 결과: …)
  ascii-1.py gui [<그림.png>]               창을 엽니다 (그림을 바로 열 수도 있음). gui --selftest 는 창을 열었다 닫는 점검
  ascii-1.py help                           이 도움말

옵션
  --width N       열 수 (%d–%d, 기본 %d). 그려질 내용의 폭에 걸리고, 클수록 촘촘합니다
  --kind K        auto(기본) · chart · wafer — 그림이 그 종류가 아니면 만들지 않고 확인을 요청합니다
  --box           가로 · 세로선을 ─ │ ┼ 로 (그 밖의 격자 글자는 그대로 ASCII)
  --stdout        파일 대신 화면에 찍습니다
  --no-wait       끝나도 Enter 를 기다리지 않습니다 (끌어다 놓아 연 콘솔에서만 기다립니다)

종료 코드  0 OK · 1 점검 실패(읽을 수 없는 그림 · 쓸 수 없음) · 2 사용법 오류 · 3 사람 확인 필요
원본 그림은 바꾸지 않습니다.
""" % (render.MIN_WIDTH, render.MAX_WIDTH, render.DEFAULT_WIDTH)


class UsageError(Exception):
    """사용법이 틀렸다 — 메시지는 사람에게 그대로 보여 줄 한국어 한 줄"""


def parse(argv):
    """argv → (명령 또는 None, 옵션 dict). 틀리면 UsageError"""
    opts = {"files": [], "width": render.DEFAULT_WIDTH, "kind": "auto", "box": False, "stdout": False, "wait": True}
    if len(argv) == 1 and argv[0] in ("version", "--version", "help", "--help", "-h", "check"):
        return {"--version": "version", "--help": "help", "-h": "help"}.get(argv[0], argv[0]), opts
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--box", "--stdout", "--no-wait"):
            opts[{"--box": "box", "--stdout": "stdout", "--no-wait": "wait"}[a]] = a != "--no-wait"
        elif a in ("--width", "--kind") or a.startswith(("--width=", "--kind=")):
            name = a.split("=", 1)[0][2:]
            if "=" in a:
                value = a.split("=", 1)[1]
            else:
                i += 1
                if i >= len(argv):
                    raise UsageError("--%s 다음에 값이 필요합니다" % name)
                value = argv[i]
            if name == "width":
                try:
                    opts["width"] = int(value)
                except ValueError:
                    raise UsageError("--width 는 숫자여야 합니다 (%s)" % value)
                if not render.MIN_WIDTH <= opts["width"] <= render.MAX_WIDTH:
                    raise UsageError("--width 는 %d–%d 사이여야 합니다 (%d)" % (render.MIN_WIDTH, render.MAX_WIDTH, opts["width"]))
            else:
                if value not in KINDS:
                    raise UsageError("--kind 는 %s 중 하나입니다 (%s)" % (" · ".join(KINDS), value))
                opts["kind"] = value
        elif a.startswith("-") and len(a) > 1:
            raise UsageError("모르는 옵션입니다: %s (help 를 보세요)" % a)
        else:
            opts["files"].append(a)
        i += 1
    if not opts["files"]:
        return "help", opts
    return None, opts


def output_file(src):
    """입력 옆의 비어 있는 <이름>.txt 를 배타적으로 연다 (있으면 <이름> (2).txt …). 덮어쓰지 않는다. → (경로, 파일 객체)"""
    folder, name = os.path.split(os.path.abspath(src))
    stem = os.path.splitext(name)[0]
    for n in range(1, MAX_COLLISIONS + 1):
        path = os.path.join(folder, (stem if n == 1 else "%s (%d)" % (stem, n)) + ".txt")
        try:
            return path, open(path, "x", encoding="utf-8")
        except FileExistsError:
            continue
    raise OSError("비어 있는 이름을 찾지 못했습니다 (%s (%d).txt 까지 있음)" % (stem, MAX_COLLISIONS))


def analyze(src):
    """그림 하나를 읽어 요소를 찾는다 (오래 걸리는 부분) → (Segmentation 또는 None, 상태, 한 줄). 원본은 읽기만 한다"""
    name = os.path.basename(src)
    try:
        image = png.load(src)
    except png.PngError as e:
        return None, FAIL, "실패  %s: %s" % (name, e)
    seg = seg_mod.segment(image)
    if seg.reason:
        return None, CONFIRM, "확인 필요  %s: %s" % (name, seg.reason)
    if not [e for e in seg.elements if e.kind != "text"]:
        return None, CONFIRM, "확인 필요  %s: 그릴 것(선 · 점 · 외곽)을 찾지 못했습니다" % name
    return seg, OK, ""


def make_art(seg, name, opts):
    """찾은 요소 → (상태, 한 줄, 글자 아트 또는 None, 모양). --kind 가 그림과 맞지 않으면 만들지 않고 확인을 요청한다"""
    if opts["kind"] == "wafer" and seg.ring is None:
        return CONFIRM, "확인 필요  %s: 웨이퍼 외곽(원)을 찾지 못했습니다 — --kind auto 로 해 보세요" % name, None, ""
    if opts["kind"] == "chart" and seg.ring is not None:
        return CONFIRM, "확인 필요  %s: 웨이퍼 맵처럼 보입니다 — --kind wafer 나 auto 로 해 보세요" % name, None, ""
    text = render.render(seg, opts["width"], opts["box"])
    lines = text.rsplit("\n\n", 1)[0].split("\n")
    return OK, "", text, "%d열 %d행 · 점 추정 %d개" % (max(len(x) for x in lines), len(lines), seg.dots())


def convert(src, opts, out):
    """그림 하나 → (상태, 한 줄). 상태는 OK · CONFIRM · FAIL. 원본은 읽기만 한다"""
    name = os.path.basename(src)
    seg, code, line = analyze(src)
    if seg is None:
        return code, line
    code, line, text, shape = make_art(seg, name, opts)
    if text is None:
        return code, line
    if opts["stdout"]:
        out.write("== %s ==\n%s\n" % (name, text))
        return OK, "OK  %s (%s)" % (name, shape)
    try:
        path, f = output_file(src)
    except OSError as e:
        return FAIL, "실패  %s: 결과 파일을 만들 수 없습니다 (%s) — --stdout 으로 화면에 찍을 수 있습니다" % (name, e.__class__.__name__)
    with f:
        f.write(text)
    return OK, "OK  %s → %s (%s)" % (name, os.path.basename(path), shape)


def png_bytes(width, height, rgb):
    """RGB 를 PNG 로 (자가 점검용 — 디코더를 실제로 거치게)"""
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + rgb[y * width * 3:(y + 1) * width * 3] for y in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def check(out):
    """내장 그림(붉은 가로선 하나와 파란 점 셋)을 PNG 로 만들어 읽기 → 요소 찾기 → 글자 아트까지 한 번 통과시킨다"""
    problems = []
    out.write("%s %s · 파이썬 %d.%d.%d\n" % (APP, VERSION, *sys.version_info[:3]))
    out.write("  창 (tkinter)  %s\n" % ("있음" if gui.available() else "없음 — 명령줄로만 쓸 수 있습니다"))
    if sys.version_info < (3, 8):
        problems.append("파이썬 3.8 이상이 필요합니다")
    w, h = 90, 60
    px = bytearray(b"\xff" * (w * h * 3))

    def paint(x0, y0, x1, y1, rgb):
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                px[3 * (y * w + x):3 * (y * w + x) + 3] = bytes(rgb)

    paint(5, 29, 84, 31, (225, 40, 45))
    for x in (15, 45, 75):
        paint(x, 10, x + 4, 14, (60, 85, 165))
    try:
        image = png.decode(png_bytes(w, h, bytes(px)))
        out.write("  PNG 읽기      %s\n" % ("OK" if (image.width, image.height) == (w, h) and image.pixel(17, 12) == (60, 85, 165) else "틀림"))
        if (image.width, image.height) != (w, h) or image.pixel(17, 12) != (60, 85, 165):
            problems.append("PNG 읽기가 내장 그림과 다르다")
        seg = seg_mod.segment(image)
        ok = seg.dots() == 3 and len(seg.of("hline")) == 1
        out.write("  요소 찾기     %s\n" % ("OK" if ok else "틀림"))
        if not ok:
            problems.append("요소 찾기: 점 %d개 · 가로선 %d줄 (3 · 1 이어야 함)" % (seg.dots(), len(seg.of("hline"))))
        text = render.render(seg, render.MIN_WIDTH)
        art = text.rsplit("\n\n", 1)[0]
        ok = sum(art.count(g) for g in "oO@") == 3 and "=" in art
        out.write("  글자 아트     %s\n" % ("OK" if ok else "틀림"))
        if not ok:
            problems.append("글자 아트가 기대와 다르다")
    except Exception as e:                                    # 점검은 어떤 예외든 실패로 보고하고 끝낸다
        problems.append("%s: %s" % (e.__class__.__name__, e))
    for p in problems:
        out.write("  × %s\n" % p)
    code = FAIL if problems else OK
    out.write(RESULT[code] + "\n")
    return code


def main(argv, out=None, err=None):
    out = out or sys.stdout
    err = err or sys.stderr
    try:
        command, opts = parse(argv)
    except UsageError as e:
        err.write("%s\n" % e)
        return USAGE
    if command == "version":
        out.write("%s %s\n" % (APP, VERSION))
        return OK
    if command == "help":
        out.write(HELP)
        return OK
    if command == "check":
        return check(out)
    codes = []
    for src in opts["files"]:
        if not os.path.isfile(src):
            code, line = FAIL, "실패  %s: 파일이 없습니다" % os.path.basename(src)
        else:
            code, line = convert(src, opts, out)
        out.write(line + "\n")
        codes.append(code)
    worst = FAIL if FAIL in codes else (CONFIRM if CONFIRM in codes else OK)
    out.write(RESULT[worst] + "\n")
    return worst


def should_wait(args):
    """끌어다 놓은 것처럼 그림 경로가 맨 앞에 오고, 대기를 끄지 않았고, 화면에 찍는 중이 아닐 때만 (명령 · 옵션부터 치면 사람이 터미널에 있다)"""
    dropped = bool(args) and not args[0].startswith("-") and args[0] not in ("version", "help", "check")
    return dropped and "--no-wait" not in args and "--stdout" not in args


def wait_for_enter():
    """끌어다 놓아 연 콘솔은 끝나자마자 닫혀 결과를 못 본다 — 사람이 앞에 있는 콘솔에서만 기다린다"""
    try:
        if sys.stdin.isatty() and sys.stdout.isatty():
            sys.stdout.write("\nEnter 를 누르면 닫힙니다.")
            sys.stdout.flush()
            input()
    except (EOFError, OSError):
        pass


def entry(args):
    """실행 진입 → 종료 코드. 인자가 없거나 gui 면 창, 그 밖에는 명령줄"""
    if not args or args[0] == "gui":
        rest = args[1:]
        me = sys.modules.get(__name__) or SimpleNamespace(**globals())      # 시험은 파일 경로로 불러와 sys.modules 에 없다
        if rest == ["--selftest"]:
            return gui.selftest(me)
        if len(rest) > 1 or (rest and rest[0].startswith("-")):
            sys.stderr.write("사용법: ascii-1.py gui [<그림.png> | --selftest]\n")
            return USAGE
        return gui.run(me, rest)
    code = main(args)
    if should_wait(args):
        wait_for_enter()
    return code


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(entry(sys.argv[1:]))
