# -*- coding: utf-8 -*-
"""ascii-1.exe 빌드 · 스모크 시험 — 개발 도구다 (tools/ 는 RULES.md › W-02 의 실행 경로가 아니다). 앱 실행에는 필요 없다.

  pip install pyinstaller==6.10.0
  python tools/build_exe.py                          dist/ascii-1.exe (Windows 밖에서는 확장자 없이) + ascii-1.exe.sha256
  python tools/build_exe.py --tag ascii-1-v0.1.0     태그가 ascii-1.py 의 VERSION 과 맞는지만 본다 (릴리스 워크플로가 먼저 부른다)
  python tools/build_exe.py --smoke [--window] dist/ascii-1.exe   만든 파일로 version · check · 변환 · 이름 충돌 · 확인 필요를 시험한다.
                                                     --window 는 창도 실제로 열어 그림 하나를 읽고 그려 본다 (화면이 있는 곳에서만)

마지막 줄은 결과: OK · 결과: 점검 실패 (S-03). 서명하지 않은 exe 라서 SmartScreen · 사내 백신이 막을 수 있다 (docs/MANUAL.md).
"""
import hashlib
import importlib.util
import os
import re
import subprocess
import sys
import tempfile

TOOLS = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(TOOLS)
ENTRY = os.path.join(APP, "ascii-1.py")
EXE_NAME = "ascii-1.exe" if os.name == "nt" else "ascii-1"
TAG_PREFIX = "ascii-1-v"
VERSION_RE = re.compile(r'^VERSION\s*=\s*"(\d+\.\d+\.\d+)"', re.M)


def read_version():
    """ascii-1.py 의 VERSION 상수 (불러오지 않고 글자로 읽는다)"""
    with open(ENTRY, encoding="utf-8") as f:
        m = VERSION_RE.search(f.read())
    if m is None:
        raise SystemExit("ascii-1.py 에서 VERSION 을 찾지 못했습니다")
    return m.group(1)


def check_tag(tag):
    """릴리스 태그가 ascii-1-vX.Y.Z 이고 VERSION 과 같은가 → 틀린 까닭 또는 None"""
    want = TAG_PREFIX + read_version()
    if not tag.startswith(TAG_PREFIX):
        return "태그는 %sX.Y.Z 모양이어야 합니다 (%s)" % (TAG_PREFIX, tag)
    return None if tag == want else "태그 %s 가 ascii-1.py 의 VERSION 이 가리키는 %s 와 다릅니다" % (tag, want)


def sha256_line(path):
    """sha256sum 이 읽는 한 줄: '<해시> *<파일 이름>'"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return "%s *%s\n" % (h.hexdigest(), os.path.basename(path))


def build(dist, work):
    """PyInstaller 로 한 파일 콘솔 exe 를 만든다 → 만든 경로"""
    os.makedirs(dist, exist_ok=True)
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--console",
           "--name", "ascii-1", "--distpath", dist, "--workpath", work, "--specpath", work, ENTRY]
    subprocess.run(cmd, check=True, cwd=APP)
    out = os.path.join(dist, EXE_NAME)
    if not os.path.isfile(out):
        raise SystemExit("PyInstaller 가 %s 를 만들지 못했습니다" % out)
    with open(out + ".sha256", "w", encoding="utf-8", newline="\n") as f:
        f.write(sha256_line(out))
    return out


def _load_app():
    spec = importlib.util.spec_from_file_location("ascii_1_src", ENTRY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(cmd, *args, cwd=None):
    env = dict(os.environ, PYTHONIOENCODING="cp949")          # 콘솔 인코딩이 UTF-8 이 아니어도 깨지지 않아야 한다
    p = subprocess.run(list(cmd) + list(args), capture_output=True, stdin=subprocess.DEVNULL, timeout=180, cwd=cwd, env=env)
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def smoke(cmd, window=False):
    """cmd(실행 파일 또는 [python, ascii-1.py]) 가 실제로 돌아가는지 시험한다 → 틀린 것의 목록(없으면 []).
    window=True 면 `gui --selftest` 로 창도 연다 — 한 파일 exe 에 창 부품(tcl/tk)이 제대로 들어갔는지는 열어 봐야 안다"""
    problems = []
    cmd = [os.path.abspath(c) if os.path.isfile(c) else c for c in cmd]    # 시험은 임시 폴더에서 돌리므로 상대 경로를 고정한다
    app = _load_app()
    code, out, _ = _run(cmd, "version")
    if code != 0 or out.strip() != "ascii-1 " + app.VERSION:
        problems.append("version: 종료 코드 %d · 출력 %r (기대: ascii-1 %s)" % (code, out.strip(), app.VERSION))
    code, out, _ = _run(cmd, "check")
    if code != 0 or not out.rstrip().endswith("결과: OK"):
        problems.append("check: 종료 코드 %d · 마지막 줄 %r" % (code, out.strip().splitlines()[-1:] or ""))
    w, h = 90, 60
    px = bytearray(b"\xff" * (w * h * 3))
    for y in range(29, 32):
        px[3 * (y * w + 5):3 * (y * w + 85)] = bytes((225, 40, 45)) * 80
    for x in (15, 45, 75):
        for y in range(10, 15):
            px[3 * (y * w + x):3 * (y * w + x + 5)] = bytes((60, 85, 165)) * 5
    blank = app.png_bytes(40, 30, b"\xff" * (40 * 30 * 3))
    with tempfile.TemporaryDirectory() as tmp:
        folder = os.path.join(tmp, "한글 폴더 two words")
        os.makedirs(folder)
        src = os.path.join(folder, "그림 하나.png")
        with open(src, "wb") as f:
            f.write(app.png_bytes(w, h, bytes(px)))
        empty = os.path.join(folder, "빈 그림.png")
        with open(empty, "wb") as f:
            f.write(blank)
        code, out, _ = _run(cmd, src, "--no-wait", cwd=tmp)
        txt = os.path.join(folder, "그림 하나.txt")
        if code != 0 or not out.rstrip().endswith("결과: OK"):
            problems.append("변환: 종료 코드 %d · 출력 %r" % (code, out.strip()[-200:]))
        if not os.path.isfile(txt):
            problems.append("변환: 입력 옆에 결과 .txt 가 없다")
        else:
            with open(txt, encoding="utf-8") as f:
                body = f.read()
            art = body.replace("\r\n", "\n").rsplit("\n\n", 1)[0]          # 범례(`o O @ …`)는 세지 않는다
            if "=" not in art or sum(art.count(g) for g in "oO@") != 3:
                problems.append("변환: 결과 모양이 기대와 다르다 (붉은 선 = 하나 · 점 셋)")
        code, _, _ = _run(cmd, src, "--no-wait", cwd=tmp)
        if code != 0 or not os.path.isfile(os.path.join(folder, "그림 하나 (2).txt")):
            problems.append("이름 충돌: 덮어쓰지 않고 '그림 하나 (2).txt' 를 만들어야 한다")
        code, out, _ = _run(cmd, empty, "--no-wait", cwd=tmp)
        if code != 3 or not out.rstrip().endswith("결과: 확인 필요"):
            problems.append("확인 필요: 빈 그림은 종료 코드 3 이어야 한다 (%d)" % code)
        code, _, _ = _run(cmd, "--width", "5", src, cwd=tmp)
        if code != 2:
            problems.append("사용법 오류: 범위 밖 --width 는 종료 코드 2 여야 한다 (%d)" % code)
    if window:
        code, out, err = _run(cmd, "gui", "--selftest")
        if code != 0 or not out.rstrip().endswith("결과: OK"):
            problems.append("창: 종료 코드 %d · 출력 %r %r" % (code, out.strip()[-200:], err.strip()[-200:]))
    return problems


def main(argv):
    if argv[:1] == ["--tag"]:
        if len(argv) != 2:
            print("--tag 다음에 태그가 필요합니다", file=sys.stderr)
            return 2
        bad = check_tag(argv[1])
        print(bad if bad else "태그 %s 는 VERSION %s 와 맞습니다" % (argv[1], read_version()))
        print("결과: 점검 실패" if bad else "결과: OK")
        return 1 if bad else 0
    if argv[:1] == ["--smoke"]:
        window = argv[1:2] == ["--window"]
        cmd = argv[2:] if window else argv[1:]
        if not cmd:
            print("--smoke 다음에 실행 파일이 필요합니다", file=sys.stderr)
            return 2
        problems = smoke(cmd, window)
        for p in problems:
            print("  × " + p)
        print("결과: 점검 실패" if problems else "결과: OK")
        return 1 if problems else 0
    if argv:
        print("사용법: build_exe.py [--tag TAG | --smoke [--window] 실행파일 [인자…]]", file=sys.stderr)
        return 2
    out = build(os.path.join(APP, "dist"), os.path.join(APP, "build"))
    print("만들었습니다: %s (%d 바이트)" % (out, os.path.getsize(out)))
    print("SHA-256: " + sha256_line(out).strip())
    print("결과: OK")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
