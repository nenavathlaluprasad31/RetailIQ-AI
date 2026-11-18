
import os
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
engine = create_engine(os.environ["DATABASE_URL"])


def main():
    print("Reading cleaned dataset...")

    df = pd.read_parquet(
        "data/processed/transactions.parquet"
    )

    print(f"Total records: {len(df):,}")

    df["date_key"] = pd.to_datetime(
        df["invoice_date"]
    ).dt.date

    df["product_key"] = df["stock_code"].astype(str)
    df["customer_key"] = df["customer_id"].astype("string")
    df["country_key"] = df["country"].astype(str)
    df["quantity"] = df["quantity"].astype(int)

    dim_date = df[["date_key"]].drop_duplicates()

    dim_product = df[
        ["product_key", "description"]
    ].drop_duplicates(subset=["product_key"])

    dim_customer = df[
        ["customer_key"]
    ].dropna().drop_duplicates()

    dim_country = df[
        ["country_key"]
    ].drop_duplicates()

    fact_sales = df[
        [
            "invoice",
            "date_key",
            "invoice_date",
            "product_key",
            "customer_key",
            "country_key",
            "quantity",
            "unit_price",
            "line_amount",
            "is_return",
            "is_outlier",
        ]
    ].copy()

    tables = {
        "dim_date": dim_date,
        "dim_product": dim_product,
        "dim_customer": dim_customer,
        "dim_country": dim_country,
        "fact_sales": fact_sales,
    }

    with engine.begin() as conn:

        # Refresh existing retail data atomically
        conn.execute(text("""
            TRUNCATE TABLE
                retail.fact_sales,
                retail.dim_date,
                retail.dim_product,
                retail.dim_customer,
                retail.dim_country
            RESTART IDENTITY
        """))

        for name, data in tables.items():
            print(f"Loading {name}...")

            data.to_sql(
                name,
                conn,
                schema="retail",
                if_exists="append",
                index=False,
                chunksize=2000,
                method="multi",
            )

            print(f"{name}: {len(data):,} rows loaded")

        count = conn.execute(text(
            "SELECT COUNT(*) FROM retail.fact_sales"
        )).scalar()

        if count != len(df):
            raise RuntimeError("Row count mismatch")

    print("DATA LOADING COMPLETED SUCCESSFULLY")
    print(f"Verified sales records: {count:,}")

    engine.dispose()


if __name__ == "__main__":
    main()

