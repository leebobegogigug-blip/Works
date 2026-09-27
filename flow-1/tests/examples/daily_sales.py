"""지어낸 예시 — 9월 VIP 주문 리포트 (Flow–1 데모 · 테스트용. 테이블 · 패키지 이름은 모두 지어낸 것)"""
import os

import pandas as pd
import demo_query as dq

START = "2026-09-01"
END = "2026-09-30"
HERE = os.path.dirname(os.path.abspath(__file__))

# 01 이번 달 주문
sql_orders = f"""
SELECT o.order_id, o.cust_id, o.order_dt, o.amount, o.status
FROM dw.orders o
WHERE o.order_dt BETWEEN '{START}' AND '{END}'
  AND o.status IN ('PAID', 'SHIPPED')
"""
df_orders = dq.query(sql_orders)

# 02 VIP 고객 — 올해 누적 구매액 (WITH + JOIN)
sql_vip = """
WITH spend AS (
    SELECT cust_id, SUM(amount) AS total
    FROM dw.orders
    WHERE order_dt >= DATE '2026-01-01'
    GROUP BY cust_id
)
SELECT c.cust_id, c.name, c.grade, s.total
FROM dw.customers c
JOIN spend s ON c.cust_id = s.cust_id
WHERE c.grade IN ('GOLD', 'VIP')
  AND s.total > 1000000
"""
df_vip = dq.query(sql_vip)

# 03 주문 상세 — 01 의 결과(주문 번호)를 조건으로
order_ids = ",".join(str(x) for x in df_orders["order_id"].unique())
sql_items = """
SELECT i.order_id, i.product_id, p.category, i.qty, i.price
FROM dw.order_items i
LEFT JOIN dw.products p ON i.product_id = p.product_id
WHERE i.order_id IN ({ids})
  AND i.qty > 0
""".format(ids=order_ids)
df_items = dq.query(sql_items)

# 04 반품 — SQL 은 파일에
with open(os.path.join(HERE, "sql", "returns.sql"), encoding="utf-8") as f:
    df_returns = dq.query(f.read())

# 05 판다스로 합치기
df = df_orders.merge(df_vip, on="cust_id", how="inner")
df = pd.merge(df, df_items, on="order_id", how="left")
report = df.groupby(["order_dt", "category"], as_index=False)["amount"].sum()

# 06 임시 테이블에 쓰고 다시 읽기
dq.execute(f"""
INSERT OVERWRITE TABLE tmp.vip_daily PARTITION (dt = '{END}')
SELECT i.order_dt, p.category, SUM(i.qty * i.price) AS sales
FROM dw.order_items i
JOIN dw.products p ON i.product_id = p.product_id
GROUP BY i.order_dt, p.category
""")
df_trend = dq.query("SELECT dt, category, sales FROM tmp.vip_daily WHERE dt >= '2026-07-01' ORDER BY dt")

# 07 내보내기
report.to_csv("out/vip_daily.csv", index=False)
pd.concat([df_trend, df_returns]).to_excel("out/vip_trend.xlsx")
