# -*- coding: utf-8 -*-
"""flow1_graph — 흐름도: 카드 줄 · 층 배치 · 직각 간선 · SVG · 글 요약 (Flow–1 · 표준 라이브러리만 · Python 3.8+)

  build(results, detail=2, runs=None) → 그래프 dict {nodes, edges, width, height, stats, files}
  svg(graph, standalone=False, theme="dark", font_b64="") → SVG 글 (화면 · --svg 가 같은 것을 쓴다)
  summary(result) → --scan 글 요약 (사내 LLM · 사람이 결과를 글로 확인하는 곳)

픽셀은 8px 칸 기준이다. 글자 폭은 내장 폰트(GNU Unifont 15.1)와 똑같이 센다 — 반각 8px · 전각 16px.
그래서 카드 크기 · 자르기(…)를 서버에서 정확히 정하고, 화면은 받은 SVG 를 그대로 붙인다.
디자인 원칙 · 색은 docs/DESIGN.md, 이 앱의 자리 · 치수는 docs/GUIDE.md › 07 화면 규격.
"""
import bisect
import html
import re
import unicodedata
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import flow1_sql

# ─────────────────────────────────────────────────────────────── 01 치수

CELL = 8                    # 반각 글자 한 칸
ROW = 20                    # 카드 한 줄 (글자 16 + 위아래 2)
HEAD = 24                   # 카드 머리
PAD = 8                     # 카드 아래 여백
LBL = 64                    # 줄 이름 칸 (SELECT · FROM · …) — 왼쪽 여백 8 포함
WIDTH = {1: 288, 2: 400, 3: 480}     # 쿼리 카드 폭 (① 상세 1 · 2 · 3)
OP_W = 232                  # 병합 카드 폭
PILL_H = 24                 # 테이블 · 파일 알약 높이
PILL_MIN, PILL_MAX = 96, 320
GAP_Y = 16                  # 같은 열의 노드 사이
GAP_X = 48                  # 열 사이 최소
TRACK = 8                   # 열 사이 간선 트랙 간격
MARGIN = 32
MAX_SELECT_ROWS = 2         # 상세 2 에서 SELECT 줄 수
MAX_WHERE_ROWS = 5          # 상세 2 에서 WHERE 줄 수
BASE = 16                   # 줄 안의 글자 기준선 (행 위에서) — Unifont ascent 14 + 여백 2

# Unifont 15.1 에서 전각(16px)인데 유니코드 East Asian Width 는 W/F 가 아닌 글자 · 그 반대 (내장 폰트에서 뽑음)
_WIDE_EXTRA = (
    "AD 2057 20B9 210E-210F 212E 213A-213D 213F-2140 2145-2149 214C 214F 2182 2188 219C-219D 21F4 21F9-21FC 21FF "
    "22B6-22B8 22D8-22D9 22F2-22F3 22F5-22F6 22F9-22FB 22FD 22FF-2300 2316 232C-2335 237B-237E 2381-2394 2397-239A "
    "23B2-23B6 23C0-23CA 23CD-23CE 23D4-23D9 23DB-23E7 23ED-23EF 23F1-23F2 23F4-23FF 2460-24FF 25EF 2603 2605-2606 "
    "2610-2612 2616-2619 2622-2624 262B-262C 262F-2637 2672-267E 2680-268F 2692 2694-26A0 26A2-26A7 26A9 26AD-26B1 "
    "26B6 26BF-26C3 26C6-26CD 26CF-26D3 26D5-26E1 26E3-26E9 26EB-26F1 26F4 26F6-26F9 26FB-26FC 26FE-2704 2706-2709 "
    "270C-2727 2729-274B 274D 274F-2752 2756 2758-2767 2776-2794 2798-27AF 27B1-27BE 27DC 29B8 2AE3-2AE5 2B00-2B05 "
    "2B08-2B0C 2B0E-2B1A 2B1F-2B24 2B2C-2B2D 2B30 2B32-2B4D 2B51-2B54 2B56-2B73 2B76-2B95 2B97-2BC8 2BCA-2BFE 3248-324F")
_NARROW_EXTRA = "231A-231B 25FD-25FE 2614 2648-2653 26A1 26AA-26AB 27B0"


def _ranges(spec: str) -> Tuple[List[int], List[int]]:
    lo, hi = [], []
    for part in spec.split():
        a, _, b = part.partition("-")
        lo.append(int(a, 16))
        hi.append(int(b or a, 16))
    return lo, hi


_WIDE = _ranges(_WIDE_EXTRA)
_NARROW = _ranges(_NARROW_EXTRA)


def _in(r: Tuple[List[int], List[int]], o: int) -> bool:
    i = bisect.bisect_right(r[0], o) - 1
    return i >= 0 and o <= r[1][i]


def cw(ch: str) -> int:
    """글자 폭 (칸) — 1 = 8px · 2 = 16px"""
    o = ord(ch)
    if o < 0x1100:
        return 2 if o == 0xAD else 1
    if _in(_NARROW, o):
        return 1
    if _in(_WIDE, o):
        return 2
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def cells(s: str) -> int:
    return sum(cw(c) for c in s)


def clip(s: str, n: int) -> str:
    """n 칸에 맞게 — 넘치면 … (한 칸)"""
    if n <= 0:
        return ""
    if cells(s) <= n:
        return s
    out, w = [], 0
    for c in s:
        k = cw(c)
        if w + k > n - 1:
            break
        out.append(c)
        w += k
    return "".join(out) + "…"


def one_line(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def snap(v: float) -> int:
    return int(round(v / CELL)) * CELL


def up8(v: float) -> int:
    return -(-int(v) // CELL) * CELL


# ─────────────────────────────────────────────────────────────── 02 카드 줄

JOIN_LBL = {"INNER": "JOIN", "LEFT": "LEFT", "RIGHT": "RIGHT", "FULL": "FULL", "CROSS": "CROSS", ",": ",",
            "LEFT SEMI": "SEMI", "LEFT ANTI": "ANTI", "SEMI": "SEMI", "ANTI": "ANTI", "USING": "USING"}
STMT_LBL = {"insert": "INSERT", "create": "CREATE", "update": "UPDATE", "delete": "DELETE", "merge": "MERGE",
            "drop": "DROP", "truncate": "TRUNC"}


def join_label(j: str) -> str:
    if not j:
        return "FROM"
    if j in JOIN_LBL:
        return JOIN_LBL[j]
    if j.startswith("LATERAL"):
        return "LATERAL"
    if j.startswith("NATURAL"):
        return "NATURAL"
    if "APPLY" in j:
        return "APPLY"
    return j.split()[0][:7]


def row(lbl: str, text: str, kind: str, anchor: str = "", ph: Sequence[str] = (), segs: Optional[List[List[str]]] = None,
        cls: str = "") -> Dict[str, Any]:
    r: Dict[str, Any] = {"lbl": lbl, "text": one_line(text), "kind": kind, "anchor": anchor, "ph": list(ph)}
    if segs is not None:
        r["segs"] = segs
    if cls:
        r["cls"] = cls
    return r


def _sel_tables(sel: Optional[Dict[str, Any]]) -> List[str]:
    """SELECT 안(서브쿼리 · CTE 포함)에서 읽는 이름들 — 줄 요약용"""
    out: List[str] = []

    def walk(s: Optional[Dict[str, Any]]) -> None:
        if not s:
            return
        for c in s.get("ctes", []):
            walk(c["select"])
        for src in s.get("sources", []):
            if src["kind"] in ("table", "cte") and src["name"] not in out:
                out.append(src["name"])
            if src["kind"] == "subquery":
                walk(src["select"])
        for key in ("where", "having"):
            for c in s.get(key, []):
                for sub in c["subs"]:
                    walk(sub)
        for u in s.get("union", []):
            walk(u["select"])

    walk(sel)
    return out


def _source_segs(s: Dict[str, Any]) -> Tuple[str, List[List[str]]]:
    alias = (" " + s["alias"]) if s.get("alias") else ""
    if s["kind"] in ("table", "cte"):
        segs = [[s["name"], "tb" if s["kind"] == "table" else "t"], [alias, "t"]]
        if s["kind"] == "cte":
            segs.append([" WITH", "d"])
        return s["name"] + alias, segs
    if s["kind"] == "subquery":
        inner = ", ".join(_sel_tables(s["select"])) or "…"
        text = f"(SELECT … {inner}){alias}"
        return text, [["(SELECT … ", "d"], [inner, "tb"], [")" + alias, "t"]]
    return s["text"], [[s["text"], "t"]]


def _cond_row(lbl: str, c: Dict[str, Any], kind: str, anchor: str) -> Dict[str, Any]:
    return row(lbl, c["text"], kind, anchor, c.get("params", []) + c.get("binds", []),
               cls="j" if c.get("kind") == "join" else "")


def _pack(items: List[str], width: int, max_rows: int) -> List[str]:
    """쉼표로 이어 여러 줄에 담기 — max_rows 를 넘으면 마지막 줄 끝에 '+n'"""
    lines: List[str] = []
    cur = ""
    k = 0
    while k < len(items):
        it = items[k]
        cand = it if not cur else cur + ", " + it
        if cells(cand) <= width or not cur:
            cur = cand
            k += 1
            continue
        lines.append(cur + ",")
        cur = ""
        if max_rows and len(lines) >= max_rows:
            break
    if cur and (not max_rows or len(lines) < max_rows):
        lines.append(cur)
    left = len(items) - k
    if left > 0 and lines:
        tail = f" +{left}"
        lines[-1] = clip(lines[-1].rstrip(","), width - cells(tail)) + tail
    return lines


def select_rows(sel: Dict[str, Any], st: Dict[str, Any], n: int, detail: int, width: int) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    ctes = st.get("ctes", []) + sel.get("ctes", [])
    if detail >= 3:
        for c in ctes:
            inner = ", ".join(_sel_tables(c["select"])) or "…"
            rows.append(row("WITH", f"{c['name']} ← {inner}", "with", f"with:{n}:{c['key']}",
                            segs=[[c["name"], "t"], [" ← ", "d"], [inner, "tb"]]))
    if detail >= 2:
        items = []
        for c in sel["columns"]:
            if detail >= 3:
                items.append(c["expr"] + (f" AS {c['alias']}" if c["alias"] else ""))
            else:
                items.append(c["alias"] or c["expr"])
        if sel.get("distinct") and items:
            items[0] = "DISTINCT " + items[0]
        if items:
            packed = _pack(items, width, MAX_SELECT_ROWS if detail == 2 else 0)
            for k, line in enumerate(packed):
                ph = [p for c in sel["columns"] for p in c.get("params", [])]
                rows.append(row("SELECT" if k == 0 else "", line, "select", f"select:{n}:0" if k == 0 else "", ph))
    for i, s in enumerate(sel["sources"]):
        text, segs = _source_segs(s)
        rows.append(row(join_label(s["join"]), text, "src", f"src:{n}:{i}", segs=segs,
                        cls="jn" if s["join"] else ""))
        if detail >= 2:
            if s.get("using"):
                rows.append(row("USING", ", ".join(s["using"]), "on"))
            conds = s.get("on") or []
            if conds and detail == 2:
                rows.append(row("ON", " AND ".join(c["text"] for c in conds), "on", "",
                                [p for c in conds for p in c.get("params", []) + c.get("binds", [])]))
            elif conds:
                for k, c in enumerate(conds):
                    rows.append(_cond_row("ON" if k == 0 else "AND", c, "on", ""))
    if detail >= 2:
        where = sel["where"]
        limit = MAX_WHERE_ROWS if detail == 2 else len(where)
        for i, c in enumerate(where[:limit]):
            lbl = "QUALIFY" if c.get("kind") == "qualify" else ("WHERE" if i == 0 else "AND")
            rows.append(_cond_row(lbl, c, "where", f"where:{n}:{i}"))
        if len(where) > limit:
            rows.append(row("", f"+ 조건 {len(where) - limit}개 더", "more", f"where+:{n}",
                            [p for c in where[limit:] for p in c.get("params", [])]))
        if sel["group"]:
            rows.append(row("GROUP", ", ".join(sel["group"]), "group"))
        if sel["having"]:
            if detail == 2:
                rows.append(row("HAVING", " AND ".join(c["text"] for c in sel["having"]), "having", f"having:{n}:*",
                                [p for c in sel["having"] for p in c.get("params", [])]))
            else:
                for i, c in enumerate(sel["having"]):
                    rows.append(_cond_row("HAVING" if i == 0 else "AND", c, "having", f"having:{n}:{i}"))
        if sel["order"]:
            tail = f" · LIMIT {sel['limit']}" if sel["limit"] else ""
            rows.append(row("ORDER", ", ".join(sel["order"]) + tail, "order"))
        elif sel["limit"]:
            rows.append(row("LIMIT", sel["limit"], "order"))
        if detail >= 3:
            for e in sel.get("extra", []):
                rows.append(row("", e, "extra"))
    for k, u in enumerate(sel.get("union", [])):
        op = u["op"].split()
        inner = ", ".join(_sel_tables(u["select"])) or "…"
        rest = (" ".join(op[1:]) + " · ") if len(op) > 1 else ""
        rows.append(row(op[0][:7], f"{rest}SELECT … {inner}", "union", f"union:{n}:{k}",
                        segs=[[rest + "SELECT … ", "d"], [inner, "tb"]]))
    return rows


def query_rows(q: Dict[str, Any], detail: int, width: int = 0) -> List[Dict[str, Any]]:
    """쿼리 카드의 줄. width = 글 칸 수 (0 = 자르지 않음 · --scan)"""
    width = width or 10 ** 6
    stmts = q["parsed"]["stmts"]
    ph_all = [p["name"] for p in q["params"]]
    if q["dynamic"] or not stmts:
        text = q["sql"] or "(SQL 을 코드에서 찾지 못함)"
        return [row("SQL", text + " — 실행할 때 정해짐" if q["dynamic"] else text, "dyn", "", ph_all)]
    rows: List[Dict[str, Any]] = []
    if detail >= 3 and q.get("via"):
        rows.append(row("VIA", q["via"], "via", cls="d"))
    elif detail >= 3 and q.get("scope"):
        rows.append(row("DEF", q["scope"][4:] + "() — 부르는 곳을 못 찾음", "via", cls="d"))
    for st in stmts:
        n = st["n"]
        if len(stmts) > 1:
            rows.append(row("SQL", f"{n + 1}/{len(stmts)}", "stmt", cls="d"))
        kind = st["kind"]
        if kind in STMT_LBL:
            note = f" ({st['note']})" if st.get("note") in ("VIEW", "TEMP") else ""
            rows.append(row(STMT_LBL[kind], st["target"] + note, "target", f"head:{n}",
                            segs=[[st["target"], "tb"], [note, "d"]], cls="jn"))
        if kind in ("other", "values"):
            rows.append(row("SQL", st["text"][:240], "other", "", ph_all))
            continue
        if kind == "update" and detail >= 2 and st.get("set"):
            rows.append(row("SET", ", ".join(st["set"]), "set"))
        for i, s in enumerate((st.get("using") or {}).get("sources", [])):
            text, segs = _source_segs(s)
            rows.append(row("USING" if kind == "merge" else "FROM", text, "src", f"using:{n}:{i}", segs=segs, cls="jn"))
            if detail >= 2 and s.get("on"):
                rows.append(row("ON", " AND ".join(c["text"] for c in s["on"]), "on"))
        if kind in ("update", "delete") and detail >= 2:
            for i, c in enumerate(st.get("where") or []):
                rows.append(_cond_row("WHERE" if i == 0 else "AND", c, "where", f"where:{n}:{i}"))
        if kind == "merge" and detail >= 3 and st.get("set"):
            rows.append(row("WHEN", st["set"][0], "set"))
        sel = st.get("select")
        if sel:
            rows += select_rows(sel, st, n, detail, width)
    return rows


def _all_selects(q: Dict[str, Any]) -> List[Dict[str, Any]]:
    """쿼리 안의 SELECT 전부 (CTE · 서브쿼리 · UNION 가지 포함)"""
    out: List[Dict[str, Any]] = []

    def walk(sel: Optional[Dict[str, Any]]) -> None:
        if not sel:
            return
        out.append(sel)
        for c in sel.get("ctes", []):
            walk(c["select"])
        for x in sel.get("sources", []):
            if x["kind"] == "subquery":
                walk(x["select"])
            for c in x.get("on", []):
                for sub in c["subs"]:
                    walk(sub)
        for k in ("where", "having"):
            for c in sel.get(k, []):
                for sub in c["subs"]:
                    walk(sub)
        for sub in sel.get("subs", []):
            walk(sub["select"])
        for u in sel.get("union", []):
            walk(u["select"])

    for st in q["parsed"]["stmts"]:
        for c in st.get("ctes", []):
            walk(c["select"])
        walk(st.get("select"))
        for x in (st.get("using") or {}).get("sources", []):
            if x["kind"] == "subquery":
                walk(x["select"])
    return out


def columns_of(q: Dict[str, Any], key: str) -> List[str]:
    """쿼리 q 가 테이블 key 에서 쓰는 컬럼 — 별칭.컬럼 · 테이블이 하나뿐이면 앞이 없는 컬럼도. * 는 '*'"""
    cols: List[str] = []

    def refs_of(text: str) -> List[str]:
        return flow1_sql.col_refs([t for t in flow1_sql.tokens(text) if t.kind not in ("ws", "com")])

    for sel in _all_selects(q):
        mine = [x for x in sel["sources"] if x["kind"] == "table" and x["key"] == key]
        if not mine:
            continue
        names = {(x["alias"] or x["name"].split(".")[-1]).lower() for x in mine} | {x["name"].lower() for x in mine}
        single = len(sel["sources"]) == 1
        refs: List[str] = []
        for c in sel["columns"]:
            refs += c["cols"]
            if c["star"] and (c["expr"] == "*" and single or c["expr"][:-2].lower() in names):
                refs.append("*")
        for x in sel["sources"]:
            for c in x["on"]:
                refs += c["cols"]
            refs += [f"{(mine[0]['alias'] or mine[0]['name'])}.{u}" for u in x.get("using", []) if x in mine]
        for c in sel["where"] + sel["having"]:
            refs += c["cols"]
        for t in sel["group"] + sel["order"]:
            refs += refs_of(t)
        for r in refs:
            if r == "*":
                name = "*"
            else:
                parts = r.split(".")
                if len(parts) >= 2 and ".".join(parts[:-1]).lower() in names:
                    name = parts[-1]
                elif len(parts) == 1 and single:
                    name = parts[0]
                else:
                    continue
            if name not in cols:
                cols.append(name)
    return cols


# ─────────────────────────────────────────────────────────────── 03 그래프 만들기

def _run_text(run: Dict[str, Any]) -> Tuple[str, str]:
    """실행 기록 한 줄 → (글, 상태 class)"""
    state = run.get("state")
    if state == "busy":
        return "◐ 실행 중", "busy"
    if state == "err":
        return "× " + (run.get("err") or "오류"), "err"
    if state == "ok":
        parts = [fmt_ms(run.get("ms", 0))]
        if run.get("rows") is not None:
            parts.append(f"{run['rows']:,}행")
        if run.get("n", 1) > 1:
            parts.append(f"×{run['n']}")
        return "√ " + " · ".join(parts), "ok"
    return "○ 실행 기록 없음", "none"


def fmt_ms(ms: float) -> str:
    if ms < 1000:
        return f"{ms:.0f}ms"
    if ms < 60_000:
        return f"{ms / 1000:.1f}s"
    return f"{int(ms // 60000)}m{int(ms % 60000 / 1000):02d}s"


def _meta(item: Dict[str, Any], multi: bool, fname: str) -> str:
    where = (f"{fname}:" if multi else "L") + str(item["line"])
    if item.get("cell"):
        where = (f"{fname} " if multi else "") + f"셀{item['cell']}:{item['cell_line']}"
    if item.get("loop"):
        where += " · 반복"
    elif item.get("branch"):
        where += " · 조건부"
    return where


def build(results: Sequence[Dict[str, Any]], detail: int = 2, runs: Optional[Dict[str, Dict[str, Any]]] = None
          ) -> Dict[str, Any]:
    """스캔 결과(파일 하나 또는 여럿) → 흐름도 그래프 (배치까지). runs = {노드 id: 실행 요약}"""
    detail = min(3, max(1, int(detail or 2)))
    multi = len(results) > 1
    runs = runs or {}
    has_run = bool(runs)
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: List[Dict[str, Any]] = []
    order: List[str] = []
    qw = WIDTH[detail]
    text_cells = (qw - LBL - 8) // CELL

    def add(n: Dict[str, Any]) -> None:
        nodes[n["id"]] = n
        order.append(n["id"])

    cur: Dict[str, str] = {}             # 테이블 key → 지금 판 노드 id
    readers: Dict[str, Set[str]] = {}    # 테이블 노드 → 읽은 노드
    versions: Dict[str, int] = {}

    def table(key: str, name: str, writing: str = "") -> str:
        tid = cur.get(key)
        if tid is not None and writing and readers.get(tid):
            tid = None                   # 이미 읽힌 판에 다시 쓰면 새 판 (INSERT OVERWRITE t … FROM t)
        if tid is None:
            v = versions.get(key, 0) + 1
            versions[key] = v
            tid = f"t:{key}" + (f"#{v}" if v > 1 else "")
            dyn = "{" in name
            add({"id": tid, "kind": "table", "name": name, "key": key, "ver": v, "w": 0, "h": PILL_H,
                 "role": "source", "dyn": dyn, "readers": [], "writers": []})
            cur[key] = tid
            readers[tid] = set()
        return tid

    stats = {"queries": 0, "tables": 0, "joins": 0, "conds": 0, "ops": 0, "inputs": 0, "outputs": 0, "params": 0}
    files = []
    for fi, res in enumerate(results):
        pre = f"f{fi}:" if multi else ""
        fname = res.get("name") or f"파일{fi + 1}"
        files.append({"i": fi, "name": fname, "file": res.get("file", ""), "error": res.get("error", "")})
        for k in stats:
            stats[k] += int((res.get("stats") or {}).get(k, 0))
        items: List[Tuple[int, str, Dict[str, Any]]] = []
        for kind, bucket in (("query", "queries"), ("op", "ops"), ("input", "inputs"), ("output", "outputs")):
            for it in res.get(bucket, []):
                items.append((it.get("seq", 0), kind, it))
        items.sort(key=lambda x: (x[0], x[2]["line"]))
        for _seq, kind, it in items:
            nid = pre + it["id"]
            base = {"id": nid, "kind": kind, "file": fi, "ref": it["id"], "line": it["line"]}
            if kind == "query":
                rows = query_rows(it, detail, text_cells)
                run = runs.get(nid)
                title = it["var"] or it["call"]
                meta = _meta(it, multi, fname) if multi else (it["call"] + " · " if it["var"] else "") + _meta(it, multi, fname)
                h = up8(HEAD + len(rows) * ROW + (ROW if has_run else 0) + PAD)
                add(dict(base, w=qw, h=h, rows=rows, title=title, meta=meta, num=f"Q{it['n']:02d}",
                         dyn=it["dynamic"], loop=it.get("loop", False), run=run, has_run=has_run,
                         params=[p["name"] for p in it["params"]]))
                for r in it["reads"]:
                    tid = table(r["key"], r["name"])
                    readers[tid].add(nid)
                    nodes[tid]["readers"].append(nid)
                    anchors = []
                    for a in r["at"]:
                        key = f"{a[1]}:{a[0]}:{a[2] if len(a) > 2 else 0}"
                        if key not in anchors:
                            anchors.append(key)
                    edges.append({"from": tid, "to": nid, "kind": "read", "label": "", "tanchors": anchors})
                for w in it["writes"]:
                    tid = table(w["key"], w["name"], writing=nid)
                    nodes[tid]["writers"].append(nid)
                    edges.append({"from": nid, "to": tid, "kind": "write", "label": ""})
            elif kind == "op":
                rows = []
                for k, inp in enumerate(it["inputs"]):
                    rows.append(row(inp["side"], inp["label"] or "(식)", "in", f"in:{k}"))
                if it["kind"] == "concat":
                    rows.append(row("CONCAT", it["how"] or "위아래로", "how", cls="jn"))
                else:
                    if it["left_on"] or it["right_on"]:
                        keys = ", ".join(it["left_on"]) + " = " + ", ".join(it["right_on"])
                    elif it["on"]:
                        keys = "on " + ", ".join(it["on"])
                    else:
                        keys = "index" if it.get("index") else "공통 컬럼"
                    rows.append(row((it["how"] or "inner").upper()[:7], keys, "how", cls="jn"))
                h = up8(HEAD + len(rows) * ROW + PAD)
                add(dict(base, w=OP_W, h=h, rows=rows, title=it["var"] or it["kind"], num=f"J{it['n']:02d}",
                         meta=it["kind"].upper() + " · " + _meta(it, multi, fname), opkind=it["kind"]))
            else:
                label = f"{it['kind']} · {it['target'] or '?'}"
                w = min(PILL_MAX, max(PILL_MIN, up8(cells(label) * CELL + 16)))
                add(dict(base, w=w, h=PILL_H, label=label, title=it["kind"], target=it["target"],
                         meta=_meta(it, multi, fname), table=it.get("table")))
                if kind == "output" and it.get("table"):
                    tid = table(it["table"]["key"], it["table"]["name"], writing=nid)
                    nodes[tid]["writers"].append(nid)
                    edges.append({"from": nid, "to": tid, "kind": "write", "label": ""})
        for e in res.get("edges", []):
            a, b = pre + e["from"], pre + e["to"]
            if a in nodes and b in nodes:
                edges.append({"from": a, "to": b, "kind": e["kind"], "label": e.get("label", ""),
                              "side": e.get("side", "")})
    for n in nodes.values():
        if n["kind"] == "table":
            n["role"] = "temp" if n["writers"] and n["readers"] else ("sink" if n["writers"] else "source")
            label = n["name"] + (f" #{n['ver']}" if n["ver"] > 1 else "")
            n["label"] = label
            n["w"] = min(PILL_MAX, max(PILL_MIN, up8(cells(label) * CELL + 16)))
    stats["tables"] = len({n["key"] for n in nodes.values() if n["kind"] == "table"})
    for i, e in enumerate(edges):
        e["id"] = i
    g = {"nodes": [nodes[i] for i in order], "edges": edges, "detail": detail, "stats": stats, "files": files,
         "multi": multi, "has_run": has_run}
    ports(g)
    layout(g)
    return g


# ─────────────────────────────────────────────────────────────── 04 포트 (간선이 카드에 붙는 줄)

def _row_y(i: int) -> int:
    return HEAD + i * ROW + ROW // 2


def ports(g: Dict[str, Any]) -> None:
    """간선마다 시작 · 끝 높이(카드 위에서) — 테이블 간선은 그 테이블이 나오는 FROM · JOIN 줄에, 파라미터는 그 자리가 든 줄에"""
    nodes = {n["id"]: n for n in g["nodes"]}
    for e in g["edges"]:
        a, b = nodes[e["from"]], nodes[e["to"]]
        e["sy"] = a["h"] // 2 if a["kind"] in ("table", "input", "output") else HEAD // 2
        e["ty"] = HEAD // 2 if b["kind"] in ("query", "op") else b["h"] // 2
        rows = b.get("rows") or []
        e["join"] = b["kind"] == "op" and b.get("opkind") in ("merge", "join")
        if b["kind"] == "query" and e["kind"] == "read":
            e["ty"] = _anchor_y(rows, e.get("tanchors") or [])
            i = (e["ty"] - HEAD) // ROW
            e["join"] = 0 <= i < len(rows) and rows[i]["kind"] == "src" and rows[i].get("cls") == "jn"
        elif b["kind"] == "query" and e["kind"] == "param":
            idx = next((i for i, r in enumerate(rows) if e["label"] in r["ph"]), None)
            e["ty"] = _row_y(idx) if idx is not None else HEAD // 2
        elif b["kind"] == "op" and e["kind"] == "df":
            ref = next((k for k, r in enumerate(rows) if r["kind"] == "in" and r["text"] == (e["label"] or "(식)")
                        and (not e.get("side") or r["lbl"] == e["side"])), None)
            e["ty"] = _row_y(ref) if ref is not None else HEAD // 2


def _anchor_y(rows: List[Dict[str, Any]], anchors: List[str]) -> int:
    for key in anchors:
        kind, st, idx = (key.split(":") + ["", "", ""])[:3]
        for i, r in enumerate(rows):
            if not r["anchor"]:
                continue
            rk = r["anchor"].split(":")
            if rk[0] == kind and rk[1] == st and (len(rk) < 3 or rk[2] in (idx, "*")):
                return _row_y(i)
        if kind == "where":
            for i, r in enumerate(rows):
                if r["anchor"] == f"where+:{st}":
                    return _row_y(i)
    return HEAD // 2


# ─────────────────────────────────────────────────────────────── 05 배치 (층 · 순서 · 높이 · 트랙 · 열)

def _pava(targets: List[float], weights: List[float]) -> List[float]:
    """오름차순 제약의 가중 최소제곱 (pool adjacent violators)"""
    blocks: List[List[float]] = []          # [값, 무게, 개수]
    for t, w in zip(targets, weights):
        blocks.append([t, w, 1])
        while len(blocks) > 1 and blocks[-2][0] > blocks[-1][0]:
            b2 = blocks.pop()
            b1 = blocks.pop()
            wt = b1[1] + b2[1]
            blocks.append([(b1[0] * b1[1] + b2[0] * b2[1]) / wt, wt, b1[2] + b2[2]])
    out: List[float] = []
    for v, _w, c in blocks:
        out += [v] * int(c)
    return out


def layout(g: Dict[str, Any]) -> None:
    nodes = {n["id"]: n for n in g["nodes"]}
    ids = [n["id"] for n in g["nodes"]]
    preds: Dict[str, List[str]] = {i: [] for i in ids}
    succs: Dict[str, List[str]] = {i: [] for i in ids}
    for e in g["edges"]:
        if e["from"] != e["to"]:
            preds[e["to"]].append(e["from"])
            succs[e["from"]].append(e["to"])
    # 층: 위상 순서 → 가장 긴 경로. 순환이 남으면(원칙상 없음) 남은 것은 그 자리 순서대로
    indeg = {i: len(preds[i]) for i in ids}
    queue = [i for i in ids if indeg[i] == 0]
    topo: List[str] = []
    while queue:
        n = queue.pop(0)
        topo.append(n)
        for s in succs[n]:
            indeg[s] -= 1
            if indeg[s] == 0:
                queue.append(s)
    topo += [i for i in ids if i not in set(topo)]
    pos = {n: k for k, n in enumerate(topo)}
    layer: Dict[str, int] = {}
    for n in topo:
        layer[n] = max((layer[p] + 1 for p in preds[n] if p in layer and pos[p] < pos[n]), default=0)
    for n in topo:                       # 원천(읽기만 하는 테이블 · 파일)은 처음 쓰는 곳 바로 앞 열로
        if not preds[n] and succs[n]:
            layer[n] = max(0, min(layer[s] for s in succs[n]) - 1)
    # 읽기만 하는 테이블 · 파일이 여러 열의 쿼리에 쓰이면 쓰는 열마다 한 벌씩 — 열을 가로지르는 긴 선 · 교차가 사라진다
    # (쓰고 다시 읽는 임시 테이블은 나누지 않는다 — 그 선이 데이터의 흐름이다)
    rank0 = {n: k for k, n in enumerate(ids)}
    for n in list(ids):
        node = nodes[n]
        if preds[n] or node["kind"] not in ("table", "input") or len(succs[n]) < 2:
            continue
        by_layer: Dict[int, List[str]] = {}
        for t in succs[n]:
            by_layer.setdefault(layer[t], []).append(t)
        if len(by_layer) < 2:
            continue
        first = min(by_layer)
        for L, targets in sorted(by_layer.items()):
            if L == first:
                continue
            cid = f"{n}~{L}"
            nodes[cid] = dict(node, id=cid, dup=True)
            g["nodes"].append(nodes[cid])
            ids.append(cid)
            layer[cid] = L - 1
            rank0[cid] = min(rank0[t] for t in targets) - 0.5
            preds[cid], succs[cid] = [], list(dict.fromkeys(targets))
            for e in g["edges"]:
                if e["from"] == n and e["to"] in targets:
                    e["from"] = cid
            succs[n] = [t for t in succs[n] if t not in targets]
            for t in targets:
                preds[t] = [cid if x == n else x for x in preds[t]]
    used = sorted(set(layer.values()))
    remap = {v: k for k, v in enumerate(used)}
    for n in ids:
        layer[n] = remap[layer[n]]
    nl = (max(layer.values()) + 1) if layer else 0
    # 긴 간선은 층마다 더미를 지난다
    dummies: Dict[str, Dict[str, Any]] = {}
    for e in g["edges"]:
        a, b = e["from"], e["to"]
        chain = [a]
        la, lb = layer[a], layer[b]
        if lb > la + 1:
            for L in range(la + 1, lb):
                d = f"~{e['id']}:{L}"
                dummies[d] = {"id": d, "kind": "dummy", "w": 0, "h": 0}
                layer[d] = L
                chain.append(d)
        chain.append(b)
        e["chain"] = chain
        e["back"] = lb <= la
    allnodes = dict(nodes, **dummies)
    adj_up: Dict[str, List[Tuple[str, Dict[str, Any], int]]] = {n: [] for n in allnodes}   # 왼쪽 이웃
    adj_dn: Dict[str, List[Tuple[str, Dict[str, Any], int]]] = {n: [] for n in allnodes}   # 오른쪽 이웃
    for e in g["edges"]:
        if e["back"]:
            continue
        ch = e["chain"]
        for k in range(len(ch) - 1):
            adj_dn[ch[k]].append((ch[k + 1], e, k))
            adj_up[ch[k + 1]].append((ch[k], e, k))
    layers: List[List[str]] = [[] for _ in range(nl)]
    for n in ids + list(dummies):
        layers[layer[n]].append(n)
    rank: Dict[str, float] = dict(rank0)
    for d in dummies:
        rank[d] = rank.get(g["edges"][int(d[1:].split(":")[0])]["from"], 0) + 0.5
    for L in layers:
        L.sort(key=lambda n: rank[n])
    # 순서: 무게중심 쓸기 (교차 줄이기)
    idx = {n: k for L in layers for k, n in enumerate(L)}

    def bary(n: str, adj: Dict[str, List[Tuple[str, Dict[str, Any], int]]]) -> Optional[float]:
        nb = [idx[m] for m, _e, _k in adj[n]]
        return sum(nb) / len(nb) if nb else None

    def crossings() -> int:
        """이웃한 두 층 사이의 간선 교차 수 — (위 순서, 아래 순서) 정렬 뒤 아래 순서의 뒤집힘 수 (펜윅 트리)"""
        total = 0
        for li in range(nl - 1):
            segs = sorted((idx[a], idx[b]) for a in layers[li] for b, _e, _k in adj_dn[a])
            if len(segs) < 2:
                continue
            size = len(layers[li + 1]) + 2
            tree = [0] * size
            for seen, (_a, b) in enumerate(segs):
                i, below = b + 1, 0
                while i > 0:
                    below += tree[i]
                    i -= i & -i
                total += seen - below
                i = b + 1
                while i < size:
                    tree[i] += 1
                    i += i & -i
        return total

    best = crossings()
    best_layers = [list(L) for L in layers]
    for sweep in range(8):
        rng = range(1, nl) if sweep % 2 == 0 else range(nl - 2, -1, -1)
        adj = adj_up if sweep % 2 == 0 else adj_dn
        for li in rng:
            L = layers[li]
            keys = {}
            for k, n in enumerate(L):
                b = bary(n, adj)
                keys[n] = (b if b is not None else k, k)
            L.sort(key=lambda n: keys[n])
            for k, n in enumerate(L):
                idx[n] = k
        c = crossings()
        if c < best:                     # 교차가 실제로 줄 때만 받아들인다 — 아니면 코드 순서(위 → 아래)를 지킨다
            best, best_layers = c, [list(L) for L in layers]
    layers = best_layers
    idx = {n: k for L in layers for k, n in enumerate(L)}
    # 높이: 포트끼리 곧게 — 층마다 목표 높이를 모아 PAVA 로 겹치지 않게
    y: Dict[str, float] = {}
    for L in layers:
        t = 0.0
        for n in L:
            y[n] = t
            t += allnodes[n]["h"] + GAP_Y

    def sy(n: str, e: Dict[str, Any], k: int) -> float:   # 이 간선이 n 에서 나가는 높이 (n 위에서)
        return float(e["sy"]) if k == 0 else 0.0

    def ty(n: str, e: Dict[str, Any], k: int) -> float:   # 이 간선이 n 으로 들어오는 높이
        return float(e["ty"]) if k + 1 == len(e["chain"]) - 1 else 0.0

    for it in range(10):
        down = it % 2 == 0
        rng = range(1, nl) if down else range(nl - 2, -1, -1)
        for li in rng:
            L = layers[li]
            targets, weights = [], []
            for n in L:
                vals = []
                if down:
                    for m, e, k in adj_up[n]:
                        vals.append(y[m] + sy(m, e, k) - ty(n, e, k))
                else:
                    for m, e, k in adj_dn[n]:
                        vals.append(y[m] + ty(m, e, k) - sy(n, e, k))
                targets.append(sum(vals) / len(vals) if vals else y[n])
                weights.append(float(len(vals)) if vals else 0.5)
            off, c = [], 0.0
            for n in L:
                off.append(c)
                c += allnodes[n]["h"] + GAP_Y
            z = _pava([t - o for t, o in zip(targets, off)], weights)
            for n, zz, o in zip(L, z, off):
                y[n] = zz + o
    low = min(y.values()) if y else 0.0
    for n in y:
        y[n] = snap(y[n] - low) + MARGIN
    # 붙이면 겹칠 수 있다 → 층마다 한 번 더 밀어낸다
    for L in layers:
        prev = None
        for n in L:
            if prev is not None:
                need = y[prev] + allnodes[prev]["h"] + (GAP_Y if allnodes[n]["h"] and allnodes[prev]["h"] else CELL)
                if y[n] < need:
                    y[n] = up8(need)
            prev = n
    # 열 폭 · 간선 트랙
    colw = [max((allnodes[n]["w"] for n in L), default=0) for L in layers]
    hops: List[List[Tuple[float, float, int, int]]] = [[] for _ in range(max(0, nl - 1))]   # 층 사이 (들어가는 y, 나오는 y, 간선, 홉)

    def at_y(n: str, e: Dict[str, Any], k_out: bool, k: int) -> float:
        node = allnodes[n]
        if node["kind"] == "dummy":
            return y[n]
        return y[n] + (e["sy"] if k_out else e["ty"])

    for e in g["edges"]:
        if e["back"]:
            continue
        ch = e["chain"]
        e["ys"] = [at_y(ch[0], e, True, 0)] + [y[d] for d in ch[1:-1]] + [at_y(ch[-1], e, False, len(ch) - 1)]
        for k in range(len(ch) - 1):
            hops[layer[ch[k]]].append((e["ys"][k], e["ys"][k + 1], e["id"], k))
    track: Dict[Tuple[int, int], int] = {}
    ntracks: List[int] = []
    for gi, hs in enumerate(hops):
        down = sorted([h for h in hs if h[1] > h[0]], key=lambda h: (h[0], h[1]))
        up = sorted([h for h in hs if h[1] < h[0]], key=lambda h: (-h[0], -h[1]))
        slots: List[List[Tuple[float, float]]] = []
        order: List[Tuple[int, int, int]] = []       # (간선, 홉, 슬롯)
        for group in (down, up):
            for a, b, eid, k in group:
                lo, hi = min(a, b), max(a, b)
                s = next((i for i, iv in enumerate(slots) if all(hi + CELL < x0 or lo - CELL > x1 for x0, x1 in iv)), None)
                if s is None:
                    slots.append([])
                    s = len(slots) - 1
                slots[s].append((lo, hi))
                order.append((eid, k, s))
        n = len(slots)
        ntracks.append(n)
        for eid, k, s in order:
            track[(eid, k)] = s
    gaps = [max(GAP_X, (t + 1) * TRACK + 2 * CELL) for t in ntracks]
    colx: List[int] = []
    x = MARGIN
    for li in range(nl):
        colx.append(x)
        x += colw[li] + (gaps[li] if li < len(gaps) else 0)
    width = x + MARGIN
    for n in allnodes:
        node = allnodes[n]
        li = layer[n]
        node["x"] = colx[li] + snap((colw[li] - node["w"]) / 2) if node["kind"] != "dummy" else colx[li]
        node["y"] = int(y[n])
        node["layer"] = li
    height = max((allnodes[n]["y"] + allnodes[n]["h"] for n in allnodes), default=0) + MARGIN
    # 간선 경로: 오른쪽 옆 → (트랙에서 꺾기) → 왼쪽 옆
    for e in g["edges"]:
        a, b = nodes[e["from"]], nodes[e["to"]]
        if e["back"]:        # 원칙상 없음 — 위로 돌아가는 선
            x0, y0 = a["x"] + a["w"], a["y"] + e["sy"]
            x1, y1 = b["x"], b["y"] + e["ty"]
            top = min(a["y"], b["y"]) - 2 * CELL
            e["pts"] = [[x0, y0], [x0 + CELL, y0], [x0 + CELL, top], [x1 - CELL, top], [x1 - CELL, y1], [x1, y1]]
            continue
        ch, ys = e["chain"], e["ys"]
        pts: List[List[float]] = [[a["x"] + a["w"], ys[0]]]
        for k in range(len(ch) - 1):
            li = layer[ch[k]]
            right = colx[li] + colw[li]
            nxt_left = colx[li + 1]
            pts.append([right, ys[k]])
            if ys[k + 1] != ys[k]:
                s = track[(e["id"], k)]
                n = ntracks[li]
                slot = (n - 1 - s) if ys[k + 1] > ys[k] else s     # 내려가는 선은 오른쪽 트랙부터 (교차가 줄어든다)
                tx = right + CELL + (slot + 1) * TRACK + (gaps[li] - (n + 1) * TRACK - 2 * CELL) // 2
                pts.append([tx, ys[k]])
                pts.append([tx, ys[k + 1]])
            pts.append([nxt_left, ys[k + 1]])
        pts.append([b["x"], ys[-1]])
        clean: List[List[float]] = []
        for p in pts:                    # 같은 점 · 한 줄 위의 가운데 점 지우기
            if clean and clean[-1] == p:
                continue
            if len(clean) >= 2 and (clean[-2][0] == clean[-1][0] == p[0] or clean[-2][1] == clean[-1][1] == p[1]):
                clean[-1] = p
                continue
            clean.append(p)
        e["pts"] = clean
    g["width"], g["height"] = width, height
    g["layers"] = nl


# ─────────────────────────────────────────────────────────────── 06 SVG

THEMES = {   # 내보내기(--svg · SVG 저장)용 — 화면은 ui.html 의 같은 이름 변수를 쓴다 (값이 같은지 테스트가 본다)
    "dark": {"--fbg": "#000000", "--ink": "#f2f2f3", "--ink-2": "#a5aaae", "--ink-3": "#81888d", "--card": "#0b0b0b",
             "--card-head": "#002341", "--card-edge": "#3f77a6", "--num": "#1f507a", "--head-ink": "#f2f2f3",
             "--head-meta": "#b8cee0", "--tbl": "#b8cee0", "--edge": "#3f77a6", "--accent": "#6aba23", "--accent-ink": "#6aba23",
             "--err": "#f2f2f3", "--err-ink": "#0b0b0b", "--bar": "#08365e", "--pill": "#0b0b0b"},
    "light": {"--fbg": "#d4d6d8", "--ink": "#0b0b0b", "--ink-2": "#4c5156", "--ink-3": "#81888d", "--card": "#f2f2f3",
              "--card-head": "#002341", "--card-edge": "#3f77a6", "--num": "#1f507a", "--head-ink": "#f2f2f3",
              "--head-meta": "#b8cee0", "--tbl": "#1f507a", "--edge": "#3f77a6", "--accent": "#6aba23", "--accent-ink": "#45741b",
              "--err": "#0b0b0b", "--err-ink": "#f2f2f3", "--bar": "#b8cee0", "--pill": "#f2f2f3"},
}

SVG_CSS = """
.flow text{font-family:var(--dos,"Flow1DOS"),monospace;font-size:16px;fill:var(--ink-2);white-space:pre}
.flow .e{fill:none;stroke:var(--edge);stroke-width:1}
.flow .e-write{stroke-width:2}
.flow .e-param{stroke-dasharray:4 3}
.flow .n-box{fill:var(--card);stroke:var(--card-edge);stroke-width:1}
.flow .n-head{fill:var(--card-head)}
.flow .n-num{fill:var(--num)}
.flow .n-numt,.flow .n-title{fill:var(--head-ink)}
.flow .n-meta{fill:var(--head-meta)}
.flow .r-l{fill:var(--ink-3)}
.flow .r-l.jn,.flow .r-t.jn{fill:var(--ink)}
.flow .t{fill:var(--ink)}
.flow .tb{fill:var(--tbl)}
.flow .d{fill:var(--ink-3)}
.flow .p{fill:var(--ink)}
.flow .ph{fill:none;stroke:var(--card-edge);stroke-width:1}
.flow .n-dyn .n-box{stroke-dasharray:4 3}
.flow .n-pill .n-box{fill:var(--pill)}
.flow .n-table .n-box{stroke:var(--ink-3)}
.flow .n-temp .n-box{stroke-dasharray:4 3;stroke:var(--card-edge)}
.flow .n-input .n-box,.flow .n-output .n-box{stroke:var(--ink-3);stroke-dasharray:2 2}
.flow .port{fill:var(--card-edge)}
.flow .run-bar{fill:var(--bar)}
.flow .run-ok{fill:var(--ink-2)}
.flow .run-busy{fill:var(--accent-ink)}
.flow .run-err-box{fill:var(--err)}
.flow .run-err{fill:var(--err-ink)}
.flow .run-none{fill:var(--ink-3)}
"""


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def _text(x: float, yb: float, s: str, cls: str, bold: bool = False, anchor: str = "") -> str:
    a = f' text-anchor="{anchor}"' if anchor else ""
    t = f'<text class="{cls}" x="{x:g}" y="{yb:g}"{a}>{esc(s)}</text>'
    if bold:     # 도스식 굵게: 1px 옆에 한 번 더 (docs/DESIGN.md › 04)
        t += f'<text class="{cls}" x="{x + 1:g}" y="{yb:g}"{a} aria-hidden="true">{esc(s)}</text>'
    return t


def _segs_for(r: Dict[str, Any]) -> List[List[str]]:
    """줄 글 → [글, class] (자리 {x} 는 'p')"""
    if r.get("segs"):
        return [list(s) for s in r["segs"] if s[0]]
    text = r["text"]
    names = sorted({p for p in r.get("ph", []) if p}, key=len, reverse=True)
    base = "t" if r.get("cls") != "j" else "t"
    if not names:
        return [[text, base]]
    pat = "|".join(re.escape("{" + n + "}") if not n.startswith((":", "?", "%", "$", "@")) else re.escape(n)
                   for n in names)
    out: List[List[str]] = []
    last = 0
    for m in re.finditer(pat, text):
        if m.start() > last:
            out.append([text[last:m.start()], base])
        out.append([m.group(0), "p"])
        last = m.end()
    if last < len(text):
        out.append([text[last:], base])
    return out


def _row_svg(r: Dict[str, Any], i: int, w: int) -> str:
    top = HEAD + i * ROW
    yb = top + BASE
    lcls = "r-l" + (" jn" if r.get("cls") == "jn" else "")
    extra = (" jn" if r.get("cls") == "jn" or r["kind"] == "on" else "") + (" has-p" if r.get("ph") else "")
    parts = [f'<g class="r r-{r["kind"]}{extra}" data-row="{i}">']
    if r["lbl"]:
        parts.append(_text(CELL, yb, r["lbl"], lcls, bold=r.get("cls") == "jn"))
    avail = (w - LBL - CELL) // CELL
    segs = _segs_for(r)
    if sum(cells(t) for t, _ in segs) > avail:          # 넘치면 끝에 … — 자리 상자도 잘린 만큼만
        budget, cut = avail - 1, []
        for t, c in segs:
            if cells(t) <= budget:
                cut.append([t, c])
                budget -= cells(t)
                continue
            head = clip(t, budget + 1)[:-1] if budget > 0 else ""
            if head:
                cut.append([head, "t" if c == "p" else c])
            break
        segs = cut + [["…", "d"]]
    x = LBL
    boxes: List[str] = []
    spans: List[str] = []
    for t, c in segs:
        n = cells(t)
        if c == "p":
            boxes.append(f'<rect class="ph" x="{x - 2}.5" y="{top + 1}.5" width="{n * CELL + 3}" height="{ROW - 3}"/>')
        spans.append(f'<tspan class="{c}">{esc(t)}</tspan>')
        x += n * CELL
    parts += boxes
    parts.append(f'<text x="{LBL}" y="{yb}">{"".join(spans)}</text>')
    parts.append("</g>")
    return "".join(parts)


def _node_svg(n: Dict[str, Any]) -> str:
    x, y, w, h = n["x"], n["y"], n["w"], n["h"]
    kind = n["kind"]
    cls = f"n n-{kind}"
    if n.get("dyn"):
        cls += " n-dyn"
    if kind == "table" and n.get("role") in ("temp", "sink"):
        cls += " n-temp"
    if kind in ("table", "input", "output"):
        cls += " n-pill"
    out = [f'<g class="{cls}" data-id="{esc(n["id"])}" transform="translate({x},{y})">',
           f'<rect class="n-box" x=".5" y=".5" width="{w - 1}" height="{h - 1}"/>']
    if kind in ("query", "op"):
        out.append(f'<rect class="n-head" x="1" y="1" width="{w - 2}" height="{HEAD - 1}"/>')
        out.append(f'<rect class="n-num" x="1" y="1" width="{5 * CELL - 1}" height="{HEAD - 1}"/>')
        out.append(_text(CELL, BASE + 2, n["num"], "n-numt"))
        meta = n.get("meta", "")
        room = (w - 6 * CELL - CELL) // CELL
        mcells = min(cells(meta), max(0, room - cells(n["title"]) - 2), (w // CELL) // 2)
        meta_s = clip(meta, mcells) if mcells > 3 else ""
        title = clip(n["title"], room - (cells(meta_s) + 2 if meta_s else 0))
        out.append(_text(6 * CELL, BASE + 2, title, "n-title", bold=True))
        if meta_s:
            out.append(_text(w - CELL, BASE + 2, meta_s, "n-meta", anchor="end"))
        for i, r in enumerate(n.get("rows") or []):
            out.append(_row_svg(r, i, w))
        if kind == "query" and n.get("has_run"):
            out.append(_run_svg(n))
    else:
        label = n.get("label", "")
        if kind == "table":
            name = clip(label, (w - 16) // CELL)
            dot = name.rfind(".", 0, len(n["name"]))
            if 0 < dot < len(name) and not n.get("dyn"):
                out.append(f'<text x="{CELL}" y="{BASE + 2}"><tspan class="d">{esc(name[:dot + 1])}</tspan>'
                           f'<tspan class="tb">{esc(name[dot + 1:])}</tspan></text>')
            else:
                out.append(_text(CELL, BASE + 2, name, "tb"))
        else:
            kind_s, _, target = label.partition(" · ")
            s1 = kind_s + " · "
            t2 = clip(target, (w - 16) // CELL - cells(s1))
            out.append(f'<text x="{CELL}" y="{BASE + 2}"><tspan class="d">{esc(s1)}</tspan>'
                       f'<tspan class="t">{esc(t2)}</tspan></text>')
    out.append("</g>")
    return "".join(out)


def _run_svg(n: Dict[str, Any]) -> str:
    run = n.get("run") or {}
    text, state = _run_text(run)
    top = n["h"] - PAD - ROW
    w = n["w"]
    out = [f'<g class="run" data-state="{state}" data-since="{run.get("since", "")}">']
    ratio = float(run.get("ratio") or 0)
    if state in ("ok", "busy") and ratio > 0:
        out.append(f'<rect class="run-bar" x="1" y="{top}" width="{max(2, int((w - 2) * min(1.0, ratio)))}" height="{ROW}"/>')
    if state == "err":
        s = clip(text, (w - 2 * CELL) // CELL)
        out.append(f'<rect class="run-err-box" x="{CELL - 2}" y="{top + 1}" width="{cells(s) * CELL + 4}" height="{ROW - 2}"/>')
        out.append(_text(CELL, top + BASE, s, "run-err"))
    else:
        out.append(_text(CELL, top + BASE, clip(text, (w - 2 * CELL) // CELL), f"run-{state}"))
    out.append("</g>")
    return "".join(out)


def _path(pts: List[List[float]]) -> str:
    if not pts:
        return ""
    d = [f"M{pts[0][0] + .5:g} {pts[0][1] + .5:g}"]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if y0 == y1:
            d.append(f"H{x1 + .5:g}")
        elif x0 == x1:
            d.append(f"V{y1 + .5:g}")
        else:
            d.append(f"L{x1 + .5:g} {y1 + .5:g}")
    return "".join(d)


def svg(g: Dict[str, Any], standalone: bool = False, theme: str = "dark", font_b64: str = "") -> str:
    w, h = g.get("width", 200), g.get("height", 120)
    head = [f'<svg xmlns="http://www.w3.org/2000/svg" class="flow" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'data-detail="{g.get("detail", 2)}">']
    if standalone:
        vars_ = ";".join(f"{k}:{v}" for k, v in THEMES.get(theme, THEMES["dark"]).items())
        font = (f'@font-face{{font-family:"Flow1DOS";src:url(data:font/woff;base64,{font_b64}) format("woff")}}'
                if font_b64 else "")
        head.append(f"<style>{font}.flow{{{vars_}}}{SVG_CSS}</style>")
        head.append(f'<rect width="{w}" height="{h}" fill="var(--fbg)"/>')
    body = ['<g class="edges">']
    for e in g["edges"]:
        body.append(f'<path class="e e-{e["kind"]}{" e-join" if e.get("join") else ""}" data-e="{e["id"]}" '
                    f'data-from="{esc(e["from"])}" '
                    f'data-to="{esc(e["to"])}" d="{_path(e.get("pts") or [])}"/>')
    body.append('</g><g class="nodes">')
    for n in g["nodes"]:
        body.append(_node_svg(n))
    body.append('</g><g class="ports">')
    for e in g["edges"]:
        pts = e.get("pts") or []
        if pts:
            x1, y1 = pts[-1]
            body.append(f'<rect class="port" data-e="{e["id"]}" x="{x1 - 3:g}" y="{y1 - 2:g}" width="4" height="5"/>')
    body.append("</g></svg>")
    return "".join(head + body)


# ─────────────────────────────────────────────────────────────── 07 글 요약 (--scan)

def _refname(res: Dict[str, Any], nid: str) -> str:
    for bucket, pre in (("queries", "Q"), ("ops", "J"), ("inputs", "I"), ("outputs", "O")):
        for it in res.get(bucket, []):
            if it["id"] == nid:
                return f"{pre}{it['n']:02d}" + (f" ({it['var']})" if it.get("var") else "")
    return nid


def _where_text(it: Dict[str, Any]) -> str:
    s = f"L{it['line']}"
    if it.get("cell"):
        s += f" 셀{it['cell']}:{it['cell_line']}"
    if it.get("via"):
        s += f" · {it['via']}"
    elif it.get("scope"):
        s += f" · {it['scope']}"
    if it.get("loop"):
        s += " · 반복"
    if it.get("branch"):
        s += " · 조건부"
    return s


def summary(res: Dict[str, Any]) -> str:
    """스캔 결과 → 사람 · 사내 LLM 이 읽는 글. 줄을 자르지 않는다 (tests/golden 이 이 글을 그대로 비교)"""
    st = res.get("stats") or {}
    out = [f"{res.get('name', '')} · 쿼리 {st.get('queries', 0)} · 테이블 {st.get('tables', 0)} · 조인 {st.get('joins', 0)}"
           f" · 조건 {st.get('conds', 0)} · 병합 {st.get('ops', 0)} · 파일 입력 {st.get('inputs', 0)}"
           f" · 출력 {st.get('outputs', 0)}"]
    if res.get("error"):
        out.append(f"× {res['error']}")
    for w in res.get("warnings", []):
        out.append(f"! {w}")
    for q in res.get("queries", []):
        call = q["call"] if q["call"] in ("%%sql", "%sql", "SQL") else q["call"] + "(…)"
        head = f"Q{q['n']:02d}  {_where_text(q)}  " + (f"{q['var']} = " if q["var"] else "") + call
        if q["sql_src"] not in ("literal",):
            head += f"  [{q['sql_src']}]"
        out.append("")
        out.append(head)
        for r in query_rows(q, 3, 0):
            if r["kind"] != "via":           # 경유는 머리 줄에 이미 있다
                out.append(f"    {r['lbl']:<7} {r['text']}".rstrip())
        for p in q["params"]:
            src = ", ".join(_refname(res, d) for d in p["deps"]) or "코드의 값"
            out.append(f"    {{{p['name']}}} ← {src}" + (f" · {p['expr']}" if p["expr"] != p["name"] else ""))
    for o in res.get("ops", []):
        out.append("")
        out.append(f"J{o['n']:02d}  {_where_text(o)}  " + (f"{o['var']} = " if o["var"] else "") + f"{o['kind']}  "
                   + (o["how"] or "") + (f" on {', '.join(o['on'])}" if o["on"] else "")
                   + (f" {', '.join(o['left_on'])} = {', '.join(o['right_on'])}" if o["left_on"] or o["right_on"] else ""))
        for inp in o["inputs"]:
            src = ", ".join(_refname(res, d) for d in inp["deps"]) or "코드의 값"
            out.append(f"    {inp['side']}  {inp['label'] or '(식)'} ← {src}")
    for i in res.get("inputs", []):
        out.append("")
        out.append(f"I{i['n']:02d}  {_where_text(i)}  " + (f"{i['var']} = " if i["var"] else "") + f"{i['kind']}  {i['target']}")
    for o in res.get("outputs", []):
        srcs = [e["from"] for e in res.get("edges", []) if e["to"] == o["id"]]
        out.append("")
        out.append(f"O{o['n']:02d}  {_where_text(o)}  {o['kind']}  {o['target']}"
                   + (f"  ← {', '.join(_refname(res, s) for s in srcs)}" if srcs else ""))
    tables: Dict[str, Dict[str, List[str]]] = {}
    names: Dict[str, str] = {}
    for q in res.get("queries", []):
        for r in q["reads"]:
            tables.setdefault(r["key"], {"r": [], "w": []})["r"].append(f"Q{q['n']:02d}")
            names.setdefault(r["key"], r["name"])
        for w in q["writes"]:
            tables.setdefault(w["key"], {"r": [], "w": []})["w"].append(f"Q{q['n']:02d}")
            names.setdefault(w["key"], w["name"])
    for o in res.get("outputs", []):
        if o.get("table"):
            tables.setdefault(o["table"]["key"], {"r": [], "w": []})["w"].append(f"O{o['n']:02d}")
            names.setdefault(o["table"]["key"], o["table"]["name"])
    if tables:
        out.append("")
        out.append("테이블")
        wide = max(cells(n) for n in names.values())
        for key in sorted(tables):
            t = tables[key]
            parts = []
            if t["w"]:
                parts.append("쓰기 " + " ".join(dict.fromkeys(t["w"])))
            if t["r"]:
                parts.append("읽기 " + " ".join(dict.fromkeys(t["r"])))
            name = names[key]
            out.append(f"  {name}{' ' * (wide - cells(name))}  " + " · ".join(parts))
    flow = [e for e in res.get("edges", [])]
    if flow:
        out.append("")
        out.append("흐름")
        for e in flow:
            label = e.get("label") or ""
            kind = {"param": "조건", "df": "데이터"}.get(e["kind"], e["kind"])
            out.append(f"  {_refname(res, e['from'])} → {_refname(res, e['to'])}  {kind}"
                       + (f" {{{label}}}" if e["kind"] == "param" else (f" {label}" if label else ""))
                       + (f" ({e['side']})" if e.get("side") in ("L", "R") else ""))
    return "\n".join(line.rstrip() for line in out) + "\n"
