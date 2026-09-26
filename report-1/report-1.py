#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Report–1 - 근거 달린 보고서 (내 PC에서만 · Python 3.8+ · 이 파일 하나가 전부)

[실행]
  python report-1.py              창을 연다 (처음이면 %LOCALAPPDATA%\report-1\config.json 을 만든다)
  python report-1.py --setup      설치 도우미: OpenCode 설정에서 사내 LLM 값을 가져오고 점검까지
  python report-1.py --check      LLM 점검 (마지막 줄 '결과: …')
  python report-1.py --draft a.txt b.txt --topic "9월 서버 장애"
                                  파일을 자료로 초안을 글로만 출력 (--form "이슈 보고" · --basic 은 LLM 없이 · - 는 표준 입력)
  기타: --set 키=값 · --status · --stop · --shortcut on|off (시작 메뉴) · --no-window · --port 8775 · --config 경로

[자료] 토픽 하나에 메일 · 메신저 · 회의 메모 · 기사 · 엑셀 표를 순서 없이 붙여 넣는다
  붙여 넣은 것 하나 = 자료 하나 (a1, a2 …). 자료는 조각(p1, p2 …)으로 나뉜다. 같은 조각 · 메일 인용(>) 줄은 건너뛴다
  보고서의 줄마다 근거 조각이 붙는다
    사실 · 추론 · 확인 줄에 근거가 없으면 ERR — 확정할 수 없다
    추론 = 조각을 이어 LLM 이 내린 판단 · 확인 = 조각끼리 다름 · 빈칸 = 양식 칸에 필요한데 자료에 없음
    근거 조각에 없는 숫자(10 이상 · 소수)는 '숫자?' 로 표시한다 · 사람이 고친 줄은 '직접'

[config.json]  %LOCALAPPDATA%\report-1\config.json  (REPORT_HOME 으로 폴더를 바꿀 수 있다)
  llm.*                 사내 LLM (docs/SPEC-llm.md 와 같은 키). 비워 두면 기본 초안(자료를 그대로 묶기)만
  report.forms          양식 이름 → 칸 이름 목록 (빈 목록 = 칸을 LLM 이 정함) · report.summary 맨 위 요약 칸
  report.budget_chars   LLM 에 한 번에 보낼 자료 글자 수 한도 (사내 LLM 입력 한도에 맞춘다)
  theme · port(8775) · open_window · idle_exit_min(창을 닫고 이만큼 지나면 저절로 꺼짐, 0 = 안 꺼짐)
  company               화면 위 이름 옆에 작게 넣는 회사 이름 (비우면 없음 · 저장소에는 넣지 않고 이 PC 설정에만)

[보안 · 저장]
  127.0.0.1 에만 열리고 실행마다 새 토큰 · 밖으로 나가는 통신은 설정한 LLM 주소 하나
  붙여 넣은 원문은 메모리에만 둔다. '보관' 을 누른 토픽만 저장 (topics\) · 확정한 보고서는 복사한 글 그대로 (reports\)
  보관 안 한 자료가 있으면 창을 닫아도 저절로 꺼지지 않는다 (다시 열면 그대로)
  사내 LLM 에 보내는 것은 화면에서 체크된 조각뿐

[폰트]
  도스풍 픽셀 폰트를 이 파일 안에 내장 (GNU Unifont 15.1.01 부분집합 · SIL OFL 1.1 · fonts/OFL.txt)
"""
from __future__ import annotations

import argparse
import base64
import copy
import json
import os
import re
import secrets
import shutil
import socket
import socketserver
import ssl
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import webbrowser
from dataclasses import asdict, dataclass, field
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

APP = "report-1"            # 명령 · 파일 · 데이터 폴더 이름
NAME = "Report–1"           # 화면에 보이는 이름
VERSION = "0.2.0"
ENV = "REPORT"              # 환경 변수 접두어 (docs/REGISTRY.md)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IS_WINDOWS = sys.platform == "win32"
NO_WINDOW = 0x08000000 if IS_WINDOWS else 0   # 자식 프로세스 콘솔 창을 띄우지 않음


def log(msg: str) -> None:
    """로그는 표준 오류로 — 표준 출력은 --draft 의 보고서 글만 쓴다"""
    try:
        print(f"[{datetime.now():%H:%M:%S}] {msg}", file=sys.stderr, flush=True)
    except Exception:
        pass


def data_dir() -> str:
    """%LOCALAPPDATA%\\report-1 (Windows 밖: ~/.local/share/report-1). REPORT_HOME 이 있으면 그 폴더"""
    if os.environ.get(ENV + "_HOME"):
        return os.path.abspath(os.environ[ENV + "_HOME"])
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, APP)


def default_config_path() -> str:
    return os.path.join(data_dir(), "config.json")


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


# ─────────────────────────────────────────────────────────────── 설정

DEFAULT_CONFIG: Dict[str, Any] = {
    "llm": {
        "base_url": "",
        "api_key": "",
        "model": "",
        "models": [],
        "temperature": 0.2,
        "max_tokens": 2048,
        "timeout_sec": 90,
        "extra_headers": {},
        "proxy": None,
        "ca_file": "",
    },
    "report": {
        "forms": {
            "현황 보고": ["개요", "현황", "문제점", "향후 계획"],
            "이슈 보고": ["현상", "원인", "영향", "조치", "요청 사항"],
            "검토 보고": ["검토 배경", "검토 내용", "대안", "검토 의견"],
            "회의 결과": ["회의 개요", "논의 내용", "결정 사항", "후속 조치"],
            "자유 구성": [],
        },
        "summary": True,
        "budget_chars": 20000,
    },
    "theme": "dark",
    "company": "",
    "port": 8775,
    "open_window": True,
    "idle_exit_min": 30,
}
SUMMARY = "요약"


class ConfigError(Exception):
    pass


def deep_merge(base: Dict[str, Any], over: Dict[str, Any]) -> Dict[str, Any]:
    """깊은 복사로 합친다 — 결과를 고쳐도 DEFAULT_CONFIG 가 바뀌지 않게 (환경 변수의 키가 기본값에 섞여 파일로 새지 않게)"""
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


_REF_RE = re.compile(r"\{(env|file):([^{}]+)\}")


def resolve_refs(value: Any, base_dir: Optional[str] = None) -> str:
    """"{env:이름}" → 환경변수 값, "{file:경로}" → 파일 내용 (OpenCode 설정과 같은 문법 · docs/SPEC-llm.md)"""
    def sub(m: Any) -> str:
        kind, arg = m.group(1), m.group(2).strip()
        if kind == "env":
            return os.environ.get(arg, "")
        path = os.path.expanduser(arg)
        if not os.path.isabs(path):
            path = os.path.join(base_dir or data_dir(), path)
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                return f.read().strip()
        except OSError:
            return ""
    return _REF_RE.sub(sub, "" if value is None else str(value))


def _read_user_config(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ConfigError(f"{path} 의 최상위는 {{ }} 객체여야 합니다")
    return data


def _write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def load_config(path: str, create: bool = True) -> Tuple[Dict[str, Any], bool]:
    created = False
    user: Dict[str, Any] = {}
    if os.path.exists(path):
        try:
            user = _read_user_config(path)
        except ValueError as e:
            raise ConfigError(f"{path} 형식 오류: {e}")
    elif create:
        try:
            _write_json(path, DEFAULT_CONFIG)
        except OSError as e:
            raise ConfigError(f"{path} 를 만들 수 없습니다: {e}")
        created = True
    cfg = deep_merge(DEFAULT_CONFIG, user)
    rep = user.get("report")
    if isinstance(rep, dict) and isinstance(rep.get("forms"), dict):
        cfg["report"]["forms"] = copy.deepcopy(rep["forms"])   # 사용자가 정한 양식은 기본 양식과 섞지 않는다 (지운 양식이 되살아나지 않게)
    for key in ("base_url", "api_key", "model"):   # docs/SPEC-llm.md › 02
        val = os.environ.get(f"{ENV}_{key.upper()}")
        if val:
            cfg["llm"][key] = val
    cfg["_dir"] = os.path.dirname(os.path.abspath(path))
    validate_config(cfg)
    return cfg, created


def validate_config(cfg: Dict[str, Any]) -> None:
    llm = cfg.get("llm") or {}
    if not isinstance(llm.get("models", []), list) or not all(isinstance(m, str) for m in llm.get("models", [])):
        raise ConfigError('llm.models 는 모델 이름 목록이어야 합니다. 예: ["qwen3-32b"]')
    rep = cfg.get("report")
    if not isinstance(rep, dict):
        raise ConfigError("report 는 { } 객체여야 합니다")
    forms = rep.get("forms")
    if not isinstance(forms, dict) or not forms:
        raise ConfigError('report.forms 는 양식 이름 → 칸 이름 목록입니다. 예: {"이슈 보고": ["현상", "원인", "조치"]}')
    clean: Dict[str, List[str]] = {}
    for name, secs in forms.items():
        n = str(name).strip()
        if not n or len(n) > 20:
            raise ConfigError(f"양식 이름은 1~20자입니다: {name!r}")
        if not isinstance(secs, list) or len(secs) > 8 \
                or not all(isinstance(s, str) and s.strip() and len(s.strip()) <= 20 for s in secs):
            raise ConfigError(f"report.forms 의 '{n}' 는 칸 이름 목록이어야 합니다 (최대 8칸 · 칸 이름 20자까지 · 빈 목록 = 자유 구성)")
        ss = [s.strip() for s in secs]
        if len(set(ss)) != len(ss):
            raise ConfigError(f"report.forms 의 '{n}' 에 같은 칸 이름이 두 번 있습니다")
        clean[n] = ss
    rep["forms"] = clean
    rep["summary"] = bool(rep.get("summary", True))
    try:
        rep["budget_chars"] = min(1_000_000, max(1000, int(rep.get("budget_chars", 20000))))
        cfg["port"] = int(cfg.get("port") or 8775)
        cfg["idle_exit_min"] = max(0.0, float(cfg.get("idle_exit_min", 30)))
    except (TypeError, ValueError):
        raise ConfigError("report.budget_chars · port · idle_exit_min 은 숫자여야 합니다")
    cfg["theme"] = str(cfg.get("theme") or "dark").strip().lower()
    if cfg["theme"] not in ("dark", "light", "system"):
        raise ConfigError('theme 는 "dark", "light", "system" 중 하나여야 합니다')
    cfg["company"] = check_company(cfg.get("company"))


def check_company(value: Any) -> str:
    """화면에 넣는 회사 이름 — 글자만, 24자까지 (비우면 없음)"""
    if value is None:
        return ""
    if not isinstance(value, str) or len(value.strip()) > 24 or re.search(r"[\x00-\x1f\x7f]", value):
        raise ConfigError("company 는 24자까지의 글자여야 합니다 (예: --set company=회사이름 · 비우려면 --set company=)")
    return value.strip()


def sections_of(cfg: Dict[str, Any], form: str) -> Tuple[List[str], bool]:
    """양식의 칸 이름 (맨 위 요약 포함) · 자유 구성이면 (요약만, True)"""
    rep = cfg["report"]
    body = [s for s in rep["forms"].get(form, []) if not (rep["summary"] and s == SUMMARY)]
    head = [SUMMARY] if rep["summary"] else []
    return head + body, not rep["forms"].get(form)


# ─────────────────────────────────────────────────────────────── 저장 (보관한 토픽 · 확정한 보고서)

class JsonDoc:
    """내 PC 의 JSON 파일 하나 ({"version": N, …}) — RULES.md › W-06.
    깨져 있으면 .broken 으로 백업하고 새로 시작 · 더 새 버전이 쓴 파일이면 읽기만 · 쓰기는 .tmp 에 쓴 뒤 바꿔치기"""

    VERSION = 1

    def __init__(self, path: str, what: str):
        self.path, self.what = path, what
        self.error = ""
        self.readonly = False

    def load(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            return {}
        try:
            with open(self.path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("최상위가 { } 가 아님")
        except Exception as e:
            self.error = f"{self.what} 파일을 읽지 못해 새로 시작합니다 ({e})"
            log(self.error)
            try:
                shutil.copyfile(self.path, self.path + ".broken")
            except OSError:
                pass
            return {}
        v = data.get("version")
        if isinstance(v, int) and v > self.VERSION:
            self.readonly = True
            self.error = f"{self.what} 파일을 더 새 버전의 {NAME} 이 썼습니다 — 읽기만 합니다 (업데이트하세요)"
        return data

    def save(self, data: Dict[str, Any]) -> None:
        if self.readonly:
            raise OSError(self.error)
        _write_json(self.path, dict(data, version=self.VERSION))
        self.error = ""


class Folder:
    """JSON 파일이 쌓이는 폴더 하나 (topics · reports). 파일 이름은 id 규칙에 맞는 것만 받는다"""

    ID_RE = re.compile(r"[0-9A-Za-z\-]{4,40}")

    def __init__(self, folder: str, what: str):
        self.folder, self.what = folder, what

    def path(self, key: str) -> str:
        if not self.ID_RE.fullmatch(key or ""):
            raise ValueError(f"잘못된 {self.what} 이름: {key}")
        return os.path.join(self.folder, key + ".json")

    def new_key(self, prefix: str = "") -> str:
        base = prefix + datetime.now().strftime("%Y%m%d-%H%M%S")
        key, n = base, 1
        while os.path.exists(self.path(key)):
            n += 1
            key = f"{base}-{n}"
        return key

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        doc = JsonDoc(self.path(key), self.what)
        data = doc.load()
        if data and doc.readonly:
            data["readonly"] = True
        return data or None

    def save(self, key: str, data: Dict[str, Any]) -> None:
        doc = JsonDoc(self.path(key), self.what)
        doc.load()   # 더 새 버전이 쓴 파일은 덮어쓰지 않는다
        doc.save(data)

    def delete(self, key: str) -> Optional[Dict[str, Any]]:
        """지우고 지운 내용을 돌려준다 (되돌리기용)"""
        before = self.get(key)
        if os.path.exists(self.path(key)):
            os.remove(self.path(key))
        return before

    def keys(self) -> List[str]:
        if not os.path.isdir(self.folder):
            return []
        out = [n[:-5] for n in os.listdir(self.folder) if n.endswith(".json") and self.ID_RE.fullmatch(n[:-5])]
        return sorted(out, reverse=True)


# ─────────────────────────────────────────────────────────────── 자료 · 조각

MAX_PASTE = 100_000     # 한 번에 붙여 넣을 수 있는 글자 수
MAX_DESK = 400_000      # 토픽 하나의 자료 전체 글자 수
MAX_FRAGS = 3000        # 토픽 하나의 조각 수
FRAG_MAX = 420          # 조각 하나의 최대 글자 수 (넘으면 줄 · 문장 단위로 자른다)
FRAG_MIN = 60           # 이보다 짧은 조각은 다음 조각과 묶는다
KIND_KO = {"mail": "메일", "chat": "대화", "table": "표", "text": "글", "memo": "메모"}

_MAIL_RE = re.compile(r"^\s*(from|to|cc|sent|date|subject|보낸\s*사람|받는\s*사람|참조|보낸\s*날짜|날짜|제목)\s*:",
                      re.I | re.M)
_SUBJECT_RE = re.compile(r"^\s*(?:subject|제목)\s*:\s*(.+)$", re.I | re.M)
_CHAT_RE = re.compile(r"^\s*(?:\[[^\]\n]{1,24}\]\s*\[(?:오전|오후)\s*\d{1,2}:\d{2}\]|(?:오전|오후)\s*\d{1,2}:\d{2}\b"
                      r"|\d{1,2}:\d{2}\s*(?:AM|PM)?\s)", re.I | re.M)
_RULE_RE = re.compile(r"^[\s\-=_*~·•.#]{3,}$")    # 구분선만 있는 줄
_SENT_RE = re.compile(r"(?<=[.!?。…])\s+")


def clean_text(text: Any) -> str:
    t = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"[​‌‍﻿­]", "", t).replace(" ", " ")


def frag_key(text: str) -> str:
    """같은 조각 찾기용 — 띄어쓰기 · 문장부호를 빼고 비교한다"""
    return re.sub(r"[\W_]+", "", text).lower()


def detect_kind(t: str) -> str:
    lines = [ln for ln in t.split("\n") if ln.strip()]
    if len(lines) >= 2 and sum(1 for ln in lines if "\t" in ln) >= max(2, int(len(lines) * 0.6)):
        return "table"
    if len(_MAIL_RE.findall(t)) >= 2:
        return "mail"
    if len(_CHAT_RE.findall(t)) >= 3:
        return "chat"
    return "text"


def _cut(text: str, limit: int) -> List[str]:
    """limit 보다 긴 한 줄을 문장 → 띄어쓰기 순으로 자른다"""
    parts: List[str] = []
    for s in _SENT_RE.split(text):
        while len(s) > limit:
            i = s.rfind(" ", 0, limit)
            i = i if i >= limit // 2 else limit
            parts.append(s[:i].strip())
            s = s[i:].strip()
        if s:
            parts.append(s)
    out, cur = [], ""
    for s in parts:
        if cur and len(cur) + 1 + len(s) > limit:
            out.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        out.append(cur)
    return out


def _split_table(lines: List[str]) -> List[str]:
    rows = [[c.strip() for c in ln.split("\t")] for ln in lines if ln.strip()]
    head = rows[0]
    use_head = len(rows) > 1 and all(h and len(h) <= 30 and not re.fullmatch(r"[\d,.\-%\s]+", h) for h in head)
    out = []
    for r in rows[1:] if use_head else rows:
        if use_head:
            parts = [f"{head[i] if i < len(head) and head[i] else f'열{i + 1}'}: {c}" for i, c in enumerate(r) if c]
        else:
            parts = [c for c in r if c]
        if parts:
            out.extend(_cut(" · ".join(parts), FRAG_MAX))
    return out


def split_paste(text: Any) -> Dict[str, Any]:
    """붙여 넣은 글 → {kind, title, frags[글], quotes(건너뛴 인용 줄 수)}"""
    t = clean_text(text)
    kind = detect_kind(t)
    lines = t.split("\n")
    quotes = 0
    if kind == "table":
        frags = _split_table(lines)
        cols = max((len(ln.split("\t")) for ln in lines if ln.strip()), default=0)
        first = [c.strip() for c in next((ln for ln in lines if ln.strip()), "").split("\t") if c.strip()]
        title = f"{' · '.join(first[:3])} … ({len(frags)}행 × {cols}열)" if first else f"표 ({len(frags)}행)"
    else:
        blocks: List[List[str]] = [[]]
        for ln in lines:
            s = ln.strip()
            if s.startswith(">"):
                quotes += 1
                continue
            if not s or _RULE_RE.fullmatch(s):
                if blocks[-1]:
                    blocks.append([])
                continue
            blocks[-1].append(s)
        pieces: List[str] = []
        for b in blocks:
            cur = ""
            for s in b:
                for seg in ([s] if len(s) <= FRAG_MAX else _cut(s, FRAG_MAX)):
                    if cur and len(cur) + 1 + len(seg) > FRAG_MAX:
                        pieces.append(cur)
                        cur = seg
                    else:
                        cur = f"{cur}\n{seg}" if cur else seg
            if cur:
                pieces.append(cur)
        frags = []
        for p in pieces:   # 아주 짧은 조각(인사 · 머리글 한 줄)은 다음 조각과 묶는다
            if frags and len(frags[-1]) < FRAG_MIN and len(frags[-1]) + 1 + len(p) <= FRAG_MAX:
                frags[-1] = frags[-1] + "\n" + p
            else:
                frags.append(p)
        m = _SUBJECT_RE.search(t) if kind == "mail" else None
        first = m.group(1) if m else next((s for b in blocks for s in b if len(s) >= 4), "")
        title = first
    if kind == "chat":   # [이름] [오후 2:10] 머리를 뗀 첫 말
        title = re.sub(r"^\s*(?:\[[^\]]*\]\s*)+", "", title)
    title = re.sub(r"\s+", " ", title).strip()
    return {"kind": kind, "title": _short(title, 40) or KIND_KO[kind], "frags": frags, "quotes": quotes}


@dataclass
class Frag:
    id: str          # p1
    paste: str       # a1
    text: str


@dataclass
class Paste:
    id: str          # a1
    kind: str        # mail · chat · table · text · memo
    title: str
    added: str
    frags: List[str] = field(default_factory=list)
    chars: int = 0
    dups: int = 0    # 이미 있는 조각이라 건너뛴 수
    quotes: int = 0  # 건너뛴 메일 인용(>) 줄 수


class Desk:
    """지금 쓰고 있는 토픽 하나 — 메모리에만 있다. 보관(save)하면 topics\\ 에 저장된다 (RULES.md › W-05)"""

    def __init__(self, form: str):
        self.topic = ""
        self.form = form
        self.pastes: List[Paste] = []
        self.frags: Dict[str, Frag] = {}
        self.exclude: Set[str] = set()
        self.next_a = 1
        self.next_p = 1
        self.saved_id = ""
        self.dirty = False
        self.created = now_iso()

    # 읽기
    def unsaved(self) -> bool:
        """보관 안 한 자료가 있나 — 있으면 창을 닫아도 서버가 기다린다"""
        return self.dirty and bool(self.pastes)

    def known(self) -> Dict[str, Frag]:
        """체크된 조각 (초안 · LLM · 근거 판정에 쓰는 것)"""
        return {k: f for k, f in self.frags.items() if k not in self.exclude}

    def chars(self, included_only: bool = True) -> int:
        src = self.known() if included_only else self.frags
        return sum(len(f.text) for f in src.values())

    def paste_of(self) -> Dict[str, Paste]:
        return {p.id: p for p in self.pastes}

    # 쓰기
    def add(self, text: Any, memo: bool = False) -> Paste:
        raw = clean_text(text)
        if not raw.strip():
            raise ValueError("붙여 넣은 글이 비어 있습니다")
        if len(raw) > MAX_PASTE:
            raise ValueError(f"한 번에 {MAX_PASTE:,}자까지 붙여 넣을 수 있습니다 (지금 {len(raw):,}자) — 나눠서 붙여 넣으세요")
        if self.chars(False) + len(raw) > MAX_DESK:
            raise ValueError(f"토픽 하나의 자료는 {MAX_DESK:,}자까지입니다 — 필요 없는 자료를 지우세요")
        sp = split_paste(raw)
        if memo:
            sp["kind"] = "memo"
        seen = {frag_key(f.text) for f in self.frags.values()}
        p = Paste(f"a{self.next_a}", sp["kind"], sp["title"], now_iso(), quotes=sp["quotes"])
        new: List[Frag] = []
        for t in sp["frags"]:
            key = frag_key(t)
            if len(key) < 2:
                continue
            if key in seen:
                p.dups += 1
                continue
            seen.add(key)
            new.append(Frag(f"p{self.next_p + len(new)}", p.id, t))
        if not new:
            raise ValueError("새 내용이 없습니다 — 이미 붙여 넣은 조각뿐입니다" if p.dups else "쓸 수 있는 글이 없습니다")
        if len(self.frags) + len(new) > MAX_FRAGS:
            raise ValueError(f"조각이 {MAX_FRAGS:,}개를 넘습니다 — 필요 없는 자료를 지우세요")
        self.next_a += 1
        self.next_p += len(new)
        p.frags = [f.id for f in new]
        p.chars = sum(len(f.text) for f in new)
        self.pastes.append(p)
        self.frags.update({f.id: f for f in new})
        self.dirty = True
        return p

    def remove(self, aid: str) -> Dict[str, Any]:
        """자료 하나를 지우고 되돌리기용 조각을 돌려준다 (id 는 다시 쓰지 않는다)"""
        i = next((i for i, p in enumerate(self.pastes) if p.id == aid), -1)
        if i < 0:
            raise KeyError(f"없는 자료: {aid}")
        p = self.pastes.pop(i)
        frags = {k: self.frags.pop(k) for k in p.frags if k in self.frags}
        off = [k for k in p.frags if k in self.exclude]
        self.exclude -= set(p.frags)
        self.dirty = True
        return {"index": i, "paste": p, "frags": frags, "exclude": off}

    def restore(self, snap: Dict[str, Any]) -> None:
        self.pastes.insert(min(snap["index"], len(self.pastes)), snap["paste"])
        self.frags.update(snap["frags"])
        self.frags = dict(sorted(self.frags.items(), key=lambda kv: int(kv[0][1:])))
        self.exclude |= set(snap["exclude"])
        self.dirty = True

    # 화면 · 파일
    def view(self, budget: int) -> Dict[str, Any]:
        return {"topic": self.topic, "form": self.form, "saved_id": self.saved_id, "dirty": self.dirty,
                "unsaved": self.unsaved(), "exclude": sorted(self.exclude, key=lambda k: int(k[1:])),
                "chars": self.chars(), "total": self.chars(False), "budget": budget,
                "pastes": [dict(asdict(p), kind_ko=KIND_KO.get(p.kind, p.kind),
                                frags=[{"id": k, "text": self.frags[k].text} for k in p.frags if k in self.frags])
                           for p in self.pastes]}

    def to_doc(self) -> Dict[str, Any]:
        return {"topic": self.topic, "form": self.form, "created": self.created, "updated": now_iso(),
                "next_a": self.next_a, "next_p": self.next_p, "exclude": sorted(self.exclude),
                "pastes": [dict(asdict(p), frags=[{"id": k, "text": self.frags[k].text} for k in p.frags
                                                  if k in self.frags]) for p in self.pastes]}

    @classmethod
    def from_doc(cls, doc: Dict[str, Any], forms: Dict[str, List[str]], default_form: str) -> "Desk":
        d = cls(doc.get("form") if doc.get("form") in forms else default_form)
        d.topic = str(doc.get("topic") or "")[:80]
        d.created = str(doc.get("created") or now_iso())
        for x in doc.get("pastes") or []:
            if not isinstance(x, dict) or not re.fullmatch(r"a\d+", str(x.get("id", ""))):
                continue
            fr = [f for f in x.get("frags") or [] if isinstance(f, dict) and re.fullmatch(r"p\d+", str(f.get("id", "")))
                  and str(f.get("text") or "").strip() and f["id"] not in d.frags]
            if not fr:
                continue
            kind = x.get("kind") if x.get("kind") in KIND_KO else "text"
            p = Paste(x["id"], kind, str(x.get("title") or "")[:60], str(x.get("added") or ""),
                      [f["id"] for f in fr], sum(len(str(f["text"])) for f in fr),
                      int(x.get("dups") or 0), int(x.get("quotes") or 0))
            d.pastes.append(p)
            d.frags.update({f["id"]: Frag(f["id"], p.id, str(f["text"])) for f in fr})
        d.exclude = {k for k in doc.get("exclude") or [] if k in d.frags}
        top_a = max([int(p.id[1:]) for p in d.pastes] + [0])
        top_p = max([int(k[1:]) for k in d.frags] + [0])
        d.next_a = max(top_a + 1, int(doc.get("next_a") or 1))
        d.next_p = max(top_p + 1, int(doc.get("next_p") or 1))
        return d


# ─────────────────────────────────────────────────────────────── 초안 · 근거 판정

LINE_KINDS = ("fact", "infer", "check", "gap")
KIND_ALIAS = {"사실": "fact", "추론": "infer", "판단": "infer", "확인": "check", "충돌": "check", "빈칸": "gap",
              "자료 없음": "gap", "conflict": "check", "inference": "infer", "missing": "gap"}
TONES = {"brief": "개조식 — 명사형으로 짧게 끝낸다 ('~완료', '~필요', '~예정')",
         "prose": "서술식 — '~했습니다', '~입니다' 로 끝나는 짧은 문장"}
DETAILS = {1: ("짧게", 3), 2: ("보통", 6), 3: ("자세히", 10)}          # 칸마다 최대 줄 수
AUDIENCES = {"team": ("팀 내부", "실무 세부(담당 · 일정 · 수치)를 빠짐없이"),
             "boss": ("상사", "핵심 사실과 판단, 필요한 요청 중심으로"),
             "exec": ("임원", "결론 · 숫자 · 결정이 필요한 사항만, 세부는 뺀다")}
SUMMARY_MAX = 3


@dataclass
class Line:
    section: int                  # 칸 번호 (요약이 있으면 0 = 요약)
    text: str
    refs: List[str] = field(default_factory=list)
    kind: str = "fact"            # fact 사실 · infer 추론 · check 자료끼리 다름 · gap 자료 없음
    level: int = 1                # 1 큰 항목 · 2 세부
    origin: str = "llm"           # llm · basic · user
    state: str = ""               # ok · infer · check · gap · err(근거 없음) · user(사람이 씀)
    nums: List[str] = field(default_factory=list)   # 근거 조각에 없는 숫자


_NUM_RE = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")


def numbers(text: str) -> List[str]:
    """글 속의 숫자를 비교할 수 있는 모양으로 (1,500 → 1500 · 09 → 9 · 3.50 → 3.5)"""
    out = []
    for m in _NUM_RE.finditer(text or ""):
        s = m.group(0).replace(",", "")
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        ip, dot, fp = s.partition(".")
        out.append((ip.lstrip("0") or "0") + (dot + fp if fp else ""))
    return out


def unsupported_numbers(text: str, sources: List[str]) -> List[str]:
    """줄의 숫자 가운데 근거 조각에 없는 것 (한 자리 정수는 세지 않는다 — '3건' 처럼 센 숫자가 흔해서)"""
    have: Set[str] = set()
    for s in sources:
        have.update(numbers(s))
    out = []
    for n in numbers(text):
        if (n.isdigit() and int(n) < 10) or n in have or n in out:
            continue
        out.append(n)
    return out


def judge(line: Line, known: Dict[str, Frag]) -> Line:
    """근거 id 를 걸러내고 줄의 상태를 정한다 — 서버가 매번 다시 한다 (LLM 도 화면도 믿지 않는다)"""
    refs: List[str] = []
    for r in line.refs:
        r = str(r).strip().strip("[]()").lower()
        if r in known and r not in refs:
            refs.append(r)
    kind = line.kind if line.kind in LINE_KINDS else "fact"
    nums: List[str] = []
    if line.origin == "user":
        state = "user"
    elif kind == "gap":
        state, refs = "gap", []
    elif not refs:
        state = "err"
    else:
        state = {"fact": "ok", "infer": "infer", "check": "check"}[kind]
        nums = unsupported_numbers(line.text, [known[r].text for r in refs])
    return Line(line.section, line.text, refs, kind, 2 if line.level == 2 else 1, line.origin, state, nums)


def basic_draft(known: Dict[str, Frag], pastes: Dict[str, Paste], sections: List[str], max_lines: int,
                summary: bool) -> List[Line]:
    """LLM 없이 — 자료마다 제목 한 줄 + 앞 조각 몇 개를 첫 칸에 그대로 묶고, 나머지 칸은 빈칸으로"""
    first = 1 if summary and len(sections) > 1 else 0
    lines: List[Line] = []
    if summary and len(sections) > 1:
        lines.append(Line(0, "", [], "gap", 1, "basic"))   # 요약은 사람이 — '+ 줄' 로
    by_paste: Dict[str, List[Frag]] = {}
    for f in known.values():
        by_paste.setdefault(f.paste, []).append(f)
    for aid, fs in by_paste.items():
        p = pastes.get(aid)
        if len([x for x in lines if x.section == first]) >= max_lines * 2:
            break
        lines.append(Line(first, f"{KIND_KO.get(p.kind, '자료') if p else '자료'} · {p.title if p else aid}",
                          [fs[0].id], "fact", 1, "basic"))
        for f in fs[:3]:
            lines.append(Line(first, _short(f.text.split("\n")[0], 120), [f.id], "fact", 2, "basic"))
    for i, name in enumerate(sections):
        if i > first:
            lines.append(Line(i, "", [], "gap", 1, "basic"))
    return [judge(x, known) for x in lines]


def strip_think(text: str) -> str:
    t = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    if "</think>" in t:
        t = t.split("</think>")[-1]
    return t.strip()


_INLINE_REF = re.compile(r"\s*[\[(]((?:p\d+)(?:\s*[,·/]\s*p\d+)*)[\])]", re.I)


def parse_draft(text: str, sections: List[str], free: bool, max_lines: int) -> Tuple[str, List[str], List[Line]]:
    """LLM 답에서 JSON 을 꺼낸다 (코드 울타리 · 앞뒤 말이 붙어 있어도) → (제목, 칸 이름, 줄). 모양이 틀리면 ValueError"""
    t = strip_think(text)
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t.strip(), flags=re.I | re.M)
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("JSON 을 찾지 못했습니다")
    data = json.loads(t[a:b + 1])
    if not isinstance(data, dict) or not isinstance(data.get("sections"), list):
        raise ValueError("sections 가 없습니다")
    title = re.sub(r"\s+", " ", str(data.get("title") or "")).strip()[:80]
    names = list(sections)
    if free:   # 자유 구성: 요약 다음 칸은 LLM 이 정한 이름
        for sec in data["sections"]:
            n = re.sub(r"\s+", " ", str(sec.get("name") or "") if isinstance(sec, dict) else "").strip()[:20]
            if n and n not in names and len(names) < 9:
                names.append(n)
        if len(names) == len(sections):
            names.append("내용")
    lines: List[Line] = []
    for i, sec in enumerate(data["sections"]):
        name = str(sec.get("name") or "").strip() if isinstance(sec, dict) else ""
        rows = sec.get("lines") if isinstance(sec, dict) else sec
        if name in names:
            idx = names.index(name)
        else:
            idx = min(i, len(names) - 1)
        cap = SUMMARY_MAX if names[idx] == SUMMARY else max_lines
        for row in (rows if isinstance(rows, list) else []):
            if len([x for x in lines if x.section == idx]) >= cap:
                break
            if isinstance(row, str):
                row = {"text": row}
            if not isinstance(row, dict):
                continue
            txt = re.sub(r"\s+", " ", str(row.get("text") or "")).strip()
            refs = row.get("refs") or []
            if isinstance(refs, str):
                refs = re.split(r"[\s,]+", refs)
            refs = [str(r) for r in refs if str(r).strip()]
            for m in _INLINE_REF.finditer(txt):   # 글 속에 박힌 [p3] 도 근거로 옮긴다
                refs += re.findall(r"p\d+", m.group(1), re.I)
            txt = _INLINE_REF.sub("", txt).strip()[:300]
            kind = str(row.get("kind") or "fact").strip().lower()
            kind = KIND_ALIAS.get(kind, kind)
            level = 2 if str(row.get("level") or "1").strip() == "2" else 1
            if txt or kind == "gap":
                lines.append(Line(idx, txt, refs, kind if kind in LINE_KINDS else "fact", level, "llm"))
    return title, names, lines


def build_messages(topic: str, form: str, sections: List[str], free: bool, known: Dict[str, Frag],
                   pastes: Dict[str, Paste], detail: int, tone: str, audience: str) -> List[Dict[str, str]]:
    per = DETAILS.get(detail, DETAILS[2])
    aud = AUDIENCES.get(audience, AUDIENCES["boss"])
    body_secs = [s for s in sections if s != SUMMARY]
    if free:
        sec_rule = ("칸: " + (f"'{SUMMARY}' 다음에 " if SUMMARY in sections else "")
                    + "자료에 맞는 칸 3~5개를 네가 정한다 (칸 이름은 짧게, 결론 → 근거 → 할 일 순서)")
    else:
        sec_rule = "칸: " + " · ".join(f"'{s}'" for s in sections) + " — 이 순서, 이 이름 그대로"
    summary_rule = (f"'{SUMMARY}' 칸은 결론부터 {SUMMARY_MAX}줄 이내로 쓴다 (두괄식). 요약 줄도 근거가 있어야 한다.\n"
                    if SUMMARY in sections else "")
    example_secs = [{"name": s, "lines": []} for s in (sections if not free else sections + ["…"])][:3]
    example_secs[0]["lines"] = [{"text": "…", "refs": ["p1", "p4"], "kind": "fact", "level": 1}]
    system = (
        f"너는 보고서를 쓰는 비서다. 사용자가 붙여 넣은 [자료] 조각만으로 '{form}' 을 쓴다. 규칙:\n"
        "1. 자료에 적힌 것만 쓴다. 자료 밖의 지식 · 수치 · 날짜 · 사람 이름 · 원인을 지어내지 않는다.\n"
        "2. 줄마다 그 줄의 근거 조각 id 를 refs 에 넣는다 (예: [\"p3\", \"p7\"]). 근거를 댈 수 없는 줄은 쓰지 않는다.\n"
        "3. kind 는 넷 중 하나다.\n"
        "   fact  = 조각에 적힌 사실\n"
        "   infer = 여러 조각을 이어 네가 내린 판단. 문장을 '~로 보임', '~로 판단됨' 처럼 끝내고 근거 조각을 모두 refs 에\n"
        "   check = 조각끼리 내용이 다름. 무엇이 어떻게 다른지 적고 다른 조각을 모두 refs 에\n"
        "   gap   = 양식 칸에 필요한데 자료에 없음. text 에는 빠진 항목 이름만 짧게, refs 는 빈 목록\n"
        "4. 숫자 · 날짜는 조각에 적힌 그대로 옮긴다. 더하거나 바꾸거나 반올림하지 않는다.\n"
        f"5. {sec_rule}. 칸마다 최대 {per[1]}줄.\n"
        f"{summary_rule}"
        f"6. 분량: {per[0]}. 어조: {TONES.get(tone, TONES['brief'])}. 읽는 사람: {aud[0]} — {aud[1]}.\n"
        "7. level 1 = 큰 항목, level 2 = 바로 위 항목의 세부.\n"
        "8. 다른 말 없이 JSON 하나만 출력한다:\n"
        + json.dumps({"title": "…", "sections": example_secs}, ensure_ascii=False)
    )
    rows = []
    for f in known.values():
        p = pastes.get(f.paste)
        head = f"자료 {p.id[1:]} · {KIND_KO.get(p.kind, '')}" if p else "자료"
        rows.append(f"[{f.id}] ({head}) {f.text.replace(chr(10), ' / ')}")
    user = (f"토픽: {topic or '(없음 — 자료를 보고 제목을 정한다)'}\n양식: {form}"
            + (f" ({' · '.join(body_secs)})" if body_secs else "")
            + "\n[자료]\n" + ("\n".join(rows) or "(없음)"))
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def render_text(title: str, sections: List[str], lines: List[Line], known: Dict[str, Frag],
                pastes: Dict[str, Paste], tone: str = "brief", with_refs: bool = False) -> str:
    """복사할 글 — 개조식(□ ○ -) 또는 서술식. 근거 붙이기를 켜면 [1] 표시와 맨 아래 근거 목록"""
    out = [title, ""] if title else []
    cite: Dict[str, int] = {}
    for i, name in enumerate(sections):
        out.append(f"□ {name}")
        rows = [ln for ln in lines if ln.section == i and (ln.text.strip() or ln.state == "gap")]
        if not rows:
            out.append("  ○ 자료 없음" if tone != "prose" else "  자료 없음")
        for ln in rows:
            text = ln.text.strip()
            if ln.state == "gap":
                text = f"{text} — 자료 없음 (확인 필요)" if text else "자료 없음 (확인 필요)"
            elif ln.state == "check":
                text += " (확인 필요)"
            mark = ""
            if with_refs and ln.refs and ln.state != "gap":
                for r in ln.refs:
                    cite.setdefault(r, len(cite) + 1)
                mark = "".join(f"[{cite[r]}]" for r in ln.refs)
            if tone == "prose":
                out.append(("  " if ln.level == 1 else "    ") + text + mark)
            else:
                out.append(("  ○ " if ln.level == 1 else "    - ") + text + mark)
        out.append("")
    if cite:
        out.append("※ 근거")
        for r, n in cite.items():
            f = known.get(r)
            p = pastes.get(f.paste) if f else None
            head = f"{KIND_KO.get(p.kind, '자료')} 「{p.title}」" if p else "자료"
            out.append(f"[{n}] {head}: {_short(f.text, 60) if f else r}")
    return "\n".join(out).rstrip() + "\n"


# ─────────────────────────────────────────────────────────────── LLM (OpenAI 호환 · docs/SPEC-llm.md)

class LLMError(Exception):
    def __init__(self, msg: str, status: Optional[int] = None):
        super().__init__(msg)
        self.status = status


def _short(s: str, n: int = 240) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[:n] + "…"


class LLMClient:
    def __init__(self, cfg: Dict[str, Any]):
        c = cfg.get("llm") or {}
        base = cfg.get("_dir") or data_dir()
        self.base_url = resolve_refs(c.get("base_url"), base).strip()
        self.api_key = resolve_refs(c.get("api_key"), base).strip()
        self.model = str(c.get("model") or "").strip()
        self.temperature = float(c.get("temperature", 0.2))
        self.max_tokens = int(c.get("max_tokens") or 2048)
        self.timeout = float(c.get("timeout_sec") or 90)
        self.extra_headers = {str(k): resolve_refs(v, base) for k, v in (c.get("extra_headers") or {}).items()}
        ca = str(c.get("ca_file") or "").strip()
        if ca and not os.path.isabs(ca):
            ca = os.path.join(base, ca)
        self.opener = self._build_opener(c.get("proxy"), ca)
        self.last_ok: Optional[bool] = None
        self.last_error = ""
        self.last_finish = ""

    @staticmethod
    def _build_opener(proxy: Any, ca_file: str) -> urllib.request.OpenerDirector:
        ctx = ssl.create_default_context()  # Windows 인증서 저장소(사내 CA 포함)를 그대로 신뢰
        if ca_file:
            ctx.load_verify_locations(cafile=ca_file)
        handlers: List[Any] = [urllib.request.HTTPSHandler(context=ctx)]
        if proxy is not None:  # "" → 프록시 끔, "http://host:port" → 지정, null → 시스템 설정
            p = str(proxy).strip()
            handlers.append(urllib.request.ProxyHandler({"http": p, "https": p} if p else {}))
        return urllib.request.build_opener(*handlers)

    @property
    def ready(self) -> bool:
        return bool(self.base_url and self.model)

    def endpoint(self) -> str:
        u = self.base_url.rstrip("/")
        return u if u.endswith("/chat/completions") else u + "/chat/completions"

    def complete(self, messages: List[Dict[str, str]]) -> str:
        if not self.ready:
            raise LLMError("config.json 의 llm.base_url 과 llm.model 을 채운 뒤 다시 실행하세요")
        payload = {"model": self.model, "messages": messages, "temperature": self.temperature,
                   "max_tokens": self.max_tokens, "stream": False}
        req = urllib.request.Request(self.endpoint(), data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                     method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        if self.api_key:
            req.add_header("Authorization", "Bearer " + self.api_key)
        for k, v in self.extra_headers.items():
            req.add_header(k, v)
        self.last_finish = ""
        try:
            with self.opener.open(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")[:2000]
            except Exception:
                pass
            finally:
                e.close()
            self.last_ok, self.last_error = False, f"LLM 서버 오류 {e.code}"
            hint = " (자료가 LLM 입력 한도를 넘었을 수 있습니다 — report.budget_chars 를 줄이세요)" \
                if e.code in (400, 413) and re.search(r"context|length|token", body, re.I) else ""
            raise LLMError(f"LLM 서버 오류 {e.code}: {_short(body) or e.reason}{hint}", e.code)
        except urllib.error.URLError as e:
            msg = (f"LLM 응답 시간 초과 ({int(self.timeout)}초)" if isinstance(e.reason, socket.timeout)
                   else f"LLM 서버에 연결할 수 없습니다: {e.reason}")
            self.last_ok, self.last_error = False, msg
            raise LLMError(msg)
        except (socket.timeout, TimeoutError):
            self.last_ok, self.last_error = False, "LLM 응답 시간 초과"
            raise LLMError(f"LLM 응답 시간 초과 ({int(self.timeout)}초)")
        except (ConnectionError, OSError) as e:
            self.last_ok, self.last_error = False, str(e)
            raise LLMError(f"LLM 서버 연결 오류: {e}")
        try:
            data = json.loads(raw)
            choice = data["choices"][0]
            msg = choice["message"]
            content = msg.get("content")
            if isinstance(content, list):
                content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
            self.last_finish = str(choice.get("finish_reason") or "")
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            self.last_ok, self.last_error = False, "LLM 응답 형식 오류"
            raise LLMError(f"LLM 응답 형식 오류: {_short(raw)}")
        self.last_ok, self.last_error = True, ""
        return strip_think(str(content or ""))


# ─────────────────────────────────────────────────────────────── 앱 · 로컬 서버

class Conflict(Exception):
    """보관 안 한 자료를 버리게 되는 요청 — 화면이 사람에게 물어본 뒤 discard 를 붙여 다시 보낸다 (HTTP 409)"""


class App:
    UNDO_SEC = 20

    def __init__(self, cfg: Dict[str, Any], config_path: str):
        self.cfg = cfg
        self.config_path = config_path
        home = cfg.get("_dir") or data_dir()
        self.token = secrets.token_urlsafe(24)
        self.topics = Folder(os.path.join(home, "topics"), "토픽")
        self.reports = Folder(os.path.join(home, "reports"), "보고서")
        self.llm = LLMClient(cfg)
        self.llm_lock = threading.Lock()
        self.lock = threading.RLock()
        self.forms: Dict[str, List[str]] = cfg["report"]["forms"]
        self.budget: int = cfg["report"]["budget_chars"]
        self.desk = Desk(self.default_form)
        self._undo: Optional[Tuple[float, str, Any]] = None
        self.httpd: Optional[ThreadingHTTPServer] = None
        self.port = 0
        self.allowed_hosts: Set[str] = set()
        self.last_seen = time.time()
        self._waiting_logged = False

    @property
    def default_form(self) -> str:
        return next(iter(self.forms))

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def render_index(self) -> bytes:
        boot = {"version": VERSION, "forms": [{"name": k, "sections": sections_of(self.cfg, k)[0],
                                              "free": sections_of(self.cfg, k)[1]} for k in self.forms],
                "undo_sec": self.UNDO_SEC, "budget": self.budget, "max_paste": MAX_PASTE,
                "company": self.cfg.get("company") or ""}
        boot_js = json.dumps(boot, ensure_ascii=False).replace("</", "<\\/")
        html = INDEX_HTML.replace("__THEME__", self.cfg.get("theme") or "dark")
        return html.replace("__TOKEN__", self.token).replace("__BOOT__", boot_js).encode("utf-8")

    def state(self) -> Dict[str, Any]:
        with self.lock:
            d = self.desk
            desk = {"topic": d.topic, "pastes": len(d.pastes), "frags": len(d.frags), "saved_id": d.saved_id,
                    "dirty": d.dirty, "unsaved": d.unsaved()}
        return {"version": VERSION, "llm_ready": self.llm.ready, "llm_ok": self.llm.last_ok,
                "llm_error": self.llm.last_error, "model": self.llm.model, "desk": desk}

    def view(self) -> Dict[str, Any]:
        with self.lock:
            return {"desk": self.desk.view(self.budget)}

    # 자료
    def paste(self, body: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            p = self.desk.add(body.get("text"), memo=bool(body.get("memo")))
            out = self.view()
        out["added"] = {"id": p.id, "frags": len(p.frags), "dups": p.dups, "quotes": p.quotes, "kind": p.kind}
        return out

    def paste_delete(self, aid: str) -> Dict[str, Any]:
        with self.lock:
            snap = self.desk.remove(aid)
            self._undo = (time.time() + self.UNDO_SEC, "paste", snap)
            return dict(self.view(), undo_sec=self.UNDO_SEC)

    def desk_update(self, body: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            d = self.desk
            if "topic" in body:
                t = re.sub(r"\s+", " ", str(body.get("topic") or "")).strip()[:80]
                if t != d.topic:
                    d.topic, d.dirty = t, True
            if "form" in body:
                f = str(body.get("form") or "")
                if f not in self.forms:
                    raise ValueError(f"없는 양식: {f}")
                if f != d.form:
                    d.form, d.dirty = f, True
            if "exclude" in body:
                ex = {str(k) for k in (body.get("exclude") or []) if str(k) in d.frags}
                if ex != d.exclude:
                    d.exclude, d.dirty = ex, True
            return self.view()

    def _guard(self, body: Dict[str, Any]) -> None:
        if self.desk.unsaved() and not body.get("discard"):
            raise Conflict(f"보관 안 한 자료 {len(self.desk.pastes)}개가 있습니다 — 보관하거나, 버린다고 해 주세요")

    def desk_new(self, body: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            self._guard(body)
            self.desk = Desk(self.desk.form if self.desk.form in self.forms else self.default_form)
            self._undo = None
            return self.view()

    def save(self) -> Dict[str, Any]:
        """보관 — 사람이 누른 때만 원문을 디스크에 쓴다 (RULES.md › W-05)"""
        with self.lock:
            d = self.desk
            if not d.pastes:
                raise ValueError("보관할 자료가 없습니다")
            key = d.saved_id or self.topics.new_key("t")
            self.topics.save(key, d.to_doc())
            d.saved_id, d.dirty = key, False
            return dict(self.view(), saved=key)

    def topic_list(self) -> Dict[str, Any]:
        out = []
        for key in self.topics.keys():
            doc = self.topics.get(key)
            if doc:
                ps = doc.get("pastes") or []
                out.append({"id": key, "topic": str(doc.get("topic") or ""), "form": str(doc.get("form") or ""),
                            "pastes": len(ps), "frags": sum(len(p.get("frags") or []) for p in ps if isinstance(p, dict)),
                            "updated": str(doc.get("updated") or "")})
        out.sort(key=lambda x: x["updated"], reverse=True)
        return {"topics": out}

    def topic_open(self, key: str, body: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            doc = self.topics.get(key)
            if not doc:
                raise KeyError(f"보관한 토픽이 없습니다: {key}")
            self._guard(body)
            d = Desk.from_doc(doc, self.forms, self.default_form)
            d.saved_id = "" if doc.get("readonly") else key
            self.desk, self._undo = d, None
            return self.view()

    def topic_delete(self, key: str) -> Dict[str, Any]:
        with self.lock:
            before = self.topics.delete(key)
            if before is None:
                raise KeyError(f"보관한 토픽이 없습니다: {key}")
            before.pop("version", None)
            was_open = self.desk.saved_id == key
            if was_open:
                self.desk.saved_id, self.desk.dirty = "", True
            self._undo = (time.time() + self.UNDO_SEC, "topic", (key, before, was_open))
            return dict(self.topic_list(), **self.view(), undo_sec=self.UNDO_SEC)

    # 초안
    def _opts(self, body: Dict[str, Any]) -> Tuple[int, str, str]:
        try:
            detail = min(3, max(1, int(body.get("detail") or 2)))
        except (TypeError, ValueError):
            detail = 2
        tone = str(body.get("tone") or "brief")
        audience = str(body.get("audience") or "boss")
        return detail, tone if tone in TONES else "brief", audience if audience in AUDIENCES else "boss"

    def draft(self, body: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            d = self.desk
            known, pastes, form, topic = d.known(), d.paste_of(), d.form, d.topic
        if not known:
            raise ValueError("자료를 붙여 넣어 주세요 (체크된 조각이 없습니다)")
        detail, tone, audience = self._opts(body)
        sections, free = sections_of(self.cfg, form)
        max_lines = DETAILS[detail][1]
        mode, error, title = "basic", "", ""
        lines: List[Line] = []
        names = sections
        if self.llm.ready and not body.get("basic"):
            chars = sum(len(f.text) for f in known.values())
            if chars > self.budget:
                raise ValueError(f"체크된 자료가 한도보다 깁니다 ({chars:,} / {self.budget:,}자) — 체크를 풀어 줄이거나 "
                                 "report.budget_chars 를 사내 LLM 입력 한도에 맞게 늘리세요")
            messages = build_messages(topic, form, sections, free, known, pastes, detail, tone, audience)
            with self.llm_lock:
                try:
                    reply = self.llm.complete(messages)
                    try:
                        title, names, lines = parse_draft(reply, sections, free, max_lines)
                    except ValueError as e:
                        if self.llm.last_finish == "length":
                            raise LLMError(f"LLM 답이 llm.max_tokens({self.llm.max_tokens})에서 잘렸습니다 — "
                                           "② 분량을 줄이거나 llm.max_tokens 를 늘리세요")
                        log(f"초안 JSON 을 읽지 못해 다시 요청합니다: {e}")   # 한 번만 다시 — JSON 으로만 답하라고
                        reply = self.llm.complete(messages + [
                            {"role": "assistant", "content": reply[:2000]},
                            {"role": "user", "content": "형식이 틀렸다. 설명 없이 위에서 말한 JSON 하나만 다시 출력해."}])
                        title, names, lines = parse_draft(reply, sections, free, max_lines)
                    lines = [judge(x, known) for x in lines]
                    mode = "llm"
                except (LLMError, ValueError) as e:
                    error = f"LLM 초안 실패 → 기본 초안으로: {e}"
                    log(error)
        if mode == "basic":
            names = sections if not free else sections + ["내용"]
            lines = basic_draft(known, pastes, names, max_lines, bool(self.cfg["report"]["summary"]))
        title = topic or title or "보고서"
        return {"mode": mode, "error": error, "title": title, "form": form, "sections": names, "tone": tone,
                "lines": [asdict(x) for x in lines], "text": render_text(title, names, lines, known, pastes, tone)}

    def check_lines(self, body: Dict[str, Any]) -> Tuple[str, List[str], List[Line], Dict[str, Frag], Dict[str, Paste]]:
        """화면이 보낸 줄을 서버에서 다시 판정한다 (화면을 믿지 않는다)"""
        form = str(body.get("form") or "")
        if form not in self.forms:
            raise ValueError(f"없는 양식: {form}")
        sections, free = sections_of(self.cfg, form)
        if free:
            got = body.get("sections") or []
            extra = [re.sub(r"\s+", " ", str(s)).strip()[:20] for s in got if isinstance(s, str)]
            sections = sections + [s for s in extra if s and s not in sections][:8]
        with self.lock:
            known, pastes = self.desk.known(), self.desk.paste_of()
        lines = []
        for row in (body.get("lines") or [])[:300]:
            if not isinstance(row, dict):
                continue
            text = re.sub(r"\s+", " ", str(row.get("text") or "")).strip()[:400]
            try:
                sec = int(row.get("section"))
            except (TypeError, ValueError):
                continue
            kind = str(row.get("kind") or "fact")
            if (text or kind == "gap") and 0 <= sec < len(sections):
                origin = row.get("origin") if row.get("origin") in ("user", "basic") else "llm"
                refs = [str(r) for r in (row.get("refs") or [])][:50]
                level = 2 if row.get("level") == 2 else 1
                lines.append(judge(Line(sec, text, refs, kind, level, str(origin)), known))
        title = re.sub(r"\s+", " ", str(body.get("title") or "")).strip()[:80] or "보고서"
        return title, sections, lines, known, pastes

    def preview(self, body: Dict[str, Any]) -> Dict[str, Any]:
        title, sections, lines, known, pastes = self.check_lines(body)
        tone = self._opts(body)[1]
        return {"lines": [asdict(x) for x in lines], "sections": sections,
                "text": render_text(title, sections, lines, known, pastes, tone, bool(body.get("with_refs")))}

    def confirm(self, body: Dict[str, Any]) -> Dict[str, Any]:
        title, sections, lines, known, pastes = self.check_lines(body)
        bad = [x for x in lines if x.state == "err"]
        if bad:
            raise ValueError(f"근거 없는 줄이 {len(bad)}개 있습니다 — 근거를 달거나, 직접 고치거나, 지워 주세요")
        if not any(x.text.strip() for x in lines if x.state != "gap"):
            raise ValueError("확정할 줄이 없습니다")
        tone = self._opts(body)[1]
        text = render_text(title, sections, lines, known, pastes, tone, bool(body.get("with_refs")))
        key = self.reports.new_key()
        with self.lock:
            topic_id = self.desk.saved_id
        report = {"key": key, "title": title, "form": str(body.get("form")), "sections": sections, "tone": tone,
                  "lines": [asdict(x) for x in lines], "text": text, "topic_id": topic_id, "confirmed": now_iso()}
        self.reports.save(key, report)   # 원문 조각은 넣지 않는다 — 복사한 글 그대로만 (RULES.md › W-05)
        with self.lock:
            self._undo = (time.time() + self.UNDO_SEC, "confirm", key)
        return {"key": key, "text": text, "undo_sec": self.UNDO_SEC}

    def undo(self) -> Dict[str, Any]:
        with self.lock:
            until, kind, payload = self._undo or (0.0, "", None)
            self._undo = None
            if not kind or time.time() > until:
                raise ValueError("되돌릴 수 있는 시간이 지났습니다")
            if kind == "confirm":
                self.reports.delete(payload)
            elif kind == "paste":
                self.desk.restore(payload)
            elif kind == "topic":
                key, before, was_open = payload
                self.topics.save(key, before)
                if was_open and not self.desk.saved_id:
                    self.desk.saved_id = key
            return dict(self.view(), undone=kind)

    def report_list(self) -> Dict[str, Any]:
        out = []
        for key in self.reports.keys():
            r = self.reports.get(key)
            if r:
                out.append({"key": key, "title": str(r.get("title") or ""), "form": str(r.get("form") or ""),
                            "confirmed": str(r.get("confirmed") or "")})
        return {"reports": out}

    def report(self, key: str) -> Dict[str, Any]:
        r = self.reports.get(key)
        if not r:
            raise KeyError(f"확정한 보고서가 없습니다: {key}")
        return r

    def shutdown(self) -> None:
        time.sleep(0.6)
        if self.httpd is not None:
            self.httpd.shutdown()

    def idle_should_exit(self, now: Optional[float] = None) -> bool:
        """창을 닫은 뒤 idle_exit_min 동안 조용하면 끈다 — 단, 보관 안 한 자료가 있으면 기다린다 (원문이 사라지지 않게)"""
        limit = float(self.cfg.get("idle_exit_min") or 0) * 60
        if limit <= 0 or (now or time.time()) - self.last_seen <= limit:
            return False
        with self.lock:
            if self.desk.unsaved():
                if not self._waiting_logged:
                    log("보관 안 한 자료가 있어 켜 둡니다 — 창을 다시 열면 그대로 있습니다")
                    self._waiting_logged = True
                return False
        return True

    def _idle_watch(self) -> None:
        limit = float(self.cfg.get("idle_exit_min") or 0) * 60
        while limit > 0:
            time.sleep(min(30.0, limit / 4))
            if self.idle_should_exit():
                log(f"{int(limit // 60)}분 동안 쓰지 않아 끕니다")
                self.shutdown()
                return

    def serve(self, port: int, open_window: bool = True) -> None:
        self.httpd, self.port = bind_server(port, make_handler(self))
        self.allowed_hosts = {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}
        log(f"Report-1 {VERSION} 실행 중 → {self.url}   (끄려면 창의 끄기 또는 Ctrl+C)")
        log(f"데이터: {self.cfg.get('_dir')} · LLM: {self.llm.model or '(미설정 → 기본 초안만)'}")
        threading.Thread(target=self._idle_watch, daemon=True).start()
        if open_window:
            open_app_window(self.url)
        try:
            self.httpd.serve_forever(poll_interval=0.5)
        except KeyboardInterrupt:
            pass
        finally:
            self.httpd.server_close()
            log("Report-1 종료")


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = not IS_WINDOWS  # Windows 에선 같은 포트 중복 바인딩을 막기 위해 끔

    def server_bind(self) -> None:
        # HTTPServer.server_bind 의 getfqdn() 이 사내망에서 수 초씩 걸리는 경우가 있어 생략
        socketserver.TCPServer.server_bind(self)
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


FONT_URL = "/font/report-1-dos.woff"
_FONT: List[bytes] = []


def font_bytes() -> bytes:
    if not _FONT:
        _FONT.append(base64.b64decode(FONT_WOFF_B64))
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
            return secrets.compare_digest(self.headers.get("X-Report-Token", ""), app.token)

        def _body(self, limit: int) -> Dict[str, Any]:
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                raise ValueError("Content-Length 가 숫자가 아닙니다")
            if n < 0 or n > limit:
                raise ValueError("요청이 너무 큽니다 — 나눠서 붙여 넣으세요" if n > limit else "요청 크기가 올바르지 않습니다")
            raw = self.rfile.read(n) if n else b""
            data = json.loads(raw.decode("utf-8")) if raw.strip() else {}
            if not isinstance(data, dict):
                raise ValueError("JSON 객체가 필요합니다")
            return data

        def _run(self, fn: Callable[[], Any]) -> None:
            try:
                return self._json(200, fn())
            except Conflict as e:
                return self._json(409, {"error": str(e)})
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
            if u.path == FONT_URL:  # @font-face 는 토큰 헤더를 못 보낸다 (공개해도 되는 정적 파일)
                return self._send(200, font_bytes(), "font/woff", cache="max-age=3600")
            if u.path == "/api/ping":
                return self._json(200, {"app": APP, "version": VERSION})
            if not u.path.startswith("/api/"):
                return self._json(404, {"error": "not found"})
            if not self._auth_ok():
                return self._json(401, {"error": "unauthorized"})
            app.last_seen = time.time()
            routes: Dict[str, Callable[[], Any]] = {
                "/api/state": app.state, "/api/desk": app.view, "/api/topics": app.topic_list,
                "/api/reports": app.report_list}
            if u.path in routes:
                return self._run(routes[u.path])
            m = re.match(r"^/api/reports/([0-9A-Za-z\-]{4,40})$", u.path)
            if m:
                return self._run(lambda: app.report(m.group(1)))
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
                body = self._body(MAX_PASTE * 8 if u.path == "/api/paste" else 1_000_000)
            except ValueError as e:
                return self._json(400 if "너무 큽니다" not in str(e) else 413, {"error": str(e)})
            routes: Dict[str, Callable[[], Any]] = {
                "/api/paste": lambda: app.paste(body), "/api/desk": lambda: app.desk_update(body),
                "/api/desk/new": lambda: app.desk_new(body), "/api/save": app.save,
                "/api/draft": lambda: app.draft(body), "/api/preview": lambda: app.preview(body),
                "/api/confirm": lambda: app.confirm(body), "/api/undo": app.undo}
            if u.path in routes:
                return self._run(routes[u.path])
            m = re.match(r"^/api/paste/(a\d+)/delete$", u.path)
            if m:
                return self._run(lambda: app.paste_delete(m.group(1)))
            m = re.match(r"^/api/topics/([0-9A-Za-z\-]{4,40})/(open|delete)$", u.path)
            if m:
                key, act = m.group(1), m.group(2)
                return self._run(lambda: app.topic_open(key, body) if act == "open" else app.topic_delete(key))
            if u.path == "/api/shutdown":
                self._json(200, {"ok": True})
                threading.Thread(target=app.shutdown, daemon=True).start()
                return None
            return self._json(404, {"error": "not found"})

    return Handler




# ─────────────────────────────────────────────────────────────── 창 · 실행 중 찾기 · 바로가기

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


def stop_running(port: int, quiet: bool = False) -> int:
    say: Callable[[str], None] = (lambda _m: None) if quiet else print
    url = find_running(port)
    if not url:
        say("Report-1 이 꺼져 있습니다.")
        return 0
    try:
        with _LOCAL_OPENER.open(url, timeout=5) as r:
            m = re.search(r'name="report-token" content="([^"]+)"', r.read().decode("utf-8", "replace"))
        if not m:
            raise ValueError("토큰을 찾지 못했습니다")
        req = urllib.request.Request(url + "api/shutdown", data=b"{}", method="POST",
                                     headers={"X-Report-Token": m.group(1), "Content-Type": "application/json"})
        with _LOCAL_OPENER.open(req, timeout=5) as r:
            r.read()
    except Exception as e:
        say(f"끄기 실패: {e}")
        return 1
    for _ in range(40):
        if not find_running(port):
            say("Report-1 을 껐습니다.")
            return 0
        time.sleep(0.25)
    say("끄기 요청은 보냈지만 아직 켜져 있습니다.")
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
    """Edge/Chrome '앱 모드'(주소창 없는 창)로 연다. 없으면 기본 브라우저."""
    if IS_WINDOWS:
        exe = _find_browser()
        if exe:
            try:
                subprocess.Popen([exe, f"--app={url}", "--window-size=1040,820"], close_fds=True)
                return
            except Exception as e:
                log(f"앱 창 열기 실패, 기본 브라우저로 엽니다: {e}")
    try:
        webbrowser.open(url)
    except Exception:
        log(f"브라우저를 열 수 없습니다. 직접 여세요: {url}")


def programs_dir() -> str:
    """시작 메뉴 › 프로그램 폴더 (회사 PC 의 폴더 리디렉션도 반영)"""
    import ctypes
    buf = ctypes.create_unicode_buffer(1024)
    if ctypes.windll.shell32.SHGetFolderPathW(None, 2, None, 0, buf) != 0:  # CSIDL_PROGRAMS
        raise OSError("시작 메뉴 폴더를 찾지 못했습니다")
    return buf.value


def set_shortcut(on: bool) -> int:
    """시작 메뉴에 'Report-1' 바로가기를 만들거나 지운다 (사용자 동의 뒤에만 · INSTALL.md)"""
    if not IS_WINDOWS:
        print("시작 메뉴 바로가기는 Windows 에서만 만듭니다.")
        return 1
    try:
        lnk = os.path.join(programs_dir(), "Report-1.lnk")
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
    ps = ("$ErrorActionPreference='Stop';$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:REPORT_LNK);"
          "$s.TargetPath=$env:REPORT_EXE;$s.Arguments='\"'+$env:REPORT_PY+'\"';$s.WorkingDirectory=$env:REPORT_DIR;"
          "$s.Description='Report-1 · 근거 달린 보고서';$s.Save()")
    err = ""
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True,
                           timeout=30, creationflags=NO_WINDOW,
                           env=dict(os.environ, REPORT_LNK=lnk, REPORT_EXE=exe, REPORT_PY=os.path.abspath(__file__),
                                    REPORT_DIR=BASE_DIR))
        if r.returncode != 0:
            err = (r.stderr or r.stdout or b"").decode("utf-8", "replace").strip() or f"exit {r.returncode}"
    except Exception as e:
        err = str(e)
    if not err and os.path.exists(lnk):
        print(f"바로가기 만듦: {lnk} → 시작 메뉴에서 'Report-1'")
        return 0
    print(f"바로가기 만들기 실패: {_short(err or '만들어지지 않았습니다', 300)}")
    return 1


# ─────────────────────────────────────────────────────────────── 설치 도우미 (--setup · --set) · docs/SPEC-llm.md
# 사람이든 OpenCode 같은 에이전트든 명령 한 줄로 설치하게 한다. API 키 값은 어떤 출력에도 찍지 않는다.

class SetupChoice(Exception):
    """고를 것이 여러 개라 사람이 정해야 함 → --provider / --model 로 다시 실행."""


def parse_jsonc(text: str) -> Any:
    """JSON + 주석(// · /* */) + 끝 쉼표 (opencode.jsonc 형식)."""
    def scan(src: str, drop: Callable[[str, int], int]) -> str:
        out, i, n, in_str = [], 0, len(src), False
        while i < n:
            c = src[i]
            if in_str:
                out.append(c)
                if c == "\\" and i + 1 < n:
                    out.append(src[i + 1])
                    i += 2
                    continue
                in_str = c != '"'
                i += 1
                continue
            if c == '"':
                in_str = True
                out.append(c)
                i += 1
                continue
            j = drop(src, i)
            if j > i:
                i = j
                continue
            out.append(c)
            i += 1
        return "".join(out)

    def comment(s: str, i: int) -> int:
        if s.startswith("//", i):
            j = s.find("\n", i)
            return len(s) if j < 0 else j
        if s.startswith("/*", i):
            j = s.find("*/", i + 2)
            return len(s) if j < 0 else j + 2
        return i

    def trailing_comma(s: str, i: int) -> int:
        if s[i] == ",":
            j = i + 1
            while j < len(s) and s[j] in " \t\r\n":
                j += 1
            if j < len(s) and s[j] in "}]":
                return i + 1
        return i

    return json.loads(scan(scan(text, comment), trailing_comma))


def opencode_config_files(dirs: Optional[List[str]] = None) -> List[str]:
    """OpenCode 설정 파일들 — 우선순위 낮은 것부터 (전역 → OPENCODE_CONFIG → 프로젝트)."""
    home = os.path.expanduser("~")
    xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config")
    cands = [os.path.join(xdg, "opencode", n) for n in ("config.json", "opencode.json", "opencode.jsonc")]
    if os.environ.get("OPENCODE_CONFIG"):
        cands.append(os.environ["OPENCODE_CONFIG"])
    for d in (dirs if dirs is not None else [os.path.dirname(BASE_DIR), BASE_DIR, os.getcwd()]):
        cands += [os.path.join(d, "opencode.json"), os.path.join(d, "opencode.jsonc")]
    seen, out = set(), []
    for p in cands:
        key = os.path.normcase(os.path.abspath(p))
        if key not in seen and os.path.isfile(p):
            seen.add(key)
            out.append(p)
    return out


def opencode_auth() -> Dict[str, Any]:
    data_home = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    try:
        with open(os.path.join(data_home, "opencode", "auth.json"), "r", encoding="utf-8-sig") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _openai_like(pid: str, p: Dict[str, Any]) -> bool:
    opts = p.get("options") if isinstance(p.get("options"), dict) else {}
    if not (opts.get("baseURL") or opts.get("baseUrl")):
        return False
    npm = str(p.get("npm") or "").lower()
    other = ("anthropic", "google", "vertex", "bedrock", "azure", "gemini")
    return not any(x in npm for x in other) and (bool(npm) or not any(x in pid.lower() for x in other))


def _portable_ref(value: Any, base: str) -> str:
    """{file:상대경로} 는 OpenCode 설정 파일 기준이라 절대경로로 바꿔 둔다. {env:…}·일반 값은 그대로."""
    def fix(m: Any) -> str:
        if m.group(1) != "file":
            return m.group(0)
        path = os.path.expanduser(m.group(2).strip())
        return "{file:" + (path if os.path.isabs(path) else os.path.normpath(os.path.join(base, path))) + "}"
    return _REF_RE.sub(fix, "" if value is None else str(value))


def find_opencode_llm(provider: str = "", model: str = "", dirs: Optional[List[str]] = None) -> Dict[str, Any]:
    """OpenCode 설정에서 사내 LLM(OpenAI 호환) 주소·모델·키·헤더를 찾는다. 키 값은 돌려주기만 하고 출력하지 않는다."""
    files = opencode_config_files(dirs)
    if not files:
        raise LookupError("OpenCode 설정 파일(opencode.json)을 찾지 못했습니다")
    providers: Dict[str, Dict[str, Any]] = {}
    origin: Dict[str, str] = {}
    default, warnings = "", []
    for path in files:
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                data = parse_jsonc(f.read())
        except (OSError, ValueError) as e:
            warnings.append(f"{path} 읽기 실패: {_short(str(e), 120)}")
            continue
        if not isinstance(data, dict):
            continue
        for pid, p in (data.get("provider") or {}).items():
            if isinstance(p, dict):
                providers[pid] = deep_merge(providers.get(pid, {}), p)
                origin[pid] = path
        if isinstance(data.get("model"), str) and "/" in data["model"]:
            default = data["model"].strip()
    usable = {pid: p for pid, p in providers.items() if _openai_like(pid, p)}
    dp, _, dm = default.partition("/")
    if provider:
        if provider not in usable:
            raise SetupChoice(f"provider '{provider}' 가 없습니다. 후보: {', '.join(sorted(usable)) or '없음'}")
        pid = provider
    elif dp in usable:
        pid = dp
    elif len(usable) == 1:
        pid = next(iter(usable))
    elif not usable:
        raise LookupError("OpenCode 설정에 OpenAI 호환 provider(options.baseURL)가 없습니다 · 읽은 파일: " + ", ".join(files))
    else:
        raise SetupChoice("provider 가 여러 개입니다 → --provider 로 고르세요: " + ", ".join(sorted(usable)))
    p = usable[pid]
    models = p.get("models") if isinstance(p.get("models"), dict) else {}
    if model:
        mkey = model
    elif dp == pid and dm:
        mkey = dm
    elif len(models) == 1:
        mkey = next(iter(models))
    elif not models:
        raise SetupChoice(f"'{pid}' 의 모델 이름을 찾지 못했습니다 → --model 로 알려주세요")
    else:
        raise SetupChoice(f"'{pid}' 모델이 여러 개입니다 → --model 로 고르세요: " + ", ".join(sorted(models)))
    minfo = models.get(mkey) if isinstance(models.get(mkey), dict) else {}
    opts = p.get("options") if isinstance(p.get("options"), dict) else {}
    base = os.path.dirname(os.path.abspath(origin[pid]))
    key, key_from = _portable_ref(opts.get("apiKey") or "", base), "OpenCode 설정"
    if not key:
        auth = opencode_auth().get(pid)
        if isinstance(auth, dict) and auth.get("type") == "api" and auth.get("key"):
            key, key_from = str(auth["key"]), "OpenCode 로그인 정보(auth.json)"
        else:
            key_from = ""
    headers: Dict[str, str] = {}
    for h in (opts.get("headers"), minfo.get("headers")):
        if isinstance(h, dict):
            headers.update({str(k): _portable_ref(v, base) for k, v in h.items()})
    names = [str(v.get("id") or k) if isinstance(v, dict) else str(k) for k, v in models.items()]
    return {"provider": pid, "base_url": _portable_ref(opts.get("baseURL") or opts.get("baseUrl"), base),
            "model": str(minfo.get("id") or mkey), "models": names, "api_key": key, "key_from": key_from,
            "extra_headers": headers, "source": origin[pid], "warnings": warnings}


def mask_secret(value: Any, base_dir: Optional[str] = None) -> str:
    v = "" if value is None else str(value).strip()
    if not v:
        return "없음 (키 없이 쓰는 서버면 정상)"
    if _REF_RE.fullmatch(v):
        return f"{v} 참조 · " + ("값 있음" if resolve_refs(v, base_dir) else "값이 비어 있음!")
    return f"설정됨 ({len(v)}자 · 값은 표시 안 함)"



def set_config_values(path: str, pairs: List[str]) -> int:
    """--set 키=값 (값은 JSON 으로 읽히면 JSON, 아니면 문자열). 저장 뒤 검증해서 틀리면 되돌린다.
    양식: --set "report.forms.주간 점검=현황;이슈;계획" 으로 더하거나 바꾸고, 값을 비우면 그 양식을 지운다."""
    user = _read_user_config(path) if os.path.exists(path) else {}
    before = json.dumps(user, ensure_ascii=False)
    for pair in pairs:
        key, eq, raw = pair.partition("=")
        key = key.strip()
        if not eq or not key:
            print(f"--set 형식은 키=값 입니다: {pair}")
            return 2
        try:
            value = json.loads(raw) if raw.strip() else ""
        except ValueError:
            value = raw
        if key == "llm.api_key" and value and not _REF_RE.fullmatch(str(value).strip()):
            print("API 키는 --set 으로 넣지 않습니다 (명령 기록에 남음). config.json 을 직접 열어 넣거나 "
                  "--set llm.api_key={env:환경변수이름} 처럼 참조로 넣으세요.")
            return 2
        if key.startswith("report.forms."):
            name = key[len("report.forms."):].strip()
            rep = user.get("report") if isinstance(user.get("report"), dict) else {}
            user["report"] = rep
            if not isinstance(rep.get("forms"), dict):   # 처음 고칠 때 기본 양식을 옮겨 둔다 (기본 양식이 사라지지 않게)
                rep["forms"] = copy.deepcopy(DEFAULT_CONFIG["report"]["forms"])
            if value is None or value == "":
                if name not in rep["forms"]:
                    print(f"없는 양식: {name}")
                    return 2
                del rep["forms"][name]
                print(f"설정: 양식 '{name}' 지움")
                continue
            if isinstance(value, str):
                value = [v.strip() for v in value.split(";") if v.strip()]
            rep["forms"][name] = value
            print(f"설정: 양식 '{name}' = {json.dumps(value, ensure_ascii=False)}")
            continue
        parts, node, spec = key.split("."), user, DEFAULT_CONFIG
        for i, part in enumerate(parts):
            free = isinstance(spec, dict) and not spec and i > 0  # extra_headers 같은 자유 형식 칸
            if not isinstance(spec, dict) or (part not in spec and not free):
                print(f"알 수 없는 설정 키: {key}")
                return 2
            spec = spec.get(part) if part in spec else None
            if i == len(parts) - 1:
                if isinstance(spec, list) and isinstance(value, str):   # 목록 칸은 ; 로 나눈 글도 받는다 (셸마다 따옴표가 달라서)
                    value = [v.strip() for v in value.split(";") if v.strip()]
                node[part] = value
            else:
                if not isinstance(node.get(part), dict):
                    node[part] = {}
                node = node[part]
        secret = key.startswith(("llm.api_key", "llm.extra_headers"))
        shown = mask_secret(value, os.path.dirname(path)) if secret else json.dumps(value, ensure_ascii=False)
        print(f"설정: {key} = {shown}")
    _write_json(path, user)
    try:
        load_config(path, create=False)
    except ConfigError as e:
        _write_json(path, json.loads(before))
        print(f"값이 올바르지 않아 되돌렸습니다: {e}")
        return 2
    return 0


def run_check(cfg: Dict[str, Any], config_path: str) -> int:
    """점검 — 0 OK · 1 점검 실패. LLM 은 없어도 된다 (기본 초안만)"""
    print(f"Report-1 {VERSION} 점검")
    print(f"- 설정 파일 : {config_path}")
    home = cfg.get("_dir") or data_dir()
    topics, reports = Folder(os.path.join(home, "topics"), "토픽"), Folder(os.path.join(home, "reports"), "보고서")
    print(f"- 데이터    : {home} · 보관한 토픽 {len(topics.keys())} · 확정한 보고서 {len(reports.keys())}")
    forms = cfg["report"]["forms"]
    print(f"- 양식      : {' · '.join(forms)} ({len(forms)}개) · 자료 한도 {cfg['report']['budget_chars']:,}자")
    llm = LLMClient(cfg)
    if not llm.ready:
        print("- LLM       : 미설정 → 기본 초안(자료를 그대로 묶기)만. 쓰려면 --setup 또는 --set llm.base_url=… llm.model=…")
        return 0
    print(f"- LLM 주소  : {llm.endpoint()} · 모델 {llm.model} · 키 {mask_secret((cfg.get('llm') or {}).get('api_key'), cfg.get('_dir'))}")
    t0 = time.time()
    try:
        r = llm.complete([{"role": "user", "content": "연결 확인이다. '확인' 한 단어로만 답해."}])
        print(f"  · 기본 응답 OK ({time.time() - t0:.1f}s): {_short(r, 60)!r}")
    except LLMError as e:
        print(f"  · 기본 응답 실패: {e}")
        if e.status == 404:
            print("    ↳ base_url 끝에 /v1 이 필요한지 확인하세요")
        if e.status in (401, 403):
            print("    ↳ api_key 또는 extra_headers(인증 헤더)를 확인하세요")
        return 1
    return 0


def run_setup(config_path: str, provider: str = "", model: str = "", force: bool = False,
              dirs: Optional[List[str]] = None) -> int:
    """설치 도우미 — 종료 코드 0 OK · 1 점검 실패 · 3 사람 확인 필요 (docs/SPEC-llm.md › 03)"""
    print(f"Report-1 {VERSION} 설치 도우미")
    print(f"- 파이썬    : {sys.version.split()[0]} · {sys.executable}")
    print(f"- 프로그램  : {BASE_DIR}")
    print(f"- 데이터    : {os.path.dirname(os.path.abspath(config_path))}")
    user = _read_user_config(config_path)
    llm = dict(user.get("llm") or {})
    if llm.get("base_url") and llm.get("model") and not force:
        print(f"- LLM 설정  : 이미 있음 · {resolve_refs(llm['base_url'])} · {llm['model']} (다시 가져오려면 --force)")
    else:
        try:
            found = find_opencode_llm(provider, model, dirs)
        except SetupChoice as e:
            print(f"- LLM 설정  : 선택 필요 · {e}")
            print("\n결과: 확인 필요 (코드 3) · 사용자에게 물어본 뒤 --provider / --model 을 붙여 다시 실행")
            return 3
        except LookupError as e:
            print(f"- LLM 설정  : {e}")
            print("\n결과: 확인 필요 (코드 3) · 사용자에게 LLM 주소·모델 이름을 받아 --set llm.base_url=… --set llm.model=… 로 넣고,"
                  "\n      키는 사용자가 config.json 에 직접 넣게 할 것 (또는 --set llm.api_key={env:환경변수이름})."
                  "\n      사내 LLM 없이 쓰려면 이 단계를 건너뛰고 --check (기본 초안만)")
            return 3
        for w in found["warnings"]:
            print(f"  ! {w}")
        llm.update(base_url=found["base_url"], model=found["model"])
        if len(found.get("models") or []) > 1:
            llm["models"] = found["models"]
        if found["api_key"]:
            llm["api_key"] = found["api_key"]
        if found["extra_headers"]:
            llm["extra_headers"] = dict(llm.get("extra_headers") or {}, **found["extra_headers"])
        user["llm"] = llm
        _write_json(config_path, user)
        print(f"- OpenCode  : {found['source']} · provider '{found['provider']}'")
        print(f"- LLM 주소  : {resolve_refs(found['base_url'])}")
        print(f"- 모델      : {found['model']}")
        print(f"- API 키    : {mask_secret(found['api_key'])}" + (f" · {found['key_from']}" if found["key_from"] else ""))
        if found["extra_headers"]:
            print(f"- 추가 헤더 : {', '.join(found['extra_headers'])} (값은 표시 안 함)")
        print(f"  → {config_path} 에 저장")
    cfg, _ = load_config(config_path)
    print()
    rc = run_check(cfg, config_path)
    print("\n결과: OK · 다음 → --shortcut on (시작 메뉴, 사용자 동의 후) · python report-1.py" if rc == 0 else
          "\n결과: 점검 실패 (코드 1) · 위 메시지와 INSTALL.md 의 '문제 해결' 표를 보고 --set 으로 고친 뒤 --check")
    return rc


def read_input(path: str) -> str:
    """파일(또는 - = 표준 입력)을 글로 — UTF-8 이 아니면 CP949(한글 Windows)로 읽는다"""
    if path == "-":
        data = sys.stdin.buffer.read()
    else:
        with open(path, "rb") as f:
            data = f.read()
    for enc in ("utf-8-sig", "cp949"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def print_draft(cfg: Dict[str, Any], config_path: str, files: List[str], topic: str, form: str, basic: bool) -> int:
    """--draft: 창 없이 — 파일 하나 = 자료 하나로 초안 글만 표준 출력에 (UTF-8). 근거 없는 줄이 있으면 종료 코드 1"""
    app = App(cfg, config_path)
    try:
        if form:
            app.desk_update({"form": form})
        app.desk_update({"topic": topic})
        for path in files or ["-"]:
            try:
                res = app.paste({"text": read_input(path)})
                log(f"자료 {res['added']['id']} · {path} · 조각 {res['added']['frags']}")
            except ValueError as e:
                log(f"{path}: {e}")
        res = app.draft({"basic": basic})
    except (OSError, ValueError) as e:
        log(str(e))
        return 2
    if res["error"]:
        log(res["error"])
    for x in res["lines"]:
        if x["state"] == "err":
            log(f"근거 없는 줄: {x['text']}")
        elif x["nums"]:
            log(f"근거에 없는 숫자 {', '.join(x['nums'])}: {x['text']}")
    data = res["text"].encode("utf-8")
    try:
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
    except AttributeError:
        sys.stdout.write(res["text"])
    return 1 if any(x["state"] == "err" for x in res["lines"]) else 0


# ─────────────────────────────────────────────────────────────── 진입점

def main(argv: Optional[List[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass
    ap = argparse.ArgumentParser(prog=APP, description="Report-1 · 근거 달린 보고서")
    ap.add_argument("--setup", action="store_true", help="설치 도우미: OpenCode 설정에서 LLM 값을 가져오고 점검")
    ap.add_argument("--provider", default="", help="--setup: 쓸 OpenCode provider 이름")
    ap.add_argument("--model", default="", help="--setup: 쓸 모델 이름")
    ap.add_argument("--force", action="store_true", help="--setup: LLM 설정이 있어도 OpenCode 에서 다시 가져오기")
    ap.add_argument("--check", action="store_true", help="LLM 점검")
    ap.add_argument("--set", action="append", default=[], metavar="키=값", help="config.json 값 바꾸기 (여러 번 가능)")
    ap.add_argument("--draft", nargs="*", metavar="파일", help="창 없이 파일(들)을 자료로 초안 글만 출력 (없거나 - 면 표준 입력)")
    ap.add_argument("--topic", default="", help="--draft: 토픽 (보고서 제목)")
    ap.add_argument("--form", default="", help="--draft: 양식 이름 (기본 report.forms 의 첫 양식)")
    ap.add_argument("--basic", action="store_true", help="--draft: LLM 없이 기본 초안")
    ap.add_argument("--shortcut", choices=("on", "off"), help="시작 메뉴 바로가기 만들기/지우기 (Windows)")
    ap.add_argument("--status", action="store_true", help="실행 중인지 확인")
    ap.add_argument("--stop", action="store_true", help="실행 중인 Report-1 끄기 (보관 안 한 자료는 사라짐)")
    ap.add_argument("--port", type=int, help="포트 (기본 config.port)")
    ap.add_argument("--no-window", action="store_true", help="창 자동 열기 끔")
    ap.add_argument("--config", default="", help="설정 파일 경로 (기본 %%LOCALAPPDATA%%\\report-1\\config.json)")
    ap.add_argument("--version", action="version", version=f"Report-1 {VERSION}")
    args = ap.parse_args(argv)
    config_path = os.path.abspath(args.config) if args.config else default_config_path()
    try:
        cfg, created = load_config(config_path, create=not (args.status or args.stop))
    except ConfigError as e:
        log(f"설정 오류: {e}")
        return 2
    port = args.port if args.port is not None else int(cfg.get("port") or 8775)
    if created:
        log(f"config.json 을 만들었습니다 → {config_path}")
    if args.set:
        rc = set_config_values(config_path, args.set)
        if rc or not (args.check or args.setup):
            return rc
        cfg, _ = load_config(config_path)
    if args.setup:
        return run_setup(config_path, args.provider, args.model, args.force)
    if args.check:
        rc = run_check(cfg, config_path)
        print("\n결과: OK" if rc == 0 else "\n결과: 점검 실패 · 위 메시지를 보고 고친 뒤 다시 --check (INSTALL.md '문제 해결')")
        return rc
    if args.draft is not None:
        return print_draft(cfg, config_path, args.draft, args.topic, args.form, args.basic)
    if args.shortcut:
        return set_shortcut(args.shortcut == "on")
    if args.status:
        url = wait_running(port, 8)
        print(f"실행 중: {url}" if url else "꺼져 있음")
        return 0 if url else 1
    if args.stop:
        return stop_running(port)
    running = find_running(port)
    if running:
        log(f"이미 실행 중입니다 → 창만 엽니다: {running}")
        if not args.no_window:
            open_app_window(running)
        return 0
    app = App(cfg, config_path)
    app.serve(port, open_window=bool(cfg.get("open_window", True)) and not args.no_window)
    return 0


INDEX_HTML = r"""<!doctype html>
<html lang="ko" data-theme="__THEME__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="report-token" content="__TOKEN__">
<title>Report–1 · 근거 달린 보고서</title>
<link rel="preload" href="/font/report-1-dos.woff" as="font" type="font/woff" crossorigin>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Crect x='4.5' y='4' width='15' height='18' fill='%230b0b0b' stroke='%23f2f2f3' stroke-width='1.4'/%3E%3Crect x='8.5' y='2' width='7' height='4' fill='%231f507a' stroke='%23f2f2f3' stroke-width='1.2'/%3E%3Crect x='8' y='10' width='2' height='2' fill='%23f2f2f3'/%3E%3Crect x='14' y='10' width='2' height='2' fill='%23f2f2f3'/%3E%3Cpath d='M8 16h8' stroke='%236aba23' stroke-width='1.6'/%3E%3C/svg%3E">
<style>
@font-face{font-family:"Report1DOS";src:url(/font/report-1-dos.woff) format("woff");font-display:block}
:root{
  /* works 팔레트 (docs/DESIGN.md › 02): 네이비 = 뼈대 · 버튼 · 번호 라벨, 라임 = 지금 · 켜짐 · 확정만, 회색 = 글자. 빨강 없음 — 경고는 가장 밝은 글자색 + ERR 칩 */
  --bg:#000;--dot:rgba(255,255,255,.075);--panel:#0b0b0b;--panel-2:#131313;--lcd:#030303;--lcd-edge:#2a2a2a;
  --ink:#f2f2f3;--ink-2:#a5aaae;--ink-3:#81888d;--lcd-ink:#f2f2f3;--lcd-ink-2:#a5aaae;
  --line:rgba(242,242,243,.09);--line-2:rgba(242,242,243,.2);
  --accent:#6aba23;--accent-ink:#6aba23;--accent-press:#45741b;--accent-glow:rgba(106,186,35,.35);--on-accent:#0b0b0b;
  --ok:#6aba23;--err:#f2f2f3;--err-ink:#0b0b0b;--seal:#6aba23;
  --key:#1c1c1c;--key-edge:#000;
  --prime:#1f507a;--prime-2:#3f77a6;--prime-deep:#002341;--prime-ink:#f2f2f3;
  --btn:#1f507a;--btn-ink:#f2f2f3;--btn-edge:#002341;--card-edge:#3f77a6;--hl:rgba(63,119,166,.28);
  /* 노브 = works 인코더 네 색: ①파랑 ②라임 ③흰색 ④회색 */
  --k1:#75a1c7;--k1-ink:#0b0b0b;--k1-edge:#3f77a6;
  --k2:#6aba23;--k2-ink:#0b0b0b;--k2-edge:#45741b;
  --k3:#f2f2f3;--k3-ink:#002341;--k3-edge:#81888d;
  --k4:#a5aaae;--k4-ink:#0b0b0b;--k4-edge:#5c6166;
  --dial:#101820;--screw:#1a1a1a;--screw-edge:#333;--screw-slot:#050505;
  --m-body:#0b0b0b;--m-line:#f2f2f3;--m-clip:#1f507a;--m-led:#6aba23;
  --dos:"Report1DOS","Cascadia Mono",Consolas,"D2Coding","GulimChe","굴림체",monospace;
  --b:1px 0 0 currentColor;
  color-scheme:dark;
}
:root[data-theme="light"]{
  --bg:#d4d6d8;--dot:rgba(0,35,65,.09);--panel:#f2f2f3;--panel-2:#fafafb;--lcd:#050709;--lcd-edge:#002341;
  --ink:#0b0b0b;--ink-2:#4c5156;--ink-3:#81888d;--line:rgba(0,35,65,.14);--line-2:rgba(0,35,65,.34);
  --accent-ink:#45741b;--accent-glow:rgba(106,186,35,.3);--err:#0b0b0b;--err-ink:#f2f2f3;--seal:#1f507a;
  --key:#e4e6e8;--key-edge:#a5aaae;--hl:rgba(63,119,166,.18);--k3-edge:#a5aaae;--dial:#e4e6e8;
  --screw:#dcdee0;--screw-edge:#a5aaae;--screw-slot:#81888d;--m-body:#f2f2f3;--m-line:#0b0b0b;
  color-scheme:light;
}
@media (prefers-color-scheme:light){:root[data-theme="system"]{
  --bg:#d4d6d8;--dot:rgba(0,35,65,.09);--panel:#f2f2f3;--panel-2:#fafafb;--lcd:#050709;--lcd-edge:#002341;
  --ink:#0b0b0b;--ink-2:#4c5156;--ink-3:#81888d;--line:rgba(0,35,65,.14);--line-2:rgba(0,35,65,.34);
  --accent-ink:#45741b;--accent-glow:rgba(106,186,35,.3);--err:#0b0b0b;--err-ink:#f2f2f3;--seal:#1f507a;
  --key:#e4e6e8;--key-edge:#a5aaae;--hl:rgba(63,119,166,.18);--k3-edge:#a5aaae;--dial:#e4e6e8;
  --screw:#dcdee0;--screw-edge:#a5aaae;--screw-slot:#81888d;--m-body:#f2f2f3;--m-line:#0b0b0b;
  color-scheme:light;
}}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--bg) radial-gradient(circle,var(--dot) 1px,transparent 1.4px) 0 0/16px 16px;color:var(--ink);font:16px/24px var(--dos);font-synthesis:none;font-variant-ligatures:none;-webkit-font-smoothing:antialiased;padding:8px;overflow:hidden}
button,input,textarea{font:inherit;color:inherit}
b{font-weight:inherit;text-shadow:var(--b)}
button:focus-visible,input:focus-visible,textarea:focus-visible,[contenteditable]:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
[hidden]{display:none!important}

/* 본체 */
.device{position:relative;max-width:1180px;height:100%;margin:0 auto;display:grid;grid-template-columns:minmax(0,1fr);grid-template-rows:auto minmax(0,1fr) auto auto;background:var(--panel);border:1px solid var(--line-2);border-radius:18px;overflow:hidden;box-shadow:0 24px 60px rgba(0,0,0,.45)}
.screw{position:absolute;width:9px;height:9px;border-radius:50%;background:var(--screw);border:1px solid var(--screw-edge);z-index:4;pointer-events:none}
.screw::after{content:"";position:absolute;left:1px;right:1px;top:50%;height:2px;margin-top:-1px;background:var(--screw-slot);transform:rotate(var(--r,35deg))}
.s1{top:8px;left:8px}.s2{top:8px;right:8px;--r:-25deg}.s3{bottom:8px;left:8px;--r:75deg}.s4{bottom:8px;right:8px;--r:10deg}

.bar{display:flex;align-items:center;gap:12px;padding:10px 24px 8px}
.logo{font-size:32px;line-height:32px;text-shadow:2px 0 0 currentColor;white-space:nowrap}
.logo::after{content:"_";color:var(--accent);animation:caret 1.06s steps(2) infinite}
.brand{align-self:flex-end;margin:0 0 4px -4px;line-height:16px;color:var(--ink-2);text-shadow:var(--b);white-space:nowrap}  /* 회사 이름 (config.company) */
.lcd{position:relative;display:flex;align-items:center;gap:10px;padding:4px 12px;background:var(--lcd);color:var(--lcd-ink);border:1px solid var(--lcd-edge);border-radius:10px;box-shadow:inset 0 2px 10px rgba(0,0,0,.75);min-width:0}
.lcd::after{content:"";position:absolute;inset:0;background:repeating-linear-gradient(0deg,rgba(255,255,255,.03) 0 1px,transparent 1px 3px);pointer-events:none}
#lcd-form{font-size:24px;line-height:32px;text-shadow:2px 0 0 currentColor;color:var(--k1);white-space:nowrap}
#lcd-meta{color:var(--lcd-ink-2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.leds{display:flex;gap:12px;margin-left:auto}
.led{display:flex;align-items:center;gap:4px;line-height:16px;color:var(--ink-2);white-space:nowrap}
.led i{width:8px;height:8px;background:var(--ink-3);opacity:.45}
.led.ok i{background:var(--ok);opacity:1;box-shadow:0 0 8px var(--accent-glow)}
.led.err i{background:var(--err);opacity:1}
.led.busy i{background:var(--accent);opacity:1;animation:blink .8s steps(2) infinite}
.power{width:32px;height:32px;border-radius:50%;border:1px solid var(--line-2);background:var(--key);cursor:pointer;line-height:30px;color:var(--ink-2);flex:none}

/* 결재판 캐릭터 */
.mascot{flex:none;width:30px;height:34px}
.mascot svg{display:block;width:100%;height:100%}
.mascot.idle svg{animation:bob 2.4s steps(2) infinite}
.mascot.think svg{animation:bob .45s steps(2) infinite}
.mascot.eat svg{animation:jump .35s cubic-bezier(.3,1.6,.5,1) 1}
.mascot.happy svg{animation:jump .7s cubic-bezier(.3,1.6,.5,1) 2}
.mascot.error svg{animation:shake .45s steps(4) 3}
.mascot .eye{fill:var(--m-line)}
.mascot.think .eye{animation:look .9s steps(2) infinite}
.mascot .mouth{stroke:var(--m-led)}
.mascot.error .mouth{stroke:var(--m-line)}

/* 구역 */
.main{display:grid;grid-template-columns:minmax(0,5fr) minmax(0,7fr);gap:10px;padding:0 12px;min-height:0}
.pane{display:flex;flex-direction:column;min-height:0;background:var(--panel-2);border:1px solid var(--line);border-radius:12px;overflow:hidden}
.pane-h{display:flex;align-items:center;gap:8px;padding:8px 12px;border-bottom:1px solid var(--line);line-height:16px;color:var(--ink-2);flex:none;white-space:nowrap}
.num{display:inline-block;padding:0 4px;background:var(--prime);color:var(--prime-ink);text-shadow:var(--b)}
.pane-h .name{color:var(--ink);text-shadow:var(--b)}
.pane-b{overflow:auto;padding:6px 12px 12px;min-height:0;flex:1}
.spacer{flex:1}
.chip{display:inline-block;padding:0 5px;line-height:16px;white-space:nowrap}
.chip.lime{background:var(--accent);color:var(--on-accent)}
.chip.navy{background:var(--prime);color:var(--prime-ink)}
.chip.err{background:var(--err);color:var(--err-ink);text-shadow:var(--b)}
.chip.out{border:1px solid var(--line-2);color:var(--ink-2);line-height:14px}
.chip.gap{border:1px dashed var(--ink-3);color:var(--ink-2);line-height:14px}
.chip.chk{border:1px solid var(--card-edge);color:var(--ink);line-height:14px}
.chip.warn{border:1px solid var(--ink);color:var(--ink);line-height:14px;text-shadow:var(--b)}
.ghost{border:1px solid var(--line-2);background:none;padding:0 6px;color:var(--ink-2);cursor:pointer;line-height:20px;white-space:nowrap}
.ghost:hover{color:var(--ink);border-color:var(--ink-2)}

/* 01 자료 */
.trow{display:flex;align-items:center;gap:8px;margin:6px 0 8px}
.trow label{color:var(--accent-ink);text-shadow:var(--b);white-space:nowrap}
#topic{flex:1;min-width:0;border:0;border-bottom:2px solid var(--ink-2);background:transparent;padding:4px 2px;outline:none;caret-color:var(--accent)}
#topic::placeholder,#drop::placeholder{color:var(--ink-3)}
#drop{display:block;width:100%;height:76px;resize:none;border:1px dashed var(--line-2);border-radius:8px;background:repeating-linear-gradient(135deg,transparent 0 8px,var(--line) 8px 9px);padding:6px 8px;outline:none;line-height:20px;caret-color:var(--accent)}
#drop:focus,#drop.over{border-color:var(--accent);border-style:solid}
.meter{display:flex;align-items:center;gap:8px;margin:8px 0 4px;line-height:16px;color:var(--ink-3);font-size:14px}
.meter .bar2{flex:1;height:8px;border:1px solid var(--line-2);position:relative;overflow:hidden}
.meter .bar2 i{position:absolute;left:0;top:0;bottom:0;background:var(--k2);width:0;transition:width .2s}
.meter.over .bar2 i{background:var(--err)}
.meter.over span{color:var(--ink);text-shadow:var(--b)}
.card{margin-top:8px;border:1px solid var(--line);border-radius:8px}
.ph{display:grid;grid-template-columns:18px auto minmax(0,1fr) auto 20px;align-items:center;gap:0 6px;padding:2px 6px;border-bottom:1px solid var(--line);line-height:20px}
.ph input,.fr input{accent-color:var(--accent);margin:0}
.ph .t{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-shadow:var(--b)}
.ph .m{color:var(--ink-3);font-size:14px;white-space:nowrap}
.x{border:0;background:none;color:var(--ink-3);cursor:pointer;padding:0 2px;line-height:20px}
.x:hover{color:var(--ink)}
.fr{display:grid;grid-template-columns:18px 38px minmax(0,1fr);align-items:start;gap:0 6px;padding:2px 6px;line-height:20px;border-radius:4px}
.fr input{margin-top:3px}
.fr .id{color:var(--k1)}
.fr .t{white-space:pre-wrap;overflow-wrap:anywhere;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;cursor:pointer}
.fr.open .t{display:block}
.fr.off .t,.fr.off .id{text-decoration:line-through;color:var(--ink-3)}
.fr.hl{background:var(--hl)}
.skip{color:var(--ink-3);font-size:14px;line-height:16px;padding:2px 30px 4px}
.hello{color:var(--ink-3);padding:18px 6px;line-height:24px}
.hello b{color:var(--ink)}

/* 02 보고서 */
.knobvals{display:flex;gap:4px;min-width:0;overflow:hidden}
.knobvals span{padding:0 5px;line-height:16px}
.kv1{background:var(--k1);color:var(--k1-ink)}.kv2{background:var(--k2);color:var(--k2-ink)}.kv3{background:var(--k3);color:var(--k3-ink);box-shadow:inset 0 0 0 1px var(--k3-edge)}.kv4{background:var(--k4);color:var(--k4-ink)}
.doc{position:relative}
.doc-t{font-size:20px;line-height:28px;text-shadow:var(--b);margin:6px 0 10px;padding-bottom:6px;border-bottom:2px solid var(--line-2);outline:none;overflow-wrap:anywhere}
.sec{margin:4px 0 12px}
.sec-h{line-height:20px;text-shadow:var(--b);margin-bottom:4px}
.ln{display:grid;grid-template-columns:18px minmax(0,1fr) auto 16px;gap:0 6px;align-items:start;padding:1px 4px;border-radius:4px;line-height:22px}
.ln.l2{padding-left:26px}
.ln:hover{background:var(--hl)}
.ln .dash{color:var(--ink-3)}
.ln .txt{outline:none;min-width:40px;overflow-wrap:anywhere}
.ln .txt:focus{background:var(--hl);box-shadow:0 2px 0 var(--accent)}
.ln .txt .n{text-decoration:underline wavy var(--ink);text-underline-offset:4px;text-shadow:var(--b)}
.ln .txt:empty::before{content:attr(data-ph);color:var(--ink-3)}
.ln .meta{display:flex;flex-wrap:wrap;gap:4px;justify-content:flex-end;align-items:center;max-width:300px}
.ref{border:1px solid var(--card-edge);color:var(--ink-2);background:none;padding:0 4px;line-height:16px;cursor:pointer}
.ref:hover{background:var(--card-edge);color:var(--prime-ink)}
.ln.err .txt{text-decoration:underline wavy var(--err);text-underline-offset:4px}
.ln.gap .txt{color:var(--ink-2)}
.ln .del{border:0;background:none;color:var(--ink-3);cursor:pointer;padding:0 2px;visibility:hidden}
.ln:hover .del{visibility:visible}
.add{border:1px dashed var(--line-2);background:none;color:var(--ink-3);cursor:pointer;padding:0 8px;line-height:20px;margin:2px 0 0 28px}
.blank{color:var(--ink-3);padding:2px 28px}
.seal{position:absolute;right:120px;top:0;width:92px;height:92px;border-radius:50%;border:3px solid var(--seal);color:var(--seal);display:grid;place-items:center;font-size:26px;line-height:26px;text-shadow:1.5px 0 0 currentColor;box-shadow:inset 0 0 0 3px var(--panel-2),inset 0 0 0 5px var(--seal);transform:rotate(-14deg);pointer-events:none;animation:stamp .45s cubic-bezier(.2,1.5,.35,1) both}
:root[data-theme="light"] .seal{mix-blend-mode:multiply}

/* 03 덱 */
.deck{display:flex;align-items:center;gap:14px;padding:10px 24px 8px;flex-wrap:wrap}
.knob{display:flex;align-items:center;gap:8px;border:0;background:none;padding:0;cursor:pointer;text-align:left}
.dial{position:relative;width:44px;height:44px;border-radius:50%;background:var(--kb);box-shadow:0 4px 0 var(--ke),inset 0 1px 0 rgba(255,255,255,.25);flex:none;transition:transform .06s}
.dial::after{content:"";position:absolute;left:50%;top:5px;width:4px;height:13px;margin-left:-2px;background:var(--ki);transform-origin:2px 17px;transform:rotate(var(--a,0deg));transition:transform .18s cubic-bezier(.3,1.6,.5,1)}
.knob:active .dial,.knob.pressed .dial{transform:translateY(3px);box-shadow:0 1px 0 var(--ke)}
.knob .lbl{display:flex;flex-direction:column;line-height:18px;min-width:64px}
.knob .lbl span{color:var(--ink-3);font-size:14px}
.k1{--kb:var(--k1);--ki:var(--k1-ink);--ke:var(--k1-edge)}
.k2{--kb:var(--k2);--ki:var(--k2-ink);--ke:var(--k2-edge)}
.k3{--kb:var(--k3);--ki:var(--k3-ink);--ke:var(--k3-edge)}
.k4{--kb:var(--k4);--ki:var(--k4-ink);--ke:var(--k4-edge)}
.acts{display:flex;align-items:center;gap:10px;margin-left:auto}
.btn{height:40px;padding:0 14px;border:0;border-radius:10px;background:var(--btn);color:var(--btn-ink);cursor:pointer;box-shadow:0 4px 0 var(--btn-edge);text-shadow:var(--b);transition:transform .06s,box-shadow .06s;white-space:nowrap}
.btn:active{transform:translateY(3px);box-shadow:0 1px 0 var(--btn-edge)}
.btn.key{background:var(--key);color:var(--ink);box-shadow:0 4px 0 var(--key-edge),inset 0 0 0 1px var(--line-2)}
.okb{width:64px;height:64px;border-radius:50%;border:0;background:var(--accent);color:var(--on-accent);text-shadow:var(--b);cursor:pointer;box-shadow:0 5px 0 var(--accent-press),0 8px 16px rgba(0,0,0,.25);transition:transform .06s,box-shadow .06s;flex:none}
.okb:active{transform:translateY(4px);box-shadow:0 1px 0 var(--accent-press)}
.btn:disabled,.okb:disabled{opacity:.4;cursor:default;transform:none}
.undo{border:1px solid var(--line-2);background:none;color:var(--ink-2);border-radius:8px;padding:0 10px;line-height:26px;cursor:pointer;white-space:nowrap}
.opt{display:flex;align-items:center;gap:4px;color:var(--ink-2);white-space:nowrap}
.opt input{accent-color:var(--accent)}
.foot{display:flex;align-items:center;gap:10px;padding:5px 24px 8px;border-top:1px solid var(--line);line-height:16px;color:var(--ink-3);white-space:nowrap}
.foot > span{overflow:hidden;text-overflow:ellipsis}
.toast{position:absolute;left:50%;bottom:112px;transform:translateX(-50%);background:var(--ink);color:var(--panel);padding:4px 12px;line-height:20px;z-index:6;animation:rise .25s ease-out;max-width:90%;text-align:center}
.drawer{position:absolute;left:12px;right:12px;top:56px;bottom:112px;display:flex;flex-direction:column;background:var(--panel-2);border:2px solid var(--card-edge);border-radius:12px;box-shadow:0 14px 34px rgba(0,0,0,.45);z-index:5;animation:drop .3s cubic-bezier(.2,1.3,.3,1)}
.drawer pre{margin:0;padding:10px 4px;font:inherit;white-space:pre-wrap;overflow-wrap:anywhere}
.shelf-h{margin:10px 0 4px;color:var(--ink-3);line-height:16px}
.row{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:8px;border-bottom:1px solid var(--line);padding:4px 2px;line-height:20px}
.row .t{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.row .t small{color:var(--ink-3);font-size:14px;margin-left:8px}
.row .b{display:flex;gap:6px}
.off-screen{position:fixed;inset:0;display:grid;place-items:center;background:var(--bg);color:var(--ink-2);z-index:9}

@keyframes caret{50%{opacity:0}}
@keyframes blink{50%{opacity:.25}}
@keyframes bob{50%{transform:translateY(-2px)}}
@keyframes jump{40%{transform:translateY(-8px)}}
@keyframes shake{25%{transform:translateX(-2px)}75%{transform:translateX(2px)}}
@keyframes look{50%{transform:translateX(1px)}}
@keyframes stamp{0%{opacity:0;transform:rotate(-14deg) scale(1.9)}100%{opacity:.92;transform:rotate(-14deg) scale(1)}}
@keyframes rise{from{opacity:0;transform:translate(-50%,8px)}}
@keyframes drop{from{opacity:0;transform:translateY(-10px) scaleY(.96)}}
@media (max-width:900px){
  body{overflow:auto}.device{height:auto;min-height:100%}
  .bar{flex-wrap:wrap;padding:10px 16px 8px}.lcd{order:3;flex:1 1 100%}
  .main{grid-template-columns:minmax(0,1fr)}.pane{max-height:none}.leds,.knobvals{display:none}
  .deck{padding:10px 16px 8px}.acts{flex-wrap:wrap;margin-left:0;width:100%}.acts .btn{flex:1}
  .foot{padding:5px 16px 8px;flex-wrap:wrap}.foot > span:first-child{flex:1 1 100%}
  .seal{right:12px}
}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>
</head>
<body>
<div class="device">
  <i class="screw s1"></i><i class="screw s2"></i><i class="screw s3"></i><i class="screw s4"></i>
  <div class="bar">
    <div id="mascot" class="mascot idle" title="결재판">
      <svg viewBox="0 0 30 34" aria-hidden="true">
        <rect x="2" y="5" width="26" height="28" rx="2" fill="var(--m-body)" stroke="var(--m-line)" stroke-width="2"/>
        <rect x="9" y="1" width="12" height="7" fill="var(--m-clip)" stroke="var(--m-line)" stroke-width="2"/>
        <rect class="eye" x="9" y="14" width="3" height="3"/><rect class="eye" x="18" y="14" width="3" height="3"/>
        <path class="mouth" d="M10 24h10" stroke-width="2.4"/>
      </svg>
    </div>
    <div class="logo">REPORT–1</div><div class="brand" id="brand" hidden></div>
    <div class="lcd"><span id="lcd-form">—</span><span id="lcd-meta">자료 0</span></div>
    <div class="leds">
      <span class="led" id="led-save" title="라임 = 보관됨 · 흰색 = 보관 안 한 자료 있음"><i></i>보관</span>
      <span class="led" id="led-llm"><i></i>llm</span>
    </div>
    <button class="power" id="power" title="끄기 (보관 안 한 자료는 사라집니다)">⏻</button>
  </div>

  <div class="main">
    <section class="pane" id="p-src">
      <div class="pane-h"><span class="num">01</span><span class="name">SOURCES</span><span>자료</span>
        <span class="chip out" id="src-n" title="체크된 조각 / 전체">0</span><span class="spacer"></span></div>
      <div class="pane-b">
        <div class="trow"><label for="topic">토픽 ›</label>
          <input id="topic" maxlength="80" placeholder="무엇에 대한 보고서인가요 — 예: 9월 결제 서버 장애" autocomplete="off"></div>
        <textarea id="drop" spellcheck="false" placeholder="메일 · 메신저 · 표 · 메모를 여기에 Ctrl+V&#10;화면 어디서든 붙여 넣어도 됩니다&#10;직접 쓴 메모는 적고 Ctrl+Enter"></textarea>
        <div class="meter" id="meter" title="체크된 조각의 글자 수 / 사내 LLM 에 한 번에 보낼 한도 (report.budget_chars)"><span class="bar2"><i></i></span><span id="meter-t">0 / 0자</span></div>
        <div id="pastes"></div>
      </div>
    </section>
    <section class="pane" id="p-draft">
      <div class="pane-h"><span class="num">02</span><span class="name">DRAFT</span><span>보고서</span>
        <span class="chip out" id="mode">—</span><span class="chip err" id="errs" hidden></span><span class="chip warn" id="nums" hidden></span>
        <span class="spacer"></span>
        <span class="knobvals" title="값의 색 = 그 값을 바꾸는 노브의 색"><span class="kv1" id="v1"></span><span class="kv2" id="v2"></span><span class="kv3" id="v3"></span><span class="kv4" id="v4"></span></span></div>
      <div class="pane-b"><div class="doc" id="doc"></div></div>
    </section>
  </div>

  <div class="deck">
    <span class="num">03</span>
    <button class="knob k1" data-k="1" title="Alt+1 · 양식"><span class="dial"></span><span class="lbl"><span>① 양식</span><b id="kl1"></b></span></button>
    <button class="knob k2" data-k="2" title="Alt+2 · 분량"><span class="dial"></span><span class="lbl"><span>② 분량</span><b id="kl2"></b></span></button>
    <button class="knob k3" data-k="3" title="Alt+3 · 어조"><span class="dial"></span><span class="lbl"><span>③ 어조</span><b id="kl3"></b></span></button>
    <button class="knob k4" data-k="4" title="Alt+4 · 읽는 사람"><span class="dial"></span><span class="lbl"><span>④ 독자</span><b id="kl4"></b></span></button>
    <div class="acts">
      <label class="opt" title="줄 끝에 [1] 을 붙이고 맨 아래에 근거 목록을 붙입니다"><input type="checkbox" id="withrefs"> 근거 붙이기</label>
      <button class="undo" id="undo" hidden></button>
      <button class="btn key" id="save" title="Ctrl+S · 붙여 넣은 원문을 이 PC 에 저장">보관</button>
      <button class="btn" id="draft" title="Ctrl+Enter">초안 만들기</button>
      <button class="okb" id="ok" title="Ctrl+Shift+Enter · 확정하고 복사" disabled>확정</button>
    </div>
  </div>
  <div class="foot"><span id="hint">원문은 메모리에만 · 보관을 눌러야 저장 · 체크한 조각만 사내 LLM 으로</span><span class="spacer"></span>
    <button class="ghost" id="new">새 토픽</button><button class="ghost" id="shelf">보관함</button><span id="model"></span><span id="ver"></span></div>
</div>

<script>
"use strict";
const BOOT = __BOOT__;
const TOKEN = document.querySelector('meta[name="report-token"]').content;
const $ = (s) => document.querySelector(s);
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
const fmt = (n) => Number(n || 0).toLocaleString("ko-KR");

// 노브 네 개 (docs/DESIGN.md › 원칙 2: 값의 색 = 그 값을 바꾸는 노브의 색)
const KNOBS = {
  1: { key: "form", vals: BOOT.forms.map(f => f.name), label: (v) => v },
  2: { key: "detail", vals: [1, 2, 3], label: (v) => ["짧게", "보통", "자세히"][v - 1] },
  3: { key: "tone", vals: ["brief", "prose"], label: (v) => (v === "brief" ? "개조식" : "서술식") },
  4: { key: "audience", vals: ["team", "boss", "exec"], label: (v) => ({ team: "팀 내부", boss: "상사", exec: "임원" })[v] },
};
const S = {
  form: BOOT.forms[0].name, detail: 2, tone: "brief", audience: "boss",
  desk: null, title: "", sections: [], lines: null, mode: "", draftForm: "", confirmed: null, busy: false, undoKind: "",
};

async function api(path, body) {
  const opt = { method: body ? "POST" : "GET", headers: { "X-Report-Token": TOKEN } };
  if (body) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
  const r = await fetch(path, opt);
  const d = await r.json().catch(() => ({}));
  if (!r.ok) { const e = new Error(d.error || `HTTP ${r.status}`); e.status = r.status; throw e; }
  return d;
}
function mascot(state) {
  const m = $("#mascot"); m.className = "mascot " + state;
  if (["happy", "error", "eat"].includes(state)) setTimeout(() => { if (m.className.includes(state)) m.className = "mascot idle"; }, state === "eat" ? 500 : 1600);
}
function toast(msg) {
  document.querySelectorAll(".toast").forEach(t => t.remove());
  const t = el("div", "toast", msg); $(".device").appendChild(t); setTimeout(() => t.remove(), 3000);
}
function led(id, state) { const e = $(id); e.classList.remove("ok", "err", "busy"); if (state) e.classList.add(state); }

// ── 노브
function renderKnobs() {
  for (const n of [1, 2, 3, 4]) {
    const k = KNOBS[n], v = S[k.key], i = Math.max(0, k.vals.indexOf(v));
    $(`#kl${n}`).textContent = k.label(v);
    $(`#v${n}`).textContent = k.label(v);
    document.querySelector(`.knob[data-k="${n}"] .dial`).style.setProperty("--a", `${-120 + (240 * i) / Math.max(1, k.vals.length - 1)}deg`);
  }
  $("#lcd-form").textContent = S.form;
}
async function turn(n, dir) {
  const k = KNOBS[n], i = k.vals.indexOf(S[k.key]);
  S[k.key] = k.vals[(i + dir + k.vals.length) % k.vals.length];
  const b = document.querySelector(`.knob[data-k="${n}"]`); b.classList.add("pressed"); setTimeout(() => b.classList.remove("pressed"), 120);
  renderKnobs();
  if (n === 1) {
    if (S.lines) { S.lines = null; S.confirmed = null; renderDraft(); toast("양식을 바꿔 초안을 비웠습니다 — 다시 초안 만들기"); }
    try { applyDesk((await api("/api/desk", { form: S.form })).desk); } catch (e) { toast(e.message); }
  }
}
document.querySelectorAll(".knob").forEach(b => {
  b.addEventListener("click", (e) => turn(+b.dataset.k, e.shiftKey ? -1 : 1));
  b.addEventListener("contextmenu", (e) => { e.preventDefault(); turn(+b.dataset.k, -1); });
  b.addEventListener("wheel", (e) => { e.preventDefault(); turn(+b.dataset.k, e.deltaY > 0 ? 1 : -1); }, { passive: false });
});

// ── 01 자료
function applyDesk(d) {
  S.desk = d;
  if (d.form && d.form !== S.form && KNOBS[1].vals.includes(d.form)) { S.form = d.form; renderKnobs(); }
  if (document.activeElement !== $("#topic")) $("#topic").value = d.topic || "";
  renderSources();
}
function renderSources() {
  const d = S.desk; if (!d) return;
  const ex = new Set(d.exclude);
  const nFr = d.pastes.reduce((a, p) => a + p.frags.length, 0);
  $("#src-n").textContent = `${nFr - ex.size}/${nFr}`;
  $("#lcd-meta").textContent = `자료 ${d.pastes.length} · 조각 ${nFr} · ${d.pastes.length ? (d.unsaved ? "보관 안 함" : "보관됨") : "비어 있음"}`;
  led("#led-save", !d.pastes.length ? "" : (d.unsaved ? "err" : "ok"));
  const m = $("#meter"), over = d.chars > d.budget;
  m.classList.toggle("over", over);
  m.querySelector("i").style.width = `${Math.min(100, (100 * d.chars) / Math.max(1, d.budget))}%`;
  $("#meter-t").textContent = `${fmt(d.chars)} / ${fmt(d.budget)}자` + (over ? " · 한도 초과 — 체크를 풀어 줄이세요" : "");
  const box = $("#pastes"); box.textContent = "";
  if (!d.pastes.length) {
    const h = el("div", "hello");
    h.innerHTML = "<b>토픽</b>을 적고, 모아 둔 글을 <b>그냥 붙여 넣으세요</b>.<br>메일 · 메신저 · 회의 메모 · 엑셀 표 — 순서도 형식도 상관없습니다.<br>붙여 넣은 것 하나 = 자료 하나, 조각(p1 p2 …)으로 나뉩니다.<br>원문은 <b>보관</b>을 눌러야 저장됩니다.";
    box.appendChild(h); return;
  }
  for (const p of d.pastes) {
    const card = el("div", "card"); card.dataset.a = p.id;
    const h = el("div", "ph");
    const all = el("input"); all.type = "checkbox"; all.title = "이 자료의 조각 전부";
    const on = p.frags.filter(f => !ex.has(f.id)).length;
    all.checked = on > 0; all.indeterminate = on > 0 && on < p.frags.length;
    all.addEventListener("change", () => setExclude(p.frags.map(f => f.id), !all.checked));
    const t = el("span", "t", p.title); t.title = p.title;
    const del = el("button", "x", "×"); del.title = "이 자료 지우기 (20초 안에 되돌리기)";
    del.addEventListener("click", () => delPaste(p.id));
    h.append(all, el("span", "chip navy", `자료 ${p.id.slice(1)} · ${p.kind_ko}`), t, el("span", "m", `조각 ${p.frags.length} · ${fmt(p.chars)}자`), del);
    card.appendChild(h);
    for (const f of p.frags) {
      const row = el("div", "fr" + (ex.has(f.id) ? " off" : "")); row.dataset.id = f.id;
      const cb = el("input"); cb.type = "checkbox"; cb.checked = !ex.has(f.id); cb.title = "체크한 조각만 초안 · LLM 에 씁니다";
      cb.addEventListener("change", () => setExclude([f.id], !cb.checked));
      const tx = el("span", "t", f.text); tx.title = "눌러서 펼치기";
      tx.addEventListener("click", () => row.classList.toggle("open"));
      row.append(cb, el("span", "id", f.id), tx); card.appendChild(row);
    }
    const skip = [];
    if (p.dups) skip.push(`같은 조각 ${p.dups}개`);
    if (p.quotes) skip.push(`메일 인용 ${p.quotes}줄`);
    if (skip.length) card.appendChild(el("div", "skip", `건너뜀: ${skip.join(" · ")}`));
    box.appendChild(card);
  }
}
async function setExclude(ids, off) {
  const ex = new Set(S.desk.exclude);
  ids.forEach(id => (off ? ex.add(id) : ex.delete(id)));
  try { applyDesk((await api("/api/desk", { exclude: [...ex] })).desk); await rejudge(); } catch (e) { toast(e.message); renderSources(); }
}
async function addPaste(text, memo) {
  if (!text || !text.trim()) return;
  if (text.length > BOOT.max_paste) { toast(`한 번에 ${fmt(BOOT.max_paste)}자까지 — 나눠서 붙여 넣으세요 (지금 ${fmt(text.length)}자)`); return; }
  try {
    const d = await api("/api/paste", { text, memo: !!memo });
    applyDesk(d.desk); mascot("eat");
    const a = d.added, extra = [];
    if (a.dups) extra.push(`같은 조각 ${a.dups}개`); if (a.quotes) extra.push(`인용 ${a.quotes}줄`);
    toast(`자료 ${a.id.slice(1)} · 조각 ${a.frags}개` + (extra.length ? ` · 건너뜀 ${extra.join(" · ")}` : ""));
    const card = document.querySelector(`.card[data-a="${a.id}"]`); if (card) card.scrollIntoView({ block: "nearest" });
    if (S.lines) rejudge();
  } catch (e) { toast(e.message); mascot("error"); }
}
async function delPaste(aid) {
  try { const d = await api(`/api/paste/${aid}/delete`, {}); applyDesk(d.desk); startUndo("paste", d.undo_sec, "자료 지움"); await rejudge(); }
  catch (e) { toast(e.message); }
}
const drop = $("#drop");
drop.addEventListener("paste", (e) => { e.preventDefault(); e.stopPropagation(); addPaste(e.clipboardData.getData("text/plain")); });
drop.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); e.stopPropagation(); const t = drop.value; drop.value = ""; addPaste(t, true); }
});
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); addPaste(e.dataTransfer.getData("text/plain")); });
document.addEventListener("paste", (e) => {   // 화면 어디서든 붙여 넣기 — 글 칸 · 고치는 줄 안에서는 보통대로
  const t = e.target;
  if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
  e.preventDefault(); addPaste(e.clipboardData.getData("text/plain"));
});
$("#topic").addEventListener("change", async (e) => {
  try { applyDesk((await api("/api/desk", { topic: e.target.value })).desk); if (S.lines && !S.titleEdited) { S.title = S.desk.topic || S.title; renderDraft(); } } catch (err) { toast(err.message); }
});
$("#topic").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.isComposing) { e.preventDefault(); e.target.blur(); } });

// ── 02 보고서
const STATE_CHIP = { err: ["chip err", "ERR 근거 없음"], user: ["chip navy", "직접"], infer: ["chip out", "추론"], check: ["chip chk", "확인"], gap: ["chip gap", "빈칸"] };
function hlFrag(id, on) {
  document.querySelectorAll(`.fr[data-id="${id}"]`).forEach(r => { r.classList.toggle("hl", on); if (on) { r.classList.add("open"); r.scrollIntoView({ block: "nearest" }); } });
}
function fragText(id) {
  if (!S.desk) return "";
  for (const p of S.desk.pastes) for (const f of p.frags) if (f.id === id) return `자료 ${p.id.slice(1)} · ${p.kind_ko} — ${f.text.slice(0, 160)}`;
  return "";
}
function paintText(span, ln) {
  span.textContent = "";
  if (!ln.nums || !ln.nums.length || ln.origin === "user") { span.textContent = ln.text; return; }
  const re = /\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?/g, want = new Set(ln.nums);
  let last = 0, m;
  const norm = (s) => { s = s.replace(/,/g, ""); if (s.includes(".")) s = s.replace(/0+$/, "").replace(/\.$/, ""); const [i, f] = s.split("."); return (i.replace(/^0+/, "") || "0") + (f ? "." + f : ""); };
  while ((m = re.exec(ln.text))) {
    if (!want.has(norm(m[0]))) continue;
    span.append(ln.text.slice(last, m.index));
    const n = el("span", "n", m[0]); n.title = "근거 조각에 없는 숫자 — 확인하세요"; span.append(n); last = m.index + m[0].length;
  }
  span.append(ln.text.slice(last));
}
function renderDraft() {
  const doc = $("#doc"); doc.textContent = "";
  $("#mode").textContent = S.mode === "llm" ? "LLM" : (S.mode === "basic" ? "기본" : "—");
  if (!S.lines) {
    const h = el("div", "hello");
    h.innerHTML = "<b>① 양식</b>을 고르고 <b>초안 만들기</b>(Ctrl+Enter).<br>맨 위는 <b>요약</b>(결론부터), 줄마다 근거 조각이 붙습니다.<br>근거 없는 사실은 <b>ERR</b> — 확정할 수 없습니다. 조각에 없는 숫자는 <b>물결 밑줄</b>.<br><b>추론</b> = 조각을 이은 판단 · <b>확인</b> = 자료끼리 다름 · <b>빈칸</b> = 자료에 없음.";
    doc.appendChild(h); $("#errs").hidden = true; $("#nums").hidden = true; $("#ok").disabled = true; return;
  }
  const t = el("div", "doc-t", S.title); t.contentEditable = "true"; t.title = "보고서 제목 — 눌러서 고치기";
  t.addEventListener("input", () => { S.title = t.textContent.replace(/\s+/g, " ").trim(); S.titleEdited = true; S.confirmed = null; });
  t.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); t.blur(); } });
  doc.appendChild(t);
  S.sections.forEach((name, si) => {
    const sec = el("div", "sec");
    sec.appendChild(el("div", "sec-h", `□ ${name}`));
    const rows = S.lines.map((ln, i) => [ln, i]).filter(([ln]) => ln.section === si);
    if (!rows.length) sec.appendChild(el("div", "blank", "○ 자료 없음"));
    for (const [ln, i] of rows) {
      const row = el("div", "ln" + (ln.level === 2 ? " l2" : ""));
      const txt = el("span", "txt"); paintText(txt, ln);
      txt.dataset.ph = ln.state === "gap" ? "자료 없음 — 눌러서 직접 쓰기" : "";
      try { txt.contentEditable = "plaintext-only"; } catch (e) { /* 지원 안 하는 브라우저 */ }
      if (txt.contentEditable !== "plaintext-only") txt.contentEditable = "true";
      txt.addEventListener("input", () => { ln.text = txt.textContent; if (ln.origin !== "user") { ln.origin = "user"; ln.state = "user"; ln.nums = []; paintMeta(row, ln); } S.dirtyLine = true; });
      txt.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); txt.blur(); } });
      txt.addEventListener("blur", () => { if (S.dirtyLine) { S.dirtyLine = false; rejudge(); } });
      const meta = el("span", "meta");
      const del = el("button", "del", "×"); del.title = "이 줄 지우기";
      del.addEventListener("click", () => { S.lines.splice(i, 1); rejudge(); renderDraft(); });
      row.append(el("span", "dash", ln.level === 2 ? "-" : "○"), txt, meta, del);
      paintMeta(row, ln); sec.appendChild(row);
    }
    const add = el("button", "add", "+ 줄"); add.title = "직접 쓰는 줄 — '직접' 으로 표시되고, 그 줄의 책임은 쓴 사람에게";
    add.addEventListener("click", () => {
      S.lines.push({ section: si, text: "", refs: [], kind: "fact", level: 1, origin: "user", state: "user", nums: [] }); renderDraft();
      const all = doc.querySelectorAll(".sec")[si].querySelectorAll(".txt"); const last = all[all.length - 1]; if (last) last.focus();
    });
    sec.appendChild(add); doc.appendChild(sec);
  });
  if (S.confirmed) doc.appendChild(el("div", "seal", "확정"));
  const errs = S.lines.filter(x => x.state === "err").length, nums = S.lines.filter(x => x.nums && x.nums.length).length;
  $("#errs").hidden = !errs; $("#errs").textContent = `ERR ${errs}`;
  $("#nums").hidden = !nums; $("#nums").textContent = `숫자? ${nums}`;
  $("#ok").disabled = S.busy || !!errs || !!S.confirmed || !S.lines.some(x => x.text.trim() && x.state !== "gap");
}
function paintMeta(row, ln) {
  const meta = row.querySelector(".meta"); meta.textContent = "";
  for (const r of ln.refs) {
    const b = el("button", "ref", r); b.title = fragText(r) || r;
    b.addEventListener("mouseenter", () => hlFrag(r, true)); b.addEventListener("mouseleave", () => hlFrag(r, false));
    b.addEventListener("click", () => hlFrag(r, true));
    meta.appendChild(b);
  }
  if (ln.nums && ln.nums.length && ln.origin !== "user") { const c = el("span", "chip warn", `숫자? ${ln.nums.join(" ")}`); c.title = "근거 조각에 없는 숫자"; meta.appendChild(c); }
  const chip = STATE_CHIP[ln.state]; if (chip) meta.appendChild(el("span", chip[0], chip[1]));
  row.classList.toggle("err", ln.state === "err"); row.classList.toggle("gap", ln.state === "gap");
}
function draftBody(extra) {
  return Object.assign({ form: S.draftForm, sections: S.sections, title: S.title, tone: S.tone, with_refs: $("#withrefs").checked,
    lines: S.lines.filter(x => x.text.trim() || x.state === "gap") }, extra || {});
}
async function rejudge() {
  if (!S.lines) return;
  try {
    const d = await api("/api/preview", draftBody());
    const keep = S.lines.filter(x => !x.text.trim() && x.state !== "gap");
    S.lines = d.lines.concat(keep); S.sections = d.sections; S.confirmed = null; renderDraft();
  } catch (e) { toast(e.message); }
}
async function makeDraft() {
  if (S.busy) return;
  if (!S.desk || !S.desk.pastes.length) { toast("먼저 자료를 붙여 넣으세요"); drop.focus(); return; }
  S.busy = true; mascot("think"); led("#led-llm", "busy"); $("#draft").disabled = true; $("#draft").textContent = "쓰는 중…"; renderDraft();
  try {
    const d = await api("/api/draft", { detail: S.detail, tone: S.tone, audience: S.audience });
    Object.assign(S, { lines: d.lines, sections: d.sections, title: d.title, mode: d.mode, draftForm: d.form, confirmed: null, titleEdited: false });
    if (d.error) toast(d.error);
    mascot(d.lines.some(x => x.state === "err") ? "error" : "idle");
  } catch (e) { toast(e.message); mascot("error"); }
  S.busy = false; $("#draft").disabled = false; $("#draft").textContent = "초안 만들기"; renderDraft(); state();
}
$("#draft").addEventListener("click", makeDraft);

// ── 보관 · 확정 · 복사 · 되돌리기
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch (e) {
    const ta = el("textarea"); ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0"; document.body.appendChild(ta); ta.select();
    let ok = false; try { ok = document.execCommand("copy"); } catch (e2) { ok = false; } ta.remove(); return ok;
  }
}
async function save() {
  try { const d = await api("/api/save", {}); applyDesk(d.desk); mascot("happy"); toast(`보관했습니다 — topics\\${d.saved}.json`); }
  catch (e) { toast(e.message); }
}
let undoTimer = 0;
function startUndo(kind, sec, label) {
  S.undoKind = kind; let left = sec; const u = $("#undo"); u.hidden = false; u.textContent = `${label} · 되돌리기 ${left}`;
  clearInterval(undoTimer);
  undoTimer = setInterval(() => { left -= 1; u.textContent = `${label} · 되돌리기 ${left}`; if (left <= 0) { clearInterval(undoTimer); u.hidden = true; S.undoKind = ""; } }, 1000);
}
async function confirmDraft() {
  if ($("#ok").disabled) return;
  try {
    const d = await api("/api/confirm", draftBody());
    S.confirmed = d; renderDraft(); mascot("happy");
    toast((await copyText(d.text)) ? "확정 · 복사했습니다 — 메일에 붙여 넣으세요" : "확정했습니다 (복사는 보관함에서)");
    startUndo("confirm", d.undo_sec, "확정");
  } catch (e) { toast(e.message); mascot("error"); }
}
async function undo() {
  if ($("#undo").hidden) return;
  try {
    const d = await api("/api/undo", {}); clearInterval(undoTimer); $("#undo").hidden = true;
    applyDesk(d.desk);
    if (d.undone === "confirm") { S.confirmed = null; renderDraft(); }
    if (d.undone === "paste") await rejudge();
    toast("되돌렸습니다");
  } catch (e) { toast(e.message); $("#undo").hidden = true; }
}
$("#ok").addEventListener("click", confirmDraft);
$("#undo").addEventListener("click", undo);
$("#save").addEventListener("click", save);

// ── 새 토픽 · 보관함
async function withDiscard(path, body) {
  try { return await api(path, body); } catch (e) {
    if (e.status !== 409) throw e;
    if (!window.confirm(`${e.message}\n\n보관하지 않고 버릴까요?`)) return null;
    return api(path, Object.assign({}, body, { discard: true }));
  }
}
function clearDraft() { Object.assign(S, { lines: null, sections: [], title: "", mode: "", confirmed: null }); renderDraft(); }
$("#new").addEventListener("click", async () => {
  try { const d = await withDiscard("/api/desk/new", {}); if (!d) return; applyDesk(d.desk); clearDraft(); $("#topic").value = ""; $("#topic").focus(); }
  catch (e) { toast(e.message); }
});
function closeDrawer() { document.querySelectorAll(".drawer").forEach(d => d.remove()); }
async function openShelf() {
  closeDrawer();
  const dr = el("div", "drawer"); const h = el("div", "pane-h"); h.append(el("span", "num", "04"), el("span", "name", "보관함"), el("span", "spacer"));
  const x = el("button", "ghost", "닫기 Esc"); x.addEventListener("click", closeDrawer); h.appendChild(x); dr.appendChild(h);
  const body = el("div", "pane-b"); dr.appendChild(body); $(".device").appendChild(dr);
  try {
    const [tp, rp] = await Promise.all([api("/api/topics"), api("/api/reports")]);
    body.appendChild(el("div", "shelf-h", `보관한 토픽 ${tp.topics.length} · 원문 포함 · %LOCALAPPDATA%\\report-1\\topics`));
    if (!tp.topics.length) body.appendChild(el("div", "hello", "아직 없습니다 — 자료를 붙여 넣고 보관(Ctrl+S)"));
    for (const t of tp.topics) {
      const row = el("div", "row"); const tt = el("span", "t", t.topic || "(토픽 없음)");
      tt.appendChild(el("small", null, `${t.form} · 자료 ${t.pastes} · 조각 ${t.frags} · ${t.updated.replace("T", " ").slice(0, 16)}`));
      const b = el("span", "b"), open = el("button", "ghost", "열기"), del = el("button", "ghost", "지우기");
      open.addEventListener("click", async () => {
        try { const d = await withDiscard(`/api/topics/${t.id}/open`, {}); if (!d) return; applyDesk(d.desk); clearDraft(); closeDrawer(); toast("토픽을 열었습니다"); }
        catch (e) { toast(e.message); }
      });
      del.addEventListener("click", async () => {
        if (!window.confirm(`'${t.topic || t.id}' 보관본을 지울까요? (20초 안에 되돌리기)`)) return;
        try { const d = await api(`/api/topics/${t.id}/delete`, {}); applyDesk(d.desk); startUndo("topic", d.undo_sec, "보관본 지움"); openShelf(); }
        catch (e) { toast(e.message); }
      });
      b.append(open, del); row.append(tt, b); body.appendChild(row);
    }
    body.appendChild(el("div", "shelf-h", `확정한 보고서 ${rp.reports.length} · 복사한 글 그대로`));
    if (!rp.reports.length) body.appendChild(el("div", "hello", "아직 없습니다"));
    for (const r of rp.reports) {
      const row = el("div", "row"); const tt = el("span", "t", r.title);
      tt.appendChild(el("small", null, `${r.form} · ${r.confirmed.replace("T", " ").slice(0, 16)}`));
      const b = el("span", "b"), view = el("button", "ghost", "보기"), cp = el("button", "ghost", "복사");
      const get = () => api(`/api/reports/${encodeURIComponent(r.key)}`);
      view.addEventListener("click", async () => { try { const full = await get(); const pre = el("pre", null, full.text); row.after(pre); view.disabled = true; } catch (e) { toast(e.message); } });
      cp.addEventListener("click", async () => { try { const full = await get(); toast((await copyText(full.text)) ? "복사했습니다" : "복사하지 못했습니다"); } catch (e) { toast(e.message); } });
      b.append(view, cp); row.append(tt, b); body.appendChild(row);
    }
  } catch (e) { toast(e.message); }
}
$("#shelf").addEventListener("click", openShelf);

// ── 상태 · 끄기 · 키
async function state() {
  try {
    const d = await api("/api/state");
    led("#led-llm", !d.llm_ready ? "" : (d.llm_ok === false ? "err" : "ok"));
    $("#model").textContent = d.llm_ready ? d.model : "LLM 없음 · 기본 초안";
    if (S.desk && (d.desk.unsaved !== S.desk.unsaved || d.desk.frags !== S.desk.pastes.reduce((a, p) => a + p.frags.length, 0))) load();
  } catch (e) { /* 꺼졌을 수 있다 */ }
}
async function load() { try { applyDesk((await api("/api/desk")).desk); } catch (e) { toast(e.message); } }
$("#power").addEventListener("click", async () => {
  if (S.desk && S.desk.unsaved && !window.confirm("보관 안 한 자료가 있습니다. 끄면 사라집니다 — 끌까요?")) return;
  try { await api("/api/shutdown", {}); } catch (e) { /* 이미 꺼짐 */ }
  S.off = true; document.body.appendChild(el("div", "off-screen", "Report–1 을 껐습니다 · 창을 닫아도 됩니다"));
});
window.addEventListener("beforeunload", (e) => { if (!S.off && S.desk && S.desk.unsaved) { e.preventDefault(); e.returnValue = ""; } });
document.addEventListener("keydown", (e) => {
  const typing = e.target.isContentEditable || e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA";
  if (e.altKey && ["1", "2", "3", "4"].includes(e.key)) { e.preventDefault(); turn(+e.key, e.shiftKey ? -1 : 1); }
  else if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === "Enter") { e.preventDefault(); confirmDraft(); }
  else if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); makeDraft(); }
  else if ((e.ctrlKey || e.metaKey) && (e.key === "s" || e.key === "S")) { e.preventDefault(); save(); }
  else if ((e.ctrlKey || e.metaKey) && (e.key === "z" || e.key === "Z") && !$("#undo").hidden && !typing) { e.preventDefault(); undo(); }
  else if (e.key === "Escape") closeDrawer();
});

$("#ver").textContent = `v${BOOT.version}`;
if (BOOT.company) { $("#brand").textContent = BOOT.company; $("#brand").hidden = false; }
renderKnobs(); renderDraft(); state(); load();
setInterval(state, 20000);   // 창이 열려 있다는 신호 — 닫으면 idle_exit_min 뒤 서버가 꺼진다 (보관 안 한 자료가 있으면 기다린다)
</script>
</body>
</html>
"""


# ─────────────────────────────────────────────────────────────── 내장 폰트
# Report1DOS — GNU Unifont 15.1.01 부분집합 (Secretary–1 과 같은 파일) · SIL Open Font License 1.1 (fonts/OFL.txt)
# Copyright © 1998-2023 Roman Czyborra, Paul Hardy, Qianqian Fang, Andrew Miller, Johnnie Weaver, David Corbett,
# Nils Moskopp, Rebecca Bettencourt, Minseo Lee, Ho-Seok Ee, et al. — python build.py 가 채운다
FONT_WOFF_B64 = """
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
EgmJ7CCRUyUySSIvS2SVRBlJVFeJCpaoDRJ1SKJeSLSuRPeS6DCJ3iPRZTKjqczoKzMWyYzTEqMk
prvELJKYKzJTX2a6ycxgmZkrMz/JLBuZNU5mZcqspxJbU2I7SmyQxG6R2PMS+01mm8lsP5m9QmZf
lzkNZE53mRMjc4pkTqXM7SRz58vc8zJPT+aNlHlLZN4xmS8yv5vMXybzT0lcDYnrKXGRErdT4l7I
gmayoKMs8JUFi2TBYVnwXBY2koVDZeFsWbhbFj6XRY1k0RBZtEYWXZf4ehI/WOJnSfx2iX8ti5vJ
4tGyeIksviAJkIRWkjBAEuZLQqEk3JCECkk0kcShkhgriUWS+EOWGMmSPrJkviw5Ikt+y9KOsjRS
lh6UpVWyzEyW+ciyFbLsoiyvLcudZHmULM+T5fdlhZIV9rJiiqyYJyvSZcVJWfFVVtaTld1l5VxZ
mSErL8jKClllLqt8ZdVqWXVeVpOs7iyrx8rqxbL6uKwukTWtZc1AWZMoa47ImieSxJLUWpJGSNJM
ScqUpJuSXFuSHSU5SpKPSPI7WdtQ1g6QtStl7U1J0ZeUwZKSJimvZV1dWddF1i2UdWdlvaasd5T1
0bJ+n6x/Jql1JNVDUmMkNUNSr0hqtWxwlQ1TZcMe2fBD0swkbYSkpUjafdnYTDb6ycbtsrFM0jtJ
epCkb5L017LJQjaFyqYtsumDbG4tm31l83LZfE4yNCSjhWR0l4xQydgmGdcks5ZkeklmmGRuksw7
klVXsvpKVqJkXZAttWVLf9kSKVu2yJbXstVYto6SrYmy9bxsrZZt5rLNR7bNk237Zdt12VYu25vI
9n6yPUK275btb2VHHdnhKjuCZUem7HgkOxvIzv6yc5nsvCQ7v8kuI9k1XHatkV03ZTdkt5vsDpfd
G2T3edldKdmWku0q2cMke5Zk75LsC5L9W3LaS46P5ERJzlbJuSe5OpLbVXJnSO4+yf0qe3Rlj53s
mSJ70mTPXdnzV/JsJW+85MVJ3nbJuy55VbLXUPY6yd7xsjdF9h6Wvd8l30byh0j+fMkvlPwSKbCS
gklSkCkFr2Sfmezzkn3TZd9e2fdB9lvK/sGyf5XsvyD7S6SwoRT2lMIYKVwmhTuk8LIUVkqRgRT1
kKJZUrRBik5I0Rc5YCQHBsqBxXLgqBz4KQdt5aCPHIyQgzvl4EM5pC+HOsqhYDm0UQ4dkUPP5HAN
OdxBDveRw8FyeK0cviiHP8uRlnJkjBxZIEf2yJGXcrSRHB0kR1fI0UtyrJYc85Jj0+TYejl2W47X
luO95fh0OZ4nx9/Kidpywk5O+MmJJDmxV07clf8uypPOcnKcnEyTk4/llIacspNTgXJqm5x6I6dN
5fR4Ob1dTn+WMwZyxkPOzJMzR+RMtZxtK2eD5ex2OXtdzlbJuXZybqKcmy/ntsu523K+tpy3lfPB
cj5Hzt+VCxpywVUuRMmFQrlQIRft5GK0XDwqF9/KJX25NEAuLZNL1+VStVx2k8vRcjlDLl+TK5Ar
DnJlhFxZKFcOyJUKudpCro6Xqzvl6n25piPXesu1JXLtuhQbSPEIKd4ixaVy3Uiu+8j1tXL9ntww
lhuD5Uaq3HgoN2vKTVe5GSE38+TmRbn5UW7py60ecitAbm2WW4/lNsnt1nJ7jNxeK7dvyB1tudNT
7sTLnQty54vcbSB3feTuYrl7Xu5+k3tt5N54ubdY7u2Ve8/kvp7ct5H7Q+X+Irl/XO6/lwdm8sBf
HqyWB6flwV956CQPY+ThYXn4Vx55yKMEebRPHr2Sx6byeJw83iaP78mThvJkkDyZI09y5clLedpY
njrK05HyNEGenpCn7+RZC3nmJ8+WyLND8qxMnreW54HyfJc8/yAv2siLMHmxQV5ckJc15KWHvFwo
L/fJy+/yqo28GiKv4uTVfnn1SV7XkdeO8nqyvM6S19fkjY688ZE3s+XNXnnzWd5ay9up8navvC2X
d67ybqG8y5d3r+S9ubyfKO+z5f0z+dBCPoyVD8vkwzH5UC4f28rHbvJxvHxMlI+H5eNj+aQnn7zk
01T5lCKfLsinKvnsIJ9D5PMO+fxWvpjJF0/5EiJfdsiXJ1LSWEq6SsksKcmTkltS8ltKzaV0iJRG
SelmKb0hX7Xlq6N8jZSvh+TrOylrLGWDpSxJyu7Jt8bybZR82yrfSuR7E/neR76vkO/XpNxAyj2l
fImUX5TyH1LRSipGSUWKVByRig/yw0h+jJIfS+VHsfw0lJ+e8nOO/DwmlSSVnlK5Qirvyq8W8itE
fm2WX3fkd1P5PUZ+75LfL+SPhfyZIn82yJ/r8reW/PWUvxPlb6L8LZK/JVJlIFXeUrVSqg5K1Xv5
11z+jZB/6+Xffak2lGpfqd4s1Rel+oeCvcI0hQKFl4pMFPkqWqBor6JXihspdlA8UnGi4lOKPyox
V+KvZJWSk0p+KWWv1HSl9itVoTSclcZcpbFLadxXmg2V5iCluU5pXlA1tFSNrqpGsKqxQdW4prQ0
lJaR0uqktPyU1hqlVaS0PqualqpmH1Vzuqq5RdW8p2rVUbV6qlqzVa1DqtZvVbuZqt1T1Z6rau9V
tcuUdmOlPVBpxyvtXUr7htKuUjptlI630pmhdHYrnbeqTn1VZ4iqs1HVuaTqVKm6TqruDFX3qNKF
0u2mdJcp3XtKTym9jkpvttI7oeqJqueg6s1Q9YpUvddK30Dpeyn9hUo/V+k/UvV1Vf3+qn6cqn9O
GdRVBu7KIEoZFCqDX6qBu2oQrxpcU4aNleFkZbheGV5TDQ1UQ1/VcJtq+Eg1aqEa+atG61Sjq6px
DdXYUzX2V42XqsaHVOMy1aSJajJcNUlTTc6qJuWqaWvVdLJqukM1faeatVLNglSzfNXskTKqrYz6
KqMlyuiSMvqlmndUzcNU8w2q+QXV/LcytlHGfZVxuDJOU8Y3lPEvZWKrTEKUyXplclGZ/FUtOqgW
U1WL3arFW9XSXLWcqFquUC2Pqpa/lamDMo1SptuV6TtlZqTMPJVZpDLbqcweK7MyZV5Xmdsr84nK
fKEyP6jMv6lW9VUrV9UqSLXarFrdVxa6ysJTWSxUFqeVxRtlWVtZdlWWUcqyQFk+Ulb6yqqHspqs
rJYrq4PK6r2yVsraQlkPUtaJyjpPWX9UrS1Vax/Veo5qvV+1LlVt2qg2garNTtXms2pro9oOU20X
qLanVNu/qp2bahek2u1S7V4pm9rKxlHZTFY2G5VNvrIpVjblqn1L1d5DtZ+u2ueo9tdU+wpla6ps
hyrb5cr2rLL9qzp0VB2mqw5rVYfDqsM3ZWem7MYqu3hld0zZfVX2esreQdmPVfbLlX2Bsn+uHAyU
wyDlEKcczinHOsqxs3KMVI77lWOl6thZdVykOl5VTo2U0yTllKKcrihnfeU8RDlnKOf7yqW5chmn
XFYrl/PKlZRrZ+U6WbmuV643VScD1clTdVqhOj1SbrrKzUu5LVdud1RnY9U5UHUuVO6ayn2ocl+q
3M+qLrqqy1DVZZvq8kJ5tFYeYcpju/J4rroaqa5jVdcE1fWQ6vpddXNQ3QJUtzzV7a/q3l51D1L/
R9F5f4Xg+F3ceE97k72yd8gWUSijsjUImcmo0KBsaVCyE0lKKVlJIUWUUERmGSl774/xPN/f7n/w
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
MymSQpJiJSn7JeWzpLaR1GmSGiep3+TsUDm7Qs5mybkacs5czvnIuXNyvrycbyPnbeT8ejl/Uc5/
kbRekuYraUcl7blcaCEXZsqFWLnwQdJ7SrqvpF+T9N+S0U0yPCTjnFwsLxd7yUVvuXhWLr6RS03k
0gS5FCKXTsmlp5JZXTItJdNDMpMl87dc7iCXHeXybrl8V64YyBVbuRImV55JVhvJmihZ/pJ1Q7Kr
S/ZEyQ6U7Hy5Wl2uDpKrbnI1Xq6WSk4NyekpOY6Ss0NyzknOD7lmLNcc5FqAXMuQa3/kel+5vlyu
J8n1X3JjgNxwkhvBciNXcitIrqXkekjuacn9KHkGkjdU8twlL1byHslNlpu95aab3NwvN5/IrVZy
a6zc2iC3Lko+SP4wyfeX/Fy5bSC3p8vtLXI7Q+6w3DGXO0FyJ0MKWArMpMBVCqKk4JHcrSd3TeWu
u9xNlLvf5F57uecq99Ll3k+531Pue8r9i/Kgujywlwex8uCPPBwjD9fLw3R5VFUeTZRHMfKoRAqN
pNBTCo9J4Vsp6ihFi6RonxQVyOM68thBHu+Qx8/libE8WSxPjsuT3/J0uDzdJU9fy7N+8ixYnr2U
4pZSPF2KT8jzsvJ8vDzfLs9fSEl3KXGRkngp+SSlfaTUWUqjpfS1vOglL9zkRaa8bCgvp8jLffLy
rbwaIK9C5NULed1fXm+X15/kTVd54ypvsuRtfXm7RN6elneV5Z2dvNsj74rkfWt5v0TeR8n7J/Kh
pXxYJB/i5cM/+ThOPm6Vj/fkUyv5tFQ+5cjnZvLZXT7nypf28mWufDkiX8vJVxv5GidfP8o3M/m2
Tb7dlu/15PtU+R4n30vkR2v5sVB+ZMhPkp928jNZfv6VX8Pl1x759Vn+GyX/xchvkN8z5Pcl+VNB
/tjIn3j5i/J3hvxNkH8V5N9U+XdQ/r3TMv20TKCWOatlvmhZIy3rpWVParlyWm6slgvScrla3kDL
O2n5JAVRmKSQoEiKgxR9FPOUGistUTqhjMpWyv7KV1WqqkxQ8VfJUq2iaqe6R/W9VjDXChu0wg2t
2FgrLtKKV7RSE63krpVuauXOWnmhVj6pVSppFQetcuZ/fxRVJ2rVw1r1tVbrotU8tNoVrfafVu+p
1Zdr9UytUV5rjNUah7XGS63ZSWt6as0crdVMa7lrrata21Br+2jt81qnnNaZoHWitW5ZrWumdXdr
3ddar53Wc9Z6J9WgrBr0UYPlapCm9atrfWutf0gblNUGQ7RBgDYo1IZG2tBfGz7XRgO00R5t9J82
HqCN12rjQm1ipE02a5N72rSbNl2nTbO0WTVtZqvN4rTZM23eQJtP0eYHtXmRtuioLXy0Raq2+Kst
h2nLbdryhRr2UUN/NXymrfpqq6XaKklbq7aeoK2PaOv32maQtgnUNtnatoK2Ha1td2jbm9qulraz
13bHtN03bT9K28dq+4/aob922KIdXmrHodpxv3b8o53stVOadibtPEY7x2kX0C4ztMtR7VpJuzpq
12jt+km7DdJuIdotT43qqtFMNTqr3VG7T9Pu6dqjkvaw1R4ntGc17blQe+aqcRc1DlXj/7TXUO0V
or0+a+/R2vuY9imnfRy1z1nty9p3nPaN1r7/tF8P7bdE+yVrf9X+w7V/mPb/pgN66QAfHZCrA1vq
QC8dmK8mHdRko5qU6qC2OshFB13WwQ108FIdfF5N66rpHDWNVdOPOqSfDvHTIZd0aFkdOlSHhujQ
PDVroWYeanZGzcuo+Sg136fm33SYpQ6L0GF/dPgkHb5Thz/SEUY6Yq2OKFILQ7XwVIsctayklmPU
cqdalujI2jpyhI5cqyNzdBTpKCsdFamjHunohjp6mo4+rKO/6xgzHROiY56rVV+1clWrE2pdXq1H
qPU+tS5Sm05qs0xtEtXmnY7tomPddWyCjn2n43rquPU67qqOb6HjfXR8hk6opBPsdcIJnVhFJ87S
iRd0UlOd5KOTMnRyZZ08Rydf0Cn1dcp0nZKqttXU1kZtd6ltidr1VDs3tTut9uXVfqLaR6j9f+ow
WR32q8M7nWqqU/fo1J86bbxOO66OtdVxuTqm6fSKOn22Tr+oMwx1xkKdcU1nttGZLjrzjDpVUKdp
6rRNnfJ0Vm2d5aizInTWN509WmcH6uxbOqeZzlmic7J0bmOd66pzb+i89jpvrs47qvNF59vq/ESd
/02dLdR5tzrf1wWNdMFMXZCoC4rVpam6OKjLYXV5oQuNdaGfLszWRdV00SRdFKWLvuviEbp4ty7+
qEvMdMk6XZKtro3U1UVdM9Wtkro5qluCur1XdyN191L3S+r+Q5d20KWzdWm8Li3WZZ10mbcuO6nL
Puvy3rp8tS7PU48m6uGsHmnqWUs9LdVzg3reUa+m6rVYvY6q11/1Nlfvleqdot6/dcUgXbFEVxzR
Fe91ZV9duVRXXlafhuozWX32qs8r9e2jvoHq+1RX9dRVQbrqpa5uravn6Oqzuqayrpmpa2J0zR9d
a6lr/XRtjq6rqevsdd1GXZeq677r+n66fpGuP6MbRDcM1A1euuGCbqygGyfoxkjd+FH9TNVvm/pd
002im8bppr266b36d1D/5ep/Qf1/aICRBizRgCQNeKeBHTXQVQMvaRBp0BQNOqlBP3TzIN0crJtL
dYuJbtmpWz5p8BgNTtDgTxrSW0OCNaRUtw7RrQG6tURD+2iot4Ze1G3VdNtU3bZbtxXq9ra6fYVu
z9AdDXWHh+64oDur6M7pujNVdxnoLnfddUt399DdO3R3ke5pp3vW657HGjZIwwI17LXuNdW9frr3
toYbavhyDT+h4d9132Ddt133PdT9PXR/iO6/rxGtNcJLI27rgW56IEgPvNHIURqZqJE/9KCpHtyn
B39q1GSNOqSHQA/Z6qEDeuidRg/Q6GCNzteYRhqzQGOy9HAtPbxEDxdobEuNXaqxNzWuq8Zt1bjv
emSyHknX+PYav0zjszShgyZs0oRPenSoHo3WRNJEG02M1MRfemysHtukx7L1eHU97qjHD+jxH3rC
Wk+E6olCPdlZT67Rk4/0VE89FaSn3mqSpSYFadIdPd1ZT6/R0080uZ0mr9bkAj1TX89M0zNH9Mwf
TemjKd6ackVTG2mqo6am6FkDPTtVzx7Rc+X03BQ9d1rP19bzi/V8vqYZa9oKTcvSC630wkq98FjT
O2q6n6Y/1Yy2muGqGRf1Yj29aKMXQ/VikV4y0ktL9dINzeygmYs185xerqGX5+rlTL3SXK+s0CtF
mjVIs9ZrVp5md9TstZr9XK921asBerVYc9ppjqvmZOi1OnrNRq/t1Gulen2gXl+v15/pjSF6I1Bv
FGpuT80N1txPmmetecf0Zl296a03L+ut2nrLTW/laX4PzV+r+c/1tone9tPbd/VOe72zSu+c14Ky
WmChBeFa8Ezv9tW7O/Ruod5rp/dW6L07er+b3g/U+6/0gYU+OKIPPuvD/vp/tH0JnE3l+7j9us/z
HPuMLSKyZ9/3naRkTdlCGUwZDF26cXHUKeSkk266cenGLaOGBiNDFJVKJS1S2Sn7nl3+513Ouefe
uYN+n+9/mLkz592f99mf533Pnwvcf55173nUvecd954r7r093Hvnu/fuc++r7d433b1vg3vfLff+
bu79Qff+w+4DrdwHAu4DB90H67gPznQf3OM+1Nx9yO8+dNF9uJ/78CfuI7ncRx5yH3nf/Vdu91/D
3H+lu/8m999Puf9Oc/99yX20s/vo2+6ju93HKriPpbiPbXMfL+o+PsZ9fIf7RFn3iWfcJ75wn7zP
fVJ1nzzsPtXJfSrNfbqY+/Qg9+kV7jOK+8xo95kf3GcruM9Od5/d4z5XzX3O4z73rft8Jff5J9zn
F7jP73dfqOe+MN594Sv3xYrui0+5L37ovviv+5/e7n9WuC/ld18a7L60wX25rPvyYPflpe7L/7qv
9HZfWem+ctV9tZf76jL31WPua3Xd115wX9vuvq64r/d2X1/ivn7VfaOd+8ZC941/3Te7um++5b55
1v1vd/e/K9y3yH3rGfetHyFXE8g1HXL9ALnrAHv3yWnI0xryLII8VyFvB8g7D/IehnwtIN9zkC8T
8v0L+XtCfj/kPw0FHoYCr0OBPeCqDS4VXH9CwSbALOfT4H4U3PPBfQCgJYAOcA6wJaAf8BRQfSAv
0NeglAVlICghUC5Aoe5Q6C0odAUKD4LC70Phq1CkNxRZBUWLQ9EJUPRXKNYKii2FYmeheHsovgxK
FIASSVBiHSSUhoSJkLAZEgtD4nBIzIKSeaDkg1DyLSh5Dkp1gFKLoXReKP0IlA5C6StQpi+UWQtl
S0LZSVB2L9zTGe6ZB/fsh3LtoNwSKF8AyveF8mvh3gS490m4Nx0q5IUKg6FCACrshYo1oKIPKn4F
91WC+2bCfd9CpVJQaQxU2gaVq0BlFSofgPs7wv3vw/1noEorqLIQqlyFqv2gagiq5YJq/aFaEKod
h+rNofpcqP4d1EiAGk9CjUyomRtqDoSaWVDLBbUeh1ofwQMueOApeGAL1K4AtWdA7UNQpw7U8UGd
vVC3JdQNQt1zUK831FsB9a5A/a5QfyHUPw8N6kCDFGiQCQ3d0PAhaLgEGt6ARm2h0Sxo9Cc0rg+N
50Djv6BJW2gShCa3oGkHaDobmh6BZi2g2QJodgiat4Lmr0PzX6FFeWiRDC02QItL0LIptJwBLX+F
VmWg1Xho9QO0ToDWQ6H1GmijQJtR0OYLaFsR2s6AtoehXQ1oNwHa7YD21aD9y9D+Z+hQFzpo0OE7
6FgSOo6Ajp9Ax5PQqSp0Gg2dMqHTRejcCToHoPPv0OVe6PIMdNkIXYtB1yTougEeTIQHx8GDK+HB
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
cUNpWUZpOUBpqSstFyktM5SWJ5WW15VWDZVWQ5RWK5VW+5XWoLRurrQerLR+Xmn9htJ6m9L6qNL6
itKmiNKmh9JmqNLmbaXNNqXNDaXtPUrbAUpbXWm7XWm7X2mXS2lXV2k3Smn3udLuktK+mtK+odJ+
nNJ+itJ+vtL+HaX9SqX9r0qHPEqHKkqHXkqHSUqHN5QOW5UOx5UOt5SO9ygdH1U6DlY6zlI6rlA6
7lA6XlE6VVA6tVY6jVA6TVU6LVY6bVM6XVE6V1M691E6P690flvp/K7S+XOl8+9Kl3JKl35KlyeV
LiOVLh6ly2qlq1vpWmt2IfNfICMhRQ+7tOQEVTdchWYbWQlePeDyJ7KfhWb7MxJ8qqarmlf3Gz7z
W9cMPaD5VL9L8yYYqlqAd6Gpmma2N//WDJ+qa5pZTdN1w/yvqaph6Kqf/W12pLMxzAZmdc0wW7GW
OqvJ/tZVXsswu9L472ZT87lZ7jK74pXNh2JarAfW3pyUznrWWLlP8+uiCzYwmwVvZn76XbxTs21A
rLDQ7GAm60RL1fkQZs8hNmE2P7PAfJhqzy0khw2kJfjESGI4XqzrbAoa70MXD3iRXzYw52RW8Os+
9sBvsK55O/anEUzQArp4bq7V/CWUkSCgwn+yCZnf/Ke1bM2cMV+ZGhktwABtz8jLf4bYbFxie2RB
iqoFdTU9sgVGwKfyQs0X0j1sGDaWX9Ojqpgr8HoNtmPmOAHNqhDkHeten2Gv2Rfg26GFzGI9I8ET
9Ho5sEQ7rz+oR1aRIh97vYGA7mXD6qKVFlTNjTT3yHzitybiM/vxshZmba/ojI0Vman5R8Dn1QI+
gQXmV1igShqHrOqRAI787dyIULoAEgeU9S/yi/xi8wsnmHjiSvXyD/Nvs6FVz+7A/rKKosBpbyyb
vWoRnnNvzVWaMDQrqBLXfGqArd4ftrHfpAvVK7A8RWcgCUscNQE4PGjD1RzDZ0LKnkCyLnBF9aYF
LIJgLQI6x5hUE3hpfr5yWWCiBdsesXPsgR60/7R6ZDuuB32cnn3R/Zq1PXoGm4usbyRzHEwz7IUk
+zhqmZ2Ih7xZINsmGDZMra9AZIrpVrsQYxl6qjmkyhiPZlgFYZNcVE4yGVqKCSpDgisCFRMiyXqa
c+ax0AukiJ0zlxnmbTgRRrVhPEtnADA4FsRA38e4jOGzacnPa/udENP8SXq6RQlJvFa6luSVC/SZ
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
AAcAbO0FVAAAAA==
"""


if __name__ == "__main__":
    sys.exit(main())
