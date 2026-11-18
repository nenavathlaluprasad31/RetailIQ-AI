CREATE OR REPLACE VIEW retail.monthly_sales AS
SELECT date_trunc('month',date_key)::date AS month, SUM(line_amount) AS net_revenue,
 COUNT(DISTINCT invoice) FILTER (WHERE NOT is_return AND unit_price>0) AS orders
FROM retail.fact_sales GROUP BY 1;
SELECT *, (net_revenue-LAG(net_revenue) OVER (ORDER BY month))/NULLIF(LAG(net_revenue) OVER (ORDER BY month),0)*100 AS mom_pct FROM retail.monthly_sales ORDER BY month;
WITH customer_orders AS (SELECT customer_key,COUNT(DISTINCT invoice) AS orders FROM retail.fact_sales WHERE NOT is_return AND unit_price>0 AND customer_key IS NOT NULL GROUP BY 1)
SELECT AVG((orders>1)::int)*100 AS repeat_rate_pct FROM customer_orders;
SELECT p.product_key,p.description,SUM(f.line_amount) AS revenue,DENSE_RANK() OVER(ORDER BY SUM(f.line_amount) DESC) AS rank FROM retail.fact_sales f JOIN retail.dim_product p ON f.product_key=p.product_key GROUP BY 1,2 ORDER BY rank LIMIT 20;
