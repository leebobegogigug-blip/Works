#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
works_check.py - works 규칙 검사기 (정본은 RULES.md · 표준 라이브러리만 · Python 3.8+)

  python tools/works_check.py             모든 앱 검사. 위반이 있어도 종료 코드 0 (경고 모드)
  python tools/works_check.py --strict    위반이 있으면 종료 코드 1 (차단 모드)
  python tools/works_check.py --no-tests  테스트 수 확인(테스트 불러오기)을 건너뜀

[검사하는 것] 검사기가 못 보는 조항(W-05 · W-06 · W-07 · W-09)은 리뷰에서 본다
  W-01 필수 파일 · 앱 워크플로 · 대장의 공개 명령 없이 다른 앱을 가리키는 코드 · 공개 명령이 코드와 MANUAL 에 있는지
  W-02 실행 코드가 불러오자마자 import 하는 표준 라이브러리 밖 모듈 (Python 3.10+ 에서만)
  W-03 0.0.0.0 바인딩 · 웹 UI 의 외부 리소스(CDN · 웹 폰트)
  W-04 키 · 토큰처럼 보이는 문자열 · 비밀 값을 받는 명령줄 옵션(--password · [string]$Token 등)
  W-08 INSTALL.md 필수 절 · [질문] 표시
  W-10 네이비 · 라임 밖의 유채색 · 빨강 계열 콘솔 색 · 옮겨 적은 디자인 원칙 · 팔레트 표
  W-11 워크플로의 OS · 경로 필터 · 약속한 최소 Python · 문서의 테스트 수 · 없는 워크플로 언급
  W-12 영감 고지문 · 내장 폰트 라이선스 · 사설 IP 주소
  S-02 VERSION 상수   S-06 대장 등록 · 포트 대역 · 전역 단축키 겹침   S-09 LLM 설정 키가 docs/SPEC-llm.md 와 같은지
  S-07 형제 앱 직접 링크 · 다른 앱과 같은 이미지 · 문서 이미지 3 MB · 남은 {{자리표시자}} · 깨진 상대 링크
  RULES AGENTS.md 요약 · 예외 대장이 RULES.md 와 맞는지

[예외 대장] docs/REGISTRY.md 에 적힌 위반은 '예외' 로만 보이고 세지 않는다.
  기한이 지나면 다시 위반으로 센다 · 걸리는 것이 없는 줄은 '지워도 됨' 으로 알려 준다.

[출력] 마지막 줄은 결과: OK · 결과: 확인 필요(경고 모드의 위반) · 결과: 점검 실패(--strict 의 위반)
  GitHub Actions 안에서는 위반마다 ::warning 주석도 찍는다.
"""
import argparse
import ast
import colorsys
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import date
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_RE = re.compile(r"^[a-z][a-z0-9]*-\d+$")          # 앱 폴더 이름 (RULES.md › W-01)
CODE_EXT = (".py", ".ps1", ".cmd", ".bat", ".html", ".js", ".css")
TEXT_EXT = CODE_EXT + (".md", ".json", ".yml", ".yaml", ".txt", ".toml", ".ini", ".cfg")
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp")
FONT_EXT = (".woff", ".woff2", ".otf", ".ttf")
DEV_DIRS = ("tests", "tools")                          # W-02: 개발 도구는 외부 패키지를 써도 된다
REQUIRED = ("README.md", "INSTALL.md", "docs/MANUAL.md", ".gitignore", ".gitattributes")
INSTALL_SECTIONS = ("규칙", "보고", "문제 해결", "업데이트", "제거")
DISCLAIMER = "해당 회사와는 관련이 없습니다"
IMAGE_BUDGET = 3 * 1024 * 1024                         # S-07: 앱 문서 이미지
UNCHECKED = {"W-05", "W-06", "W-07", "W-09"}           # 검사기가 못 보는 조항 → 예외가 안 걸려도 '지워도 됨' 이 아님
NAVY_HUE, LIME_HUE, MIN_CHROMA = (190, 230), (75, 110), 0.10   # docs/DESIGN.md › 02 색


class Finding(NamedTuple):
    rule: str        # W-01 · S-07 · RULES
    app: str         # 앱 폴더 이름, "" 이면 저장소 전체
    path: str        # 저장소 기준 경로 (/ 구분)
    msg: str
    line: int = 0


class Waiver(NamedTuple):
    """예외 대장의 한 줄"""
    app: str
    rule: str
    files: Tuple[str, ...]   # ("*",) = 앱 폴더 전체
    note: str
    due: Optional[date]      # None = 기한 없음
    due_text: str
    line: int


# ─────────────────────────────────────────────────────────────── 저장소 읽기

class Repo:
    def __init__(self, root: str = ROOT):
        self.root = root
        self.files = self._list_files()
        self.apps = sorted(d for d in os.listdir(root)
                           if APP_RE.match(d) and os.path.isdir(os.path.join(root, d)))
        self.notes: List[str] = []           # 결과에는 안 세는 안내 (건너뛴 검사 등)
        self._text: Dict[str, str] = {}

    def _list_files(self) -> List[str]:
        """git 이 추적하는 파일 + 새로 만든(무시되지 않은) 파일. git 이 없으면 폴더를 훑는다"""
        try:
            out = subprocess.run(["git", "-C", self.root, "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                                 capture_output=True, check=True).stdout
            files = {f for f in out.decode("utf-8").split("\0") if f}
        except (OSError, subprocess.CalledProcessError):
            files = set()
            for d, subdirs, names in os.walk(self.root):
                subdirs[:] = [s for s in subdirs if s not in (".git", "__pycache__")]
                for n in names:
                    files.add(os.path.relpath(os.path.join(d, n), self.root).replace(os.sep, "/"))
        return sorted(f for f in files if os.path.isfile(self.abs(f)))

    def abs(self, rel: str) -> str:
        return os.path.join(self.root, *rel.split("/"))

    def exists(self, rel: str) -> bool:
        return os.path.exists(self.abs(rel))

    def text(self, rel: str) -> str:
        if rel not in self._text:
            try:
                with open(self.abs(rel), "r", encoding="utf-8-sig", errors="replace") as f:
                    self._text[rel] = f.read()
            except OSError:
                self._text[rel] = ""
        return self._text[rel]

    def app_files(self, app: str, ext: Tuple[str, ...] = (), dev: bool = True) -> List[str]:
        """앱 폴더의 파일. dev=False 면 tests/ · tools/ 를 뺀다"""
        out = []
        for f in self.files:
            if not f.startswith(app + "/"):
                continue
            if not dev and f.split("/")[1] in DEV_DIRS:
                continue
            if ext and not f.lower().endswith(ext):
                continue
            out.append(f)
        return out

    def app_of(self, rel: str) -> str:
        head = rel.split("/")[0]
        return head if head in self.apps else ""


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def headings_before(text: str) -> List[Tuple[int, str]]:
    """(줄 번호, 제목) — 마크다운 제목만"""
    return [(i, ln.lstrip("#").strip()) for i, ln in enumerate(text.splitlines(), 1) if ln.startswith("#")]


def section_rows(text: str, heading: str) -> List[Tuple[int, List[str]]]:
    """'## heading' 절 안의 표 줄 → (줄 번호, 칸 목록). 구분 줄(|---|)은 뺀다"""
    rows, inside = [], False
    for i, ln in enumerate(text.splitlines(), 1):
        if ln.startswith("## "):
            inside = ln[3:].strip() == heading
            continue
        if inside and ln.strip().startswith("|") and not re.match(r"^\|[\s:|-]+\|$", ln.strip()):
            rows.append((i, [c.strip() for c in ln.strip().strip("|").split("|")]))
    return rows


def unquote(cell: str) -> str:
    return cell.strip().strip("`").strip()


# ─────────────────────────────────────────────────────────────── W-01 폴더 = 앱 = 명령

def check_structure(repo: Repo) -> List[Finding]:
    out = []
    for app in repo.apps:
        for rel in REQUIRED:
            if not repo.exists(f"{app}/{rel}"):
                out.append(Finding("W-01", app, f"{app}/{rel}", f"{rel} 가 없습니다"))
        tests = [f for f in repo.app_files(app, (".py",)) if f.startswith(f"{app}/tests/")
                 and os.path.basename(f).startswith("test")]
        if not tests:
            out.append(Finding("W-01", app, f"{app}/tests", "tests/ 에 test*.py 가 없습니다"))
        wf = f".github/workflows/{app}.yml"
        if not repo.exists(wf):
            out.append(Finding("W-01", app, wf, "앱 워크플로가 없습니다 (docs/templates/workflow.yml)"))
    return out


def py_imports(tree: ast.AST, top_only: bool) -> List[Tuple[str, int]]:
    """(모듈 첫 이름, 줄). top_only 면 불러오자마자 실행되는 것만 — 함수 안 · try 안은 선택 기능으로 본다"""
    if not top_only:
        found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found += [(a.name.split(".")[0], node.lineno) for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                found.append((node.module.split(".")[0], node.lineno))
        return found
    found: List[Tuple[str, int]] = []

    def walk(body: List[ast.stmt]) -> None:
        for node in body:
            if isinstance(node, ast.Import):
                found.extend((a.name.split(".")[0], node.lineno) for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    found.append((node.module.split(".")[0], node.lineno))
            elif isinstance(node, (ast.If, ast.With)):
                walk(node.body)
                walk(getattr(node, "orelse", []))
            elif isinstance(node, ast.ClassDef):
                walk(node.body)

    walk(getattr(tree, "body", []))
    return found


def parse_py(repo: Repo, rel: str) -> Optional[ast.AST]:
    try:
        return ast.parse(repo.text(rel), filename=rel)
    except (SyntaxError, ValueError):
        return None


def modules_of(repo: Repo, app: str) -> Set[str]:
    return {os.path.splitext(os.path.basename(f))[0] for f in repo.app_files(app, (".py",))}


def public_commands(repo: Repo) -> List[Dict[str, object]]:
    """대장의 공개 명령 표 → [{app, command, format, users, line}]"""
    out = []
    for ln, cells in section_rows(repo.text("docs/REGISTRY.md"), "공개 명령")[1:]:
        if len(cells) < 5:
            continue
        users = [unquote(u) for u in re.split(r"[,·]", cells[4]) if unquote(u) not in ("", "—", "-", "없음")]
        out.append({"app": unquote(cells[0]), "command": unquote(cells[1]), "format": cells[3].strip(),
                    "users": users, "line": ln})
    return out


def check_cross_refs(repo: Repo) -> List[Finding]:
    """다른 앱의 이름 · 경로가 코드에 나오면 대장의 공개 명령으로 이어진 사이여야 한다. 다른 앱 모듈 import 는 언제나 위반"""
    out = []
    mods = {app: modules_of(repo, app) for app in repo.apps}
    linked = {(str(c["app"]), str(u)) for c in public_commands(repo) for u in c["users"]}   # (내주는 앱, 쓰는 앱)
    for app in repo.apps:
        others = [o for o in repo.apps if o != app]
        foreign = {m: o for o in others for m in mods[o]} if others else {}
        for rel in repo.app_files(app, CODE_EXT):
            text = repo.text(rel)
            for o in others:
                if (o, app) in linked:
                    continue
                m = re.search(r"(?<![\w-])" + re.escape(o) + r"(?![\w-])", text)
                if m:
                    out.append(Finding("W-01", app, rel, f"다른 앱({o})을 가리킵니다 — 앱끼리는 대장에 올린 공개 명령으로만",
                                       line_of(text, m.start())))
            if rel.endswith(".py") and foreign:
                tree = parse_py(repo, rel)
                for name, ln in (py_imports(tree, top_only=False) if tree else []):
                    if name in foreign and name not in mods[app]:
                        out.append(Finding("W-01", app, rel, f"다른 앱({foreign[name]})의 모듈 {name} 을 import 합니다", ln))
    return out


def check_public_commands(repo: Repo) -> List[Finding]:
    """공개 명령은 내주는 앱의 코드와 MANUAL 에 실제로 있어야 하고, 형식 버전 · 쓰는 앱이 분명해야 한다"""
    out, reg = [], "docs/REGISTRY.md"
    registered = {str(r["app"]) for r in registry_apps(repo)}
    for c in public_commands(repo):
        app, ln = str(c["app"]), int(c["line"])
        if app not in repo.apps:
            out.append(Finding("W-01", "", reg, f"공개 명령을 내주는 앱 폴더가 없습니다: {app}", ln))
            continue
        flags = re.findall(r"--[a-z][\w-]*", str(c["command"]))
        manual = repo.text(f"{app}/docs/MANUAL.md")
        code = "\n".join(repo.text(f) for f in repo.app_files(app, (".py", ".ps1"), dev=False))
        for where, text in (("MANUAL", manual), ("코드", code)):
            missing = [f for f in flags if f not in text]
            if missing:
                out.append(Finding("W-01", app, reg, f"공개 명령 {' '.join(missing)} 가 {where}에 없습니다", ln))
        if not re.fullmatch(r"\d+", str(c["format"])):
            out.append(Finding("W-01", app, reg, f"공개 명령의 형식 버전이 숫자가 아닙니다: {c['format']}", ln))
        for u in c["users"]:
            if u not in registered:
                out.append(Finding("W-01", app, reg, f"공개 명령을 쓰는 앱 {u} 가 앱 대장에 없습니다", ln))
    return out


# ─────────────────────────────────────────────────────────────── W-02 의존성 0

def check_imports(repo: Repo) -> List[Finding]:
    stdlib = set(getattr(sys, "stdlib_module_names", ()))
    if not stdlib:
        repo.notes.append("W-02 import 검사는 Python 3.10+ 에서만 합니다 (지금 %s)" % sys.version.split()[0])
        return []
    stdlib.add("__future__")
    out = []
    for app in repo.apps:
        local = modules_of(repo, app)
        for rel in repo.app_files(app, (".py",), dev=False):
            tree = parse_py(repo, rel)
            if tree is None:
                out.append(Finding("W-02", app, rel, "파이썬 문법을 읽지 못했습니다"))
                continue
            seen = set()
            for name, ln in py_imports(tree, top_only=True):
                if name in stdlib or name in local or name in seen:
                    continue
                seen.add(name)
                out.append(Finding("W-02", app, rel, f"표준 라이브러리 밖 모듈 {name} 을 바로 import 합니다 "
                                                     "(선택 기능이면 함수 안에서)", ln))
    return out


# ─────────────────────────────────────────────────────────────── W-03 내 PC 에서만 · W-04 비밀

BIND_ALL_RE = re.compile(r"[\"']0\.0\.0\.0[\"']")
EXT_RESOURCE_RE = re.compile(
    r"<(?:script|link|img|iframe)\b[^>]*?\b(?:src|href)\s*=\s*[\"']?(?:https?:)?//"
    r"|(?:@import\s+(?:url\()?|url\()\s*[\"']?(?:https?:)?//", re.I)
SECRET_RES = (
    ("OpenAI 식 키", re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}")),
    ("GitHub 토큰", re.compile(r"\b(?:ghp|gho|ghs|ghu)_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{30,}")),
    ("AWS 키", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Slack 토큰", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("개인 키", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
)


def check_network(repo: Repo) -> List[Finding]:
    out = []
    for app in repo.apps:
        for rel in repo.app_files(app, CODE_EXT, dev=False):
            text = repo.text(rel)
            m = BIND_ALL_RE.search(text)
            if m:
                out.append(Finding("W-03", app, rel, "0.0.0.0 — 127.0.0.1 에만 바인딩합니다", line_of(text, m.start())))
            if rel.endswith((".html", ".js", ".css", ".py")):
                m = EXT_RESOURCE_RE.search(text)
                if m:
                    out.append(Finding("W-03", app, rel, "외부 리소스(CDN · 웹 폰트)를 불러옵니다 — 내장하세요",
                                       line_of(text, m.start())))
    return out


SECRET_OPTION_RES = (
    (".py", re.compile(r"add_argument\(\s*[\"']--(?:\w+[-_])*(?:password|passwd|api[-_]?key|apikey|secret|token)[\"']", re.I)),
    (".ps1", re.compile(r"\[(?:string|securestring)\]\s*\$\w*(?:password|passwd|apikey|secret|token)\b", re.I)),
)


def check_secrets(repo: Repo) -> List[Finding]:
    out = []
    for app in repo.apps:     # 비밀 값을 명령줄로 받는 옵션 — 보안 솔루션 로그 · 작업 관리자에 남는다
        for rel in repo.app_files(app, (".py", ".ps1"), dev=False):
            text = repo.text(rel)
            for ext, rx in SECRET_OPTION_RES:
                m = rx.search(text) if rel.endswith(ext) else None
                if m:
                    out.append(Finding("W-04", app, rel, "비밀 값을 명령줄 옵션으로 받습니다 → 환경 변수 · 파일로 받으세요",
                                       line_of(text, m.start())))
    for rel in repo.files:
        if not rel.lower().endswith(TEXT_EXT) and "." in os.path.basename(rel):
            continue
        text = repo.text(rel)
        for what, rx in SECRET_RES:
            m = rx.search(text)
            if m:
                out.append(Finding("W-04", repo.app_of(rel), rel, f"{what}처럼 보이는 문자열 — 값은 커밋하지 않습니다",
                                   line_of(text, m.start())))
    return out


# ─────────────────────────────────────────────────────────────── W-08 설치

def check_install(repo: Repo) -> List[Finding]:
    out = []
    for app in repo.apps:
        rel = f"{app}/INSTALL.md"
        if not repo.exists(rel):
            continue
        text = repo.text(rel)
        heads = [h for _, h in headings_before(text)]
        missing = [s for s in INSTALL_SECTIONS if not any(s in h for h in heads)]
        if "[질문]" not in text:
            missing.append("[질문] 표시")
        if missing:
            out.append(Finding("W-08", app, rel, "INSTALL.md 에 없는 것: " + " · ".join(missing)))
    return out


# ─────────────────────────────────────────────────────────────── W-10 디자인

HEX_RE = re.compile(r"(?<![\w&#])#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})(?![0-9A-Za-z])")
RGB_RE = re.compile(r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})")
ANSI_WARM_RE = re.compile(r"(?:\\x1b|\\033|\\e)\[(?:\d+;)*(?:3[135]|9[135]|4[135]|10[135])m")
PS_WARM_RE = re.compile(r"['\"](?:Dark)?(?:Red|Yellow|Magenta)['\"]|(?:Fore|Back)groundColor\s+(?:Dark)?(?:Red|Yellow|Magenta)\b")
PRINCIPLE_ROW_RE = re.compile(r"^\|\s*([1-7])\s*\|\s*\*\*(.+?)\*\*", re.M)
HEX_TABLE_RE = re.compile(r"^\s*\|.*#[0-9A-Fa-f]{6}\b", re.M)


def color_ok(r: int, g: int, b: int) -> Tuple[bool, int]:
    """(허용?, 색상각). 무채색이거나 네이비 · 라임 계열이면 허용"""
    hue = int(round(colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)[0] * 360))
    if (max(r, g, b) - min(r, g, b)) / 255 < MIN_CHROMA:
        return True, hue
    return NAVY_HUE[0] <= hue <= NAVY_HUE[1] or LIME_HUE[0] <= hue <= LIME_HUE[1], hue


def off_palette(text: str) -> List[Tuple[str, int, int]]:
    """(색, 색상각, 처음 나온 줄) — 네이비 · 라임 밖의 유채색"""
    found: Dict[str, Tuple[int, int]] = {}
    for m in HEX_RE.finditer(text):
        h = m.group(1)
        h = "".join(c * 2 for c in h) if len(h) == 3 else h
        rgb = (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
        ok, hue = color_ok(*rgb)
        if not ok:
            found.setdefault("#" + h.upper(), (hue, line_of(text, m.start())))
    for m in RGB_RE.finditer(text):
        rgb = tuple(min(255, int(x)) for x in m.groups())
        ok, hue = color_ok(*rgb)
        if not ok:
            found.setdefault("rgb(%d,%d,%d)" % rgb, (hue, line_of(text, m.start())))
    return sorted(((c, hu, ln) for c, (hu, ln) in found.items()), key=lambda x: x[2])


def norm_name(s: str) -> str:
    return re.sub(r"[\s`]+", " ", s).strip(" .")


def design_principles(repo: Repo) -> Dict[str, str]:
    return {n: norm_name(name) for n, name in PRINCIPLE_ROW_RE.findall(repo.text("docs/DESIGN.md"))}


def check_design(repo: Repo) -> List[Finding]:
    out = []
    canon = design_principles(repo)
    for app in repo.apps:
        for rel in repo.app_files(app, CODE_EXT, dev=False):
            text = repo.text(rel)
            bad = off_palette(text)
            if bad:
                shown = " ".join(f"{c}({hu}°)" for c, hu, _ in bad[:4]) + (f" 외 {len(bad) - 4}개" if len(bad) > 4 else "")
                out.append(Finding("W-10", app, rel, f"네이비 · 라임 밖의 유채색: {shown}", bad[0][2]))
            warm = (PS_WARM_RE if rel.endswith(".ps1") else ANSI_WARM_RE).search(text)
            if warm:
                out.append(Finding("W-10", app, rel, f"빨강 · 노랑 · 자홍 콘솔 색: {warm.group(0)}", line_of(text, warm.start())))
        for rel in repo.app_files(app, (".md",)):
            text = repo.text(rel)
            m = HEX_TABLE_RE.search(text)
            if m:
                out.append(Finding("W-10", app, rel, "팔레트 값을 표로 옮겨 적었습니다 → docs/DESIGN.md 링크",
                                   line_of(text, m.start())))
            wrong, first = [], 0
            heads = headings_before(text)
            for m in PRINCIPLE_ROW_RE.finditer(text):
                ln = line_of(text, m.start())
                head = next((h for i, h in reversed(heads) if i < ln), "")
                if "디자인" not in head and "design" not in head.lower():
                    continue
                n, name = m.group(1), norm_name(m.group(2))
                if canon and canon.get(n) != name:
                    wrong.append(f"{n} '{name}' (정본 '{canon.get(n, '없음')}')")
                    first = first or ln
            if wrong:
                out.append(Finding("W-10", app, rel, "디자인 원칙 이름이 정본과 다릅니다: " + " · ".join(wrong[:3])
                                   + (f" 외 {len(wrong) - 3}개" if len(wrong) > 3 else ""), first))
    return out


# ─────────────────────────────────────────────────────────────── W-11 CI

MIN_PY_RE = re.compile(r"(?:Python|파이썬)\s*3\.(\d+)\s*\+")
MATRIX_PY_RE = re.compile(r"python(?:-version)?\s*:\s*\[([^\]]*)\]")
WF_REF_RE = re.compile(r"\.github/workflows/([\w.\-]+\.ya?ml)")
TEST_CLAIM_RE = re.compile(r"(?:테스트|unittest|통합)\s*(\d+)(?!\d|\.\d)")


def count_tests(repo: Repo, app: str) -> Tuple[Optional[int], str]:
    """(테스트 수, 오류). unittest 가 찾는 그대로 센다 — 앱 코드를 불러오므로 별도 프로세스에서"""
    code = ("import json, unittest\n"
            "l = unittest.TestLoader(); s = l.discover('tests')\n"
            "print(json.dumps({'count': s.countTestCases(), 'errors': len(getattr(l, 'errors', []))}))")
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
    try:
        p = subprocess.run([sys.executable, "-c", code], cwd=repo.abs(app), capture_output=True, timeout=300,
                           env=env)
        res = json.loads(p.stdout.decode("utf-8", "replace").strip().splitlines()[-1])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError) as e:
        return None, f"테스트를 불러오지 못했습니다 ({e.__class__.__name__})"
    if res["errors"]:
        return None, f"테스트 {res['errors']}개를 불러오지 못했습니다"
    return int(res["count"]), ""


def check_ci(repo: Repo, run_tests: bool = True) -> List[Finding]:
    out = []
    for app in repo.apps:
        wf = f".github/workflows/{app}.yml"
        if repo.exists(wf):
            text = repo.text(wf)
            if f"{app}/**" not in text:
                out.append(Finding("W-11", app, wf, f"paths 에 {app}/** 가 없습니다 (자기 폴더만 볼 때 실행)"))
            if "windows" not in text or "ubuntu" not in text:
                out.append(Finding("W-11", app, wf, "Windows 와 Ubuntu 에서 모두 돌려야 합니다"))
            versions = [v.strip().strip("\"'") for grp in MATRIX_PY_RE.findall(text) for v in grp.split(",") if v.strip()]
            m = MIN_PY_RE.search(repo.text(f"{app}/README.md"))
            if m and f"3.{m.group(1)}" not in versions:
                out.append(Finding("W-11", app, wf, f"README 가 약속한 최소 Python 3.{m.group(1)} 이 CI 에 없습니다 "
                                                   f"(있는 것: {', '.join(versions) or '없음'})"))
        docs = repo.app_files(app, (".md",))
        for rel in docs:
            text = repo.text(rel)
            for m in WF_REF_RE.finditer(text):
                if not repo.exists(".github/workflows/" + m.group(1)):
                    out.append(Finding("W-11", app, rel, f"없는 워크플로를 가리킵니다: {m.group(0)}", line_of(text, m.start())))
        if not run_tests:
            continue
        claims = [(rel, int(m.group(1)), line_of(repo.text(rel), m.start()))
                  for rel in docs for m in TEST_CLAIM_RE.finditer(repo.text(rel))]
        if not claims:
            continue
        count, err = count_tests(repo, app)
        if err:
            out.append(Finding("W-11", app, f"{app}/tests", err))
            continue
        for rel, n, ln in claims:
            if n != count:
                out.append(Finding("W-11", app, rel, f"테스트 수를 {n} 이라고 적었지만 실제는 {count} 입니다", ln))
    if not run_tests:
        repo.notes.append("테스트 수 확인을 건너뛰었습니다 (--no-tests)")
    return out


# ─────────────────────────────────────────────────────────────── W-12 공개 저장소

PRIVATE_IP_RE = re.compile(r"(?<![\d.])(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}(?!\d|\.\d)")


def check_public(repo: Repo) -> List[Finding]:
    out = []
    for app in repo.apps:
        readme = f"{app}/README.md"
        if repo.exists(readme) and DISCLAIMER not in repo.text(readme):
            out.append(Finding("W-12", app, readme, "영감 고지문이 없습니다 (RULES.md › W-12)"))
        for font in repo.app_files(app, FONT_EXT):
            d = os.path.dirname(font)
            near = [f for f in repo.files if os.path.dirname(f) in (d, app)
                    and re.search(r"(?:OFL|LICEN[CS]E|COPYING)", os.path.basename(f), re.I)]
            if not near:
                out.append(Finding("W-12", app, font, "내장 폰트 옆에 라이선스 파일이 없습니다"))
        for rel in repo.app_files(app, TEXT_EXT):
            text = repo.text(rel)
            m = PRIVATE_IP_RE.search(text)
            if m:
                out.append(Finding("W-12", app, rel, f"사설 IP 주소 {m.group(0)} — 사내 주소는 커밋하지 않습니다",
                                   line_of(text, m.start())))
    return out


# ─────────────────────────────────────────────────────────────── S-02 버전 · S-06 대장 · S-07 문서

VERSION_RE = re.compile(r"^\s*(?:VERSION|\$Version)\s*=\s*[\"']\d+\.\d+\.\d+[\"']", re.M)
PLACEHOLDER_RE = re.compile(r"(?<!\$)\{\{[A-Z_]+\}\}")
LINK_RE = re.compile(r"(?:src|srcset|href)\s*=\s*\"([^\"]+)\"|\]\(([^)\s]+)\)")


def broken_links(repo: Repo, rel: str) -> List[Tuple[str, int]]:
    """문서의 상대 링크 · 이미지 중 없는 파일 → (대상, 줄). 주소 · #앵커만 있는 링크는 보지 않는다"""
    text, out = repo.text(rel), []
    for m in LINK_RE.finditer(text):
        for target in (m.group(1) or m.group(2)).split(","):   # srcset="a.png 1x, b.png 2x"
            target = target.strip().split(" ")[0].split("#")[0]
            if not target or re.match(r"^[a-z][a-z0-9+.\-]*:", target, re.I) or target.startswith("//"):
                continue
            path = os.path.normpath(os.path.join(os.path.dirname(repo.abs(rel)), target.replace("%20", " ")))
            if not os.path.exists(path):
                out.append((target, line_of(text, m.start())))
    return out


def llm_spec_keys(repo: Repo) -> Tuple[Set[str], Set[str]]:
    """(꼭 있어야 하는 키, 있어도 되는 키) — docs/SPEC-llm.md › 01 설정 키 표에서 읽는다 ('…앱만' 은 선택)"""
    need, maybe = set(), set()
    for _, cells in section_rows(repo.text("docs/SPEC-llm.md"), "01 설정 키")[1:]:
        if len(cells) >= 3 and cells[0].startswith("`"):
            (maybe if "앱만" in cells[2] else need).add(unquote(cells[0]))
    return need, maybe


def check_llm_spec(repo: Repo) -> List[Finding]:
    need, maybe = llm_spec_keys(repo)
    if not need:
        return []
    out = []
    for app in repo.apps:
        rel = f"{app}/config.example.json"
        uses_llm = any("chat/completions" in repo.text(f) for f in repo.app_files(app, (".py",), dev=False))
        llm = None
        if repo.exists(rel):
            try:
                data = json.loads(repo.text(rel))
                llm = data.get("llm") if isinstance(data, dict) else None
            except ValueError:
                out.append(Finding("S-09", app, rel, "config.example.json 이 JSON 이 아닙니다"))
                continue
        if not isinstance(llm, dict):
            if uses_llm:
                out.append(Finding("S-09", app, rel, "사내 LLM 을 부르는데 config.example.json 에 llm 설정이 없습니다"))
            continue
        missing = sorted(need - set(llm))
        unknown = sorted(set(llm) - need - maybe)
        if missing or unknown:
            out.append(Finding("S-09", app, rel, "LLM 설정 키가 docs/SPEC-llm.md 와 다릅니다: "
                               + " · ".join((["빠짐 " + ", ".join(missing)] if missing else [])
                                            + (["모름 " + ", ".join(unknown)] if unknown else []))))
    return out


def check_version(repo: Repo) -> List[Finding]:
    out = []
    for app in repo.apps:
        if not any(VERSION_RE.search(repo.text(f)) for f in repo.app_files(app, (".py", ".ps1"), dev=False)):
            out.append(Finding("S-02", app, app, 'VERSION = "x.y.z" 상수가 없습니다'))
    return out


def port_range(cell: str) -> Optional[Tuple[int, int]]:
    m = re.search(r"(\d+)\s*[–\-~]\s*(\d+)", cell) or re.search(r"(\d{2,5})", cell)
    if not m:
        return None
    lo = int(m.group(1))
    return lo, int(m.group(2)) if m.lastindex and m.lastindex > 1 else lo


def registry_apps(repo: Repo) -> List[Dict[str, object]]:
    """앱 대장 → [{app, state, ports, hotkey, line}]. 칸은 제목 줄의 이름으로 찾는다"""
    rows = section_rows(repo.text("docs/REGISTRY.md"), "앱 대장")
    if not rows:
        return []
    head = rows[0][1]

    def col(key: str) -> int:
        return next((i for i, h in enumerate(head) if key in h), -1)

    ci, si, pi, hi = col("폴더"), col("상태"), col("포트"), col("단축키")
    out = []
    for ln, cells in rows[1:]:
        if ci < 0 or ci >= len(cells):
            continue
        get = (lambda i: cells[i] if 0 <= i < len(cells) else "")
        hk = re.sub(r"\s+", "", get(hi)).lower()
        out.append({"app": unquote(get(ci)), "state": get(si), "ports": port_range(get(pi)),
                    "hotkey": "" if hk in ("", "—", "-", "없음") else hk, "line": ln})
    return out


def check_registry(repo: Repo) -> List[Finding]:
    reg_path = "docs/REGISTRY.md"
    if not repo.exists(reg_path):
        return [Finding("S-06", "", reg_path, "대장이 없습니다")]
    out = []
    reg = registry_apps(repo)
    names = {str(r["app"]) for r in reg}
    for app in repo.apps:
        if app not in names:
            out.append(Finding("S-06", app, reg_path, "대장에 등록되지 않은 앱입니다"))
    for r in reg:
        if "운영" in str(r["state"]) and r["app"] not in repo.apps:
            out.append(Finding("S-06", "", reg_path, f"대장에는 운영인데 폴더가 없습니다: {r['app']}", int(r["line"])))
        if "예정" in str(r["state"]) and r["app"] in repo.apps:
            out.append(Finding("S-06", r["app"], reg_path, f"폴더가 생겼는데 대장에는 아직 예정입니다 → 운영: {r['app']}",
                               int(r["line"])))
    for i, a in enumerate(reg):
        for b in reg[i + 1:]:
            pa, pb = a["ports"], b["ports"]
            if pa and pb and pa[0] <= pb[1] and pb[0] <= pa[1]:
                out.append(Finding("S-06", "", reg_path, f"포트 대역이 겹칩니다: {a['app']} {pa[0]}–{pa[1]} · "
                                                         f"{b['app']} {pb[0]}–{pb[1]}", int(b["line"])))
            if a["hotkey"] and a["hotkey"] == b["hotkey"]:
                out.append(Finding("S-06", "", reg_path, f"전역 단축키가 같습니다: {a['app']} · {b['app']} ({a['hotkey']})",
                                   int(b["line"])))
    return out


def check_docs(repo: Repo) -> List[Finding]:
    out = []
    hashes: Dict[str, Set[str]] = {}          # 이미지 내용 → 그 이미지를 가진 곳 (앱 이름 또는 "works")
    where: Dict[Tuple[str, str], str] = {}    # (앱, 내용) → 파일
    for rel in repo.files:
        if rel.lower().endswith(IMAGE_EXT):
            owner = repo.app_of(rel) or "works"
            with open(repo.abs(rel), "rb") as f:
                h = hashlib.sha1(f.read()).hexdigest()
            hashes.setdefault(h, set()).add(owner)
            where.setdefault((owner, h), rel)
    for app in repo.apps:
        others = [o for o in repo.apps if o != app]
        for rel in repo.app_files(app, (".md",)):
            text = repo.text(rel)
            hits = [(o, m) for o in others for m in [re.search(r"\.\./(?:\.\./)*" + re.escape(o) + r"/", text)] if m]
            if hits:
                out.append(Finding("S-07", app, rel, "형제 앱으로 직접 링크합니다 (" + " · ".join(o for o, _ in hits)
                                   + ") → 루트 README 만 링크", line_of(text, hits[0][1].start())))
        dup = sorted(where[(app, h)] for h, owners in hashes.items() if app in owners and len(owners) > 1)
        if dup:
            out.append(Finding("S-07", app, dup[0], f"다른 앱 · 루트와 같은 이미지 {len(dup)}개 → 루트 docs/page/ 에 하나만"))
        size = sum(os.path.getsize(repo.abs(f)) for f in repo.app_files(app, IMAGE_EXT) if f.startswith(f"{app}/docs/"))
        if size > IMAGE_BUDGET:
            out.append(Finding("S-07", app, f"{app}/docs", f"문서 이미지 {size / 1048576:.1f} MB — 앱당 "
                                                          f"{IMAGE_BUDGET // 1048576} MB 까지"))
        for rel in repo.app_files(app, TEXT_EXT) + [f".github/workflows/{app}.yml"]:
            text = repo.text(rel) if repo.exists(rel) else ""
            m = PLACEHOLDER_RE.search(text)
            if m:
                out.append(Finding("S-07", app, rel, f"뼈대의 자리표시자가 남았습니다: {m.group(0)}", line_of(text, m.start())))
    for rel in repo.files:      # 뼈대(docs/templates/)의 링크는 앱 폴더에 복사된 뒤를 기준으로 적혀 있어서 뺀다
        if rel.endswith(".md") and not rel.startswith("docs/templates/"):
            for target, ln in broken_links(repo, rel):
                out.append(Finding("S-07", repo.app_of(rel), rel, f"없는 파일을 가리킵니다: {target}", ln))
    return out


# ─────────────────────────────────────────────────────────────── RULES.md · AGENTS.md · 예외 대장

def rule_ids(repo: Repo) -> Dict[str, str]:
    """RULES.md 의 조항 번호 → 제목 (규약은 제목 없이)"""
    text = repo.text("RULES.md")
    ids = {m.group(1): m.group(2).strip() for m in re.finditer(r"^### (W-\d\d) (.+)$", text, re.M)}
    ids.update({m.group(1): "" for m in re.finditer(r"^\| (S-\d\d) \|", text, re.M)})
    return ids


def load_waivers(repo: Repo) -> List[Waiver]:
    out = []
    for ln, cells in section_rows(repo.text("docs/REGISTRY.md"), "예외 대장")[1:]:
        if len(cells) < 5:
            continue
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", cells[4])
        due = date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None
        files = tuple(unquote(f) for f in cells[2].split(",") if f.strip()) or ("*",)
        out.append(Waiver(unquote(cells[0]), cells[1].strip(), files, cells[3], due, cells[4].strip(), ln))
    return out


def check_meta(repo: Repo, waivers: List[Waiver]) -> List[Finding]:
    out = []
    ids = rule_ids(repo)
    if not ids:
        return [Finding("RULES", "", "RULES.md", "RULES.md 에서 조항을 찾지 못했습니다")]
    agents = repo.text("AGENTS.md")
    summary = {m.group(1): norm_name(m.group(2)) for m in re.finditer(r"(W-\d\d)\s+\*\*(.+?)\*\*", agents)}
    for wid, title in ids.items():
        if wid.startswith("W-") and summary.get(wid) != norm_name(title):
            out.append(Finding("RULES", "", "AGENTS.md", f"{wid} 요약이 RULES.md 와 다릅니다 "
                                                        f"('{summary.get(wid, '없음')}' · 정본 '{title}')"))
    for wid in sorted(set(summary) - set(ids)):
        out.append(Finding("RULES", "", "AGENTS.md", f"RULES.md 에 없는 조항 {wid} 가 요약에 있습니다"))
    for w in waivers:
        if w.rule not in ids:
            out.append(Finding("RULES", "", "docs/REGISTRY.md", f"예외 대장의 조항 {w.rule} 이 RULES.md 에 없습니다", w.line))
        if w.app not in repo.apps:
            out.append(Finding("RULES", "", "docs/REGISTRY.md", f"예외 대장의 앱 {w.app} 폴더가 없습니다", w.line))
    return out


def waiver_covers(w: Waiver, f: Finding) -> bool:
    if w.app != f.app or w.rule != f.rule:
        return False
    if "*" in w.files:
        return True
    cands = {f.path, f.path[len(f.app) + 1:] if f.path.startswith(f.app + "/") else f.path}
    return any(c == x or c.startswith(x.rstrip("/") + "/") for c in cands for x in w.files)


# ─────────────────────────────────────────────────────────────── 실행

def run_checks(repo: Repo, run_tests: bool = True) -> Tuple[List[Finding], List[Waiver]]:
    waivers = load_waivers(repo)
    findings: List[Finding] = []
    for check in (check_structure, check_cross_refs, check_public_commands, check_imports, check_network, check_secrets,
                  check_install, check_design, check_public, check_version, check_llm_spec, check_registry, check_docs):
        findings += check(repo)
    findings += check_ci(repo, run_tests)
    findings += check_meta(repo, waivers)
    findings.sort(key=lambda f: (f.app or "~", f.rule, f.path, f.line))
    return findings, waivers


def judge(findings: List[Finding], waivers: List[Waiver], today: date):
    """→ [(finding, waiver|None, expired)], 걸린 것 없는 예외, 기한 지난 예외"""
    judged, used = [], set()
    for f in findings:
        w = next((w for w in waivers if waiver_covers(w, f)), None)
        if w is not None:
            used.add(w)
        judged.append((f, w, bool(w and w.due and w.due < today)))
    unused = [w for w in waivers if w not in used and w.rule not in UNCHECKED]
    expired = [w for w in waivers if w.due and w.due < today]
    return judged, unused, expired


def gh_escape(s: str, prop: bool = False) -> str:
    s = s.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    return s.replace(":", "%3A").replace(",", "%2C") if prop else s


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="works 규칙 검사기 (RULES.md)")
    ap.add_argument("--strict", action="store_true", help="위반이 있으면 종료 코드 1 (차단 모드)")
    ap.add_argument("--no-tests", action="store_true", help="테스트 수 확인을 건너뜀")
    ap.add_argument("--root", default=ROOT, help=argparse.SUPPRESS)
    ap.add_argument("--today", default="", help=argparse.SUPPRESS)   # 테스트용: 기한 계산 기준일
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(errors="replace")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    today = date.fromisoformat(args.today) if args.today else date.today()
    repo = Repo(args.root)
    findings, waivers = run_checks(repo, run_tests=not args.no_tests)
    judged, unused, expired = judge(findings, waivers, today)
    gha = os.environ.get("GITHUB_ACTIONS") == "true"

    print(f"works 규칙 검사 · {today.isoformat()} · 앱 {len(repo.apps)}개 ({' · '.join(repo.apps) or '없음'})")
    violations = 0
    current = None
    for f, w, late in judged:
        group = f.app or "저장소"
        if group != current:
            print(f"\n── {group}")
            current = group
        where = f.path + (f":{f.line}" if f.line else "")
        if w and not late:
            print(f"  ○ {f.rule}  {where}  {f.msg}  [예외 · {w.due_text}]")
            continue
        violations += 1
        mark = "‼" if late else "×"
        tail = f"  [예외 기한 지남 · {w.due_text}]" if late and w else ""
        print(f"  {mark} {f.rule}  {where}  {f.msg}{tail}")
        if gha:
            loc = f"file={gh_escape(f.path, True)}" + (f",line={f.line}" if f.line else "")
            print(f"::warning {loc},title={gh_escape('works ' + f.rule, True)}::{gh_escape(f.msg)}")
    if not judged:
        print("\n  √ 걸린 것이 없습니다")
    if unused or expired:
        print("\n── 예외 대장 (docs/REGISTRY.md)")
        for w in expired:
            print(f"  ‼ {w.app} {w.rule} — 기한 지남 ({w.due_text}): {w.note}")
        for w in unused:
            print(f"  √ {w.app} {w.rule} {', '.join(w.files)} — 걸리는 것이 없습니다. 고쳤다면 이 줄을 지우세요 "
                  f"(docs/REGISTRY.md:{w.line})")
    for n in repo.notes:
        print(f"  · {n}")
    waived = sum(1 for _, w, late in judged if w and not late)
    print(f"\n위반 {violations} · 예외 {waived} · 기한 지난 예외 {len(expired)} · 지워도 되는 예외 {len(unused)}"
          + ("" if args.strict else " · 경고 모드 (RULES.md › 검사기)"))
    if violations == 0:
        print("결과: OK")
        return 0
    print("결과: 점검 실패" if args.strict else "결과: 확인 필요")
    return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
