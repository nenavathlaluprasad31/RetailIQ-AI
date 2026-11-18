import os
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import joblib

from dotenv import load_dotenv
from sqlalchemy import create_engine

from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

load_dotenv()
engine = create_engine(os.environ["DATABASE_URL"])

output = Path("reports/forecast")
output.mkdir(parents=True, exist_ok=True)

Path("models").mkdir(exist_ok=True)

# Get daily revenue from PostgreSQL
query = """
SELECT invoice_date::date AS date,
       SUM(line_amount) AS revenue
FROM retail.fact_sales
GROUP BY invoice_date::date
ORDER BY date;
"""

df = pd.read_sql(query, engine)
engine.dispose()

df["date"] = pd.to_datetime(df["date"])
df = df.set_index("date").sort_index()
df = df.asfreq("D", fill_value=0)

print("Total days:", len(df))
print("Total revenue:", round(df["revenue"].sum(), 2))

# Create features from previous sales
def create_features(data):

    data = data.copy()

    data["day"] = data.index.day
    data["month"] = data.index.month
    data["day_of_week"] = data.index.dayofweek
    data["weekend"] = (data.index.dayofweek >= 5).astype(int)

    for lag in [1, 7, 14, 30]:
        data[f"lag_{lag}"] = data["revenue"].shift(lag)

    data["rolling_7"] = data["revenue"].shift(1).rolling(7).mean()
    data["rolling_30"] = data["revenue"].shift(1).rolling(30).mean()

    return data


sales = create_features(df).dropna()

features = [
    "day", "month", "day_of_week", "weekend",
    "lag_1", "lag_7", "lag_14", "lag_30",
    "rolling_7", "rolling_30"
]

# Split data in chronological order
split = int(len(sales) * 0.8)

train = sales.iloc[:split]
test = sales.iloc[split:]

X_train = train[features]
y_train = train["revenue"]

X_test = test[features]
y_test = test["revenue"]

print("Training days:", len(train))
print("Testing days:", len(test))

models = {
    "Linear Regression": LinearRegression(),

    "Random Forest": RandomForestRegressor(
        n_estimators=200,
        max_depth=10,
        random_state=42
    ),

    "Gradient Boosting": GradientBoostingRegressor(
        n_estimators=150,
        learning_rate=0.05,
        random_state=42
    )
}

results = []

# Train and compare models
for name, model in models.items():

    model.fit(X_train, y_train)
    pred = model.predict(X_test)

    mae = mean_absolute_error(y_test, pred)
    rmse = np.sqrt(mean_squared_error(y_test, pred))

    results.append({
        "model": name,
        "MAE": mae,
        "RMSE": rmse
    })

    print(name, "completed")

results = pd.DataFrame(results)
results = results.sort_values("RMSE")

print("\nModel Comparison:")
print(results.round(2).to_string(index=False))

best_name = results.iloc[0]["model"]
best_model = models[best_name]

print("\nBest model:", best_name)

# Actual vs predicted revenue
pred = best_model.predict(X_test)

plt.figure(figsize=(13, 6))
plt.plot(test.index, y_test, label="Actual Revenue")
plt.plot(test.index, pred, label="Predicted Revenue")

plt.title("Actual vs Predicted Sales")
plt.xlabel("Date")
plt.ylabel("Revenue (GBP)")
plt.legend()
plt.tight_layout()
plt.savefig(output / "actual_vs_predicted.png")
plt.close()

# Compare model errors
results.set_index("model")[["MAE", "RMSE"]].plot(
    kind="bar", figsize=(10, 6)
)

plt.title("Forecasting Model Comparison")
plt.ylabel("Error")
plt.xticks(rotation=15)
plt.tight_layout()
plt.savefig(output / "model_comparison.png")
plt.close()

# Retrain using all available historical data
best_model.fit(sales[features], sales["revenue"])

history = df.copy()
forecast = []

# Predict revenue for the next 30 days
for i in range(30):

    next_date = history.index[-1] + pd.Timedelta(days=1)

    history.loc[next_date, "revenue"] = np.nan

    future = create_features(history)
    row = future.loc[[next_date], features]

    prediction = float(best_model.predict(row)[0])

    history.loc[next_date, "revenue"] = prediction

    forecast.append({
        "date": next_date,
        "predicted_revenue": round(prediction, 2)
    })

forecast = pd.DataFrame(forecast)

print("\nNext 30 Days Forecast:")
print(forecast.to_string(index=False))

print(
    "\nExpected revenue:",
    round(forecast["predicted_revenue"].sum(), 2),
    "GBP"
)

# Plot future sales
plt.figure(figsize=(13, 6))

plt.plot(
    df.index[-90:],
    df["revenue"].tail(90),
    label="Historical Revenue"
)

plt.plot(
    forecast["date"],
    forecast["predicted_revenue"],
    label="Forecast Revenue",
    linestyle="--",
    color="green"
)

plt.title("Next 30 Days Sales Forecast")
plt.xlabel("Date")
plt.ylabel("Revenue (GBP)")
plt.legend()
plt.tight_layout()
plt.savefig(output / "future_forecast.png")
plt.close()

# Save reports and trained model
results.to_csv(output / "model_results.csv", index=False)
forecast.to_csv(output / "future_forecast.csv", index=False)

joblib.dump(best_model, "models/forecast_model.pkl")

print("\nSales forecasting completed successfully!")
