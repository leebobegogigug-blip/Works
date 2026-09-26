# -*- coding: utf-8 -*-
"""works_check.py 테스트 (표준 라이브러리 unittest). 임시 폴더에 작은 works 저장소를 만들어 검사한다."""
import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import works_check as wc  # noqa: E402

RULES = """# works 규칙

### W-01 폴더 = 앱 = 명령
### W-02 의존성 0
### W-03 내 PC 에서만
### W-10 디자인은 하나

| # | 규약 |
|---|---|
| S-02 | **버전.** |
| S-07 | **문서.** |
"""

AGENTS = """- W-01 **폴더 = 앱 = 명령** — 요약
- W-02 **의존성 0** — 요약
- W-03 **내 PC 에서만** — 요약
- W-10 **디자인은 하나** — 요약
"""

DESIGN = """# works 디자인

## 01 원칙 일곱 가지

| # | 원칙 |
|---|---|
| 1 | **한 화면 = 한 모드** |
| 2 | **색 = 조작** |
"""

REGISTRY = """# works 대장

## 앱 대장

| 폴더 · 명령 | 이름 | 상태 | 포트 | 전역 단축키 |
|---|---|---|---|---|
{rows}

## 예외 대장

| 앱 | 조항 | 파일 | 내용 | 기한 |
|---|---|---|---|---|
{waivers}
"""

README = """<p>데모–1</p>
<sub>파이썬 3.8+ · 표준 라이브러리만 · 테스트 1</sub>
<p><a href="../README.md">explore ›</a></p>
<sub>화면 문법은 소형 하드웨어 계측기(Teenage Engineering 류)에서 영감을 받았고, 해당 회사와는 관련이 없습니다.</sub>
"""

INSTALL = """# 설치

## 0. 목표와 규칙
**[질문]** 물어본다.
## 9. 완료 보고
## 문제 해결
## 업데이트
## 제거
"""

MANUAL = """# 데모–1 매뉴얼

## 디자인

| # | 원칙 | 데모–1 에서 |
|---|---|---|
| 1 | **한 화면 = 한 모드** | 큰 숫자 |
| 2 | **색 = 조작** | 노브 |
"""

APP_PY = '''import json
import os

VERSION = "0.1.0"
NAVY, LIME, GRAY, INK = "#1F507A", "#6ABA23", "#A5AAAE", "#0b0b0b"


def serve():
    return ("127.0.0.1", 8775)


def outlook():
    import win32com.client  # 선택 기능: 함수 안에서
    return win32com.client
'''

TEST_PY = '''import unittest


class T(unittest.TestCase):
    def test_one(self):
        self.assertTrue(True)
'''

WORKFLOW = """name: demo-1
on:
  push:
    paths: ["demo-1/**", ".github/workflows/demo-1.yml"]
jobs:
  test:
    strategy:
      matrix:
        os: [windows-latest, ubuntu-22.04]
        python: ["3.8", "3.13"]
    runs-on: ${{ matrix.os }}
"""


def write(root, rel, text):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def make_repo(root, app="demo-1", rows=None, waivers="", **files):
    """규칙을 모두 지키는 앱 하나짜리 저장소. files 로 파일을 바꾸거나 더한다 (None = 지우기)"""
    base = {
        "RULES.md": RULES, "AGENTS.md": AGENTS, "docs/DESIGN.md": DESIGN,
        "docs/REGISTRY.md": REGISTRY.format(
            rows=rows or f"| `{app}` | 데모–1 | 운영 | 8775–8784 | Ctrl+Alt+K |", waivers=waivers),
        f"{app}/README.md": README, f"{app}/INSTALL.md": INSTALL, f"{app}/docs/MANUAL.md": MANUAL,
        f"{app}/{app}.py": APP_PY, f"{app}/tests/test_demo.py": TEST_PY,
        f"{app}/.gitignore": "config.json\n", f"{app}/.gitattributes": "* text=auto eol=lf\n",
        f".github/workflows/{app}.yml": WORKFLOW,
    }
    for k, v in files.items():
        base[k.replace("__", "/")] = v
    for rel, text in base.items():
        if text is not None:
            write(root, rel, text)
    return wc.Repo(root)


def rules_of(findings):
    return sorted({f.rule for f in findings})


class Base(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="works-check-")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)


class CleanRepo(Base):
    def test_conforming_app_has_no_findings(self):
        """규칙을 지키는 앱에서는 아무것도 잡지 않는다 (헛경고 0)"""
        repo = make_repo(self.root)
        findings, _ = wc.run_checks(repo, run_tests=True)
        self.assertEqual(findings, [], "\n".join(f"{f.rule} {f.path}:{f.line} {f.msg}" for f in findings))

    def test_main_prints_ok_last(self):
        make_repo(self.root)
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = wc.main(["--root", self.root, "--strict", "--no-tests"])
        self.assertEqual(code, 0)
        self.assertEqual(buf.getvalue().strip().splitlines()[-1], "결과: OK")


class Violations(Base):
    def test_each_rule_is_caught(self):
        bad_py = APP_PY + (
            'import requests\n'
            'RED = "#E03030"\n'
            'HOST = "0.0.0.0"\n'
            'KEY = "sk-' + "a1B2" * 6 + '"\n'
            'LAN = "http://10.20.30.40/v1"\n'
        )
        repo = make_repo(
            self.root,
            **{"demo-1/demo-1.py": bad_py,
               "demo-1/README.md": README.replace("해당 회사와는 관련이 없습니다", "").replace("테스트 1", "테스트 7")
               + '<a href="../other-2/README.md">형제</a>\n',
               "demo-1/INSTALL.md": "# 설치\n## 0. 규칙\n",
               "demo-1/docs/MANUAL.md": MANUAL.replace("색 = 조작", "팔레트") + "| 네이비 | #002341 |\n{{NAME}}\n",
               "other-2/README.md": "x", "demo-1/.gitattributes": None})
        findings, _ = wc.run_checks(repo, run_tests=True)
        got = {(f.rule, f.msg.split(" ")[0]) for f in findings}
        for rule in ("W-01", "W-02", "W-03", "W-04", "W-08", "W-10", "W-11", "W-12", "S-06", "S-07"):
            self.assertIn(rule, rules_of(findings), rule)
        self.assertTrue(any(f.rule == "W-11" and "7" in f.msg and "1" in f.msg for f in findings), got)
        self.assertTrue(any(f.rule == "W-10" and "#E03030" in f.msg for f in findings))
        self.assertTrue(any(f.rule == "W-10" and "'팔레트'" in f.msg for f in findings))
        self.assertTrue(any(f.rule == "W-02" and "requests" in f.msg for f in findings))
        self.assertFalse(any("win32com" in f.msg for f in findings), "함수 안 import 는 선택 기능")

    def test_missing_min_python_in_ci(self):
        repo = make_repo(self.root, **{".github/workflows/demo-1.yml": WORKFLOW.replace('"3.8", ', "")})
        findings, _ = wc.run_checks(repo, run_tests=False)
        self.assertEqual(rules_of(findings), ["W-11"])
        self.assertIn("3.8", findings[0].msg)

    def test_version_missing(self):
        repo = make_repo(self.root, **{"demo-1/demo-1.py": APP_PY.replace('VERSION = "0.1.0"', "")})
        findings, _ = wc.run_checks(repo, run_tests=False)
        self.assertEqual(rules_of(findings), ["S-02"])

    def test_registry_overlap_and_unregistered(self):
        rows = ("| `demo-1` | 데모–1 | 운영 | 8775–8784 | Ctrl+Alt+K |\n"
                "| `demo-2` | 데모–2 | 예정 | 8780–8789 | ctrl + alt + k |")
        repo = make_repo(self.root, rows=rows)
        write(self.root, "demo-3/README.md", "x")
        repo = wc.Repo(self.root)
        msgs = [f.msg for f in wc.check_registry(repo)]
        self.assertTrue(any("포트 대역이 겹칩니다" in m for m in msgs), msgs)
        self.assertTrue(any("전역 단축키가 같습니다" in m for m in msgs), msgs)
        self.assertTrue(any("등록되지 않은" in m for m in msgs), msgs)

    def test_agents_summary_must_match_rules(self):
        repo = make_repo(self.root, **{"AGENTS.md": AGENTS.replace("의존성 0", "의존성 없음")})
        findings, _ = wc.run_checks(repo, run_tests=False)
        self.assertEqual([(f.rule, f.path) for f in findings], [("RULES", "AGENTS.md")])

    def test_github_expression_is_not_a_placeholder(self):
        repo = make_repo(self.root)
        self.assertIn("${{ matrix.os }}", repo.text(".github/workflows/demo-1.yml"))
        self.assertEqual([f for f in wc.check_docs(repo) if "자리표시자" in f.msg], [])


class Waivers(Base):
    WAIVER = "| `demo-1` | W-10 | demo-1.py | 옛 색 변환표 | {due} |"

    def run_with(self, due, today):
        repo = make_repo(self.root, waivers=self.WAIVER.format(due=due),
                         **{"demo-1/demo-1.py": APP_PY + 'OLD = "#EC4899"\n'})
        findings, waivers = wc.run_checks(repo, run_tests=False)
        return wc.judge(findings, waivers, today)

    def test_waiver_covers_until_due(self):
        judged, unused, expired = self.run_with("2026-10-31", date(2026, 9, 26))
        self.assertEqual([(f.rule, w is not None, late) for f, w, late in judged], [("W-10", True, False)])
        self.assertEqual((unused, expired), ([], []))

    def test_expired_waiver_counts_again(self):
        judged, _, expired = self.run_with("2026-10-31", date(2026, 11, 1))
        self.assertEqual([late for _, _, late in judged], [True])
        self.assertEqual(len(expired), 1)

    def test_waiver_scope_is_per_file(self):
        repo = make_repo(self.root, waivers=self.WAIVER.format(due="영구"),
                         **{"demo-1/other.py": 'X = "#EC4899"\n'})
        judged, unused, _ = wc.judge(*wc.run_checks(repo, run_tests=False), date(2026, 9, 26))
        self.assertEqual([(f.path, w) for f, w, _ in judged], [("demo-1/other.py", None)])
        self.assertEqual(len(unused), 1, "걸린 것 없는 예외는 '지워도 됨'")

    def test_unchecked_rule_waiver_is_not_reported_unused(self):
        repo = make_repo(self.root, waivers="| `demo-1` | W-06 | * | 데이터 위치 | 영구 |")
        _, unused, _ = wc.judge(*wc.run_checks(repo, run_tests=False), date(2026, 9, 26))
        self.assertEqual(unused, [])

    def test_strict_exit_code(self):
        make_repo(self.root, **{"demo-1/demo-1.py": APP_PY + 'OLD = "#EC4899"\n'})
        with redirect_stdout(io.StringIO()) as buf:
            warn = wc.main(["--root", self.root, "--no-tests"])
            strict = wc.main(["--root", self.root, "--no-tests", "--strict"])
        lines = buf.getvalue().strip().splitlines()
        self.assertEqual((warn, strict), (0, 1))
        self.assertIn("결과: 확인 필요", lines)
        self.assertEqual(lines[-1], "결과: 점검 실패")


class Colors(unittest.TestCase):
    def test_palette_families(self):
        for hexc in ("002341", "1F507A", "75A1C7", "B8CEE0", "6ABA23", "2C4912", "95D85A", "A5AAAE", "F2F2F3", "0B0B0B"):
            rgb = tuple(int(hexc[i:i + 2], 16) for i in (0, 2, 4))
            self.assertTrue(wc.color_ok(*rgb)[0], hexc)
        for hexc in ("FF0000", "E03030", "FFA500", "EC4899", "8B5CF6", "FFD700"):
            rgb = tuple(int(hexc[i:i + 2], 16) for i in (0, 2, 4))
            self.assertFalse(wc.color_ok(*rgb)[0], hexc)

    def test_warm_console_colors(self):
        self.assertTrue(wc.PS_WARM_RE.search("Write-Host 'x' -ForegroundColor Red"))
        self.assertTrue(wc.PS_WARM_RE.search("Say 'ERR' 'msg' '' 'DarkYellow'"))
        self.assertFalse(wc.PS_WARM_RE.search("Say 'OK' 'msg' '' 'DarkGreen'"))
        self.assertTrue(wc.ANSI_WARM_RE.search(r'print("\x1b[31mERR")'))
        self.assertFalse(wc.ANSI_WARM_RE.search(r'print("\x1b[0m\x1b[1m")'))


if __name__ == "__main__":
    unittest.main()
