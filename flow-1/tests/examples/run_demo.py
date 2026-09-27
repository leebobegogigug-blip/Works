"""지어낸 예시 — --run 테스트 · 데모용 (판다스 없이 가짜 패키지 demo_query 만)"""
import sys

import demo_query as dq
from run_helper import load_stock

orders = dq.query("SELECT order_id, amount FROM dw.orders LIMIT 5")
stock = load_stock(10)
both = orders.merge(stock)
if "--fail" in sys.argv:
    dq.query("SELECT FAIL FROM dw.nowhere")
both.to_csv("out.csv")
print("rows", orders.shape[0], stock.shape[0])
