from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

df = pd.read_parquet("data/processed/transactions.parquet")

output = Path("reports/eda")
output.mkdir(parents=True, exist_ok=True)

sns.set_theme(style="whitegrid")

print("Dataset shape:", df.shape)
print(df.head())
print(df.isnull().sum())
print(df.describe())


# Monthly sales trend
df["invoice_date"] = pd.to_datetime(df["invoice_date"])

monthly_sales = df.groupby(
    df["invoice_date"].dt.to_period("M")
)["line_amount"].sum()

plt.figure(figsize=(12, 5))
plt.plot(monthly_sales.index.astype(str),
         monthly_sales.values, marker="o")
plt.title("Monthly Revenue Trend")
plt.xlabel("Month")
plt.ylabel("Revenue (GBP)")
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig(output / "monthly_sales.png")
plt.close()


# Top 10 countries by revenue
countries = df.groupby("country")["line_amount"].sum()
countries = countries.nlargest(10)

plt.figure(figsize=(10, 6))
countries.sort_values().plot(kind="barh", color="steelblue")
plt.title("Top 10 Countries by Revenue")
plt.xlabel("Revenue (GBP)")
plt.tight_layout()
plt.savefig(output / "country_sales.png")
plt.close()


# Top 10 products excluding postage
products = df[~df["stock_code"].isin(["DOT", "POST"])]

top_products = products.groupby("description")[
    "line_amount"
].sum().nlargest(10)

plt.figure(figsize=(12, 6))
top_products.sort_values().plot(kind="barh", color="teal")
plt.title("Top 10 Products by Revenue")
plt.xlabel("Revenue (GBP)")
plt.tight_layout()
plt.savefig(output / "top_products.png")
plt.close()


# Sales and returns
returns = df["is_return"].value_counts()
returns = returns.rename(index={False: "Sales", True: "Returns"})

plt.figure(figsize=(7, 7))
plt.pie(returns.values, labels=returns.index,
        autopct="%1.1f%%", startangle=90)
plt.title("Sales vs Returns")
plt.tight_layout()
plt.savefig(output / "return_analysis.png")
plt.close()


# Correlation between numerical features
columns = ["quantity", "unit_price", "line_amount"]

plt.figure(figsize=(8, 6))
sns.heatmap(df[columns].corr(), annot=True,
            cmap="coolwarm", fmt=".2f")
plt.title("Correlation Heatmap")
plt.tight_layout()
plt.savefig(output / "correlation.png")
plt.close()

print("\nEDA completed successfully!")
print("Charts saved in:", output)