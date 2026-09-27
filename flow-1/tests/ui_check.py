# -*- coding: utf-8 -*-
"""화면 확인 도구 (개발용 · 표준 라이브러리만) — Playwright 가 없는 사내 PC 에서 화면을 고칠 때 쓴다.

  python tests/ui_check.py shots                    예시 폴더로 Flow–1 을 띄워 다크 · 라이트 × 폭 1440 · 500 을 찍는다
  python tests/ui_check.py shots --watch "D:\\분석"   내 폴더로 (코드는 읽기만 · 설정 · 감시 목록은 건드리지 않음)
  python tests/ui_check.py glyphs "새 문구 ◐"        내장 폰트에 없는 글자 · 흐름도에서 차지하는 칸 수

사진은 shots/ui-<테마>-<폭>.png (shots/ 는 커밋하지 않는다). 브라우저는 Edge → Chrome → Chromium 순서로 찾는다.
못 찾으면 --browser "경로" 또는 환경 변수 FLOW_BROWSER. 창은 뜨지 않는다 (headless).
Flow–1 은 임시 데이터 폴더(FLOW_HOME)에서 따로 띄우고 끝나면 끈다 — 켜 둔 Flow–1 · 사용자 설정과 상관없다.
"""
import argparse
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FONT = os.path.join(ROOT, "fonts", "flow-1-dos.woff")
LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))     # 127.0.0.1 은 프록시를 거치지 않는다


# ─────────────────────────────────────────────────────────────── 브라우저

def find_browser(given: str = "") -> str:
    cands = [given, os.environ.get("FLOW_BROWSER", "")]
    for env in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            cands += [os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
                      os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")]
    cands += [shutil.which(n) or "" for n in ("msedge", "microsoft-edge", "google-chrome", "chrome", "chromium", "chromium-browser")]
    return next((c for c in cands if c and os.path.isfile(c)), "")


def browser_args(exe: str, profile: str, w: int, h: int) -> list:
    args = [exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run", "--no-default-browser-check",
            "--no-proxy-server", "--disable-extensions", f"--user-data-dir={profile}", f"--window-size={w},{h}"]
    if os.name == "posix" and hasattr(os, "geteuid") and os.geteuid() == 0:
        args.append("--no-sandbox")          # 리눅스에서 root 로 돌 때만 (CI · 컨테이너)
    return args


def viewport(exe: str, tmp: str):
    """headless 창의 (가장 좁은 화면 폭, 창과 화면 높이 차이). Chromium 141: 폭은 500 아래로 안 줄고, 화면이 창보다 87px 낮다.
    재서 높이는 그만큼 창을 키워 찍고 잘라 내며, 더 좁은 폭은 가장 좁은 폭으로 찍는다"""
    probe = os.path.join(tmp, "vp.html")
    with open(probe, "w", encoding="utf-8") as f:
        f.write('<html><body><script>document.body.textContent = "VP" + innerWidth + "VP" + innerHeight + "VP";</script></body></html>')
    try:
        p = subprocess.run(browser_args(exe, os.path.join(tmp, "probe"), 320, 600)
                           + ["--virtual-time-budget=1000", "--dump-dom", "file:///" + probe.replace("\\", "/").lstrip("/")],
                           capture_output=True, timeout=60)
        parts = p.stdout.decode("utf-8", "replace").split("VP")
        return max(320, int(parts[1])), max(0, min(300, 600 - int(parts[2])))
    except (subprocess.SubprocessError, OSError, ValueError, IndexError):
        return 320, 0


def crop_png(path: str, height: int) -> bool:
    """PNG 를 위에서 height 줄만 남긴다 (8비트 RGB · RGBA · 비인터레이스 — Chromium 스크린숏). 아래 줄만 버리므로 필터를 풀 필요가 없다"""
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return False
    pos, chunks = 8, []
    while pos + 8 <= len(data):
        n = struct.unpack(">I", data[pos:pos + 4])[0]
        chunks.append((data[pos + 4:pos + 8], data[pos + 8:pos + 8 + n]))
        pos += 12 + n
    w, h, depth, ctype, _, _, inter = struct.unpack(">IIBBBBB", chunks[0][1])
    if height >= h or depth != 8 or inter != 0 or ctype not in (2, 6):
        return False
    raw = zlib.decompress(b"".join(b for t, b in chunks if t == b"IDAT"))
    keep = raw[:height * (1 + w * (3 if ctype == 2 else 4))]

    def chunk(t: bytes, b: bytes) -> bytes:
        return struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, height, depth, ctype, 0, 0, 0)
    extra = b"".join(chunk(t, b) for t, b in chunks[1:] if t not in (b"IDAT", b"IEND"))
    with open(path, "wb") as f:
        f.write(data[:8] + chunk(b"IHDR", ihdr) + extra + chunk(b"IDAT", zlib.compress(keep, 9)) + chunk(b"IEND", b""))
    return True


# ─────────────────────────────────────────────────────────────── Flow–1 띄우기

def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def start_app(tmp: str, theme: str, watch: str):
    import json
    home = tempfile.mkdtemp(prefix=f"home-{theme}-", dir=tmp)
    with open(os.path.join(home, "config.json"), "w", encoding="utf-8") as f:
        json.dump({"watch": [watch], "theme": theme, "idle_exit_min": 0, "open_window": False}, f)
    port = free_port()
    proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "flow-1.py"), "--no-window", "--port", str(port)],
                            env=dict(os.environ, FLOW_HOME=home, PYTHONUTF8="1"),
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    url = f"http://127.0.0.1:{port}/"
    for _ in range(100):
        try:
            with LOCAL.open(url + "api/ping", timeout=1):
                return proc, url
        except OSError:
            if proc.poll() is not None:
                break
            time.sleep(0.2)
    proc.kill()
    err = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
    raise SystemExit("Flow–1 을 띄우지 못했습니다\n" + err[-2000:])


def cmd_shots(a) -> int:
    exe = find_browser(a.browser)
    if not exe:
        print("브라우저(Edge · Chrome · Chromium)를 찾지 못했습니다 → --browser \"경로\" 또는 FLOW_BROWSER")
        print("결과: 점검 실패")
        return 1
    watch = os.path.abspath(a.watch or os.path.join(HERE, "examples"))
    sizes = [tuple(int(v) for v in s.lower().split("x")) for s in a.sizes.split(",")]
    os.makedirs(a.out, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="flow1-ui-")
    made, bad = [], []
    try:
        min_w, gap = viewport(exe, tmp)
        print(f"- 브라우저 : {exe} (headless · 가장 좁은 폭 {min_w}px · 창과 화면 높이 차이 {gap}px)")
        if any(w < min_w for w, _ in sizes):
            print(f"- 알림     : 이 브라우저는 {min_w}px 보다 좁게 못 그린다 → 그 폭은 {min_w}px 로 찍는다 (더 좁은 창은 tests/e2e_ui.py)")
            sizes = [(max(w, min_w), h) for w, h in sizes]
        for theme in a.themes.split(","):
            proc, url = start_app(tmp, theme, watch)
            try:
                for w, h in sizes:
                    path = os.path.abspath(os.path.join(a.out, f"ui-{theme}-{w}.png"))
                    if os.path.exists(path):
                        os.remove(path)
                    subprocess.run(browser_args(exe, os.path.join(tmp, "profile"), w, h + gap)
                                   + [f"--virtual-time-budget={a.wait * 1000}", f"--screenshot={path}", url],
                                   capture_output=True, timeout=120)
                    if os.path.exists(path) and os.path.getsize(path) > 1000:
                        if gap:
                            crop_png(path, h)
                        made.append(path)
                    else:
                        bad.append(f"{theme} {w}x{h}")
            finally:
                proc.terminate()
                try:
                    proc.wait(10)
                except subprocess.TimeoutExpired:
                    proc.kill()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for p in made:
        print(f"- 사진     : {p}")
    for b in bad:
        print(f"- 못 찍음  : {b}")
    print("눈으로 볼 것: docs/UI.md › 09 (다크 · 라이트 · 좁은 창 · 빨강 없음 · 라임은 지금 · 켜짐 · 선택 · 진행에만)")
    print("결과: OK" if made and not bad else "결과: 점검 실패")
    return 0 if made and not bad else 1


# ─────────────────────────────────────────────────────────────── 글자

def font_codepoints() -> set:
    """내장 폰트(WOFF 1 · zlib)의 cmap 에 있는 글자"""
    with open(FONT, "rb") as f:
        data = f.read()
    n = struct.unpack(">H", data[12:14])[0]
    tables = {}
    for i in range(n):
        tag, off, comp, orig, _ = struct.unpack(">4sIIII", data[44 + 20 * i:64 + 20 * i])
        raw = data[off:off + comp]
        tables[tag] = zlib.decompress(raw) if comp < orig else raw
    cmap, cps = tables[b"cmap"], set()
    for i in range(struct.unpack(">H", cmap[2:4])[0]):
        so = struct.unpack(">I", cmap[8 + 8 * i:12 + 8 * i])[0]
        fmt = struct.unpack(">H", cmap[so:so + 2])[0]
        if fmt == 4:
            seg2 = struct.unpack(">H", cmap[so + 6:so + 8])[0]
            ends = struct.unpack(f">{seg2 // 2}H", cmap[so + 14:so + 14 + seg2])
            starts = struct.unpack(f">{seg2 // 2}H", cmap[so + 16 + seg2:so + 16 + 2 * seg2])
            for s, e in zip(starts, ends):
                if s != 0xFFFF:
                    cps.update(range(s, e + 1))
        elif fmt == 12:
            for g in range(struct.unpack(">I", cmap[so + 12:so + 16])[0]):
                s, e, _ = struct.unpack(">III", cmap[so + 16 + 12 * g:so + 28 + 12 * g])
                cps.update(range(s, e + 1))
    return cps


def cmd_glyphs(a) -> int:
    sys.path.insert(0, ROOT)
    import flow1_graph
    cps = font_codepoints()
    seen, missing = [], []
    for ch in a.text:
        if ch in seen or ch in "\r\n\t":
            continue
        seen.append(ch)
        o, w = ord(ch), flow1_graph.cw(ch)
        ok = o in cps
        if not ok:
            missing.append(ch)
        note = "" if ok else "  ← 내장 폰트에 없음: 다른 글꼴로 그려져 칸이 어긋난다"
        if ok and w == 2 and not (0xAC00 <= o <= 0xD7A3 or 0x3130 <= o <= 0x318F):
            note = "  ← 폭 2칸 기호: 상태 표시에는 쓰지 않는다 (docs/DESIGN.md › 03)"
        print(f"{ch}  U+{o:04X}  {w}칸{note}")
    print(f"- 글자 {len(seen)}개 · 흐름도 폭 {flow1_graph.cells(a.text)}칸 ({flow1_graph.cells(a.text) * flow1_graph.CELL}px) · 폰트에 없는 글자 {len(missing)}개")
    print("결과: OK" if not missing else "결과: 확인 필요")
    return 0 if not missing else 3


def main() -> int:
    ap = argparse.ArgumentParser(description="Flow–1 화면 확인 (Playwright 없이)")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("shots", help="다크 · 라이트 × 폭마다 화면 사진")
    s.add_argument("--browser", default="", help="Edge · Chrome · Chromium 실행 파일 (없으면 찾는다)")
    s.add_argument("--watch", default="", help="감시할 폴더 · 파일 (기본: tests/examples)")
    s.add_argument("--out", default=os.path.join(ROOT, "shots"))
    s.add_argument("--themes", default="dark,light")
    s.add_argument("--sizes", default="1440x900,500x900", help="폭x높이, 쉼표로 여럿 (headless 는 500 보다 좁게 못 그린다)")
    s.add_argument("--wait", type=int, default=8, help="화면이 그려질 때까지 기다리는 초 (가상 시간)")
    g = sub.add_parser("glyphs", help="글자가 내장 폰트에 있는지 · 흐름도 칸 수")
    g.add_argument("text")
    a = ap.parse_args()
    if a.cmd == "shots":
        return cmd_shots(a)
    if a.cmd == "glyphs":
        return cmd_glyphs(a)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
