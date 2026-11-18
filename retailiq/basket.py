import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from mlxtend.frequent_patterns import apriori, association_rules

df = pd.read_parquet("data/processed/transactions.parquet")

output = Path("reports/basket")
output.mkdir(parents=True, exist_ok=True)

# Keep valid purchases
sales = df[
    (~df["is_return"]) &
    (df["quantity"] > 0) &
    (df["unit_price"] > 0) &
    (df["country"] == "United Kingdom")
].copy()

# Remove postage and other non-product entries
sales = sales[sales["stock_code"].str.match(
    r"^\d{5}[A-Za-z]*$", na=False
)]

# Select frequently purchased products
top_products = sales["description"].value_counts().head(150).index
sales = sales[sales["description"].isin(top_products)]

# Prepare transaction basket
basket = pd.crosstab(
    sales["invoice"],
    sales["description"]
).astype(bool)

print("Total baskets:", len(basket))
print("Total products:", len(basket.columns))

# Find frequent itemsets
items = apriori(
    basket,
    min_support=0.01,
    use_colnames=True,
    max_len=3,
    low_memory=True
)

print("Frequent itemsets:", len(items))

# Generate association rules
rules = association_rules(
    items,
    metric="confidence",
    min_threshold=0.3
)

rules = rules[rules["lift"] > 1]
rules = rules.sort_values("lift", ascending=False)

rules = rules[
    ["antecedents", "consequents",
     "support", "confidence", "lift"]
].copy()

rules["antecedents"] = rules["antecedents"].apply(
    lambda x: ", ".join(sorted(x))
)

rules["consequents"] = rules["consequents"].apply(
    lambda x: ", ".join(sorted(x))
)

rules.to_csv(output / "association_rules.csv", index=False)

print("\nTop 10 Product Recommendations:")
print(rules.head(10).to_string(index=False))

# Visualize association rules
plt.figure(figsize=(10, 6))

plt.scatter(
    rules["support"],
    rules["confidence"],
    c=rules["lift"],
    cmap="viridis",
    alpha=0.7
)

plt.colorbar(label="Lift")
plt.xlabel("Support")
plt.ylabel("Confidence")
plt.title("Market Basket Analysis")
plt.tight_layout()
plt.savefig(output / "association_rules.png", dpi=150)
plt.close()

print("\nMarket Basket Analysis completed successfully!")