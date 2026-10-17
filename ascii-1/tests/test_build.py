# -*- coding: utf-8 -*-
"""tools/build_exe.py 시험 — 태그 · 버전 · 해시 · 스모크 시험이 제대로 잡는지. PyInstaller 없이 돈다
(스모크는 [python, ascii-1.py] 로 시험하고, 일부러 틀린 명령으로 실패를 잡는지 본다). 파일은 임시 폴더에만 만든다"""
import hashlib
import importlib.util
import io
import os
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


be = load("build_exe", os.path.join(ROOT, "tools", "build_exe.py"))
app = load("ascii_1_for_build", os.path.join(ROOT, "ascii-1.py"))
WORKFLOW = os.path.join(os.path.dirname(ROOT), ".github", "workflows", "ascii-1-release.yml")


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = be.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class Version(unittest.TestCase):
    def test_reads_the_constant_without_importing(self):
        self.assertEqual(be.read_version(), app.VERSION)

    def test_tag_must_match(self):
        self.assertIsNone(be.check_tag("ascii-1-v" + app.VERSION))
        self.assertIn("다릅니다", be.check_tag("ascii-1-v9.9.9"))
        for bad in ("v" + app.VERSION, "ascii-1-" + app.VERSION, "flow-1-v1.0.0", ""):
            self.assertIn("ascii-1-vX.Y.Z", be.check_tag(bad), bad)              # 모양부터 틀림
        self.assertIn("다릅니다", be.check_tag("ascii-1-v"), "접두어만 있고 버전이 비었다")

    def test_tag_follows_the_constant(self):
        with mock.patch.object(be, "read_version", return_value="1.2.3"):
            self.assertIsNone(be.check_tag("ascii-1-v1.2.3"))
            self.assertIsNotNone(be.check_tag("ascii-1-v1.2.4"))

    def test_main_tag_exit_codes(self):
        code, out, _ = run("--tag", "ascii-1-v" + app.VERSION)
        self.assertEqual((code, out.splitlines()[-1]), (0, "결과: OK"))
        code, out, _ = run("--tag", "ascii-1-v0.0.0")
        self.assertEqual((code, out.splitlines()[-1]), (1, "결과: 점검 실패"))


class Hash(unittest.TestCase):
    def test_line_is_what_sha256sum_reads(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "ascii-1.exe")
            data = os.urandom(3 * (1 << 20) + 17)         # 블록 경계를 넘는 크기
            with open(path, "wb") as f:
                f.write(data)
            self.assertEqual(be.sha256_line(path), "%s *ascii-1.exe\n" % hashlib.sha256(data).hexdigest())


class Smoke(unittest.TestCase):
    def test_passes_for_the_real_program(self):
        self.assertEqual(be.smoke([sys.executable, os.path.join(ROOT, "ascii-1.py")]), [])

    def test_relative_paths_are_fixed_before_changing_folders(self):
        here = os.getcwd()
        try:
            os.chdir(ROOT)
            self.assertEqual(be.smoke([sys.executable, "ascii-1.py"]), [])
        finally:
            os.chdir(here)

    def test_a_program_that_only_pretends_is_caught(self):
        liar = [sys.executable, "-c", "print('결과: OK')"]          # version · 변환 · 이름 충돌 · 확인 필요 · 사용법 오류를 못 한다
        problems = be.smoke(liar)
        self.assertGreaterEqual(len(problems), 4, problems)
        self.assertTrue(any("version" in p for p in problems))

    def test_wrong_version_is_caught(self):
        wrong = [sys.executable, "-c", "import sys; print('ascii-1 9.9.9' if sys.argv[1:] == ['version'] else '결과: OK')"]
        self.assertTrue(any(p.startswith("version") for p in be.smoke(wrong)))

    def test_a_program_that_overwrites_is_caught(self):
        real = os.path.join(ROOT, "ascii-1.py")
        patched = ("import runpy, sys, os\n"
                   "import builtins\n"
                   "_open = builtins.open\n"
                   "builtins.open = lambda p, m='r', *a, **k: _open(p, 'w' if m == 'x' else m, *a, **k)\n"      # 배타 열기를 덮어쓰기로
                   "sys.argv = [%r] + sys.argv[1:]\n"
                   "runpy.run_path(%r, run_name='__main__')\n" % (real, real))
        with tempfile.TemporaryDirectory() as d:
            script = os.path.join(d, "overwriting.py")
            with open(script, "w", encoding="utf-8") as f:
                f.write(patched)
            problems = be.smoke([sys.executable, script])
        self.assertTrue(any("이름 충돌" in p for p in problems), problems)

    def test_main_smoke_exit_codes(self):
        code, out, _ = run("--smoke", sys.executable, os.path.join(ROOT, "ascii-1.py"))
        self.assertEqual((code, out.splitlines()[-1]), (0, "결과: OK"))
        code, out, _ = run("--smoke", sys.executable, "-c", "print('x')")
        self.assertEqual((code, out.splitlines()[-1]), (1, "결과: 점검 실패"))


class Usage(unittest.TestCase):
    def test_usage_errors(self):
        for argv in (["--tag"], ["--smoke"], ["--nope"], ["x"]):
            with self.subTest(argv=argv):
                code, out, err = run(*argv)
                self.assertEqual((code, out), (2, ""))
                self.assertTrue(err)


class Workflow(unittest.TestCase):
    """릴리스 워크플로가 약속을 지키는지 글자로 본다 (실제 빌드는 GitHub 의 Windows 에서 돈다)"""

    def setUp(self):
        self.assertTrue(os.path.isfile(WORKFLOW), WORKFLOW)
        with open(WORKFLOW, encoding="utf-8") as f:
            self.text = f.read()

    def test_release_only_on_tags_and_with_write_scope_only_there(self):
        self.assertIn('tags: ["ascii-1-v*"]', self.text)
        self.assertIn("startsWith(github.ref, 'refs/tags/ascii-1-v')", self.text)
        head, release = self.text.split("  release:", 1)
        self.assertIn("permissions:\n  contents: read", head, "기본 권한은 읽기")
        self.assertNotIn("contents: write", head, "쓰기 권한은 release 잡에만")
        self.assertIn("contents: write", release)
        self.assertIn("--verify-tag", release)

    def test_builds_on_windows_with_a_pinned_pyinstaller_and_smoke_tests_it(self):
        self.assertIn("runs-on: windows-latest", self.text)
        pin = re.search(r"pyinstaller==(\d+\.\d+(?:\.\d+)?)", self.text)
        self.assertIsNotNone(pin, "PyInstaller 버전을 고정해야 한다")
        with open(os.path.join(ROOT, "tools", "build_exe.py"), encoding="utf-8") as f:
            self.assertIn("pyinstaller==" + pin.group(1), f.read(), "도구 설명의 버전과 워크플로의 고정 버전이 같아야 한다")
        self.assertLess(self.text.index("build_exe.py --smoke"), self.text.index("upload-artifact"))
        self.assertLess(self.text.index("--tag"), self.text.index("pip install pyinstaller"), "태그 검사가 먼저")

    def test_pull_requests_build_but_do_not_release(self):
        self.assertIn("pull_request:", self.text)
        self.assertIn('paths: ["ascii-1/**"', self.text)
        self.assertEqual(self.text.count("gh release create"), 1)


if __name__ == "__main__":
    unittest.main()
