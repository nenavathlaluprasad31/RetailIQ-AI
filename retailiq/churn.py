import os
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import joblib

from dotenv import load_dotenv
from sqlalchemy import create_engine

from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline

from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    confusion_matrix
)

load_dotenv()
engine = create_engine(os.environ["DATABASE_URL"])

output = Path("reports/churn")
output.mkdir(parents=True, exist_ok=True)

Path("models").mkdir(exist_ok=True)

# Read customer transactions
query = """
SELECT customer_key, invoice, invoice_date,
       quantity, line_amount
FROM retail.fact_sales
WHERE customer_key IS NOT NULL
AND NOT is_return;
"""

df = pd.read_sql(query, engine)
engine.dispose()

df["invoice_date"] = pd.to_datetime(df["invoice_date"])

# Prepare customer features and churn labels
def prepare_data(cutoff):
    start = cutoff - pd.Timedelta(days=180)
    end = cutoff + pd.Timedelta(days=90)

    past = df[
        (df["invoice_date"] >= start) &
        (df["invoice_date"] < cutoff)
    ]

    future = df[
        (df["invoice_date"] >= cutoff) &
        (df["invoice_date"] < end)
    ]

    customers = past.groupby("customer_key").agg(
        last_purchase=("invoice_date", "max"),
        frequency=("invoice", "nunique"),
        monetary=("line_amount", "sum"),
        total_units=("quantity", "sum")
    )

    customers["recency"] = (
        cutoff - customers["last_purchase"]
    ).dt.days

    customers["avg_order_value"] = (
        customers["monetary"] / customers["frequency"]
    )

    active = future["customer_key"].unique()

    customers["churn"] = (
        ~customers.index.isin(active)
    ).astype(int)

    return customers.drop(columns="last_purchase")


# Split the data using dates
last_date = df["invoice_date"].max().normalize()

test_date = last_date - pd.Timedelta(days=90)
train_date = test_date - pd.Timedelta(days=90)

train = prepare_data(train_date)
test = prepare_data(test_date)

features = [
    "recency",
    "frequency",
    "monetary",
    "total_units",
    "avg_order_value"
]

X_train = train[features]
y_train = train["churn"]

X_test = test[features]
y_test = test["churn"]

print("Training customers:", len(train))
print("Testing customers:", len(test))

# Compare three classification models
models = {
    "Logistic Regression": make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=1000)
    ),

    "Random Forest": RandomForestClassifier(
        n_estimators=200,
        max_depth=10,
        random_state=42
    ),

    "Gradient Boosting": GradientBoostingClassifier(
        n_estimators=100,
        random_state=42
    )
}

results = []

for name, model in models.items():

    model.fit(X_train, y_train)

    pred = model.predict(X_test)
    prob = model.predict_proba(X_test)[:, 1]

    results.append({
        "model": name,
        "accuracy": accuracy_score(y_test, pred),
        "precision": precision_score(
            y_test, pred, zero_division=0
        ),
        "recall": recall_score(
            y_test, pred, zero_division=0
        ),
        "f1_score": f1_score(y_test, pred),
        "roc_auc": roc_auc_score(y_test, prob)
    })

    print(name, "completed")

results = pd.DataFrame(results)
results = results.sort_values("roc_auc", ascending=False)

print("\nModel Comparison:")
print(results.round(4).to_string(index=False))

best_name = results.iloc[0]["model"]
best_model = models[best_name]

print("\nBest model:", best_name)

# Compare model performance
results.set_index("model")[
    ["accuracy", "precision", "recall", "f1_score", "roc_auc"]
].plot(kind="bar", figsize=(11, 6))

plt.title("Churn Prediction - Model Comparison")
plt.ylabel("Score")
plt.xticks(rotation=15)
plt.ylim(0, 1)
plt.tight_layout()
plt.savefig(output / "model_comparison.png")
plt.close()

# Confusion matrix
pred = best_model.predict(X_test)

plt.figure(figsize=(7, 5))

sns.heatmap(
    confusion_matrix(y_test, pred),
    annot=True,
    fmt="d",
    cmap="Blues",
    xticklabels=["Active", "Churned"],
    yticklabels=["Active", "Churned"]
)

plt.xlabel("Predicted")
plt.ylabel("Actual")
plt.title("Confusion Matrix - " + best_name)
plt.tight_layout()
plt.savefig(output / "confusion_matrix.png")
plt.close()

# Save historical test predictions
test["churn_probability"] = (
    best_model.predict_proba(X_test)[:, 1]
)

test["predicted_churn"] = pred

test["risk_level"] = pd.cut(
    test["churn_probability"],
    bins=[-0.01, 0.3, 0.7, 1.0],
    labels=["Low Risk", "Medium Risk", "High Risk"]
)

results.to_csv(output / "model_results.csv", index=False)
test.to_csv(output / "churn_predictions.csv")

joblib.dump(best_model, "models/churn_model.pkl")

print("\nCustomer Risk Summary:")
print(test["risk_level"].value_counts())

print("\nChurn prediction completed successfully!")