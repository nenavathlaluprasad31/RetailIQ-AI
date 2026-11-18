CREATE SCHEMA IF NOT EXISTS retail;
CREATE TABLE IF NOT EXISTS retail.dim_date (date_key date PRIMARY KEY);
CREATE TABLE IF NOT EXISTS retail.dim_product (product_key text PRIMARY KEY, description text NOT NULL);
CREATE TABLE IF NOT EXISTS retail.dim_customer (customer_key text PRIMARY KEY);
CREATE TABLE IF NOT EXISTS retail.dim_country (country_key text PRIMARY KEY);
CREATE TABLE IF NOT EXISTS retail.fact_sales (
 line_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 invoice text NOT NULL, date_key date NOT NULL REFERENCES retail.dim_date,
 invoice_date timestamp NOT NULL, product_key text NOT NULL REFERENCES retail.dim_product,
 customer_key text REFERENCES retail.dim_customer, country_key text NOT NULL REFERENCES retail.dim_country,
 quantity integer NOT NULL, unit_price numeric(18,4) NOT NULL CHECK(unit_price>=0),
 line_amount numeric(20,4) NOT NULL, is_return boolean NOT NULL, is_outlier boolean NOT NULL);
CREATE INDEX IF NOT EXISTS fact_sales_date ON retail.fact_sales(date_key);
CREATE INDEX IF NOT EXISTS fact_sales_customer ON retail.fact_sales(customer_key,date_key);
