#!/usr/bin/env python
"""
oc_monitor.py - ocmux 모니터 (Python stdlib only, Windows 네이티브 콘솔 대응)

모드:
  status   : 인스턴스 1개 - 세션 트리 / busy·idle·retry / 담당 agent / 모델 / 토큰 / 비용 / 실시간 이벤트
  overview : ocmux 레지스트리의 모든 인스턴스 - 인스턴스별 요약 + 진행 중 작업 + 통합 이벤트
  logs     : opencode 로그 tail (파일 지정 / 실행 시각 이후 생성 파일 / 전체)
  usage    : 실시간 토큰 사용량 차트
  rpg      : TOKEN QUEST 토큰펫 (다마고치+RPG) - opencode 활동과 연동 / --all 이면 모든 펫 목장
  compose  : 큰 메시지 입력창 (Ctrl+V 붙여넣기, Ctrl+S 로 opencode에 전송)

예:
  python oc_monitor.py status --url http://127.0.0.1:4096
  python oc_monitor.py status --name api-server          # 레지스트리 이름으로
  python oc_monitor.py overview
  python oc_monitor.py logs --since 1790000000 --tag api-server
  python oc_monitor.py logs --all
"""
import argparse
import base64
import collections
import glob
import hashlib
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import quote

# ---------------------------------------------------------------- console (공용 유틸은 ocmux_term.py)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ocmux_term import (  # noqa: E402
    RST, B, RED, GRN, BLU, MAG, CYN, HOME, CLR_EOL, CLR_EOS, HIDE, SHOW, PALETTE, P3, fix_color,
    rgb, bg, term_size, cw, vlen, clip, pad, read_keys_windows, poll_keys, RawInput,
    chip, keycap, module, segbar, spinner, seg_lines, seg_width, sect, navbar, title_end, cells, readouts,
    ENC, ICON, enc_dot, sysline, Canvas, canvas_from_lines, guide_draw, boot_draw,
)

# 팔레트 (네이비 = 구조, 라임 = 강조/켜짐, 그레이 = 글자, 흰색 = 경고)
LIME, LIME3 = rgb(P3["lime"]), rgb(P3["lime3"])
NV1, NV2, NV3, NV4 = rgb(P3["navy1"]), rgb(P3["navy2"]), rgb(P3["navy3"]), rgb(P3["navy4"])
G0, G1, G2, G, G4, WH, BLACK = (rgb(P3["gray0"]), rgb(P3["gray1"]), rgb(P3["gray2"]), rgb(P3["gray"]), rgb(P3["gray4"]),
                                rgb(P3["white"]), rgb(P3["black"]))


def fmt_tok(n):
    n = n or 0
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}k"
    return str(n)


def ago(ms):
    if not ms:
        return "-"
    s = max(0, time.time() - ms / 1000)
    if s < 60:
        return f"{int(s)}s"
    if s < 3600:
        return f"{int(s // 60)}m"
    if s < 86400:
        return f"{int(s // 3600)}h"
    return f"{int(s // 86400)}d"


def money(c):
    return f"${c:.3f}" if c else "-"


def short(sid):
    return sid[-6:] if sid else "------"


# ---------------------------------------------------------------- registry
def registry_path():
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "ocmux", "instances.json")


_REG_CACHE = {"data": None}


def load_registry():
    """instances.json 읽기. PowerShell 이 막 쓰는 중이라 비어 있거나 반쯤 쓰인 파일이면
    잠깐 기다렸다 다시 읽고, 그래도 안 되면 마지막으로 읽은 목록을 돌려준다 (인스턴스가 깜빡 사라지지 않게)."""
    for i in range(4):
        try:
            with open(registry_path(), "r", encoding="utf-8-sig") as f:
                raw = f.read()
            if not raw.strip():
                raise ValueError("empty")
            data = json.loads(raw)
            data = data if isinstance(data, list) else [data]
            for r in data:
                if isinstance(r, dict) and r.get("color"):
                    r["color"] = fix_color(r["color"])
            _REG_CACHE["data"] = data
            return data
        except FileNotFoundError:
            if i >= 1:
                _REG_CACHE["data"] = []
                return []
        except (ValueError, OSError):
            pass
        time.sleep(0.05)
    return list(_REG_CACHE["data"] or [])


# ---------------------------------------------------------------- http
class Api:
    def __init__(self, url, user="opencode", password=None, directory=None):
        self.url = url.rstrip("/")
        self.dir = directory
        self.headers = {"Accept": "application/json"}
        if password:
            tok = base64.b64encode(f"{user}:{password}".encode()).decode()
            self.headers["Authorization"] = f"Basic {tok}"
        # 사내 프록시 환경변수가 localhost 요청을 가로채지 않도록
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _u(self, path):
        if self.dir:
            sep = "&" if "?" in path else "?"
            return f"{self.url}{path}{sep}directory={quote(self.dir)}"
        return self.url + path

    def get(self, path, timeout=5):
        req = urllib.request.Request(self._u(path), headers=self.headers)
        with self.opener.open(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def post(self, path, body, timeout=5):
        req = urllib.request.Request(self._u(path), data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers=dict(self.headers, **{"Content-Type": "application/json"}))
        with self.opener.open(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else None

    def stream(self, path):
        req = urllib.request.Request(self._u(path), headers=dict(self.headers, Accept="text/event-stream"))
        return self.opener.open(req, timeout=60 * 60 * 24)


# ---------------------------------------------------------------- 사용자 응답 대기 (허락/질문) 이벤트
# opencode 버전마다 이름이 조금씩 다르다: permission.updated(구) / permission.asked / permission.v2.asked,
# question.asked / question.v2.asked (question 도구: AI가 사용자에게 선택지를 물어봄)
WAIT_ASK_EVENTS = ("permission.updated", "permission.asked", "permission.v2.asked", "question.asked", "question.v2.asked")
WAIT_DONE_EVENTS = ("permission.replied", "permission.v2.replied", "question.replied", "question.rejected",
                    "question.v2.replied", "question.v2.rejected")


def wait_info(typ, p):
    """허락/질문 요청 이벤트 → {id, sid, kind, label, since} (모양이 이상하면 None)"""
    if not isinstance(p, dict):
        return None
    wid = p.get("id") or p.get("requestID") or p.get("permissionID")
    sid = p.get("sessionID")
    if not wid:
        return None
    if typ.startswith("question"):
        qs = p.get("questions") or []
        q = qs[0] if qs and isinstance(qs[0], dict) else {}
        label = q.get("question") or q.get("header") or "AI가 질문을 했어요"
        kind = "ask"
    else:
        pats = p.get("patterns") or p.get("pattern") or []
        if isinstance(pats, str):
            pats = [pats]
        what = p.get("permission") or p.get("type") or "tool"
        label = p.get("title") or (what + (" " + " ".join(str(x) for x in pats) if pats else ""))
        kind = "perm"
    return dict(id=str(wid), sid=sid, kind=kind, label=" ".join(str(label).split())[:80], since=time.time())


class TokenDelta:
    """세션별 누적 토큰의 증가분 계산기.
    이 계산기가 생기기 전부터 있던 세션은 '처음 본 값'을 기준점으로 삼고(예전 세션을 다시 열어도
    과거 토큰이 한꺼번에 들어오지 않게), 그 뒤에 새로 만들어진 세션은 0부터 센다."""

    def __init__(self, start_ms=None):
        self.start_ms = start_ms or time.time() * 1000
        self.base = {}

    def update(self, inst):
        if not inst.ready:
            return 0, 0
        din = dout = 0
        for sid, (tin, tout, created) in inst.session_tokens().items():
            if not created:
                continue      # 생성 시각을 아직 모름(폴링 전) → 기준점도 아직 안 잡는다 (예전 세션 토큰 몰림 방지)
            prev = self.base.get(sid)
            if prev is None:
                prev = (0, 0) if created >= self.start_ms - 5000 else (tin, tout)
            din += max(0, tin - prev[0])
            dout += max(0, tout - prev[1])
            self.base[sid] = (tin, tout)
        return din, dout


# ---------------------------------------------------------------- instance
def calc_stats(msgs):
    st = dict(agent="-", model="-", tin=0, tout=0, reason=0, cache=0, cost=0.0)
    for m in msgs:
        info = m.get("info", m)
        agent = info.get("agent") or info.get("mode")
        if agent:
            st["agent"] = agent
        if info.get("role") == "assistant":
            t = info.get("tokens") or {}
            st["tin"] += t.get("input", 0) or 0
            st["tout"] += t.get("output", 0) or 0
            st["reason"] += t.get("reasoning", 0) or 0
            c = t.get("cache") or {}
            st["cache"] += (c.get("read", 0) or 0) + (c.get("write", 0) or 0)
            st["cost"] += info.get("cost", 0) or 0
            if info.get("modelID"):
                st["model"] = info["modelID"]
        elif info.get("role") == "user":
            mdl = info.get("model") or {}
            if mdl.get("modelID") and st["model"] == "-":
                st["model"] = mdl["modelID"]
    return st


class Instance:
    """opencode 서버 1개 = 폴링 스레드 + SSE 스레드"""

    def __init__(self, name, url, color=None, directory=None, password=None, interval=2.0,
                 max_sessions=15, event_sink=None, headless=False):
        self.name, self.url = name, url
        self.color = fix_color(color) or PALETTE[int(hashlib.md5(name.encode()).hexdigest(), 16) % len(PALETTE)]
        self.api = Api(url, os.environ.get("OPENCODE_SERVER_USERNAME", "opencode"), password, directory)
        self.interval, self.max_sessions = interval, max_sessions
        self.lock = threading.Lock()
        self.sessions, self.status, self.stats, self.stats_ver, self.running_tool = {}, {}, {}, {}, {}
        self.events = collections.deque(maxlen=200)
        self.event_sink = event_sink  # overview 통합 이벤트
        self.connected, self.sse_ok, self.version, self.err = False, False, "?", ""
        self.alive = True
        self.headless = headless
        self.ready = False  # 첫 폴링 완료 여부 (usage 기준점)
        self.listeners = []
        self.err_count = 0
        self.last_activity = 0
        self.todos = {}      # sid -> [{"content", "status"}]  (opencode todowrite 목록)
        self.waits = {}      # 요청 id -> {"sid", "kind": perm|ask, "label", "since"}  (사용자 응답 대기)
        self.created_ms = {}  # sid -> 세션 생성 시각 (토큰 증가분 기준점 판정용)
        self.offline_since = None
        self.rtt_ms = 0.0     # 서버 응답 시간 (지수 평균) — 숨기지 않는 엔지니어링
        self.ev_total = 0     # 받은 이벤트 수
        self.last_event_t = 0.0
        self.ch = channel_of(name)

    @property
    def tag(self):
        return f"{rgb(self.color)}{self.name}{RST}"

    def start(self):
        threading.Thread(target=self._poll, daemon=True).start()
        threading.Thread(target=self._sse, daemon=True).start()
        return self

    def event(self, color, text):
        ts = time.strftime("%H:%M:%S")
        with self.lock:
            self.events.append((ts, color, text))
            self.ev_total += 1
            self.last_event_t = time.time()
            if "ERROR" in text:
                self.err_count += 1
        if self.event_sink is not None:
            self.event_sink.append((ts, self, color, text))

    # --- polling
    def _poll(self):
        while self.alive:
            try:
                try:
                    self.version = self.api.get("/global/health", timeout=2).get("version", "?")
                except Exception:
                    pass
                t_req = time.time()
                sessions = self.api.get("/session")
                ms = (time.time() - t_req) * 1000
                self.rtt_ms = ms if not self.rtt_ms else self.rtt_ms * 0.7 + ms * 0.3
                try:
                    status = self.api.get("/session/status")  # 보통 non-idle 세션만 포함
                except urllib.error.HTTPError:
                    status = None
                sessions.sort(key=lambda s: s["time"]["updated"], reverse=True)
                sessions = sessions[: self.max_sessions]
                cur_status = status if status is not None else self.status
                for s in sessions:
                    sid, ver = s["id"], s["time"]["updated"]
                    if self.stats_ver.get(sid) != ver or cur_status.get(sid, {}).get("type") == "busy":
                        try:
                            st = calc_stats(self.api.get(f"/session/{sid}/message"))
                            with self.lock:
                                self.stats[sid], self.stats_ver[sid] = st, ver
                        except Exception:
                            pass
                with self.lock:
                    self.sessions = {s["id"]: s for s in sessions}
                    for s in sessions:
                        self.created_ms.setdefault(s["id"], (s.get("time") or {}).get("created") or 0)
                    if status is not None:
                        self.status = status
                        # idle 이 된 세션의 '응답 대기'는 정리 (이벤트를 놓쳤을 때 대비)
                        for wid, w in list(self.waits.items()):
                            if (status.get(w["sid"]) or {}).get("type") in (None, "idle") and time.time() - w["since"] > 5:
                                self.waits.pop(wid, None)
                    self.ready = True
                    if sessions:
                        self.last_activity = max(self.last_activity, sessions[0]["time"]["updated"])
                    if not self.connected:
                        self.connected = True
                        self.err = ""
                        was_off = True
                    else:
                        was_off = False
                    self.offline_since = None
                if was_off:
                    self.event(GRN, "online")
            except Exception as e:
                with self.lock:
                    was_on = self.connected
                    self.connected, self.err = False, f"{type(e).__name__}: {e}"
                    if self.offline_since is None:
                        self.offline_since = time.time()
                if was_on:
                    self.event(RED, "offline")
            time.sleep(self.interval)

    # --- SSE
    def _sse(self):
        while self.alive:
            try:
                resp = self.api.stream("/event")
                self.sse_ok = True
                data = []
                for raw in resp:
                    if not self.alive:
                        return
                    line = raw.decode("utf-8", "replace").rstrip("\r\n")
                    if line.startswith("data:"):
                        data.append(line[5:].lstrip())
                    elif line == "" and data:
                        try:
                            self._handle(json.loads("\n".join(data)))
                        except Exception:
                            pass
                        data = []
            except Exception:
                self.sse_ok = False
                time.sleep(3)

    def _handle(self, ev):
        typ, p = ev.get("type", ""), ev.get("properties", {}) or {}
        self.last_activity = time.time() * 1000
        for fn in self.listeners:  # 원본 이벤트 구독자 (토큰펫 등)
            try:
                fn(ev)
            except Exception:
                pass
        if typ == "session.status":
            sid, stt = p.get("sessionID"), p.get("status", {})
            with self.lock:
                self.status[sid] = stt
                if stt.get("type") == "idle":
                    for wid in [w for w, v in self.waits.items() if v["sid"] == sid]:
                        self.waits.pop(wid, None)
            t = stt.get("type")
            col = {"busy": LIME, "idle": G, "retry": WH}.get(t, G1)
            extra = f" ({stt.get('message', '')})" if t == "retry" else ""
            self.event(col, f"[{short(sid)}] status → {t}{extra}")
        elif typ == "session.idle":
            with self.lock:
                self.running_tool.pop(p.get("sessionID"), None)
        elif typ == "session.error":
            err = p.get("error") or {}
            msg = (err.get("data") or {}).get("message") or err.get("name") or "error"
            if err.get("name") == "MessageAbortedError":
                self.event(G1, f"[{short(p.get('sessionID'))}] ■ aborted")
            else:
                self.event(RED, f"[{short(p.get('sessionID'))}] ERROR {msg}")
        elif typ == "todo.updated":
            sid = p.get("sessionID")
            todos = [{"content": str(t.get("content", "")), "status": t.get("status", "pending")}
                     for t in (p.get("todos") or []) if isinstance(t, dict)]
            with self.lock:
                old = self.todos.get(sid) or []
                self.todos[sid] = todos
            done = sum(1 for t in todos if t["status"] == "completed")
            if todos and done != sum(1 for t in old if t["status"] == "completed") or (todos and not old):
                self.event(GRN, f"[{short(sid)}] ☑ todo {done}/{len(todos)}")
        elif typ in WAIT_ASK_EVENTS:
            w = wait_info(typ, p)
            if w:
                with self.lock:
                    self.waits[w["id"]] = w
                icon = "⚠ 허락 필요" if w["kind"] == "perm" else "? 질문"
                self.event(MAG, f"[{short(w['sid'])}] {icon}: {w['label']}")
        elif typ in WAIT_DONE_EVENTS:
            wid = p.get("permissionID") or p.get("requestID") or p.get("id")
            with self.lock:
                w = self.waits.pop(wid, None)
            if w:
                reply = p.get("response") or p.get("reply") or ("answered" if typ.startswith("question") else "")
                self.event(G1, f"[{short(w['sid'])}] ✓ {reply or 'done'}")
        elif typ == "session.compacted":
            self.event(CYN, f"[{short(p.get('sessionID'))}] ⇣ compacted (컨텍스트 압축)")
        elif typ == "session.deleted":
            sid = (p.get("info") or {}).get("id")
            with self.lock:
                for d in (self.sessions, self.stats, self.todos, self.status, self.running_tool):
                    d.pop(sid, None)
        elif typ == "message.updated":
            info = p.get("info", {})
            agent, sid = info.get("agent") or info.get("mode"), info.get("sessionID")
            if agent and sid:
                with self.lock:
                    st = self.stats.setdefault(sid, calc_stats([]))
                    changed = st["agent"] != agent
                    st["agent"] = agent
                if changed:
                    self.event(CYN, f"[{short(sid)}] agent = {agent}")
        elif typ == "message.part.updated":
            part = p.get("part", {})
            if part.get("type") != "tool":
                return
            sid, tool, s = part.get("sessionID"), part.get("tool"), part.get("state", {})
            status, title = s.get("status"), s.get("title") or ""
            if status == "running":
                with self.lock:
                    self.running_tool[sid] = f"{tool} {title}".strip()
                self.event(BLU, f"[{short(sid)}] ▶ {tool} {title}")
            elif status == "completed":
                with self.lock:
                    self.running_tool.pop(sid, None)
                t = s.get("time", {})
                self.event(G1, f"[{short(sid)}] ✓ {tool} {title} ({(t.get('end', 0) - t.get('start', 0)) / 1000:.1f}s)")
            elif status == "error":
                with self.lock:
                    self.running_tool.pop(sid, None)
                self.event(RED, f"[{short(sid)}] ✗ {tool}: {str(s.get('error', ''))[:120]}")
        elif typ == "session.created":
            info = p.get("info", {})
            kind = "subagent" if info.get("parentID") else "session"
            self.event(GRN, f"[{short(info.get('id'))}] new {kind}: {info.get('title', '')}")

    # --- aggregates
    def totals(self):
        with self.lock:
            tin = sum((st or {}).get("tin", 0) for st in self.stats.values())
            tout = sum((st or {}).get("tout", 0) + (st or {}).get("reason", 0) for st in self.stats.values())
        return tin, tout

    def session_tokens(self):
        """sid -> (in, out+reasoning, 생성 시각 ms)"""
        with self.lock:
            return {sid: ((st or {}).get("tin", 0), (st or {}).get("tout", 0) + (st or {}).get("reason", 0),
                          self.created_ms.get(sid, 0)) for sid, st in self.stats.items()}

    def todo_progress(self, sid):
        """(완료, 전체, 지금 하는 일) 또는 None"""
        todos = list(self.todos.get(sid) or [])
        if not todos:
            return None
        done = sum(1 for t in todos if t["status"] == "completed")
        live = [t for t in todos if t["status"] not in ("completed", "cancelled")]
        cur = next((t["content"] for t in todos if t["status"] == "in_progress"), None)
        total = len([t for t in todos if t["status"] != "cancelled"])
        return done, total, cur or (live[0]["content"] if live else "")

    def waits_for(self, sid):
        # 잠금 없이 불리기도 하므로(overview) 복사본으로 순회 (다른 스레드가 바꾸는 중일 수 있음)
        return [w for w in list(self.waits.values()) if w["sid"] == sid]

    def summary(self):
        with self.lock:
            tot = dict(tin=0, tout=0, cache=0, cost=0.0)
            busy = []
            for sid, s in self.sessions.items():
                st = self.stats.get(sid) or calc_stats([])
                for k in tot:
                    tot[k] += st[k]
                t = (self.status.get(sid) or {}).get("type", "idle")
                if t != "idle":
                    busy.append((s, st, t, self.running_tool.get(sid)))
            return dict(n=len(self.sessions), busy=busy, **tot)


# ---------------------------------------------------------------- pet 연동 (있으면)
_PET_CACHE = {}


def pet_info(scope, kind="badge"):
    """토큰펫 요약/배지를 2초 캐시로 읽는다. 펫 모듈이 없거나 펫이 없으면 None"""
    now = time.time()
    hit = _PET_CACHE.get((scope, kind))
    if hit and now - hit[0] < 2:
        return hit[1]
    val = None
    try:
        import ocmux_pet
        val = ocmux_pet.pet_badge(scope) if kind == "badge" else ocmux_pet.pet_summary(scope)
    except Exception:
        val = None
    _PET_CACHE[(scope, kind)] = (now, val)
    return val


# ---------------------------------------------------------------- render: status
def order_tree(sessions):
    children, roots = collections.defaultdict(list), []
    for s in sessions.values():
        pid = s.get("parentID")
        (children[pid] if pid in sessions else roots).append(s)
    def key(s):
        return s["time"]["updated"]
    out = []

    def walk(s, d):
        out.append((s, d))
        for c in sorted(children[s["id"]], key=key, reverse=True):
            walk(c, d + 1)

    for r in sorted(roots, key=key, reverse=True):
        walk(r, 0)
    return out


def conn_badge(inst):
    c = f"{LIME}●{RST} {G4}ONLINE{RST}" if inst.connected else f"{WH}{B}○ OFFLINE{RST}"
    e = f"{LIME}SSE{RST}" if inst.sse_ok else f"{G1}SSE{RST}"
    return f"{c} {e}"

def channel_of(name):
    """레지스트리의 채널 번호 (ocmux add 할 때 매겨짐). 없으면 등록 순서"""
    for i, r in enumerate(load_registry()):
        if r.get("name") == name:
            try:
                return int(r.get("ch") or i + 1)
            except (TypeError, ValueError):
                return i + 1
    return None

def ch_chip(inst):
    """채널 번호 칩 (인스턴스 색 바탕): 01"""
    n = getattr(inst, "ch", None)
    return f"{bg(inst.color)}{BLACK}{B}{n:02d}{RST}" if isinstance(n, int) else f"{bg(inst.color)}{BLACK}{B}--{RST}"

def st_chip(stt, waits=None):
    """세션 상태 칩: BUSY(라임) / RTRY(흰색) / PERM·ASK(깜빡) / idle(회색 글자). 폭 6 고정"""
    if waits and stt != "idle":
        tag = "PERM" if waits[0]["kind"] == "perm" else "ASK"
        return chip(f"{tag:<4}", "black", "lime") if int(time.time() * 2) % 2 else chip(f"{tag:<4}", "lime", "navy2")
    if stt == "busy":
        return chip("BUSY", "black", "lime")
    if stt == "retry":
        return chip("RTRY", "black", "white")
    return f"{G1} idle {RST}"

def recent(t, window=1.5):
    return bool(t) and time.time() - t < window


def split_tail(L, W, H, events_fmt, logf, n_ev=2, n_log=3, anchors=None, ev_t=0.0):
    """남은 영역을 EVENTS / LOGS 위아래 반반으로. 제목 옆 LED = 1.5초 안에 새 줄"""
    room = max(4, H - len(L))
    if logf is None:
        _anc(anchors, title_end(n_ev, "EVENTS", led=True), len(L), "events")
        L.append(sect(n_ev, "EVENTS", W, led=recent(ev_t)))
        L.extend(events_fmt[-(room - 1):])
        return L
    ev_n = max(1, (room - 2) // 2)
    lg_n = max(1, room - 2 - ev_n)
    _anc(anchors, title_end(n_ev, "EVENTS", led=True), len(L), "events")
    L.append(sect(n_ev, "EVENTS", W, led=recent(ev_t)))
    ev = events_fmt[-ev_n:]
    L.extend(ev + [""] * (ev_n - len(ev)))
    _anc(anchors, title_end(n_log, "LOGS", led=True), len(L), "logs")
    L.append(sect(n_log, "LOGS", W, f"{G1}{clip(logf.describe(), max(8, W - 22))}{RST}", led=recent(logf.last_new)))
    L.extend(logf.tail(lg_n))
    return L

def _anc(anchors, x, y, key):
    if anchors is not None and all(k != key for _, _, k in anchors):
        anchors.append((x, y, key))

def token_cells(tin, tout, cache, cost, W, H, big_rows=30):
    """핵심 값 4개 (색 = ①IN 파랑 ②OUT 초록 ③CACHE 흰색 ④COST 회색). 넉넉하면 세그먼트 숫자"""
    items = [("IN", fmt_tok(tin), 0), ("OUT", fmt_tok(tout), 1), ("CACHE", fmt_tok(cache), 2), ("COST", money(cost), 3)]
    if H >= big_rows:
        rows = readouts(items, W)
        if rows:
            return rows
    return [cells([(k, f"{G4}{B}{v}{RST}", e) for k, v, e in items], W)]

def top_bar(left, W, sys_parts=None, extra="", anchors=None):
    """모든 모니터 칸의 맨 윗줄: 왼쪽 이름 ··· 오른쪽 (시스템 상태) (LED) 시계 [?]"""
    tail = (extra + " " if extra else "") + f"{G}{time.strftime('%H:%M:%S')}{RST} {keycap('?')} "
    right = (sysline(sys_parts) + "  " + tail) if sys_parts else tail
    if vlen(left) + vlen(right) + 2 > W:
        right = tail
    elif sys_parts:
        _anc(anchors, W - vlen(right) - 1, 0, "sys")
    return navbar(left, right, W)

def render_status(inst, show_idle_sub, W, H, logf=None, anchors=None):
    L = []
    now = time.time()
    port = inst.url.rsplit(":", 1)[-1]
    left = f" {ch_chip(inst)} {G4}{B}{inst.name}{RST} {G1}:{port} v{inst.version}{RST}"
    sysp = [("rtt", f"{inst.rtt_ms:.0f}ms"), ("poll", f"{inst.interval:g}s"), ("ev", str(inst.ev_total))]
    _anc(anchors, min(W - 2, vlen(left) + 1), 0, "channel")
    L.append(top_bar(left, W, sysp, conn_badge(inst), anchors))
    if inst.err and not inst.connected:
        L.append(f"{chip('ERR', 'black', 'white')} {WH}{inst.err}{RST}")
    models = sorted({st["model"] for st in inst.stats.values() if st["model"] != "-"})
    if models:
        L.append(f"{G1}MODEL{RST} {G4}{', '.join(models)}{RST}   {G1}DIR{RST} {G}{inst.api.dir or '-'}{RST}")
    badge = pet_info(inst.name, "badge")
    if badge:
        _anc(anchors, W - 2, len(L), "pet")
        L.append(badge)
    summ = inst.summary()
    # 01 TOKENS: 핵심 값 4개 (색 = 인코더 색)
    _anc(anchors, title_end(1, "TOKENS"), len(L), "tokens")
    L.append(sect(1, "TOKENS", W, f"{G1}SESS{RST} {G4}{summ['n']}{RST}"))
    L.extend(token_cells(summ["tin"], summ["tout"], summ["cache"], summ["cost"], W, H))
    _anc(anchors, title_end(2, "SESSIONS", led=True), len(L), "sessions")
    L.append(sect(2, "SESSIONS", W, f"{G1}ACTIVE{RST} {LIME if summ['busy'] else G1}{B}{len(summ['busy'])}{RST}",
                  led=bool(summ["busy"])))
    wide = W >= 100
    cols = [("ST", 6), ("SESSION", 0), ("AGENT", 9)] + ([("MODEL", 14)] if wide else []) + \
           [("IN", 6), ("OUT", 6)] + ([("CACHE", 6)] if wide else []) + [("COST", 6), ("UPD", 4)]
    title_w = max(14, W - sum(w for _, w in cols) - len(cols))
    cols = [(n, w or title_w) for n, w in cols]
    dots = {"IN": enc_dot(0), "OUT": enc_dot(1), "CACHE": enc_dot(2), "COST": enc_dot(3)}
    L.append(" ".join(pad((dots[n] + G1 + n + RST) if n in dots else (G1 + n + RST), w) for n, w in cols))
    with inst.lock:
        rows = order_tree(inst.sessions)
        for s, depth in rows:
            sid = s["id"]
            stt = (inst.status.get(sid) or {}).get("type", "idle")
            if not show_idle_sub and stt == "idle" and depth > 0:
                continue
            st = inst.stats.get(sid) or calc_stats([])
            waits = inst.waits_for(sid)
            prefix = (f"{NV3}{'  ' * (depth - 1)}└{RST} ") if depth else ""
            tcol = G4 if stt != "idle" else G
            title = f"{prefix}{tcol}{s.get('title') or '(untitled)'}{RST} {G2}{short(sid)}{RST}"
            vals = [st_chip(stt, waits), title, f"{NV4 if not depth else G}{st['agent']}{RST}"] + \
                   ([f"{G}{st['model']}{RST}"] if wide else []) + \
                   [f"{G4}{fmt_tok(st['tin'])}{RST}", f"{G4}{fmt_tok(st['tout'])}{RST}"] + \
                   ([f"{G}{fmt_tok(st['cache'])}{RST}"] if wide else []) + \
                   [f"{G4}{money(st['cost'])}{RST}", f"{G1}{ago(s['time']['updated'])}{RST}"]
            L.append(" ".join(pad(v, w) for v, (_, w) in zip(vals, cols)))
            ind = f"{' ' * 7}{'  ' * depth}"
            for w in waits[:2]:
                what = "허락 대기" if w["kind"] == "perm" else "질문 대기"
                L.append(f"{ind}{WH}{B}{ICON['wait']} {what}{RST} {G4}{w['label']}{RST} {G1}{int(now - w['since'])}s · opencode 창에서 응답{RST}")
            prog = inst.todo_progress(sid)
            if prog and prog[1] and (stt != "idle" or prog[0] < prog[1]):
                done, total, cur = prog
                tail = (f" {G1}지금{RST} {G4}{cur}{RST}" if cur and done < total else f" {LIME}전부 완료{RST}" if done >= total else "")
                L.append(f"{ind}{G1}QUEST{RST} {LIME}{B}{done}/{total}{RST} {segbar(done, total, min(10, max(4, total)))}{tail}")
            tool = inst.running_tool.get(sid)
            if tool and stt == "busy":
                L.append(f"{ind}{LIME}{spinner(now)}{RST} {NV4}{tool}{RST}")
        if not rows:
            L.append(f"{G1}  — 세션 없음 —{RST}")
        events = list(inst.events)
    return split_tail(L, W, H, [f"{NV3}{ts}{RST} {col}{txt}{RST}" for ts, col, txt in events], logf, 3, 4,
                      anchors, inst.last_event_t)


# ---------------------------------------------------------------- render: overview
def render_overview(insts, sink, W, H, logf=None, anchors=None):
    L = []
    online = sum(1 for i in insts if i.connected)
    left = (f" {chip('OCMUX', 'black', 'lime')} {G4}{B}OVERVIEW{RST}  {G1}INST{RST} {G4}{len(insts)}{RST}  "
            f"{G1}ONLINE{RST} {LIME}{B}{online}{RST}")
    sse = sum(1 for i in insts if i.sse_ok)
    rtt = [i.rtt_ms for i in insts if i.connected and i.rtt_ms]
    sysp = [("sse", f"{sse}/{len(insts)}"), ("rtt", f"{(sum(rtt) / len(rtt)) if rtt else 0:.0f}ms"), ("reg", "instances.json")]
    _anc(anchors, min(W - 2, vlen(left) + 1), 0, "overview")
    L.append(top_bar(left, W, sysp, anchors=anchors))
    T = dict(n=0, busy=0, tin=0, tout=0, cache=0, cost=0.0)
    active = []
    rows = []
    cols = [("", 1), ("CH", 2), ("INSTANCE", 14), ("PORT", 5), ("MODE", 8), ("SESS", 4), ("BUSY", 4), ("ACTIVE AGENTS", 18),
            ("IN", 7), ("OUT", 6), ("COST", 6), ("LAST", 4), ("PET", 20), ("DIR", 0)]
    flex = max(12, W - sum(w for _, w in cols) - len(cols))
    cols = [(n, w or flex) for n, w in cols]
    for inst in insts:
        s = inst.summary()
        T["n"] += s["n"]
        T["busy"] += len(s["busy"])
        T["tin"] += s["tin"]
        T["tout"] += s["tout"]
        T["cache"] += s.get("cache", 0)
        T["cost"] += s["cost"]
        dot = f"{LIME}{ICON['online']}{RST}" if inst.connected else f"{WH}{ICON['offline']}{RST}"
        agents = sorted({st["agent"] for _, st, _, _ in s["busy"]})
        if not inst.connected:
            agents_txt = f"{WH}{B}OFFLINE{RST}"
        else:
            agents_txt = f"{NV4}{', '.join(agents)}{RST}" if agents else f"{G2}-{RST}"
        port = inst.url.rsplit(":", 1)[-1]
        busy_txt = f"{LIME}{B}{len(s['busy'])}{RST}" if s["busy"] else f"{G2}0{RST}"
        mode = f"{G1}headless{RST}" if inst.headless else f"{G4}tui{RST}"
        pet = pet_info(inst.name, "summary")
        if pet:
            pcol = rgb(pet.get("color") or P3["lime"])
            pet_txt = (f"{pcol}(알){RST} {G4}{pet['name']}{RST}" if pet.get("form") == "egg" else
                       f"{pcol}({pet['face']}){RST} {G4}{pet['name']}{RST} {G1}LV{RST}{LIME}{pet['lvl']}{RST}"
                       + (f" {LIME}{B}{ICON['call']}{RST}" if pet.get("call") else "")
                       + (f" {WH}{B}{ICON['wait']}{RST}" if pet.get("wait") and not pet.get("stale") else "")
                       + (f" {NV4}⚔{RST}" if pet.get("where") in ("exp", "raid") else ""))
        else:
            pet_txt = f"{G2}-{RST}"
        vals = [dot, ch_chip(inst), inst.tag, f"{G}{port}{RST}", mode, f"{G4}{s['n']}{RST}", busy_txt, agents_txt,
                f"{G4}{fmt_tok(s['tin'])}{RST}", f"{G4}{fmt_tok(s['tout'])}{RST}", f"{G4}{money(s['cost'])}{RST}",
                f"{G1}{ago(inst.last_activity)}{RST}", pet_txt, f"{G1}{inst.api.dir or ''}{RST}"]
        rows.append(" ".join(pad(v, w) for v, (_, w) in zip(vals, cols)))
        for b in s["busy"]:
            active.append((inst, *b))
    # 01 TOKENS: 전체 합계 4개 (색 = 인코더 색)
    _anc(anchors, title_end(1, "TOKENS"), len(L), "tokens")
    L.append(sect(1, "TOKENS", W, f"{G1}SESS{RST} {G4}{T['n']}{RST}  {G1}ACTIVE{RST} {LIME}{B}{T['busy']}{RST}"))
    L.extend(token_cells(T["tin"], T["tout"], T["cache"], T["cost"], W, H, big_rows=36))
    _anc(anchors, title_end(2, "INSTANCES", led=True), len(L), "instances")
    L.append(sect(2, "INSTANCES", W, led=any(i.connected for i in insts)))
    dots = {"IN": enc_dot(0), "OUT": enc_dot(1), "COST": enc_dot(3)}
    L.append(" ".join(pad((dots[n] + G1 + n + RST) if n in dots else (G1 + n + RST), w) for n, w in cols))
    L.extend(rows)
    if not insts:
        L.append(f"{G1}  — 등록된 인스턴스 없음 · ocmux add 로 추가 —{RST}")
    _anc(anchors, title_end(3, "ACTIVE WORK", led=True), len(L), "active")
    L.append(sect(3, "ACTIVE WORK", W, f"{LIME if active else G1}{B}{len(active)}{RST}", led=bool(active)))
    if not active:
        L.append(f"{G1}  모두 idle{RST}")
    now = time.time()
    for inst, s, st, t, tool in active:
        waits = inst.waits_for(s["id"])
        sub = f"{G1}sub{RST} " if s.get("parentID") else ""
        prog = inst.todo_progress(s["id"])
        todo = f" {LIME}[{prog[0]}/{prog[1]}]{RST}" if prog and prog[1] else ""
        line = (f"  {st_chip(t, waits)} {ch_chip(inst)} {pad(inst.tag, 14)} {sub}{G4}{s.get('title') or '(untitled)'}{RST}{todo} {G1}·{RST} "
                f"{G if s.get('parentID') else NV4}{st['agent']}{RST}")
        if waits:
            line += f" {WH}{B}{ICON['wait']}{RST} {G4}{waits[0]['label']}{RST}"
        elif tool:
            line += f" {LIME}{spinner(now)}{RST} {NV4}{tool}{RST}"
        L.append(line)
    last_ev = max((i.last_event_t for i in insts), default=0.0)
    return split_tail(L, W, H, [f"{NV3}{ts}{RST} {ch_chip(inst)} {pad(inst.tag, 12)} {col}{txt}{RST}" for ts, inst, col, txt in list(sink)],
                      logf, 4, 5, anchors, last_ev)


# ---------------------------------------------------------------- logs
LEVELS = ["DEBUG", "INFO", "WARN", "ERROR"]


def default_log_dirs():
    home = os.path.expanduser("~")
    c = [os.environ.get("OPENCODE_LOG_DIR", ""),
         os.path.join(os.environ["XDG_DATA_HOME"], "opencode", "log") if os.environ.get("XDG_DATA_HOME") else "",
         os.path.join(home, ".local", "share", "opencode", "log"),
         os.path.join(os.environ["LOCALAPPDATA"], "opencode", "log") if os.environ.get("LOCALAPPDATA") else ""]
    return [x for x in c if x]


def log_files(dirs):
    out = []
    for d in dirs:
        out += glob.glob(os.path.join(d, "*.log"))
    return out


_LOG_RE = re.compile(r"^(DEBUG|INFO|WARN|ERROR)\s+(?:\d{4}-\d\d-\d\dT)?(\d\d:\d\d:\d\d)\S*\s*(\+\S+)?\s*(.*)$")
_KV_RE = re.compile(r"([A-Za-z_][\w.]*)=(\S+)")


def colorize(line):
    """opencode 로그 한 줄 → 레벨 칩(5칸) + 시각 + key=value (키는 흐리게, 값은 밝게)"""
    m = _LOG_RE.match(line)
    if not m:
        return f"{G}{line}{RST}"
    lvl, hms, dur, rest = m.groups()
    tag = {"ERROR": chip("ERR", "black", "white"), "WARN": f" {LIME3}{B}WRN{RST} ", "INFO": f" {G1}INF{RST} ",
           "DEBUG": f" {G0}DBG{RST} "}[lvl]
    body = WH if lvl == "ERROR" else G4 if lvl == "WARN" else G
    rest = _KV_RE.sub(lambda k: f"{G1}{k.group(1)}={RST}{body}{k.group(2)}{RST}{body}", rest)
    return f"{tag} {NV3}{hms}{RST} " + (f"{G1}{dur}{RST} " if dur else "") + f"{body}{rest}{RST}"


class Tail:
    """파일을 계속 열어두지 않는 tail. (Windows 에선 열린 파일을 opencode 가 지우지 못하므로
    읽을 때만 열고 바로 닫는다. 위치는 바이트 오프셋으로 기억)"""

    def __init__(self, path, from_end=True):
        self.path = path
        self.pos = 0
        self.partial = b""
        self.ident = self._ident()
        if from_end:
            size = os.path.getsize(path)
            self.pos = max(0, size - 6000)
            self.skip_first = size > 6000
        else:
            self.skip_first = False
        self.last_mtime = time.time()

    def _ident(self):
        try:
            st = os.stat(self.path)
            return (st.st_ino, st.st_dev)
        except OSError:
            return None

    def lines(self):
        try:
            size = os.path.getsize(self.path)
        except OSError:
            return []
        ident = self._ident()
        if size < self.pos or (ident and self.ident and ident != self.ident):   # 잘리거나 다른 파일로 바뀜
            self.pos, self.partial, self.skip_first = 0, b"", False
            self.ident = ident
        if size == self.pos:
            return []
        try:
            with open(self.path, "rb") as f:
                f.seek(self.pos)
                data = f.read(size - self.pos)
        except OSError:
            return []
        self.pos += len(data)
        self.last_mtime = time.time()
        data = self.partial + data
        parts = data.split(b"\n")
        self.partial = parts.pop()   # 아직 줄바꿈이 안 온 마지막 조각
        if self.skip_first and parts:
            parts = parts[1:]
            self.skip_first = False
        return [p.decode("utf-8", "replace").rstrip("\r") for p in parts]


class LogFollower:
    """로그 추적기. mode: file(지정 파일) / since(실행 이후 첫 파일) / all(최근 전체) / newest"""

    def __init__(self, dirs=None, file=None, since=None, all_=False, level="DEBUG", grep=None, keep=400):
        self.dirs = dirs or default_log_dirs()
        self.file, self.since, self.all, self.grep = file, since, all_, grep
        self.min_idx = LEVELS.index(level) if level in LEVELS else 0
        self.tails = {}
        self.buf = collections.deque(maxlen=keep)
        self.last_scan = 0
        self.last_new = 0.0   # 마지막으로 새 줄이 들어온 시각 (LOGS LED)

    def describe(self):
        if self.file:
            return os.path.basename(self.file)
        cur = next(iter(self.tails), None)
        if self.all:
            return f"all · {LEVELS[self.min_idx]}+"
        return os.path.basename(cur) if cur else "waiting for log file…"

    def _keep(self, line):
        lvl = line.split(" ", 1)[0].upper()
        if lvl in LEVELS and LEVELS.index(lvl) < self.min_idx:
            return False
        return not self.grep or self.grep.lower() in line.lower()

    def _scan(self):
        now = time.time()
        if now - self.last_scan < 2:
            return []
        self.last_scan = now
        notes = []
        try:
            if self.file:
                if self.file not in self.tails and os.path.exists(self.file):
                    self.tails[self.file] = Tail(self.file)
                return notes
            files = log_files(self.dirs)
            if self.all:
                for f in files:
                    if f not in self.tails and now - os.path.getmtime(f) < 3600:
                        self.tails[f] = Tail(f)
                for f in list(self.tails):   # 두 시간 넘게 조용한 파일은 추적 중단
                    if now - self.tails[f].last_mtime > 7200:
                        del self.tails[f]
            elif self.since:
                if not self.tails:
                    cands = [f for f in files if os.path.getctime(f) >= self.since - 2]
                    if cands:
                        f = min(cands, key=os.path.getctime)
                        self.tails[f] = Tail(f, from_end=False)
            elif files:
                f = max(files, key=os.path.getmtime)
                if f not in self.tails:
                    self.tails.clear()
                    self.tails[f] = Tail(f)
                    notes.append(f"{CYN}==> {f}{RST}")
        except OSError:
            pass
        return notes

    def poll(self):
        """새 줄을 buf에 쌓고, 이번에 새로 들어온 줄 리스트 반환"""
        new = self._scan()
        for path, t in list(self.tails.items()):
            for ln in t.lines():
                if self._keep(ln):
                    prefix = f"{NV3}{os.path.splitext(os.path.basename(path))[0][-17:]}{RST} " if self.all else ""
                    new.append(prefix + colorize(ln))
        self.buf.extend(new)
        if new:
            self.last_new = time.time()
        return new

    def tail(self, n):
        self.poll()
        out = list(self.buf)[-n:]
        if not out:
            out = [f"{G1}(no log lines yet){RST}"]
        return out + [""] * (n - len(out))


def make_follower(a, level=None):
    if a.no_logs:
        return None
    return LogFollower(a.log_dir, a.file, a.since, a.all, (level or a.level), a.grep)


def run_logs(a):
    lf = make_follower(a) or LogFollower(a.log_dir, a.file, a.since, a.all, a.level, a.grep)
    tag = rgb(a.color) + (a.tag or "logs") + RST
    print(f"{chip('LOGS', 'black', 'lime')} {tag}  {G1}{lf.describe()}  ({' | '.join(lf.dirs)}){RST}")
    while True:
        new = lf.poll()
        for ln in new:
            print(ln)
        if not new:
            time.sleep(0.2)


# ---------------------------------------------------------------- usage chart
EIGHTHS = " ▁▂▃▄▅▆▇█"


def nice_ceil(v):
    if v <= 0:
        return 10
    import math
    e = 10 ** int(math.floor(math.log10(v)))
    for m in (1, 2, 2.5, 5, 10):
        if v <= m * e:
            return int(m * e)
    return int(10 * e)


class UsageTracker:
    """인스턴스별 누적 토큰의 증가분을 bucket(초) 단위로 적재"""

    def __init__(self, bucket=10, keep=720):
        self.bucket = bucket
        self.hist = collections.deque(maxlen=keep)       # [(in, out)] 완료된 bucket
        self.per = collections.defaultdict(lambda: collections.deque(maxlen=keep))  # name -> [tokens]
        self.cur = [0, 0]
        self.cur_per = collections.defaultdict(int)
        self.deltas = {}          # name -> TokenDelta (세션별 기준점)
        self.idx = int(time.time() // bucket)
        self.total = [0, 0]

    def update(self, insts):
        now_idx = int(time.time() // self.bucket)
        while self.idx < now_idx:  # bucket 경계 넘어가면 확정
            self.hist.append(tuple(self.cur))
            names = set(self.per) | set(self.cur_per)
            for n in names:
                self.per[n].append(self.cur_per.get(n, 0))
            self.cur, self.cur_per = [0, 0], collections.defaultdict(int)
            self.idx += 1
        for inst in insts:
            if not inst.ready:
                continue
            td = self.deltas.get(inst.name)
            if td is None:
                td = self.deltas[inst.name] = TokenDelta()
            din, dout = td.update(inst)
            self.cur[0] += din
            self.cur[1] += dout
            self.cur_per[inst.name] += din + dout
            self.total[0] += din
            self.total[1] += dout

    def series(self, n):
        s = list(self.hist)[-(n - 1):] + [tuple(self.cur)]
        return [(0, 0)] * (n - len(s)) + s

    def rate_per_min(self, name=None):
        k = max(1, int(60 // self.bucket))
        if name is None:
            vals = [a + b for a, b in list(self.hist)[-(k - 1):]] + [sum(self.cur)]
        else:
            vals = list(self.per.get(name, []))[-(k - 1):] + [self.cur_per.get(name, 0)]
        return sum(vals)


def render_usage(tr, insts, scope, W, H, anchors=None):
    L = []
    IN_C, OUT_C = rgb(ENC[0]), rgb(ENC[1])
    flowing = sum(tr.cur) > 0
    now = time.time()
    reels = (f"{LIME}({spinner(now, 6)}){NV3}━━{RST}{LIME}({spinner(now + 0.2, 6)}){RST}" if flowing
             else f"{G0}(○)━━(○){RST}")
    left = f" {chip('USAGE', 'black', 'lime')} {G4}{B}{scope}{RST} {G1}tokens/{tr.bucket}s{RST}"
    legend = f"{enc_dot(0)} {G1}IN{RST} {enc_dot(1)} {G1}OUT{RST}"
    L.append(navbar(left, f"{reels} {legend} {keycap('?')} ", W))
    _anc(anchors, min(W - 2, vlen(left) + 1), 0, "usage")
    rate = tr.rate_per_min()
    info = [f"{G1}TOTAL{RST} {IN_C}{fmt_tok(tr.total[0])}{RST}{G1}/{RST}{OUT_C}{fmt_tok(tr.total[1])}{RST}"]
    if len(insts) == 1:
        pet = pet_info(insts[0].name, "summary")
        if pet and pet.get("form") != "egg" and not pet.get("stale"):
            info.append(f"{rgb(pet.get('color') or P3['lime'])}{pet['name']}{RST} " + (
                f"{LIME3}냠냠{RST} {G1}포만{RST} {G4}{pet['full']}{RST}" if flowing else f"{G1}포만{RST} {G4}{pet['full']}{RST}"))
    multi = len(insts) > 1
    # 큰 세그먼트 숫자: 분당 토큰
    num = fmt_tok(rate)
    sw = seg_width(num)
    _anc(anchors, W - 2, len(L), "rate")
    if H >= 14 and sw + 2 <= W:
        seg = seg_lines(num, P3["lime"] if rate else P3["gray1"], ghost=P3["navy1"])
        tail = [f"{G1}TOKENS / MIN{RST}", info[0], info[1] if len(info) > 1 else ""]
        side = W - sw - 3
        if side >= 16:
            for i in range(3):
                L.append(f" {seg[i]}" + " " * 2 + clip(tail[i], side, False))
        else:
            for i in range(3):
                L.append(f" {seg[i]}" + (f" {G1}/min{RST}" if i == 2 else ""))
            L.append("  ".join(info))
    else:
        L.append(f"{G1}NOW{RST} {LIME}{B}{num}{RST}{G1}/min{RST}  " + "  ".join(info))
    # 02 MIXER: 인스턴스마다 채널 막대 (여러 인스턴스일 때, 오른쪽)
    mix = []
    if multi:
        chans = [i for i in insts][:8]
        mix_w = 5 * len(chans) + 1
        if W - mix_w >= 40:
            mix = chans
    rows = max(3, H - len(L) - 3 - (1 if multi else 0))
    yw = 6
    pw = max(8, W - yw - 1 - (5 * len(mix) + 2 if mix else 0))
    data = tr.series(pw)
    peak = max((a + b for a, b in data), default=0)
    scale = nice_ceil(peak)
    units = rows * 8
    _anc(anchors, title_end(1, "TOKENS"), len(L), "chart")
    head = sect(1, "TOKENS", yw + 1 + pw, f"{G1}PEAK{RST} {G4}{fmt_tok(peak)}{RST}{G1}/{tr.bucket}s{RST}")
    if mix:
        _anc(anchors, W - 5 * len(mix) - 1 + title_end(2, "MIX") - 3, len(L), "mixer")
        head += " " + clip(sect(2, "MIX", W - vlen(head) - 1), W - vlen(head) - 1, False)
    L.append(head)
    levels, busy_f = [], []
    if mix:
        mx = max([tr.rate_per_min(i.name) for i in mix] + [1])
        levels = [tr.rate_per_min(i.name) / mx for i in mix]
        busy_f = [bool(i.summary()["busy"]) for i in mix]
    for r in range(rows - 1, -1, -1):  # 위에서 아래로
        lbl = fmt_tok(scale) if r == rows - 1 else (fmt_tok(scale // 2) if r == rows // 2 else ("0" if r == 0 else ""))
        line = [f"{G1}{lbl:>{yw - 1}}{RST}{NV2}┤{RST}" if lbl else f"{'':>{yw - 1}}{NV2}│{RST}"]
        for a, b in data:
            tot_u = round((a + b) / scale * units) if scale else 0
            in_u = round(a / scale * units) if scale else 0
            if (a + b) > 0 and tot_u == 0:
                tot_u = 1
            lo = r * 8
            fill = max(0, min(8, tot_u - lo))
            if fill == 0:
                line.append(f"{NV1}·{RST}" if r == rows // 2 else " ")
                continue
            top = lo + fill
            in_part = max(0, min(top, in_u) - lo)
            color = IN_C if in_part * 2 >= fill else OUT_C
            line.append(color + EIGHTHS[fill] + RST)
        if mix:
            line.append("  ")
            for k, inst in enumerate(mix):
                u = levels[k] * rows * 8
                f = max(0, min(8, int(round(u - r * 8))))
                busy = busy_f[k]
                col = rgb(inst.color)
                cell = (col + EIGHTHS[f] * 2 + RST) if f else (f"{NV1}··{RST}" if r == 0 else "  ")
                if r == rows - 1:     # 맨 위 줄: 바쁘면 LED
                    cell = f"{LIME if busy else G0}●{RST} " if not f else cell
                line.append(cell + "   ")
        L.append("".join(line))
    axis_line = f"{'':>{yw - 1}}{NV2}└{'─' * pw}{RST}"
    if mix:
        axis_line += "  " + "".join(f"{ch_chip(i)}   " for i in mix)
    L.append(axis_line)
    span = pw * tr.bucket
    left_t = f"-{span // 60}m" if span >= 60 else f"-{span}s"
    mid = f"-{span // 120}m" if span >= 120 else ""
    axis = [" "] * pw
    for pos, txt in ((0, left_t), (pw // 2 - len(mid) // 2, mid), (pw - 3, "now")):
        for i, ch in enumerate(txt):
            if 0 <= pos + i < pw:
                axis[pos + i] = ch
    L.append(f"{G1}{'':>{yw}}{''.join(axis)}{RST}")
    if multi:
        parts = [f"{ch_chip(i)} {i.tag} {G4}{fmt_tok(tr.rate_per_min(i.name))}{RST}" for i in insts if i.connected]
        L.append(f"{G1}/min{RST} " + "  ".join(parts))
    return L

def compose_keys(on=None):
    """색 = 조작: ①파랑 ^P 넣기 · ②초록 ^S 전송 · ③흰색 ^R 복구 · ④회색 ^L 지우기 · ^V 붙여넣기 · F1 가이드"""
    pairs = [("^P", "넣기만", ENC[0]), ("^S", "전송", ENC[1]), ("^R", "복구", ENC[2]), ("^L", "지우기", ENC[3]),
             ("^V", "붙여넣기", None), ("F1", "가이드", None)]
    return "  ".join(keycap(k, v, on=(on == k), color=c) for k, v, c in pairs)

def ghost_num(n, width):
    """테이프 카운터: 0145 — 앞자리 0 은 꺼진 LCD 처럼 흐리게"""
    s = f"{n:0{width}d}"
    k = len(s) - len(str(n))
    return f"{NV2}{s[:k]}{RST}{G4}{B}{s[k:]}{RST}"


# ---------------------------------------------------------------- main loops
def paint(lines, W, H, once):
    if once:
        sys.stdout.write("\n".join(clip(ln, W) for ln in lines[:H]) + "\n")
        sys.stdout.flush()
        return
    rows = lines[:H]
    out = []
    for i, ln in enumerate(rows):
        # 마지막 줄은 W-1 칸까지만: 오른쪽 끝 칸에 쓰면 일부 터미널이 스크롤/줄바꿈 대기 상태가 된다
        s = clip(ln, W - 1 if i == H - 1 else W)
        # 꽉 찬 줄 뒤의 ESC[K 는 '줄바꿈 대기' 상태에서 마지막 글자를 지울 수 있어서 생략
        out.append(s if vlen(s) >= W else s + CLR_EOL)
    # \r\n: POSIX raw 모드(OPOST 꺼짐)에서도 줄 맨 앞으로 돌아가도록
    if not out:
        sys.stdout.write(HOME + CLR_EOS)
    else:
        sys.stdout.write(HOME + "\r\n".join(out) + (("\r\n" + CLR_EOS) if len(rows) < H else ""))
    sys.stdout.flush()


def size(a):
    W, H = term_size()
    return (a.cols or W), (a.rows or H)


BOOT_T = 0.8


def loop(a, frame, tick=0.5, word="OCMUX", on_key=None, table=None):
    """모니터 칸 공통 루프: 짧은 부팅 연출 → frame(W, H, anchors) 를 주기적으로 그림.
    키: ? / F1 = 가이드 (번호표 + 범례), 그 밖의 키는 on_key 로"""
    if a.once:
        time.sleep(a.once)
        W, H = size(a)
        anchors = []
        lines = frame(W, H, anchors)
        if getattr(a, "guide", False):
            MON["guide"] = True
            lines = guide_overlay(lines, W, H, anchors, table)
        paint(lines, W, H, True)
        return
    sys.stdout.write(HIDE + "\x1b[2J")
    t0 = time.time()
    with RawInput() as fd:
        while True:
            W, H = size(a)
            el = time.time() - t0
            if el < BOOT_T:
                cv = Canvas(W, H)
                boot_draw(cv, W, H, el, word, "OCMUX · opencode monitor", BOOT_T)
                lines, wait = cv.lines(), 0.05
            else:
                anchors = []
                lines = frame(W, H, anchors)
                if MON["guide"]:
                    lines = guide_overlay(lines, W, H, anchors, table)
                wait = min(tick, 0.3) if MON["guide"] else tick
            paint(lines, W, H, False)
            for k in poll_keys(wait, fd):
                if el < BOOT_T:
                    t0 = time.time() - BOOT_T          # 아무 키나 누르면 부팅 연출 건너뜀
                elif not guide_key(k) and on_key:
                    on_key(k)


def single_instance(a):
    name, url, color, directory, headless = a.name or "opencode", a.url, a.color, a.dir, False
    if a.name and not a.url:
        for r in load_registry():
            if r.get("name") == a.name:
                url, color, directory = r.get("url"), color or r.get("color"), directory or r.get("dir")
                headless = bool(r.get("headless"))
    url = url or "http://127.0.0.1:4096"
    return Instance(name, url, color, directory, a.password, a.interval, a.max_sessions, headless=headless).start()


class RegistryWatcher:
    """레지스트리의 인스턴스 목록을 3초마다 동기화"""

    def __init__(self, a, sink=None):
        self.a, self.sink, self.insts, self.last = a, sink, {}, 0

    def get(self):
        if time.time() - self.last > 3:
            self.last = time.time()
            seen = set()
            for idx, r in enumerate(load_registry()):
                key = r.get("name")
                if not key or not r.get("url"):
                    continue
                seen.add(key)
                if key not in self.insts:
                    self.insts[key] = Instance(key, r["url"], r.get("color"), r.get("dir"), self.a.password,
                                               self.a.interval, self.a.max_sessions, self.sink, bool(r.get("headless"))).start()
                try:
                    self.insts[key].ch = int(r.get("ch") or idx + 1)
                except (TypeError, ValueError):
                    self.insts[key].ch = idx + 1
            for key in list(self.insts):
                if key not in seen:
                    self.insts.pop(key).alive = False
        return list(self.insts.values())


def run_status(a):
    inst = single_instance(a)
    inst.event(G1, f"connecting {inst.url} ...")
    logf = make_follower(a)
    opt = {"idle": not a.hide_idle_sub}

    def on_key(k):
        if k == "i":                         # idle 서브에이전트 세션 보이기/숨기기
            opt["idle"] = not opt["idle"]

    loop(a, lambda W, H, anc=None: render_status(inst, opt["idle"], W, H, logf, anc), word="STATUS", on_key=on_key)


def run_overview(a):
    sink = collections.deque(maxlen=300)
    reg = RegistryWatcher(a, sink)
    a.all = a.all or not (a.file or a.since)
    logf = make_follower(a, level=a.level if a.level != "DEBUG" else "WARN")
    reg.get()
    loop(a, lambda W, H, anc=None: render_overview(reg.get(), sink, W, H, logf, anc), word="OVERVIEW")


def run_usage(a):
    tr = UsageTracker(a.bucket)
    if a.all or not (a.name or a.url):
        reg = RegistryWatcher(a)
        scope = "all instances"
        get = reg.get
    else:
        inst = single_instance(a)
        scope = inst.name
        def get():
            return [inst]

    def frame(W, H, anc=None):
        insts = get()
        tr.update(insts)
        return render_usage(tr, insts, scope, W, H, anc)

    loop(a, frame, tick=1.0, word="USAGE")


# ---------------------------------------------------------------- compose (큰 입력창)


def win_clipboard_text():
    """Windows 클립보드 텍스트 (ctypes, 추가 설치 불필요)"""
    import ctypes
    from ctypes import wintypes
    u, k = ctypes.windll.user32, ctypes.windll.kernel32
    u.GetClipboardData.restype = wintypes.HANDLE
    k.GlobalLock.restype = wintypes.LPVOID
    k.GlobalLock.argtypes = [wintypes.HGLOBAL]
    k.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    if not u.OpenClipboard(None):
        return ""
    try:
        h = u.GetClipboardData(13)  # CF_UNICODETEXT
        if not h:
            return ""
        p = k.GlobalLock(h)
        try:
            return ctypes.wstring_at(p) if p else ""
        finally:
            k.GlobalUnlock(h)
    finally:
        u.CloseClipboard()


def clipboard_text():
    try:
        if os.name == "nt":
            return win_clipboard_text()
        import subprocess
        for cmd in (["wl-paste", "-n"], ["xclip", "-o", "-selection", "clipboard"], ["pbpaste"]):
            try:
                return subprocess.run(cmd, capture_output=True, text=True, timeout=2).stdout
            except Exception:
                continue
    except Exception:
        pass
    return ""


class Editor:
    """여러 줄 텍스트 편집기 상태. 키는 토큰(str 1글자 = 입력, 'UP' 등 = 동작)"""

    def __init__(self):
        self.lines, self.r, self.c = [""], 0, 0
        self.last_sent = ""

    @property
    def text(self):
        return "\n".join(self.lines)

    def set_text(self, t):
        self.lines = t.split("\n") or [""]
        self.r = len(self.lines) - 1
        self.c = len(self.lines[-1])

    def insert(self, s):
        s = s.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
        s = "".join(ch for ch in s if ch == "\n" or ch >= " ")
        if not s:
            return
        cur = self.lines[self.r]
        before, after = cur[: self.c], cur[self.c:]
        parts = s.split("\n")
        if len(parts) == 1:
            self.lines[self.r] = before + s + after
            self.c += len(s)
        else:
            new = [before + parts[0]] + parts[1:-1] + [parts[-1] + after]
            self.lines[self.r: self.r + 1] = new
            self.r += len(parts) - 1
            self.c = len(parts[-1])

    def key(self, k):
        L = self.lines
        if k == "LEFT":
            if self.c > 0:
                self.c -= 1
            elif self.r > 0:
                self.r -= 1
                self.c = len(L[self.r])
        elif k == "RIGHT":
            if self.c < len(L[self.r]):
                self.c += 1
            elif self.r < len(L) - 1:
                self.r, self.c = self.r + 1, 0
        elif k == "UP":
            if self.r > 0:
                self.r -= 1
                self.c = min(self.c, len(L[self.r]))
        elif k == "DOWN":
            if self.r < len(L) - 1:
                self.r += 1
                self.c = min(self.c, len(L[self.r]))
        elif k == "HOME":
            self.c = 0
        elif k == "END":
            self.c = len(L[self.r])
        elif k == "BS":
            if self.c > 0:
                L[self.r] = L[self.r][: self.c - 1] + L[self.r][self.c:]
                self.c -= 1
            elif self.r > 0:
                self.c = len(L[self.r - 1])
                L[self.r - 1] += L[self.r]
                del L[self.r]
                self.r -= 1
        elif k == "DEL":
            if self.c < len(L[self.r]):
                L[self.r] = L[self.r][: self.c] + L[self.r][self.c + 1:]
            elif self.r < len(L) - 1:
                L[self.r] += L[self.r + 1]
                del L[self.r + 1]
        elif k == "ENTER":
            self.insert("\n")
        elif k == "CLEAR":
            self.lines, self.r, self.c = [""], 0, 0
        elif k == "RESTORE" and self.last_sent:
            self.set_text(self.last_sent)
        elif k == "TAB":
            self.insert("    ")
        elif len(k) == 1 or k.startswith("TEXT:"):
            self.insert(k[5:] if k.startswith("TEXT:") else k)

    def wrapped(self, width):
        """[(display_line, is_cursor_line, cursor_col)]"""
        out = []
        for li, line in enumerate(self.lines):
            segs, cur, w, start = [], "", 0, 0
            for i, ch in enumerate(line):
                c = cw(ch)
                if w + c > width:
                    segs.append((start, cur))
                    cur, w, start = "", 0, i
                cur += ch
                w += c
            segs.append((start, cur))
            for si, (st, seg) in enumerate(segs):
                end = st + len(seg)
                last = si == len(segs) - 1
                has = li == self.r and st <= self.c and (self.c < end or (last and self.c == end))
                out.append((seg, has, vlen(line[st:self.c]) if has else -1, st))
        return out


def render_compose(ed, inst, status, W, H, flash=None, anchors=None, sent=0):
    """flash = (색, 끝나는 시각): 방금 누른 조작 키의 색으로 상자 테두리가 잠깐 켜진다 (색 = 조작)"""
    L = []
    now = time.time()
    port = inst.url.rsplit(":", 1)[-1]
    dirty = bool(ed.text) and ed.text != getattr(ed, "last_sent", None)
    rec = (f"{LIME if int(now * 2) % 2 else G0}●{RST} {G4}REC{RST}" if dirty else f"{G0}○ REC{RST}")
    left = f" {chip('COMPOSE', 'black', 'lime')} {ch_chip(inst)} {G4}{B}{inst.name}{RST} {G1}:{port}{RST}"
    right = (f"{rec}  {G1}CHR{RST} {ghost_num(len(ed.text), 5)} {G1}LN{RST} {ghost_num(len(ed.lines), 3)} "
             f"{G1}SENT{RST} {ghost_num(sent, 2)} {keycap('F1')} ")
    L.append(navbar(left, right, W))
    _anc(anchors, min(W - 2, vlen(left) + 1), 0, "compose")
    if W > 70:
        _anc(anchors, W - vlen(right) - 1, 0, "counter")
    inner = max(10, W - 4)
    box_h = max(3, H - 5)  # header + 테두리 2 + 상태줄 + 여유 1
    rows = ed.wrapped(inner)
    cur_i = next((i for i, r in enumerate(rows) if r[1]), 0)
    top = max(0, min(cur_i - box_h + 1, len(rows) - box_h)) if len(rows) > box_h else 0
    top = min(top, cur_i)
    fc = rgb(flash[0]) if flash and flash[1] > now else NV2
    lab = f" {module(1, 'MESSAGE')} "
    scroll = f" {G1}{top + 1}-{min(len(rows), top + box_h)}/{len(rows)}{RST} " if len(rows) > box_h else ""
    _anc(anchors, 1 + title_end(1, "MESSAGE", boxed=True), len(L), "message")
    L.append(f"{fc}┌─{RST}{lab}{fc}{'─' * max(0, W - 3 - vlen(lab) - vlen(scroll))}{RST}{scroll}{fc}┐{RST}")
    CUR = bg(P3["lime"]) + BLACK
    for i in range(top, top + box_h):
        if i < len(rows):
            seg, has, ccol, _ = rows[i]
            if has:
                # 커서 위치: 라임 블록
                acc, pre, post, at = 0, "", "", " "
                for j, ch in enumerate(seg):
                    if acc == ccol:
                        pre, at, post = seg[:j], ch, seg[j + 1:]
                        break
                    acc += cw(ch)
                else:
                    pre = seg
                body = f"{G4}{pre}{RST}{CUR}{at}{RST}{G4}{post}{RST}"
            else:
                body = f"{G4}{seg}{RST}"
            if not ed.text and i == 0:
                body = f"{CUR} {RST} {G1}여기에 입력하거나 Ctrl+V로 붙여넣기…{RST}"
        else:
            body = ""
        L.append(f"{fc}│{RST} {pad(body, inner)} {fc}│{RST}")
    L.append(f"{fc}└{'─' * (W - 2)}┘{RST}")
    _anc(anchors, W - 1, len(L), "keys")
    on = None
    if flash and flash[1] > now and len(flash) > 2:
        on = flash[2]
    L.append(status or compose_keys(on))
    return L

# ---------------------------------------------------------------- `?` 가이드 (모든 모니터 칸 공통)
MON_GUIDE = {
    "channel": ("CHANNEL", "채널 번호(인스턴스 색) · 이름 · 포트 · opencode 버전"),
    "sys": ("SYS", "rtt = 서버 응답 시간 · poll = 갱신 주기 · ev = 받은 이벤트 수. 숨기지 않는 엔지니어링"),
    "pet": ("PET", "이 탭 펫의 한 줄 상태: 포만 · 기분 · 체력 · 허락 대기 · 퀘스트"),
    "tokens": ("TOKENS", "핵심 값 4개: ①파랑 IN · ②초록 OUT · ③흰색 CACHE · ④회색 COST. 표·차트도 같은 색"),
    "sessions": ("SESSIONS", "세션 트리. BUSY 라임 · RTRY 흰색 · PERM/ASK 깜빡 = 사용자 응답 대기. i = idle 서브 보이기"),
    "events": ("EVENTS", "이벤트 흐름. ▶ 도구 시작 · ✓ 끝 · × 오류 · ⚠ 대기 · ☑ 할 일 · ⇣ 압축. LED = 방금 새 이벤트"),
    "logs": ("LOGS", "opencode 로그. 레벨 칩 ERR/WRN/INF/DBG · 키는 흐리게 값은 밝게. LED = 방금 새 줄"),
    "overview": ("OVERVIEW", "모든 인스턴스 요약: 등록 수 · 온라인 수"),
    "instances": ("INSTANCES", "채널마다 한 줄: 포트 · 모드 · 세션 · 바쁨 · 에이전트 · 토큰 · 펫"),
    "active": ("ACTIVE WORK", "지금 일하는 세션 전부 (할 일 [2/4] · 돌아가는 도구)"),
    "usage": ("USAGE", "토큰 흐름. 흐르는 동안 테이프 릴이 돌아요"),
    "rate": ("RATE", "최근 1분 토큰 수 (세그먼트 숫자)"),
    "chart": ("TOKENS", "10초 단위 막대: ①파랑 = IN · ②초록 = OUT"),
    "mixer": ("MIX", "채널 막대: 인스턴스별 최근 1분 비율. 맨 위 LED = 작업 중"),
    "compose": ("COMPOSE", "긴 메시지를 써서 opencode 입력칸으로 보내는 칸"),
    "counter": ("COUNTER", "REC = 안 보낸 글 있음 · CHR 글자 · LN 줄 · SENT 보낸 횟수"),
    "message": ("MESSAGE", "입력 상자. 조작 키를 누르면 그 키 색으로 테두리가 켜져요"),
    "keys": ("KEYS", "①파랑 ^P 넣기만 · ②초록 ^S 전송 · ③흰색 ^R 복구 · ④회색 ^L 지우기"),
    "ranch": ("RANCH", "모든 탭의 펫 목장 (읽기 전용)"),
    "raidbar": ("RAID", "이번 주 공동 레이드 진행 · MVP"),
    "cards": ("CARDS", "채널 번호 · 펫 · 상태 칩 · 퀘스트/한마디"),
}
MON = {"guide": False, "sel": 0}


def guide_overlay(lines, W, H, anchors, table=None):
    """줄 단위 화면 위에 `?` 가이드(번호표 + 범례 띠)를 겹친다"""
    table = table or MON_GUIDE
    items = [(x, y) + table[k] for x, y, k in anchors if k in table]
    cv = canvas_from_lines(lines, W, H)
    MON["sel"] = min(MON["sel"], max(0, len(items) - 1))
    guide_draw(cv, W, H, items, MON["sel"])
    return cv.lines()

def guide_key(k):
    """가이드가 떠 있을 때의 키: 숫자·←→ 고르기, 나머지 닫기. 처리했으면 True"""
    if not MON["guide"]:
        if k in ("?", "F1"):
            MON["guide"], MON["sel"] = True, 0
            return True
        return False
    if len(k) == 1 and k in "123456789":
        MON["sel"] = int(k) - 1
    elif k in ("LEFT", "RIGHT"):
        MON["sel"] = max(0, MON["sel"] + (1 if k == "RIGHT" else -1))
    else:
        MON["guide"] = False
    return True


def compose_send(inst, text, submit):
    try:
        inst.api.post("/tui/append-prompt", {"text": text})
        if submit:
            inst.api.post("/tui/submit-prompt", {})
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def recover_paste(toks):
    """Windows Terminal 이 Ctrl+V 를 가로채 '타이핑'처럼 흘려보낸 붙여넣기를 클립보드 원문으로 복원.
    (WT 는 키보드에 없는 문자(… — “ ” • 등)를 Alt+숫자패드 입력으로 보내는데 msvcrt 는 그걸 놓친다)
    몰려 들어온 글자들이 클립보드 내용의 부분열이면 클립보드 원문을 돌려준다. 아니면 None."""
    kept = [t for t in toks if len(t) == 1 or t in ("ENTER", "TAB")]
    if len(kept) < 8 or len(kept) < len(toks) * 0.9:
        return None
    burst = "".join("\n" if t == "ENTER" else "\t" if t == "TAB" else t for t in kept)
    clip = clipboard_text().replace("\r\n", "\n").replace("\r", "\n")
    if not clip or len(burst) > len(clip) or len(burst) < 0.6 * len(clip.rstrip("\n")):
        return None
    it = iter(clip)
    return clip if all(ch in it for ch in burst) else None


def drain_burst(toks):
    """붙여넣기처럼 몰려오는 입력은 조금 더 기다렸다가 한 덩어리로 모은다 (Windows)"""
    import msvcrt
    quiet = 0
    for _ in range(200):
        time.sleep(0.02)
        if msvcrt.kbhit():
            toks += read_keys_windows()
            quiet = 0
        else:
            quiet += 1
            if quiet >= 5:
                break
    return toks


def run_compose(a):
    inst = single_instance(a)
    ed = Editor()
    status, status_until = "", 0.0
    flash = None          # (색, 끝나는 시각, 키) — 누른 조작 키의 색으로 테두리가 잠깐 켜진다
    sent = 0
    t0 = time.time()
    with RawInput() as fd:
        sys.stdout.write(HIDE + "\x1b[2J")
        while True:
            W, H = size(a)
            now = time.time()
            if now - t0 < BOOT_T:
                cv = Canvas(W, H)
                boot_draw(cv, W, H, now - t0, "COMPOSE", "OCMUX · 긴 메시지 입력", BOOT_T)
                lines = cv.lines()
            else:
                anchors = []
                lines = render_compose(ed, inst, status if now < status_until else "", W, H, flash, anchors, sent)
                if MON["guide"]:
                    lines = guide_overlay(lines, W, H, anchors)
            paint(lines, W, H, False)
            toks = poll_keys(0.25, fd)
            if not toks:
                continue
            if now - t0 < BOOT_T:
                t0 = now - BOOT_T
            if fd is None and len(toks) >= 8:
                toks = drain_burst(toks)
                fixed = recover_paste(toks)
                if fixed is not None:
                    # 붙여넣기 뒤에 이어 누른 Ctrl+S 같은 명령 키는 살린다
                    toks = ["TEXT:" + fixed] + [t for t in toks if t in ("SEND", "PUT", "CLEAR", "RESTORE")]
            for t in toks:
                if MON["guide"] or t == "F1":        # 가이드 중엔 글자를 입력하지 않는다
                    guide_key(t)
                    continue
                if t == "PASTE":
                    ed.key("TEXT:" + clipboard_text())
                elif t in ("SEND", "PUT"):
                    flash = (ENC[1] if t == "SEND" else ENC[0], time.time() + 0.6, "^S" if t == "SEND" else "^P")
                    txt = ed.text.strip("\n")
                    if not txt.strip():
                        status, status_until = f"{chip('EMPTY', 'black', 'gray')} {G}보낼 내용이 없습니다{RST}", time.time() + 4
                        continue
                    ok, err = compose_send(inst, txt, t == "SEND")
                    if ok:
                        sent += 1
                        ed.last_sent = txt
                        ed.key("CLEAR")
                        what = "전송" if t == "SEND" else "opencode 입력칸에 넣음"
                        status = f"{chip('SENT', 'black', 'lime')} {G4}{what} {time.strftime('%H:%M:%S')}{RST} {G1}(Ctrl+R 복구){RST}"
                        status = compose_after_send(inst, txt, t == "SEND", status)
                    else:
                        status = f"{chip('FAIL', 'black', 'white')} {WH}전송 실패: {err}{RST}"
                    status_until = time.time() + 8
                else:
                    if t in ("RESTORE", "CLEAR"):
                        flash = (ENC[2] if t == "RESTORE" else ENC[3], time.time() + 0.6, "^R" if t == "RESTORE" else "^L")
                    ed.key(t)


def compose_after_send(inst, text, submitted, status):
    """전송 후 펫 연동: 이벤트 버스 기록 + 펫 반응 한 줄 (펫 모듈이 없으면 그대로)"""
    try:
        import ocmux_pet
        ocmux_pet.bus_write(inst.name, {"type": "compose", "chars": len(text), "submitted": submitted,
                                        "text": text[:400]})
        line = ocmux_pet.compose_reaction(inst.name, text)
        if line:
            return status + "  " + line
    except Exception:
        pass
    return status


# ---------------------------------------------------------------- pet (TOKEN QUEST: 토큰펫)
def run_rpg(a):
    import ocmux_pet_run
    ocmux_pet_run.run(a, sys.modules[__name__])


def main():
    ap = argparse.ArgumentParser(description="ocmux monitor")
    ap.add_argument("mode", choices=["status", "overview", "logs", "usage", "rpg", "compose"], nargs="?", default="status")
    ap.add_argument("--url")
    ap.add_argument("--name", help="인스턴스 이름 (레지스트리 조회/표시용)")
    ap.add_argument("--color", default=None, help="#RRGGBB 태그 색")
    ap.add_argument("--password", default=os.environ.get("OPENCODE_SERVER_PASSWORD"))
    ap.add_argument("--dir", default=None)
    ap.add_argument("--interval", type=float, default=2.0)
    ap.add_argument("--max-sessions", type=int, default=15)
    ap.add_argument("--hide-idle-sub", action="store_true", help="idle subagent 세션 숨김")
    # logs (status/overview 내부 LOGS 영역 + logs 모드)
    ap.add_argument("--log-dir", action="append")
    ap.add_argument("--file", help="특정 로그 파일 tail (headless serve 로그)")
    ap.add_argument("--since", type=float, help="이 epoch 이후 생성된 첫 로그 파일을 추적")
    ap.add_argument("--all", action="store_true", help="logs: 최근 로그 전체 / usage: 전체 인스턴스 합산")
    ap.add_argument("--no-logs", action="store_true", help="status/overview에서 LOGS 영역 끄기")
    ap.add_argument("--tag", default=None)
    ap.add_argument("--level", default="DEBUG")
    ap.add_argument("--grep", default=None)
    # usage / rpg
    ap.add_argument("--bucket", type=int, default=10, help="usage 차트 막대 1개 = N초")
    ap.add_argument("--hero", default=None, help="rpg: 새 알에 붙일 펫 이름 (기본: 토큰이)")
    ap.add_argument("--bell", action="store_true", help="rpg: 응답 도착 시 터미널 벨 (게임 설정도 켜짐)")
    # debug / screenshot
    ap.add_argument("--once", type=float, default=0, help="N초 수집 후 1프레임 출력하고 종료")
    ap.add_argument("--cols", type=int, default=0)
    ap.add_argument("--rows", type=int, default=0)
    ap.add_argument("--guide", action="store_true", help="--once 와 함께: `?` 가이드를 켠 화면으로 출력")
    a = ap.parse_args()
    a.level = a.level.upper()
    try:
        {"status": run_status, "overview": run_overview, "logs": run_logs,
         "usage": run_usage, "rpg": run_rpg, "compose": run_compose}[a.mode](a)
    except KeyboardInterrupt:
        pass
    finally:
        if not a.once:
            sys.stdout.write(SHOW + RST + "\n")


if __name__ == "__main__":
    main()
