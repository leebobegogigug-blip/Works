# -*- coding: utf-8 -*-
"""flow1_sql 테스트 — SQL 을 절로 나누기 (표준 라이브러리 unittest). 예시 SQL 은 모두 지어낸 것 (RULES.md › W-12)"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import flow1_sql as fs  # noqa: E402


def stmt(sql, known=None, n=0):
    return fs.parse_sql(sql, known)["stmts"][n]


def names(items):
    return [x["name"] for x in items]


class Tokens(unittest.TestCase):
    def test_strings_comments_and_placeholders_are_single_tokens(self):
        toks = [t for t in fs.tokens("SELECT 'a;b' -- 주석; x\n, `c d`, {start}, :bind, ?, %(k)s, ${hivevar:dt} /* x */")
                if t.kind not in ("ws",)]
        kinds = [t.kind for t in toks]
        self.assertEqual(kinds, ["word", "str", "com", ",", "qid", ",", "ph", ",", "bind", ",", "bind", ",", "bind", ",",
                                 "bind", "com"])

    def test_escaped_quotes(self):
        toks = [t for t in fs.tokens("x = 'it''s' AND y = 'a\\'b' AND z = 1") if t.kind == "str"]
        self.assertEqual([t.text for t in toks], ["'it''s'", "'a\\'b'"])

    def test_span_text_normalizes_space_but_keeps_dots_and_calls(self):
        toks = [t for t in fs.tokens("a . b ,\n  COUNT( * )  -- c\n x") if t.kind not in ("ws", "com")]
        self.assertEqual(fs.span_text(toks), "a . b , COUNT( * ) x")
        toks = [t for t in fs.tokens("o.amount+COUNT(*)") if t.kind not in ("ws", "com")]
        self.assertEqual(fs.span_text(toks), "o.amount+COUNT(*)")

    def test_never_raises_on_garbage(self):
        for q in ["", ";;;", "SELECT", "(((", ")))", "'unterminated", "WITH x AS", "SELECT a FROM t LEFT JOIN u ON",
                  "select case when a and b", "MERGE INTO t USING", "\x00\x01", "SELECT 1 UNION", "INSERT INTO",
                  "select * from t where a between 1 and", "{", "}", "${", "SELECT a FROM (SELECT"]:
            r = fs.parse_sql(q)
            self.assertIsInstance(r["stmts"], list, q)


class Select(unittest.TestCase):
    SQL = """
    SELECT o.order_id, o.cust_id, SUM(i.qty * i.price) AS amount, COUNT(*) cnt,
           ROW_NUMBER() OVER (PARTITION BY o.cust_id ORDER BY o.order_dt DESC) rn
    FROM dw.orders o
    LEFT JOIN dw.order_items i ON o.order_id = i.order_id AND i.qty > 0
    JOIN dw.customers c USING (cust_id)
    WHERE o.order_dt BETWEEN '{start}' AND '{end}'
      AND o.status IN ('PAID', 'SHIPPED')
    GROUP BY o.order_id, o.cust_id
    HAVING SUM(i.qty) > 10
    ORDER BY amount DESC
    LIMIT 100
    """

    def test_clauses(self):
        sel = stmt(self.SQL, {"start", "end"})["select"]
        self.assertEqual([(c["expr"], c["alias"]) for c in sel["columns"]],
                         [("o.order_id", ""), ("o.cust_id", ""), ("SUM(i.qty * i.price)", "amount"), ("COUNT(*)", "cnt"),
                          ("ROW_NUMBER() OVER (PARTITION BY o.cust_id ORDER BY o.order_dt DESC)", "rn")])
        self.assertEqual([c["agg"] for c in sel["columns"]], [False, False, True, True, False])
        self.assertTrue(sel["columns"][4]["win"])
        self.assertEqual([(s["name"], s["alias"], s["join"]) for s in sel["sources"]],
                         [("dw.orders", "o", ""), ("dw.order_items", "i", "LEFT"), ("dw.customers", "c", "INNER")])
        self.assertEqual([c["text"] for c in sel["sources"][1]["on"]], ["o.order_id = i.order_id", "i.qty > 0"])
        self.assertEqual(sel["sources"][2]["using"], ["cust_id"])
        self.assertEqual([c["text"] for c in sel["where"]],
                         ["o.order_dt BETWEEN '{start}' AND '{end}'", "o.status IN ('PAID', 'SHIPPED')"])
        self.assertEqual(sel["where"][0]["params"], ["start", "end"])
        self.assertEqual(sel["group"], ["o.order_id", "o.cust_id"])
        self.assertEqual([c["text"] for c in sel["having"]], ["SUM(i.qty) > 10"])
        self.assertEqual((sel["order"], sel["limit"]), (["amount DESC"], "100"))

    def test_and_or_between_case_splitting(self):
        w = stmt("SELECT a FROM t WHERE x BETWEEN 1 AND 5 AND CASE WHEN a > 1 AND b < 2 THEN 1 ELSE 0 END = 1 "
                 "AND (p = 1 OR q = 2) AND r = 3")["select"]["where"]
        self.assertEqual([c["text"] for c in w], ["x BETWEEN 1 AND 5", "CASE WHEN a > 1 AND b < 2 THEN 1 ELSE 0 END = 1",
                                                  "(p = 1 OR q = 2)", "r = 3"])
        w = stmt("SELECT a FROM t WHERE a = 1 AND b = 2 OR c = 3")["select"]["where"]
        self.assertEqual([(c["text"], c["kind"]) for c in w], [("a = 1 AND b = 2 OR c = 3", "or")])   # AND 가 먼저 묶인다

    def test_implicit_join_predicates(self):
        sel = stmt("SELECT a.x FROM t1 a, t2 b WHERE a.id = b.id AND a.k = b.k(+) AND a.v > 3 AND a.id = 7")["select"]
        self.assertEqual([s["join"] for s in sel["sources"]], ["", ","])
        self.assertEqual([c["kind"] for c in sel["where"]], ["join", "join", "filter", "filter"])

    def test_join_kinds(self):
        sel = stmt("SELECT a FROM t1 FULL OUTER JOIN t2 ON t1.k = t2.k LEFT SEMI JOIN t3 ON t3.k = t1.k "
                   "CROSS JOIN t4 NATURAL JOIN t5 RIGHT OUTER JOIN t6 ON t6.k = t1.k LEFT ANTI JOIN t7 ON t7.k = t1.k")["select"]
        self.assertEqual([s["join"] for s in sel["sources"]],
                         ["", "FULL", "LEFT SEMI", "CROSS", "NATURAL", "RIGHT", "LEFT ANTI"])

    def test_parenthesized_join_group_keeps_outer_on(self):
        sel = stmt("SELECT * FROM (SELECT a FROM s.t) x JOIN (s.u u JOIN s.w w ON u.k = w.k) ON x.a = u.a")["select"]
        self.assertEqual([(s["kind"], s["name"], s["join"]) for s in sel["sources"]],
                         [("subquery", "", ""), ("table", "s.u", "INNER"), ("table", "s.w", "INNER")])
        self.assertEqual([c["text"] for c in sel["sources"][1]["on"]], ["x.a = u.a"])

    def test_union_top_fetch_distinct(self):
        sel = stmt("SELECT DISTINCT a FROM s.a UNION ALL SELECT b FROM s.b EXCEPT SELECT c FROM s.c")["select"]
        self.assertTrue(sel["distinct"])
        self.assertEqual([(u["op"], names(u["select"]["sources"])) for u in sel["union"]],
                         [("UNION ALL", ["s.b"]), ("EXCEPT", ["s.c"])])
        self.assertEqual(stmt("SELECT TOP 5 a FROM t")["select"]["limit"], "TOP 5")
        self.assertEqual(stmt("SELECT a FROM t FETCH FIRST 10 ROWS ONLY")["select"]["limit"], "10")

    def test_function_keywords_inside_parens_do_not_split_clauses(self):
        sel = stmt("SELECT EXTRACT(YEAR FROM dt) y, CAST(v AS DECIMAL(10,2)) v2, v::int, SUBSTRING(s FROM 1 FOR 2) "
                   "FROM t WHERE dt >= CURRENT_DATE - INTERVAL '7' DAY")["select"]
        self.assertEqual([c["alias"] for c in sel["columns"]], ["y", "v2", "", ""])
        self.assertEqual(names(sel["sources"]), ["t"])
        self.assertEqual(sel["where"][0]["cols"], ["dt"])       # CURRENT_DATE · DAY 는 컬럼이 아니다

    def test_quoted_and_korean_identifiers(self):
        sel = stmt('select `a`.`b` as "Col A", 매출 from `db`.`tbl` `a` where 지역 = \'서울\'')["select"]
        self.assertEqual([(c["expr"], c["alias"]) for c in sel["columns"]], [("`a`.`b`", "Col A"), ("매출", "")])
        self.assertEqual((sel["sources"][0]["name"], sel["sources"][0]["alias"]), ("db.tbl", "a"))
        self.assertEqual(sel["where"][0]["cols"], ["지역"])

    def test_dynamic_table_and_clause_placeholders(self):
        sel = stmt("SELECT {cols} FROM {schema}.orders WHERE {cond}", {"cols", "schema", "cond"})["select"]
        self.assertEqual(sel["sources"][0]["name"], "{schema}.orders")
        self.assertEqual(sel["where"][0]["params"], ["cond"])

    def test_binds_are_recorded(self):
        w = stmt("SELECT a FROM t WHERE n > :n AND m = %(m)s AND k = ${hivevar:k} AND z = ?")["select"]["where"]
        self.assertEqual([c["binds"] for c in w], [[":n"], ["%(m)s"], ["${hivevar:k}"], ["?"]])


class ReadsWrites(unittest.TestCase):
    def test_cte_tables_attach_to_the_row_that_uses_the_cte(self):
        r = fs.parse_sql("""
            WITH vip AS (SELECT cust_id FROM dw.customers WHERE grade = 'VIP'),
                 recent AS (SELECT o.* FROM dw.orders o JOIN vip v ON o.cust_id = v.cust_id)
            SELECT r.cust_id FROM recent r
            WHERE r.amount > (SELECT AVG(amount) FROM dw.orders)
              AND r.cust_id NOT IN (SELECT cust_id FROM dw.blacklist)""")
        st = r["stmts"][0]
        self.assertEqual(st["select"]["sources"][0]["kind"], "cte")
        at = {x["name"]: x["at"] for x in r["reads"]}
        self.assertEqual(at, {"dw.orders": [[0, "src", 0], [0, "where", 0]], "dw.customers": [[0, "src", 0]],
                              "dw.blacklist": [[0, "where", 1]]})

    def test_recursive_cte_is_not_a_table(self):
        r = fs.parse_sql("WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r WHERE n < 10) SELECT * FROM r")
        self.assertEqual(r["reads"], [])

    def test_insert_create_merge_update_delete_drop(self):
        r = fs.parse_sql("""
            INSERT OVERWRITE TABLE tmp.a PARTITION (dt='{dt}') SELECT * FROM dw.x LATERAL VIEW explode(items) t AS item;
            CREATE TABLE IF NOT EXISTS tmp.b STORED AS ORC AS SELECT dt, SUM(v) v FROM tmp.a GROUP BY dt;
            MERGE INTO dw.target t USING (SELECT * FROM stg.src WHERE d = ?) s ON t.id = s.id
              WHEN MATCHED THEN UPDATE SET t.v = s.v;
            UPDATE dw.acct a SET balance = 0 WHERE EXISTS (SELECT 1 FROM dw.closed c WHERE c.id = a.id);
            DELETE FROM dw.log WHERE dt < '2020-01-01';
            DROP TABLE IF EXISTS tmp.old;
            INSERT INTO tmp.c (a, b) VALUES (1, 2)""", {"dt"})
        self.assertEqual([(s["kind"], s["target"]) for s in r["stmts"]],
                         [("insert", "tmp.a"), ("create", "tmp.b"), ("merge", "dw.target"), ("update", "dw.acct"),
                          ("delete", "dw.log"), ("drop", "tmp.old"), ("insert", "tmp.c")])
        self.assertEqual(names(r["reads"]), ["dw.x", "tmp.a", "stg.src", "dw.closed"])
        self.assertEqual(names(r["writes"]), ["tmp.a", "tmp.b", "dw.target", "dw.acct", "dw.log", "tmp.c"])
        lat = r["stmts"][0]["select"]["sources"][1]
        self.assertEqual((lat["kind"], lat["join"], lat["alias"]), ("lateral", "LATERAL VIEW", "t"))

    def test_create_view_and_explain(self):
        st = stmt("CREATE OR REPLACE TEMPORARY VIEW v AS SELECT * FROM dw.x")
        self.assertEqual((st["kind"], st["target"], st["note"]), ("create", "v", "VIEW"))
        st = stmt("EXPLAIN SELECT * FROM x.y")
        self.assertEqual((st["kind"], st["note"], names(st["reads"])), ("select", "EXPLAIN", ["x.y"]))

    def test_unknown_statement_falls_back_to_regex_tables(self):
        r = fs.parse_sql("FROM dw.src INSERT OVERWRITE TABLE tmp.t SELECT a")     # Hive 다중 INSERT
        self.assertEqual(r["stmts"][0]["kind"], "other")
        self.assertIn("dw.src", names(r["reads"]))

    def test_statement_split_ignores_semicolons_in_strings_and_comments(self):
        r = fs.parse_sql("SELECT 'a;b' FROM t1; -- x;y\nSELECT 1 FROM t2 /* ; */")
        self.assertEqual(len(r["stmts"]), 2)
        self.assertEqual(names(r["reads"]), ["t1", "t2"])


class LooksLikeSql(unittest.TestCase):
    def test_sql_versus_english(self):
        yes = ["select a from b", "SELECT a FROM b", "  -- c\n WITH x AS (select 1) select * from x", "SELECT *\nFROM t",
               "Select a, b From t", "INSERT INTO t VALUES (1)", "UPDATE t SET a=1", "delete from t", "DROP TABLE x",
               "CREATE TABLE x AS SELECT 1", "MERGE INTO t USING s ON 1=1", "EXPLAIN SELECT a FROM b"]
        no = ["Select files from the list", "Select one of the options", "With this in mind", "Insert a coin",
              "update the docs set", "Delete from the list", "drop the ball", "Create a table for me", "hello", ""]
        self.assertEqual([q for q in yes if not fs.looks_like_sql(q)], [])
        self.assertEqual([q for q in no if fs.looks_like_sql(q)], [])


class Spans(unittest.TestCase):
    def test_spans_cover_text_and_mark_tables(self):
        sql = "SELECT a FROM dw.t x WHERE y = '{v}' -- c\n"
        spans = fs.sql_spans(sql, fs.parse_sql(sql)["stmts"])
        self.assertEqual("".join(t for t, _ in spans), sql)
        self.assertIn(["dw.t", "tbl"], spans)
        self.assertIn(["SELECT", "kw"], spans)
        self.assertIn(["-- c", "com"], spans)


if __name__ == "__main__":
    unittest.main()
