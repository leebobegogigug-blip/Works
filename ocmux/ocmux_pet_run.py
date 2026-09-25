"""
ocmux_pet_run.py - TOKEN QUEST 실행기: opencode 이벤트 → 게임 신호, 키 입력, 화면 루프

  python oc_monitor.py rpg --url http://127.0.0.1:4096 --name api-server   # 인스턴스 탭 (펫 돌보기)
  python oc_monitor.py rpg --all                                          # overview 탭 (목장: 모든 펫)
"""
import collections
import os
import queue
import sys
import threading
import time

import ocmux_pet as P
import ocmux_pet_ui as UI
from ocmux_term import HIDE, SHOW, RST, poll_keys, RawInput


class SignalBridge:
    """Instance(폴링+SSE) 상태 변화를 게임 신호로 바꾼다

    루트 세션 busy → 'busy' (자동 원정 출발) / idle → 'idle' (응답 도착 = 퀘스트 보상)
    서브에이전트 세션 → 'sub_start' / 'sub_end' (동료)
    todo.updated → 'todos' (메인 퀘스트) / permission·question → 'wait' / 'wait_done'
    """

    OFFLINE_GRACE = 10.0   # 서버가 이만큼 응답이 없으면 진행 중이던 작업은 끝난 것으로 본다

    def __init__(self, inst, token_delta=None, wait_info=None, ask_events=(), done_events=()):
        self.inst = inst
        self.q = queue.Queue()
        self.parent = {}          # sid -> parentID (None = 루트)
        self.agent = {}           # sid -> agent
        self.busy = set()         # 현재 busy 인 sid (분류 끝난 것만)
        self.kind = {}            # sid -> "root" / "sub"  (시작할 때 정한 분류를 끝날 때도 그대로 쓴다)
        self.retry = set()
        self.tok = token_delta
        self.wait_info = wait_info
        self.ask_events, self.done_events = tuple(ask_events), tuple(done_events)
        self.seen_tools = collections.OrderedDict()
        self.running_parts = set()
        self.last_tok = None
        inst.listeners.append(self._on_event)

    # SSE 스레드에서 호출됨 → 큐에만 넣는다
    def _on_event(self, ev):
        typ, p = ev.get("type", ""), ev.get("properties", {}) or {}
        if typ in ("session.created", "session.updated"):
            info = p.get("info", {})
            if info.get("id"):
                self.q.put(("_session", info.get("id"), info.get("parentID"), info.get("title")))
        elif typ == "session.deleted":
            info = p.get("info", {})
            if info.get("id"):
                self.q.put(("_deleted", info["id"]))
        elif typ == "message.updated":
            info = p.get("info", {})
            agent = info.get("agent") or info.get("mode")
            if agent and info.get("sessionID"):
                self.q.put(("_agent", info["sessionID"], agent))
        elif typ == "message.part.updated":
            part = p.get("part", {})
            if part.get("type") == "tool":
                state = part.get("state") or {}
                st = state.get("status")
                key = part.get("id") or part.get("callID")
                if st == "running" and key:
                    self.q.put(("_running", key))
                elif st in ("completed", "error"):
                    t = state.get("time") or {}
                    # 컨텍스트 압축(prune) 때 예전 도구 결과가 다시 흘러오는 건 새 도구 사용이 아니다
                    if t.get("compacted"):
                        return
                    end = t.get("end") or 0
                    stale = bool(end) and time.time() * 1000 - end > 120_000
                    self.q.put(("_tool", key or id(part), part.get("tool") or "", st == "completed", stale))
        elif typ == "session.error":
            err = p.get("error") or {}
            if err.get("name") == "MessageAbortedError":      # 사용자가 Esc 로 멈춘 것 = 에러 아님
                self.q.put(("abort", p.get("sessionID")))
                return
            msg = (err.get("data") or {}).get("message") or err.get("name") or "error"
            self.q.put(("error", msg))
        elif typ == "todo.updated":
            self.q.put(("_todos", p.get("sessionID"), p.get("todos") or []))
        elif typ in self.ask_events and self.wait_info:
            w = self.wait_info(typ, p)
            if w:
                self.q.put(("_wait", w))
        elif typ in self.done_events:
            wid = p.get("permissionID") or p.get("requestID") or p.get("id")
            reply = p.get("response") or p.get("reply") or ""
            if wid:
                self.q.put(("_wait_done", str(wid), str(reply)))
        elif typ == "session.compacted":
            self.q.put(("compacted", p.get("sessionID")))
        elif typ == "command.executed":
            self.q.put(("command", p.get("name") or ""))

    def _fetch_todos(self, sid):
        """루트 작업이 시작되면 그 세션의 할 일 목록을 한 번 받아 온다 (펫 창을 나중에 켰을 때 대비)"""
        def go():
            try:
                todos = self.inst.api.get(f"/session/{sid}/todo", timeout=3)
                if isinstance(todos, list) and todos:
                    self.q.put(("_todos", sid, todos))
            except Exception:
                pass
        threading.Thread(target=go, daemon=True).start()

    def _is_root(self, sid, sessions):
        return not (self.parent.get(sid) or (sessions.get(sid) or {}).get("parentID"))

    def poll(self, game):
        inst = self.inst
        with inst.lock:
            sessions = dict(inst.sessions)
        # 1) 큐 처리
        while True:
            try:
                item = self.q.get_nowait()
            except queue.Empty:
                break
            kind = item[0]
            if kind == "_session":
                self.parent[item[1]] = item[2]
            elif kind == "_deleted":
                sid = item[1]
                self.busy.discard(sid)
                self.kind.pop(sid, None)
                game.signal("gone", sid=sid)     # 보상 없이 정리 (busy_roots/동료/응답 대기, 자동 원정 귀환)
            elif kind == "_agent":
                sid, agent = item[1], item[2]
                self.agent[sid] = agent
                if self.kind.get(sid) == "root" and sid in self.busy:
                    game.signal("agent", agent=agent)
            elif kind == "_running":
                self.running_parts.add(item[1])
                if len(self.running_parts) > 2000:
                    self.running_parts.clear()
            elif kind == "_tool":
                key, tool, ok, stale = item[1], item[2], item[3], item[4]
                if key in self.seen_tools:
                    continue
                self.seen_tools[key] = 1
                while len(self.seen_tools) > 1000:
                    self.seen_tools.popitem(last=False)
                if stale and key not in self.running_parts:
                    continue     # 오래전에 끝난 도구가 (재연결/압축으로) 다시 온 것
                self.running_parts.discard(key)
                game.signal("tool", tool=tool, ok=ok)
            elif kind == "_todos":
                sid, todos = item[1], item[2]
                title = (sessions.get(sid) or {}).get("title") or ""
                known = sid in self.parent or sid in sessions
                # 어떤 세션인지 모르면 루트로 단정하지 않는다 (서브에이전트 목록이 메인 퀘스트를 덮지 않게)
                game.signal("todos", sid=sid, title=title, todos=todos, root=known and self._is_root(sid, sessions))
            elif kind == "_wait":
                w = item[1]
                game.signal("wait", id=w["id"], sid=w.get("sid") or "", wkind=w["kind"], label=w["label"])
            elif kind == "_wait_done":
                game.signal("wait_done", id=item[1], reply=item[2])
            elif kind == "error":
                game.signal("error", msg=item[1])
            elif kind == "abort":
                game.signal("abort", sid=item[1] or "")
            elif kind == "compacted":
                game.signal("compacted", sid=item[1] or "")
            elif kind == "command":
                game.signal("command", name=item[1])
        if not inst.ready:
            return
        # 2) 토큰 (세션별 기준점: 예전 세션을 다시 열어도 과거 토큰이 한꺼번에 들어오지 않게)
        if self.tok is not None:
            din, dout = self.tok.update(inst)
        else:
            tin, tout = inst.totals()
            din = dout = 0
            if self.last_tok is not None:
                din, dout = max(0, tin - self.last_tok[0]), max(0, tout - self.last_tok[1])
            self.last_tok = (tin, tout)
        if din or dout:
            game.signal("tokens", tin=din, tout=dout)
        # 3) busy / idle / retry 전이
        with inst.lock:
            status = {sid: (st or {}).get("type") for sid, st in inst.status.items()}
            stats = {sid: st.get("agent") for sid, st in inst.stats.items()}
            off = inst.offline_since
        offline = bool(off) and time.time() - off > self.OFFLINE_GRACE
        if offline:
            status = {}          # 서버가 죽었으면 진행 중이던 작업은 끝난 것으로 (보상 없이 정리)
        for sid, s in sessions.items():
            self.parent.setdefault(sid, s.get("parentID"))
        busy = {sid for sid, t in status.items() if t in ("busy", "retry")}
        for sid in busy - self.busy:
            if sid not in self.parent and sid not in sessions:
                continue         # 아직 어떤 세션인지 모름 → 다음 폴링 때 분류 (루트/서브 오분류 방지)
            agent = self.agent.get(sid) or (stats.get(sid) if stats.get(sid) not in (None, "-") else None)
            if self._is_root(sid, sessions):
                self.kind[sid] = "root"
                title = (sessions.get(sid) or {}).get("title") or "요청"
                game.signal("busy", sid=sid, title=title, agent=agent)
                self._fetch_todos(sid)
            else:
                self.kind[sid] = "sub"
                game.signal("sub_start", sid=sid, agent=agent or "general")
        for sid in self.busy - busy:
            k = self.kind.pop(sid, None) or ("root" if self._is_root(sid, sessions) else "sub")
            if offline:
                game.signal("gone", sid=sid)       # 서버가 안 보여서 끝낸 것 → 다시 살아나면 그때 정상 처리
            elif k == "sub":
                game.signal("sub_end", sid=sid, agent=self.agent.get(sid))
            else:
                title = (sessions.get(sid) or {}).get("title") or "요청"
                game.signal("idle", sid=sid, title=title)
        retry = {sid for sid, t in status.items() if t == "retry"}
        for sid in retry - self.retry:
            game.signal("retry", msg="retry")
        self.busy = {sid for sid in busy if sid in self.kind}
        self.retry = retry


def _toast(inst, title, message, variant):
    def go():
        try:
            inst.api.post("/tui/show-toast", {"title": title, "message": message,
                                              "variant": {"error": "error", "warning": "warning"}.get(variant, "success")})
        except Exception:
            pass
    threading.Thread(target=go, daemon=True).start()


_CTRL_HANDLER = []   # ctypes 콜백이 GC 되지 않게 붙잡아 둔다


def install_close_handler(game):
    """Windows: 탭/창을 X 로 닫으면(CTRL_CLOSE_EVENT) finally 가 안 돈다 → 여기서 저장하고 잠금을 푼다"""
    if os.name != "nt":
        return
    try:
        import ctypes

        @ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint)
        def handler(ev):
            if ev in (2, 5, 6):   # CLOSE / LOGOFF / SHUTDOWN
                try:
                    game.close()
                except Exception:
                    pass
            return 0
        ctypes.windll.kernel32.SetConsoleCtrlHandler(handler, 1)
        _CTRL_HANDLER.append(handler)
    except Exception:
        pass


def run(a, M):
    """M: oc_monitor 모듈 (Instance / RegistryWatcher / paint / size 재사용)"""
    if a.all or not (a.name or a.url):
        return run_ranch(a, M)
    inst = M.single_instance(a)
    scope = inst.name
    game = P.PetGame(scope, name=getattr(a, "hero", None))
    if getattr(a, "bell", False) and not game.readonly:
        game.s["settings"]["bell"] = True
    ui = UI.PetUI(game)
    bridge = SignalBridge(inst, M.TokenDelta(), M.wait_info, M.WAIT_ASK_EVENTS, M.WAIT_DONE_EVENTS)
    bus = P.BusReader(scope)
    if a.once:
        end = time.time() + a.once
        while time.time() < end:
            bridge.poll(game)
            game.tick()
            time.sleep(0.1)
        W, H = M.size(a)
        ui.boot_until = 0          # 한 장 찍기(--once)에는 부팅 연출 없이 바로 본 화면
        ui.guide = bool(getattr(a, "guide", False))
        M.paint(ui.render(W, H), W, H, True)
        game.close()
        return
    install_close_handler(game)
    sys.stdout.write(HIDE + "\x1b[2J")
    last_bus = 0.0
    try:
        with RawInput() as fd:
            while True:
                now = time.time()
                bridge.poll(game)
                if now - last_bus > 0.5:
                    last_bus = now
                    for ev in bus.poll():
                        if ev.get("type") == "compose":
                            game.signal("compose", chars=ev.get("chars", 0), text=ev.get("text", ""),
                                        submitted=ev.get("submitted", True), ctx=ev.get("ctx"))
                game.tick()
                if game.outbox:
                    if game.s["settings"].get("toast"):
                        for title, msg, variant in game.outbox[:3]:
                            _toast(inst, title, msg, variant)
                    game.outbox.clear()
                if game.ring:
                    game.ring = False
                    sys.stdout.write("\a")
                W, H = M.size(a)
                M.paint(ui.render(W, H), W, H, False)
                ui.keys(poll_keys(0.1, fd))
    except KeyboardInterrupt:
        pass
    finally:
        game.close()
        sys.stdout.write(SHOW + RST + "\n")


def run_ranch(a, M):
    colors = {}

    def frame(W, H, anc=None):
        rows = M.load_registry()
        for r in rows:
            if r.get("name"):
                colors[r["name"]] = r.get("color") or "#6ABA23"
        scopes = [r["name"] for r in rows if r.get("name")]
        return UI.render_ranch(scopes, W, H, colors, anc)

    M.loop(a, frame, tick=1.0, word="RANCH")


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, here)
    import oc_monitor
    sys.argv = [sys.argv[0], "rpg"] + sys.argv[1:]
    oc_monitor.main()
