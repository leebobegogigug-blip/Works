# -*- coding: utf-8 -*-
r"""flow1_trace — --run: 스크립트를 실행하며 쿼리 호출마다 걸린 시간 · 행 수를 잰다 (Flow–1 · 표준 라이브러리만)

정적 분석(flow1_scan)이 찾은 '쿼리 호출 자리'만 감싼다. 사내 패키지의 API 를 몰라도 되고, 다른 코드는 그대로 돈다.
  감싸는 곳: 실행한 스크립트 + 그 폴더 아래에서 import 하는 .py (site-packages · 가상환경은 건드리지 않는다)
  감싸는 법: 코드의 dq.query(sql) 를 __flow1_wrap__("파일:줄:칸", dq.query)(sql) 로 바꿔 컴파일 (디스크의 파일은 그대로)

[기록 — %LOCALAPPDATA%\flow-1\runs\<스크립트 키>\]  RULES.md › W-05 · W-06
  live.json          실행 중인 상태 (3초마다 · 호출 시작 · 끝마다 원자적으로 다시 씀). 끝나면 지운다
  <날짜-시각>.json   끝난 실행 하나: 호출 자리 · 사용자 코드 스택(파일, 줄) · 시작(초) · 걸린 ms · 행 수 · 열 수 · 성공 · 오류
  기록하지 않는 것: SQL 원문 · 인자 값 · 결과 데이터 · 명령줄 인자 · 환경 변수. 오류 글의 비밀번호 꼴은 가린다
"""
import ast
import builtins
import hashlib
import importlib.abc
import importlib.machinery
import json
import os
import re
import sys
import threading
import time
import traceback
import types
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

import flow1_scan

FORMAT = 1
KEEP_DEFAULT = 20
BEAT_SEC = 3.0              # live.json 을 다시 쓰는 간격 (화면은 15초 넘게 안 바뀌면 끊긴 것으로 본다)
STALE_SEC = 15.0
_SKIP_DIRS = ("site-packages", "dist-packages", os.sep + "venv" + os.sep, os.sep + ".venv" + os.sep, os.sep + "Lib" + os.sep)


def script_key(path: str) -> str:
    """스크립트 경로 → 기록 폴더 이름 (같은 이름의 다른 폴더 스크립트와 섞이지 않게)"""
    ap = os.path.normcase(os.path.abspath(path))
    base = re.sub(r"[^0-9A-Za-z_.-]+", "_", os.path.basename(ap))[:40] or "script"
    return base + "-" + hashlib.sha1(ap.encode("utf-8")).hexdigest()[:10]


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def write_json(path: str, data: Any) -> None:
    """원자적 쓰기 — .tmp 에 쓰고 바꿔치기 (RULES.md › W-06)"""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False)
    for _ in range(20):          # Windows: 화면 서버가 읽는 순간이면 잠깐 기다렸다가
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.05)
    os.replace(tmp, path)


_SECRET_RE = re.compile(r"((?:password|passwd|pwd|secret|token|api[_-]?key)\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|[^\s,;&]+)", re.I)
_URL_PW_RE = re.compile(r"(://[^:/@\s]+:)[^@\s]+(@)")


def redact(msg: str) -> str:
    """오류 글에서 비밀번호 · 토큰 꼴을 가린다 (RULES.md › W-04)"""
    msg = _SECRET_RE.sub(lambda m: m.group(1) + "***", msg)
    return _URL_PW_RE.sub(r"\1***\2", msg)


def shape_of(result: Any) -> Tuple[Optional[int], Optional[int]]:
    """결과의 (행, 열) — 데이터는 보지 않고 모양만. 지연 계산 객체(len 이 쿼리를 다시 부를 수 있는 것)는 건드리지 않는다"""
    try:
        sh = getattr(result, "shape", None)
        if isinstance(sh, tuple) and sh and all(isinstance(x, int) for x in sh):
            return sh[0], (sh[1] if len(sh) > 1 else None)
        if isinstance(result, (list, tuple)):
            first = result[0] if result else None
            return len(result), (len(first) if isinstance(first, (list, tuple, dict)) else None)
        rc = getattr(result, "rowcount", None)
        if isinstance(rc, int) and rc >= 0:
            return rc, None
    except Exception:
        pass
    return None, None


# ─────────────────────────────────────────────────────────────── 01 감싸기 (AST)

class _Wrap(ast.NodeTransformer):
    def __init__(self, path: str, spots: Set[Tuple[int, int, int, int]]):
        self.path = path
        self.spots = spots
        self.done = 0

    def visit_Call(self, node: ast.Call) -> ast.AST:
        self.generic_visit(node)
        key = (node.lineno, node.col_offset, getattr(node, "end_lineno", 0) or 0, getattr(node, "end_col_offset", 0) or 0)
        if key in self.spots:
            tag = f"{self.path}:{node.lineno}:{node.col_offset}"
            wrapped = ast.Call(func=ast.Name(id="__flow1_wrap__", ctx=ast.Load()),
                               args=[ast.Constant(value=tag), node.func], keywords=[])
            node.func = ast.copy_location(wrapped, node.func)
            self.done += 1
        return node


def spots_of(result: Dict[str, Any]) -> Set[Tuple[int, int, int, int]]:
    """정적 분석 결과 → 감쌀 호출 자리 (줄, 칸, 끝 줄, 끝 칸)"""
    out: Set[Tuple[int, int, int, int]] = set()
    for q in result.get("queries", []):
        pos = q.get("pos") or []
        if len(pos) == 4 and q.get("call") not in ("%%sql", "%sql", "SQL"):
            out.add(tuple(pos))  # type: ignore[arg-type]
    return out


def instrument(source: str, path: str, cfg: Dict[str, Any], kind: str = "py") -> Tuple[Any, int]:
    """코드 글 → (감싼 코드 객체, 감싼 자리 수). 노트북은 코드 셀을 이어 붙인 글 (정적 분석과 같은 줄 번호)"""
    res = flow1_scan.scan_text(source, os.path.basename(path), cfg, "py", path)
    tree = ast.parse(source, filename=path)
    w = _Wrap(path, spots_of(res))
    tree = ast.fix_missing_locations(w.visit(tree))
    return compile(tree, path, "exec"), w.done


def notebook_source(text: str) -> str:
    return "\n".join(c["code"] for c in flow1_scan.notebook_cells(text))


class _Loader(importlib.machinery.SourceFileLoader):
    """스크립트 폴더 아래 모듈을 감싸서 컴파일 — .pyc 는 읽지도 쓰지도 않는다 (감싼 코드가 평소 실행에 섞이지 않게)"""
    cfg: Dict[str, Any] = {}
    counts: Dict[str, int] = {}

    def get_code(self, fullname: str) -> Any:
        path = os.path.abspath(self.get_filename(fullname))      # 기록의 파일 경로는 언제나 절대 경로
        source = flow1_scan.read_text_file(path)
        try:
            code, n = instrument(source, path, self.cfg)
            _Loader.counts[path] = n
            return code
        except SyntaxError:
            return compile(source, path, "exec")


class _Finder(importlib.abc.MetaPathFinder):
    def __init__(self, root: str, cfg: Dict[str, Any]):
        self.root = os.path.normcase(os.path.abspath(root))
        _Loader.cfg = cfg

    def find_spec(self, fullname: str, path: Any, target: Any = None) -> Any:
        spec = importlib.machinery.PathFinder.find_spec(fullname, path, target)
        origin = getattr(spec, "origin", None) if spec is not None else None
        if not origin or not origin.endswith(".py") or not isinstance(spec.loader, importlib.machinery.SourceFileLoader):
            return spec
        o = os.path.normcase(os.path.abspath(origin))
        if not o.startswith(self.root + os.sep) or any(s.lower() in o.lower() for s in _SKIP_DIRS):
            return spec
        spec.loader = _Loader(fullname, origin)
        return spec


# ─────────────────────────────────────────────────────────────── 02 기록

class Recorder:
    def __init__(self, script: str, runs_dir: str, keep: int = KEEP_DEFAULT, root: str = ""):
        self.script = os.path.abspath(script)
        self.root = os.path.normcase(os.path.abspath(root or os.path.dirname(self.script)))
        self.dir = os.path.join(runs_dir, script_key(self.script))
        self.keep = max(1, int(keep))
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]     # 고정 길이 → 파일 이름 순서 = 시간 순서
        rid, n = stamp, 1
        while os.path.exists(os.path.join(self.dir, rid + ".json")):
            n += 1
            rid = f"{stamp}-{n}"
        self.run_id = rid
        self.t0 = time.time()
        self.started = now_iso()
        self.calls: List[Dict[str, Any]] = []
        self.busy: Dict[int, Dict[str, Any]] = {}
        self.seq = 0
        self.lock = threading.Lock()
        self.done = threading.Event()
        self.me = os.path.normcase(os.path.abspath(__file__))

    # ── 파일
    def _doc(self) -> Dict[str, Any]:
        return {"version": FORMAT, "run": self.run_id, "file": self.script, "started": self.started, "t0": self.t0,
                "pid": os.getpid(), "python": sys.version.split()[0], "calls": list(self.calls),
                "busy": list(self.busy.values()), "beat": time.time()}

    def flush_live(self) -> None:
        with self.lock:
            doc = self._doc()
        try:
            write_json(os.path.join(self.dir, "live.json"), doc)
        except OSError:
            pass

    def _beat(self) -> None:
        while not self.done.wait(BEAT_SEC):
            self.flush_live()

    def start_beat(self) -> None:
        self.flush_live()
        threading.Thread(target=self._beat, daemon=True).start()

    # ── 호출
    def _stack(self) -> List[List[Any]]:
        out: List[List[Any]] = []
        f = sys._getframe(3)
        while f is not None and len(out) < 8:
            fn = os.path.normcase(os.path.abspath(f.f_code.co_filename))
            if fn != self.me and (fn == os.path.normcase(self.script) or fn.startswith(self.root + os.sep)):
                out.append([f.f_code.co_filename, f.f_lineno])
            f = f.f_back
        return out

    def begin(self, tag: str) -> int:
        with self.lock:
            self.seq += 1
            seq = self.seq
            self.busy[seq] = {"seq": seq, "tag": tag, "stack": self._stack(), "t": round(time.time() - self.t0, 3)}
        self.flush_live()
        return seq

    def end(self, seq: int, ms: float, result: Any, err: Optional[BaseException]) -> None:
        rows, cols = shape_of(result) if err is None else (None, None)
        with self.lock:
            b = self.busy.pop(seq, {"seq": seq, "tag": "", "stack": [], "t": 0})
            rec = dict(b, ms=round(ms, 1), rows=rows, cols=cols, ok=err is None, err="")
            if err is not None:
                first = (str(err).strip().splitlines() or [""])[0]
                rec["err"] = redact(f"{type(err).__name__}: {first}")[:160].rstrip(": ")
            self.calls.append(rec)
        self.flush_live()

    def wrap(self, tag: str, func: Callable[..., Any]) -> Callable[..., Any]:
        rec = self

        def flow1_timed(*args: Any, **kwargs: Any) -> Any:
            seq = rec.begin(tag)
            t = time.perf_counter()
            try:
                result = func(*args, **kwargs)
            except BaseException as e:
                rec.end(seq, (time.perf_counter() - t) * 1000, None, e)
                raise
            rec.end(seq, (time.perf_counter() - t) * 1000, result, None)
            return result

        return flow1_timed

    # ── 끝
    def finish(self, exit_code: int, error: str) -> str:
        self.done.set()
        with self.lock:
            doc = self._doc()
        for b in doc.pop("busy"):            # 끝나지 않은 호출 (Ctrl+C · 예외로 빠져나감)
            doc["calls"].append(dict(b, ms=round((time.time() - self.t0 - b["t"]) * 1000, 1), rows=None, cols=None,
                                     ok=False, err="끝나지 않음"))
        doc.pop("beat", None)
        doc.update(ended=now_iso(), ms=round((time.time() - self.t0) * 1000, 1), exit=exit_code,
                   ok=exit_code == 0 and not error, error=redact(error)[:300])
        path = os.path.join(self.dir, self.run_id + ".json")
        write_json(path, doc)
        try:
            os.remove(os.path.join(self.dir, "live.json"))
        except OSError:
            pass
        self.prune()
        return path

    def prune(self) -> None:
        runs = sorted(n for n in os.listdir(self.dir) if n.endswith(".json") and n != "live.json")
        for old in runs[:-self.keep]:
            try:
                os.remove(os.path.join(self.dir, old))
            except OSError:
                pass


# ─────────────────────────────────────────────────────────────── 03 실행

def run_script(script: str, argv: Sequence[str], cfg: Dict[str, Any], runs_dir: str, keep: int = KEEP_DEFAULT,
               say: Callable[[str], None] = lambda m: print(m, file=sys.stderr)) -> int:
    """스크립트(.py · .ipynb)를 이 프로세스에서 __main__ 으로 실행한다. 종료 코드는 스크립트의 것"""
    script = os.path.abspath(script)
    kind = flow1_scan.kind_of(script)
    if kind == "sql":
        say("[flow-1] .sql 파일은 실행하지 않습니다 — 파이썬 스크립트나 노트북을 주세요")
        return 2
    try:
        text = flow1_scan.read_text_file(script)
        source = notebook_source(text) if kind == "ipynb" else text.replace("\r\n", "\n")
        code, n = instrument(source, script, cfg)
    except OSError as e:
        say(f"[flow-1] 파일을 읽지 못했습니다: {e}")
        return 2
    except (SyntaxError, ValueError) as e:
        say(f"[flow-1] 코드를 읽지 못했습니다: {e}")
        return 2
    rec = Recorder(script, runs_dir, keep)
    say(f"[flow-1] 실행 {os.path.basename(script)} · 쿼리 호출 자리 {n}곳을 잽니다 · 기록 {rec.dir}")
    main_mod = types.ModuleType("__main__")        # runpy 처럼 임시 __main__ — pickle · multiprocessing 이 스크립트를 찾게
    main_mod.__dict__.update({"__file__": script, "__builtins__": builtins, "__package__": None, "__spec__": None,
                              "__cached__": None, "__loader__": None})
    g = main_mod.__dict__
    old_main = sys.modules.get("__main__")
    sys.modules["__main__"] = main_mod
    old_argv, old_path = list(sys.argv), list(sys.path)
    sys.argv = [script] + list(argv)
    sys.path.insert(0, os.path.dirname(script))
    finder = _Finder(os.path.dirname(script), cfg)
    sys.meta_path.insert(0, finder)
    setattr(builtins, "__flow1_wrap__", rec.wrap)
    exit_code, error = 0, ""
    rec.start_beat()
    try:
        exec(code, g)
    except SystemExit as e:
        exit_code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    except KeyboardInterrupt:
        exit_code, error = 130, "중단 (Ctrl+C)"
    except BaseException as e:   # 스크립트의 오류 — 알리고 기록은 남긴다 (Flow–1 의 감싸기 줄은 트레이스백에서 뺀다)
        te = traceback.TracebackException(type(e), e, e.__traceback__)
        te.stack = traceback.StackSummary.from_list([f for f in te.stack if os.path.normcase(os.path.abspath(f.filename))
                                                     != rec.me])
        sys.stderr.write("".join(te.format()))
        exit_code, error = 1, f"{type(e).__name__}: {(str(e).splitlines() or [''])[0]}"
    finally:
        path = rec.finish(exit_code, error)
        try:
            delattr(builtins, "__flow1_wrap__")
        except AttributeError:
            pass
        if finder in sys.meta_path:
            sys.meta_path.remove(finder)
        sys.argv, sys.path[:] = old_argv, old_path
        if old_main is not None:
            sys.modules["__main__"] = old_main
    total = sum(c["ms"] for c in rec.calls)
    bad = sum(1 for c in rec.calls if not c["ok"])
    spent = f"{total:.0f}ms" if total < 1000 else f"{total / 1000:.1f}s"
    say(f"[flow-1] 끝 · 종료 코드 {exit_code} · 쿼리 호출 {len(rec.calls)}번 · 쿼리 시간 {spent}"
        + (f" · 실패 {bad}" if bad else "") + f" · {path}")
    return exit_code


# ─────────────────────────────────────────────────────────────── 04 읽기 (화면 서버)

def _load(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) and isinstance(data.get("calls"), list) else None
    except (OSError, ValueError):
        return None


def list_runs(runs_dir: str, script: str) -> List[Dict[str, Any]]:
    """그 스크립트의 실행 기록 (최근 것부터) · 실행 중이면 맨 앞에 live"""
    d = os.path.join(runs_dir, script_key(script))
    if not os.path.isdir(d):
        return []
    out: List[Dict[str, Any]] = []
    live = _load(os.path.join(d, "live.json"))
    if live is not None:
        live["live"] = True
        live["stale"] = time.time() - float(live.get("beat") or 0) > STALE_SEC
        out.append(live)
    for n in sorted((n for n in os.listdir(d) if n.endswith(".json") and n != "live.json"), reverse=True):
        doc = _load(os.path.join(d, n))
        if doc is not None and int(doc.get("version") or 0) <= FORMAT:
            out.append(doc)
    return out


def pick_run(runs_dir: str, script: str, run_id: str = "") -> Optional[Dict[str, Any]]:
    """실행 기록 하나만 읽는다 — run_id 가 있으면 그것, 없으면 실행 중(live) · 가장 최근 것 (화면이 자주 부른다)"""
    d = os.path.join(runs_dir, script_key(script))
    if run_id:
        if not re.fullmatch(r"[0-9-]{8,40}", run_id):
            return None
        return _load(os.path.join(d, run_id + ".json"))
    live = _load(os.path.join(d, "live.json"))
    if live is not None:
        live["live"] = True
        live["stale"] = time.time() - float(live.get("beat") or 0) > STALE_SEC
        return live
    try:
        names = sorted((n for n in os.listdir(d) if n.endswith(".json") and n != "live.json"), reverse=True)
    except OSError:
        return None
    for n in names[:3]:
        doc = _load(os.path.join(d, n))
        if doc is not None:
            return doc
    return None


def match(run: Dict[str, Any], results: Sequence[Tuple[str, Dict[str, Any]]]) -> Dict[str, Dict[str, Any]]:
    """실행 기록 하나 → {그래프 노드 id: 요약}. results = [(노드 id 앞붙이, 스캔 결과)]
    호출 자리(파일:줄:칸)로 정적 노드를 찾고, 같은 자리의 노드가 여럿(함수를 여러 곳에서 부름)이면 스택의 줄로 가른다"""
    index: Dict[Tuple[str, int, int], List[Tuple[str, Dict[str, Any]]]] = {}
    for pre, res in results:
        f = os.path.normcase(os.path.abspath(res.get("file") or ""))
        for q in res.get("queries", []):
            pos = q.get("pos") or [0, 0]
            index.setdefault((f, pos[0], pos[1]), []).append((pre + q["id"], q))
    out: Dict[str, Dict[str, Any]] = {}
    t0 = float(run.get("t0") or 0)
    items = [(c, False) for c in run.get("calls", [])] + [(b, True) for b in run.get("busy", [])]
    for c, busy in items:
        m = re.match(r"^(.*):(\d+):(\d+)$", c.get("tag") or "")
        if not m:
            continue
        key = (os.path.normcase(os.path.abspath(m.group(1))), int(m.group(2)), int(m.group(3)))
        cands = index.get(key) or []
        if not cands:
            continue
        lines = {(os.path.normcase(os.path.abspath(s[0])), s[1]) for s in c.get("stack") or []}
        pick = next((nid for nid, q in cands if (key[0], q["line"]) in lines and q.get("via")), cands[0][0])
        s = out.setdefault(pick, {"state": "ok", "ms": 0.0, "n": 0, "rows": None, "cols": None, "err": "", "since": 0})
        if busy:
            s["state"] = "busy"
            s["since"] = t0 + float(c.get("t") or 0)
            continue
        s["n"] += 1
        s["ms"] += float(c.get("ms") or 0)
        if c.get("rows") is not None:
            s["rows"], s["cols"] = c["rows"], c.get("cols")
        if not c.get("ok"):
            s["err"] = c.get("err") or "오류"
            if s["state"] != "busy":
                s["state"] = "err"
    top = max((s["ms"] for s in out.values()), default=0.0)
    for s in out.values():
        s["ratio"] = (s["ms"] / top) if top else 0.0
    return out
