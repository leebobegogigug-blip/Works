# -*- coding: utf-8 -*-
"""ascii-1.py 뼈대 테스트 — version · help · 모르는 명령. 변환 명령이 생기면 여기서 늘린다"""
import importlib.util
import io
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("ascii_1", os.path.join(os.path.dirname(HERE), "ascii-1.py"))
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class Cli(unittest.TestCase):
    def test_version(self):
        for flag in ("version", "--version"):
            code, out, _ = run(flag)
            self.assertEqual((code, out.strip()), (0, "ascii-1 " + cli.VERSION))

    def test_help_is_default(self):
        self.assertEqual(run()[0], 0)
        self.assertIn("Ascii–1", run("help")[1])

    def test_unknown_command_is_usage_error(self):
        code, out, err = run("그림.png")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("개발 중", err)


if __name__ == "__main__":
    unittest.main()
