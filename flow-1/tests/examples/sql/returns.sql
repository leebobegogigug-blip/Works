-- 반품 (지어낸 예시)
SELECT r.order_id, r.product_id, r.qty AS return_qty, r.reason
FROM dw.returns r
WHERE r.return_dt >= '2026-09-01'
  AND r.reason <> 'TEST'
