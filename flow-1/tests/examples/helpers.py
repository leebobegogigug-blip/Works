"""지어낸 예시 — 함수 · 반복 · 클래스로 쿼리를 부르는 모양 (Flow–1 테스트용)"""
import demo_query as dq
from demo_query import Client


def run(sql):
    """쿼리 한 번 — 흔한 감싸기"""
    print("running", sql[:30])
    return dq.query(sql)


def load_month(month):
    return run(f"SELECT order_id, cust_id, amount FROM dw.orders WHERE ym = '{month}'")


jan = load_month("2026-01")
feb = load_month("2026-02")

TABLES = ["dw.customers", "dw.products"]
counts = {}
for t in TABLES:
    counts[t] = dq.query(f"SELECT COUNT(*) AS n FROM {t}")

QUERIES = {
    "stock": "SELECT product_id, qty FROM dw.stock WHERE qty < 10",
    "price": "SELECT product_id, price FROM dw.price_history WHERE valid_to IS NULL",
}
frames = {}
for name, sql in QUERIES.items():
    frames[name] = dq.query(sql)


class Loader:
    def __init__(self, env="dev"):
        self.cli = Client(env)
        self.base = "SELECT cust_id, name, grade FROM dw.customers"

    def customers(self, grade):
        return self.cli.fetch(self.base + f" WHERE grade = '{grade}'")


ld = Loader()
gold = ld.customers("GOLD")
merged = jan.merge(gold, on="cust_id")
