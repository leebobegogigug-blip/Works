#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Flow–1 - 파이썬 데이터 쿼리를 흐름도 한 장으로 (내 PC에서만 · Python 3.8+ · 표준 라이브러리만)

[실행]
  python flow-1.py                         창을 연다 (감시 목록의 파일 · 폴더)
  python flow-1.py "D:\분석\daily.py"       그 파일(폴더)을 감시 목록에 더하고 창을 연다
  python flow-1.py --scan 경로…             창 없이 — 쿼리마다 SELECT · FROM · JOIN · WHERE 와 흐름을 글로
  python flow-1.py --json 경로…             창 없이 — 분석 결과 JSON (format 1)
  python flow-1.py --svg 흐름.svg 경로…      흐름도를 SVG 파일로 (--detail 1-3 · --theme light)
  python flow-1.py --run 스크립트.py [인자…]  실행하며 쿼리 호출마다 걸린 시간 · 행 수를 잰다 (창에 바로 보인다)
  python flow-1.py --check                 점검 (마지막 줄 '결과: …')
  기타: --setup · --set 키=값 · --remove 경로 · --status · --stop · --shortcut on|off · --port · --no-window · --config

[모듈] 이 파일은 진입점 · 설정 · 감시 · 로컬 서버다. 분석은 옆의 모듈이 한다 (docs/GUIDE.md › 02 코드 지도)
  flow1_sql.py    SQL → 절 (SELECT · FROM · JOIN · WHERE …) · 읽는/쓰는 테이블
  flow1_scan.py   파이썬 · 노트북 → 쿼리 호출 · 변수 흐름 · 병합 · 출력
  flow1_graph.py  흐름도: 카드 줄 · 배치 · 간선 · SVG · --scan 글
  flow1_trace.py  --run: 쿼리 호출 자리만 감싸 시간 · 행 수 기록
  flow1_assets.py 화면(ui.html) · 폰트 — python build.py 로 만드는 생성 파일

[config.json]  %LOCALAPPDATA%\flow-1\config.json  (FLOW_HOME 으로 폴더를 바꿀 수 있다)
  watch            감시할 파일 · 폴더 (.py · .ipynb)
  query.modules    사내 쿼리 패키지 이름 — SQL 이 변수라 못 읽어도 그 패키지 호출은 쿼리로 잡는다 (비워도 SQL 모양 인자로 찾는다)
  query.calls      그 패키지에서 SQL 을 받는 함수 · 메서드 이름 · query.sinks 출력으로 볼 메서드 (to_csv …)
  scan.max_files · scan.poll_sec · run.keep · theme · company · port(8785) · open_window · idle_exit_min

[보안 · 저장]
  127.0.0.1 에만 열리고 실행마다 새 토큰 · 밖으로 나가는 통신 없음
  코드를 읽기만 한다 (--run 을 빼면 실행하지 않는다). 붙여 넣은 코드는 메모리에만
  실행 기록(runs\)은 시각 · 걸린 시간 · 행 수 · 오류 이름만 — SQL 원문 · 결과 데이터는 남기지 않는다
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import importlib.util
import json
import os
import re
import secrets
import shutil
import socket
import socketserver
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qs, urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import flow1_graph  # noqa: E402
import flow1_scan  # noqa: E402
import flow1_sql  # noqa: E402
import flow1_trace  # noqa: E402

APP = "flow-1"              # 명령 · 파일 · 데이터 폴더 이름
NAME = "Flow–1"             # 화면에 보이는 이름
VERSION = "0.1.1"
ENV = "FLOW"                # 환경 변수 접두어 (docs/REGISTRY.md)
IS_WINDOWS = sys.platform == "win32"
NO_WINDOW = 0x08000000 if IS_WINDOWS else 0
EXAMPLES = os.path.join(BASE_DIR, "tests", "examples")


def log(msg: str) -> None:
    """로그는 표준 오류로 — 표준 출력은 --scan · --json 결과만 쓴다"""
    try:
        print(f"[{datetime.now():%H:%M:%S}] {msg}", file=sys.stderr, flush=True)
    except Exception:
        pass


def data_dir() -> str:
    """%LOCALAPPDATA%\\flow-1 (Windows 밖: ~/.local/share/flow-1). FLOW_HOME 이 있으면 그 폴더"""
    if os.environ.get(ENV + "_HOME"):
        return os.path.abspath(os.environ[ENV + "_HOME"])
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, APP)


def default_config_path() -> str:
    return os.path.join(data_dir(), "config.json")


# ─────────────────────────────────────────────────────────────── 01 설정

DEFAULT_CONFIG: Dict[str, Any] = {
    "watch": [],
    "query": {
        "modules": [],
        "calls": list(flow1_scan.DEFAULT_CALLS),
        "sinks": list(flow1_scan.DEFAULT_SINKS),
    },
    "scan": {"max_files": 400, "poll_sec": 2},
    "run": {"keep": 20},
    "theme": "dark",
    "company": "",
    "port": 8785,
    "open_window": True,
    "idle_exit_min": 30,
}
_NAME_RE = re.compile(r"^[A-Za-z_][\w.]*$")


class ConfigError(Exception):
    pass


def deep_merge(base: Dict[str, Any], over: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def write_json(path: str, data: Any) -> None:
    """원자적 쓰기 (RULES.md › W-06)"""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def read_user_config(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except ValueError as e:
        raise ConfigError(f"{path} 형식 오류: {e}")
    if not isinstance(data, dict):
        raise ConfigError(f"{path} 의 최상위는 {{ }} 객체여야 합니다")
    return data


def load_config(path: str, create: bool = True) -> Tuple[Dict[str, Any], bool]:
    created = False
    user = read_user_config(path)
    if not user and not os.path.exists(path) and create:
        try:
            write_json(path, DEFAULT_CONFIG)
            created = True
        except OSError as e:
            raise ConfigError(f"{path} 를 만들 수 없습니다: {e}")
    cfg = deep_merge(DEFAULT_CONFIG, user)
    for key in ("modules", "calls", "sinks"):          # 목록은 사용자가 정한 그대로 (기본값과 섞지 않는다)
        if isinstance((user.get("query") or {}).get(key), list):
            cfg["query"][key] = list(user["query"][key])
    cfg["_dir"] = os.path.dirname(os.path.abspath(path))
    validate_config(cfg)
    return cfg, created


def _name_list(v: Any, what: str) -> List[str]:
    if not isinstance(v, list) or not all(isinstance(x, str) and _NAME_RE.match(x.strip()) for x in v):
        raise ConfigError(f"{what} 는 이름 목록이어야 합니다 (예: [\"query\", \"execute\"])")
    return [x.strip() for x in v]


def validate_config(cfg: Dict[str, Any]) -> None:
    w = cfg.get("watch")
    if not isinstance(w, list) or not all(isinstance(x, str) and x.strip() for x in w):
        raise ConfigError('watch 는 파일 · 폴더 경로 목록이어야 합니다. 예: ["D:\\\\분석"]')
    cfg["watch"] = [x.strip() for x in w]
    q = cfg.get("query")
    if not isinstance(q, dict):
        raise ConfigError("query 는 { } 객체여야 합니다")
    q["modules"] = _name_list(q.get("modules"), "query.modules")
    q["calls"] = _name_list(q.get("calls"), "query.calls")
    q["sinks"] = _name_list(q.get("sinks"), "query.sinks")
    try:
        cfg["scan"]["max_files"] = min(5000, max(1, int(cfg["scan"]["max_files"])))
        cfg["scan"]["poll_sec"] = min(60.0, max(1.0, float(cfg["scan"]["poll_sec"])))
        cfg["run"]["keep"] = min(200, max(1, int(cfg["run"]["keep"])))
        cfg["port"] = int(cfg.get("port") or 8785)
        cfg["idle_exit_min"] = max(0.0, float(cfg.get("idle_exit_min", 30)))
    except (TypeError, ValueError, KeyError):
        raise ConfigError("scan.max_files · scan.poll_sec · run.keep · port · idle_exit_min 은 숫자여야 합니다")
    cfg["theme"] = str(cfg.get("theme") or "dark").strip().lower()
    if cfg["theme"] not in ("dark", "light", "system"):
        raise ConfigError('theme 는 "dark", "light", "system" 중 하나여야 합니다')
    c = cfg.get("company")
    if c is None:
        c = ""
    if not isinstance(c, str) or len(c.strip()) > 24 or re.search(r"[\x00-\x1f\x7f]", c):
        raise ConfigError("company 는 24자까지의 글자여야 합니다 (예: --set company=회사이름 · 비우려면 --set company=)")
    cfg["company"] = c.strip()


def scan_cfg(cfg: Dict[str, Any]) -> Dict[str, Any]:
    q = cfg["query"]
    return {"modules": q["modules"], "calls": q["calls"], "sinks": q["sinks"]}


def set_config_values(path: str, pairs: List[str]) -> int:
    """--set 키=값 (값은 JSON 으로 읽히면 JSON, 목록 칸은 ; 로 나눈 글도). 저장 뒤 검증해서 틀리면 되돌린다"""
    user = read_user_config(path)
    before = json.dumps(user, ensure_ascii=False)
    for pair in pairs:
        key, eq, raw = pair.partition("=")
        key = key.strip()
        if not eq or not key:
            print(f"--set 형식은 키=값 입니다: {pair}")
            return 2
        try:
            value: Any = json.loads(raw) if raw.strip() else ""
        except ValueError:
            value = raw
        parts, node, spec = key.split("."), user, DEFAULT_CONFIG
        for i, part in enumerate(parts):
            if not isinstance(spec, dict) or part not in spec:
                print(f"알 수 없는 설정 키: {key}")
                return 2
            spec = spec[part]
            if i == len(parts) - 1:
                if isinstance(spec, list) and not isinstance(value, list):
                    value = [v.strip() for v in str(value).split(";") if v.strip()]
                node[part] = value
            else:
                if not isinstance(node.get(part), dict):
                    node[part] = {}
                node = node[part]
        print(f"설정: {key} = {json.dumps(value, ensure_ascii=False)}")
    write_json(path, user)
    try:
        load_config(path, create=False)
    except ConfigError as e:
        write_json(path, json.loads(before))
        print(f"값이 올바르지 않아 되돌렸습니다: {e}")
        return 2
    return 0


def watch_edit(path: str, add: List[str], remove: List[str]) -> List[str]:
    """감시 목록 고치기 (config.json 의 watch 만) → 알림 글"""
    user = read_user_config(path)
    cur = [x for x in (user.get("watch") or []) if isinstance(x, str)]
    notes = []
    for p in add:
        ap = os.path.abspath(os.path.expanduser(p.strip().strip('"')))
        if not os.path.exists(ap):
            raise ConfigError(f"없는 경로입니다: {ap}")
        if os.path.isfile(ap) and flow1_scan.kind_of(ap) == "py" and not ap.lower().endswith(".py"):
            raise ConfigError(f".py · .ipynb · .sql 파일이나 폴더만 볼 수 있습니다: {ap}")
        if any(_covers(c, ap) for c in cur):
            notes.append(f"이미 보고 있습니다: {ap}")
            continue
        cur.append(ap)
        notes.append(f"감시 목록에 더함: {ap}")
    for p in remove:
        ap = os.path.abspath(os.path.expanduser(p.strip().strip('"')))
        keep = [c for c in cur if os.path.normcase(c) != os.path.normcase(ap)]
        notes.append(f"감시 목록에서 뺌: {ap}" if len(keep) != len(cur) else f"감시 목록에 없습니다: {ap}")
        cur = keep
    user["watch"] = cur
    write_json(path, user)
    return notes


def _covers(root: str, path: str) -> bool:
    r, p = os.path.normcase(os.path.abspath(root)), os.path.normcase(os.path.abspath(path))
    return p == r or (os.path.isdir(r) and p.startswith(r.rstrip("\\/") + os.sep))


# ─────────────────────────────────────────────────────────────── 02 감시 (파일 목록 · 바뀐 파일만 다시 읽기 · 실행 기록)

SKIP_DIRS = {"__pycache__", ".git", ".hg", ".svn", ".venv", "venv", "env", ".env", "site-packages", "node_modules",
             ".ipynb_checkpoints", ".mypy_cache", ".pytest_cache", ".tox", ".idea", ".vscode"}
MAX_FILE_BYTES = 2_000_000
MAX_PASTE = 2_000_000


def file_key(path: str) -> str:
    return hashlib.sha1(os.path.normcase(os.path.abspath(path)).encode("utf-8")).hexdigest()[:10]


class Watch:
    """감시 목록의 파일을 읽어 둔다. 바뀐 파일(mtime · 크기)만 다시 분석하고, 무엇이든 바뀌면 gen 을 올린다"""
    LIST_SEC = 10.0

    def __init__(self, cfg: Dict[str, Any]):
        self.cfg = cfg
        self.lock = threading.RLock()
        self.files: Dict[str, Dict[str, Any]] = {}
        self.order: List[str] = []
        self.pastes: Dict[str, Dict[str, Any]] = {}
        self.paste_n = 0
        self.gen = 1
        self.listed = 0.0
        self.scanned = ""
        self.truncated = False
        self.opened: List[str] = []          # 탐색기에서 '이번만 열기' 한 파일 (설정에 저장하지 않는다)
        self.runs_dir = os.path.join(cfg.get("_dir") or data_dir(), "runs")

    def list_files(self) -> List[Tuple[str, str]]:
        """(경로, 뿌리) — 뿌리 순서대로, 폴더 안은 이름 순. 이번만 연 파일은 맨 뒤 (뿌리 '')"""
        out: List[Tuple[str, str]] = self._walk_roots()
        seen = {os.path.normcase(p) for p, _ in out}
        for p in self.opened:
            if os.path.normcase(p) not in seen:
                out.append((p, ""))
        return out

    def covered(self, path: str) -> bool:
        return any(_covers(r, path) for r in self.cfg["watch"])

    def open(self, path: str) -> str:
        """탐색기의 '이번만 열기' — 감시 목록에 있으면 그 파일, 없으면 이번 실행 동안만 본다 → 파일 key"""
        ap = os.path.abspath(os.path.expanduser(str(path or "").strip().strip('"')))
        if not os.path.isfile(ap):
            raise ValueError(f"없는 파일입니다: {ap}")
        if not ap.lower().endswith((".py", ".ipynb", ".sql", ".hql")):
            raise ValueError(".py · .ipynb · .sql 파일만 열 수 있습니다")
        with self.lock:
            if not self.covered(ap) and all(os.path.normcase(p) != os.path.normcase(ap) for p in self.opened):
                self.opened.append(ap)
        self.refresh(force=True)
        return file_key(ap)

    def close(self, key: str) -> None:
        with self.lock:
            keep = [p for p in self.opened if file_key(p) != key]
            if len(keep) == len(self.opened):
                raise KeyError(f"이번만 연 파일이 아닙니다: {key}")
            self.opened = keep
        self.refresh(force=True)

    def _walk_roots(self) -> List[Tuple[str, str]]:
        out: List[Tuple[str, str]] = []
        limit = int(self.cfg["scan"]["max_files"])
        self.truncated = False
        for root in self.cfg["watch"]:
            if os.path.isfile(root):
                out.append((os.path.abspath(root), root))
                continue
            if not os.path.isdir(root):
                continue
            for d, subdirs, names in os.walk(root):
                subdirs[:] = sorted(s for s in subdirs if s not in SKIP_DIRS and not s.startswith("."))
                for n in sorted(names):
                    if n.lower().endswith((".py", ".ipynb")):
                        out.append((os.path.join(d, n), root))
                        if len(out) >= limit:
                            self.truncated = True
                            return out
        return out

    def refresh(self, force: bool = False) -> bool:
        """감시 한 바퀴 — 바뀐 것이 있으면 True"""
        changed = False
        now = time.time()
        with self.lock:
            if force or now - self.listed > self.LIST_SEC:
                self.listed = now
                found = self.list_files()
                keys = []
                for path, root in found:
                    k = file_key(path)
                    keys.append(k)
                    if k not in self.files:
                        self.files[k] = {"key": k, "path": path, "root": root, "name": os.path.basename(path),
                                         "kind": flow1_scan.kind_of(path), "sig": None, "result": None, "run_sig": None}
                        changed = True
                for k in list(self.files):
                    if k not in keys:
                        del self.files[k]
                        changed = True
                if keys != self.order:
                    self.order = keys
                    changed = True
            entries = [self.files[k] for k in self.order]
        for e in entries:
            try:
                st = os.stat(e["path"])
                sig: Any = (st.st_mtime_ns, st.st_size)
            except OSError:
                sig = "gone"
            if sig != e["sig"] or force:
                if sig == "gone":
                    res = flow1_scan.empty_result(e["path"], e["name"], e["kind"])
                    res["error"] = "파일이 없습니다"
                elif isinstance(sig, tuple) and sig[1] > MAX_FILE_BYTES:
                    res = flow1_scan.empty_result(e["path"], e["name"], e["kind"])
                    res["error"] = f"{sig[1] // 1_000_000} MB — 2 MB 보다 큰 파일은 읽지 않습니다"
                else:
                    res = flow1_scan.scan_file(e["path"], scan_cfg(self.cfg))
                with self.lock:
                    e["sig"], e["result"] = sig, res
                changed = True
            rs = self.run_sig(e["path"])
            if rs != e["run_sig"]:
                e["run_sig"] = rs
                changed = True
        if changed:
            with self.lock:
                self.gen += 1
                self.scanned = datetime.now().strftime("%H:%M:%S")
        return changed

    def run_sig(self, path: str) -> Any:
        d = os.path.join(self.runs_dir, flow1_trace.script_key(path))
        try:
            names = sorted(os.listdir(d))
        except OSError:
            return None
        live = os.path.join(d, "live.json")
        try:
            lm = os.stat(live).st_mtime_ns
        except OSError:
            lm = 0
        return (names[-1] if names else "", len(names), lm)

    def entries(self) -> List[Dict[str, Any]]:
        with self.lock:
            return [self.files[k] for k in self.order if self.files[k]["result"] is not None] + list(self.pastes.values())

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            return self.files.get(key) or self.pastes.get(key)

    def paste(self, text: str, name: str = "") -> Dict[str, Any]:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("붙여 넣은 글이 비어 있습니다")
        if len(text) > MAX_PASTE:
            raise ValueError("2 MB 까지만 붙여 넣을 수 있습니다")
        name = re.sub(r"[\x00-\x1f]", "", str(name or "")).strip()[:80]
        kind = flow1_scan.kind_of(name) if name else "py"
        if kind == "py" and not name.lower().endswith(".py"):
            try:
                compile(text, "<paste>", "exec", flags=0, dont_inherit=True)
                is_py = True
            except (SyntaxError, ValueError):
                is_py = False
            if not is_py and flow1_sql.looks_like_sql(text):
                kind = "sql"
        with self.lock:
            self.paste_n += 1
            key = f"p{self.paste_n}"
            label = name or ("붙여 넣은 SQL" if kind == "sql" else "붙여 넣은 코드") + f" {self.paste_n}"
            res = flow1_scan.scan_text(text, label, scan_cfg(self.cfg), kind)
            self.pastes[key] = {"key": key, "path": "", "root": "", "name": label, "kind": kind, "result": res,
                                "paste": True}
            self.gen += 1
            return self.pastes[key]

    def unpaste(self, key: str) -> None:
        with self.lock:
            if self.pastes.pop(key, None) is None:
                raise KeyError(f"붙여 넣은 것이 없습니다: {key}")
            self.gen += 1


EXPLORE_EXT = (".py", ".ipynb", ".sql", ".hql")
MAX_LIST = 400              # 탐색기 한 폴더에 보여 주는 항목 수
_SQL_HINT_RE = re.compile(rb"(?is)\bselect\b.{1,4000}?\bfrom\b|\binsert\s+(?:into|overwrite)\b|\bcreate\s+table\b")


def sql_hint(path: str) -> bool:
    """파일 앞부분(256 KB)에 SQL 이 있어 보이는지 — 탐색기의 ● 표시용. 읽기만 하고 남기지 않는다"""
    try:
        with open(path, "rb") as f:
            return bool(_SQL_HINT_RE.search(f.read(256_000)))
    except OSError:
        return False


def places() -> List[Dict[str, Any]]:
    """탐색기 맨 위 — 드라이브(Windows) · / · 홈 · 바탕 화면 · 문서"""
    out: List[Dict[str, Any]] = []
    if IS_WINDOWS:
        for d in "CDEFGHIJKLMNOPQRSTUVWXYZ":
            root = f"{d}:\\"
            if os.path.isdir(root):
                out.append({"name": root, "path": root, "dir": True})
    else:
        out.append({"name": "/", "path": "/", "dir": True})
    home = os.path.expanduser("~")
    for label, p in (("홈", home), ("바탕 화면", os.path.join(home, "Desktop")), ("문서", os.path.join(home, "Documents"))):
        if os.path.isdir(p):
            out.append({"name": f"{label} · {p}", "path": p, "dir": True})
    return out


def list_dir(path: str, watch: Optional["Watch"] = None) -> Dict[str, Any]:
    """탐색기 한 층 — 폴더 · .py · .ipynb · .sql (숨김 · 가상환경 · 캐시 폴더는 뺀다). path '' = 드라이브 · 홈"""
    if not str(path or "").strip():
        return {"path": "", "parent": None, "items": places(), "more": 0}
    ap = os.path.abspath(os.path.expanduser(str(path).strip().strip('"')))
    if not os.path.isdir(ap):
        raise ValueError(f"폴더가 아닙니다: {ap}")
    try:
        entries = list(os.scandir(ap))
    except OSError as e:
        raise ValueError(f"열 수 없는 폴더입니다: {ap} ({e.strerror or e})")
    dirs: List[Dict[str, Any]] = []
    files: List[Dict[str, Any]] = []
    for de in entries:
        n = de.name
        if n.startswith((".", "$", "~")) or n in SKIP_DIRS:
            continue
        try:
            isdir = de.is_dir()
        except OSError:
            continue
        if isdir:
            dirs.append({"name": n, "path": de.path, "dir": True})
        elif n.lower().endswith(EXPLORE_EXT):
            try:
                size = de.stat().st_size
            except OSError:
                size = 0
            files.append({"name": n, "path": de.path, "dir": False, "kind": flow1_scan.kind_of(n), "size": size})
    dirs.sort(key=lambda x: x["name"].casefold())
    files.sort(key=lambda x: x["name"].casefold())
    items = dirs + files
    more = max(0, len(items) - MAX_LIST)
    items = items[:MAX_LIST]
    for it in items:
        if not it["dir"]:
            it["sql"] = it["size"] <= 2_000_000 and sql_hint(it["path"])
        if watch is not None:
            it["watched"] = watch.covered(it["path"])
            it["opened"] = any(os.path.normcase(p) == os.path.normcase(it["path"]) for p in watch.opened)
    parent = os.path.dirname(ap.rstrip("\\/")) if os.path.dirname(ap.rstrip("\\/")) != ap.rstrip("\\/") else ""
    if IS_WINDOWS and re.fullmatch(r"[A-Za-z]:\\?", ap):
        parent = ""
    return {"path": ap, "parent": parent if parent != ap else "", "items": items, "more": more}


# ─────────────────────────────────────────────────────────────── 03 앱 · 로컬 서버

def file_summary(e: Dict[str, Any], runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    res = e["result"] or {}
    last = runs[0] if runs else None
    run: Dict[str, Any] = {}
    if last is not None:
        if last.get("live"):
            run = {"state": "stale" if last.get("stale") else "live", "started": last.get("started", "")}
        else:
            run = {"state": "ok" if last.get("ok") else "err", "ended": last.get("ended", ""), "ms": last.get("ms", 0),
                   "calls": len(last.get("calls") or [])}
    return {"key": e["key"], "name": e["name"], "path": e["path"], "root": e["root"], "kind": e["kind"],
            "paste": bool(e.get("paste")), "opened": not e.get("paste") and not e["root"],
            "error": res.get("error", ""), "warnings": res.get("warnings", []), "stats": res.get("stats", {}),
            "run": run}


class App:
    def __init__(self, cfg: Dict[str, Any], config_path: str):
        self.cfg = cfg
        self.config_path = config_path
        self.token = secrets.token_urlsafe(24)
        self.watch = Watch(cfg)
        self.lock = threading.RLock()
        self.cache: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
        self.httpd: Optional[ThreadingHTTPServer] = None
        self.port = 0
        self.allowed_hosts: Set[str] = set()
        self.last_seen = time.time()
        self.stop = threading.Event()
        self.cfg_sig = self._cfg_sig()

    def _cfg_sig(self) -> Any:
        try:
            st = os.stat(self.config_path)
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def reload_config(self) -> bool:
        """다른 창의 --run · --set · 경로 더하기가 설정 파일을 바꿨으면 감시 목록 · 찾는 규칙을 다시 읽는다"""
        sig = self._cfg_sig()
        if sig == self.cfg_sig:
            return False
        self.cfg_sig = sig
        try:
            cfg, _ = load_config(self.config_path, create=False)
        except ConfigError as e:
            log(f"설정을 다시 읽지 못했습니다 (그대로 씁니다): {e}")
            return False
        rules = cfg["query"] != self.cfg["query"]
        for key in ("watch", "query", "scan", "run"):
            self.cfg[key] = cfg[key]
        if not rules:
            self.watch.listed = 0.0          # 감시 목록만 바뀜 → 다음 한 바퀴에서 목록부터 다시
        self.watch.refresh(force=rules)       # 찾는 규칙이 바뀜 → 전부 다시 분석
        return True

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def render_index(self) -> bytes:
        import flow1_assets
        boot = {"version": VERSION, "company": self.cfg.get("company") or "", "poll": self.cfg["scan"]["poll_sec"],
                "example": os.path.isdir(EXAMPLES), "detail": 2}
        boot_js = json.dumps(boot, ensure_ascii=False).replace("</", "<\\/")
        html = flow1_assets.INDEX_HTML.replace("__THEME__", self.cfg.get("theme") or "dark")
        html = html.replace("__SVGCSS__", flow1_graph.SVG_CSS)
        return html.replace("__TOKEN__", self.token).replace("__BOOT__", boot_js).encode("utf-8")

    def runs_of(self, e: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not e.get("path"):
            return []
        return flow1_trace.list_runs(self.watch.runs_dir, e["path"])

    def last_run(self, e: Dict[str, Any]) -> List[Dict[str, Any]]:
        """파일의 최근 실행 하나 (없으면 []) — 감시 한 바퀴마다 run_sig 가 바뀔 때만 다시 읽는다"""
        if not e.get("path"):
            return []
        sig = e.get("run_sig")
        if e.get("_run_cache", (None, None))[0] != sig or sig is None:
            run = flow1_trace.pick_run(self.watch.runs_dir, e["path"])
            e["_run_cache"] = (sig, [run] if run is not None else [])
        if e["_run_cache"][1] and e["_run_cache"][1][0].get("live"):      # 실행 중이면 끊김 여부를 늘 새로
            run = flow1_trace.pick_run(self.watch.runs_dir, e["path"])
            e["_run_cache"] = (sig, [run] if run is not None else [])
        return e["_run_cache"][1]

    def state(self) -> Dict[str, Any]:
        w = self.watch
        files = [file_summary(e, self.last_run(e)) for e in w.entries()]
        roots = [{"path": r, "exists": os.path.exists(r), "dir": os.path.isdir(r)} for r in self.cfg["watch"]]
        return {"version": VERSION, "gen": w.gen, "files": files, "roots": roots, "scanned": w.scanned,
                "truncated": w.truncated, "poll": self.cfg["scan"]["poll_sec"], "modules": self.cfg["query"]["modules"],
                "live": any(f["run"].get("state") == "live" for f in files), "example": os.path.isdir(EXAMPLES),
                "start": (self.cfg["watch"][0] if self.cfg["watch"] and os.path.isdir(self.cfg["watch"][0])
                          else os.path.dirname(self.cfg["watch"][0]) if self.cfg["watch"] else os.path.expanduser("~"))}

    def _results(self, key: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """(엔트리, 스캔 결과) — all 이면 쿼리가 있는 파일 전부"""
        if key == "all":
            ents = [e for e in self.watch.entries() if (e["result"] or {}).get("queries")]
        else:
            e = self.watch.get(key)
            if e is None or e["result"] is None:
                raise KeyError(f"파일이 없습니다: {key}")
            ents = [e]
        return ents, [e["result"] for e in ents]

    def _runs_for(self, ents: List[Dict[str, Any]], results: List[Dict[str, Any]], run_id: str
                  ) -> Tuple[Dict[str, Dict[str, Any]], Optional[Dict[str, Any]]]:
        multi = len(results) > 1
        pairs = [(f"f{i}:" if multi else "", r) for i, r in enumerate(results)]
        out: Dict[str, Dict[str, Any]] = {}
        shown: Optional[Dict[str, Any]] = None
        for e in ents:
            if not e.get("path"):
                continue
            run = (flow1_trace.pick_run(self.watch.runs_dir, e["path"], run_id) if run_id else None) \
                or flow1_trace.pick_run(self.watch.runs_dir, e["path"])
            if run is None:
                continue
            if shown is None or run.get("live"):
                shown = {"id": run.get("run"), "file": e["name"], "live": bool(run.get("live")),
                         "stale": bool(run.get("stale")), "started": run.get("started", ""), "ms": run.get("ms"),
                         "ok": run.get("ok"), "error": run.get("error", ""), "calls": len(run.get("calls") or [])}
            out.update(flow1_trace.match(run, pairs))
        return out, shown

    def graph(self, key: str, detail: int, run_id: str = "") -> Dict[str, Any]:
        detail = min(3, max(1, int(detail or 2)))
        gen = self.watch.gen
        ck = (key, detail, gen, run_id)
        with self.lock:
            if ck in self.cache:
                return self.cache[ck]
        ents, results = self._results(key)
        runs, shown = self._runs_for(ents, results, run_id)
        g = flow1_graph.build(results, detail, runs)
        nodes = []
        for n in g["nodes"]:
            text = " ".join([n.get("title", ""), n.get("label", ""), n.get("meta", "")] +
                            [r["lbl"] + " " + r["text"] for r in n.get("rows") or []])
            nodes.append({"id": n["id"], "kind": n["kind"], "title": n.get("title") or n.get("label", ""),
                          "file": n.get("file", 0), "ref": n.get("ref", ""), "x": n["x"], "y": n["y"], "w": n["w"],
                          "h": n["h"], "text": text.lower(), "run": (n.get("run") or {}).get("state", "")})
        edges = [{"id": e["id"], "from": e["from"], "to": e["to"], "kind": e["kind"],
                  "join": e.get("join", False)} for e in g["edges"]]
        out = {"key": key, "gen": gen, "detail": detail, "svg": flow1_graph.svg(g), "width": g["width"],
               "height": g["height"], "stats": g["stats"], "nodes": nodes, "edges": edges,
               "files": [{"key": e["key"], "name": e["name"]} for e in ents], "run": shown}
        with self.lock:
            if len(self.cache) > 24:
                self.cache.clear()
            self.cache[ck] = out
        return out

    def export_svg(self, key: str, detail: int, run_id: str, theme: str) -> str:
        """내려받을 SVG — 색 · 폰트를 안에 담아 어디서 열어도 같게"""
        import flow1_assets
        ents, results = self._results(key)
        runs, _ = self._runs_for(ents, results, run_id)
        g = flow1_graph.build(results, detail, runs)
        return flow1_graph.svg(g, standalone=True, theme="light" if theme == "light" else "dark",
                               font_b64=flow1_assets.FONT_WOFF_B64.replace("\n", ""))

    def detail(self, key: str, nid: str) -> Dict[str, Any]:
        ents, results = self._results(key)
        multi = len(results) > 1
        m = re.match(r"^(?:f(\d+):)?([qjio]\d+)$", nid)
        if nid.startswith("t:"):
            return self._table_detail(ents, results, nid)
        if not m:
            raise KeyError(f"없는 노드: {nid}")
        fi = int(m.group(1) or 0) if multi else 0
        if fi >= len(results):
            raise KeyError(f"없는 노드: {nid}")
        res, ref = results[fi], m.group(2)
        bucket = {"q": "queries", "j": "ops", "i": "inputs", "o": "outputs"}[ref[0]]
        item = next((x for x in res.get(bucket, []) if x["id"] == ref), None)
        if item is None:
            raise KeyError(f"없는 노드: {nid}")
        pre = f"f{fi}:" if multi else ""
        out: Dict[str, Any] = {"id": nid, "kind": {"q": "query", "j": "op", "i": "input", "o": "output"}[ref[0]],
                               "file": ents[fi]["name"], "path": ents[fi]["path"], "item": item, "pre": pre}
        names = {x["id"]: x for b in ("queries", "ops", "inputs", "outputs") for x in res.get(b, [])}
        out["refs"] = {k: {"n": v["n"], "var": v.get("var", ""), "kind": k[0]} for k, v in names.items()}
        if ref[0] == "q":
            out["spans"] = flow1_sql.sql_spans(item["sql"], item["parsed"]["stmts"])
            out["rows"] = flow1_graph.query_rows(item, 3, 0)
            out["columns"] = {r["name"]: flow1_graph.columns_of(item, r["key"]) for r in item["reads"]}
            out["history"] = self._history(ents[fi], res, ref)
        out["into"] = [e for e in res.get("edges", []) if e["to"] == ref]
        out["out"] = [e for e in res.get("edges", []) if e["from"] == ref]
        return out

    def _history(self, e: Dict[str, Any], res: Dict[str, Any], ref: str) -> List[Dict[str, Any]]:
        hist = []
        for run in self.runs_of(e)[:12]:
            s = flow1_trace.match(run, [("", res)]).get(ref)
            if s is not None:
                hist.append({"run": run.get("run"), "started": run.get("started", ""), "live": bool(run.get("live")),
                             "state": s["state"], "ms": s["ms"], "rows": s["rows"], "n": s["n"], "err": s["err"]})
        return hist

    def _table_detail(self, ents: List[Dict[str, Any]], results: List[Dict[str, Any]], nid: str) -> Dict[str, Any]:
        key = nid[2:].split("~")[0].split("#")[0]        # 판(#2) · 열마다 나눈 벌(~3)은 같은 테이블
        multi = len(results) > 1
        readers, writers, name = [], [], key
        for fi, res in enumerate(results):
            pre = f"f{fi}:" if multi else ""
            for q in res.get("queries", []):
                for r in q["reads"]:
                    if r["key"] == key:
                        name = r["name"]
                        readers.append({"id": pre + q["id"], "n": q["n"], "var": q["var"], "file": ents[fi]["name"],
                                        "line": q["line"], "cols": flow1_graph.columns_of(q, key)})
                for w in q["writes"]:
                    if w["key"] == key:
                        name = w["name"]
                        writers.append({"id": pre + q["id"], "n": q["n"], "var": q["var"], "file": ents[fi]["name"],
                                        "line": q["line"], "kind": "query"})
            for o in res.get("outputs", []):
                if (o.get("table") or {}).get("key") == key:
                    writers.append({"id": pre + o["id"], "n": o["n"], "var": o["var"], "file": ents[fi]["name"],
                                    "line": o["line"], "kind": "output"})
        cols: List[str] = []
        for r in readers:
            cols += [c for c in r["cols"] if c not in cols]
        return {"id": nid, "kind": "table", "name": name, "key": key, "readers": readers, "writers": writers,
                "columns": cols}

    def run_list(self, key: str) -> Dict[str, Any]:
        e = self.watch.get(key)
        if e is None:
            raise KeyError(f"파일이 없습니다: {key}")
        out = []
        for r in self.runs_of(e):
            calls = r.get("calls") or []
            out.append({"id": r.get("run"), "live": bool(r.get("live")), "stale": bool(r.get("stale")),
                        "started": r.get("started", ""), "ended": r.get("ended", ""), "ms": r.get("ms"),
                        "ok": r.get("ok"), "exit": r.get("exit"), "error": r.get("error", ""), "calls": len(calls),
                        "failed": sum(1 for c in calls if not c.get("ok")),
                        "query_ms": round(sum(float(c.get("ms") or 0) for c in calls), 1)})
        return {"key": key, "name": e["name"], "runs": out, "dir": os.path.join(self.watch.runs_dir,
                                                                                 flow1_trace.script_key(e["path"]))
                if e.get("path") else ""}

    def watch_change(self, body: Dict[str, Any]) -> Dict[str, Any]:
        add = [str(body["add"])] if body.get("add") else []
        rem = [str(body["remove"])] if body.get("remove") else []
        if not add and not rem:
            raise ValueError("add 나 remove 에 경로를 주세요")
        try:
            notes = watch_edit(self.config_path, add, rem)
            cfg, _ = load_config(self.config_path, create=False)
        except ConfigError as e:
            raise ValueError(str(e))
        self.cfg["watch"] = cfg["watch"]
        self.cfg_sig = self._cfg_sig()
        self.watch.refresh(force=True)
        return dict(self.state(), notes=notes)

    def browse(self, path: str) -> Dict[str, Any]:
        return list_dir(path, self.watch)

    def open_file(self, body: Dict[str, Any]) -> Dict[str, Any]:
        key = self.watch.open(str(body.get("path") or ""))
        return dict(self.state(), opened=key)

    def close_file(self, body: Dict[str, Any]) -> Dict[str, Any]:
        self.watch.close(str(body.get("key") or ""))
        return self.state()

    def example(self) -> Dict[str, Any]:
        if not os.path.isdir(EXAMPLES):
            raise ValueError("예시 폴더가 없습니다 (tests/examples)")
        return self.watch_change({"add": EXAMPLES})

    def paste(self, body: Dict[str, Any]) -> Dict[str, Any]:
        e = self.watch.paste(body.get("text"), str(body.get("name") or ""))
        return dict(self.state(), added=e["key"])

    def unpaste(self, body: Dict[str, Any]) -> Dict[str, Any]:
        self.watch.unpaste(str(body.get("key") or ""))
        return self.state()

    def rescan(self) -> Dict[str, Any]:
        self.watch.refresh(force=True)
        return self.state()

    def shutdown(self) -> None:
        time.sleep(0.5)
        self.stop.set()
        if self.httpd is not None:
            self.httpd.shutdown()

    def idle_should_exit(self, now: Optional[float] = None) -> bool:
        limit = float(self.cfg.get("idle_exit_min") or 0) * 60
        return limit > 0 and (now or time.time()) - self.last_seen > limit

    def _loop(self) -> None:
        """감시 · 저절로 꺼지기"""
        poll = float(self.cfg["scan"]["poll_sec"])
        while not self.stop.wait(poll):
            try:
                if not self.reload_config():
                    self.watch.refresh()
            except Exception:
                log("감시 오류:\n" + traceback.format_exc())
            if self.idle_should_exit():
                log(f"{int(self.cfg['idle_exit_min'])}분 동안 쓰지 않아 끕니다")
                threading.Thread(target=self.shutdown, daemon=True).start()
                return

    def serve(self, port: int, open_window: bool = True) -> None:
        self.watch.refresh(force=True)
        self.httpd, self.port = bind_server(port, make_handler(self))
        self.allowed_hosts = {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}
        log(f"Flow-1 {VERSION} 실행 중 → {self.url}   (끄려면 창의 끄기 또는 Ctrl+C)")
        log(f"감시 {len(self.cfg['watch'])}곳 · 파일 {len(self.watch.order)}개 · 사내 쿼리 패키지: "
            f"{', '.join(self.cfg['query']['modules']) or '(설정 안 함 — SQL 모양 인자로 찾음)'}")
        threading.Thread(target=self._loop, daemon=True).start()
        if open_window:
            open_app_window(self.url)
        try:
            self.httpd.serve_forever(poll_interval=0.5)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop.set()
            self.httpd.server_close()
            log("Flow-1 종료")


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = not IS_WINDOWS

    def server_bind(self) -> None:
        socketserver.TCPServer.server_bind(self)     # getfqdn() 생략 (사내망에서 수 초씩 걸리기도 한다)
        host, port = self.server_address[:2]
        self.server_name, self.server_port = str(host), int(port)

    def handle_error(self, request: Any, client_address: Any) -> None:
        if isinstance(sys.exc_info()[1], (ConnectionError, socket.timeout)):
            return
        log("요청 처리 오류:\n" + traceback.format_exc())


def bind_server(port: int, handler: Any) -> Tuple[ThreadingHTTPServer, int]:
    last: Optional[Exception] = None
    for p in ([0] if port == 0 else range(port, port + 10)):
        try:
            srv = _Server(("127.0.0.1", p), handler)
            return srv, int(srv.server_address[1])
        except OSError as e:
            last = e
    raise OSError(f"포트 {port}~{port + 9} 를 열 수 없습니다: {last}")


FONT_URL = "/font/flow-1-dos.woff"
_FONT: List[bytes] = []


def font_bytes() -> bytes:
    if not _FONT:
        import flow1_assets
        _FONT.append(base64.b64decode(flow1_assets.FONT_WOFF_B64))
    return _FONT[0]


def make_handler(app: App) -> Any:
    class Handler(BaseHTTPRequestHandler):
        server_version = f"{APP}/{VERSION}"

        def log_message(self, fmt: str, *args: Any) -> None:
            pass

        def _send(self, code: int, body: bytes, ctype: str, cache: str = "no-store") -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            if body and self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, code: int, obj: Any) -> None:
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _host_ok(self) -> bool:
            return (self.headers.get("Host") or "").strip().lower() in app.allowed_hosts

        def _auth_ok(self) -> bool:
            return secrets.compare_digest(self.headers.get("X-Flow-Token", ""), app.token)

        def _body(self, limit: int) -> Dict[str, Any]:
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                raise ValueError("Content-Length 가 숫자가 아닙니다")
            if n < 0 or n > limit:
                raise ValueError("요청이 너무 큽니다" if n > limit else "요청 크기가 올바르지 않습니다")
            raw = self.rfile.read(n) if n else b""
            data = json.loads(raw.decode("utf-8")) if raw.strip() else {}
            if not isinstance(data, dict):
                raise ValueError("JSON 객체가 필요합니다")
            return data

        def _run(self, fn: Callable[[], Any]) -> None:
            try:
                return self._json(200, fn())
            except KeyError as e:
                return self._json(404, {"error": str(e).strip("'\"")})
            except (ValueError, OSError) as e:
                return self._json(400, {"error": str(e)})
            except Exception as e:
                log("요청 처리 오류:\n" + traceback.format_exc())
                return self._json(500, {"error": str(e)})

        def do_GET(self) -> None:
            u = urlparse(self.path)
            if not self._host_ok():
                return self._json(403, {"error": "forbidden host"})
            if u.path in ("/", "/index.html"):
                return self._send(200, app.render_index(), "text/html; charset=utf-8")
            if u.path == FONT_URL:        # @font-face 는 토큰 헤더를 못 보낸다 (공개해도 되는 정적 파일)
                return self._send(200, font_bytes(), "font/woff", cache="max-age=3600")
            if u.path == "/api/ping":
                return self._json(200, {"app": APP, "version": VERSION})
            if not u.path.startswith("/api/"):
                return self._json(404, {"error": "not found"})
            if not self._auth_ok():
                return self._json(401, {"error": "unauthorized"})
            app.last_seen = time.time()
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            if u.path == "/api/state":
                return self._run(app.state)
            if u.path == "/api/graph":
                return self._run(lambda: app.graph(q.get("f", "all"), int(q.get("d", "2") or 2), q.get("run", "")))
            if u.path == "/api/detail":
                return self._run(lambda: app.detail(q.get("f", "all"), q.get("id", "")))
            if u.path == "/api/runs":
                return self._run(lambda: app.run_list(q.get("f", "")))
            if u.path == "/api/browse":
                return self._run(lambda: app.browse(q.get("path", "")))
            if u.path == "/api/svg":
                try:
                    body = app.export_svg(q.get("f", "all"), int(q.get("d", "2") or 2), q.get("run", ""),
                                          q.get("theme", "dark"))
                except KeyError as e:
                    return self._json(404, {"error": str(e).strip("'\"")})
                return self._send(200, body.encode("utf-8"), "image/svg+xml; charset=utf-8")
            return self._json(404, {"error": "not found"})

        def do_POST(self) -> None:
            u = urlparse(self.path)
            if not self._host_ok():
                return self._json(403, {"error": "forbidden host"})
            if not self._auth_ok():
                return self._json(401, {"error": "unauthorized"})
            if "application/json" not in (self.headers.get("Content-Type") or ""):
                return self._json(415, {"error": "application/json 필요"})
            app.last_seen = time.time()
            try:
                body = self._body(MAX_PASTE * 3)
            except ValueError as e:
                return self._json(413 if "너무 큽니다" in str(e) else 400, {"error": str(e)})
            routes: Dict[str, Callable[[], Any]] = {
                "/api/watch": lambda: app.watch_change(body), "/api/paste": lambda: app.paste(body),
                "/api/paste/delete": lambda: app.unpaste(body), "/api/rescan": app.rescan,
                "/api/example": app.example, "/api/open": lambda: app.open_file(body),
                "/api/close": lambda: app.close_file(body)}
            if u.path in routes:
                return self._run(routes[u.path])
            if u.path == "/api/shutdown":
                self._json(200, {"ok": True})
                threading.Thread(target=app.shutdown, daemon=True).start()
                return None
            return self._json(404, {"error": "not found"})

    return Handler


# ─────────────────────────────────────────────────────────────── 04 창 · 실행 중 찾기 · 바로가기

_LOCAL_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _port_free(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if not IS_WINDOWS:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def find_running(port: int) -> Optional[str]:
    if not port:
        return None
    for p in range(port, port + 10):
        if _port_free(p):
            continue
        try:
            with _LOCAL_OPENER.open(f"http://127.0.0.1:{p}/api/ping", timeout=0.6) as r:
                d = json.loads(r.read().decode("utf-8"))
            if isinstance(d, dict) and d.get("app") == APP:
                return f"http://127.0.0.1:{p}/"
        except Exception:
            continue
    return None


def wait_running(port: int, seconds: float = 0.0) -> Optional[str]:
    end = time.time() + seconds
    while True:
        url = find_running(port)
        if url or time.time() >= end:
            return url
        time.sleep(0.5)


def stop_running(port: int) -> int:
    url = find_running(port)
    if not url:
        print("Flow-1 이 꺼져 있습니다.")
        return 0
    try:
        with _LOCAL_OPENER.open(url, timeout=5) as r:
            m = re.search(r'name="flow-token" content="([^"]+)"', r.read().decode("utf-8", "replace"))
        if not m:
            raise ValueError("토큰을 찾지 못했습니다")
        req = urllib.request.Request(url + "api/shutdown", data=b"{}", method="POST",
                                     headers={"X-Flow-Token": m.group(1), "Content-Type": "application/json"})
        with _LOCAL_OPENER.open(req, timeout=5) as r:
            r.read()
    except Exception as e:
        print(f"끄기 실패: {e}")
        return 1
    for _ in range(40):
        if not find_running(port):
            print("Flow-1 을 껐습니다.")
            return 0
        time.sleep(0.25)
    print("끄기 요청은 보냈지만 아직 켜져 있습니다.")
    return 1


def _find_browser() -> Optional[str]:
    env = os.environ
    cands = []
    for base in (env.get("ProgramFiles(x86)"), env.get("ProgramFiles"), env.get("LOCALAPPDATA")):
        if base:
            cands.append(os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"))
    for base in (env.get("ProgramFiles"), env.get("ProgramFiles(x86)"), env.get("LOCALAPPDATA")):
        if base:
            cands.append(os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"))
    for c in cands:
        if os.path.isfile(c):
            return c
    return shutil.which("msedge") or shutil.which("chrome")


def open_app_window(url: str) -> None:
    """Edge/Chrome '앱 모드'(주소창 없는 창)로 연다. 없으면 기본 브라우저"""
    if IS_WINDOWS:
        exe = _find_browser()
        if exe:
            try:
                subprocess.Popen([exe, f"--app={url}", "--window-size=1480,900"], close_fds=True)
                return
            except Exception as e:
                log(f"앱 창 열기 실패, 기본 브라우저로 엽니다: {e}")
    try:
        webbrowser.open(url)
    except Exception:
        log(f"브라우저를 열 수 없습니다. 직접 여세요: {url}")


def programs_dir() -> str:
    import ctypes
    buf = ctypes.create_unicode_buffer(1024)
    if ctypes.windll.shell32.SHGetFolderPathW(None, 2, None, 0, buf) != 0:  # type: ignore[attr-defined]
        raise OSError("시작 메뉴 폴더를 찾지 못했습니다")
    return buf.value


def set_shortcut(on: bool) -> int:
    """시작 메뉴에 'Flow-1' 바로가기를 만들거나 지운다 (사용자 동의 뒤에만 · INSTALL.md)"""
    if not IS_WINDOWS:
        print("시작 메뉴 바로가기는 Windows 에서만 만듭니다.")
        return 1
    try:
        lnk = os.path.join(programs_dir(), "Flow-1.lnk")
    except Exception as e:
        print(f"바로가기: {e}")
        return 1
    if not on:
        if os.path.exists(lnk):
            os.remove(lnk)
            print(f"바로가기 지움: {lnk}")
        else:
            print("바로가기가 없습니다.")
        return 0
    exe = sys.executable or "python"
    if os.path.basename(exe).lower() == "python.exe":
        alt = os.path.join(os.path.dirname(exe), "pythonw.exe")
        exe = alt if os.path.isfile(alt) else exe
    ps = ("$ErrorActionPreference='Stop';$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:FLOW_LNK);"
          "$s.TargetPath=$env:FLOW_EXE;$s.Arguments='\"'+$env:FLOW_PY+'\"';$s.WorkingDirectory=$env:FLOW_DIR;"
          "$s.Description='Flow-1 · 파이썬 데이터 쿼리 흐름도';$s.Save()")
    err = ""
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True,
                           timeout=30, creationflags=NO_WINDOW,
                           env=dict(os.environ, FLOW_LNK=lnk, FLOW_EXE=exe, FLOW_PY=os.path.abspath(__file__),
                                    FLOW_DIR=BASE_DIR))
        if r.returncode != 0:
            err = (r.stderr or r.stdout or b"").decode("utf-8", "replace").strip() or f"exit {r.returncode}"
    except Exception as e:
        err = str(e)
    if not err and os.path.exists(lnk):
        print(f"바로가기 만듦: {lnk} → 시작 메뉴에서 'Flow-1'")
        return 0
    print(f"바로가기 만들기 실패: {(err or '만들어지지 않았습니다')[:300]}")
    return 1


# ─────────────────────────────────────────────────────────────── 05 창 없이 (--scan · --json · --svg) · 점검

def expand(paths: List[str], cfg: Dict[str, Any]) -> List[str]:
    """파일 · 폴더 → 파일 목록 (폴더는 .py · .ipynb)"""
    out: List[str] = []
    w = Watch(dict(cfg, watch=[os.path.abspath(p) for p in paths]))
    for p in paths:
        if not os.path.exists(p):
            raise FileNotFoundError(p)
    for path, _root in w.list_files():
        if path not in out:
            out.append(path)
    return out


def cli_scan(cfg: Dict[str, Any], paths: List[str], fmt: str) -> int:
    try:
        files = expand(paths, cfg)
    except FileNotFoundError as e:
        print(f"없는 경로입니다: {e}", file=sys.stderr)
        return 2
    if not files:
        print("읽을 .py · .ipynb 파일이 없습니다", file=sys.stderr)
        return 2
    results = [flow1_scan.scan_file(f, scan_cfg(cfg)) for f in files]
    if fmt == "json":
        doc = {"format": flow1_scan.FORMAT, "app": APP, "version": VERSION, "files": results}
        text = json.dumps(doc, ensure_ascii=False, indent=1) + "\n"
    else:
        text = "\n".join(flow1_graph.summary(r) for r in results)
    try:
        sys.stdout.buffer.write(text.encode("utf-8"))
        sys.stdout.buffer.flush()
    except AttributeError:
        sys.stdout.write(text)
    return 1 if any(r.get("error") for r in results) else 0


def cli_svg(cfg: Dict[str, Any], out: str, paths: List[str], detail: int, theme: str) -> int:
    try:
        files = expand(paths, cfg)
    except FileNotFoundError as e:
        print(f"없는 경로입니다: {e}", file=sys.stderr)
        return 2
    results = [flow1_scan.scan_file(f, scan_cfg(cfg)) for f in files]
    results = [r for r in results if r["queries"]] or results
    if not results:
        print("읽을 .py · .ipynb 파일이 없습니다", file=sys.stderr)
        return 2
    import flow1_assets
    g = flow1_graph.build(results, detail)
    t = theme if theme in ("dark", "light") else ("light" if cfg.get("theme") == "light" else "dark")
    svg = flow1_graph.svg(g, standalone=True, theme=t, font_b64=flow1_assets.FONT_WOFF_B64.replace("\n", ""))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(svg)
    print(f"SVG 저장: {os.path.abspath(out)} ({g['width']}×{g['height']} · 쿼리 {g['stats']['queries']} · "
          f"테이블 {g['stats']['tables']})")
    return 0


def run_check(cfg: Dict[str, Any], config_path: str) -> int:
    """점검 — 0 OK · 1 점검 실패 · 3 사람 확인 필요 (마지막 줄은 main 이 찍는다)"""
    rc = 0
    print(f"Flow-1 {VERSION} 점검")
    print(f"- 파이썬    : {sys.version.split()[0]} · {sys.executable}")
    print(f"- 프로그램  : {BASE_DIR}")
    print(f"- 설정 파일 : {config_path}")
    home = cfg.get("_dir") or data_dir()
    runs = os.path.join(home, "runs")
    try:
        os.makedirs(runs, exist_ok=True)
        probe = os.path.join(runs, ".write-test")
        write_json(probe, {"ok": True})
        os.remove(probe)
        n = sum(len([x for x in os.listdir(os.path.join(runs, d)) if x.endswith(".json")])
                for d in os.listdir(runs) if os.path.isdir(os.path.join(runs, d)))
        print(f"- 데이터    : {home} · 실행 기록 {n}개")
    except OSError as e:
        print(f"- 데이터    : {home} 에 쓸 수 없습니다 ({e})")
        rc = 1
    mods = cfg["query"]["modules"]
    if not mods:
        print("- 쿼리 패키지: 설정 안 함 — SQL 모양 인자로만 찾습니다 (사내 패키지 이름을 넣으려면 "
              "--set \"query.modules=<패키지 이름>\")")
    for m in mods:
        try:
            found = importlib.util.find_spec(m.split(".")[0]) is not None
        except (ImportError, ValueError):
            found = False
        print(f"- 쿼리 패키지: {m} · " + ("이 파이썬에서 import 할 수 있음" if found else
                                       "이 파이썬에 없음 (정적 분석은 되지만, 스크립트를 --run 하려면 그 패키지가 있는 파이썬으로)"))
        if not found:
            rc = rc or 3
    print(f"- 찾는 호출 : {', '.join(cfg['query']['calls'])} · 출력 {', '.join(cfg['query']['sinks'])}")
    w = Watch(cfg)
    files = w.list_files()
    missing = [r for r in cfg["watch"] if not os.path.exists(r)]
    nq = nerr = 0
    bad = []
    for path, _root in files:
        res = flow1_scan.scan_file(path, scan_cfg(cfg))
        nq += len(res["queries"])
        if res["error"]:
            nerr += 1
            bad.append(os.path.basename(path))
    print(f"- 감시      : {len(cfg['watch'])}곳 · 파일 {len(files)}개" + (" (한도에서 멈춤)" if w.truncated else "")
          + f" · 쿼리 {nq}개" + (f" · 읽지 못한 파일 {nerr} ({', '.join(bad[:3])})" if nerr else ""))
    for r in missing:
        print(f"  ! 없는 경로: {r} → --remove \"{r}\"")
        rc = rc or 3
    ex = os.path.join(EXAMPLES, "daily_sales.py")
    if os.path.isfile(ex):
        res = flow1_scan.scan_file(ex, scan_cfg(cfg))
        st = res["stats"]
        ok = st.get("queries") == 6 and st.get("tables") == 6 and not res["error"]
        print(f"- 자체 시험 : 내장 예시 쿼리 {st.get('queries')} · 테이블 {st.get('tables')} · 조인 {st.get('joins')} · "
              + ("정상" if ok else "예상과 다름 (6 · 6) — 코드가 바뀌었는지 확인"))
        if not ok:
            rc = 1
    return rc


# ─────────────────────────────────────────────────────────────── 06 진입점

def main(argv: Optional[List[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass
    ap = argparse.ArgumentParser(prog=APP, description="Flow-1 · 파이썬 데이터 쿼리를 흐름도 한 장으로")
    ap.add_argument("paths", nargs="*", help="감시 목록에 더할 파일 · 폴더 (--scan · --json · --svg 에서는 읽을 곳)")
    ap.add_argument("--scan", action="store_true", help="창 없이 — 쿼리 · 조인 · 조건 · 흐름을 글로")
    ap.add_argument("--json", action="store_true", help="창 없이 — 분석 결과 JSON")
    ap.add_argument("--svg", metavar="파일", help="흐름도를 SVG 파일로 저장")
    ap.add_argument("--detail", type=int, choices=(1, 2, 3), default=2, help="--svg: 카드 상세 (1 간단 · 2 보통 · 3 전부)")
    ap.add_argument("--theme", choices=("dark", "light"), help="--svg: 색")
    ap.add_argument("--run", nargs=argparse.REMAINDER, metavar="스크립트", help="스크립트를 실행하며 쿼리 호출마다 시간 · 행 수 기록")
    ap.add_argument("--setup", action="store_true", help="설치 도우미: 설정 파일을 만들고 점검")
    ap.add_argument("--check", action="store_true", help="점검")
    ap.add_argument("--set", action="append", default=[], metavar="키=값", help="config.json 값 바꾸기 (여러 번 가능)")
    ap.add_argument("--remove", action="append", default=[], metavar="경로", help="감시 목록에서 빼기")
    ap.add_argument("--shortcut", choices=("on", "off"), help="시작 메뉴 바로가기 만들기/지우기 (Windows)")
    ap.add_argument("--status", action="store_true", help="실행 중인지 확인")
    ap.add_argument("--stop", action="store_true", help="실행 중인 Flow-1 끄기")
    ap.add_argument("--port", type=int, help="포트 (기본 config.port)")
    ap.add_argument("--no-window", action="store_true", help="창 자동 열기 끔")
    ap.add_argument("--config", default="", help="설정 파일 경로 (기본 %%LOCALAPPDATA%%\\flow-1\\config.json)")
    ap.add_argument("--version", action="version", version=f"Flow-1 {VERSION}")
    args = ap.parse_args(argv)
    config_path = os.path.abspath(args.config) if args.config else default_config_path()
    try:
        cfg, created = load_config(config_path, create=not (args.status or args.stop))
    except ConfigError as e:
        log(f"설정 오류: {e}")
        return 2
    if created:
        log(f"config.json 을 만들었습니다 → {config_path}")
    port = args.port if args.port is not None else int(cfg.get("port") or 8785)
    if args.set:
        rc = set_config_values(config_path, args.set)
        if rc or not (args.check or args.setup):
            return rc
        cfg, _ = load_config(config_path)
    if args.run is not None:
        if not args.run:
            print("--run 뒤에 실행할 스크립트를 주세요: python flow-1.py --run 스크립트.py [인자…]", file=sys.stderr)
            return 2
        script = os.path.abspath(args.run[0])
        if not os.path.isfile(script):
            print(f"없는 파일입니다: {script}", file=sys.stderr)
            return 2
        try:
            if not any(_covers(r, script) for r in cfg["watch"]):
                for note in watch_edit(config_path, [script], []):
                    log(note)
        except (ConfigError, OSError) as e:
            log(f"감시 목록에 더하지 못했습니다: {e}")
        running = find_running(port)
        log(f"화면: {running}" if running else "화면으로 보려면: python flow-1.py (켜 두면 실행하는 동안 카드가 바뀐다)")
        runs_dir = os.path.join(cfg.get("_dir") or data_dir(), "runs")
        return flow1_trace.run_script(script, args.run[1:], scan_cfg(cfg), runs_dir, int(cfg["run"]["keep"]))
    if args.scan or args.json:
        if not args.paths:
            print("읽을 파일 · 폴더를 주세요: python flow-1.py --scan 경로", file=sys.stderr)
            return 2
        return cli_scan(cfg, args.paths, "json" if args.json else "text")
    if args.svg:
        if not args.paths:
            print("읽을 파일 · 폴더를 주세요: python flow-1.py --svg 흐름.svg 경로", file=sys.stderr)
            return 2
        return cli_svg(cfg, args.svg, args.paths, args.detail, args.theme or "")
    if args.remove:
        try:
            for note in watch_edit(config_path, [], args.remove):
                print(note)
        except ConfigError as e:
            print(e)
            return 2
        return 0
    if args.setup or args.check:
        if args.setup:
            print(f"Flow-1 {VERSION} 설치 도우미 — 설정 파일: {config_path}" + (" (새로 만듦)" if created else " (이미 있음)"))
            print()
        rc = run_check(cfg, config_path)
        tail = {0: "결과: OK", 3: "결과: 확인 필요 (코드 3) · 위의 ! · 쿼리 패키지 줄을 사용자와 확인"}
        print("\n" + tail.get(rc, "결과: 점검 실패 (코드 1) · 위 메시지와 INSTALL.md 의 '문제 해결' 표를 보고 고친 뒤 --check"))
        return rc
    if args.shortcut:
        return set_shortcut(args.shortcut == "on")
    if args.status:
        url = wait_running(port, 8)
        print(f"실행 중: {url}" if url else "꺼져 있음")
        return 0 if url else 1
    if args.stop:
        return stop_running(port)
    if args.paths:
        try:
            for note in watch_edit(config_path, args.paths, []):
                log(note)
            cfg, _ = load_config(config_path)
        except ConfigError as e:
            log(str(e))
            return 2
    running = find_running(port)
    if running:
        log(f"이미 실행 중입니다 → 창만 엽니다: {running}")
        if not args.no_window:
            open_app_window(running)
        return 0
    app = App(cfg, config_path)
    app.serve(port, open_window=bool(cfg.get("open_window", True)) and not args.no_window)
    return 0


if __name__ == "__main__":
    sys.exit(main())
