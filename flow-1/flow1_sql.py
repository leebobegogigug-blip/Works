# -*- coding: utf-8 -*-
"""flow1_sql — SQL 을 절(WITH · SELECT · FROM · JOIN · WHERE …)로 나눈다 (Flow–1 · 표준 라이브러리만 · Python 3.8+)

완전한 문법기가 아니다. 방언(Hive · Spark · Impala · Presto/Trino · Oracle · ANSI)이 섞여도 멈추지 않고,
흐름도에 필요한 것 — 읽는 테이블 · 쓰는 테이블 · 조인 · 조건 · 컬럼 — 만 뽑는다. 모르는 것은 글 그대로 둔다.

  parse_sql(text, known=None) → {"stmts": [문장…], "reads": [...], "writes": [...], "error": ""}
      known = 파이썬 쪽 자리표시자 이름 집합 ({start} 처럼 SQL 에 박힌 것). None 이면 {이름} 꼴을 모두 자리표시자로 본다
  sql_spans(text, stmts) → [[글, 종류], …]   화면의 SQL 색칠 (kw · str · num · com · ph · bind · tbl · id · op)

결과는 전부 JSON 으로 옮길 수 있는 dict · list · str · bool 이다. 모양은 docs/GUIDE.md › 03 데이터 모델.
이 파일은 예외를 밖으로 던지지 않는다 — 읽지 못한 문장은 kind "other" + error 와 정규식으로 찾은 테이블만 남긴다.
"""
import re
from typing import Any, Dict, List, NamedTuple, Optional, Sequence, Set, Tuple

# ─────────────────────────────────────────────────────────────── 01 토큰

KEYWORDS = frozenset("""
ALL ALTER ANALYZE AND ANTI ANY APPLY AS ASC BETWEEN BUCKETS BY CASE CAST CLUSTER CLUSTERED COMMENT CONNECT CREATE
CROSS CUBE CURRENT DATE DELETE DESC DISTINCT DISTRIBUTE DIV DROP ELSE END ESCAPE EXCEPT EXCLUDE EXISTS EXPLAIN
EXTERNAL EXTRACT FALSE FETCH FILTER FIRST FOLLOWING FOR FORMAT FROM FULL GLOBAL GROUP GROUPING GROUPS HAVING IF
ILIKE IN INNER INSERT INTERSECT INTERVAL INTO IS JOIN LAST LATERAL LEFT LIKE LIMIT LOCAL LOCATION MATCHED
MATERIALIZED MERGE MINUS NATURAL NEXT NOT NULL NULLS OFFSET ON ONLY OR ORDER ORDINALITY OUTER OVER OVERWRITE
PARTITION PARTITIONED PERCENT PIVOT PRECEDING PRIOR QUALIFY RANGE RECURSIVE REGEXP REPLACE RIGHT RLIKE ROLLUP ROW
ROWS SELECT SEMI SET SETS SOME SORT START STORED TABLE TABLESAMPLE TBLPROPERTIES TEMP TEMPORARY THEN TIES
TIMESTAMP TOP TRUE TRUNCATE TRY_CAST UNBOUNDED UNION UNNEST UNPIVOT UPDATE USING VALUES VIEW VOLATILE WHEN WHERE
WINDOW WITH WITHIN XOR
""".split())
AGGREGATES = frozenset("""
ANY_VALUE APPROX_COUNT_DISTINCT APPROX_DISTINCT APPROX_PERCENTILE ARBITRARY ARRAY_AGG AVG BOOL_AND BOOL_OR
COLLECT_LIST COLLECT_SET CORR COUNT COUNT_IF COVAR_POP COVAR_SAMP EVERY GROUP_CONCAT HISTOGRAM LISTAGG MAP_AGG MAX
MEDIAN MIN MODE PERCENTILE PERCENTILE_APPROX PERCENTILE_CONT PERCENTILE_DISC STDDEV STDDEV_POP STDDEV_SAMP
STRING_AGG SUM SUM_IF VARIANCE VAR_POP VAR_SAMP
""".split())
# 컬럼이 아닌 낱말 (괄호 없이 쓰는 함수 · 의사 컬럼 · 날짜 단위)
NOT_COLUMN = KEYWORDS | frozenset("""
CURRENT_DATE CURRENT_TIME CURRENT_TIMESTAMP CURRENT_USER LOCALTIME LOCALTIMESTAMP SYSDATE SYSTIMESTAMP USER
ROWNUM LEVEL YEAR MONTH DAY HOUR MINUTE SECOND WEEK QUARTER
""".split())
# 별칭이 될 수 없는 낱말 (FROM 의 테이블 뒤)
ALIAS_STOP = frozenset("""
ANTI ANY APPLY AS ASOF CLUSTER CONNECT CROSS DISTRIBUTE EXCEPT FETCH FOR FROM FULL GLOBAL GROUP HAVING INNER
INTERSECT JOIN LATERAL LEFT LIMIT MINUS NATURAL OFFSET ON ORDER OUTER PARTITION PIVOT QUALIFY RIGHT SELECT SEMI
SET SORT START STRAIGHT_JOIN TABLESAMPLE UNION UNPIVOT USING VALUES WHERE WINDOW WITH
""".split())
JOIN_WORDS = frozenset("INNER LEFT RIGHT FULL OUTER CROSS NATURAL SEMI ANTI ANY ASOF GLOBAL".split())
SET_OPS = frozenset("UNION INTERSECT EXCEPT MINUS".split())


class Tok(NamedTuple):
    kind: str      # ws · com · str · qid · num · word · op · ( · ) · , · . · ; · ph · bind · other
    text: str
    start: int
    end: int
    up: str        # word 이면 대문자, 아니면 text


_PH_RE = re.compile(r"\{[A-Za-z_\u0080-\uffff][\w.\u0080-\uffff]{0,60}(?:\(\))?\}")
_BIND_RE = re.compile(r"%\([A-Za-z_]\w*\)[sdif]|%[sdif]")
_NUM_RE = re.compile(r"\d+(?:\.\d*)?(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?")
_OPS = ("->>", "<=>", "<=", ">=", "<>", "!=", "==", "||", "::", "->", "=>")


def _word_char(c: str) -> bool:
    return c.isalnum() or c in "_$"


def tokens(text: str) -> List[Tok]:
    """SQL 글 → 토큰 (공백 · 주석도 남긴다 — 위치로 원문을 다시 자르려고)"""
    out: List[Tok] = []
    i, n = 0, len(text)
    add = out.append
    while i < n:
        c = text[i]
        if c.isspace():
            j = i + 1
            while j < n and text[j].isspace():
                j += 1
            add(Tok("ws", text[i:j], i, j, ""))
            i = j
            continue
        if c == "-" and text.startswith("--", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            add(Tok("com", text[i:j], i, j, ""))
            i = j
            continue
        if c == "/" and text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            add(Tok("com", text[i:j], i, j, ""))
            i = j
            continue
        if c in "'\"`":
            j = i + 1
            while j < n:
                d = text[j]
                if d == "\\" and c != "`":        # Hive · Spark · Impala 식 역슬래시 이스케이프
                    j += 2
                    continue
                if d == c:
                    if j + 1 < n and text[j + 1] == c:   # '' · "" 이스케이프
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            j = min(j, n)
            add(Tok("str" if c == "'" else "qid", text[i:j], i, j, text[i:j]))
            i = j
            continue
        if c == "{":
            m = _PH_RE.match(text, i)
            if m:
                add(Tok("ph", m.group(0), i, m.end(), m.group(0)))
                i = m.end()
                continue
        if c == "$" and text.startswith("${", i):
            j = text.find("}", i)
            if 0 < j - i < 80:
                add(Tok("bind", text[i:j + 1], i, j + 1, text[i:j + 1]))
                i = j + 1
                continue
        if c == ":" and i + 1 < n and (text[i + 1].isalpha() or text[i + 1] == "_") \
                and not (out and out[-1].text == ":") and not text.startswith("::", i):
            j = i + 1
            while j < n and _word_char(text[j]):
                j += 1
            add(Tok("bind", text[i:j], i, j, text[i:j]))
            i = j
            continue
        if c == "?":
            add(Tok("bind", "?", i, i + 1, "?"))
            i += 1
            continue
        if c == "%":
            m = _BIND_RE.match(text, i)
            if m:
                add(Tok("bind", m.group(0), i, m.end(), m.group(0)))
                i = m.end()
                continue
        if c == "@" and i + 1 < n and (text[i + 1].isalpha() or text[i + 1] == "_"):
            j = i + 1
            while j < n and _word_char(text[j]):
                j += 1
            add(Tok("bind", text[i:j], i, j, text[i:j]))
            i = j
            continue
        if c.isdigit() or (c == "." and i + 1 < n and text[i + 1].isdigit() and not (out and out[-1].kind in ("word", "qid"))):
            m = _NUM_RE.match(text, i)
            j = m.end() if m else i + 1
            add(Tok("num", text[i:j], i, j, text[i:j]))
            i = j
            continue
        if c.isalpha() or c == "_":
            j = i + 1
            while j < n and _word_char(text[j]):
                j += 1
            w = text[i:j]
            add(Tok("word", w, i, j, w.upper()))
            i = j
            continue
        if c in "(),;.":
            add(Tok(c, c, i, i + 1, c))
            i += 1
            continue
        op = next((o for o in _OPS if text.startswith(o, i)), "")
        if op:
            add(Tok("op", op, i, i + len(op), op))
            i += len(op)
            continue
        if c in "=<>+-*/%|&^~![]:":
            add(Tok("op", c, i, i + 1, c))
        else:
            add(Tok("other", c, i, i + 1, c))
        i += 1
    return out


def unquote(t: Tok) -> str:
    """"a" · `a` → a (따옴표 안의 겹 따옴표도 풀기)"""
    if t.kind == "qid" and len(t.text) >= 2:
        q = t.text[0]
        return t.text[1:-1].replace(q + q, q)
    return t.text


def span_text(toks: Sequence[Tok]) -> str:
    """토큰을 다시 글로 — 원문에 공백 · 줄바꿈 · 주석이 있던 자리는 빈칸 하나로"""
    out: List[str] = []
    prev: Optional[Tok] = None
    for t in toks:
        if prev is not None and t.start > prev.end:
            out.append(" ")
        out.append(t.text)
        prev = t
    return "".join(out)


def _match_map(toks: Sequence[Tok]) -> Dict[int, int]:
    """여는 괄호 위치 → 닫는 괄호 위치 (짝이 없으면 끝)"""
    stack: List[int] = []
    out: Dict[int, int] = {}
    for i, t in enumerate(toks):
        if t.kind == "(":
            stack.append(i)
        elif t.kind == ")" and stack:
            out[stack.pop()] = i
    for i in stack:
        out[i] = len(toks)
    return out


class Toks:
    """의미 있는 토큰 목록 (공백 · 주석 뺌) + 괄호 짝"""

    def __init__(self, toks: Sequence[Tok]):
        self.t = list(toks)
        self.m = _match_map(self.t)

    def close(self, i: int) -> int:
        return self.m.get(i, len(self.t))


def split_top(toks: Sequence[Tok], kind: str = ",") -> List[List[Tok]]:
    """괄호 밖의 kind(, · ;) 로 나눈다"""
    out: List[List[Tok]] = [[]]
    depth = 0
    for t in toks:
        if t.kind == "(":
            depth += 1
        elif t.kind == ")":
            depth -= 1
        elif t.kind == kind and depth == 0:
            out.append([])
            continue
        out[-1].append(t)
    return out


# ─────────────────────────────────────────────────────────────── 02 조건 · 컬럼

_PARAM_RE = re.compile(r"\{([A-Za-z_\u0080-\uffff][\w.\u0080-\uffff]{0,60}(?:\(\))?)\}")


def params_in(text: str, known: Optional[Set[str]]) -> List[str]:
    out: List[str] = []
    for m in _PARAM_RE.finditer(text):
        name = m.group(1)
        if (known is None or name in known) and name not in out:
            out.append(name)
    return out


def col_refs(toks: Sequence[Tok]) -> List[str]:
    """컬럼 참조 (a.b · b) — 함수 이름 · 키워드 · 형 이름(:: · AS 뒤) · 문자열은 뺀다"""
    refs: List[str] = []
    i, n = 0, len(toks)
    while i < n:
        t = toks[i]
        if t.kind == "qid" or (t.kind == "word" and t.up not in NOT_COLUMN):
            parts = [unquote(t)]
            j = i + 1
            while j + 1 < n and toks[j].kind == "." and toks[j + 1].kind in ("word", "qid"):
                parts.append(unquote(toks[j + 1]))
                j += 2
            nxt = toks[j] if j < n else None
            prev = toks[i - 1] if i > 0 else None
            func = nxt is not None and nxt.kind == "("
            typ = prev is not None and (prev.text == "::" or (prev.kind == "word" and prev.up == "AS"))
            if not func and not typ:
                ref = ".".join(parts)
                if ref not in refs:
                    refs.append(ref)
            i = j
            continue
        i += 1
    return refs


def _split_bool(toks: Sequence[Tok], word: str) -> List[List[Tok]]:
    """괄호 · CASE…END 밖의 AND / OR 로 나눈다. BETWEEN x AND y 의 AND 는 나누지 않는다"""
    out: List[List[Tok]] = [[]]
    depth = case = between = 0
    for t in toks:
        if t.kind == "(":
            depth += 1
        elif t.kind == ")":
            depth -= 1
        elif depth == 0 and t.kind == "word":
            if t.up == "CASE":
                case += 1
            elif t.up == "END" and case:
                case -= 1
            elif not case:
                if t.up == "BETWEEN":
                    between += 1
                elif t.up == word:
                    if word == "AND" and between:
                        between -= 1
                    else:
                        out.append([])
                        continue
        out[-1].append(t)
    return out


def _strip_parens(toks: List[Tok]) -> List[Tok]:
    """조건 전체를 감싼 괄호 한 겹을 벗긴다 ((a = b) → a = b)"""
    while len(toks) >= 2 and toks[0].kind == "(" and _match_map(toks).get(0) == len(toks) - 1:
        toks = toks[1:-1]
    return toks


def _colref_only(toks: Sequence[Tok]) -> str:
    """토큰이 컬럼 참조 하나뿐이면 그 이름 (Oracle 의 (+) 는 무시)"""
    toks = list(toks)
    if len(toks) >= 3 and [t.text for t in toks[-3:]] == ["(", "+", ")"]:
        toks = toks[:-3]
    if not toks or len(toks) % 2 == 0:
        return ""
    for k, t in enumerate(toks):
        if k % 2 == 0 and not (t.kind == "qid" or (t.kind == "word" and t.up not in NOT_COLUMN)):
            return ""
        if k % 2 == 1 and t.kind != ".":
            return ""
    return ".".join(unquote(t) for t in toks[::2])


class Parser:
    """문장 하나를 읽는다. known = 파이썬 자리표시자 이름"""

    def __init__(self, known: Optional[Set[str]]):
        self.known = known

    # ── 조건
    def conditions(self, toks: Sequence[Tok]) -> List[Dict[str, Any]]:
        toks = [t for t in toks]
        if not toks:
            return []
        ors = _split_bool(toks, "OR")
        if len(ors) > 1:
            return [self.cond(toks, "or")]
        return [self.cond(p) for p in _split_bool(toks, "AND") if p]

    def cond(self, toks: List[Tok], kind: str = "") -> Dict[str, Any]:
        text = span_text(toks)
        subs = self.subqueries(toks)
        core = _strip_parens(list(toks))
        if not kind:
            eq = [k for k, t in enumerate(core) if t.kind == "op" and t.text in ("=", "==", "<=>")]
            if len(eq) == 1:
                a, b = _colref_only(core[:eq[0]]), _colref_only(core[eq[0] + 1:])
                if "." in a and "." in b and a.split(".")[-2].lower() != b.split(".")[-2].lower():
                    kind = "join"
        if not kind:
            kind = "sub" if subs else "filter"
        return {"text": text, "kind": kind, "cols": col_refs(toks), "params": params_in(text, self.known),
                "binds": [t.text for t in toks if t.kind == "bind"], "subs": subs}

    def subqueries(self, toks: Sequence[Tok]) -> List[Dict[str, Any]]:
        """조건 · 컬럼 안의 (SELECT …) 들"""
        tt = Toks(toks)
        out: List[Dict[str, Any]] = []
        i = 0
        while i < len(tt.t):
            if tt.t[i].kind == "(" and i + 1 < len(tt.t) and tt.t[i + 1].up in ("SELECT", "WITH"):
                j = tt.close(i)
                out.append(self.query(tt.t[i + 1:j]))
                i = j + 1
                continue
            i += 1
        return out

    # ── SELECT
    def query(self, toks: Sequence[Tok]) -> Dict[str, Any]:
        """[WITH …] SELECT … (UNION …) — 괄호로 감싼 것도"""
        toks = list(toks)
        ctes: List[Dict[str, Any]] = []
        if toks and toks[0].up == "WITH":
            ctes, toks = self.with_list(toks)
        sel = self.select(toks)
        sel["ctes"] = ctes + sel.get("ctes", [])
        return sel

    def with_list(self, toks: List[Tok]) -> Tuple[List[Dict[str, Any]], List[Tok]]:
        tt = Toks(toks)
        t = tt.t
        i = 1
        if i < len(t) and t[i].up == "RECURSIVE":
            i += 1
        ctes: List[Dict[str, Any]] = []
        while i < len(t) and t[i].kind in ("word", "qid"):
            name = unquote(t[i])
            i += 1
            cols: List[str] = []
            if i < len(t) and t[i].kind == "(":
                j = tt.close(i)
                cols = [span_text(c) for c in split_top(t[i + 1:j]) if c]
                i = j + 1
            if i < len(t) and t[i].up == "AS":
                i += 1
            while i < len(t) and t[i].up in ("NOT", "MATERIALIZED"):
                i += 1
            if i < len(t) and t[i].kind == "(":
                j = tt.close(i)
                ctes.append({"name": name, "key": name.lower(), "cols": cols, "select": self.query(t[i + 1:j])})
                i = j + 1
            else:
                break
            if i < len(t) and t[i].kind == ",":
                i += 1
                continue
            break
        return ctes, t[i:]

    def select(self, toks: Sequence[Tok]) -> Dict[str, Any]:
        """SELECT 하나 (UNION 가지는 union 에)"""
        branches: List[Tuple[str, List[Tok]]] = []
        cur: List[Tok] = []
        op = ""
        depth = 0
        toks = list(toks)
        k = 0
        while k < len(toks):
            t = toks[k]
            if t.kind == "(":
                depth += 1
            elif t.kind == ")":
                depth -= 1
            elif depth == 0 and t.up in SET_OPS:
                branches.append((op, cur))
                op, cur = t.up, []
                if k + 1 < len(toks) and toks[k + 1].up in ("ALL", "DISTINCT"):
                    op += " " + toks[k + 1].up
                    k += 1
                k += 1
                continue
            cur.append(t)
            k += 1
        branches.append((op, cur))
        first = self.branch(branches[0][1])
        first["union"] = [{"op": o, "select": self.branch(b)} for o, b in branches[1:]]
        return first

    def branch(self, toks: Sequence[Tok]) -> Dict[str, Any]:
        toks = _strip_parens(list(toks))
        if toks and toks[0].up == "WITH":         # (WITH … SELECT …) 가지
            return self.query(toks)
        sel: Dict[str, Any] = {"distinct": False, "top": "", "columns": [], "sources": [], "where": [], "group": [],
                               "having": [], "order": [], "limit": "", "union": [], "ctes": [], "subs": [], "extra": []}
        clauses = self.clauses(toks)
        for name, body in clauses:
            if name == "SELECT":
                self.columns(body, sel)
            elif name == "FROM":
                sel["sources"] = self.sources(body)
            elif name == "WHERE":
                sel["where"] = self.conditions(body)
            elif name in ("GROUP BY",):
                sel["group"] = [span_text(p) for p in split_top(body) if p]
            elif name == "HAVING":
                sel["having"] = self.conditions(body)
            elif name in ("ORDER BY", "SORT BY", "CLUSTER BY", "DISTRIBUTE BY"):
                items = [span_text(p) for p in split_top(body) if p]
                if name == "ORDER BY" or not sel["order"]:
                    sel["order"] = items
                if name != "ORDER BY":
                    sel["extra"].append(name + " " + ", ".join(items))
            elif name in ("LIMIT", "FETCH", "OFFSET"):
                txt = span_text(body)
                if name == "LIMIT":
                    sel["limit"] = txt
                elif name == "FETCH":
                    m = re.search(r"\d+|\{[^}]+\}|:\w+|\?", txt)
                    sel["limit"] = sel["limit"] or (m.group(0) if m else txt)
                else:
                    sel["extra"].append("OFFSET " + txt)
            elif name == "QUALIFY":
                sel["where"] += [dict(c, kind="qualify") for c in self.conditions(body)]
            elif name:
                sel["extra"].append((name + " " + span_text(body)).strip())
        return sel

    CLAUSE_STARTS = {"SELECT": "", "FROM": "", "WHERE": "", "HAVING": "", "LIMIT": "", "OFFSET": "", "FETCH": "",
                     "QUALIFY": "", "WINDOW": "", "GROUP": "BY", "ORDER": "BY", "SORT": "BY", "CLUSTER": "BY",
                     "DISTRIBUTE": "BY", "CONNECT": "BY", "START": "WITH"}

    def clauses(self, toks: Sequence[Tok]) -> List[Tuple[str, List[Tok]]]:
        """괄호 밖의 절 키워드로 나눈다 → [(절 이름, 토큰)]. 처음 SELECT 앞의 것은 이름 ''"""
        out: List[Tuple[str, List[Tok]]] = [("", [])]
        depth = 0
        toks = list(toks)
        k = 0
        while k < len(toks):
            t = toks[k]
            if t.kind == "(":
                depth += 1
            elif t.kind == ")":
                depth -= 1
            elif depth == 0 and t.kind == "word" and t.up in self.CLAUSE_STARTS:
                need = self.CLAUSE_STARTS[t.up]
                if not need:
                    if t.up == "FETCH" and not (k + 1 < len(toks) and toks[k + 1].up in ("FIRST", "NEXT")):
                        pass
                    else:
                        out.append((t.up, []))
                        k += 1
                        continue
                elif k + 1 < len(toks) and toks[k + 1].up == need:
                    out.append((t.up + " " + need, []))
                    k += 2
                    continue
            out[-1][1].append(t)
            k += 1
        return [c for c in out if c[0] or c[1]]

    def columns(self, toks: List[Tok], sel: Dict[str, Any]) -> None:
        i = 0
        while i < len(toks) and toks[i].up in ("DISTINCT", "ALL", "TOP", "STRAIGHT_JOIN", "SQL_NO_CACHE"):
            if toks[i].up == "DISTINCT":
                sel["distinct"] = True
            if toks[i].up == "TOP" and i + 1 < len(toks):
                sel["top"] = toks[i + 1].text
                i += 1
                if i + 1 < len(toks) and toks[i + 1].up == "PERCENT":
                    sel["top"] += " PERCENT"
                    i += 1
                sel["limit"] = sel["limit"] or "TOP " + sel["top"]
            i += 1
        for item in split_top(toks[i:]):
            if not item:
                continue
            alias = ""
            expr = item
            if len(item) >= 3 and item[-2].up == "AS" and item[-1].kind in ("word", "qid", "str"):
                alias, expr = unquote(item[-1]).strip("'"), item[:-2]
            elif len(item) >= 2 and item[-1].kind in ("word", "qid") and item[-1].up not in NOT_COLUMN \
                    and item[-2].kind not in ("op", ".") and not (item[-2].kind == "word" and item[-2].up in ("DISTINCT",)):
                alias, expr = unquote(item[-1]), item[:-1]
            et = span_text(expr)
            subs = self.subqueries(expr)
            sel["subs"] += [{"at": "select", "select": s} for s in subs]
            sel["columns"].append({
                "text": span_text(item), "expr": et, "alias": alias,
                "star": et == "*" or et.endswith(".*"),
                "agg": any(t.kind == "word" and t.up in AGGREGATES and k + 1 < len(expr) and expr[k + 1].kind == "("
                           for k, t in enumerate(expr)),
                "win": any(t.up == "OVER" for t in expr),
                "cols": col_refs(expr), "params": params_in(et, self.known), "subs": subs})

    # ── FROM · JOIN
    def sources(self, toks: Sequence[Tok]) -> List[Dict[str, Any]]:
        tt = Toks(toks)
        t = tt.t
        out: List[Dict[str, Any]] = []
        join = ""
        i = 0
        while i < len(t):
            tk = t[i]
            if tk.kind == ",":
                join = ","
                i += 1
                continue
            if tk.up == "LATERAL" and i + 1 < len(t) and t[i + 1].up == "VIEW":
                j = i + 2
                outer = j < len(t) and t[j].up == "OUTER"
                j += 1 if outer else 0
                end = self._join_end(tt, j)
                body = t[j:end]
                k = next((x for x, b in enumerate(body) if b.kind == "("), len(body))     # explode(…) 다음이 별칭
                after = body[_close_in(body, k) + 1:] if k < len(body) else []
                alias = unquote(after[0]) if after and after[0].kind in ("word", "qid") and after[0].up != "AS" else ""
                out.append(self._source("lateral", span_text(body), alias, "LATERAL VIEW" + (" OUTER" if outer else ""),
                                        text=span_text(body)))
                i = end
                continue
            if tk.up in JOIN_WORDS or tk.up in ("JOIN", "STRAIGHT_JOIN"):
                words: List[str] = []
                j = i
                while j < len(t) and t[j].up in JOIN_WORDS:
                    words.append(t[j].up)
                    j += 1
                if j < len(t) and t[j].up in ("JOIN", "STRAIGHT_JOIN"):
                    join = _join_type(words)
                    i = j + 1
                    continue
                if j < len(t) and t[j].up == "APPLY":     # CROSS/OUTER APPLY (SQL Server)
                    join = " ".join(words) + " APPLY"
                    i = j + 1
                    continue
            src, i = self.table_ref(tt, i)
            if src is None:
                i += 1
                continue
            src["join"] = join if out or join not in ("", ",") else ""
            join = ""
            if i < len(t) and t[i].up == "ON":
                end = self._join_end(tt, i + 1)
                src["on"] = self.conditions(t[i + 1:end])
                i = end
            elif i < len(t) and t[i].up == "USING" and i + 1 < len(t) and t[i + 1].kind == "(":
                j = tt.close(i + 1)
                src["using"] = [span_text(c) for c in split_top(t[i + 2:j]) if c]
                i = j + 1
            if src["kind"] == "group":              # (a JOIN b ON …) 묶음 — 펼치고, 묶음의 조인 · ON 은 첫 항목에
                inner = src.pop("group")
                if inner:
                    inner[0]["join"] = src["join"]
                    inner[0]["on"] = inner[0]["on"] + src["on"]
                    inner[0]["using"] = inner[0]["using"] + src["using"]
                    out += inner
            else:
                out.append(src)
        if out:
            out[0]["join"] = ""
        return out

    def _join_end(self, tt: Toks, i: int) -> int:
        """ON 조건 · LATERAL VIEW 가 끝나는 곳 — 괄호 밖의 , · 조인 키워드 · LATERAL VIEW"""
        t = tt.t
        while i < len(t):
            tk = t[i]
            if tk.kind == "(":
                i = tt.close(i) + 1
                continue
            if tk.kind == ",":
                return i
            if tk.up in ("JOIN", "STRAIGHT_JOIN") or (tk.up in JOIN_WORDS and self._starts_join(t, i)):
                return i
            if tk.up == "LATERAL" and i + 1 < len(t) and t[i + 1].up == "VIEW":
                return i
            i += 1
        return i

    @staticmethod
    def _starts_join(t: Sequence[Tok], i: int) -> bool:
        j = i
        while j < len(t) and t[j].up in JOIN_WORDS:
            j += 1
        return j < len(t) and t[j].up in ("JOIN", "STRAIGHT_JOIN", "APPLY") and j > i

    def _source(self, kind: str, name: str, alias: str, join: str = "", text: str = "", pos: Tuple[int, int] = (0, 0),
                select: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {"kind": kind, "name": name, "key": name.lower() if kind in ("table", "cte") else "", "alias": alias,
                "join": join, "on": [], "using": [], "select": select, "text": text or name, "pos": list(pos)}

    def table_ref(self, tt: Toks, i: int) -> Tuple[Optional[Dict[str, Any]], int]:
        t = tt.t
        if i >= len(t):
            return None, i
        tk = t[i]
        src: Optional[Dict[str, Any]] = None
        start_i = i
        if tk.up == "LATERAL" and i + 1 < len(t):
            i += 1
            tk = t[i]
        if tk.kind == "(":
            j = tt.close(i)
            inner = t[i + 1:j]
            probe = _strip_parens(list(inner))
            if probe and probe[0].up in ("SELECT", "WITH", "VALUES"):
                sel = self.query(probe) if probe[0].up != "VALUES" else None
                src = self._source("subquery" if sel else "values", "", "", select=sel,
                                   text="(" + (span_text(probe)[:60]) + ")")
            else:
                src = self._source("group", "", "")
                src["group"] = self.sources(inner)
            i = j + 1
        elif tk.up in ("TABLE", "UNNEST") and i + 1 < len(t) and t[i + 1].kind == "(":
            j = tt.close(i + 1)
            src = self._source("function", span_text(t[i:j + 1]), "", text=span_text(t[i:j + 1]))
            i = j + 1
        elif tk.kind in ("word", "qid", "ph", "bind"):
            parts = [tk]
            j = i + 1
            while j + 1 < len(t) and t[j].kind == "." and t[j + 1].kind in ("word", "qid", "ph"):
                parts.append(t[j + 1])
                j += 2
            if j < len(t) and t[j].kind == "(":           # 테이블 함수 range(10) · json_table(…)
                k = tt.close(j)
                src = self._source("function", span_text(t[i:k + 1]), "", text=span_text(t[i:k + 1]))
                j = k + 1
            else:
                name = ".".join(unquote(p) for p in parts)
                src = self._source("table", name, "", text=span_text(t[i:j]), pos=(parts[0].start, parts[-1].end))
            if j < len(t) and t[j].kind == "bind" and t[j].text.startswith("@"):   # Oracle db link
                j += 1
            i = j
        else:
            return None, start_i + 1
        # 테이블 뒤 꼬리표: TABLESAMPLE (…) · FOR SYSTEM_TIME AS OF … · WITH (NOLOCK)
        while i < len(t):
            if t[i].up == "TABLESAMPLE" and i + 1 < len(t) and t[i + 1].kind == "(":
                i = tt.close(i + 1) + 1
            elif t[i].up == "WITH" and i + 1 < len(t) and t[i + 1].kind == "(":
                i = tt.close(i + 1) + 1
            else:
                break
        if i < len(t) and t[i].up == "AS":
            i += 1
        if i < len(t) and t[i].kind in ("word", "qid") and t[i].up not in ALIAS_STOP:
            src["alias"] = unquote(t[i])
            i += 1
            if i < len(t) and t[i].kind == "(":           # 별칭(컬럼, …)
                i = tt.close(i) + 1
        if src["kind"] in ("table", "function", "subquery", "values"):
            src["text"] = src["text"] + (" " + src["alias"] if src["alias"] else "")
        return src, i

    # ── 문장
    def statement(self, toks: List[Tok]) -> Dict[str, Any]:
        st: Dict[str, Any] = {"kind": "other", "target": "", "target_key": "", "select": None, "ctes": [],
                              "set": [], "where": [], "using": None, "text": span_text(toks), "error": "", "note": ""}
        t = toks
        if t and t[0].up == "EXPLAIN":
            k = 1
            while k < len(t) and t[k].up in ("ANALYZE", "EXTENDED", "FORMATTED", "VERBOSE", "PLAN", "FOR", "LOGICAL"):
                k += 1
            t = t[k:]
            st["note"] = "EXPLAIN"
        if t and t[0].up == "WITH":
            ctes, rest = self.with_list(t)
            st["ctes"] = ctes
            t = rest
        if not t:
            return st
        head = t[0].up
        tt = Toks(t)
        if head in ("SELECT", "(", "VALUES") or t[0].kind == "(":
            if head == "VALUES":
                st["kind"] = "values"
                return st
            st["kind"] = "select"
            st["select"] = self.query(t)
        elif head == "INSERT" or (head == "UPSERT") or (head == "REPLACE" and len(t) > 1 and t[1].up == "INTO"):
            st["kind"] = "insert"
            i = 1
            while i < len(t) and t[i].up in ("INTO", "OVERWRITE", "TABLE", "IGNORE", "ALL"):
                i += 1
            name, i = self._name(tt, i)
            st["target"], st["target_key"] = name, name.lower()
            while i < len(t) and t[i].up not in ("SELECT", "WITH", "VALUES", "(", "FROM"):
                i = tt.close(i + 1) + 1 if t[i].up == "PARTITION" and i + 1 < len(t) and t[i + 1].kind == "(" else i + 1
            if i < len(t) and t[i].kind == "(":           # (컬럼 목록) 또는 (SELECT …)
                probe = t[i + 1] if i + 1 < len(t) else None
                if probe is None or probe.up not in ("SELECT", "WITH"):
                    i = tt.close(i) + 1
            if i < len(t) and t[i].up in ("SELECT", "WITH", "(", "FROM"):
                st["select"] = self.query(t[i:]) if t[i].up != "FROM" else self.query(t[i:])
        elif head == "CREATE":
            i = 1
            words = []
            while i < len(t) and t[i].up in ("OR", "REPLACE", "GLOBAL", "LOCAL", "TEMP", "TEMPORARY", "VOLATILE",
                                             "EXTERNAL", "TRANSIENT", "UNLOGGED", "MULTISET", "SET", "MATERIALIZED",
                                             "SECURE", "TABLE", "VIEW"):
                words.append(t[i].up)
                i += 1
            if "TABLE" not in words and "VIEW" not in words:
                st["note"] = "CREATE " + " ".join(words)
                return st
            st["kind"] = "create"
            st["note"] = "VIEW" if "VIEW" in words else ("TEMP" if {"TEMP", "TEMPORARY", "VOLATILE"} & set(words) else "")
            if i + 2 < len(t) and t[i].up == "IF" and t[i + 1].up == "NOT" and t[i + 2].up == "EXISTS":
                i += 3
            name, i = self._name(tt, i)
            st["target"], st["target_key"] = name, name.lower()
            depth = 0
            while i < len(t):                                 # 괄호 밖의 AS (SELECT | WITH | ( ) — 저장 옵션은 건너뛴다
                if t[i].kind == "(":
                    i = tt.close(i) + 1
                    continue
                if t[i].up == "AS" and i + 1 < len(t) and t[i + 1].up in ("SELECT", "WITH", "("):
                    st["select"] = self.query(t[i + 1:])
                    break
                if t[i].up in ("SELECT", "WITH") and depth == 0:
                    st["select"] = self.query(t[i:])
                    break
                if t[i].up == "LIKE" and i + 1 < len(t):
                    like, _ = self._name(tt, i + 1)
                    st["note"] = (st["note"] + " LIKE " + like).strip()
                i += 1
        elif head == "UPDATE":
            st["kind"] = "update"
            name, i = self._name(tt, 1)
            st["target"], st["target_key"] = name, name.lower()
            cl = dict(self.clauses_generic(t[i:], ("SET", "FROM", "WHERE")))
            st["set"] = [span_text(p) for p in split_top(cl.get("SET", [])) if p]
            if cl.get("FROM"):
                st["using"] = {"sources": self.sources(cl["FROM"])}
            st["where"] = self.conditions(cl.get("WHERE", []))
        elif head == "DELETE":
            st["kind"] = "delete"
            i = 1
            if i < len(t) and t[i].up == "FROM":
                i += 1
            name, i = self._name(tt, i)
            if i < len(t) and t[i].up == "FROM":              # DELETE t FROM t JOIN …
                name2, i = self._name(tt, i + 1)
                name = name or name2
            st["target"], st["target_key"] = name, name.lower()
            cl = dict(self.clauses_generic(t[i:], ("USING", "WHERE")))
            if cl.get("USING"):
                st["using"] = {"sources": self.sources(cl["USING"])}
            st["where"] = self.conditions(cl.get("WHERE", []))
        elif head == "MERGE":
            st["kind"] = "merge"
            i = 1
            if i < len(t) and t[i].up == "INTO":
                i += 1
            name, i = self._name(tt, i)
            st["target"], st["target_key"] = name, name.lower()
            while i < len(t) and t[i].up != "USING":
                i += 1
            if i < len(t):
                src, j = self.table_ref(tt, i + 1)
                if src is not None:
                    src["join"] = "USING"
                    on_end = j
                    if j < len(t) and t[j].up == "ON":
                        k = j + 1
                        while k < len(t) and t[k].up != "WHEN":
                            k = tt.close(k) + 1 if t[k].kind == "(" else k + 1
                        src["on"] = self.conditions(t[j + 1:k])
                        on_end = k
                    st["using"] = {"sources": [src]}
                    st["set"] = [span_text(t[on_end:])[:120]] if on_end < len(t) else []
        elif head in ("DROP", "TRUNCATE"):
            st["kind"] = head.lower()
            i = 1
            while i < len(t) and t[i].up in ("TABLE", "VIEW", "IF", "EXISTS", "TEMPORARY", "MATERIALIZED", "PURGE"):
                i += 1
            name, _ = self._name(tt, i)
            st["target"], st["target_key"] = name, name.lower()
        else:
            st["note"] = head
        return st

    def clauses_generic(self, toks: Sequence[Tok], names: Sequence[str]) -> List[Tuple[str, List[Tok]]]:
        out: List[Tuple[str, List[Tok]]] = [("", [])]
        depth = 0
        for t in toks:
            if t.kind == "(":
                depth += 1
            elif t.kind == ")":
                depth -= 1
            elif depth == 0 and t.up in names:
                out.append((t.up, []))
                continue
            out[-1][1].append(t)
        return out

    def _name(self, tt: Toks, i: int) -> Tuple[str, int]:
        """점으로 이은 이름 하나 (a.b.c · `a`.b · {schema}.t)"""
        t = tt.t
        if i >= len(t) or t[i].kind not in ("word", "qid", "ph", "bind"):
            return "", i
        parts = [t[i]]
        j = i + 1
        while j + 1 < len(t) and t[j].kind == "." and t[j + 1].kind in ("word", "qid", "ph"):
            parts.append(t[j + 1])
            j += 2
        return ".".join(unquote(p) for p in parts), j


def _close_in(toks: Sequence[Tok], k: int) -> int:
    return _match_map(toks).get(k, len(toks))


def _join_type(words: Sequence[str]) -> str:
    """LEFT OUTER → LEFT · (없음) → INNER · LEFT SEMI · CROSS · NATURAL LEFT …"""
    w = [x for x in words if x not in ("OUTER", "GLOBAL", "ANY", "ASOF")]
    if not w or w == ["INNER"]:
        return "INNER"
    return " ".join(w)


# ─────────────────────────────────────────────────────────────── 03 읽는 테이블 · 쓰는 테이블 · 자리

def _walk_refs(sel: Optional[Dict[str, Any]], at: Optional[List[Any]], out: List[Tuple[Dict[str, Any], List[Any]]]) -> None:
    """SELECT 안의 테이블 참조 → (source, 자리). 자리는 가장 바깥 SELECT 의 줄: ["src", i] · ["where", i] · …"""
    if not sel:
        return
    for c in sel.get("ctes", []):
        _walk_refs(c["select"], at or ["with", c["key"]], out)
    for i, s in enumerate(sel.get("sources", [])):
        a = at or ["src", i]
        if s["kind"] in ("table", "cte"):
            out.append((s, a))
        elif s["kind"] == "subquery":
            _walk_refs(s["select"], a, out)
        for c in s.get("on", []):
            for sub in c["subs"]:
                _walk_refs(sub, a, out)
    for key in ("where", "having"):
        for i, c in enumerate(sel.get(key, [])):
            for sub in c["subs"]:
                _walk_refs(sub, at or [key, i], out)
    for s in sel.get("subs", []):
        _walk_refs(s["select"], at or ["select", 0], out)
    for k, u in enumerate(sel.get("union", [])):
        _walk_refs(u["select"], at or ["union", k], out)


def _mark_ctes(sel: Optional[Dict[str, Any]], names: Set[str]) -> None:
    """CTE 이름을 가리키는 FROM 항목은 kind "cte" (진짜 테이블이 아님)"""
    if not sel:
        return
    names = names | {c["key"] for c in sel.get("ctes", [])}
    for c in sel.get("ctes", []):
        _mark_ctes(c["select"], names)
    for s in sel.get("sources", []):
        if s["kind"] == "table" and s["key"] in names:
            s["kind"] = "cte"
        if s["kind"] == "subquery":
            _mark_ctes(s["select"], names)
        for c in s.get("on", []):
            for sub in c["subs"]:
                _mark_ctes(sub, names)
    for key in ("where", "having"):
        for c in sel.get(key, []):
            for sub in c["subs"]:
                _mark_ctes(sub, names)
    for s in sel.get("subs", []):
        _mark_ctes(s["select"], names)
    for u in sel.get("union", []):
        _mark_ctes(u["select"], names)


AT_ORDER = ["src", "using", "where", "having", "select", "union", "with", "head"]


def statement_io(st: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """문장 하나 → (읽는 것 [{key, name, at: [자리…]}], 쓰는 것 [{key, name}])
    CTE 안에서 읽은 테이블은 그 CTE 를 쓰는 자리(바깥 FROM 줄)에 붙는다."""
    top = {"ctes": st.get("ctes", []), "sources": [], "where": [], "having": [], "subs": [], "union": []}
    main = st.get("select")
    names = {c["key"] for c in st.get("ctes", [])}
    _mark_ctes(main, names)
    for c in st.get("ctes", []):
        _mark_ctes(c["select"], names)
    refs: List[Tuple[Dict[str, Any], List[Any]]] = []
    _walk_refs(main, None, refs)
    extra = st.get("using") or {}
    for s in extra.get("sources", []):
        if s["kind"] == "subquery":
            _walk_refs(s["select"], ["using", 0], refs)
        elif s["kind"] == "table":
            refs.append((s, ["using", 0]))
        for c in s.get("on", []):
            for sub in c["subs"]:
                _walk_refs(sub, ["using", 0], refs)
    for i, c in enumerate(st.get("where", [])):
        for sub in c["subs"]:
            _walk_refs(sub, ["where", i], refs)
    # CTE → 쓰이는 자리
    cte_at: Dict[str, List[Any]] = {}
    for s, a in refs:
        if s["kind"] == "cte" and s["key"] not in cte_at:
            cte_at[s["key"]] = a
    body: Dict[str, List[Tuple[Dict[str, Any], List[Any]]]] = {}
    for c in top["ctes"]:
        r: List[Tuple[Dict[str, Any], List[Any]]] = []
        _walk_refs(c["select"], ["with", c["key"]], r)
        body[c["key"]] = r

    def where_is(key: str, seen: Set[str]) -> List[Any]:
        if key in cte_at:
            return cte_at[key]
        seen = seen | {key}
        for other, r in body.items():
            if other in seen:
                continue
            if any(s["kind"] == "cte" and s["key"] == key for s, _ in r):
                return where_is(other, seen)
        return ["with", key]

    reads: Dict[str, Dict[str, Any]] = {}

    def add(s: Dict[str, Any], a: List[Any]) -> None:
        r = reads.setdefault(s["key"], {"key": s["key"], "name": s["name"], "at": []})
        if a not in r["at"]:
            r["at"].append(a)

    for s, a in refs:
        if s["kind"] == "table" and a[0] != "with":
            add(s, a)
    for key, r in body.items():
        for s, _a in r:
            if s["kind"] == "table":
                add(s, where_is(key, set()))
    for r in reads.values():         # 자리 순서: FROM 줄 먼저 (첫 자리가 흐름도의 간선이 붙는 곳)
        r["at"].sort(key=lambda a: (AT_ORDER.index(a[0]) if a[0] in AT_ORDER else 9, str(a[1:])))
    writes = [{"key": st["target_key"], "name": st["target"]}] \
        if st.get("target") and st["kind"] in ("insert", "create", "update", "delete", "merge") else []
    return list(reads.values()), writes


_FALLBACK_RE = re.compile(r"\b(?:FROM|JOIN|USING|INTO|TABLE|UPDATE)\s+([A-Za-z_{`\"\u0080-\uffff][\w.{}`\"$\u0080-\uffff]*)", re.I)


def _fallback_reads(text: str) -> List[Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for m in _FALLBACK_RE.finditer(text):
        name = m.group(1).replace("`", "").replace('"', "")
        if name.upper() in KEYWORDS or name.startswith("("):
            continue
        out.setdefault(name.lower(), {"key": name.lower(), "name": name, "at": [["head", 0]]})
    return list(out.values())


# ─────────────────────────────────────────────────────────────── 04 바깥에 내주는 것

def split_statements(toks: Sequence[Tok]) -> List[List[Tok]]:
    """괄호 밖의 ; 로 문장을 나눈다 (공백 · 주석 포함 토큰)"""
    out: List[List[Tok]] = [[]]
    depth = 0
    for t in toks:
        if t.kind == "(":
            depth += 1
        elif t.kind == ")":
            depth = max(0, depth - 1)
        elif t.kind == ";" and depth == 0:
            out.append([])
            continue
        out[-1].append(t)
    return out


_LEAD_RE = re.compile(r"^(?:\s+|--[^\n]*(?:\n|$)|/\*.*?\*/)+", re.S)
_HEAD_RE = re.compile(r"(select|with|insert|upsert|replace|create|merge|update|delete|drop|truncate|explain)\b", re.I)
_SIGNAL_RE = re.compile(r"[\n*,.=()'\"]|\b(?:WHERE|JOIN|GROUP\s+BY|ORDER\s+BY|LIMIT|UNION|DISTINCT|AS)\b", re.I)


def looks_like_sql(text: str) -> bool:
    """문자열이 SQL 같은지 — 파이썬 쪽에서 '이 호출이 쿼리인가' 를 가를 때 쓴다.
    영어 문장('Select files from the list')과 가르려고: 첫 낱말이 전부 대문자 · 전부 소문자이거나, SQL 기호 · 절이 있어야 한다"""
    s = _LEAD_RE.sub("", text or "")
    m = _HEAD_RE.match(s)
    if not m:
        return False
    word, body = m.group(1), s[m.end():]
    kw = word.upper()
    strong = word in (kw, kw.lower()) or bool(_SIGNAL_RE.search(s))

    def has(pat: str, where: str = body) -> bool:
        return bool(re.search(pat, where, re.I))

    if kw == "SELECT":
        return has(r"\bFROM\b") and strong
    if kw == "WITH":
        return has(r"\bAS\s*\(") and has(r"\bSELECT\b")
    if kw == "EXPLAIN":
        return looks_like_sql(body)
    if kw in ("INSERT", "UPSERT"):
        return has(r"^\s+(?:INTO|OVERWRITE)\b")
    if kw == "REPLACE":
        return has(r"^\s+INTO\b")
    if kw == "CREATE":
        return has(r"\b(?:TABLE|VIEW)\b", body[:120]) and strong
    if kw == "MERGE":
        return has(r"^\s+INTO\b") and has(r"\bUSING\b")
    if kw == "UPDATE":
        return has(r"\bSET\b") and strong and not has(r"^\s+(?:the|a|an|your|my)\b")
    if kw == "DELETE":
        return has(r"^\s+FROM\b") and strong
    return has(r"^\s+(?:TABLE|VIEW)\b")         # DROP · TRUNCATE


def parse_sql(text: str, known: Optional[Set[str]] = None) -> Dict[str, Any]:
    """SQL 글 → 문장들 · 읽는/쓰는 테이블. 예외를 던지지 않는다"""
    result: Dict[str, Any] = {"stmts": [], "reads": [], "writes": [], "error": ""}
    try:
        all_toks = tokens(text or "")
    except Exception as e:     # 토큰에서 실패하는 일은 없어야 하지만, 흐름도는 멈추지 않는다
        result["error"] = f"SQL 을 읽지 못했습니다 ({e.__class__.__name__})"
        result["reads"] = _fallback_reads(text or "")
        return result
    p = Parser(known)
    reads: Dict[str, Dict[str, Any]] = {}
    writes: Dict[str, Dict[str, Any]] = {}
    for n, part in enumerate(split_statements(all_toks)):
        sig = [t for t in part if t.kind not in ("ws", "com")]
        if not sig:
            continue
        try:
            st = p.statement(sig)
            r, w = statement_io(st)
        except Exception as e:    # 모르는 모양 — 글 그대로 두고 정규식으로 테이블만
            st = {"kind": "other", "target": "", "target_key": "", "select": None, "ctes": [], "set": [], "where": [],
                  "using": None, "text": span_text(sig), "error": f"구문을 다 읽지 못했습니다 ({e.__class__.__name__})",
                  "note": ""}
            r, w = _fallback_reads(st["text"]), []
        if st["kind"] == "other" and not r:
            r = _fallback_reads(st["text"])
        st["n"] = len(result["stmts"])
        st["reads"], st["writes"] = r, w
        st["span"] = [sig[0].start, sig[-1].end]
        result["stmts"].append(st)
        for x in r:
            rr = reads.setdefault(x["key"], {"key": x["key"], "name": x["name"], "at": []})
            for a in x["at"]:
                a2 = [st["n"]] + list(a)
                if a2 not in rr["at"]:
                    rr["at"].append(a2)
        for x in w:
            writes.setdefault(x["key"], dict(x, stmt=st["n"]))
    result["reads"] = list(reads.values())
    result["writes"] = list(writes.values())
    return result


def table_positions(stmts: Sequence[Dict[str, Any]]) -> List[Tuple[int, int]]:
    """원문에서 테이블 이름이 있는 자리 (색칠용)"""
    out: List[Tuple[int, int]] = []

    def walk(sel: Optional[Dict[str, Any]]) -> None:
        if not sel:
            return
        for c in sel.get("ctes", []):
            walk(c["select"])
        for s in sel.get("sources", []):
            if s["kind"] == "table" and s.get("pos") and s["pos"][1] > s["pos"][0]:
                out.append((s["pos"][0], s["pos"][1]))
            if s["kind"] == "subquery":
                walk(s["select"])
            for c in s.get("on", []):
                for sub in c["subs"]:
                    walk(sub)
        for key in ("where", "having"):
            for c in sel.get(key, []):
                for sub in c["subs"]:
                    walk(sub)
        for s in sel.get("subs", []):
            walk(s["select"])
        for u in sel.get("union", []):
            walk(u["select"])

    for st in stmts:
        for c in st.get("ctes", []):
            walk(c["select"])
        walk(st.get("select"))
        for s in (st.get("using") or {}).get("sources", []):
            if s["kind"] == "table" and s.get("pos"):
                out.append((s["pos"][0], s["pos"][1]))
    return sorted(set(out))


def sql_spans(text: str, stmts: Optional[Sequence[Dict[str, Any]]] = None) -> List[List[str]]:
    """원문 전체를 [글, 종류] 로 — 화면이 색칠한다. 종류: kw str num com ph bind tbl id op ''"""
    toks = tokens(text or "")
    tbl = table_positions(stmts or [])
    out: List[List[str]] = []
    ti = 0
    for t in toks:
        while ti < len(tbl) and tbl[ti][1] <= t.start:
            ti += 1
        in_tbl = ti < len(tbl) and tbl[ti][0] <= t.start < tbl[ti][1]
        if t.kind == "word":
            cls = "tbl" if in_tbl else ("kw" if t.up in KEYWORDS or t.up in AGGREGATES else "id")
        elif t.kind == "qid":
            cls = "tbl" if in_tbl else "id"
        elif t.kind == "ph":
            cls = "ph"
        elif t.kind in ("str", "num", "bind"):
            cls = t.kind
        elif t.kind == "com":
            cls = "com"
        elif t.kind == ".":
            cls = "tbl" if in_tbl else "op"
        elif t.kind in ("op", "(", ")", ",", ";"):
            cls = "op"
        else:
            cls = ""
        if out and out[-1][1] == cls:
            out[-1][0] += t.text
        else:
            out.append([t.text, cls])
    return out
