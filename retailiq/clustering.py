import os
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import joblib

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score
from sklearn.decomposition import PCA

load_dotenv()
engine = create_engine(os.environ["DATABASE_URL"])

output = Path("reports/clustering")
output.mkdir(parents=True, exist_ok=True)

models = Path("models")
models.mkdir(exist_ok=True)

# Get customer data from PostgreSQL
query = """
SELECT customer_id, recency, frequency, monetary
FROM retail.customer_segments;
"""

df = pd.read_sql(query, engine)

df = df.dropna()
df = df[df["monetary"] > 0].copy()

print("Total customers:", len(df))

# Prepare RFM features
features = df[["recency", "frequency", "monetary"]]

# Reduce skewness in customer data
features = np.log1p(features)

scaler = StandardScaler()
X = scaler.fit_transform(features)

# Find a suitable number of clusters
inertia = []
scores = []
k_values = range(2, 11)

for k in k_values:
    model = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = model.fit_predict(X)

    inertia.append(model.inertia_)
    score = silhouette_score(X, labels)
    scores.append(score)

    print(f"K = {k}, Silhouette Score = {score:.4f}")

# Elbow method
plt.figure(figsize=(8, 5))
plt.plot(list(k_values), inertia, marker="o")
plt.xlabel("Number of Clusters")
plt.ylabel("Inertia")
plt.title("Elbow Method")
plt.grid(alpha=0.3)
plt.tight_layout()
plt.savefig(output / "elbow_method.png")
plt.close()

# Silhouette score comparison
plt.figure(figsize=(8, 5))
plt.plot(list(k_values), scores, marker="o", color="green")
plt.xlabel("Number of Clusters")
plt.ylabel("Silhouette Score")
plt.title("Silhouette Score Comparison")
plt.tight_layout()
plt.savefig(output / "silhouette_scores.png")
plt.close()

# Train the final model
best_k = list(k_values)[np.argmax(scores)]

model = KMeans(
    n_clusters=best_k,
    random_state=42,
    n_init=10
)

df["cluster"] = model.fit_predict(X)

print("\nBest number of clusters:", best_k)
print("Silhouette score:", round(max(scores), 4))

# Visualize clusters using PCA
pca = PCA(n_components=2)
points = pca.fit_transform(X)

plt.figure(figsize=(10, 6))

for cluster in range(best_k):
    mask = df["cluster"] == cluster

    plt.scatter(
        points[mask, 0],
        points[mask, 1],
        label=f"Cluster {cluster}",
        alpha=0.6,
        s=20
    )

plt.xlabel("Principal Component 1")
plt.ylabel("Principal Component 2")
plt.title("Customer Segmentation using K-Means")
plt.legend()
plt.tight_layout()
plt.savefig(output / "customer_clusters.png")
plt.close()

# Understand each customer cluster
summary = df.groupby("cluster").agg(
    customers=("customer_id", "count"),
    avg_recency=("recency", "mean"),
    avg_frequency=("frequency", "mean"),
    avg_spending=("monetary", "mean"),
    total_revenue=("monetary", "sum")
).round(2)

print("\nCustomer Cluster Summary:")
print(summary)

# Save results
df.to_csv(output / "customer_clusters.csv", index=False)
summary.to_csv(output / "cluster_summary.csv")

joblib.dump(model, models / "kmeans_model.pkl")
joblib.dump(scaler, models / "rfm_scaler.pkl")
joblib.dump(pca, models / "pca_model.pkl")

engine.dispose()

print("\nCustomer clustering completed successfully!")