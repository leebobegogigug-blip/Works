# -*- coding: utf-8 -*-
r"""flow1_scan — 파이썬 · 노트북 코드에서 쿼리 호출과 그 사이의 흐름을 찾는다 (Flow–1 · 표준 라이브러리만 · Python 3.8+)

코드를 실행하지 않는다. ast 로 읽으면서 문자열 · 변수를 따라가 SQL 을 되살린다.

  scan_file(path, cfg)                 → 결과 dict (파일 하나)
  scan_text(text, name, cfg, kind)     → 결과 dict (kind: py · ipynb · sql)
  cfg = {"modules": [사내 쿼리 패키지 이름…], "calls": [SQL 을 받는 함수 이름…], "sinks": [to_csv …]}

[쿼리 호출을 찾는 규칙] 정본은 docs/GUIDE.md › 04 분석 규칙
  1. 인자에 SQL 모양 문자열(flow1_sql.looks_like_sql)이 들어간 호출 — 패키지 이름을 몰라도 잡힌다
     단, print · logging · write · append 처럼 SQL 을 '다루기만' 하는 호출(DENY_CALLS)은 뺀다
  2. 설정한 사내 패키지(modules)에서 나온 객체의 calls 이름 호출 — SQL 이 변수라 못 읽어도 잡는다
  3. pandas.read_sql · read_sql_query
[흐름]
  쿼리 결과 변수가 다음 SQL 의 {자리}에 들어가면 param 간선 · merge · join · concat 은 병합 노드 ·
  to_csv 같은 출력은 출력 노드 · read_csv 같은 파일 입력은 파일 노드. 로컬 함수는 부른 자리마다 펼쳐 읽는다 (3단계까지)
"""
import ast
import builtins
import json
import os
import re
import textwrap
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Sequence, Set, Tuple

import flow1_sql

FORMAT = 1                  # 결과 dict 의 형식 버전 (--json 출력 · 화면 API)
MAX_NODES = 400             # 파일 하나에서 만드는 노드 수 한도 (펼치기가 폭주하지 않게)
MAX_INLINE = 3              # 로컬 함수 펼치기 깊이
MAX_UNROLL = 20             # for 문을 목록 원소마다 펼치는 한도
MAX_SQL_FILE = 1_000_000    # open(…).read() 로 읽는 .sql 파일 크기 한도
SQL_FILE_EXT = (".sql", ".hql", ".txt")
SQL_KWARGS = ("sql", "query", "stmt", "statement", "q", "hql")    # SQL 을 받는 키워드 인자 이름 (이것부터 찾는다)
SQL_KWARG_RE = re.compile(r"sql|hql|query|stmt", re.I)          # 없으면 이름에 이것이 든 인자 (hive_sql= · sql_path= …)

DEFAULT_CALLS = ["query", "execute", "read_sql", "sql", "run", "fetch"]
DEFAULT_SINKS = ["to_csv", "to_excel", "to_parquet", "to_pickle", "to_json", "to_feather", "to_sql"]
PANDAS_QUERY = {"read_sql", "read_sql_query"}
PANDAS_READERS = {"read_csv", "read_excel", "read_parquet", "read_pickle", "read_json", "read_feather", "read_table",
                  "read_fwf", "read_hdf", "read_orc", "read_xml"}
# SQL 을 인자로 받아도 쿼리 실행이 아닌 호출 (마지막 이름)
DENY_CALLS = frozenset("""
print pprint debug info warning warn error exception critical log write writelines display echo markdown
append extend insert add put send format join replace strip lstrip rstrip dedent indent cleandoc len str repr hash
md5 sha1 sha256 encode decode split startswith endswith find count lower upper set_description set_postfix
assertEqual assertIn assertTrue sub search match findall compile loads dumps
""".split())
BUILTINS = frozenset(dir(builtins))


# ─────────────────────────────────────────────────────────────── 01 값 (정적으로 아는 만큼)

class Val:
    """변수 · 식의 값. parts 가 있으면 문자열 (("t", 글) · ("p", 자리 이름)). deps = 이 값이 기대는 노드 id"""
    __slots__ = ("kind", "parts", "deps", "items", "module", "phs", "src", "path", "attrs")

    def __init__(self, kind: str = "other", parts: Optional[List[Tuple[str, str]]] = None,
                 deps: Iterable[str] = (), items: Any = None, module: str = "",
                 phs: Optional[Dict[str, Dict[str, Any]]] = None, src: str = "", path: str = ""):
        self.kind = kind            # str · num · df · mod · list · dict · obj · file · path · other · none
        self.parts = parts
        self.deps: FrozenSet[str] = frozenset(deps)
        self.items = items
        self.module = module        # mod: 모듈 경로 (demo_query · pandas.merge) · obj: 로컬 클래스 이름
        self.phs = phs or {}        # 자리 이름 → {"expr", "deps", "line", "value"}
        self.src = src              # 문자열을 만든 방법: literal · fstring · format · percent · concat · file:…
        self.path = path            # file · path: 경로
        self.attrs: Dict[str, "Val"] = {}

    def text(self) -> str:
        return "".join(t if k == "t" else "{" + t + "}" for k, t in (self.parts or []))

    @property
    def is_str(self) -> bool:
        return self.parts is not None and self.kind in ("str", "num")

    def const(self) -> Optional[str]:
        """자리 없이 전부 아는 문자열이면 그 글"""
        if self.parts is None or any(k == "p" for k, _ in self.parts):
            return None
        return "".join(t for _, t in self.parts)


def S(text: str, src: str = "literal") -> Val:
    return Val("str", [("t", text)], src=src)


def union(vals: Iterable[Optional[Val]]) -> FrozenSet[str]:
    out: Set[str] = set()
    for v in vals:
        if v is not None:
            out |= v.deps
    return frozenset(out)


def concat(vals: Sequence[Val], src: str) -> Val:
    parts: List[Tuple[str, str]] = []
    phs: Dict[str, Dict[str, Any]] = {}
    for v in vals:
        for k, t in v.parts or []:
            if k == "t" and parts and parts[-1][0] == "t":
                parts[-1] = ("t", parts[-1][1] + t)
            else:
                parts.append((k, t))
        for name, info in v.phs.items():
            old = phs.get(name)
            phs[name] = info if old is None else dict(old, deps=sorted(set(old["deps"]) | set(info["deps"])))
    return Val("str", parts, deps=union(vals), phs=phs, src=src)


def map_text(v: Val, fn: Any) -> Val:
    """문자열의 글 조각에만 fn 적용 (자리는 그대로)"""
    out = Val("str", [(k, fn(t) if k == "t" else t) for k, t in v.parts or []], deps=v.deps, phs=dict(v.phs), src=v.src)
    return out


class Env:
    """이름 → 값. 함수 안이면 parent = 모듈 전역"""

    def __init__(self, parent: Optional["Env"] = None):
        self.vars: Dict[str, Val] = {}
        self.parent = parent

    def get(self, name: str) -> Optional[Val]:
        e: Optional[Env] = self
        while e is not None:
            if name in e.vars:
                return e.vars[name]
            e = e.parent
        return None

    def set(self, name: str, val: Val) -> None:
        self.vars[name] = val

    def copy(self) -> "Env":
        e = Env(self.parent)
        e.vars = dict(self.vars)
        return e


# ─────────────────────────────────────────────────────────────── 02 파일 읽기 (py · ipynb · sql)

def read_text_file(path: str) -> str:
    with open(path, "rb") as f:
        data = f.read()
    for enc in ("utf-8-sig", "cp949"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


_MAGIC_PY = ("%%time", "%%timeit", "%%capture", "%%prun")


def notebook_cells(text: str) -> List[Dict[str, Any]]:
    """.ipynb → 코드 셀 [{n: 셀 번호(1부터 · 코드 셀만 셈), line: 이어 붙인 줄 번호, code, sql}]
    %매직 · !명령 줄은 주석으로 바꿔 줄 번호를 지킨다. %%sql 셀은 SQL 로, %%time 류는 첫 줄만 뺀다, 그 밖의 %% 셀은 건너뛴다"""
    nb = json.loads(text)
    cells = nb.get("cells") if isinstance(nb, dict) else None
    if cells is None and isinstance(nb, dict) and nb.get("worksheets"):      # 아주 옛 형식
        cells = nb["worksheets"][0].get("cells", [])
    out: List[Dict[str, Any]] = []
    line = 1
    n = 0
    for c in cells or []:
        if not isinstance(c, dict) or c.get("cell_type") != "code":
            continue
        src = c.get("source") or c.get("input") or ""
        code = "".join(src) if isinstance(src, list) else str(src)
        n += 1
        lines = code.split("\n")
        first = lines[0].strip() if lines else ""
        cell: Dict[str, Any] = {"n": n, "line": line, "code": "", "sql": None, "var": ""}
        if first.startswith("%%sql"):
            m = re.match(r"%%sql(?:\s+(?:--\S+\s+)*)?(?:(\w+)\s*<<)?\s*(.*)$", first)
            cell["var"] = (m.group(1) or "") if m else ""
            rest = (m.group(2) if m else "").strip()
            cell["sql"] = ("\n".join([rest] + lines[1:]) if rest else "\n".join(lines[1:]))
            cell["code"] = "\n".join("#" for _ in lines)
        elif first.startswith("%%") and not first.startswith(_MAGIC_PY):
            cell["code"] = "\n".join("#" for _ in lines)
        else:
            fixed = []
            for k, ln in enumerate(lines):
                s = ln.lstrip()
                if (k == 0 and s.startswith("%%")) or s.startswith(("%", "!")) or re.match(r"^\s*\w+\s*=\s*[%!]", ln):
                    m = re.match(r"^(\s*)(?:(\w+)\s*=\s*)?%sql\s+(.*)$", ln)
                    if m:   # 줄 매직 %sql SELECT … (결과를 변수에 받는 꼴도)
                        fixed.append(m.group(1) + (m.group(2) + " = " if m.group(2) else "")
                                     + "__flow1_sql__(" + repr(m.group(3)) + ")")
                    else:
                        fixed.append(ln[:len(ln) - len(s)] + "pass  # " + s)
                else:
                    fixed.append(ln)
            cell["code"] = "\n".join(fixed)
        out.append(cell)
        line += len(lines)
    return out


# ─────────────────────────────────────────────────────────────── 03 스캐너

def _seg(source: str, node: ast.AST, limit: int = 60) -> str:
    try:
        s = ast.get_source_segment(source, node) or ""
    except Exception:
        s = ""
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= limit else s[:limit - 1] + "…"


def _dotted(node: ast.AST) -> str:
    """a.b.c 꼴이면 그 이름, 아니면 ''"""
    parts: List[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def _slice(node: ast.Subscript) -> ast.AST:
    sl = node.slice
    idx = getattr(ast, "Index", None)
    if idx is not None and isinstance(sl, idx):    # Python 3.8
        sl = sl.value  # type: ignore[attr-defined]
    return sl


class Scanner:
    def __init__(self, cfg: Dict[str, Any], path: str, source: str, kind: str):
        self.cfg = cfg
        self.modules = [m for m in (cfg.get("modules") or []) if isinstance(m, str) and m.strip()]
        self.calls = set(cfg.get("calls") if cfg.get("calls") is not None else DEFAULT_CALLS)
        self.sinks = set(cfg.get("sinks") if cfg.get("sinks") is not None else DEFAULT_SINKS)
        self.path = path
        self.dir = os.path.dirname(path) if path and os.path.isabs(path) else ""
        self.source = source
        self.kind = kind
        self.queries: List[Dict[str, Any]] = []
        self.ops: List[Dict[str, Any]] = []
        self.inputs: List[Dict[str, Any]] = []
        self.outputs: List[Dict[str, Any]] = []
        self.edges: List[Dict[str, Any]] = []
        self.warnings: List[str] = []
        self.sql_files: List[str] = []
        self.funcs: Dict[str, Tuple[ast.AST, str]] = {}      # 이름 → (def 노드, 클래스 이름)
        self.classes: Dict[str, ast.ClassDef] = {}
        self.called: Set[str] = set()
        self.inline: List[Tuple[str, int, int]] = []        # 펼치는 중인 함수 (이름, 부른 줄, 끝 줄)
        self.returns: List[List[Val]] = []
        self.loop = 0
        self.branch = 0
        self.scope = ""
        self.module_env = Env()
        self.cell_lines: List[Tuple[int, int]] = []          # ipynb: (셀 번호, 첫 줄)
        self.count = 0
        self.created: List[str] = []                         # 만든 노드 id (만든 순서)
        self.stmt_nodes: List[str] = []                      # 지금 문장에서 만든 노드 (변수 이름 붙이기)

    # ── 공통
    def _new_id(self, prefix: str, bucket: List[Dict[str, Any]]) -> str:
        return f"{prefix}{len(bucket) + 1}"

    def _full(self) -> bool:
        if self.count >= MAX_NODES:
            if "노드가 많아" not in " ".join(self.warnings):
                self.warnings.append(f"노드가 많아 {MAX_NODES}개에서 멈췄습니다 (펼치기 · 반복을 줄여 보세요)")
            return True
        return False

    def _where(self, node: ast.AST) -> Dict[str, Any]:
        """노드 자리 — 로컬 함수를 펼치는 중이면 바깥에서 부른 줄"""
        line = getattr(node, "lineno", 0)
        end = getattr(node, "end_lineno", line) or line
        via = ""
        if self.inline:
            name, l0, l1 = self.inline[0]
            via = " › ".join(f"{n}()" for n, _, _ in self.inline) + f" L{line}"
            line, end = l0, l1
        pos = [getattr(node, "lineno", 0), getattr(node, "col_offset", 0), getattr(node, "end_lineno", 0) or 0,
               getattr(node, "end_col_offset", 0) or 0]          # 실제 호출 자리 (--run 이 이 자리의 호출을 잰다)
        out: Dict[str, Any] = {"line": line, "end": end, "via": via, "scope": self.scope, "pos": pos,
                               "loop": self.loop > 0, "branch": self.branch > 0}
        if self.cell_lines:
            n, first = max((c for c in self.cell_lines if c[1] <= line), default=(0, 1), key=lambda c: c[1])
            out["cell"], out["cell_line"] = n, line - first + 1
        return out

    def _edge(self, src: str, dst: str, kind: str, label: str, side: str = "") -> None:
        e = {"from": src, "to": dst, "kind": kind, "label": label}
        if side:
            e["side"] = side
        if src != dst and e not in self.edges:
            self.edges.append(e)

    def _ph_name(self, node: ast.AST, env: Env) -> str:
        d = _dotted(node)
        if d:
            return d
        bound = {n.id for c in ast.walk(node) if isinstance(c, ast.comprehension)
                 for n in ast.walk(c.target) if isinstance(n, ast.Name)}         # 컴프리헨션 변수(x)는 이름으로 안 쓴다
        names = [n.id for n in ast.walk(node) if isinstance(n, ast.Name) and n.id not in BUILTINS and n.id not in bound]
        with_deps = [n for n in names if (env.get(n) is not None and env.get(n).deps)]   # type: ignore[union-attr]
        if with_deps:
            return with_deps[0]
        if names:
            return names[0]
        if isinstance(node, ast.Call):
            f = _dotted(node.func) or getattr(node.func, "attr", "") or "expr"
            return f + "()"
        return "expr"

    def _ph(self, node: ast.AST, env: Env, v: Val, name: str = "") -> Val:
        """모르는 값 → 자리 {이름}"""
        name = name or self._ph_name(node, env)
        info = {"expr": _seg(self.source, node, 80), "deps": sorted(v.deps), "line": getattr(node, "lineno", 0)}
        return Val("str", [("p", name)], deps=v.deps, phs={name: info}, src="fstring")

    # ── 문장
    def block(self, body: Sequence[ast.stmt], env: Env) -> None:
        for st in body:
            if self._full():
                return
            self.stmt(st, env)

    def stmt(self, st: ast.stmt, env: Env) -> None:
        self.stmt_nodes = []
        if isinstance(st, ast.Import):
            for a in st.names:
                if a.asname:
                    env.set(a.asname, Val("mod", module=a.name))
                else:
                    top = a.name.split(".")[0]
                    env.set(top, Val("mod", module=top))
        elif isinstance(st, ast.ImportFrom):
            if st.module and st.level == 0:
                for a in st.names:
                    if a.name != "*":
                        env.set(a.asname or a.name, Val("mod", module=f"{st.module}.{a.name}"))
        elif isinstance(st, ast.Assign):
            v = self.expr(st.value, env)
            self._name_nodes(st.targets, v)
            for t in st.targets:
                self.assign(t, v, env)
        elif isinstance(st, ast.AnnAssign):
            if st.value is not None:
                v = self.expr(st.value, env)
                self._name_nodes([st.target], v)
                self.assign(st.target, v, env)
        elif isinstance(st, ast.AugAssign):
            old = self.expr(st.target, env)
            v = self.expr(st.value, env)
            if isinstance(st.op, ast.Add) and (old.is_str or v.is_str):
                nv = concat([old if old.is_str else self._ph(st.target, env, old),
                             v if v.is_str else self._ph(st.value, env, v)], "concat")
            else:
                nv = Val(old.kind if old.kind != "none" else "other", deps=old.deps | v.deps)
            self.assign(st.target, nv, env)
        elif isinstance(st, ast.Expr):
            self.expr(st.value, env)
        elif isinstance(st, (ast.For, getattr(ast, "AsyncFor", ast.For))):
            self.for_loop(st, env)
        elif isinstance(st, ast.While):
            self.expr(st.test, env)
            self.loop += 1
            self.block(st.body, env)
            self.loop -= 1
            self.block(st.orelse, env)
        elif isinstance(st, ast.If):
            self.if_stmt(st, env)
        elif isinstance(st, (ast.With, getattr(ast, "AsyncWith", ast.With))):
            for item in st.items:
                v = self.expr(item.context_expr, env)
                if item.optional_vars is not None:
                    self.assign(item.optional_vars, v, env)
            self.block(st.body, env)
        elif isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self.funcs[st.name] = (st, "")
            env.set(st.name, Val("func", module=st.name))
        elif isinstance(st, ast.ClassDef):
            self.classes[st.name] = st
            env.set(st.name, Val("class", module=st.name))
            for b in st.body:
                if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.funcs[f"{st.name}.{b.name}"] = (b, st.name)
        elif isinstance(st, ast.Return):
            if st.value is not None:
                v = self.expr(st.value, env)
                if self.returns:
                    self.returns[-1].append(v)
        elif isinstance(st, ast.Delete):
            for t in st.targets:
                if isinstance(t, ast.Name):
                    env.vars.pop(t.id, None)
        else:
            for key in ("body", "orelse", "finalbody"):
                sub = getattr(st, key, None)
                if isinstance(sub, list):
                    self.block(sub, env)
            for h in getattr(st, "handlers", None) or []:
                self.block(h.body, env)
            for c in getattr(st, "cases", None) or []:      # match (3.10+)
                self.block(c.body, env)
            if isinstance(st, ast.Raise) and st.exc is not None:
                self.expr(st.exc, env)

    def _name_nodes(self, targets: Sequence[ast.AST], v: Val) -> None:
        """이 문장에서 만든 노드가 값의 출처면 변수 이름을 붙인다 (df = q(…) → 쿼리 노드의 var)"""
        names = [_dotted(t) or _seg(self.source, t, 24) for t in targets]
        names = [n for n in names if n]
        if not names:
            return
        mine = [i for i in v.deps if i in self.stmt_nodes]
        if len(mine) == 1:
            node = self.node(mine[0])
            if node is not None and not node.get("var"):
                node["var"] = names[0]

    def node(self, nid: str) -> Optional[Dict[str, Any]]:
        for bucket in (self.queries, self.ops, self.inputs, self.outputs):
            for n in bucket:
                if n["id"] == nid:
                    return n
        return None

    def assign(self, target: ast.AST, v: Val, env: Env) -> None:
        if isinstance(target, ast.Name):
            if v.parts is not None and len(v.parts) == 1 and v.parts[0][0] == "p" and v.parts[0][1] != target.id:
                old = v.parts[0][1]      # 통째로 모르는 문자열을 변수에 담으면 자리 이름 = 변수 이름 (ids = ",".join(…))
                info = dict(v.phs.get(old) or {"expr": old, "deps": sorted(v.deps), "line": 0})
                v = Val("str", [("p", target.id)], deps=v.deps, phs={target.id: info}, src=v.src)
            env.set(target.id, v)
        elif isinstance(target, (ast.Tuple, ast.List)):
            elts = target.elts
            if v.kind == "list" and isinstance(v.items, list) and len(v.items) == len(elts):
                for t, item in zip(elts, v.items):
                    self.assign(t, item, env)
            else:
                for t in elts:
                    self.assign(t.value if isinstance(t, ast.Starred) else t,
                                Val("df" if v.kind == "df" else "other", deps=v.deps), env)
        elif isinstance(target, ast.Attribute):
            base = self.expr(target.value, env)
            if base.kind == "obj":
                base.attrs[target.attr] = v
            d = _dotted(target)
            if d:
                env.set(d, v)
        elif isinstance(target, ast.Subscript):
            base_name = _dotted(target.value)
            base = env.get(base_name) if base_name else None
            key = self.expr(_slice(target), env).const()
            if base is not None and base.kind == "dict" and key is not None:
                base.items[key] = v
                base.deps = base.deps | v.deps
            elif base is not None and base_name:
                base.deps = base.deps | v.deps
        elif isinstance(target, ast.Starred):
            self.assign(target.value, v, env)

    def for_loop(self, st: Any, env: Env) -> None:
        it = self.expr(st.iter, env)
        items = it.items if it.kind == "list" and isinstance(it.items, list) else None
        if items and len(items) <= MAX_UNROLL and any(x.is_str or x.kind == "list" for x in items):
            for x in items:                      # SQL 목록을 도는 반복 — 원소마다 펼친다
                self.assign(st.target, x, env)
                self.loop += 1
                self.block(st.body, env)
                self.loop -= 1
        else:
            name = _dotted(st.target) if not isinstance(st.target, (ast.Tuple, ast.List)) else ""
            loopv = Val("df" if it.kind == "df" else "other", deps=it.deps, module=name)
            self.assign(st.target, loopv, env)
            self.loop += 1
            self.block(st.body, env)
            self.loop -= 1
        self.block(st.orelse, env)

    def if_stmt(self, st: ast.If, env: Env) -> None:
        self.expr(st.test, env)
        test = _seg(self.source, st.test, 80).replace(" ", "")
        if test in ("__name__=='__main__'", '__name__=="__main__"'):
            self.block(st.body, env)
            self.block(st.orelse, env)
            return
        a, b = env.copy(), env.copy()
        self.branch += 1
        self.block(st.body, a)
        self.block(st.orelse, b)
        self.branch -= 1
        for name in set(a.vars) | set(b.vars):     # 두 갈래를 합친다 — 한쪽만 바꿨으면 그 값, 둘 다면 if 쪽 + 의존 합침
            va, vb = a.vars.get(name), b.vars.get(name)
            old = env.vars.get(name)
            if va is vb:
                if va is not None:
                    env.vars[name] = va
                continue
            if va is not None and vb is not None and va is not old and vb is not old:
                merged = Val(va.kind, va.parts, deps=va.deps | vb.deps, items=va.items, module=va.module,
                             phs=dict(vb.phs, **va.phs), src=va.src, path=va.path)
                env.vars[name] = merged
            elif va is not None and va is not old:
                env.vars[name] = va
            elif vb is not None and vb is not old:
                env.vars[name] = vb

    # ── 식
    def expr(self, node: Optional[ast.AST], env: Env) -> Val:
        if node is None:
            return Val("none")
        try:
            return self._expr(node, env)
        except RecursionError:
            return Val()

    def _expr(self, node: ast.AST, env: Env) -> Val:
        if isinstance(node, ast.Constant):
            v = node.value
            if isinstance(v, str):
                return S(v)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return Val("num", [("t", repr(v))])
            if v is None:
                return Val("none")
            return Val("other", [("t", str(v))])
        if isinstance(node, ast.JoinedStr):
            pieces: List[Val] = []
            for part in node.values:
                if isinstance(part, ast.Constant):
                    pieces.append(S(str(part.value)))
                elif isinstance(part, ast.FormattedValue):
                    v = self.expr(part.value, env)
                    if v.is_str and part.format_spec is None and part.conversion in (-1, None):
                        pieces.append(v)
                    else:
                        pieces.append(self._ph(part.value, env, v))
                else:
                    pieces.append(self._ph(part, env, self.expr(part, env)))
            out = concat(pieces, "fstring")
            return out
        if isinstance(node, ast.BinOp):
            return self.binop(node, env)
        if isinstance(node, ast.Call):
            return self.call(node, env)
        if isinstance(node, ast.Name):
            if node.id == "__file__" and self.path:
                return Val("path", path=self.path)
            v = env.get(node.id)
            return v if v is not None else Val("other", module=node.id)
        if isinstance(node, ast.Attribute):
            d = _dotted(node)
            if d and env.get(d) is not None:
                return env.get(d)  # type: ignore[return-value]
            base = self.expr(node.value, env)
            if base.kind == "obj" and node.attr in base.attrs:
                return base.attrs[node.attr]
            if base.kind == "mod":
                return Val("mod", module=f"{base.module}.{node.attr}", deps=base.deps)
            if base.kind == "path" and node.attr == "parent":
                return Val("path", path=os.path.dirname(base.path))
            if base.kind == "df":
                return Val("df", deps=base.deps)
            return Val("other", deps=base.deps)
        if isinstance(node, ast.Subscript):
            base = self.expr(node.value, env)
            key = self.expr(_slice(node), env)
            k = key.const()
            if base.kind == "dict" and k is not None and k in base.items:
                return base.items[k]
            if base.kind == "list" and isinstance(base.items, list):
                try:
                    return base.items[int(k)] if k is not None else Val(deps=base.deps)
                except (ValueError, IndexError):
                    return Val(deps=base.deps)
            return Val("df" if base.kind == "df" else "other", deps=base.deps | key.deps)
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            items = [self.expr(e.value if isinstance(e, ast.Starred) else e, env) for e in node.elts]
            return Val("list", items=items, deps=union(items))
        if isinstance(node, ast.Dict):
            d: Dict[str, Val] = {}
            vals: List[Val] = []
            for k, v in zip(node.keys, node.values):
                vv = self.expr(v, env)
                vals.append(vv)
                kk = self.expr(k, env).const() if k is not None else None
                if kk is not None:
                    d[kk] = vv
            return Val("dict", items=d, deps=union(vals))
        if isinstance(node, ast.IfExp):
            self.expr(node.test, env)
            a, b = self.expr(node.body, env), self.expr(node.orelse, env)
            return Val(a.kind, a.parts, deps=a.deps | b.deps, items=a.items, module=a.module, phs=a.phs, src=a.src)
        if isinstance(node, getattr(ast, "NamedExpr", ())):
            v = self.expr(node.value, env)  # type: ignore[attr-defined]
            self.assign(node.target, v, env)  # type: ignore[attr-defined]
            return v
        if isinstance(node, ast.Await):
            return self.expr(node.value, env)
        if isinstance(node, ast.Starred):
            return self.expr(node.value, env)
        if isinstance(node, ast.Lambda):
            return Val()
        # 비교 · 논리 · 컴프리헨션 · 그 밖 — 안에 든 이름의 의존만 모은다 (호출은 평가해서 쿼리를 놓치지 않게)
        deps: Set[str] = set()
        kind = "other"
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.expr):
                v = self.expr(child, env)
                deps |= v.deps
                if v.kind == "df":
                    kind = "df"
            elif isinstance(child, ast.comprehension):
                it = self.expr(child.iter, env)
                deps |= it.deps
                self.assign(child.target, Val(deps=it.deps), env)
        if isinstance(node, (ast.ListComp, ast.GeneratorExp, ast.SetComp, ast.DictComp)):
            kind = "other"
        return Val(kind, deps=deps)

    def binop(self, node: ast.BinOp, env: Env) -> Val:
        left, right = self.expr(node.left, env), self.expr(node.right, env)
        if isinstance(node.op, ast.Add) and (left.is_str or right.is_str) and left.kind != "df" and right.kind != "df":
            lv = left if left.is_str else self._ph(node.left, env, left)
            rv = right if right.is_str else self._ph(node.right, env, right)
            return concat([lv, rv], "concat")
        if isinstance(node.op, ast.Mod) and left.kind == "str" and left.parts is not None:
            return self.percent(left, node.right, right, env)
        if isinstance(node.op, ast.Div) and left.kind == "path":
            r = right.const()
            return Val("path", path=os.path.join(left.path, r)) if r is not None else Val(deps=left.deps | right.deps)
        kind = "df" if "df" in (left.kind, right.kind) else ("num" if left.kind == right.kind == "num" else "other")
        return Val(kind, deps=left.deps | right.deps)

    def percent(self, tmpl: Val, rnode: ast.AST, right: Val, env: Env) -> Val:
        """'… %s …' % (a, b) · '%(x)s' % {'x': …}"""
        if right.kind == "list" and isinstance(rnode, ast.Tuple):
            seq: List[Tuple[ast.AST, Val]] = list(zip(rnode.elts, right.items))
        else:
            seq = [(rnode, right)]
        named = right.items if right.kind == "dict" else {}
        dnodes: Dict[str, ast.AST] = {}
        if isinstance(rnode, ast.Dict):
            for k, v in zip(rnode.keys, rnode.values):
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    dnodes[k.value] = v
        pieces: List[Val] = []
        idx = 0
        rx = re.compile(r"%(?:\((\w+)\))?[-+ #0]*\d*(?:\.\d+)?([sdifrxXeEgGc%])")
        for k, t in tmpl.parts or []:
            if k == "p":
                pieces.append(Val("str", [("p", t)], phs={t: tmpl.phs.get(t, {"expr": t, "deps": [], "line": 0})}))
                continue
            last = 0
            for m in rx.finditer(t):
                pieces.append(S(t[last:m.start()]))
                last = m.end()
                if m.group(2) == "%":
                    pieces.append(S("%"))
                    continue
                if m.group(1):
                    key = m.group(1)
                    v = named.get(key) if isinstance(named, dict) else None
                    if v is not None and v.is_str:
                        pieces.append(v)
                    else:
                        n = dnodes.get(key, rnode)
                        pieces.append(self._ph(n, env, v or right, (_dotted(n) if key in dnodes else "") or key))
                else:
                    if idx < len(seq):
                        n, v = seq[idx]
                        pieces.append(v if v.is_str else self._ph(n, env, v))
                    else:
                        pieces.append(self._ph(rnode, env, right))
                    idx += 1
            pieces.append(S(t[last:]))
        out = concat(pieces, "percent")
        out.deps = out.deps | right.deps
        return out

    def str_format(self, tmpl: Val, node: ast.Call, env: Env) -> Val:
        args = [(a, self.expr(a, env)) for a in node.args]
        kw = {k.arg: (k.value, self.expr(k.value, env)) for k in node.keywords if k.arg}
        pieces: List[Val] = []
        auto = 0
        rx = re.compile(r"\{\{|\}\}|\{([^{}!:]*)(?:![rsa])?(?::[^{}]*)?\}")
        for k, t in tmpl.parts or []:
            if k == "p":
                pieces.append(Val("str", [("p", t)], phs={t: tmpl.phs.get(t, {"expr": t, "deps": [], "line": 0})}))
                continue
            last = 0
            for m in rx.finditer(t):
                pieces.append(S(t[last:m.start()]))
                last = m.end()
                if m.group(0) in ("{{", "}}"):
                    pieces.append(S(m.group(0)[0]))
                    continue
                field = (m.group(1) or "").strip()
                base = re.split(r"[.\[]", field)[0] if field else ""
                if not base:
                    pair = args[auto] if auto < len(args) else None
                    auto += 1
                elif base.isdigit():
                    pair = args[int(base)] if int(base) < len(args) else None
                else:
                    pair = kw.get(base)
                if pair is None:
                    pieces.append(Val("str", [("p", base or "arg")], phs={base or "arg": {"expr": field, "deps": [], "line": 0}}))
                    continue
                n, v = pair
                simple = field == base or not field
                label = _dotted(n) or (base if base and not base.isdigit() else "")
                pieces.append(v if (v.is_str and simple) else self._ph(n, env, v, label))
            pieces.append(S(t[last:]))
        out = concat(pieces, "format")
        out.deps = out.deps | union(v for _, v in args) | union(v for _, v in kw.values())
        return out

    # ── 호출
    def call(self, node: ast.Call, env: Env) -> Val:
        func = node.func
        attr = func.attr if isinstance(func, ast.Attribute) else (func.id if isinstance(func, ast.Name) else "")
        recv = self.expr(func.value, env) if isinstance(func, ast.Attribute) else None
        fval = env.get(func.id) if isinstance(func, ast.Name) else None
        # 문자열 다루기 (쿼리가 아니다)
        if recv is not None and recv.is_str:
            if attr == "format":
                return self.str_format(recv, node, env)
            if attr == "join" and node.args:
                it = self.expr(node.args[0], env)
                if it.kind == "list" and isinstance(it.items, list) and all(x.is_str for x in it.items):
                    sep = recv.const() or ""
                    out: List[Val] = []
                    for i, x in enumerate(it.items):
                        if i:
                            out.append(S(sep))
                        out.append(x)
                    return concat(out, "concat") if out else S("")
                return self._ph(node, env, it)          # 식 전체를 남긴다 (",".join(…))
            if attr in ("strip", "lstrip", "rstrip", "upper", "lower", "casefold") and not node.args:
                v = map_text(recv, getattr(str, attr))
                if attr in ("strip", "lstrip") and v.parts and v.parts[0][0] == "t":
                    v.parts[0] = ("t", v.parts[0][1].lstrip())
                if attr in ("strip", "rstrip") and v.parts and v.parts[-1][0] == "t":
                    v.parts[-1] = ("t", v.parts[-1][1].rstrip())
                return v
            if attr == "replace" and len(node.args) >= 2:
                a, b = self.expr(node.args[0], env).const(), self.expr(node.args[1], env)
                if a is not None and b.const() is not None:
                    return map_text(recv, lambda s: s.replace(a, b.const()))  # type: ignore[arg-type]
                return recv
            if attr in ("encode", "splitlines", "split"):
                return Val(deps=recv.deps)
        name = _dotted(func)
        last = name.split(".")[-1] if name else attr
        if last in ("dedent", "cleandoc") and node.args:
            v = self.expr(node.args[0], env)
            return map_text(v, textwrap.dedent) if v.is_str else v
        if name == "str" and node.args:
            v = self.expr(node.args[0], env)
            return v if v.is_str else self._ph(node.args[0], env, v)
        # 파일 · 경로 (.sql 파일 읽기)
        if name in ("open", "io.open", "codecs.open") and node.args:
            p = self.expr(node.args[0], env)
            return Val("file", path=p.path if p.kind == "path" else (p.const() or ""))
        if last in ("Path", "PurePath", "PureWindowsPath", "PurePosixPath") and node.args:
            p = self.expr(node.args[0], env)
            return Val("path", path=p.path if p.kind == "path" else (p.const() or ""))
        if name in ("os.path.join",) and node.args:
            parts = [self.expr(a, env) for a in node.args]
            texts = [x.path if x.kind == "path" else x.const() for x in parts]
            if all(t is not None for t in texts):
                return Val("path", path=os.path.join(*texts))  # type: ignore[arg-type]
            return Val(deps=union(parts))
        if name in ("os.path.dirname", "os.path.abspath", "os.path.realpath") and node.args:
            p = self.expr(node.args[0], env)
            base = p.path if p.kind == "path" else (p.const() or "")
            return Val("path", path=os.path.dirname(base) if name.endswith("dirname") else base)
        if recv is not None and recv.kind in ("file", "path") and attr in ("read", "read_text"):
            return self.read_sql_file(recv.path, node)
        if recv is not None and recv.kind in ("file",) and attr == "readlines":
            return self.read_sql_file(recv.path, node)
        # 목록 · 사전 다루기
        if recv is not None and recv.kind == "dict" and attr in ("items", "values", "keys", "get"):
            if attr == "get" and node.args:
                k = self.expr(node.args[0], env).const()
                return recv.items.get(k, Val(deps=recv.deps)) if k is not None else Val(deps=recv.deps)
            items = list(recv.items.items())
            if attr == "items":
                return Val("list", items=[Val("list", items=[S(k), v], deps=v.deps) for k, v in items], deps=recv.deps)
            if attr == "values":
                return Val("list", items=[v for _, v in items], deps=recv.deps)
            return Val("list", items=[S(k) for k, _ in items], deps=recv.deps)
        if recv is not None and recv.kind == "list" and attr in ("append", "extend") and node.args:
            v = self.expr(node.args[0], env)
            if isinstance(recv.items, list):
                if attr == "append":
                    recv.items.append(v)
                elif v.kind == "list" and isinstance(v.items, list):
                    recv.items.extend(v.items)
            recv.deps = recv.deps | v.deps
            return Val("none")
        # 인자 평가
        args = [self.expr(a, env) for a in node.args]
        kws = {k.arg or "**": self.expr(k.value, env) for k in node.keywords}
        # 매직 %sql (노트북 줄 매직을 바꾼 것)
        if name == "__flow1_sql__" and args and args[0].is_str:
            return self.make_query(node, env, args[0], "%sql", [], {})
        # 로컬 함수 · 클래스 → 펼친다
        if isinstance(func, ast.Name) and func.id in self.funcs and (fval is None or fval.kind == "func"):
            return self.inline_call(func.id, node, args, kws, env, None)
        if isinstance(func, ast.Name) and func.id in self.classes and (fval is None or fval.kind == "class"):
            obj = Val("obj", module=func.id)
            if f"{func.id}.__init__" in self.funcs:
                self.inline_call(f"{func.id}.__init__", node, args, kws, env, obj)
            return obj
        if recv is not None and recv.kind == "obj" and f"{recv.module}.{attr}" in self.funcs:
            return self.inline_call(f"{recv.module}.{attr}", node, args, kws, env, recv)
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "self" \
                and self.scope and "." in self.scope:
            cls = self.scope.split(".")[0].replace("def ", "")
            if f"{cls}.{attr}" in self.funcs:
                return self.inline_call(f"{cls}.{attr}", node, args, kws, env, recv)
        root = recv if recv is not None else fval
        module = root.module if root is not None and root.kind == "mod" else ""
        full = f"{module}.{attr}" if recv is not None and module else module
        # pandas: 병합 · 파일 입력 · read_sql
        is_pd = module.split(".")[0] == "pandas" if module else False
        if is_pd and last in ("merge", "concat", "merge_asof", "merge_ordered"):
            return self.make_op(node, env, "concat" if last == "concat" else "merge", args, kws, None)
        if recv is not None and recv.kind == "df" and attr in ("merge", "join", "merge_asof") and (args or kws.get("right")):
            other = args[0] if args else kws.get("right")
            if attr != "join" or (other is not None and (other.kind == "df" or other.deps)):
                return self.make_op(node, env, "join" if attr == "join" else "merge", args, kws, recv)
        if recv is not None and recv.kind == "df" and attr == "append" and args and args[0].deps:
            return self.make_op(node, env, "concat", args, kws, recv)
        if (is_pd or (recv is None and module.split(".")[0] == "pandas")) and last in PANDAS_READERS:
            return self.make_input(node, env, last, args, kws)
        # 출력
        if recv is not None and attr in self.sinks and (recv.kind == "df" or recv.deps):
            return self.make_output(node, env, attr, recv, args, kws)
        # 쿼리
        sql_val: Optional[Val] = None
        sql_node: Optional[ast.AST] = None
        for a_node, v in list(zip(node.args, args)) + [(k.value, kws.get(k.arg or "**")) for k in node.keywords]:
            if v is not None and v.is_str and flow1_sql.looks_like_sql(v.text()):
                sql_val, sql_node = v, a_node
                break
        mine = self._module_call(module, attr, full)
        pandas_sql = is_pd and last in PANDAS_QUERY
        denied = last in DENY_CALLS and not mine and not pandas_sql
        if not denied and (sql_val is not None or mine or pandas_sql):
            if sql_val is None:                      # SQL 을 못 읽었다 — SQL 이 들어갈 인자를 골라 식 그대로
                a_node, v = self._sql_arg(node, args, kws)
                if a_node is None or v is None:
                    if not mine:
                        return Val("df", deps=union(args) | union(kws.values()))
                    sql_val = S("")
                else:
                    path = v.path if v.kind in ("path", "file") else (v.const() or "")
                    if path.lower().endswith(SQL_FILE_EXT) and "\n" not in path:   # SQL 파일 경로를 받는 호출 (run_file("a.sql"))
                        fv = self.read_sql_file(path, a_node)
                        v = fv if fv.is_str else v
                    sql_val = v if v.is_str else self._ph(a_node, env, v)
                sql_node = a_node
            others = [(a, v) for a, v in zip(node.args, args) if a is not sql_node] + \
                     [(k.value, kws.get(k.arg or "**")) for k in node.keywords if k.value is not sql_node]
            return self.make_query(node, env, sql_val, _seg(self.source, func, 36), others, kws)
        # 그 밖: 의존만 이어 준다 (df 에서 나온 값은 df 로)
        deps = union(args) | union(kws.values()) | (recv.deps if recv is not None else frozenset())
        if recv is not None and recv.kind == "mod":
            return Val("mod", module=f"{recv.module}.{attr}()", deps=deps)
        if fval is not None and fval.kind == "mod":
            return Val("mod", module=f"{fval.module}()", deps=deps)
        kind = "df" if (recv is not None and recv.kind == "df") else "other"
        return Val(kind, deps=deps)

    @staticmethod
    def _sql_arg(node: ast.Call, args: List[Val], kws: Dict[str, Val]) -> Tuple[Optional[ast.AST], Optional[Val]]:
        """SQL 을 못 읽은 쿼리 호출에서 SQL 이 들어갈 인자 — sql= 류 이름 → 첫 인자 → 이름에 sql · query 가 든 인자"""
        named = [k for k in node.keywords if k.arg and kws.get(k.arg) is not None and kws[k.arg].kind != "num"]
        k = next((k for k in named if k.arg in SQL_KWARGS), None)
        if k is not None:
            return k.value, kws[k.arg]  # type: ignore[index]
        if node.args:
            return node.args[0], args[0]
        k = next((k for k in named if SQL_KWARG_RE.search(k.arg or "")), None)
        return (k.value, kws[k.arg]) if k is not None else (None, None)  # type: ignore[index]

    def _module_call(self, module: str, attr: str, full: str) -> bool:
        """설정한 사내 패키지에서 나온 이름의 SQL 호출인가"""
        if not module or not self.modules:
            return False
        root = module.replace("()", "")
        for m in self.modules:
            if root == m or root.startswith(m + "."):
                last = (full or module).replace("()", "").split(".")[-1]
                return last in self.calls
        return False

    def read_sql_file(self, path: str, node: ast.AST) -> Val:
        if not path:
            return Val()
        cand = path if os.path.isabs(path) else (os.path.join(self.dir, path) if self.dir else "")
        if not cand or not cand.lower().endswith(SQL_FILE_EXT):
            return Val()
        cand = os.path.normpath(cand)       # sql/a.sql · ./sql//a.sql · (Windows) sql\a.sql 는 같은 파일
        try:
            if os.path.getsize(cand) > MAX_SQL_FILE:
                self.warnings.append(f"{path}: 1 MB 가 넘어 읽지 않았습니다")
                return Val()
            text = read_text_file(cand)
        except OSError:
            self.warnings.append(f"L{getattr(node, 'lineno', 0)} {path}: SQL 파일을 찾지 못했습니다")
            return Val()
        rel = os.path.relpath(cand, self.dir) if self.dir else path
        if all(os.path.normcase(f) != os.path.normcase(cand) for f in self.sql_files):     # Windows 는 대소문자도 같은 파일
            self.sql_files.append(cand)
        return S(text, src="file:" + rel.replace("\\", "/"))

    def inline_call(self, fname: str, node: ast.Call, args: List[Val], kws: Dict[str, Val], env: Env,
                    self_val: Optional[Val]) -> Val:
        fdef, cls = self.funcs[fname]
        self.called.add(fname)
        if len(self.inline) >= MAX_INLINE or any(n == fname for n, _, _ in self.inline):
            return Val(deps=union(args) | union(kws.values()))
        fenv = Env(self.module_env)
        a = fdef.args  # type: ignore[attr-defined]
        params = [p.arg for p in getattr(a, "posonlyargs", [])] + [p.arg for p in a.args]
        defaults = [None] * (len(params) - len(a.defaults)) + list(a.defaults)
        bound = list(args)
        if cls and params:                                     # 메서드: self
            fenv.set(params[0], self_val or Val("obj", module=cls))
            params, defaults = params[1:], defaults[1:]
        for i, p in enumerate(params):
            if i < len(bound):
                fenv.set(p, bound[i])
            elif p in kws:
                fenv.set(p, kws[p])
            elif defaults[i] is not None:
                fenv.set(p, self.expr(defaults[i], self.module_env))
            else:
                fenv.set(p, Val("other", module=p))
        for k, d in zip(a.kwonlyargs, a.kw_defaults):
            fenv.set(k.arg, kws.get(k.arg) or (self.expr(d, self.module_env) if d is not None else Val()))
        if a.vararg:
            fenv.set(a.vararg.arg, Val("list", items=bound[len(params):], deps=union(bound[len(params):])))
        if a.kwarg:
            fenv.set(a.kwarg.arg, Val("dict", items=dict(kws), deps=union(kws.values())))
        self.inline.append((fname.split(".")[-1], node.lineno, getattr(node, "end_lineno", node.lineno) or node.lineno))
        self.returns.append([])
        saved_scope, saved_nodes, mark = self.scope, self.stmt_nodes, len(self.created)
        self.scope = f"def {fname}"
        try:
            self.block(fdef.body, fenv)  # type: ignore[attr-defined]
        finally:
            self.scope = saved_scope
            rets = self.returns.pop()
            self.inline.pop()
            self.stmt_nodes = saved_nodes + self.created[mark:]     # 펼친 함수가 만든 노드도 부른 문장의 것
        if not rets:
            return Val("none")
        first = next((r for r in rets if r.is_str), rets[0])
        kind = "df" if any(r.kind == "df" for r in rets) else first.kind
        return Val(kind, first.parts, deps=union(rets), items=first.items, module=first.module, phs=first.phs,
                   src=first.src)

    # ── 노드 만들기
    def make_query(self, node: ast.Call, env: Env, sql_val: Val, call: str, others: List[Tuple[ast.AST, Optional[Val]]],
                   kws: Dict[str, Val]) -> Val:
        if self._full():
            return Val("df", deps=sql_val.deps)
        qid = self._new_id("q", self.queries)
        text = sql_val.text() if sql_val.parts is not None else ""
        known = {t for k, t in (sql_val.parts or []) if k == "p"}
        parsed = flow1_sql.parse_sql(text, known) if text else {"stmts": [], "reads": [], "writes": [], "error": ""}
        dynamic = sql_val.parts is None or (len(sql_val.parts) == 1 and sql_val.parts[0][0] == "p")
        params = []
        for name in sorted(known, key=lambda n: text.find("{" + n + "}")):
            info = sql_val.phs.get(name, {"expr": name, "deps": [], "line": 0})
            params.append({"name": name, "expr": info.get("expr", name), "deps": list(info.get("deps", [])),
                           "line": info.get("line", 0)})
        for a_node, v in others:
            if v is not None and v.deps:
                params.append({"name": _dotted(a_node) or "args", "expr": _seg(self.source, a_node, 60),
                               "deps": sorted(v.deps), "line": getattr(a_node, "lineno", 0), "arg": True})
        q: Dict[str, Any] = dict(self._where(node), seq=len(self.created), id=qid, n=len(self.queries) + 1, call=call, var="",
                                 sql=text, sql_src="dynamic" if dynamic else (sql_val.src or "literal"),
                                 dynamic=dynamic, params=params, parsed=parsed,
                                 reads=parsed["reads"], writes=parsed["writes"])
        if q["sql_src"].startswith("file:"):
            q["sql_file"] = q["sql_src"][5:]
        self.queries.append(q)
        self.count += 1
        self.stmt_nodes.append(qid)
        self.created.append(qid)
        for p in params:
            for d in p["deps"]:
                self._edge(d, qid, "param", p["name"])
        return Val("df", deps={qid})

    def _input_label(self, a_node: Optional[ast.AST], v: Optional[Val], env: Env) -> str:
        if a_node is None:
            return ""
        return _dotted(a_node) or self._ph_name(a_node, env)

    def make_op(self, node: ast.Call, env: Env, kind: str, args: List[Val], kws: Dict[str, Val],
                recv: Optional[Val]) -> Val:
        if self._full():
            return Val("df", deps=union(args) | (recv.deps if recv is not None else frozenset()))
        oid = self._new_id("j", self.ops)
        func = node.func
        inputs: List[Tuple[Optional[ast.AST], Val, str]] = []
        if kind == "concat":
            if recv is not None:
                inputs.append((func.value if isinstance(func, ast.Attribute) else None, recv, "+"))  # type: ignore[union-attr]
            first = node.args[0] if node.args else None
            v0 = args[0] if args else kws.get("objs")
            if isinstance(first, (ast.List, ast.Tuple)) and v0 is not None and isinstance(v0.items, list):
                for e, v in zip(first.elts, v0.items):
                    inputs.append((e, v, "+"))
            elif first is not None and v0 is not None:
                inputs.append((first, v0, "+"))
        else:
            if recv is not None:
                inputs.append((func.value if isinstance(func, ast.Attribute) else None, recv, "L"))  # type: ignore[union-attr]
                right_node = node.args[0] if node.args else next((k.value for k in node.keywords if k.arg == "right"), None)
                inputs.append((right_node, args[0] if args else kws.get("right", Val()), "R"))
            else:
                l_node = node.args[0] if node.args else next((k.value for k in node.keywords if k.arg == "left"), None)
                r_node = node.args[1] if len(node.args) > 1 else next((k.value for k in node.keywords if k.arg == "right"), None)
                inputs.append((l_node, args[0] if args else kws.get("left", Val()), "L"))
                inputs.append((r_node, args[1] if len(args) > 1 else kws.get("right", Val()), "R"))

        def const_list(v: Optional[Val]) -> List[str]:
            if v is None:
                return []
            if v.kind == "list" and isinstance(v.items, list):
                return [x.const() or "?" for x in v.items]
            c = v.const()
            return [c] if c is not None else ([v.text()] if v.is_str else [])

        how = (kws.get("how").const() if kws.get("how") is not None else None) or \
              ("left" if kind == "join" else ("" if kind == "concat" else "inner"))
        on = const_list(kws.get("on"))
        if kind == "join" and not on and len(args) > 1:
            on = const_list(args[1])
        op = dict(self._where(node), seq=len(self.created), id=oid, n=len(self.ops) + 1, kind=kind, var="", how=how.lower(), on=on,
                  left_on=const_list(kws.get("left_on")), right_on=const_list(kws.get("right_on")),
                  index=bool((kws.get("left_index") or Val()).const() or (kws.get("right_index") or Val()).const()),
                  call=_seg(self.source, node.func, 36), inputs=[])
        if kind == "concat":
            ax = kws.get("axis")
            op["how"] = "axis=1" if ax is not None and ax.const() in ("1", "columns") else ""
        deps: Set[str] = set()
        for a_node, v, side in inputs:
            label = self._input_label(a_node, v, env)
            op["inputs"].append({"side": side, "label": label, "deps": sorted(v.deps)})
            for d in sorted(v.deps):
                self._edge(d, oid, "df", label, side)
            deps |= v.deps
        self.ops.append(op)
        self.count += 1
        self.stmt_nodes.append(oid)
        self.created.append(oid)
        return Val("df", deps={oid})

    def make_input(self, node: ast.Call, env: Env, reader: str, args: List[Val], kws: Dict[str, Val]) -> Val:
        if self._full():
            return Val("df")
        iid = self._new_id("i", self.inputs)
        target = ""
        if args:
            target = args[0].const() or (args[0].path if args[0].kind == "path" else "") or _seg(self.source, node.args[0], 40)
        self.inputs.append(dict(self._where(node), seq=len(self.created), id=iid, n=len(self.inputs) + 1, kind=reader, target=target,
                                var="", call=_seg(self.source, node.func, 36)))
        self.count += 1
        self.stmt_nodes.append(iid)
        self.created.append(iid)
        return Val("df", deps={iid} | union(args))

    def make_output(self, node: ast.Call, env: Env, sink: str, recv: Val, args: List[Val], kws: Dict[str, Val]) -> Val:
        if self._full():
            return Val("none")
        oid = self._new_id("o", self.outputs)
        target = ""
        tnode = node.args[0] if node.args else next((k.value for k in node.keywords if k.arg in ("path_or_buf", "excel_writer", "path", "name")), None)
        if tnode is not None:
            tv = self.expr(tnode, env)
            target = tv.const() or (tv.path if tv.kind == "path" else "") or (tv.text() if tv.is_str else _seg(self.source, tnode, 40))
        label = _dotted(node.func.value) if isinstance(node.func, ast.Attribute) else ""  # type: ignore[union-attr]
        out = dict(self._where(node), seq=len(self.created), id=oid, n=len(self.outputs) + 1, kind=sink, target=target, var=label,
                   call=_seg(self.source, node.func, 36))
        if sink == "to_sql" and target:
            schema = (kws.get("schema") or Val()).const()
            name = f"{schema}.{target}" if schema else target
            out["table"] = {"key": name.lower(), "name": name}
        self.outputs.append(out)
        self.count += 1
        self.stmt_nodes.append(oid)
        self.created.append(oid)
        for d in sorted(recv.deps):
            self._edge(d, oid, "df", label)
        return Val("none")

    # ── 부르지 않은 함수 · 메서드
    def uncalled(self) -> None:
        for fname, (fdef, cls) in list(self.funcs.items()):
            if fname in self.called or self._full():
                continue
            fenv = Env(self.module_env)
            a = fdef.args  # type: ignore[attr-defined]
            names = [p.arg for p in getattr(a, "posonlyargs", [])] + [p.arg for p in a.args] + [k.arg for k in a.kwonlyargs]
            for i, p in enumerate(names):
                fenv.set(p, Val("obj", module=cls) if cls and i == 0 else Val("other", module=p))
            saved = self.scope
            self.scope = f"def {fname}"
            self.returns.append([])
            try:
                self.block(fdef.body, fenv)  # type: ignore[attr-defined]
            finally:
                self.returns.pop()
                self.scope = saved


# ─────────────────────────────────────────────────────────────── 04 결과

def _stats(res: Dict[str, Any]) -> Dict[str, int]:
    tables: Set[str] = set()
    joins = conds = 0
    for q in res["queries"]:
        for r in q["reads"] + q["writes"]:
            tables.add(r["key"])
        for st in q["parsed"]["stmts"]:
            sel = st.get("select")
            if sel:
                joins += sum(1 for s in sel["sources"] if s.get("join"))
                conds += len(sel["where"]) + len(sel["having"])
            conds += len(st.get("where") or [])
            for s in (st.get("using") or {}).get("sources", []):
                joins += 1
    for o in res["outputs"]:
        if o.get("table"):
            tables.add(o["table"]["key"])
    joins += sum(1 for o in res["ops"] if o["kind"] in ("merge", "join"))
    return {"queries": len(res["queries"]), "tables": len(tables), "joins": joins, "conds": conds,
            "ops": len(res["ops"]), "inputs": len(res["inputs"]), "outputs": len(res["outputs"]),
            "params": sum(1 for e in res["edges"] if e["kind"] == "param")}


def empty_result(path: str, name: str, kind: str) -> Dict[str, Any]:
    return {"format": FORMAT, "file": path, "name": name, "kind": kind, "error": "", "warnings": [], "lines": 0,
            "cells": [], "queries": [], "ops": [], "inputs": [], "outputs": [], "edges": [], "sql_files": [],
            "stats": {}}


def scan_text(text: str, name: str, cfg: Optional[Dict[str, Any]] = None, kind: str = "py",
              path: str = "") -> Dict[str, Any]:
    """코드 글 → 결과 dict. 예외를 던지지 않는다 (문법 오류는 error 에)"""
    cfg = cfg or {}
    res = empty_result(path, name, kind)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if kind == "sql":
        sc = Scanner(cfg, path, text, kind)
        v = S(text)
        call = ast.Call(func=ast.Name(id="SQL", ctx=ast.Load()), args=[], keywords=[])
        call.lineno, call.end_lineno, call.col_offset = 1, max(1, text.count("\n") + 1), 0  # type: ignore[attr-defined]
        sc.make_query(call, sc.module_env, v, "SQL", [], {})
        res.update(queries=sc.queries, lines=text.count("\n") + 1)
        res["stats"] = _stats(res)
        return res
    cells: List[Dict[str, Any]] = []
    if kind == "ipynb":
        try:
            cells = notebook_cells(text)
        except (ValueError, TypeError, KeyError, IndexError) as e:
            res["error"] = f"노트북(JSON)을 읽지 못했습니다: {e}"
            res["stats"] = _stats(res)
            return res
        source = "\n".join(c["code"] for c in cells)
    else:
        source = text
    sc = Scanner(cfg, path, source, kind)
    res["lines"] = source.count("\n") + 1
    if kind == "ipynb":
        sc.cell_lines = [(c["n"], c["line"]) for c in cells]
        res["cells"] = [[c["n"], c["line"], c["code"].count("\n") + 1] for c in cells]
        env = sc.module_env
        for c in cells:
            if c["sql"] is not None:        # %%sql 셀
                call = ast.Call(func=ast.Name(id="SQL", ctx=ast.Load()), args=[], keywords=[])
                call.lineno, call.col_offset = c["line"], 0  # type: ignore[attr-defined]
                call.end_lineno = c["line"] + c["code"].count("\n")  # type: ignore[attr-defined]
                v = sc.make_query(call, env, S(c["sql"], "cell"), "%%sql", [], {})
                if c["var"]:
                    env.set(c["var"], v)
                    sc.queries[-1]["var"] = c["var"]
                continue
            try:
                tree = ast.parse(c["code"] or "\n", filename=name)
            except SyntaxError as e:
                sc.warnings.append(f"셀 {c['n']}: 문법 오류 ({e.msg}, {(e.lineno or 1)}번째 줄) — 이 셀은 건너뜀")
                continue
            ast.increment_lineno(tree, c["line"] - 1)
            sc.source = source
            sc.block(tree.body, env)
    else:
        try:
            tree = ast.parse(source, filename=name)
        except SyntaxError as e:
            res["error"] = f"문법 오류: {e.msg} ({e.lineno}번째 줄)"
            res["stats"] = _stats(res)
            return res
        except (ValueError, MemoryError, RecursionError) as e:
            res["error"] = f"코드를 읽지 못했습니다: {e.__class__.__name__}"
            res["stats"] = _stats(res)
            return res
        sc.block(tree.body, sc.module_env)
    sc.uncalled()
    res.update(queries=sc.queries, ops=sc.ops, inputs=sc.inputs, outputs=sc.outputs, edges=sc.edges,
               warnings=sc.warnings, sql_files=sc.sql_files)
    res["stats"] = _stats(res)
    return res


def kind_of(path: str) -> str:
    low = path.lower()
    if low.endswith(".ipynb"):
        return "ipynb"
    if low.endswith((".sql", ".hql")):
        return "sql"
    return "py"


def scan_file(path: str, cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    path = os.path.abspath(path)
    name = os.path.basename(path)
    kind = kind_of(path)
    try:
        text = read_text_file(path)
    except OSError as e:
        res = empty_result(path, name, kind)
        res["error"] = f"파일을 읽지 못했습니다: {e.strerror or e}"
        res["stats"] = _stats(res)
        return res
    return scan_text(text, name, cfg, kind, path)
