"""지어낸 예시 — run_demo.py 가 import 하는 도우미 (--run 이 import 한 모듈의 쿼리도 재는지)"""
import demo_query as dq


def load_stock(n):
    return dq.query(f"SELECT product_id, qty FROM dw.stock LIMIT {n}")
